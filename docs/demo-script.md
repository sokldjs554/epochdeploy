# 3-minute demo script

## Scene 1 — control plane, not chatbot
Open the dashboard. Point out that the primary object is an immutable deployment epoch, not a chat message.

## Scene 2 — exact approved release succeeds
1. Bootstrap the sample release.
2. Approve it as the approver role.
3. Execute it as operator.
4. Show `EXECUTED` and the equal expected/observed fingerprints.

## Scene 3 — stale approval is blocked
1. Bootstrap again and approve.
2. Change only the live artifact digest after approval.
3. Execute.
4. Show `DENIED_STALE`, the mismatching `artifact_digest`, and both fingerprints.

## Scene 4 — explain job-fit architecture
Show the architecture strip: FastAPI orchestration -> PostgreSQL workflow state -> Go executor; GitLab webhook enters on the left; file evidence is hashed and attached to the epoch; JWT separates operator/approver responsibilities.

## Interview line
“AI가 배포를 추천하는 기능보다, AI가 실행 단계까지 들어오는 순간 무엇을 승인했고 무엇이 실제 실행됐는지를 고정하는 문제가 더 어렵다고 봤습니다. 그래서 모델 성능이 아니라 실행 경계와 재현 가능한 증거를 백엔드 문제로 풀었습니다.”
