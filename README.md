# EpochDeploy

**AI 기반 DevOps를 위한 TOCTOU 안전 배포 제어 플레인**

EpochDeploy는 Agentic DevOps와 CI/CD에서 발생할 수 있는 미묘한 실패를 막습니다. 사람이나 AI 워크플로가 특정 리비전을 승인했더라도, 실행 전 mutable branch·image tag·설정·배포 대상이 바뀔 수 있습니다. EpochDeploy는 "latest"를 신뢰하지 않고 승인 대상을 immutable deployment identity로 고정한 뒤, 실행 직전에 동일성을 다시 검증합니다.

## 무엇이 다른가

이 프로젝트는 DevOps 챗봇, 로그 요약기, 범용 Internal Developer Platform이 아닙니다. 핵심 데모는 의도적으로 공격적인 시나리오를 다룹니다.

- 정확한 commit + artifact digest + config hash를 승인합니다.
- 승인 이후 그중 하나를 변경합니다.
- Go 실행 경계가 stale approval을 필드 단위 diff와 함께 차단하는지 확인합니다.
- 감사 가능한 execution receipt를 저장합니다.
- 사람과 AI Agent의 **왜 / 누가 / 승인 / capability / evidence / 실행**을 append-only Change Passport로 연결합니다.
- AI Agent가 승인된 epoch·project·environment·action·actor·fingerprint 안에서만 실행하도록 짧은 수명의 **scoped capability**를 발급합니다.
- 동일한 결정적 **ALLOW / ASK / DENY 정책 엔진**을 dry-run과 실제 capability 발급에 함께 사용합니다.

## 아키텍처

```text
GitLab Pipeline Hook ─┐
Evidence Upload ──────┼──> FastAPI Orchestrator ──> PostgreSQL
JWT Operator/Approver ┘          │                    │
                                 │ gRPC 실행 요청      ├─ approvals
                                 v                    ├─ receipts
                       Go/Gin Execution Boundary      └─ outbox
                                 │
                                 └─ 실행 직전 identity 재검증
                                    EXECUTED / DENIED_STALE
```

### 역할 분리

- **FastAPI** — 오케스트레이션, GitLab webhook 수신, JWT/RBAC, evidence 업로드, 관계형 워크플로 상태, receipt API.
- **Go/Gin + gRPC** — 운영형 실행 경계. Docker Compose에서는 9090의 signed gRPC로 Observe/Execute를 처리하고, 9080의 Gin HTTP는 health/호환 adapter로 남깁니다. 두 transport는 같은 target store, capability verifier, TOCTOU core를 공유합니다.
- **PostgreSQL** — epoch, Agent change request, append-only passport event, approval, live target observation, evidence, receipt, outbox.
- **GitLab CI** — 검증 stage와 Docker Compose 통합 검증 계약.
- **gRPC runtime** — `proto/executor.proto`에서 Go/Python binding을 생성하고 CI에서 drift를 검증합니다. FastAPI는 deterministic protobuf 요청을 HMAC metadata로 서명하고, Go executor가 Observe/Execute 전에 독립 검증합니다.

## 데모 계정

로컬 데모 전용 계정입니다.

| 사용자 | 비밀번호 | 역할 |
|---|---|---|
| `operator` | `operator-demo` | 생성/실행 |
| `approver` | `approver-demo` | 승인 |
| `admin` | `admin-demo` | 데모/초기화/관리 |

데모 외 환경에서는 이 계정을 재사용하지 마세요.

## Docker 없이 로컬 실행

```bash
make test
make run-go
# 다른 터미널
make run-api
```

브라우저에서 `http://localhost:8000`을 엽니다.

## 운영형 구성 실행

```bash
docker compose up --build
```

이 구성에서는 오케스트레이터가 PostgreSQL을 사용하고 별도 **Go/Gin executor**와 **signed gRPC**로 통신합니다. gRPC는 내부 9090, Gin HTTP는 health/호환 용도로 내부 9080을 사용합니다. Observe/Execute protobuf 요청은 `timestamp + RPC method + deterministic protobuf bytes`를 HMAC-SHA256으로 서명합니다.

## 테스트 전략

- deterministic fingerprint 단위 테스트
- 인증/JWT/RBAC 테스트
- immutable ref 검증
- GitLab webhook token + commit SHA binding + 중복 이벤트 idempotency
- evidence upload hash + 경로 정규화
- 정상 실행 경로
- commit/artifact/config drift fail-closed 테스트
- execution receipt idempotency
- Go core/server 테스트: HTTP HMAC, gRPC metadata 인증, cross-runtime fingerprint, capability scope, stale target
- HTTP smoke script: `scripts/smoke.sh`
- Chromium E2E: Release Control, **Policy Simulator**, Change Passport, Evidence, Execution Receipts, Integrations
- GitLab Docker Compose 통합 검증 계약

## 검증 범위

로컬 검증은 Python 테스트, Go race/vet, 패키지 설치, 두 서비스 smoke, stale approval 반복 검증을 수행합니다. Chromium E2E는 실제 UI를 클릭하며 evidence 업로드, receipt 조회, integration 상태, `EXECUTED`와 `DENIED_STALE` 흐름을 확인합니다.

GitHub-hosted 원격 검증에서는 Docker image를 빌드하고 **PostgreSQL 16**과 함께 Compose stack을 기동한 뒤, 실제 gRPC 경로와 브라우저 E2E를 반복 검증했습니다.

`.gitlab-ci.yml`은 지원 포지션에 맞춘 GitLab CI 계약으로 유지하고 있습니다. 이 환경에서는 실제 GitLab Runner를 연결해 실행했다고 주장하지 않습니다. Kubernetes도 아직 실행 검증 대상으로 남겨두었습니다. 정확한 검증 증거와 미검증 범위는 `docs/verification.md`를 확인하세요.

추가 문서:
- `docs/architecture.md`
- `docs/demo-script.md`
- `docs/demo-setup-runbook.md`
- `docs/jd-mapping.md`
- `docs/research-notes.md`
- `docs/verification.md`
