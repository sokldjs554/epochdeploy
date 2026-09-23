# 아키텍처

EpochDeploy는 하나의 좁지만 중요한 시스템 문제를 다룹니다.

> **승인한 배포 대상과 실제 실행되는 대상이 달라질 수 있다.**

## 요청 흐름

1. GitLab pipeline evidence가 FastAPI 오케스트레이터로 들어옵니다.
2. 오케스트레이터는 project, environment, commit SHA, artifact digest, config hash 다섯 값을 묶어 immutable deployment epoch를 만듭니다.
3. AI Agent가 시작한 작업은 1:1 Change Request에 연결됩니다. 여기에는 **왜 이 변경이 필요한지**, 어떤 AI actor인지, 어떤 사람이 요청했는지, 어떤 action을 요청했는지가 기록됩니다.
4. append-only Change Passport가 GitLab 검증, 사람 승인, evidence 첨부, 최종 실행 이벤트를 순서대로 기록합니다.
5. 별도 Approver가 epoch fingerprint에 승인을 묶습니다.
6. 결정적 정책 엔진이 권한 발급 전에 agent action + environment를 평가합니다. 비운영 배포는 `ALLOW`, 운영 배포는 `ASK`, 파괴적 작업은 `DENY`입니다.
7. 같은 정책 엔진이 side-effect 없는 dry-run API와 실제 capability gate에 함께 사용됩니다. `ASK`는 사람 승인이 필요하고, `ALLOW`는 검증된 pipeline + scoped capability로 진행할 수 있으며, `DENY`는 capability를 받을 수 없습니다.
8. AI Agent가 시작한 변경에는 epoch, actor, project, environment, action, approved fingerprint, expiry에 묶인 HS256 capability가 발급됩니다. raw token은 저장하지 않고 grant metadata만 보관합니다.
9. FastAPI가 grant를 확인한 뒤 전달하고, Go/Gin executor가 capability signature·expiry·scope·expected release fingerprint를 다시 독립 검증합니다.
10. Go executor는 인증된 내부 경계 안에서 최신 live target observation을 유지합니다. 실행 요청은 caller가 만든 observed 값이 아니라 승인된 expected identity만 전달합니다.
11. 실행 직전 observed fingerprint를 다시 계산해 승인 identity와 비교합니다. 완전히 같으면 `EXECUTED`, 다르면 필드 단위 diff와 함께 `DENIED_STALE`입니다.
12. 오케스트레이터는 execution receipt와 transactional outbox event를 같은 DB transaction에 저장합니다.

## Python + Go를 나눈 이유

- **Python/FastAPI**: 오케스트레이션, 인증, GitLab webhook, evidence ingestion, 관계형 워크플로 상태, UI API.
- **Go/Gin**: 운영형 실행 경계. Gin HTTP adapter와 gRPC server가 같은 deterministic core와 live-target store를 공유합니다. stdlib adapter는 외부 의존성이 없는 로컬 검증용으로 유지합니다.

`proto/executor.proto`에서 Go/Python binding을 생성하고, 운영형 Compose 경로는 Health/Observe/Execute에 gRPC를 사용합니다. generated binding은 CI에서 재생성한 뒤 diff가 0인지 검증합니다.

## PostgreSQL 모델

운영형 `docker-compose.yml`은 PostgreSQL을 사용합니다. SQLite는 외부 의존성 없는 개발/테스트 모드에서만 사용합니다. 주요 read path에는 project/environment 최신순, pipeline 조회, state, epoch별 receipt/time, outbox publication state 인덱스를 둡니다.

## 서비스 간 신뢰 경계

검증된 운영형 transport는 gRPC입니다. FastAPI는 Observe/Execute protobuf를 deterministic하게 직렬화하고 `timestamp + RPC method + protobuf bytes`를 HMAC-SHA256 metadata로 서명합니다. Go unary interceptor가 같은 방식으로 요청을 직렬화해 서명을 다시 확인하고, 30초 clock-skew를 벗어난 metadata도 거부합니다.

그 다음 capability scope를 검증하고, 마지막으로 공통 live-target/TOCTOU 검증을 수행합니다. Gin HTTP는 내부 health/호환 adapter이며 Compose에서는 executor 포트를 host에 공개하지 않습니다.
