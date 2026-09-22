#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

command -v protoc >/dev/null
command -v protoc-gen-go >/dev/null
command -v protoc-gen-go-grpc >/dev/null

rm -rf executor-gin/gen/executorv1 orchestrator/app/gen
mkdir -p executor-gin/gen orchestrator/app/gen
touch orchestrator/app/gen/__init__.py

protoc -I proto \
  --go_out=executor-gin \
  --go_opt=module=epochdeploy/executor/ginserver \
  --go-grpc_out=executor-gin \
  --go-grpc_opt=module=epochdeploy/executor/ginserver \
  proto/executor.proto

python -m grpc_tools.protoc \
  -I proto \
  --python_out=orchestrator/app/gen \
  --grpc_python_out=orchestrator/app/gen \
  proto/executor.proto

python - <<'PY'
from pathlib import Path
path = Path("orchestrator/app/gen/executor_pb2_grpc.py")
text = path.read_text()
text = text.replace("import executor_pb2 as executor__pb2", "from . import executor_pb2 as executor__pb2")
path.write_text(text)
PY

gofmt -w executor-gin/gen
echo "gRPC code generation: PASS"
