#!/bin/sh
#
# Runs every scenario against every configuration, launching the application afresh for each configuration, and writes
# the results to results/<timestamp>.txt. Expects a built application: mvn package
#
# Usage: ./bench.sh [seconds per scenario, default 8]
#

cd "`dirname \"$0\"`"

SECONDS_PER_SCENARIO=${1:-8}
PORT=7100
URL=http://127.0.0.1:${PORT}/Apps/WebObjects/Bench.woa
WOA=target/wo-adaptor-jetty-bench-1.0.0-SNAPSHOT.woa
mkdir -p results target/hammer
RESULTS=results/`date +%Y-%m-%d-%H%M%S`.txt
CONFIGURATION=0

javac -d target/hammer Hammer.java || exit 1

JVM_OPTIONS="-Xms2g -Xmx2g -Xlog:gc:file=`pwd`/target/gc-%p.log --add-exports java.base/sun.security.action=ALL-UNNAMED --add-opens java.base/java.util=ALL-UNNAMED --add-opens java.base/java.time=ALL-UNNAMED --add-opens java.base/java.lang=ALL-UNNAMED"

say() {
	echo "$@" | tee -a "${RESULTS}"
}

# Launch the application with the given arguments, and wait until it answers
start() {
	CONFIGURATION=$((CONFIGURATION + 1))
	"${WOA}/Bench" -WOPort ${PORT} "-launch.jvmOptions=${JVM_OPTIONS}" "$@" > target/app-${CONFIGURATION}.log 2>&1 &

	for i in `seq 60`; do
		curl -s -o /dev/null "${URL}/b/hello" && break
		sleep 0.5
	done

	if ! curl -s -o /dev/null "${URL}/b/hello"; then
		say "The application did not start, see target/app-${CONFIGURATION}.log"
		stop
		exit 1
	fi

	say "`grep BENCH target/app-${CONFIGURATION}.log`"
}

stop() {
	pkill -f "${WOA}"
	sleep 2
}

# Run one scenario: a label, then Hammer's arguments. Waits first for the previous scenario's closed connections to
# leave TIME_WAIT, which otherwise holds the ephemeral ports a connection-per-request scenario needs.
scenario() {
	for i in `seq 40`; do
		[ `netstat -an -p tcp | grep -c TIME_WAIT` -lt 2000 ] && break
		sleep 1
	done

	label=$1
	shift
	printf "  %-34s " "${label}" | tee -a "${RESULTS}"
	java -cp target/hammer Hammer -d ${SECONDS_PER_SCENARIO} "$@" | tee -a "${RESULTS}"
}

# The scenarios every configuration runs
standard() {
	scenario "hello keep-alive c=64" -c 64 "${URL}/b/hello"
	scenario "hello new connection each c=16" -c 16 --close "${URL}/b/hello"
	scenario "component page c=64" -c 64 "${URL}/wa/default"
	scenario "256 KB response c=16" -c 16 "${URL}/b/bytes?kb=256"
	scenario "64 KB upload c=16" -c 16 --post 64 "${URL}/b/upload"
	scenario "sleep 200ms c=100" -c 100 "${URL}/b/sleep?ms=200"
	scenario "sleep 200ms c=1000" -c 1000 "${URL}/b/sleep?ms=200"
	scenario "sleep 200ms c=2000" -c 2000 "${URL}/b/sleep?ms=200"
	scenario "direct action sleep 200ms c=100" -c 100 "${URL}/wa/sleep?ms=200"
}

say "wo-adaptor-jetty bench, `date`, `sysctl -n hw.ncpu` CPUs, `java -version 2>&1 | head -1`, ${SECONDS_PER_SCENARIO}s per scenario"
say "adaptor `grep -o 'wo-adaptor-jetty-[0-9][^/]*\.jar' ${WOA}/classpath.txt | head -1`"
say

say "1. Jetty adaptor, concurrent request handling"
start
standard
stop

say
say "2. Jetty adaptor, WO's default: no concurrent request handling"
start -DBenchConcurrent=false
scenario "hello keep-alive c=64" -c 64 "${URL}/b/hello"
scenario "component page c=64" -c 64 "${URL}/wa/default"
scenario "direct action sleep 200ms c=100" -c 100 "${URL}/wa/sleep?ms=200"
stop

say
say "3. WO's classic adaptor (WODefaultAdaptor), concurrent request handling"
start -WOAdaptor WODefaultAdaptor
standard
stop

say
say "4. Jetty adaptor, JettyMaxConcurrentRequests=50"
start -DJettyMaxConcurrentRequests=50
scenario "hello keep-alive c=64" -c 64 "${URL}/b/hello"
scenario "sleep 200ms c=1000" -c 1000 "${URL}/b/sleep?ms=200"
stop

say
say "Written to ${RESULTS}"
