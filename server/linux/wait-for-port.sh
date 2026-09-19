#!/bin/sh
# wait-for-port.sh <tcp port> [seconds]: succeed once something listens on the port (horizon-dme's ExecStartPre:
# DME registers with Medius' MPS on 10077 and dies quietly if it is not there yet).
port="$1"; limit="${2:-30}"; i=0
while [ "$i" -lt $((limit * 2)) ]; do
  ss -Hltn "sport = :$port" | grep -q . && exit 0
  i=$((i + 1)); sleep 0.5
done
echo "wait-for-port: nothing listening on $port after ${limit}s" >&2
exit 1
