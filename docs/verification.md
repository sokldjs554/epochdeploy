# 검증 기록

검증 기준일: 2026-09-23 (Asia/Seoul)

이 문서는 **실제로 실행한 검증만** 기록합니다. 코드나 설정 파일이 존재한다는 이유만으로 실행 검증으로 간주하지 않습니다.

## 1. 로컬 전체 검증

gRPC runtime 전환 전 로컬 HTTP reference 경로에서 `scripts/verify-local.sh`를 **3회 연속** 성공시켰습니다.

각 회차에서 다음을 실행했습니다.

- `python -m compileall -q orchestrator`
- `node --check orchestrator/app/static/app.js`
- `gofmt -l executor` 결과가 비어 있는지 확인
- `go vet ./...`
- `go test -race -count=1 ./...`
- 당시 Python regression suite 전체 통과
- `pyproject.toml`로 wheel을 만들고 격리된 target에 실제 설치
- 설치된 package에서 `app.main` import 및 static asset 포함 여부 확인
- 새로운 Go executor binary build
- 검증용 포트가 비어 있는지 확인해 stale process가 health check를 대신 통과하지 못하도록 차단
- Go와 FastAPI를 별도 process로 실행
- 두 `/healthz`와 방금 띄운 PID 생존 확인
- unsigned executor request가 **HTTP 401**인지 확인
- dashboard HTML/JavaScript 실제 fetch + JavaScript syntax 확인
- 한 회차마다 smoke flow 3회 실행

Smoke flow는 다음 두 경로를 확인합니다.

1. 승인 identity와 live target이 같음 → `EXECUTED`
2. 승인 후 artifact digest 변경 → `DENIED_STALE`

## 2. Docker / PostgreSQL 원격 검증

GitHub-hosted `Remote Verification`에서 실제 Docker Compose와 PostgreSQL 경로를 실행했습니다.

검증 내용:

- Docker image build/start
- PostgreSQL 16 readiness
- 실제 PostgreSQL database에 `deployment_epochs` table 존재 확인
- FastAPI + Go/Gin 별도 서비스 기동
- 반복 smoke 3회
- clean teardown

이 검증은 실제 GitLab Runner 실행을 대신한다고 주장하지 않습니다. GitLab CI 계약은 별도로 `.gitlab-ci.yml`에 유지합니다.

## 3. 브라우저 E2E

`scripts/browser-e2e.py`는 Chromium에서 실제 UI JavaScript와 backend API를 사용합니다.

검증 흐름:

1. Release Control에서 epoch 생성
2. production policy에 필요한 승인 수행
3. scoped capability 발급
4. 정상 실행 → `EXECUTED / MATCH`
5. **Policy Simulator**에서 `ALLOW / ASK / DENY` 확인
6. **Change Passport**에서 WHY / WHO / policy / approval / capability / execution 확인
7. **Evidence**에서 실제 multipart file upload와 SHA-256 ledger 확인
8. **Execution Receipts**에서 저장된 receipt 확인
9. **Integrations**에서 실제 executor/database/gRPC runtime 확인
10. 새 epoch에서 artifact drift 주입
11. 실행 → `DENIED_STALE / BLOCKED`
12. receipt와 Change Passport에서 차단 기록 확인

브라우저 검증에서는 console error, page error, failed request, 예상하지 않은 HTTP 4xx/5xx를 확인합니다.

## 4. Agent Governance / Change Passport

Agent-originated change는 다음 정보를 보존합니다.

- 변경 이유: `WHY`
- Agent actor: `WHO`
- human requester
- project / environment / action
- immutable release fingerprint
- GitLab pipeline evidence
- human approval
- scoped capability
- evidence attachment
- terminal execution result

검증된 timeline 예시:

```text
EPOCH_CREATED
→ CHANGE_REQUESTED
→ PIPELINE_VERIFIED
→ POLICY_EVALUATED
→ APPROVED
→ CAPABILITY_ISSUED
→ EVIDENCE_ATTACHED
→ EXECUTED
```

차단 경로에서는 마지막이 `DENIED_STALE`로 기록됩니다.

## 5. Scoped Capability 검증

AI Agent 실행 권한은 다음 scope에 묶입니다.

```text
epoch_id
actor_type
actor_id
project
environment
action
approved fingerprint
expiry
```

검증 항목:

- 사람 승인이 필요한 policy에서 승인 전 capability 발급 차단
- AI Agent-originated change에만 capability 발급
- raw token은 DB/Passport에 저장하지 않고 grant metadata만 저장
- tampered token 차단
- expired token 차단
- 다른 epoch로 token 재사용 차단
- FastAPI에서 grant 상태 확인
- Go/Gin executor에서 signature·expiry·scope 독립 재검증

검증 과정에서 demo capability secret 길이가 SHA-256 HMAC 권고보다 짧은 문제를 발견했고, 기본값/example/Compose 값을 32바이트 이상으로 수정한 뒤 다시 검증했습니다.

## 6. Policy Dry-run / 실제 실행 gate 검증

동일한 deterministic policy engine을 simulation과 실제 capability 발급에 사용합니다.

| 시나리오 | 결정 | 의미 |
|---|---|---|
| AI Agent + staging deploy | `ALLOW` | verified pipeline + scoped capability로 진행 가능 |
| AI Agent + production deploy | `ASK` | 명시적 사람 승인 필요 |
| destructive action 예: production delete | `DENY` | 사람 승인이 있어도 capability 발급 금지 |

