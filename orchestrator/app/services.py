from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .capability import CapabilityError, CapabilityScope, issue_capability, verify_capability
from .config import settings
from .executor_client import ExecutorBoundaryError, executor_client
from .fingerprint import fingerprint
from .governance import record_event
from .models import Approval, ArtifactEvidence, CapabilityGrant, ChangeRequest, DeploymentEpoch, ExecutionReceipt, LiveTarget, OutboxEvent
from .policy import evaluate_policy


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
    record_event(
        db,
        epoch_id=row.id,
        event_type="EPOCH_CREATED",
        actor_type="human",
        actor_id=created_by,
        summary=f"Deployment epoch created for {row.project}/{row.environment}",
        details={"fingerprint": row.fingerprint, "pipeline_id": row.pipeline_id},
    )
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
    record_event(
        db,
        epoch_id=locked.id,
        event_type="APPROVED",
        actor_type="human",
        actor_id=approver,
        summary="Human approver bound approval to the immutable release fingerprint",
        details={"approved_fingerprint": locked.fingerprint},
    )
    db.commit()
    return approval


def issue_execution_capability(
    db: Session,
    epoch: DeploymentEpoch,
    issued_by: str,
    ttl_seconds: int = 300,
) -> tuple[CapabilityGrant, str]:
    locked = db.execute(
        select(DeploymentEpoch).where(DeploymentEpoch.id == epoch.id).with_for_update()
    ).scalar_one()
    change = db.query(ChangeRequest).filter(ChangeRequest.epoch_id == locked.id).one_or_none()
    if change is None or change.actor_type != "ai_agent":
        raise HTTPException(status_code=409, detail="scoped capability is only issued for AI-agent-originated changes")
    if locked.pipeline_status != "success":
        raise HTTPException(status_code=409, detail="verified pipeline is required before capability issuance")

    decision = evaluate_policy(
        actor_type=change.actor_type,
        action=change.action,
        environment=locked.environment,
    )
    record_event(
        db,
        epoch_id=locked.id,
        event_type="POLICY_EVALUATED",
        actor_type="system",
        actor_id="policy-engine",
        summary=f"Policy decision {decision.decision}: {decision.reason}",
        details={
            "decision": decision.decision,
            "rule_id": decision.rule_id,
            "required_controls": list(decision.required_controls),
            "action": change.action,
            "environment": locked.environment,
        },
    )

    if decision.decision == "DENY":
        db.commit()
        raise HTTPException(status_code=403, detail=decision.reason)

    approval = db.query(Approval).filter(Approval.epoch_id == locked.id).one_or_none()
    if decision.decision == "ASK":
        if locked.state != "APPROVED" or approval is None or approval.approved_fingerprint != locked.fingerprint:
            db.commit()
            raise HTTPException(status_code=409, detail="policy requires explicit human approval before capability issuance")

    actor_type = change.actor_type
    actor_id = change.actor_id
    action = change.action
    scope = CapabilityScope(
        epoch_id=locked.id,
        actor_type=actor_type,
        actor_id=actor_id,
        project=locked.project,
        environment=locked.environment,
        action=action,
        fingerprint=locked.fingerprint,
    )
    token, jti, expires_at = issue_capability(scope, ttl_seconds)
    grant = CapabilityGrant(
        id=jti,
        epoch_id=locked.id,
        actor_type=actor_type,
        actor_id=actor_id,
        project=locked.project,
        environment=locked.environment,
        action=action,
        fingerprint=locked.fingerprint,
        issued_by=issued_by,
        expires_at=expires_at,
    )
    db.add(grant)
    record_event(
        db,
        epoch_id=locked.id,
        event_type="CAPABILITY_ISSUED",
        actor_type="human" if decision.decision == "ASK" else "system",
        actor_id=issued_by if decision.decision == "ASK" else "policy-engine",
        summary=f"Scoped {action} capability issued to {actor_type}:{actor_id}",
        details={
            "capability_id": jti,
            "policy_decision": decision.decision,
            "policy_rule": decision.rule_id,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "project": locked.project,
            "environment": locked.environment,
            "action": action,
            "fingerprint": locked.fingerprint,
            "expires_at": expires_at.isoformat(),
        },
    )
    db.commit()
    return grant, token


def execute_agent_epoch(
    db: Session,
    epoch: DeploymentEpoch,
    idempotency_key: str,
    capability_token: str,
) -> tuple[ExecutionReceipt, list[dict[str, str]]]:
    change = db.query(ChangeRequest).filter(ChangeRequest.epoch_id == epoch.id).one_or_none()
    if change is None or change.actor_type != "ai_agent":
        raise HTTPException(status_code=409, detail="epoch is not an AI-agent-originated change")
    scope = CapabilityScope(
        epoch_id=epoch.id,
        actor_type=change.actor_type,
        actor_id=change.actor_id,
        project=epoch.project,
        environment=epoch.environment,
        action=change.action,
        fingerprint=epoch.fingerprint,
    )
    try:
        claims = verify_capability(capability_token, scope)
    except CapabilityError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    grant = db.get(CapabilityGrant, claims["jti"])
    now = datetime.now(timezone.utc)
    if grant is None or grant.epoch_id != epoch.id or grant.revoked_at is not None:
        raise HTTPException(status_code=403, detail="capability grant is not active")
    expires = grant.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        raise HTTPException(status_code=403, detail="capability grant expired")
    context = {
        "epoch_id": epoch.id,
        "actor_type": change.actor_type,
        "actor_id": change.actor_id,
        "action": change.action,
        "approved_fingerprint": epoch.fingerprint,
        "capability_token": capability_token,
    }
    return execute_epoch(db, epoch, idempotency_key, execution_context=context)


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


def execute_epoch(
    db: Session,
    epoch: DeploymentEpoch,
    idempotency_key: str,
    execution_context: dict | None = None,
) -> tuple[ExecutionReceipt, list[dict[str, str]]]:
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
        result = executor_client().execute(expected, observed, execution_context)
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
    record_event(
        db,
        epoch_id=locked.id,
        event_type=result.outcome,
        actor_type="service",
        actor_id="go-executor",
        summary=result.reason,
        details={
            "expected_fingerprint": locked.fingerprint,
            "observed_fingerprint": result.observed_fingerprint,
            "differences": result.differences,
            "latency_ms": result.latency_ms,
        },
    )
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
    record_event(
        db,
        epoch_id=epoch.id,
        event_type="EVIDENCE_ATTACHED",
        actor_type="service",
        actor_id="fastapi-orchestrator",
        summary=f"Evidence attached: {safe_name}",
        details={"kind": kind, "sha256": sha, "size_bytes": len(content)},
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return row
