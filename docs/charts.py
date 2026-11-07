"""
Draws charts from a results file, one series per adaptor that ran the full set of scenarios. Run from the project root:

    python3 docs/charts.py results/<timestamp>.txt [output directory]

Writes throughput.svg and waiting.svg to the output directory, or next to the results file as
<timestamp>-throughput.svg and <timestamp>-waiting.svg without one. The README's charts are drawn with docs as the output
directory. Each SVG carries its own light and dark colours, chosen by the viewer's colour scheme, and a transparent
background so it sits on GitHub's page in either.
"""

import math
import os
import re
import sys

# Categorical slots in a fixed order, light and dark: an adaptor's colour is its position in the results file
SERIES = [ ( "#2a78d6", "#3987e5" ), ( "#eb6834", "#d95926" ), ( "#1baf7a", "#199e70" ), ( "#eda100", "#c98500" ),
           ( "#e87ba4", "#d55181" ), ( "#008300", "#008300" ), ( "#6250d6", "#9085e9" ), ( "#e34948", "#e66767" ) ]

NAMES = { "WOAdaptorJetty": "wo-adaptor-jetty", "WODefaultAdaptor": "WO's classic adaptor" }

FULL_SET = "sleep 200ms c=2000"


def style( count ):
    light = "\n".join( f"  .s{i} {{ fill: {SERIES[i][0]}; stroke: {SERIES[i][0]}; }}" for i in range( count ) )
    dark = "\n".join( f"    .s{i} {{ fill: {SERIES[i][1]}; stroke: {SERIES[i][1]}; }}" for i in range( count ) )
    return f"""<style>
  .text {{ fill: #1f2328; }}
  .muted {{ fill: #59636e; }}
  .grid {{ stroke: #d1d9e0; }}
  .ring {{ stroke: #ffffff; }}
{light}
  @media (prefers-color-scheme: dark) {{
    .text {{ fill: #f0f6fc; }}
    .muted {{ fill: #9198a1; }}
    .grid {{ stroke: #3d444d; }}
    .ring {{ stroke: #0d1117; }}
{dark}
  }}
  text {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }}
</style>"""


def parse( path ):
    """
    Returns the machine's CPU count, and a list of (adaptor name, {scenario: (rps, errors)}) for every configuration that
    ran the full set of scenarios, in the order they ran
    """
    cpus = None
    configurations = []

    for line in open( path ):
        header = re.search( r"(\d+) CPUs", line )

        if header and cpus is None:
            cpus = int( header.group( 1 ) )

        bench = re.match( r"^BENCH adaptor=(\S+)", line )

        if bench:
            configurations.append( ( NAMES.get( bench.group( 1 ), bench.group( 1 ) ), {} ) )

        scenario = re.match( r"^  (.+?)\s+requests=\d+ rps=(\d+).* errors=(\d+)", line )

        if scenario and configurations:
            configurations[-1][1][scenario.group( 1 ).strip()] = ( int( scenario.group( 2 ) ), int( scenario.group( 3 ) ) )

    return cpus, [ c for c in configurations if FULL_SET in c[1] ]


def compact( value ):
    if value >= 1000:
        return f"{value / 1000:.1f}K".replace( ".0K", "K" )

    return f"{value:,}"


def axis( maximum ):
    """A tick step of 1, 2, 2.5 or 5 times a power of ten giving four or five ticks, and the axis maximum it reaches"""
    magnitude = 10 ** math.floor( math.log10( maximum / 4 ) )
    step = next( magnitude * f for f in ( 1, 2, 2.5, 5, 10 ) if maximum / (magnitude * f) <= 5 )
    return step, step * math.ceil( maximum / step )


def legend( names, y ):
    parts = []
    x = 0

    for i, name in enumerate( names ):
        parts.append( f'<rect class="s{i}" x="{x}" y="{y - 9}" width="10" height="10" rx="2"/>' )
        parts.append( f'<text class="text" x="{x + 16}" y="{y}" font-size="13">{escape( name )}</text>' )
        x += 16 + 7.5 * len( name ) + 24

    return "\n".join( parts )


def escape( text ):
    return text.replace( "&", "&amp;" ).replace( "<", "&lt;" ).replace( ">", "&gt;" )


def header( width, height, title, description, subtitle, names ):
    return [ f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="t d">',
             f'<title id="t">{escape( title )}</title>',
             f'<desc id="d">{escape( description )}</desc>',
             style( len( names ) ),
             f'<text class="text" x="0" y="22" font-size="17" font-weight="600">{escape( title )}</text>',
             f'<text class="muted" x="0" y="42" font-size="13">{escape( subtitle )}</text>',
             legend( names, 66 ) ]


