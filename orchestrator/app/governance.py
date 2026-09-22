from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from .models import (
    Approval,
    ArtifactEvidence,
    ChangeRequest,
    DeploymentEpoch,
    ExecutionReceipt,
    PassportEvent,
)


def record_event(
    db: Session,
    *,
    epoch_id: str,
    event_type: str,
    actor_type: str,
    actor_id: str,
    summary: str,
    details: dict[str, Any] | None = None,
) -> PassportEvent:
    event = PassportEvent(
        epoch_id=epoch_id,
        event_type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        summary=summary[:255],
        details_json=details or {},
    )
    db.add(event)
    return event


def create_change_request(
    db: Session,
    *,
    epoch: DeploymentEpoch,
    external_ref: str,
    reason: str,
    actor_type: str,
    actor_id: str,
    requested_by: str,
    action: str = "deploy",
) -> ChangeRequest:
    row = ChangeRequest(
        id=str(uuid.uuid4()),
        epoch_id=epoch.id,
        external_ref=external_ref,
        reason=reason,
        actor_type=actor_type,
        actor_id=actor_id,
        requested_by=requested_by,
        action=action,
    )
    db.add(row)
    record_event(
        db,
        epoch_id=epoch.id,
        event_type="CHANGE_REQUESTED",
        actor_type=actor_type,
        actor_id=actor_id,
        summary=f"{external_ref}: {reason}",
        details={
            "external_ref": external_ref,
            "requested_by": requested_by,
            "action": action,
        },
    )
    db.commit()
    return row


def build_passport(db: Session, epoch: DeploymentEpoch) -> dict[str, Any]:
    change = db.query(ChangeRequest).filter(ChangeRequest.epoch_id == epoch.id).one_or_none()
    approval = db.query(Approval).filter(Approval.epoch_id == epoch.id).one_or_none()
    evidence = (
        db.query(ArtifactEvidence)
        .filter(ArtifactEvidence.epoch_id == epoch.id)
        .order_by(ArtifactEvidence.created_at.asc())
        .all()
    )
    receipts = (
        db.query(ExecutionReceipt)
        .filter(ExecutionReceipt.epoch_id == epoch.id)
        .order_by(ExecutionReceipt.created_at.asc())
        .all()
    )
    events = (
        db.query(PassportEvent)
        .filter(PassportEvent.epoch_id == epoch.id)
        .order_by(PassportEvent.created_at.asc(), PassportEvent.id.asc())
        .all()
    )

    return {
        "epoch_id": epoch.id,
        "change": None if change is None else {
            "id": change.id,
            "external_ref": change.external_ref,
            "reason": change.reason,
            "actor_type": change.actor_type,
            "actor_id": change.actor_id,
            "requested_by": change.requested_by,
            "action": change.action,
            "created_at": change.created_at,
        },
        "release": {
            "project": epoch.project,
            "environment": epoch.environment,
            "commit_sha": epoch.commit_sha,
            "artifact_digest": epoch.artifact_digest,
            "config_hash": epoch.config_hash,
            "pipeline_id": epoch.pipeline_id,
            "pipeline_status": epoch.pipeline_status,
            "fingerprint": epoch.fingerprint,
            "state": epoch.state,
        },
        "approval": None if approval is None else {
            "approver": approval.approver,
            "approved_fingerprint": approval.approved_fingerprint,
            "created_at": approval.created_at,
        },
        "evidence": [{
            "id": row.id,
            "kind": row.kind,
            "filename": row.filename,
            "sha256": row.sha256,
            "size_bytes": row.size_bytes,
            "content_type": row.content_type,
            "created_at": row.created_at,
        } for row in evidence],
        "executions": [{
            "id": row.id,
            "outcome": row.outcome,
            "expected_fingerprint": row.expected_fingerprint,
            "observed_fingerprint": row.observed_fingerprint,
            "reason": row.reason,
            "differences": row.differences_json or [],
            "latency_ms": row.latency_ms,
            "created_at": row.created_at,
        } for row in receipts],
        "timeline": [{
            "id": row.id,
            "event_type": row.event_type,
            "actor_type": row.actor_type,
            "actor_id": row.actor_id,
            "summary": row.summary,
            "details": row.details_json or {},
            "created_at": row.created_at,
        } for row in events],
    }
