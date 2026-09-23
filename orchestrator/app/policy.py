from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyDecision:
    decision: str
    rule_id: str
    reason: str
    required_controls: tuple[str, ...]


def evaluate_policy(*, actor_type: str, action: str, environment: str) -> PolicyDecision:
    actor = actor_type.strip().lower()
    act = action.strip().lower()
    env = environment.strip().lower()

    if act in {"delete", "destroy", "drop", "purge"}:
        return PolicyDecision(
            decision="DENY",
            rule_id="deny-destructive-action",
            reason="파괴적 작업은 자율 Agent에게 위임할 수 없습니다.",
            required_controls=("manual-operator",),
        )

    if act in {"read", "inspect", "status"}:
        return PolicyDecision(
            decision="ALLOW",
            rule_id="allow-readonly",
            reason="읽기 전용 작업은 배포 상태를 변경하지 않습니다.",
            required_controls=(),
        )

    if actor == "ai_agent" and env in {"prod", "production"} and act in {"deploy", "write", "promote"}:
        return PolicyDecision(
            decision="ASK",
            rule_id="ask-agent-production-write",
            reason="AI Agent의 운영 환경 쓰기 작업에는 명시적인 사람 승인이 필요합니다.",
            required_controls=("verified-pipeline", "human-approval", "scoped-capability"),
        )

    if actor == "ai_agent" and env in {"dev", "development", "staging", "stage"} and act in {"deploy", "write", "promote"}:
        return PolicyDecision(
            decision="ALLOW",
            rule_id="allow-agent-nonprod-write",
            reason="비운영 환경의 Agent 쓰기 작업은 immutable release와 scoped capability가 있으면 허용됩니다.",
            required_controls=("verified-pipeline", "scoped-capability"),
        )

    return PolicyDecision(
        decision="ASK",
        rule_id="ask-default-mutating-action",
        reason="알 수 없거나 상태를 변경하는 작업은 사람 검토가 필요합니다.",
        required_controls=("human-approval",),
    )
