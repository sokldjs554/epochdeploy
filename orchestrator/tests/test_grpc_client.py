import hashlib
import hmac

from app.config import settings
from app.executor_client import (
    _GRPC_EXECUTE,
    _GRPC_OBSERVE,
    _grpc_metadata,
    _pb_context,
    _pb_identity,
)
from app.gen import executor_pb2


def identity():
    return {
        "project": "payments-api",
        "environment": "prod",
        "commit_sha": "8f375e7b64f6d20a3c1a1b2a6f9a1d9e2f7c1234",
        "artifact_digest": "sha256:" + "1" * 64,
        "config_hash": "cfg:" + "2" * 32,
    }


def test_grpc_metadata_signs_deterministic_protobuf(monkeypatch):
    monkeypatch.setattr("app.executor_client.time.time", lambda: 1_700_000_000)
    request = executor_pb2.ObserveRequest(identity=_pb_identity(identity()))
    metadata = dict(_grpc_metadata(_GRPC_OBSERVE, request))

    body = request.SerializeToString(deterministic=True)
    timestamp = "1700000000"
    expected = hmac.new(
        settings.executor_hmac_secret.encode(),
        timestamp.encode() + b"." + _GRPC_OBSERVE.encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()

    assert metadata["x-epochdeploy-timestamp"] == timestamp
    assert metadata["x-epochdeploy-signature"] == f"sha256={expected}"


def test_grpc_execution_context_preserves_capability_and_policy():
    context = {
        "epoch_id": "epoch-001",
        "actor_type": "ai_agent",
        "actor_id": "release-agent-01",
        "action": "deploy",
        "approved_fingerprint": "f" * 64,
        "capability_token": "token-value",
        "policy_decision": "ASK",
        "policy_rule": "ask-agent-production-write",
    }
    message = _pb_context(context)

    assert message.epoch_id == context["epoch_id"]
    assert message.actor_type == "ai_agent"
    assert message.actor_id == "release-agent-01"
    assert message.action == "deploy"
    assert message.approved_fingerprint == "f" * 64
    assert message.capability_token == "token-value"
    assert message.policy_decision == "ASK"
    assert message.policy_rule == "ask-agent-production-write"


def test_grpc_execute_signature_changes_when_scope_changes(monkeypatch):
    monkeypatch.setattr("app.executor_client.time.time", lambda: 1_700_000_000)
    first = executor_pb2.ExecuteRequest(
        expected=_pb_identity(identity()),
        context=_pb_context({
            "epoch_id": "epoch-001",
            "actor_type": "ai_agent",
            "actor_id": "release-agent-01",
            "action": "deploy",
            "approved_fingerprint": "f" * 64,
            "capability_token": "token-a",
            "policy_decision": "ASK",
            "policy_rule": "ask-agent-production-write",
        }),
    )
    second = executor_pb2.ExecuteRequest()
    second.CopyFrom(first)
    second.context.epoch_id = "epoch-002"

    assert dict(_grpc_metadata(_GRPC_EXECUTE, first))["x-epochdeploy-signature"] != dict(
        _grpc_metadata(_GRPC_EXECUTE, second)
    )["x-epochdeploy-signature"]
