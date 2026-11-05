package bench;

import com.webobjects.appserver.WOSession;

/**
 * Unused by the benchmark, which creates no sessions. WO looks its session class up by the short name "Session", and
 * without this one it finds Jetty's org.eclipse.jetty.server.Session and refuses it.
 */
public class Session extends WOSession {}
