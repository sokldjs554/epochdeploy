# Architecture

EpochDeploy is a small control plane for one narrow systems problem: **the thing approved for deployment can differ from the thing executed later**.

## Request path

1. GitLab pipeline evidence arrives at the FastAPI orchestrator.
2. The orchestrator creates an immutable deployment epoch from five identity fields: project, environment, commit SHA, artifact digest, and configuration hash.
3. Agent-originated work is linked to a one-to-one Change Request that records **why** the change exists, the AI actor, the human requester, and the requested action.
4. An append-only Change Passport records GitLab verification, human approval, evidence attachment, and terminal execution events.
5. A separate approver binds approval to the epoch fingerprint.
6. For AI-agent-originated changes, the approver issues a five-minute HS256 capability scoped to epoch, actor, project, environment, action, and approved fingerprint. Only grant metadata is persisted; the raw token is returned once.
7. FastAPI verifies the grant before dispatch, and the Go/Gin executor independently verifies the capability signature, expiry, scope, and expected release fingerprint.
8. The Go executor maintains the most recent target observation behind its authenticated internal boundary; execute requests contain only the approved expected identity, not a caller-supplied observed value.
9. Immediately before execution, the Go executor recomputes the observed fingerprint and compares it with the approved identity. Exact match -> `EXECUTED`. Any mismatch -> `DENIED_STALE` with a field-level diff.
10. The orchestrator stores an execution receipt and a transactional-outbox event in the same DB transaction.

## Why Python + Go

- **Python/FastAPI:** orchestration, auth, GitLab webhooks, evidence ingestion, relational workflow state, UI API.
- **Go/Gin:** the production-shaped Compose path runs a Gin adapter around the same deterministic execution core. The stdlib adapter is retained for zero-dependency local verification. Both keep only ephemeral live-target observations; workflow state remains in PostgreSQL.

The transport boundary is deliberately explicit. `proto/executor.proto` is the intended gRPC contract. The first runnable transport is HTTP/JSON so the repository remains locally testable without code generation; gRPC transport can be generated from the same service contract in a network-enabled build environment.

## PostgreSQL model

The production `docker-compose.yml` uses PostgreSQL. SQLite is supported only as a zero-dependency developer/test mode. Indexes are included for the main read paths: project/environment recency, pipeline lookup, state, receipts by epoch/time, and outbox publication state.

## Service-to-service trust

The verified production-shaped HTTP transport is Gin-based and is not anonymous. FastAPI signs the exact request body with HMAC-SHA256 plus a Unix timestamp; the Go boundary rejects missing/invalid signatures and requests outside a 30-second clock-skew window. In Docker Compose the executor is only exposed on the internal service network.
