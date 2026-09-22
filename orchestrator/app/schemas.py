from __future__ import annotations

import re
from pydantic import BaseModel, ConfigDict, Field, field_validator

_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
_CONFIG_RE = re.compile(r"^(?:cfg:[0-9a-fA-F]{32,64}|sha256:[0-9a-fA-F]{64})$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class IdentityFields(StrictModel):
    project: str = Field(min_length=2, max_length=120)
    environment: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,31}$")
    commit_sha: str = Field(min_length=7, max_length=64)
    artifact_digest: str = Field(min_length=71, max_length=71)
    config_hash: str = Field(min_length=36, max_length=71)

    @field_validator("commit_sha")
    @classmethod
    def immutable_commit(cls, value: str) -> str:
        if not _HEX_RE.fullmatch(value):
            raise ValueError("commit_sha must be a hexadecimal immutable Git commit id")
        return value.lower()

    @field_validator("artifact_digest")
    @classmethod
    def immutable_artifact(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("artifact_digest must be an immutable sha256:<64 hex> digest")
        return value.lower()

    @field_validator("config_hash")
    @classmethod
    def immutable_config(cls, value: str) -> str:
        if not _CONFIG_RE.fullmatch(value):
            raise ValueError("config_hash must be cfg:<32-64 hex> or sha256:<64 hex>")
        return value.lower()


class EpochCreate(IdentityFields):
    pipeline_id: str = Field(min_length=1, max_length=80)


class AgentChangeCreate(EpochCreate):
    change_request_id: str = Field(min_length=2, max_length=120)
    reason: str = Field(min_length=8, max_length=1000)
    actor_id: str = Field(min_length=2, max_length=120)
    action: str = Field(default="deploy", pattern=r"^[a-z][a-z0-9_-]{1,39}$")


class TargetObservation(IdentityFields):
    pass


class ExecuteRequest(StrictModel):
    idempotency_key: str = Field(min_length=8, max_length=120)


class DriftRequest(StrictModel):
    field: str
    value: str = Field(min_length=1, max_length=256)


class ReceiptOut(BaseModel):
    epoch_id: str
    outcome: str
    expected_fingerprint: str
    observed_fingerprint: str
    reason: str
    latency_ms: int
    differences: list[dict[str, str]] = Field(default_factory=list)
