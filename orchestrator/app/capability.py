from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import uuid

import jwt

from .config import settings


class CapabilityError(ValueError):
    pass


@dataclass(frozen=True)
class CapabilityScope:
    epoch_id: str
    actor_type: str
    actor_id: str
    project: str
    environment: str
    action: str
    fingerprint: str


def issue_capability(scope: CapabilityScope, ttl_seconds: int = 300) -> tuple[str, str, datetime]:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=ttl_seconds)
    jti = str(uuid.uuid4())
    payload = {
        "ver": 1,
        "jti": jti,
        "typ": "epochdeploy-capability",
        "epoch_id": scope.epoch_id,
        "actor_type": scope.actor_type,
        "actor_id": scope.actor_id,
        "project": scope.project,
        "environment": scope.environment,
        "action": scope.action,
        "fingerprint": scope.fingerprint,
        "iat": now,
        "exp": expires,
    }
    token = jwt.encode(payload, settings.capability_secret, algorithm="HS256")
    return token, jti, expires


def verify_capability(token: str, expected: CapabilityScope) -> dict:
    try:
        claims = jwt.decode(token, settings.capability_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise CapabilityError("capability가 만료되었습니다.") from exc
    except jwt.PyJWTError as exc:
        raise CapabilityError("capability 서명이 유효하지 않습니다.") from exc

    expected_claims = {
        "typ": "epochdeploy-capability",
        "epoch_id": expected.epoch_id,
        "actor_type": expected.actor_type,
        "actor_id": expected.actor_id,
        "project": expected.project,
        "environment": expected.environment,
        "action": expected.action,
        "fingerprint": expected.fingerprint,
    }
    for key, value in expected_claims.items():
        if claims.get(key) != value:
            raise CapabilityError(f"capability scope가 일치하지 않습니다: {key}")
    if claims.get("ver") != 1 or not claims.get("jti"):
        raise CapabilityError("지원하지 않는 capability token입니다.")
    return claims
