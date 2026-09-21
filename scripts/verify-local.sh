#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

EXECUTOR_PORT=${EPOCHDEPLOY_VERIFY_EXECUTOR_PORT:-19080}
API_PORT=${EPOCHDEPLOY_VERIFY_API_PORT:-18000}
EXECUTOR_SECRET='verify-executor-secret'

python -m compileall -q orchestrator
node --check orchestrator/app/static/app.js
if [[ -n "$(gofmt -l executor)" ]]; then
  echo "gofmt required" >&2
  gofmt -l executor >&2
  exit 1
fi
(cd executor && go vet ./... && go test -race -count=1 ./...)
python -m pytest

rm -rf /tmp/epochdeploy-package
python -m pip install --quiet --disable-pip-version-check --no-deps --no-build-isolation --target /tmp/epochdeploy-package .
PYTHONPATH=/tmp/epochdeploy-package python - <<'PY_PACKAGE'
from pathlib import Path
import app
import app.main
assert (Path(app.__file__).parent / "static" / "index.html").exists()
print("python package install: PASS")
PY_PACKAGE

# Never let a stale process satisfy this run's health checks.
python - "$EXECUTOR_PORT" "$API_PORT" <<'PY'
import socket, sys
for raw in sys.argv[1:]:
    port=int(raw)
    with socket.socket() as s:
        s.settimeout(.2)
        if s.connect_ex(('127.0.0.1', port)) == 0:
            raise SystemExit(f"verification port already in use: {port}")
PY

(cd executor && go build -o /tmp/epochdeploy-executor ./cmd/server)
rm -f "$ROOT/verify.db"
rm -rf "$ROOT/verify_uploads"
rm -f /tmp/epochdeploy-executor.log /tmp/epochdeploy-api.log

EPOCHDEPLOY_EXECUTOR_PORT="$EXECUTOR_PORT" \
EPOCHDEPLOY_EXECUTOR_HMAC_SECRET="$EXECUTOR_SECRET" \
/tmp/epochdeploy-executor >/tmp/epochdeploy-executor.log 2>&1 &
GO_PID=$!

EPOCHDEPLOY_EXECUTOR_MODE=http \
EPOCHDEPLOY_EXECUTOR_URL="http://127.0.0.1:$EXECUTOR_PORT" \
EPOCHDEPLOY_EXECUTOR_HMAC_SECRET="$EXECUTOR_SECRET" \
EPOCHDEPLOY_DATABASE_URL="sqlite:///$ROOT/verify.db" \
EPOCHDEPLOY_UPLOAD_DIR="$ROOT/verify_uploads" \
EPOCHDEPLOY_JWT_SECRET='verify-secret-0123456789abcdef0123456789' \
EPOCHDEPLOY_DEMO_MODE=true \
PYTHONPATH=orchestrator uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" >/tmp/epochdeploy-api.log 2>&1 &
API_PID=$!

cleanup(){ kill "$API_PID" "$GO_PID" 2>/dev/null || true; wait "$API_PID" "$GO_PID" 2>/dev/null || true; }
trap cleanup EXIT

sleep .15
if ! kill -0 "$GO_PID" 2>/dev/null; then cat /tmp/epochdeploy-executor.log >&2; exit 1; fi
if ! kill -0 "$API_PID" 2>/dev/null; then cat /tmp/epochdeploy-api.log >&2; exit 1; fi

for i in $(seq 1 50); do curl -fsS "http://127.0.0.1:$EXECUTOR_PORT/healthz" >/dev/null 2>&1 && break; sleep .1; done
for i in $(seq 1 80); do curl -fsS "http://127.0.0.1:$API_PORT/healthz" >/dev/null 2>&1 && break; sleep .1; done
kill -0 "$GO_PID"
kill -0 "$API_PID"

UNSIGNED_STATUS=$(curl -sS -o /tmp/epochdeploy-unsigned.json -w '%{http_code}' \
  -H 'content-type: application/json' \
  -d '{"expected":{},"observed":{}}' "http://127.0.0.1:$EXECUTOR_PORT/v1/execute")
[[ "$UNSIGNED_STATUS" == "401" ]]

curl -fsS "http://127.0.0.1:$API_PORT/" | grep -q 'EpochDeploy Control Plane'
curl -fsS "http://127.0.0.1:$API_PORT/static/app.js" -o /tmp/epochdeploy-app.js
node --check /tmp/epochdeploy-app.js

for round in 1 2 3; do
  echo "smoke round $round"
  BASE="http://127.0.0.1:$API_PORT" bash scripts/smoke.sh
done

kill -0 "$GO_PID"
kill -0 "$API_PID"
echo "local verification: PASS"
