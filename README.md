# wo-adaptor-jetty-bench

An experimental load test of [wo-adaptor-jetty](https://github.com/undur/wo-adaptor-jetty): a plain WebObjects 5.4.3
application (no Wonder) with a handful of endpoints, a load generator, and a script that runs every scenario against
several configurations, including WO's classic adaptor for comparison.

```
mvn package
./bench.sh            # 8 seconds per scenario, about 6 minutes in all; results/<timestamp>.txt
```

To bench the adaptor's working copy instead of the release, `mvn install` its reactor and build this with
`mvn package -Dadaptor.version=0.12.4-SNAPSHOT`.

## The application

Endpoints under `http://127.0.0.1:7100/Apps/WebObjects/Bench.woa/`:

| Path | What it does |
|---|---|
| `b/hello` | A 5 byte text response |
| `b/sleep?ms=200` | Waits, as a request waiting on a database or a remote service does, then answers |
| `b/bytes?kb=256` | A response of that size |
| `b/upload` | A POST, answered with the length of its body |
| `wa/default` | A direct action rendering a component: a 100 row `WORepetition`, about 6 KB of HTML, no session |
| `wa/sleep?ms=200` | The sleep, as a direct action |

The `b/` endpoints are a `WORequestHandler` of their own, so no context, page or session is created and what is measured
is the adaptor plus WO's dispatch. WO's request lock, taken when concurrent request handling is off, belongs to its
component and direct action handlers; a custom request handler like this one is never serialized by it, which is why the
lock is tested with `wa/sleep`.

`-DBenchConcurrent=false` turns concurrent request handling off (WO's own default); the application turns it on otherwise.

## Hammer

`Hammer.java` is the load generator: closed-loop HTTP/1.1, one platform thread per connection, a fixed duration after a
warmup, latency percentiles from every request. `ab` is single-threaded and runs out of CPU at about 97k requests per
second on an M-series Mac, below what the adaptor serves.

```
java Hammer.java [-c connections] [-d seconds] [-w warmup seconds] [--close] [--post kilobytes] url
```

## Caveats

Client and server run on the same machine and share its cores, over loopback, with no Apache or modulo in front. The
scenarios are synthetic. Treat the numbers as the adaptor's ceiling and as a comparison between configurations, not as
what a production application will see.
