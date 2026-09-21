from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import settings
from .fingerprint import diff_identity, fingerprint


class ExecutorBoundaryError(RuntimeError):
    pass


@dataclass
class ExecutorResult:
    outcome: str
    observed_fingerprint: str
    reason: str
    latency_ms: int
    differences: list[dict[str, str]]


class LocalExecutorClient:
    def observe(self, identity: dict[str, str]) -> None:
        return None

    def execute(self, expected: dict[str, str], observed: dict[str, str]) -> ExecutorResult:
        started = time.perf_counter()
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

    def execute(self, expected: dict[str, str], observed: dict[str, str]) -> ExecutorResult:
        del observed  # HTTP execution boundary resolves its own last observed target.
        started = time.perf_counter()
        data = self._signed_post("/v1/execute", {"expected": expected})
        return ExecutorResult(
            outcome=data["outcome"],
            observed_fingerprint=data["observed_fingerprint"],
            reason=data["reason"],
            latency_ms=int((time.perf_counter()-started)*1000),
            differences=data.get("differences", []),
        )


def executor_client():
    return HTTPExecutorClient() if settings.executor_mode == "http" else LocalExecutorClient()
