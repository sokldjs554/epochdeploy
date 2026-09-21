from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DeploymentEpoch(Base):
    __tablename__ = "deployment_epochs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project: Mapped[str] = mapped_column(String(120), index=True)
    environment: Mapped[str] = mapped_column(String(32), index=True)
    commit_sha: Mapped[str] = mapped_column(String(64))
    artifact_digest: Mapped[str] = mapped_column(String(128))
    config_hash: Mapped[str] = mapped_column(String(128))
    pipeline_id: Mapped[str] = mapped_column(String(80), index=True)
    pipeline_status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    created_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_epoch_project_env_created", "project", "environment", "created_at"),
    )


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    epoch_id: Mapped[str] = mapped_column(ForeignKey("deployment_epochs.id", ondelete="CASCADE"), unique=True, index=True)
    approver: Mapped[str] = mapped_column(String(80))
    approved_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArtifactEvidence(Base):
    __tablename__ = "artifact_evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    epoch_id: Mapped[str] = mapped_column(ForeignKey("deployment_epochs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LiveTarget(Base):
    __tablename__ = "live_targets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project: Mapped[str] = mapped_column(String(120))
    environment: Mapped[str] = mapped_column(String(32))
    commit_sha: Mapped[str] = mapped_column(String(64))
    artifact_digest: Mapped[str] = mapped_column(String(128))
    config_hash: Mapped[str] = mapped_column(String(128))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (UniqueConstraint("project", "environment", name="uq_live_target_project_env"),)


class ExecutionReceipt(Base):
    __tablename__ = "execution_receipts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    epoch_id: Mapped[str] = mapped_column(ForeignKey("deployment_epochs.id", ondelete="CASCADE"), index=True)
    outcome: Mapped[str] = mapped_column(String(32), index=True)
    expected_fingerprint: Mapped[str] = mapped_column(String(64))
    observed_fingerprint: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(120))
    differences_json: Mapped[list] = mapped_column(JSON, default=list)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


    __table_args__ = (UniqueConstraint("epoch_id", "idempotency_key", name="uq_receipt_epoch_idempotency"),)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(80))
    external_id: Mapped[str] = mapped_column(String(120), default="")
    payload_hash: Mapped[str] = mapped_column(String(64), unique=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic: Mapped[str] = mapped_column(String(120), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
