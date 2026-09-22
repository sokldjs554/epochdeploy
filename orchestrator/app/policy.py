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
            reason="Destructive actions are not delegable to autonomous agents.",
            required_controls=("manual-operator",),
        )

    if act in {"read", "inspect", "status"}:
        return PolicyDecision(
            decision="ALLOW",
            rule_id="allow-readonly",
            reason="Read-only operations do not mutate deployment state.",
            required_controls=(),
        )

    if actor == "ai_agent" and env in {"prod", "production"} and act in {"deploy", "write", "promote"}:
        return PolicyDecision(
            decision="ASK",
            rule_id="ask-agent-production-write",
            reason="AI-agent production writes require explicit human approval.",
            required_controls=("verified-pipeline", "human-approval", "scoped-capability"),
        )

    if actor == "ai_agent" and env in {"dev", "development", "staging", "stage"} and act in {"deploy", "write", "promote"}:
        return PolicyDecision(
            decision="ALLOW",
            rule_id="allow-agent-nonprod-write",
            reason="Non-production agent writes are allowed with an immutable release and scoped capability.",
            required_controls=("verified-pipeline", "scoped-capability"),
        )

    return PolicyDecision(
        decision="ASK",
        rule_id="ask-default-mutating-action",
        reason="Unknown or mutating actions require human review.",
        required_controls=("human-approval",),
    )
