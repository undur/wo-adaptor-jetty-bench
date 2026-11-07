import java.io.BufferedInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * A closed-loop HTTP/1.1 load generator: each connection sends a request, reads the whole response, and sends the next,
 * for a fixed time. ab is single-threaded and runs out of CPU long before the adaptor does; this runs every connection on
 * a thread of its own.
 *
 * <pre>
 * java Hammer.java [-c connections] [-d seconds] [-w warmup seconds] [--close] [--post kilobytes] url
 * </pre>
 *
 * --close sends "Connection: close" and opens a new connection per request. A server may also close a connection,
 * saying so with "Connection: close" or not: a reused connection that closes before a response begins is reconnected
 * and the request resent, as browsers do, and counted under resent rather than errors. Prints one line of results,
 * latencies in milliseconds.
 */
public class Hammer {

	private static int connections = 64;
	private static int seconds = 10;
	private static int warmupSeconds = 2;
	private static boolean keepAlive = true;
	private static int postKilobytes = -1;

	private static final AtomicBoolean measuring = new AtomicBoolean();
	private static final AtomicBoolean stopping = new AtomicBoolean();
	private static final AtomicLong errors = new AtomicLong();
	private static final AtomicLong non2xx = new AtomicLong();
	private static final AtomicLong bytesRead = new AtomicLong();
	private static final AtomicLong connects = new AtomicLong();
	private static final AtomicLong resent = new AtomicLong();
	private static volatile String firstError;

	public static void main( final String[] args ) throws Exception {
		String url = null;

		for( int i = 0; i < args.length; i++ ) {
			switch( args[i] ) {
				case "-c" -> connections = Integer.parseInt( args[++i] );
				case "-d" -> seconds = Integer.parseInt( args[++i] );
				case "-w" -> warmupSeconds = Integer.parseInt( args[++i] );
				case "--close" -> keepAlive = false;
				case "--post" -> postKilobytes = Integer.parseInt( args[++i] );
				default -> url = args[i];
			}
		}

		final URI uri = URI.create( url );
		final InetSocketAddress address = new InetSocketAddress( uri.getHost(), uri.getPort() );
		final byte[] request = request( uri );

		final List<Thread> threads = new ArrayList<>();
		final List<long[]> latencies = new ArrayList<>();
		final int[] counts = new int[connections];

		for( int i = 0; i < connections; i++ ) {
			final int index = i;
			latencies.add( null );

			threads.add( Thread.ofPlatform().daemon().start( () -> {
				final Latencies recorded = new Latencies();
				run( address, request, recorded );
				synchronized( latencies ) {
					latencies.set( index, recorded.values() );
				}
				counts[index] = recorded.size;
			} ) );
		}

		Thread.sleep( warmupSeconds * 1000L );
		measuring.set( true );
		final long start = System.nanoTime();
		Thread.sleep( seconds * 1000L );
		measuring.set( false );
		final double elapsed = (System.nanoTime() - start) / 1e9;
		stopping.set( true );

		// Connections still waiting on a response when time is up get 15 seconds between them to finish
		final long deadline = System.currentTimeMillis() + 15_000;

		for( final Thread thread : threads ) {
			thread.join( Math.max( 1, deadline - System.currentTimeMillis() ) );
		}

		final long[] all = latencies.stream().filter( l -> l != null ).flatMapToLong( Arrays::stream ).sorted().toArray();
		final int idle = (int)Arrays.stream( counts ).filter( n -> n == 0 ).count();

		System.out.printf( "requests=%d rps=%.0f p50=%s p90=%s p99=%s p999=%s max=%s MB/s=%.0f connects=%d resent=%d non2xx=%d errors=%d idleConnections=%d%s%n",
				all.length,
				all.length / elapsed,
				ms( all, 0.50 ), ms( all, 0.90 ), ms( all, 0.99 ), ms( all, 0.999 ), ms( all, 1.0 ),
				bytesRead.get() / elapsed / 1e6,
				connects.get(),
				resent.get(),
				non2xx.get(),
				errors.get(),
				idle,
				firstError == null ? "" : " firstError=" + firstError );
	}

