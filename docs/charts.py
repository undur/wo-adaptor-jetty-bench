"""
Draws the README's charts from the numbers in the latest results file. Run from the project root:

    python3 docs/charts.py results/<timestamp>.txt

Writes docs/throughput.svg and docs/waiting.svg. Each SVG carries its own light and dark colours, chosen by the
viewer's colour scheme, and a transparent background so it sits on GitHub's page in either.
"""

import re
import sys

STYLE = """<style>
  .text { fill: #1f2328; }
  .muted { fill: #59636e; }
  .grid { stroke: #d1d9e0; }
  .jetty { fill: #2a78d6; stroke: #2a78d6; }
  .classic { fill: #eb6834; stroke: #eb6834; }
  .ring { stroke: #ffffff; }
  @media (prefers-color-scheme: dark) {
    .text { fill: #f0f6fc; }
    .muted { fill: #9198a1; }
    .grid { stroke: #3d444d; }
    .jetty { fill: #3987e5; stroke: #3987e5; }
    .classic { fill: #d95926; stroke: #d95926; }
    .ring { stroke: #0d1117; }
  }
  text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
</style>"""


def parse( path ):
    """Returns {configuration number: {scenario label: rps}}"""
    results = {}
    configuration = None

    for line in open( path ):
        heading = re.match( r"^(\d)\. ", line )

        if heading:
            configuration = int( heading.group( 1 ) )
            results[configuration] = {}

        scenario = re.match( r"^  (.+?)\s+requests=\d+ rps=(\d+)", line )

        if scenario and configuration:
            results[configuration][scenario.group( 1 ).strip()] = int( scenario.group( 2 ) )

    return results


def compact( value ):
    return f"{value / 1000:.1f}K".replace( ".0K", "K" ) if value >= 1000 else f"{value:,}"


def legend( x, y ):
    return f"""<rect class="jetty" x="{x}" y="{y - 9}" width="10" height="10" rx="2"/>
<text class="text" x="{x + 16}" y="{y}" font-size="13">wo-adaptor-jetty</text>
<rect class="classic" x="{x + 140}" y="{y - 9}" width="10" height="10" rx="2"/>
<text class="text" x="{x + 156}" y="{y}" font-size="13">WO's classic adaptor</text>"""


def throughput( jetty, classic ):
    rows = [
        ( "Small response", "hello keep-alive c=64" ),
        ( "64 KB upload", "64 KB upload c=16" ),
        ( "256 KB response", "256 KB response c=16" ),
        ( "Component page, 6 KB", "component page c=64" ),
        ( "New connection per request", "hello new connection each c=16" ),
    ]

    width, left, right = 760, 200, 70
    top, bar, gap, group = 86, 14, 2, 20
    height = top + len( rows ) * (2 * bar + gap + group) + 24
    maximum = 125_000
    scale = (width - left - right) / maximum

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="t d">',
             '<title id="t">Requests per second</title>',
             '<desc id="d">' + "; ".join( f"{label}: wo-adaptor-jetty {jetty[key]:,}, classic adaptor {classic[key]:,} requests per second" for label, key in rows ) + "</desc>",
             STYLE,
             '<text class="text" x="0" y="22" font-size="17" font-weight="600">Requests per second</text>',
             '<text class="muted" x="0" y="42" font-size="13">Closed loop over loopback, client and server on one 14-core Mac</text>',
             legend( 0, 66 )]

    for tick in range( 0, maximum + 1, 25_000 ):
        x = left + tick * scale
        parts.append( f'<line class="grid" x1="{x:.1f}" y1="{top - 8}" x2="{x:.1f}" y2="{height - 22}" stroke-width="1"/>' )
        parts.append( f'<text class="muted" x="{x:.1f}" y="{height - 6}" font-size="11" text-anchor="middle">{compact( tick )}</text>' )

    y = top

    for label, key in rows:
        parts.append( f'<text class="text" x="{left - 12}" y="{y + bar + 5}" font-size="13" text-anchor="end">{label}</text>' )

        for css, value in ( ( "jetty", jetty[key] ), ( "classic", classic[key] ) ):
            length = value * scale
            # Rounded at the data end only: a square-ended rect under a rounded one
            parts.append( f'<rect class="{css}" x="{left}" y="{y}" width="{max( length - 4, 0 ):.1f}" height="{bar}"/>' )
            parts.append( f'<rect class="{css}" x="{left + max( length - 8, 0 ):.1f}" y="{y}" width="{min( 8, length ):.1f}" height="{bar}" rx="4"/>' )
            parts.append( f'<text class="muted" x="{left + length + 6:.1f}" y="{y + bar - 3}" font-size="11">{compact( value )}</text>' )
            y += bar + gap

        y += group - gap

    parts.append( "</svg>" )
    return "\n".join( parts )


