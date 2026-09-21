# EpochDeploy

**TOCTOU-safe deployment control plane for AI-assisted DevOps.**

EpochDeploy prevents a subtle failure mode in agentic DevOps and CI/CD: a human or AI workflow approves one revision, but a mutable branch, image tag, configuration, or target changes before execution. Instead of trusting “latest”, EpochDeploy binds approval to an immutable deployment identity and re-verifies that identity at execution time.

## What makes this different

This is not a DevOps chatbot, log summarizer, or generic Internal Developer Platform. The core demo is adversarial:

- approve an exact commit + artifact digest + config hash;
- mutate one of them after approval;
- verify the Go execution boundary rejects the stale approval with a field-level diff;
- persist an auditable execution receipt.

## Architecture

```text
GitLab Pipeline Hook ─┐
Evidence Upload ──────┼──> FastAPI Orchestrator ──> PostgreSQL
JWT Operator/Approver ┘          │                    │
                                 │ execution request  ├─ approvals
                                 v                    ├─ receipts
                         Go Execution Boundary        └─ outbox
                                 │
                                 └─ exact identity re-check
                                    EXECUTED / DENIED_STALE
```

### Role split

- **FastAPI** — orchestration, GitLab webhook ingestion, JWT/RBAC, evidence upload, relational workflow state, receipts.
- **Go** — authenticated execution boundary, independent live-target observation, and final TOCTOU check.
- **PostgreSQL** — epochs, approvals, live target observations, evidence, receipts, outbox.
- **GitLab CI** — test stages plus a Docker Compose contract job.
- **gRPC contract** — `proto/executor.proto`; HTTP/JSON is the first runnable transport so local development does not depend on `protoc`.

## Demo credentials

Local-only seeded users:

| user | password | role |
|---|---|---|
| `operator` | `operator-demo` | create/execute |
| `approver` | `approver-demo` | approve |
| `admin` | `admin-demo` | demo/reset/admin |

Never reuse these credentials outside the demo.

## Local run without Docker

```bash
make test
make run-go
# another shell
make run-api
```

Open `http://localhost:8000`.

## Production-shaped run

```bash
docker compose up --build
```

This switches the orchestrator to PostgreSQL and talks to the separate Go service over signed HTTP. Executor requests use timestamped HMAC-SHA256 and the executor port stays internal to the Compose network. See `proto/executor.proto` for the gRPC service contract.

## Test strategy

- deterministic fingerprint unit tests;
- auth/RBAC tests;
- immutable-ref validation;
- GitLab webhook token + commit-SHA binding + duplicate-event idempotency;
- evidence upload hashing + path sanitization;
- happy-path execution;
- stale commit/artifact/config fail-closed tests;
- idempotent execution receipts;
- Go core/server tests, including HMAC tamper/stale-signature checks and cross-runtime fingerprint vectors;
- live HTTP smoke script (`scripts/smoke.sh`);
- GitLab Docker Compose integration job.

## Current verification boundary

The repository is designed for PostgreSQL, Docker Compose, and GitLab CI, but those require a runtime that has Docker/PostgreSQL/networked dependency installation. SQLite exists only to let core orchestration behavior be tested in a zero-dependency environment. Verification evidence should distinguish those two modes rather than claiming a deployment that was not actually run.

See `docs/architecture.md`, `docs/demo-script.md`, and `docs/verification.md`.
