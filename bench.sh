#!/bin/sh
#
# Runs the scenarios against each configuration, launching the application afresh for each, and writes the results to
# results/<timestamp>.txt. Expects a built application: mvn package
#
# Usage: ./bench.sh [-d seconds] [-a adaptor class] [-cp classpath] [-o]
#
#   -d seconds     How long each scenario measures, after a 2 second warmup. Default 8.
#   -a class       Also bench this adaptor, by the class name -WOAdaptor takes. Repeatable.
#   -cp classpath  Jars the -a adaptors need: the adaptor and its dependencies, separated by ':'. Added to the classpath
#                  of the -a configurations only.
#   -o             Only compare adaptors: skip the configurations about wo-adaptor-jetty's own settings (WO's request
#                  lock, and JettyMaxConcurrentRequests).
#

cd "`dirname \"$0\"`"

SECONDS_PER_SCENARIO=8
EXTRA_ADAPTORS=
EXTRA_CLASSPATH=
ONLY_ADAPTORS=false

while [ $# -gt 0 ]; do
	case $1 in
		-d)  SECONDS_PER_SCENARIO=$2; shift ;;
		-a)  EXTRA_ADAPTORS="${EXTRA_ADAPTORS} $2"; shift ;;
		-cp) EXTRA_CLASSPATH=$2; shift ;;
		-o)  ONLY_ADAPTORS=true ;;
		*)   sed -n '6,15p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
	esac
	shift
done

# The launch script runs from inside the .woa, so make the -cp entries absolute
ABSOLUTE_CLASSPATH=
for entry in `echo "${EXTRA_CLASSPATH}" | tr ':' ' '`; do
	if [ ! -e "${entry}" ]; then
		echo "No such file: ${entry}"
		exit 1
	fi

	entry="$(cd "$(dirname "${entry}")" && pwd)/$(basename "${entry}")"
	ABSOLUTE_CLASSPATH="${ABSOLUTE_CLASSPATH:+${ABSOLUTE_CLASSPATH}:}${entry}"
done
EXTRA_CLASSPATH=${ABSOLUTE_CLASSPATH}

PORT=7100
URL=http://127.0.0.1:${PORT}/Apps/WebObjects/Bench.woa
WOA=target/wo-adaptor-jetty-bench-1.0.0-SNAPSHOT.woa
mkdir -p results target/hammer
RESULTS=results/`date +%Y-%m-%d-%H%M%S`.txt
CONFIGURATION=0

if [ ! -x "${WOA}/Bench" ]; then
	echo "No application at ${WOA}: run mvn package first"
	exit 1
fi

if curl -s -o /dev/null "${URL}/b/hello"; then
	echo "Something is already answering on port ${PORT}: stop it first"
	exit 1
fi

javac -d target/hammer Hammer.java || exit 1

JVM_OPTIONS="-Xms2g -Xmx2g -Xlog:gc:file=`pwd`/target/gc-%p.log --add-exports java.base/sun.security.action=ALL-UNNAMED --add-opens java.base/java.util=ALL-UNNAMED --add-opens java.base/java.time=ALL-UNNAMED --add-opens java.base/java.lang=ALL-UNNAMED"

say() {
	echo "$@" | tee -a "${RESULTS}"
}

# Launch the application with the given arguments, and wait until it answers. The launch script appends $CLASSPATH to
# the application's classpath, which is how an -a adaptor's jars get there.
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
		[ `netstat -an | grep -c TIME_WAIT` -lt 2000 ] && break
		sleep 1
	done

	label=$1
	shift
	printf "  %-34s " "${label}" | tee -a "${RESULTS}"
	java -cp target/hammer Hammer -d ${SECONDS_PER_SCENARIO} "$@" | tee -a "${RESULTS}"
}

# The scenarios every adaptor runs
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

CPUS=`getconf _NPROCESSORS_ONLN 2>/dev/null || sysctl -n hw.ncpu`
say "wo-adaptor-jetty bench, `date`, ${CPUS} CPUs, `java -version 2>&1 | head -1`, ${SECONDS_PER_SCENARIO}s per scenario"
say "adaptor `grep -o 'wo-adaptor-jetty-[0-9][^/]*\.jar' ${WOA}/classpath.txt | head -1`"
say

say "1. Jetty adaptor, concurrent request handling"
start -WOAdaptor WOAdaptorJetty
standard
stop

if [ ${ONLY_ADAPTORS} = false ]; then
	say
	say "$((CONFIGURATION + 1)). Jetty adaptor, WO's default: no concurrent request handling"
	start -WOAdaptor WOAdaptorJetty -DBenchConcurrent=false
	scenario "hello keep-alive c=64" -c 64 "${URL}/b/hello"
	scenario "component page c=64" -c 64 "${URL}/wa/default"
	scenario "direct action sleep 200ms c=100" -c 100 "${URL}/wa/sleep?ms=200"
	stop
fi

say
say "$((CONFIGURATION + 1)). WO's classic adaptor (WODefaultAdaptor), concurrent request handling"
start -WOAdaptor WODefaultAdaptor
standard
stop

if [ ${ONLY_ADAPTORS} = false ]; then
	say
	say "$((CONFIGURATION + 1)). Jetty adaptor, JettyMaxConcurrentRequests=50"
	start -WOAdaptor WOAdaptorJetty -DJettyMaxConcurrentRequests=50
	scenario "hello keep-alive c=64" -c 64 "${URL}/b/hello"
	scenario "sleep 200ms c=1000" -c 1000 "${URL}/b/sleep?ms=200"
	stop
fi

for adaptor in ${EXTRA_ADAPTORS}; do
	say
	say "$((CONFIGURATION + 1)). ${adaptor}, concurrent request handling"
	export CLASSPATH="${EXTRA_CLASSPATH}"
	start -WOAdaptor "${adaptor}"
	standard
	stop
	unset CLASSPATH
done

say
say "Written to ${RESULTS}"
say "Charts: python3 docs/charts.py ${RESULTS}"
