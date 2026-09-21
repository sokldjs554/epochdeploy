# Verification log

Verification date: 2026-09-21 (Asia/Seoul)

This document records only checks actually executed against the current repository state. Source presence is not counted as runtime verification.

## Full local verification

After the latest application changes, `scripts/verify-local.sh` completed successfully **three consecutive times**.

Each successful full round performed:

- `python -m compileall -q orchestrator`
- `node --check orchestrator/app/static/app.js`
- `gofmt -l executor` (must return no files)
- `go vet ./...`
- `go test -race -count=1 ./...`
- `python -m pytest` -> **29 passed**
- build a Python wheel from `pyproject.toml`, install it into an isolated target, import `app.main`, and verify packaged static assets
- build a fresh Go executor binary
- assert the dedicated verification ports are unused before starting services, preventing a stale process from satisfying health checks
- start Go and FastAPI as separate processes with signed HTTP transport
- verify both `/healthz` endpoints and confirm both newly spawned PIDs remain alive
- send an unsigned executor request and require **HTTP 401**
- fetch the actual dashboard HTML and JavaScript and syntax-check the served JavaScript
- execute the end-to-end smoke script **three times per full round**

The smoke script verifies both:

1. exact approved identity -> `EXECUTED`
2. artifact digest changed after approval -> `DENIED_STALE`

Result: the latest candidate state has three consecutive full verification passes and **nine end-to-end smoke repetitions**.

## Python/API coverage highlights

The 29 passing tests include:

- JWT login and unauthenticated rejection
- RBAC: operator cannot approve
- security headers/CSP
- strict immutable identity validation
- client cannot forge `pipeline_status=success` when creating an epoch
- approval blocked until a verified GitLab Pipeline Hook marks the matching commit successful
- GitLab webhook token validation
- GitLab commit-SHA mismatch blocks approval
- duplicate webhook idempotency
- webhook payload size limit
- evidence upload hashing and path sanitization
- evidence metadata bounds
- exact-match execution
- missing approval rejection
- missing target observation rejection
- commit/artifact/config drift rejection
- terminal-state enforcement
- execution idempotency and stale-diff replay
- approval idempotency
- executor observation failures mapped to a 502 boundary error
- Python/Go shared fingerprint test vector

## Go boundary coverage highlights

Go tests cover:

- exact identity execution
- commit drift fail-closed behavior
- deterministic fingerprinting
- the shared Python/Go fingerprint vector and canonical whitespace behavior
- HMAC request authentication
- body tamper rejection
- stale timestamp rejection
- independent target observation storage rather than caller-supplied observed identity at execute time

The server also uses explicit read/write/header/idle timeouts and graceful SIGTERM shutdown.

## Executor concurrency benchmark

Command: `python scripts/benchmark_executor.py`

Current workload: one signed target observation followed by 1,000 signed execution checks with concurrency 50. The Go boundary resolves the target from its own observation store for every execute request.

| round | failures | throughput | p50 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| 1 | 0 | 556.6 req/s | 59.52 ms | 258.57 ms | 401.88 ms |
| 2 | 0 | 614.2 req/s | 55.38 ms | 227.00 ms | 320.50 ms |
| 3 | 0 | 585.5 req/s | 54.34 ms | 257.79 ms | 348.14 ms |

These are local-environment measurements, not production capacity claims.

## Fixes found by verification rather than assumption

The verification process itself exposed and fixed several issues:

- SQLite teardown originally reused pooled handles after the DB file was deleted.
- FastAPI lifespan deprecation warning was removed.
- the first verification script built Go from the wrong directory.
- a stale old process on port 9080 could have made a new failed binary look healthy; verification now uses dedicated ports, asserts they are free, and checks the exact spawned PIDs.
- Python trimmed identity fields before hashing while Go initially did not; both runtimes now share a fixed fingerprint vector.
- epoch creation originally trusted caller-supplied pipeline status; it now always starts pending and only GitLab evidence can make it approvable.
- the first service split let Python send both expected and observed values to Go; the Go boundary now owns the observed target and execute requests send only the approved expected identity.
- executor traffic was initially unauthenticated; it now uses timestamped HMAC-SHA256 and rejects unsigned/tampered/stale requests.
- UI diff rendering originally used `innerHTML`; it now builds DOM nodes with text content and ships CSP/security headers.
- the PostgreSQL schema and service path used `pipeline_status=pending`, but the SQLAlchemy model default still said `success`; the ORM default is now `pending` and a direct-model regression test locks this invariant.

## Not yet verified in this environment

These items are **not** claimed complete:

- **Docker Compose build/run:** Docker is not installed in the current execution environment.
- **Real PostgreSQL runtime/query plans/concurrency:** no PostgreSQL server/client is installed here. The reference schema is in `db/migrations/001_initial.sql`; SQLite is only the local/test mode.
- **Actual GitLab Runner execution:** `.gitlab-ci.yml` is present and structurally reviewed, but no runner is connected here.
- **Generated gRPC transport:** `proto/executor.proto` documents the target service contract, but `protoc` and required networked Go dependencies are unavailable here. The verified transport is signed HTTP/JSON.
- **Gin transport:** the verified Go service deliberately uses the standard library HTTP server; Gin is not falsely claimed as executed.
- **Browser screenshot/E2E clicks:** dashboard HTML/JS is served and syntax-checked. A Chromium headless screenshot attempt in this environment did not terminate reliably, so visual browser verification remains open.
- **Kubernetes deployment:** intentionally deferred until the container path can be executed and verified.
- **Remote GitHub repository:** `sokldjs554/epochdeploy` now exists. Source import is performed through the connected GitHub integration; remote tree integrity is checked against local Git blob SHAs before the release handoff is considered synchronized.
