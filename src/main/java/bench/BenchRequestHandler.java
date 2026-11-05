package bench;

import java.util.Arrays;

import com.webobjects.appserver.WORequest;
import com.webobjects.appserver.WORequestHandler;
import com.webobjects.appserver.WOResponse;
import com.webobjects.foundation.NSData;

/**
 * The benchmark's endpoints, under /Apps/WebObjects/Bench.woa/b/. A request handler of its own rather than direct
 * actions, so no context, page or session is created and what is measured is the adaptor plus WO's dispatch.
 *
 * <ul>
 * <li>hello: a tiny text response</li>
 * <li>sleep?ms=200: waits, as a request waiting on a database or a remote service does</li>
 * <li>bytes?kb=256: a response of that size</li>
 * <li>upload: a POST, answered with the length of its body</li>
 * </ul>
 */
public class BenchRequestHandler extends WORequestHandler {

	private static final byte[] KILOBYTE = new byte[1024];

	static {
		Arrays.fill( KILOBYTE, (byte)'x' );
	}

	@Override
	public WOResponse handleRequest( final WORequest request ) {
		final String key = request.requestHandlerPath();

		final WOResponse response = switch( key == null ? "" : key ) {
			case "hello" -> text( "Hello" );
			case "sleep" -> {
				sleep( intValue( request, "ms", 200 ) );
				yield text( "Slept" );
			}
			case "bytes" -> bytes( intValue( request, "kb", 256 ) );
			case "upload" -> text( String.valueOf( request.content() == null ? 0 : request.content().length() ) );
			default -> {
				final WOResponse notFound = text( "No such endpoint: " + key );
				notFound.setStatus( 404 );
				yield notFound;
			}
		};

		// A new WOResponse says HTTP/1.0, and the classic adaptor closes the connection after it. A component's response
		// answers in the request's version, so do the same, or the comparison measures connection setup.
		response.setHTTPVersion( request.httpVersion() );
		return response;
	}

	private static WOResponse text( final String content ) {
		final WOResponse response = new WOResponse();
		response.setHeader( "text/plain; charset=utf-8", "content-type" );
		response.setContent( content );
		return response;
	}

	private static WOResponse bytes( final int kilobytes ) {
		final byte[] content = new byte[kilobytes * KILOBYTE.length];

		for( int i = 0; i < kilobytes; i++ ) {
			System.arraycopy( KILOBYTE, 0, content, i * KILOBYTE.length, KILOBYTE.length );
		}

		final WOResponse response = new WOResponse();
		response.setHeader( "application/octet-stream", "content-type" );
		response.setContent( new NSData( content ) );
		return response;
	}

	private static int intValue( final WORequest request, final String key, final int defaultValue ) {
		final String value = request.stringFormValueForKey( key );
		return value == null ? defaultValue : Integer.parseInt( value );
	}

	private static void sleep( final int millis ) {
		try {
			Thread.sleep( millis );
		}
		catch( final InterruptedException e ) {
			Thread.currentThread().interrupt();
		}
	}
}