실제 capability 발급 시마다 `POLICY_EVALUATED`가 Change Passport에 기록되며 decision, rule id, required controls를 저장합니다.

Dry-run API는 배포 상태에 side effect를 만들지 않습니다.

## 7. Gin 운영형 runtime 검증

운영형 Compose executor는 Gin adapter를 사용합니다.

검증 항목:

- `go mod tidy` 후 module lock diff 0
- `go vet`
- `go test -race -count=1 ./...`
- Docker image build/start
- PostgreSQL과 함께 서비스 기동
- Chromium E2E에서 `implementation=gin` 확인

Gin은 README에만 적어둔 키워드가 아니라 실제 Docker Compose 실행 경계입니다.

## 8. 실제 gRPC transport 검증

Stage-4 최종 Remote Verification은 **run #57**, head `99a4a001e3609cc494c31f9fdf92146e2269ed10`에서 성공했습니다.

### gRPC codegen

- `proto/executor.proto`에서 Go/Python binding 재생성
- `go mod tidy`
- checked-in generated code와 module lock에 대해 **diff 0**
- generated binding 5개는 CI artifact 원본과 Git blob SHA까지 대조

### Python / Go 테스트

최종 Python regression suite:

**47 passed**

추가 gRPC coverage:

- unsigned gRPC metadata 거부
- exact Observe/Execute → `EXECUTED`
- stale artifact → `DENIED_STALE`
- valid scoped capability 실행
- cross-epoch capability 거부
- Python deterministic protobuf HMAC metadata
- execution context에서 capability/policy mapping
- scope가 달라지면 signature가 달라지는지 확인

Go/Gin/gRPC server는 `go vet`과 `go test -race`를 통과했습니다.

### 실제 Compose gRPC 경로

Compose에서:

- FastAPI
- PostgreSQL 16
- Gin HTTP adapter :9080
- **gRPC executor :9090**

을 기동했습니다.

FastAPI의 Observe/Execute는 `executor_mode=grpc`로 **실제 gRPC 9090**을 사용합니다.

요청 인증:

```text
HMAC-SHA256(
  timestamp + "." +
  RPC method + "." +
  deterministic protobuf bytes
)
```

Go unary interceptor가 같은 protobuf bytes를 다시 직렬화해 metadata signature와 30초 clock-skew를 확인합니다.

### 최종 Compose / 브라우저 검증 결과

- Docker build/start: 성공
- PostgreSQL schema 확인: 성공
- two-service smoke: **3/3 성공**
- Chromium E2E: 성공
- screenshot artifact upload: 성공
- teardown: 성공

최종 Integrations 화면에서 실제로 확인한 값:

```text
Go Executor
  mode           = grpc
  implementation = gin
  transport      = grpc

Database
  backend = postgresql

gRPC Runtime
  status = ACTIVE
```

최종 screenshot artifact:

- 이름: `epochdeploy-browser-e2e`
- artifact id: `10711056411`
- SHA-256: `232959fb8cfeab5910f25808b6ea415c1445cbe0bd6a495a42a9599380ef5e83`

## 9. 검증 과정에서 실제로 발견해 수정한 문제

완료 여부를 코드 존재만으로 판단하지 않았기 때문에 다음 문제를 실제로 발견했습니다.

- SQLite teardown이 삭제된 DB 파일의 pooled handle을 재사용하던 문제
- FastAPI lifespan deprecation 처리
- 초기 검증 script가 잘못된 Go directory에서 build하던 문제
- 오래된 9080 process가 새 binary의 실패를 가릴 수 있던 문제
- Python과 Go fingerprint canonicalization 불일치
- epoch 생성 API가 client의 `pipeline_status=success`를 신뢰할 수 있던 문제
- FastAPI가 expected와 observed를 모두 Go에 전달하던 약한 신뢰 경계
- executor traffic이 처음에는 인증되지 않았던 문제
- UI diff rendering의 `innerHTML` 사용
- PostgreSQL schema와 ORM의 pipeline default 불일치
- Chromium headless / sandbox 정책 문제
- decorative sidebar menu 문제
- capability secret 길이 문제
- JavaScript replacement-string의 `$` semantics로 event binding이 깨진 문제
- gRPC codegen script executable permission 문제
- CI bot generated binding push의 non-fast-forward 문제
- 최신 grpc-go가 Go 1.25를 요구해 Go 1.23 프로젝트와 충돌한 문제 → **grpc-go v1.75.1 pin**

## 10. 최종 merge 무결성

Stage-4 PR #8 merge 후 변경된 **31개 파일 전부**를 merge 전 branch와 `main`의 Git blob SHA로 대조했습니다.

결과:

**31 / 31 일치**

더 나아가 merge 전 branch와 merge 후 main의 전체 Git tree SHA가 동일했습니다.

최종 main commit:

`c84cce80016c62f6cb88849e68e6fb1459c2885f`

## 11. 현재 의도적으로 남겨둔 검증 범위

다음 항목은 과장하지 않고 아직 별도 확장 범위로 남깁니다.

- PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` 기반 query-plan tuning
- 실제 multi-writer DB lock contention test
- 실제 GitLab Runner에서 `.gitlab-ci.yml` 실행
- Kubernetes 실제 배포

이 항목들은 현재 지원용 프로젝트의 핵심 실행 경계가 미완성이라는 뜻이 아니라, 운영 확장 시 추가로 검증할 범위입니다.
