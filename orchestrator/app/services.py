from __future__ import annotations

import asyncio
import hashlib
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .executor_client import ExecutorBoundaryError, executor_client
from .fingerprint import fingerprint
from .models import Approval, ArtifactEvidence, DeploymentEpoch, ExecutionReceipt, LiveTarget, OutboxEvent


def epoch_identity(epoch: DeploymentEpoch) -> dict[str, str]:
    return {
        "project": epoch.project,
        "environment": epoch.environment,
        "commit_sha": epoch.commit_sha,
        "artifact_digest": epoch.artifact_digest,
        "config_hash": epoch.config_hash,
    }


def create_epoch(db: Session, payload, created_by: str, *, pipeline_status: str = "pending") -> DeploymentEpoch:
    ident = payload.model_dump(include={"project", "environment", "commit_sha", "artifact_digest", "config_hash"})
    row = DeploymentEpoch(
        id=str(uuid.uuid4()),
        fingerprint=fingerprint(ident),
        created_by=created_by,
        pipeline_status=pipeline_status,
        **payload.model_dump(),
    )
    db.add(row)
    db.commit()
    return row


def approve_epoch(db: Session, epoch: DeploymentEpoch, approver: str) -> Approval:
    locked = db.execute(
        select(DeploymentEpoch).where(DeploymentEpoch.id == epoch.id).with_for_update()
    ).scalar_one()
    if locked.pipeline_status != "success":
        raise HTTPException(status_code=409, detail="verified GitLab pipeline must be successful before approval")
    existing = db.query(Approval).filter(Approval.epoch_id == locked.id).one_or_none()
    if existing:
        return existing
    approval = Approval(epoch_id=locked.id, approver=approver, approved_fingerprint=locked.fingerprint)
    locked.state = "APPROVED"
    db.add(approval)
    db.commit()
    return approval


def upsert_target(db: Session, payload) -> LiveTarget:
    row = db.query(LiveTarget).filter(
        LiveTarget.project == payload.project,
        LiveTarget.environment == payload.environment,
    ).one_or_none()
    if row is None:
        row = LiveTarget(**payload.model_dump())
        db.add(row)
    else:
        for k, v in payload.model_dump().items():
            setattr(row, k, v)
    db.commit()
    sync_executor_observation(payload.model_dump())
    return row


def sync_executor_observation(identity: dict[str, str]) -> None:
    try:
        executor_client().observe(identity)
    except ExecutorBoundaryError as exc:
        raise HTTPException(status_code=502, detail="executor observation unavailable") from exc


def execute_epoch(db: Session, epoch: DeploymentEpoch, idempotency_key: str) -> tuple[ExecutionReceipt, list[dict[str, str]]]:
    # PostgreSQL uses this row lock to serialize execution attempts per epoch.
    locked = db.execute(
        select(DeploymentEpoch).where(DeploymentEpoch.id == epoch.id).with_for_update()
    ).scalar_one()
    existing = db.query(ExecutionReceipt).filter(
        ExecutionReceipt.epoch_id == locked.id,
        ExecutionReceipt.idempotency_key == idempotency_key,
    ).one_or_none()
    if existing:
        return existing, list(existing.differences_json or [])
    if locked.state != "APPROVED":
        raise HTTPException(status_code=409, detail=f"epoch is not executable from state {locked.state}")
    approval = db.query(Approval).filter(Approval.epoch_id == locked.id).one_or_none()
    if approval is None or approval.approved_fingerprint != locked.fingerprint:
        raise HTTPException(status_code=409, detail="epoch has no valid approval bound to its current fingerprint")
    live = db.query(LiveTarget).filter(
        LiveTarget.project == locked.project,
        LiveTarget.environment == locked.environment,
    ).one_or_none()
    if live is None:
        raise HTTPException(status_code=409, detail="live target has not been observed")
    expected = epoch_identity(locked)
    observed = {
        "project": live.project,
        "environment": live.environment,
        "commit_sha": live.commit_sha,
        "artifact_digest": live.artifact_digest,
        "config_hash": live.config_hash,
    }
    try:
        result = executor_client().execute(expected, observed)
    except ExecutorBoundaryError as exc:
        raise HTTPException(status_code=502, detail="executor boundary unavailable") from exc
    receipt = ExecutionReceipt(
        epoch_id=locked.id,
        outcome=result.outcome,
        expected_fingerprint=locked.fingerprint,
        observed_fingerprint=result.observed_fingerprint,
        reason=result.reason,
        idempotency_key=idempotency_key,
        differences_json=result.differences,
        latency_ms=result.latency_ms,
    )
    locked.state = result.outcome
    db.add(receipt)
    db.add(OutboxEvent(topic="deployment.execution", payload={
        "epoch_id": locked.id,
        "outcome": result.outcome,
        "expected_fingerprint": locked.fingerprint,
        "observed_fingerprint": result.observed_fingerprint,
    }))
    db.commit()
    return receipt, result.differences



async def save_evidence(db: Session, epoch: DeploymentEpoch, kind: str, upload: UploadFile) -> ArtifactEvidence:
    target_dir = Path(settings.upload_dir) / epoch.id
    target_dir.mkdir(parents=True, exist_ok=True)
    original_name = Path(upload.filename or "evidence.bin").name
    safe_name = original_name[:180] or "evidence.bin"
    content = await upload.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="evidence file too large")
    sha = hashlib.sha256(content).hexdigest()
    path = target_dir / f"{sha[:12]}-{safe_name}"
    await asyncio.to_thread(path.write_bytes, content)
    row = ArtifactEvidence(
        epoch_id=epoch.id,
        kind=kind,
        filename=safe_name,
        sha256=sha,
        content_type=(upload.content_type or "application/octet-stream")[:120],
        size_bytes=len(content),
        storage_path=str(path),
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return row
