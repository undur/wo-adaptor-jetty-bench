package bench;

import com.webobjects.appserver.WOApplication;

public class Application extends WOApplication {

	public static void main( final String[] argv ) {
		WOApplication.main( argv, Application.class );
	}

	public Application() {
		super();
		setAllowsConcurrentRequestHandling( Boolean.parseBoolean( System.getProperty( "BenchConcurrent", "true" ) ) );
		registerRequestHandler( new BenchRequestHandler(), "b" );
		System.out.printf( "BENCH adaptor=%s concurrent=%s cpus=%s%n", adaptors().objectAtIndex( 0 ).getClass().getSimpleName(), allowsConcurrentRequestHandling(), Runtime.getRuntime().availableProcessors() );
	}
}
