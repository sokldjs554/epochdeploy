from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

import grpc
import httpx

from .capability import CapabilityError, CapabilityScope, verify_capability
from .config import settings
from .fingerprint import diff_identity, fingerprint
from .gen import executor_pb2, executor_pb2_grpc

_GRPC_HEALTH = "/epochdeploy.executor.v1.Executor/Health"
_GRPC_OBSERVE = "/epochdeploy.executor.v1.Executor/Observe"
_GRPC_EXECUTE = "/epochdeploy.executor.v1.Executor/Execute"


class ExecutorBoundaryError(RuntimeError):
    pass


@dataclass
class ExecutorResult:
    outcome: str
    observed_fingerprint: str
    reason: str
    latency_ms: int
    differences: list[dict[str, str]]


def _grpc_metadata(method: str, request) -> tuple[tuple[str, str], ...]:
    body = request.SerializeToString(deterministic=True)
    timestamp = str(int(time.time()))
    mac = hmac.new(
        settings.executor_hmac_secret.encode("utf-8"),
        timestamp.encode("ascii") + b"." + method.encode("utf-8") + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return (
        ("x-epochdeploy-timestamp", timestamp),
        ("x-epochdeploy-signature", f"sha256={mac}"),
    )


def _pb_identity(identity: dict[str, str]) -> executor_pb2.DeploymentIdentity:
    return executor_pb2.DeploymentIdentity(
        project=identity["project"],
        environment=identity["environment"],
        commit_sha=identity["commit_sha"],
        artifact_digest=identity["artifact_digest"],
        config_hash=identity["config_hash"],
    )


def _pb_context(context: dict | None):
    if not context:
        return None
    return executor_pb2.ExecutionContext(
        epoch_id=context.get("epoch_id", ""),
        actor_type=context.get("actor_type", ""),
        actor_id=context.get("actor_id", ""),
        action=context.get("action", ""),
        approved_fingerprint=context.get("approved_fingerprint", ""),
        capability_token=context.get("capability_token", ""),
        policy_decision=context.get("policy_decision", ""),
        policy_rule=context.get("policy_rule", ""),
    )


class LocalExecutorClient:
    def observe(self, identity: dict[str, str]) -> None:
        return None

    def execute(self, expected: dict[str, str], observed: dict[str, str], context: dict | None = None) -> ExecutorResult:
        started = time.perf_counter()
        if context and context.get("actor_type") == "ai_agent":
            scope = CapabilityScope(
                epoch_id=context["epoch_id"],
                actor_type=context["actor_type"],
                actor_id=context["actor_id"],
                project=expected["project"],
                environment=expected["environment"],
                action=context["action"],
                fingerprint=context["approved_fingerprint"],
            )
            try:
                verify_capability(context["capability_token"], scope)
            except CapabilityError as exc:
                raise ExecutorBoundaryError(str(exc)) from exc
        expected_fp = fingerprint(expected)
        observed_fp = fingerprint(observed)
        diffs = diff_identity(expected, observed)
        if expected_fp != observed_fp:
            outcome = "DENIED_STALE"
            reason = "execution target changed after approval: " + ", ".join(d["field"] for d in diffs)
        else:
            outcome = "EXECUTED"
            reason = "approved deployment identity matches live target"
        return ExecutorResult(outcome, observed_fp, reason, int((time.perf_counter()-started)*1000), diffs)


class HTTPExecutorClient:
    def _signed_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        timestamp = str(int(time.time()))
        mac = hmac.new(
            settings.executor_hmac_secret.encode("utf-8"),
            timestamp.encode("ascii") + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-EpochDeploy-Timestamp": timestamp,
            "X-EpochDeploy-Signature": f"sha256={mac}",
        }
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.post(f"{settings.executor_url.rstrip('/')}{path}", content=body, headers=headers)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise ExecutorBoundaryError("executor boundary request failed") from exc

    def observe(self, identity: dict[str, str]) -> None:
        self._signed_post("/v1/targets/observe", {"identity": identity})

    def execute(self, expected: dict[str, str], observed: dict[str, str], context: dict | None = None) -> ExecutorResult:
        del observed
        started = time.perf_counter()
        payload: dict[str, Any] = {"expected": expected}
        if context:
            payload["context"] = context
        data = self._signed_post("/v1/execute", payload)
        return ExecutorResult(
            outcome=data["outcome"],
            observed_fingerprint=data["observed_fingerprint"],
            reason=data["reason"],
            latency_ms=int((time.perf_counter()-started)*1000),
            differences=data.get("differences", []),
        )


class GRPCExecutorClient:
    def observe(self, identity: dict[str, str]) -> None:
        request = executor_pb2.ObserveRequest(identity=_pb_identity(identity))
        try:
            with grpc.insecure_channel(settings.executor_grpc_target) as channel:
                stub = executor_pb2_grpc.ExecutorStub(channel)
                stub.Observe(
                    request,
                    timeout=5.0,
                    metadata=_grpc_metadata(_GRPC_OBSERVE, request),
                )
        except grpc.RpcError as exc:
            raise ExecutorBoundaryError(
                f"gRPC observe failed: {exc.code().name}: {exc.details()}"
            ) from exc

    def execute(self, expected: dict[str, str], observed: dict[str, str], context: dict | None = None) -> ExecutorResult:
        del observed
        request = executor_pb2.ExecuteRequest(
            expected=_pb_identity(expected),
            context=_pb_context(context),
        )
        started = time.perf_counter()
        try:
            with grpc.insecure_channel(settings.executor_grpc_target) as channel:
                stub = executor_pb2_grpc.ExecutorStub(channel)
                response = stub.Execute(
                    request,
                    timeout=5.0,
                    metadata=_grpc_metadata(_GRPC_EXECUTE, request),
                )
        except grpc.RpcError as exc:
            raise ExecutorBoundaryError(
                f"gRPC execute failed: {exc.code().name}: {exc.details()}"
            ) from exc
        return ExecutorResult(
            outcome=response.outcome,
            observed_fingerprint=response.observed_fingerprint,
            reason=response.reason,
            latency_ms=int((time.perf_counter() - started) * 1000),
            differences=[
                {
                    "field": item.field,
                    "expected": item.expected,
                    "observed": item.observed,
                }
                for item in response.differences
            ],
        )


def executor_runtime_info() -> dict[str, str]:
    if settings.executor_mode == "grpc":
        try:
            with grpc.insecure_channel(settings.executor_grpc_target) as channel:
                response = executor_pb2_grpc.ExecutorStub(channel).Health(
                    executor_pb2.HealthRequest(),
                    timeout=1.5,
                )
                return {
                    "implementation": response.implementation or "unknown",
                    "transport": response.transport or "grpc",
                }
        except grpc.RpcError:
            return {"implementation": "unavailable", "transport": "grpc"}
    if settings.executor_mode == "http":
        try:
            with httpx.Client(timeout=1.5) as client:
                response = client.get(f"{settings.executor_url.rstrip('/')}/healthz")
                response.raise_for_status()
                data = response.json()
                return {
                    "implementation": str(data.get("implementation") or "unknown"),
                    "transport": "http-json",
                }
        except (httpx.HTTPError, ValueError, TypeError):
            return {"implementation": "unavailable", "transport": "http-json"}
    return {"implementation": "local", "transport": "local"}


def executor_implementation() -> str:
    return executor_runtime_info()["implementation"]


def executor_transport() -> str:
    return executor_runtime_info()["transport"]


def executor_client():
    if settings.executor_mode == "grpc":
        return GRPCExecutorClient()
    if settings.executor_mode == "http":
        return HTTPExecutorClient()
    return LocalExecutorClient()
