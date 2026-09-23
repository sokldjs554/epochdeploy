# 사전 조사 기록

조사일: 2026-09-21

범위: 아래 항목은 공고와 기술적으로 겹치는 공개 오픈소스/레퍼런스 프로젝트입니다. **실제 CollabOps 지원자 프로젝트라고 확인된 것은 아닙니다.** 흔한 포트폴리오 주제를 피하기 위한 비교 조사였습니다.

## CollabOps 제품 방향

- 공식 제품: https://collabops.ai/
- planning/issue → code review → CI/CD → test/security → deployment를 연결하는 제품 방향을 확인했습니다.
- 따라서 일반 CRUD 백엔드나 분리된 챗봇보다는 workflow orchestration과 실제 execution boundary를 보여주는 쪽이 공고와 더 직접적으로 연결됩니다.

## 검토한 유사 공개 프로젝트

### Merkuryo/internal-developer-platform
- https://github.com/Merkuryo/internal-developer-platform
- FastAPI + PostgreSQL + Redis
- Service catalog, golden-path template, mock deployment, dark dashboard, Docker Compose, OpenAPI
- 판단: 서비스 카탈로그 + “Deploy” 버튼형 IDP는 이미 완성도 높은 공개 예제가 있어 그대로 따라가면 흔합니다.

### ideaweaver-ai/devops-open-agent
- https://github.com/ideaweaver-ai/devops-open-agent
- Kubernetes/AWS/security/performance 조사, integration, 제품형 UI를 포함한 AI DevOps 프로젝트
- 판단: “LLM이 로그를 읽고 원인과 명령을 추천”하는 구조는 이미 흔합니다. EpochDeploy의 핵심 장면은 LLM 진단보다 deterministic systems guarantee가 되어야 합니다.

### open-devops-agent/open-devops-agent
- https://github.com/open-devops-agent/open-devops-agent
- CI/CD, Kubernetes, cloud, GitOps, container를 아우르는 자동 incident diagnosis/remediation
- approval gate와 audit trail 포함
- 판단: 넓은 autonomous DevOps Agent는 이미 공개 구현이 많으므로 더 좁고 깊은 실행 제어 문제를 선택했습니다.

### babushkai/internal-developer-platform
- https://github.com/babushkai/internal-developer-platform
- FastAPI, queue/data store, control plane, 별도 Rust auth service를 포함하는 깊은 IDP 예제
- 판단: FastAPI + UI만으로는 Platform Engineering 역량을 충분히 보여주기 어렵고, 명확한 service boundary가 필요합니다.

## 차별화에 사용한 보안 문제

### GitHub Security Lab — GHSL-2025-038
- https://securitylab.github.com/advisories/GHSL-2025-038_github_branch-deploy_action/
- 승인 이후 실제 사용 전에 target이 바뀔 수 있는 deployment approval TOCTOU window를 다룹니다.

### CodeQL — Untrusted Checkout TOCTOU
- https://codeql.github.com/codeql-query-help/actions/actions-untrusted-checkout-toctou-high/
- security/approval check 이후 mutable ref가 아니라 commit SHA 같은 immutable reference 사용을 권고합니다.

EpochDeploy의 핵심 보장은 여기서 출발합니다.

> 승인은 immutable identity에 묶고, execution boundary가 실제 사용 시점에 observed target을 다시 독립 검증한다.

## 데모 방식 조사

### GitLab Duo Agent Platform demo 예시
- https://gitlab.com/groups/gl-demo-ultimate-adess/duo-agent-platform
- walkthrough, setup runbook, metadata, validation step, common pitfall, 반복 가능한 scripted flow를 요구합니다.

EpochDeploy도 다음 구조를 따릅니다.

- `docs/demo-setup-runbook.md`
- `docs/demo-script.md`
- `scripts/verify-local.sh`
- README-only가 아닌 실제 서비스형 dashboard
- `docs/verification.md`의 명확한 검증 경계

## 최종 방향

**EpochDeploy — AI 기반 DevOps를 위한 TOCTOU-safe deployment control plane**

차별점은 “AI가 배포할 수 있다”가 아닙니다.

> **사람이나 AI Agent가 배포를 시작하더라도, 승인된 code/artifact/config와 실행 경계가 실제로 보는 대상이 끝까지 같음을 보장한다.**

이 위에 Agent Governance, Policy Dry-run, Scoped Capability, Change Passport, 실제 signed gRPC runtime을 결합했습니다.