def waiting( jetty, classic ):
    points = [ 100, 1000, 2000 ]
    keys = { 100: "sleep 200ms c=100", 1000: "sleep 200ms c=1000", 2000: "sleep 200ms c=2000" }

    width, left, right, top, bottom = 760, 56, 190, 86, 300
    height = bottom + 40
    maximum = 10_000

    def x( connections ):
        return left + connections / 2000 * (width - left - right)

    def y( rps ):
        return bottom - rps / maximum * (bottom - top)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="t d">',
             '<title id="t">Requests that wait 200 ms</title>',
             '<desc id="d">' + "; ".join( f"{n} connections: wo-adaptor-jetty {jetty[keys[n]]:,}, classic adaptor {classic[keys[n]]:,} requests per second" for n in points ) + "</desc>",
             STYLE,
             '<text class="text" x="0" y="22" font-size="17" font-weight="600">Requests that wait 200 ms, as on a database</text>',
             '<text class="muted" x="0" y="42" font-size="13">Requests per second by concurrent connections</text>',
             legend( 0, 66 )]

    for tick in range( 0, maximum + 1, 2_500 ):
        parts.append( f'<line class="grid" x1="{left}" y1="{y( tick ):.1f}" x2="{width - right}" y2="{y( tick ):.1f}" stroke-width="1"/>' )
        parts.append( f'<text class="muted" x="{left - 8}" y="{y( tick ) + 4:.1f}" font-size="11" text-anchor="end">{compact( tick )}</text>' )

    for n in points:
        parts.append( f'<text class="muted" x="{x( n ):.1f}" y="{bottom + 18}" font-size="11" text-anchor="middle">{n:,}</text>' )

    parts.append( f'<text class="muted" x="{(left + width - right) / 2:.1f}" y="{bottom + 36}" font-size="11" text-anchor="middle">concurrent connections</text>' )

    for css, values, note in ( ( "jetty", jetty, "" ), ( "classic", classic, ", the rest refused" ) ):
        coordinates = " ".join( f"{x( n ):.1f},{y( values[keys[n]] ):.1f}" for n in points )
        parts.append( f'<polyline class="{css}" points="{coordinates}" style="fill:none" stroke-width="2" stroke-linejoin="round"/>' )

        for n in points:
            parts.append( f'<circle class="{css} ring" cx="{x( n ):.1f}" cy="{y( values[keys[n]] ):.1f}" r="4.5" style="stroke-width:2"/>' )
            parts.append( f'<circle class="{css}" cx="{x( n ):.1f}" cy="{y( values[keys[n]] ):.1f}" r="4" stroke="none"/>' )

        end = values[keys[2000]]
        parts.append( f'<text class="text" x="{x( 2000 ) + 12:.1f}" y="{y( end ) + 4:.1f}" font-size="13">{end:,} req/s{note}</text>' )

    parts.append( "</svg>" )
    return "\n".join( parts )


results = parse( sys.argv[1] )
open( "docs/throughput.svg", "w" ).write( throughput( results[1], results[3] ) )
open( "docs/waiting.svg", "w" ).write( waiting( results[1], results[3] ) )
