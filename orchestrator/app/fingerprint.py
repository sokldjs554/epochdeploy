from __future__ import annotations

import hashlib
import json
from typing import Mapping

FIELDS = ("project", "environment", "commit_sha", "artifact_digest", "config_hash")


def canonical_identity(identity: Mapping[str, str]) -> dict[str, str]:
    return {k: str(identity[k]).strip() for k in FIELDS}


def fingerprint(identity: Mapping[str, str]) -> str:
    payload = json.dumps(canonical_identity(identity), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def diff_identity(expected: Mapping[str, str], observed: Mapping[str, str]) -> list[dict[str, str]]:
    diffs = []
    for field in FIELDS:
        e, o = str(expected[field]).strip(), str(observed[field]).strip()
        if e != o:
            diffs.append({"field": field, "expected": e, "observed": o})
    return diffs
