# CollabOps 백엔드 Platform 엔지니어 공고 매핑

| 공고 요구사항 | EpochDeploy에서 보여주는 근거 |
|---|---|
| FastAPI 오케스트레이션 | epoch lifecycle, 인증, GitLab webhook, evidence upload, execution coordination |
| Python + Go 역할 분리 | Python이 workflow state를 관리하고 Go가 최종 deterministic execution boundary를 담당. 운영형 adapter는 Gin |
| 서비스 간 통신 | 운영형 Compose에서 FastAPI↔Go가 signed gRPC 사용. deterministic protobuf bytes를 HMAC metadata로 인증하고 Gin HTTP는 호환 adapter로 유지 |
| PostgreSQL | release/approval/capability/receipt/passport/outbox 모델과 production SQL/index |
| GitLab CI/CD | Pipeline Hook 수신, SHA binding, duplicate webhook idempotency, `.gitlab-ci.yml` |
| JWT 인증 | signed JWT + operator/approver/admin RBAC |
| 이미지/파일 업로드 | multipart 크기 제한, filename sanitization, SHA-256 evidence hash |
| 안정성 | idempotent receipt, terminal state machine, fail-closed stale check, outbox |
| AI DevOps 실행 거버넌스 | Agent change provenance, ALLOW/ASK/DENY dry-run, production approval gate, short-lived scoped capability, Gin-side capability verification, append-only Change Passport |
| 성능/확장성 | 작은 stateless Go execution service, index 설계, local concurrency benchmark |
| 테스트/문서화 | Python API/client 테스트, stdlib Go core, Gin+gRPC bufconn 테스트, codegen drift 검증, two-service smoke, Chromium E2E, demo runbook, verification log |
| Kubernetes 선택사항 | Docker/Compose 경로는 검증됨. Kubernetes는 실행 검증 전까지 과장하지 않음 |
