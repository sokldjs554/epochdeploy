# CollabOps backend-platform JD mapping

| JD area | EpochDeploy evidence |
|---|---|
| FastAPI orchestration | epoch lifecycle, auth, GitLab webhooks, evidence upload, execution coordination |
| Python + Go role split | Python owns workflow state; Go owns the final deterministic execution boundary; the production-shaped adapter is implemented with Gin |
| Service-to-service communication | production Compose uses signed gRPC between FastAPI and Go; deterministic protobuf bytes are authenticated with HMAC metadata, while Gin HTTP remains a compatibility adapter |
| PostgreSQL | normalized release/approval/receipt/outbox model plus production SQL and indexes |
| GitLab CI/CD | Pipeline Hook ingestion, SHA binding, duplicate webhook idempotency, `.gitlab-ci.yml` |
| JWT auth | signed JWT, RBAC split across operator/approver/admin |
| Image/file upload | bounded multipart upload, filename sanitization, SHA-256 evidence hashing |
| Stability | idempotent receipts, terminal state machine, fail-closed stale checks, outbox record |
| AI DevOps execution governance | AI-agent change provenance, ALLOW/ASK/DENY policy dry-run, production approval gates, short-lived scoped capability, Gin-side capability verification, and append-only Change Passport timeline |
| Performance/scalability | small stateless Go execution service; indexed relational query paths; local concurrency benchmark script |
| Testing/documentation | Python API/client tests, stdlib Go core tests, Gin + gRPC bufconn tests, codegen drift verification, live two-service smoke, Chromium E2E, demo runbook, verification log |
| Kubernetes optional | Docker images/Compose are ready; Kubernetes manifests intentionally deferred until container runtime verification exists |
