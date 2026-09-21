from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import statistics
import time

import httpx

BASE_URL = os.getenv("EPOCHDEPLOY_BENCHMARK_URL", "http://127.0.0.1:9080")
SECRET = os.getenv("EPOCHDEPLOY_EXECUTOR_HMAC_SECRET", "local-executor-secret")
IDENTITY = {
    "project": "payments-api",
    "environment": "prod",
    "commit_sha": "8f375e7b64f6d20a3c1a1b2a6f9a1d9e2f7c1234",
    "artifact_digest": "sha256:3a7d5d6259081b92f69359685c9b0f3f3f2ad7b3ce84b3ae6a711a3fa2d0ef77",
    "config_hash": "cfg:2e9d35a12347bd18bb3c9dcb7a4c8701",
}


def signed_payload(payload: dict) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(SECRET.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return body, {
        "content-type": "application/json",
        "x-epochdeploy-timestamp": timestamp,
        "x-epochdeploy-signature": f"sha256={signature}",
    }


async def main(total: int = 1000, concurrency: int = 50):
    sem = asyncio.Semaphore(concurrency)
    latencies = []
    failures = 0
    async with httpx.AsyncClient(timeout=5.0) as client:
        body, headers = signed_payload({"identity": IDENTITY})
        observed = await client.post(f"{BASE_URL}/v1/targets/observe", content=body, headers=headers)
        observed.raise_for_status()

        async def one():
            nonlocal failures
            async with sem:
                body, headers = signed_payload({"expected": IDENTITY})
                started = time.perf_counter()
                response = await client.post(f"{BASE_URL}/v1/execute", content=body, headers=headers)
                latencies.append((time.perf_counter() - started) * 1000)
                if response.status_code != 200 or response.json().get("outcome") != "EXECUTED":
                    failures += 1

        started = time.perf_counter()
        await asyncio.gather(*(one() for _ in range(total)))
        elapsed = time.perf_counter() - started
    ordered = sorted(latencies)

    def pct(p):
        return ordered[min(len(ordered) - 1, int(len(ordered) * p))]

    print(json.dumps({
        "requests": total,
        "concurrency": concurrency,
        "failures": failures,
        "elapsed_s": round(elapsed, 3),
        "throughput_rps": round(total / elapsed, 1),
        "latency_ms": {
            "p50": round(statistics.median(ordered), 2),
            "p95": round(pct(.95), 2),
            "p99": round(pct(.99), 2),
        },
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
