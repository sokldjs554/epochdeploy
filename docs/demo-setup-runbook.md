# 데모 실행 가이드

이 가이드는 재현 가능한 데모만 보여주기 위한 절차입니다. 사전 검증이 실패하면 데모를 검증 완료 상태로 소개하지 않습니다.

## 1. 사전 검증

```bash
./scripts/verify-local.sh
```

예상 결과: Python 테스트, Go 테스트/vet, 정적 검사, 서비스 빌드, 반복 smoke flow가 모두 통과합니다.

## 2. 실행 경계 시작

외부 의존성이 없는 로컬 reference adapter:

```bash
make run-go
```

Health check: `GET http://127.0.0.1:9080/healthz`

운영형 경로는 Docker Compose를 사용합니다.

```bash
docker compose up --build
```

Compose에서는 FastAPI → Go/Gin 실행 요청이 gRPC 9090을 사용합니다.

## 3. 오케스트레이터 시작

Docker를 사용하지 않는 경우 저장소 루트에서 두 번째 터미널을 열고:

```bash
make run-api
```

브라우저에서 `http://127.0.0.1:8000/`을 엽니다.

## 4. 데모 순서

1. **Policy Simulator**에서 staging deploy=`ALLOW`, production deploy=`ASK`, destructive action=`DENY`를 확인합니다.
2. 새 epoch를 만들고 production deploy를 사람 승인합니다.
3. scoped capability를 발급합니다.
4. 정상 실행 후 `EXECUTED`를 확인합니다.
5. 새 epoch를 만들고 승인·capability 발급 후 `artifact_digest`만 바꿉니다.
6. 실행해 `DENIED_STALE`과 필드 단위 diff를 확인합니다.
7. Change Passport에서 policy·approval·capability·execution timeline을 확인합니다.
8. 같은 idempotency key 재시도 시 두 번째 실행이 아니라 동일 receipt가 반환되는지 확인합니다.

## 5. 설명할 포인트

- AI Agent는 배포를 제안하거나 시작할 수 있지만 실행 시점의 승인 identity를 다시 정의할 수 없습니다.
- 승인은 commit SHA, image digest, config hash, project, environment에 묶입니다.
- Agent 실행 권한은 짧은 수명의 scoped capability로 제한됩니다.
- Go/Gin 실행 경계는 deterministic하고 fail-closed이며 최종 권한 판단에 LLM을 사용하지 않습니다.
- gRPC runtime, PostgreSQL, Docker Compose는 실제 원격 CI에서 실행 검증했습니다.
- 실제 GitLab Runner와 Kubernetes는 아직 실행했다고 주장하지 않습니다.
