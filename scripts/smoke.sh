#!/usr/bin/env bash
set -euo pipefail
BASE=${BASE:-http://127.0.0.1:8000}
login() {
  curl -fsS -H 'content-type: application/json' -d "{\"username\":\"$1\",\"password\":\"$2\"}" "$BASE/api/auth/token" | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])'
}
ADMIN=$(login admin admin-demo)
OP=$(login operator operator-demo)
AP=$(login approver approver-demo)
EPOCH=$(curl -fsS -X POST -H "Authorization: Bearer $ADMIN" "$BASE/api/demo/bootstrap" | python -c 'import sys,json; print(json.load(sys.stdin)["id"])')
curl -fsS -X POST -H "Authorization: Bearer $ADMIN" "$BASE/api/demo/gitlab-success/$EPOCH" >/dev/null
curl -fsS -X POST -H "Authorization: Bearer $AP" "$BASE/api/epochs/$EPOCH/approve" >/dev/null
curl -fsS -X POST -H 'content-type: application/json' -H "Authorization: Bearer $OP" -d '{"idempotency_key":"smoke-happy-0001"}' "$BASE/api/epochs/$EPOCH/execute" | grep -q 'EXECUTED'
EPOCH=$(curl -fsS -X POST -H "Authorization: Bearer $ADMIN" "$BASE/api/demo/bootstrap" | python -c 'import sys,json; print(json.load(sys.stdin)["id"])')
curl -fsS -X POST -H "Authorization: Bearer $ADMIN" "$BASE/api/demo/gitlab-success/$EPOCH" >/dev/null
curl -fsS -X POST -H "Authorization: Bearer $AP" "$BASE/api/epochs/$EPOCH/approve" >/dev/null
curl -fsS -X POST -H 'content-type: application/json' -H "Authorization: Bearer $ADMIN" -d '{"field":"artifact_digest","value":"sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"}' "$BASE/api/demo/drift/$EPOCH" >/dev/null
curl -fsS -X POST -H 'content-type: application/json' -H "Authorization: Bearer $OP" -d '{"idempotency_key":"smoke-drift-0001"}' "$BASE/api/epochs/$EPOCH/execute" | grep -q 'DENIED_STALE'
echo 'smoke: PASS'
