# CollabOps backend-platform JD mapping

| JD area | EpochDeploy evidence |
|---|---|
| FastAPI orchestration | epoch lifecycle, auth, GitLab webhooks, evidence upload, execution coordination |
| Python + Go role split | Python owns workflow state; Go owns the final deterministic execution boundary |
| Service-to-service communication | signed HTTP service boundary with HMAC authentication and independent Go-side target observation; protobuf contract in `proto/executor.proto` documents the gRPC shape |
| PostgreSQL | normalized release/approval/receipt/outbox model plus production SQL and indexes |
| GitLab CI/CD | Pipeline Hook ingestion, SHA binding, duplicate webhook idempotency, `.gitlab-ci.yml` |
| JWT auth | signed JWT, RBAC split across operator/approver/admin |
| Image/file upload | bounded multipart upload, filename sanitization, SHA-256 evidence hashing |
| Stability | idempotent receipts, terminal state machine, fail-closed stale checks, outbox record |
| Performance/scalability | small stateless Go execution service; indexed relational query paths; local concurrency benchmark script |
| Testing/documentation | Python API tests, Go core tests, live two-service smoke test, demo runbook, verification log |
| Kubernetes optional | Docker images/Compose are ready; Kubernetes manifests intentionally deferred until container runtime verification exists |
