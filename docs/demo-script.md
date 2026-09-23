# 3분 데모 스크립트

## 장면 1 — 챗봇이 아니라 실행 제어 플레인
대시보드를 엽니다. 이 프로젝트의 핵심 객체가 채팅 메시지가 아니라 **immutable deployment epoch**라는 점을 먼저 설명합니다.

## 장면 2 — 승인된 정확한 릴리스는 정상 실행
1. 샘플 릴리스를 생성합니다.
2. Approver 역할로 승인합니다.
3. scoped capability를 발급합니다.
4. Agent 실행을 수행합니다.
5. `EXECUTED`와 동일한 expected/observed fingerprint를 보여줍니다.

## 장면 3 — 승인 후 바뀐 대상은 차단
1. 새 epoch를 만들고 승인합니다.
2. capability를 발급합니다.
3. 승인 후 live artifact digest만 변경합니다.
4. Agent 실행을 수행합니다.
5. `DENIED_STALE`, 불일치한 `artifact_digest`, 두 fingerprint를 보여줍니다.

## 장면 4 — 공고와 연결된 아키텍처 설명
FastAPI orchestration → PostgreSQL workflow state → Go/Gin + gRPC executor 흐름을 보여줍니다. 왼쪽에서 GitLab webhook이 들어오고, evidence가 hash되어 epoch에 연결되며, JWT/RBAC가 operator/approver 역할을 분리한다는 점을 설명합니다.

## 면접에서 설명할 한 문장
“AI가 배포를 추천하는 기능보다, AI가 실행 단계까지 들어오는 순간 무엇을 승인했고 무엇이 실제 실행됐는지를 고정하는 문제가 더 어렵다고 봤습니다. 그래서 모델 성능이 아니라 실행 경계와 재현 가능한 증거를 백엔드 문제로 풀었습니다.”

## 3분 핵심 데모 이후 추가로 보여줄 부분

- **Policy Simulator**: 같은 정책 엔진으로 `ALLOW / ASK / DENY`를 dry-run 합니다.
- **Change Passport**: WHY / WHO / WHAT / APPROVAL / CAPABILITY / EVIDENCE / EXECUTION을 한 화면에서 확인합니다.
- **Evidence**: `build-provenance.txt`를 업로드하고 backend에서 기록한 SHA-256을 보여줍니다.
- **Execution Receipts**: 승인 fingerprint와 observed fingerprint, 최종 결과를 확인합니다.
- **Integrations**: Go implementation=`gin`, executor mode/transport=`grpc`, PostgreSQL backend=`postgresql`, gRPC Runtime=`ACTIVE`를 보여줍니다.
