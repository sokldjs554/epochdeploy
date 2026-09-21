# Pre-build research notes

Research date: 2026-09-21

Scope note: these are publicly discoverable open-source/reference projects with overlap to the posting, **not confirmed CollabOps applicants**. The goal was to avoid a portfolio theme that already looks routine.

## CollabOps product direction

- Official product: https://collabops.ai/
- The product connects planning/issues to code review and then CI/CD, testing, security, and deployment. That makes a generic CRUD backend or isolated chatbot a weak match; the project should demonstrate workflow orchestration and a real execution boundary.

## Similar public projects reviewed

### Merkuryo/internal-developer-platform

- https://github.com/Merkuryo/internal-developer-platform
- FastAPI + PostgreSQL + Redis.
- Service catalog, golden-path templates, mock deployments, dark dashboard, Docker Compose, OpenAPI.
- Takeaway: this is already a polished and understandable portfolio shape, so another service-catalog / “deploy button” IDP would be too common.

### ideaweaver-ai/devops-open-agent

- https://github.com/ideaweaver-ai/devops-open-agent
- AI-powered DevOps investigations across Kubernetes/AWS/security/performance, with integrations and a full product UI.
- Demo emphasizes platform overview, live investigation, AI diagnosis, integrations, schedules, and self-hosted setup.
- Takeaway: “LLM reads logs and suggests a fix” is crowded. EpochDeploy should make its strongest moment a deterministic systems guarantee rather than another diagnosis chat flow.

### open-devops-agent/open-devops-agent

- https://github.com/open-devops-agent/open-devops-agent
- Automated incident diagnosis/remediation across CI/CD, Kubernetes, cloud, GitOps and containers; includes approval gates and audit trails.
- Takeaway: broad autonomous DevOps agents already exist publicly. A narrower, deeper control-plane problem is more differentiated.

### babushkai/internal-developer-platform

- https://github.com/babushkai/internal-developer-platform
- A deeper reference IDP with FastAPI, queues/data stores, a control plane, and a separate Rust auth service.
- Takeaway: multi-service/backend depth matters; simply having FastAPI plus a UI is not enough to signal platform-engineering ability.

## Security problem used for differentiation

### GitHub Security Lab — GHSL-2025-038

- https://securitylab.github.com/advisories/GHSL-2025-038_github_branch-deploy_action/
- Documents a deployment approval TOCTOU window where the target can change after approval and before use.

### CodeQL — Untrusted Checkout TOCTOU

- https://codeql.github.com/codeql-query-help/actions/actions-untrusted-checkout-toctou-high/
- Recommends using immutable references such as commit SHA rather than mutable refs after a security/approval check.

This is the basis for EpochDeploy's core guarantee: approval is bound to an immutable identity and the execution boundary independently re-checks the observed target at use time.

## Demo research

### GitLab Duo Agent Platform demo examples

- https://gitlab.com/groups/gl-demo-ultimate-adess/duo-agent-platform
- GitLab's demo guidelines call for a walkthrough, setup runbook, metadata, validation steps, common pitfalls, and a repeatable scripted flow.

EpochDeploy follows that shape with:

- `docs/demo-setup-runbook.md`
- `docs/demo-script.md`
- `scripts/verify-local.sh`
- an interactive service-style dashboard rather than a README-only demo
- explicit verification boundaries in `docs/verification.md`

## Selected direction

**EpochDeploy — a TOCTOU-safe deployment control plane for AI-assisted DevOps.**

The differentiator is not “AI can deploy.” It is: **even if an AI agent or human initiates deployment, the exact code/artifact/config that was approved must be the exact target the execution boundary sees at use time.**