	private static byte[] request( final URI uri ) {
		final String target = uri.getRawPath() + (uri.getRawQuery() == null ? "" : "?" + uri.getRawQuery());
		final StringBuilder head = new StringBuilder();
		head.append( postKilobytes >= 0 ? "POST " : "GET " ).append( target ).append( " HTTP/1.1\r\n" );
		head.append( "Host: " ).append( uri.getHost() ).append( ':' ).append( uri.getPort() ).append( "\r\n" );

		if( !keepAlive ) {
			head.append( "Connection: close\r\n" );
		}

		final byte[] body = new byte[Math.max( postKilobytes, 0 ) * 1024];
		Arrays.fill( body, (byte)'y' );

		if( postKilobytes >= 0 ) {
			head.append( "Content-Type: application/octet-stream\r\nContent-Length: " ).append( body.length ).append( "\r\n" );
		}

		head.append( "\r\n" );

		final byte[] headBytes = head.toString().getBytes( StandardCharsets.US_ASCII );
		final byte[] whole = Arrays.copyOf( headBytes, headBytes.length + body.length );
		System.arraycopy( body, 0, whole, headBytes.length, body.length );
		return whole;
	}

	/**
	 * One connection's loop. Reconnects after an error, or after every request without keep-alive.
	 */
	private static void run( final InetSocketAddress address, final byte[] request, final Latencies recorded ) {
		Socket socket = null;
		boolean reused = false;

		while( !stopping.get() ) {
			try {
				if( socket == null ) {
					socket = new Socket();
					socket.setTcpNoDelay( true );
					socket.connect( address, 10_000 );
					socket.setSoTimeout( 60_000 );
					reused = false;

					if( measuring.get() ) {
						connects.incrementAndGet();
					}
				}

				final long sent = System.nanoTime();
				final OutputStream out = socket.getOutputStream();
				out.write( request );
				out.flush();

				final int status = readResponse( new BufferedInputStream( socket.getInputStream(), 65536 ) );

				if( measuring.get() ) {
					recorded.add( System.nanoTime() - sent );

					if( Math.abs( status ) < 200 || Math.abs( status ) > 299 ) {
						non2xx.incrementAndGet();
					}
				}

				// A negative status: the server said it will close the connection
				if( !keepAlive || status < 0 ) {
					socket.close();
					socket = null;
				}
				else {
					reused = true;
				}
			}
			catch( final ClosedBeforeResponse e ) {
				// Closed by the server between responses: reconnect and resend, unless it never answered at all
				close( socket );
				socket = null;

				if( measuring.get() ) {
					if( reused ) {
						resent.incrementAndGet();
					}
					else {
						errors.incrementAndGet();
						firstError = firstError == null ? "closed_before_any_response" : firstError;
					}
				}
			}
			catch( final IOException e ) {
				if( reused && e instanceof java.net.SocketException && measuring.get() ) {
					// Reset or a broken pipe on a reused connection: the server closed it while the request was on its way
					resent.incrementAndGet();
				}
				else if( measuring.get() ) {
					errors.incrementAndGet();

					if( firstError == null ) {
						firstError = e.toString().replace( ' ', '_' );
					}
				}

				close( socket );
				socket = null;
			}
		}

		close( socket );
	}

