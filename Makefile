.PHONY: test test-python test-go test-go-gin verify run-api run-go run-go-gin demo-check benchmark

EXECUTOR_SECRET ?= local-executor-secret

test: test-python test-go

test-python:
	python -m pytest

test-go:
	cd executor && go test -race ./...

test-go-gin:
	cd executor-gin && go test -race ./...

verify:
	bash scripts/verify-local.sh

run-api:
	EPOCHDEPLOY_DEMO_MODE=true EPOCHDEPLOY_EXECUTOR_MODE=http EPOCHDEPLOY_EXECUTOR_HMAC_SECRET=$(EXECUTOR_SECRET) PYTHONPATH=orchestrator uvicorn app.main:app --host 0.0.0.0 --port 8000

run-go:
	cd executor && EPOCHDEPLOY_EXECUTOR_HMAC_SECRET=$(EXECUTOR_SECRET) go run ./cmd/server

run-go-gin:
	cd executor-gin && EPOCHDEPLOY_EXECUTOR_HMAC_SECRET=$(EXECUTOR_SECRET) go run ./cmd/server

demo-check:
	BASE=http://127.0.0.1:8000 bash scripts/smoke.sh

benchmark:
	EPOCHDEPLOY_EXECUTOR_HMAC_SECRET=$(EXECUTOR_SECRET) python scripts/benchmark_executor.py
