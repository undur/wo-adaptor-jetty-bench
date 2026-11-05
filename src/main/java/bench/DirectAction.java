package bench;

import com.webobjects.appserver.WOActionResults;
import com.webobjects.appserver.WODirectAction;
import com.webobjects.appserver.WORequest;
import com.webobjects.appserver.WOResponse;

/**
 * The same work through WO's usual path: a direct action rendering a component, with no session
 */
public class DirectAction extends WODirectAction {

	public DirectAction( final WORequest request ) {
		super( request );
	}

	@Override
	public WOActionResults defaultAction() {
		return pageWithName( Page.class.getName() );
	}

	/**
	 * Waits, then answers. The same as the request handler's sleep, except that it runs inside WO's direct action
	 * handling, which takes the application's request lock when concurrent request handling is off.
	 */
	public WOActionResults sleepAction() {
		final String ms = request().stringFormValueForKey( "ms" );

		try {
			Thread.sleep( ms == null ? 200 : Integer.parseInt( ms ) );
		}
		catch( final InterruptedException e ) {
			Thread.currentThread().interrupt();
		}

		final WOResponse response = new WOResponse();
		response.setHTTPVersion( request().httpVersion() );
		response.setContent( "Slept" );
		return response;
	}
}