def throughput( cpus, configurations ):
    rows = [
        ( "Small response", "hello keep-alive c=64" ),
        ( "64 KB upload", "64 KB upload c=16" ),
        ( "256 KB response", "256 KB response c=16" ),
        ( "Component page, 6 KB", "component page c=64" ),
        ( "New connection per request", "hello new connection each c=16" ),
    ]

    names = [ name for name, _ in configurations ]
    count = len( configurations )
    width, left, right = 760, 200, 70
    top, bar, gap, group = 86, 14, 2, 20
    height = top + len( rows ) * (count * (bar + gap) - gap + group) + 24
    step, maximum = axis( max( results[key][0] for _, results in configurations for _, key in rows ) )
    scale = (width - left - right) / maximum

    description = "; ".join( f"{label}: " + ", ".join( f"{name} {results[key][0]:,}" for name, results in configurations ) for label, key in rows )
    parts = header( width, height, "Requests per second", description + " requests per second",
                    f"Closed loop over loopback, client and server on one {cpus}-core machine", names )

    tick = 0

    while tick <= maximum:
        x = left + tick * scale
        parts.append( f'<line class="grid" x1="{x:.1f}" y1="{top - 8}" x2="{x:.1f}" y2="{height - 22}" stroke-width="1"/>' )
        parts.append( f'<text class="muted" x="{x:.1f}" y="{height - 6}" font-size="11" text-anchor="middle">{compact( tick )}</text>' )
        tick += step

    y = top

    for label, key in rows:
        group_height = count * (bar + gap) - gap
        parts.append( f'<text class="text" x="{left - 12}" y="{y + group_height / 2 + 5:.1f}" font-size="13" text-anchor="end">{label}</text>' )

        for i, ( _, results ) in enumerate( configurations ):
            value = results[key][0]
            length = value * scale
            # Rounded at the data end only: a square-ended rect under a rounded one
            parts.append( f'<rect class="s{i}" x="{left}" y="{y}" width="{max( length - 4, 0 ):.1f}" height="{bar}"/>' )
            parts.append( f'<rect class="s{i}" x="{left + max( length - 8, 0 ):.1f}" y="{y}" width="{min( 8, length ):.1f}" height="{bar}" rx="4"/>' )
            parts.append( f'<text class="muted" x="{left + length + 6:.1f}" y="{y + bar - 3}" font-size="11">{compact( value )}</text>' )
            y += bar + gap

        y += group - gap

    parts.append( "</svg>" )
    return "\n".join( parts )


def waiting( configurations ):
    points = [ 100, 1000, 2000 ]
    keys = { n: f"sleep 200ms c={n}" for n in points }

    names = [ name for name, _ in configurations ]
    width, left, right, top, bottom = 760, 56, 190, 86, 300
    height = bottom + 40
    step, maximum = axis( max( results[keys[n]][0] for _, results in configurations for n in points ) )

    def x( connections ):
        return left + connections / 2000 * (width - left - right)

    def y( rps ):
        return bottom - rps / maximum * (bottom - top)

    description = "; ".join( f"{n:,} connections: " + ", ".join( f"{name} {results[keys[n]][0]:,}" for name, results in configurations ) for n in points )
    parts = header( width, height, "Requests that wait 200 ms, as on a database", description + " requests per second",
                    "Requests per second by concurrent connections", names )

    tick = 0

    while tick <= maximum:
        parts.append( f'<line class="grid" x1="{left}" y1="{y( tick ):.1f}" x2="{width - right}" y2="{y( tick ):.1f}" stroke-width="1"/>' )
        parts.append( f'<text class="muted" x="{left - 8}" y="{y( tick ) + 4:.1f}" font-size="11" text-anchor="end">{compact( tick )}</text>' )
        tick += step

    for n in points:
        parts.append( f'<text class="muted" x="{x( n ):.1f}" y="{bottom + 18}" font-size="11" text-anchor="middle">{n:,}</text>' )

    parts.append( f'<text class="muted" x="{(left + width - right) / 2:.1f}" y="{bottom + 36}" font-size="11" text-anchor="middle">concurrent connections</text>' )

    for i, ( _, results ) in enumerate( configurations ):
        coordinates = " ".join( f"{x( n ):.1f},{y( results[keys[n]][0] ):.1f}" for n in points )
        parts.append( f'<polyline class="s{i}" points="{coordinates}" style="fill:none" stroke-width="2" stroke-linejoin="round"/>' )

        for n in points:
            parts.append( f'<circle class="s{i} ring" cx="{x( n ):.1f}" cy="{y( results[keys[n]][0] ):.1f}" r="4.5" style="stroke-width:2"/>' )
            parts.append( f'<circle class="s{i}" cx="{x( n ):.1f}" cy="{y( results[keys[n]][0] ):.1f}" r="4" stroke="none"/>' )

    # End labels, from the top down, leaving out any that would overlap the one above: the legend names every line
    placed = None

    for _, results in sorted( configurations, key = lambda c: -c[1][keys[2000]][0] ):
        rps, errors = results[keys[2000]]

        if placed is None or y( rps ) - placed >= 16:
            note = f", {compact( errors )} errors" if errors else ""
            parts.append( f'<text class="text" x="{x( 2000 ) + 12:.1f}" y="{y( rps ) + 4:.1f}" font-size="13">{rps:,} req/s{note}</text>' )
            placed = y( rps )

    parts.append( "</svg>" )
    return "\n".join( parts )


path = sys.argv[1]
cpus, configurations = parse( path )

if not configurations:
    sys.exit( f"No configuration in {path} ran the full set of scenarios" )

if len( configurations ) > len( SERIES ):
    sys.exit( f"{len( configurations )} adaptors, but colours for only {len( SERIES )}" )

if len( sys.argv ) > 2:
    prefix = os.path.join( sys.argv[2], "" )
else:
    prefix = os.path.splitext( path )[0] + "-"

open( prefix + "throughput.svg", "w" ).write( throughput( cpus, configurations ) )
open( prefix + "waiting.svg", "w" ).write( waiting( configurations ) )
print( f"Wrote {prefix}throughput.svg and {prefix}waiting.svg: " + ", ".join( name for name, _ in configurations ) )
