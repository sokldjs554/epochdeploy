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
- `python -m pytest` -> **35 passed**
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

## Remote Docker/PostgreSQL verification

A supplementary GitHub pull-request workflow (`Remote Verification`) was then executed against the synchronized repository. Its first complete run (`35595521040`) finished with both jobs successful:

- **unit-and-package:** project installation, all **29 Python tests**, Python package build, `go vet`, `go test -race -count=1 ./...`, and JavaScript syntax check.
- **compose-postgres-smoke:** `docker compose config`, image build/start, PostgreSQL 16 readiness, existence of the `deployment_epochs` table in the live PostgreSQL database, and **three repeated two-service smoke rounds**, followed by clean teardown.

This closes the earlier runtime gap for Docker Compose and the PostgreSQL-backed application path. It does **not** substitute for an actual GitLab Runner execution, and it is not a production capacity benchmark.

## Browser E2E verification

After the service-style navigation was made functional, `scripts/browser-e2e.py` completed successfully **three consecutive times** against freshly started FastAPI + Go processes. Each round used Chromium and exercised the actual UI JavaScript and real backend APIs:

1. create epoch -> approve -> execute -> `EXECUTED` / `MATCH`;
2. open **Evidence**, upload a real multipart provenance file, and verify its SHA-256 ledger entry;
3. open **Execution Receipts** and verify the stored happy-path receipt;
4. open **Integrations** and verify GitLab, executor, database, and the explicitly `contract-only` gRPC status;
5. create a fresh epoch -> approve -> mutate artifact digest -> execute -> `DENIED_STALE` / `BLOCKED` with an `artifact_digest` diff;
6. reopen **Execution Receipts** and verify the blocked receipt.

Each round produced seven screenshots. Across all three rounds there were **zero browser console errors, page errors, failed requests, or HTTP 4xx/5xx responses** during the UI flow. The sandbox's managed Chromium blocks top-level localhost navigation, so the E2E runner has a documented fallback: it loads the exact repository HTML/CSS/JS in-memory and proxies browser fetch/XHR requests to the real local FastAPI service. On unrestricted runners it navigates to the served page directly.

### Remote Chromium evidence

GitHub-hosted `Remote Verification` run **#5** (run id `35608531620`) independently exercised the same update on the production-shaped Compose path and completed both jobs successfully:

- **unit-and-package:** all **31 Python tests**, package build, `go vet`, `go test -race -count=1 ./...`, and JavaScript syntax check.
- **compose-postgres-smoke:** Docker image build/start, PostgreSQL 16 runtime/schema check, three two-service smoke rounds, Chromium installation, and the complete browser E2E flow above.
- the workflow uploaded the seven remote Chromium screenshots as artifact `epochdeploy-browser-e2e` (artifact id `10643117861`, SHA-256 `4673c87a596e030a20cab636a149393fe972d69f1553ca0004bc3eaca6c1043d`).

The downloaded remote artifact was inspected after the run. Evidence, Integrations, and stale-approval screens rendered without clipping or layout breakage; the Integrations view reported the live database backend as `postgresql`, and the stale flow visibly showed `DENIED_STALE` / `BLOCKED` with the approved-vs-observed artifact digest difference.

## Agent Governance / Change Passport verification

Remote Verification run **#19** (run id `35721783280`) exercised the first governance expansion on the Gin + PostgreSQL Compose path.

- Python regression suite: **35 passed**. New coverage verifies AI-agent provenance, WHY/WHO preservation, the complete `EPOCH_CREATED → CHANGE_REQUESTED → PIPELINE_VERIFIED → APPROVED → EVIDENCE_ATTACHED → EXECUTED` sequence, idempotent approval audit behavior, and visible pipeline SHA rejection.
- the production-shaped Compose job rebuilt the Gin executor, verified PostgreSQL, passed the repeated two-service smoke flow, and passed the expanded Chromium E2E.
- Chromium now visits **Change Passport** in both happy and blocked releases and verifies `ISSUE-184`, `release-agent-01`, approval, `EXECUTED`, `DENIED_STALE`, and the append-only timeline.
- downloaded screenshots were visually inspected; WHY / WHO / WHAT / APPROVAL / EVIDENCE / EXECUTION cards and the timeline render without clipping in both terminal states.

## Python/API coverage highlights

The 35 passing tests include:

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
- authenticated evidence-ledger listing and metadata integrity
- integration-status reporting without exposing configured secrets
- exact-match execution
- missing approval rejection
- missing target observation rejection
- commit/artifact/config drift rejection
- terminal-state enforcement
- execution idempotency and stale-diff replay
- approval idempotency
- executor observation failures mapped to a 502 boundary error
- Python/Go shared fingerprint test vector

## Verified Gin production-shaped runtime

Pull-request workflow run **#14** (run id `35686009639`) verified the Gin executor on the exact dependency lock committed to `executor-gin/go.mod` and `executor-gin/go.sum`.

- the **unit-and-package** job passed all **31 Python tests**, Python package build, stdlib Go `vet/race`, Gin module-lock stability (`go mod tidy` + zero diff), Gin `go vet`, Gin `go test -race -count=1 ./...`, and JavaScript syntax.
- the **compose-postgres-smoke** job built and started the Gin executor image, started PostgreSQL 16 and FastAPI, verified the live PostgreSQL schema, passed three signed two-service smoke rounds, and passed the complete Chromium browser E2E.
- the browser E2E required the Integrations view to report `implementation=gin`; the downloaded artifact confirmed `Go Executor / implementation: gin`, `Database / backend: postgresql`, and gRPC remaining explicitly `CONTRACT-ONLY`.
- screenshot artifact `epochdeploy-browser-e2e`: artifact id `10676288669`, SHA-256 `e22a4ff19935a8e8ee476479aaa9638a9157da62674eeaa2bbd2a82b757f53ba`.

This means Gin is no longer a keyword-only or source-only claim: it is the executor implementation used by the verified Docker Compose path.

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

- **PostgreSQL query-plan and database-lock contention analysis:** the PostgreSQL-backed Compose path is now remotely verified, but `EXPLAIN (ANALYZE, BUFFERS)` tuning and multi-writer lock-contention testing have not been run.
- **Actual GitLab Runner execution:** `.gitlab-ci.yml` is present and structurally reviewed, but no runner is connected here. The successful GitHub-hosted workflow is supplementary validation, not a claim that GitLab CI itself ran.
- **Generated gRPC transport:** `proto/executor.proto` documents the target service contract, but `protoc` and required networked Go dependencies are unavailable here. The verified transport is signed HTTP/JSON.
- **Kubernetes deployment:** intentionally deferred until the container path can be executed and verified.
- **Remote GitHub repository:** `sokldjs554/epochdeploy` exists. The previous release was compared file-by-file against local Git blob SHAs before merge; this verification discipline remains the handoff requirement for the current UI/E2E update.
