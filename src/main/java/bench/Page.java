package bench;

import java.util.stream.IntStream;

import com.webobjects.appserver.WOComponent;
import com.webobjects.appserver.WOContext;
import com.webobjects.foundation.NSArray;

/**
 * A page of a hundred table rows, about 6 KB of HTML: a modest but real amount of template work per request
 */
public class Page extends WOComponent {

	private static final NSArray<Integer> ROWS = new NSArray<>( IntStream.range( 0, 100 ).boxed().toList() );

	public Integer row;

	public Page( final WOContext context ) {
		super( context );
	}

	public NSArray<Integer> rows() {
		return ROWS;
	}

	public String name() {
		return "Row number " + row;
	}

	public int square() {
		return row * row;
	}
}