	/**
	 * Reads one response, its body delimited by Content-Length, chunked encoding, or the connection closing, and returns
	 * its status, negated if the server will close the connection. The buffered stream is per response, so nothing may
	 * be read past the body - which holds since the client never pipelines.
	 */
	private static int readResponse( final InputStream in ) throws IOException {
		final StringBuilder head = new StringBuilder();
		int c;

		while( (c = in.read()) != -1 ) {
			head.append( (char)c );

			if( c == '\n' && head.length() >= 4 && head.charAt( head.length() - 3 ) == '\n' ) {
				break;
			}
		}

		if( c == -1 && head.isEmpty() ) {
			throw new ClosedBeforeResponse();
		}

		if( c == -1 ) {
			throw new IOException( "Connection closed before the response headers ended" );
		}

		final String[] lines = head.toString().split( "\r\n" );
		final int status = Integer.parseInt( lines[0].split( " " )[1] );
		long length = -1;
		boolean chunked = false;
		boolean closing = lines[0].startsWith( "HTTP/1.0" );

		for( final String line : lines ) {
			final int colon = line.indexOf( ':' );

			if( colon > 0 && line.substring( 0, colon ).trim().equalsIgnoreCase( "content-length" ) ) {
				length = Long.parseLong( line.substring( colon + 1 ).trim() );
			}

			if( colon > 0 && line.substring( 0, colon ).trim().equalsIgnoreCase( "transfer-encoding" ) ) {
				chunked = line.substring( colon + 1 ).trim().toLowerCase().endsWith( "chunked" );
			}

			if( colon > 0 && line.substring( 0, colon ).trim().equalsIgnoreCase( "connection" ) ) {
				closing = line.substring( colon + 1 ).trim().equalsIgnoreCase( "close" );
			}
		}

		final long bodyLength;

		if( chunked ) {
			bodyLength = readChunked( in );
		}
		else if( length >= 0 ) {
			skip( in, length );
			bodyLength = length;
		}
		else if( closing ) {
			// No length given: the body ends when the server closes the connection
			bodyLength = in.transferTo( OutputStream.nullOutputStream() );
		}
		else {
			throw new IOException( "Neither Content-Length nor chunked, on a connection kept open: " + lines[0] );
		}

		bytesRead.addAndGet( head.length() + bodyLength );
		return closing ? -status : status;
	}

	/**
	 * Reads a chunked body to its last chunk and the trailers after it, and returns the length of its content
	 */
	private static long readChunked( final InputStream in ) throws IOException {
		long total = 0;

		while( true ) {
			final String sizeLine = line( in );
			final int extension = sizeLine.indexOf( ';' );
			final long size = Long.parseLong( (extension < 0 ? sizeLine : sizeLine.substring( 0, extension )).trim(), 16 );

			if( size == 0 ) {
				// Trailers, if any, end with an empty line
				while( !line( in ).isEmpty() ) {}
				return total;
			}

			skip( in, size );
			line( in );
			total += size;
		}
	}

	/**
	 * Reads one CRLF-terminated line, without its terminator
	 */
	private static String line( final InputStream in ) throws IOException {
		final StringBuilder line = new StringBuilder();
		int c;

		while( (c = in.read()) != '\n' ) {
			if( c == -1 ) {
				throw new IOException( "Connection closed in a chunked body" );
			}

			if( c != '\r' ) {
				line.append( (char)c );
			}
		}

		return line.toString();
	}

	private static void skip( final InputStream in, final long length ) throws IOException {
		long remaining = length;
		final byte[] buffer = new byte[65536];

		while( remaining > 0 ) {
			final int n = in.read( buffer, 0, (int)Math.min( buffer.length, remaining ) );

			if( n == -1 ) {
				throw new IOException( "Connection closed in the body" );
			}

			remaining -= n;
		}
	}

	private static String ms( final long[] sorted, final double quantile ) {
		if( sorted.length == 0 ) {
			return "-";
		}

		final int index = (int)Math.min( sorted.length - 1, Math.ceil( quantile * sorted.length ) - 1 );
		return String.format( "%.2f", sorted[Math.max( index, 0 )] / 1e6 );
	}

	private static void close( final Socket socket ) {
		if( socket != null ) {
			try {
				socket.close();
			}
			catch( final IOException e ) {}
		}
	}

	/**
	 * The connection closed before a single byte of the response arrived
	 */
	private static class ClosedBeforeResponse extends IOException {}

	private static class Latencies {
		long[] values = new long[1 << 16];
		int size;

		void add( final long value ) {
			if( size == values.length ) {
				values = Arrays.copyOf( values, size * 2 );
			}

			values[size++] = value;
		}

		long[] values() {
			return Arrays.copyOf( values, size );
		}
	}
}
