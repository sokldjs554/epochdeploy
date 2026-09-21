# Architecture

EpochDeploy is a small control plane for one narrow systems problem: **the thing approved for deployment can differ from the thing executed later**.

## Request path

1. GitLab pipeline evidence arrives at the FastAPI orchestrator.
2. The orchestrator creates an immutable deployment epoch from five identity fields: project, environment, commit SHA, artifact digest, and configuration hash.
3. A separate approver binds approval to the epoch fingerprint.
4. The Go executor maintains the most recent target observation behind its authenticated internal boundary; execute requests contain only the approved expected identity, not a caller-supplied observed value.
5. Immediately before execution, the Go executor recomputes the observed fingerprint and compares it with the approved identity. Exact match -> `EXECUTED`. Any mismatch -> `DENIED_STALE` with a field-level diff.
6. The orchestrator stores an execution receipt and a transactional-outbox event in the same DB transaction.

## Why Python + Go

- **Python/FastAPI:** orchestration, auth, GitLab webhooks, evidence ingestion, relational workflow state, UI API.
- **Go:** small deterministic execution boundary with a tiny attack surface. The demo adapter keeps only ephemeral live-target observations; workflow state remains in PostgreSQL. A production adapter would resolve the target directly from the deployment environment.

The transport boundary is deliberately explicit. `proto/executor.proto` is the intended gRPC contract. The first runnable transport is HTTP/JSON so the repository remains locally testable without code generation; gRPC transport can be generated from the same service contract in a network-enabled build environment.

## PostgreSQL model

The production `docker-compose.yml` uses PostgreSQL. SQLite is supported only as a zero-dependency developer/test mode. Indexes are included for the main read paths: project/environment recency, pipeline lookup, state, receipts by epoch/time, and outbox publication state.

## Service-to-service trust

The runnable HTTP transport is not anonymous. FastAPI signs the exact request body with HMAC-SHA256 plus a Unix timestamp; the Go boundary rejects missing/invalid signatures and requests outside a 30-second clock-skew window. In Docker Compose the executor is only exposed on the internal service network.
