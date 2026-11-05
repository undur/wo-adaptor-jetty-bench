# Results, 2026-11-05

MacBook, 14 CPUs, 48 GB, JDK 25.0.4.1, `-Xms2g -Xmx2g`, wo-adaptor-jetty 0.12.3, WebObjects 5.4.3. Full output in
`results/2026-11-05-204101.txt`. Latencies in milliseconds.

| Scenario | Jetty adaptor | | Classic adaptor | |
|---|---:|---:|---:|---:|
| | **req/s** | **p99** | **req/s** | **p99** |
| Hello, keep-alive, 64 connections | 121,000 | 1.8 | 11,200 ¹ | 2.4 |
| Hello, a new connection per request, 16 at a time | 16,700 | 0.6 | 12,900 ¹ | 0.7 |
| Component page (6 KB, 100 rows), 64 connections | 27,800 | 8.7 | 24,100 | 8.5 |
| 256 KB response, 16 connections | 42,700 (13.7 GB/s) | 1.1 | 11,300 (3.7 GB/s) ¹ | 1.4 |
| 64 KB upload, 16 connections | 81,500 | 0.8 | 6,300 ¹ | 0.8 |
| 200 ms wait, 100 connections | 487 | 218 | 488 | 209 |
| 200 ms wait, 1,000 connections | 4,790 | 227 | 1,230, 234k errors ² | 400 |
| 200 ms wait, 2,000 connections | 9,530 | 231 | 1,100, 220k errors ² | 471 |

¹ The classic adaptor closed the connection after every response from the `b/` handler, keep-alive or not (it kept
connections open for the component page). Every request therefore paid for a connection, and in some scenarios the
client ran out of local ports (`BindException`), so these numbers are partly the client's limit.

² The classic adaptor handles at most 256 requests at a time (`WOWorkerThreadCountMax`), so it tops out at
256 / 0.2 s = 1,280 req/s, and connections beyond its listen queue were reset.

Errors: none in any Jetty scenario.

## What it shows

- **Raw throughput.** About 120k small requests per second with keep-alive. The server used about 6 cores doing it and
  the load generator most of the rest, and no thread was waiting on a lock, so this is the limit of running both on one
  machine, not of the adaptor. Without keep-alive, about 17k new connections per second.
- **Waiting requests scale with connections.** Each request runs on a virtual thread, so 2,000 requests waiting 200 ms
  at once give 2,000 / 0.2 s = 10,000 req/s, and p99 stays within 31 ms of the wait. This is the clearest difference
  from the classic adaptor, which is capped by its worker threads and drops the rest.
- **Large bodies are cheap.** 13.7 GB/s of 256 KB responses, and 81k uploads of 64 KB per second.
- **WO's request lock, not the adaptor, decides concurrency for WO's own handlers.** With concurrent request handling
  off (WO's default), 100 connections to a direct action that waits 200 ms got 2 req/s, against 487 with it on. Fast,
  CPU-bound pages barely notice (25,000 against 27,800 req/s): the lock costs little when no request holds it for long.
- **QoS works as configured.** With `JettyMaxConcurrentRequests=50`, 1,000 connections waiting 200 ms got exactly
  50 / 0.2 s = 244 req/s, the rest queued (p50 4.06 s), and no errors. Small requests were unaffected (123k req/s).

## Unexplained

In one of three full runs, the component page scenario had two connections that got no response for the whole 8
seconds, and one request that took 6.4 s. It did not recur in the full run after it or in ten targeted runs (cold start,
and right after 140k connections had been opened and closed). GC pauses never exceeded 24 ms. Worth watching for.
