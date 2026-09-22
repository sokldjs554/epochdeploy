# EpochDeploy

**TOCTOU-safe deployment control plane for AI-assisted DevOps.**

EpochDeploy prevents a subtle failure mode in agentic DevOps and CI/CD: a human or AI workflow approves one revision, but a mutable branch, image tag, configuration, or target changes before execution. Instead of trusting “latest”, EpochDeploy binds approval to an immutable deployment identity and re-verifies that identity at execution time.

## What makes this different

This is not a DevOps chatbot, log summarizer, or generic Internal Developer Platform. The core demo is adversarial:

- approve an exact commit + artifact digest + config hash;
- mutate one of them after approval;
- verify the Go execution boundary rejects the stale approval with a field-level diff;
- persist an auditable execution receipt;
- connect **why / who / approval / capability / evidence / execution** in an append-only Change Passport for human and AI-agent actions;
- issue short-lived **scoped capabilities** so an AI agent can execute only the approved epoch, project, environment, action, actor and fingerprint;
- run the same deterministic **ALLOW / ASK / DENY policy engine** in dry-run simulation and real capability issuance.

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
- **Go/Gin + gRPC** — production-shaped authenticated execution boundary. Docker Compose sends Observe/Execute over signed gRPC on port 9090; Gin HTTP on 9080 remains a health/compatibility adapter. Both share the same target store, capability verifier, and TOCTOU core.
- **PostgreSQL** — epochs, agent change requests, append-only passport events, approvals, live target observations, evidence, receipts, outbox.
- **GitLab CI** — test stages plus a Docker Compose contract job.
- **gRPC runtime** — `proto/executor.proto` is generated into checked, drift-verified Go/Python bindings. FastAPI signs deterministic protobuf requests in gRPC metadata; the Go executor verifies the signature before Observe/Execute.

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

This switches the orchestrator to PostgreSQL and talks to the separate **Go/Gin** executor over **signed gRPC**. The executor exposes gRPC internally on 9090 and keeps Gin HTTP on 9080 for health/compatibility. Observe/Execute protobuf requests are HMAC-SHA256 signed with timestamp + RPC method + deterministic protobuf bytes.

## Test strategy

- deterministic fingerprint unit tests;
- auth/RBAC tests;
- immutable-ref validation;
- GitLab webhook token + commit-SHA binding + duplicate-event idempotency;
- evidence upload hashing + path sanitization;
- happy-path execution;
- stale commit/artifact/config fail-closed tests;
- idempotent execution receipts;
- Go core/server tests, including HTTP HMAC checks, gRPC metadata authentication, cross-runtime fingerprint vectors, capability scope enforcement, and stale-target behavior;
- live HTTP smoke script (`scripts/smoke.sh`);
- Chromium browser E2E across Release Control, **Policy Simulator**, Change Passport, Evidence, Execution Receipts, and Integrations (`scripts/browser-e2e.py`);
- GitLab Docker Compose integration job.

## Verification boundary

The local verification harness runs Python tests, Go race/vet checks, package installation, signed two-service HTTP smoke tests, and repeated stale-approval checks. A separate Chromium E2E script clicks through the service UI, performs a real evidence upload, inspects execution receipts and integration status, then verifies both `EXECUTED` and `DENIED_STALE` flows. A supplementary GitHub-hosted workflow also builds the Docker images, starts the Compose stack with **PostgreSQL 16**, verifies the production-shaped database path, and repeats the end-to-end smoke flow.

GitLab CI remains the job-aligned pipeline contract in `.gitlab-ci.yml`; a real GitLab Runner has not been connected in this environment. The Gin executor and generated gRPC transport are exercised in Docker Compose and remote Chromium E2E. Kubernetes is still not claimed as executed; browser E2E is part of the verification evidence. See `docs/verification.md` for the exact evidence and remaining boundaries.

See `docs/architecture.md`, `docs/demo-script.md`, and `docs/verification.md`.
