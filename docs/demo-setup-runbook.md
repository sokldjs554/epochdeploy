# Demo Setup Runbook

This runbook is intentionally executable and conservative: if preflight fails, do not record or present the demo as verified.

## 1. Preflight

```bash
./scripts/verify-local.sh
```

Expected result: Python tests, Go tests/vet, static checks, service build, and repeated live smoke flows all pass.

## 2. Start the execution boundary

```bash
make run-go
```

Health check: `GET http://127.0.0.1:9080/healthz`.

## 3. Start the orchestrator

From the repository root in a second terminal:

```bash
make run-api
```

Open `http://127.0.0.1:8000/`.

## 4. Demo sequence

1. Run **Exact identity / safe execute** and show `EXECUTED`.
2. Create a fresh epoch, approve it, mutate only `artifact_digest`, then execute.
3. Show `DENIED_STALE` and the field-level `artifact_digest` diff.
4. Retry with the same idempotency key and show the same receipt rather than a second execution.
5. Send a GitLab pipeline webhook whose SHA does not match the epoch commit and show that approval remains blocked.

## 5. What to say

- The AI agent may propose or initiate a deployment, but it does not get to redefine the approved identity at execution time.
- Approval is bound to immutable inputs: commit SHA, image digest, config hash, project, and environment.
- The Go boundary is deliberately deterministic and fail-closed. It does not use an LLM for the final authorization decision.
- PostgreSQL, Docker Compose, GitLab Runner, gRPC generation, Gin transport, and Kubernetes must only be presented as verified after those environments have actually been exercised.
