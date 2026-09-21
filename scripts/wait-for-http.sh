#!/bin/sh
set -eu
url="$1"; attempts="${2:-60}"
i=0
while [ "$i" -lt "$attempts" ]; do
  if curl -fsS "$url" >/dev/null 2>&1; then exit 0; fi
  i=$((i+1)); sleep 1
done
echo "timeout waiting for $url" >&2
exit 1
