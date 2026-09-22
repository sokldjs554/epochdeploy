# Architecture

EpochDeploy is a small control plane for one narrow systems problem: **the thing approved for deployment can differ from the thing executed later**.

## Request path

1. GitLab pipeline evidence arrives at the FastAPI orchestrator.
2. The orchestrator creates an immutable deployment epoch from five identity fields: project, environment, commit SHA, artifact digest, and configuration hash.
3. Agent-originated work is linked to a one-to-one Change Request that records **why** the change exists, the AI actor, the human requester, and the requested action.
4. An append-only Change Passport records GitLab verification, human approval, evidence attachment, and terminal execution events.
5. A separate approver binds approval to the epoch fingerprint.
6. The deterministic policy engine evaluates agent action + environment before authority is issued: non-production deploy is `ALLOW`, production deploy is `ASK`, and destructive actions are `DENY`.
7. The same engine powers a side-effect-free dry-run API and the real capability gate. `ASK` requires human approval; `ALLOW` can proceed with verified pipeline + scoped capability; `DENY` cannot receive a capability.
8. For AI-agent-originated changes, an HS256 capability is scoped to epoch, actor, project, environment, action, approved fingerprint, and expiry. Only grant metadata is persisted; the raw token is returned once.
9. FastAPI verifies the grant before dispatch, and the Go/Gin executor independently verifies the capability signature, expiry, scope, and expected release fingerprint.
10. The Go executor maintains the most recent target observation behind its authenticated internal boundary; execute requests contain only the approved expected identity, not a caller-supplied observed value.
11. Immediately before execution, the Go executor recomputes the observed fingerprint and compares it with the approved identity. Exact match -> `EXECUTED`. Any mismatch -> `DENIED_STALE` with a field-level diff.
12. The orchestrator stores an execution receipt and a transactional-outbox event in the same DB transaction.

## Why Python + Go

- **Python/FastAPI:** orchestration, auth, GitLab webhooks, evidence ingestion, relational workflow state, UI API.
- **Go/Gin:** the production-shaped Compose path runs a Gin adapter around the same deterministic execution core. The stdlib adapter is retained for zero-dependency local verification. Both keep only ephemeral live-target observations; workflow state remains in PostgreSQL.

The transport boundary is deliberately explicit. `proto/executor.proto` is generated into Go and Python bindings and the production-shaped Compose path uses gRPC for Health, Observe, and Execute. Generated bindings are regenerated in CI and must produce zero diff. The Gin HTTP adapter remains available for health/compatibility and shares the same deterministic execution core and live-target store.

## PostgreSQL model

The production `docker-compose.yml` uses PostgreSQL. SQLite is supported only as a zero-dependency developer/test mode. Indexes are included for the main read paths: project/environment recency, pipeline lookup, state, receipts by epoch/time, and outbox publication state.

## Service-to-service trust

The verified production-shaped transport is gRPC and is not anonymous. FastAPI deterministically serializes each protobuf Observe/Execute request and signs `timestamp + RPC method + protobuf bytes` with HMAC-SHA256 metadata. A Go unary interceptor independently serializes the request, validates that signature, and rejects missing/invalid or stale metadata outside a 30-second clock-skew window. Capability scope is then verified before the shared live-target/TOCTOU check. Gin HTTP remains an internal compatibility adapter; neither executor port is published to the host in Compose.
