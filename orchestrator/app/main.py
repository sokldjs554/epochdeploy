from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .fingerprint import fingerprint
from .models import Approval, ArtifactEvidence, DeploymentEpoch, ExecutionReceipt, LiveTarget, User, WebhookEvent
from .schemas import DriftRequest, EpochCreate, ExecuteRequest, LoginRequest, ReceiptOut, TargetObservation, TokenResponse
from .security import current_user, hash_password, issue_token, require_role, verify_password
from .services import apply_gitlab_pipeline_event, approve_epoch, create_epoch, epoch_identity, execute_epoch, save_evidence, sync_executor_observation, upsert_target

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.demo_mode:
        _seed_demo_users()
    yield


app = FastAPI(title="EpochDeploy", version="0.1.0", docs_url="/api/docs", redoc_url=None, lifespan=lifespan)
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


def _demo_only() -> None:
    if not settings.demo_mode:
        raise HTTPException(status_code=404, detail="not found")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    return response


def _seed_demo_users() -> None:
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add_all([
                User(username="operator", password_hash=hash_password("operator-demo"), role="operator"),
                User(username="approver", password_hash=hash_password("approver-demo"), role="approver"),
                User(username="admin", password_hash=hash_password("admin-demo"), role="admin"),
            ])
            db.commit()
    finally:
        db.close()


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(static_dir / "index.html")


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "epochdeploy-orchestrator"}


@app.post("/api/auth/token", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    return TokenResponse(access_token=issue_token(user), role=user.role)


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username, "role": user.role}


@app.post("/api/epochs", status_code=201)
def api_create_epoch(payload: EpochCreate, user: User = Depends(require_role("operator", "admin")), db: Session = Depends(get_db)):
    row = create_epoch(db, payload, user.username)
    return epoch_view(db, row)


@app.get("/api/epochs")
def list_epochs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(DeploymentEpoch).order_by(DeploymentEpoch.created_at.desc()).limit(100).all()
    return [epoch_view(db, row) for row in rows]


@app.get("/api/epochs/{epoch_id}")
def get_epoch(epoch_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = _epoch_or_404(db, epoch_id)
    return epoch_view(db, row)


@app.post("/api/epochs/{epoch_id}/approve")
def approve(epoch_id: str, user: User = Depends(require_role("approver", "admin")), db: Session = Depends(get_db)):
    row = _epoch_or_404(db, epoch_id)
    approval = approve_epoch(db, row, user.username)
    return {"epoch_id": row.id, "state": row.state, "approved_fingerprint": approval.approved_fingerprint, "approver": approval.approver}


@app.post("/api/epochs/{epoch_id}/execute", response_model=ReceiptOut)
def execute(epoch_id: str, payload: ExecuteRequest, user: User = Depends(require_role("operator", "admin")), db: Session = Depends(get_db)):
    row = _epoch_or_404(db, epoch_id)
    receipt, diffs = execute_epoch(db, row, payload.idempotency_key)
    return ReceiptOut(
        epoch_id=row.id,
        outcome=receipt.outcome,
        expected_fingerprint=receipt.expected_fingerprint,
        observed_fingerprint=receipt.observed_fingerprint,
        reason=receipt.reason,
        latency_ms=receipt.latency_ms,
        differences=diffs,
    )


@app.get("/api/epochs/{epoch_id}/receipts")
def receipts(epoch_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _epoch_or_404(db, epoch_id)
    rows = db.query(ExecutionReceipt).filter(ExecutionReceipt.epoch_id == epoch_id).order_by(ExecutionReceipt.created_at.desc()).all()
    return [{
        "id": r.id, "outcome": r.outcome, "reason": r.reason,
        "expected_fingerprint": r.expected_fingerprint,
        "observed_fingerprint": r.observed_fingerprint,
        "latency_ms": r.latency_ms, "created_at": r.created_at,
    } for r in rows]


@app.post("/api/targets/observe")
def observe_target(payload: TargetObservation, user: User = Depends(require_role("operator", "admin")), db: Session = Depends(get_db)):
    row = upsert_target(db, payload)
    ident = payload.model_dump()
    return {"project": row.project, "environment": row.environment, "fingerprint": fingerprint(ident), **ident}


@app.post("/api/epochs/{epoch_id}/evidence", status_code=201)
async def upload_evidence(
    epoch_id: str,
    kind: str = Form(..., min_length=1, max_length=40),
    file: UploadFile = File(...),
    user: User = Depends(require_role("operator", "admin")),
    db: Session = Depends(get_db),
):
    row = _epoch_or_404(db, epoch_id)
    evidence = await save_evidence(db, row, kind, file)
    return {"id": evidence.id, "kind": evidence.kind, "filename": evidence.filename, "sha256": evidence.sha256, "size_bytes": evidence.size_bytes}


@app.post("/api/integrations/gitlab/webhook")
async def gitlab_webhook(
    request: Request,
    x_gitlab_token: str | None = Header(default=None),
    x_gitlab_event: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if x_gitlab_token is None or not hmac.compare_digest(x_gitlab_token, settings.gitlab_webhook_token):
        raise HTTPException(status_code=401, detail="invalid gitlab webhook token")
    raw_buffer = bytearray()
    async for chunk in request.stream():
        raw_buffer.extend(chunk)
        if len(raw_buffer) > settings.max_webhook_bytes:
            raise HTTPException(status_code=413, detail="gitlab webhook payload too large")
    raw = bytes(raw_buffer)
    payload_hash = hashlib.sha256(raw).hexdigest()
    if db.query(WebhookEvent).filter(WebhookEvent.payload_hash == payload_hash).one_or_none():
        return {"accepted": True, "duplicate": True}
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid json")
    event = WebhookEvent(provider="gitlab", event_type=x_gitlab_event or "unknown", external_id=str(payload.get("object_attributes", {}).get("id", "")), payload_hash=payload_hash)
    db.add(event)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return {"accepted": True, "duplicate": True}
    if (x_gitlab_event or "").lower() == "pipeline hook":
        attrs = payload.get("object_attributes", {})
        pipeline_id = str(attrs.get("id", ""))
        status = str(attrs.get("status", "unknown"))
        pipeline_sha = str(attrs.get("sha", ""))
        apply_gitlab_pipeline_event(db, pipeline_id=pipeline_id, status=status, pipeline_sha=pipeline_sha)
    db.commit()
    return {"accepted": True, "duplicate": False}


@app.get("/api/epochs/{epoch_id}/evidence")
def list_evidence(epoch_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _epoch_or_404(db, epoch_id)
    rows = (
        db.query(ArtifactEvidence)
        .filter(ArtifactEvidence.epoch_id == epoch_id)
        .order_by(ArtifactEvidence.created_at.desc())
        .all()
    )
    return [{
        "id": row.id,
        "kind": row.kind,
        "filename": row.filename,
        "sha256": row.sha256,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "created_at": row.created_at,
    } for row in rows]


@app.get("/api/integrations/status")
def integrations_status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    last_event = db.query(WebhookEvent).order_by(WebhookEvent.received_at.desc()).first()
    return {
        "gitlab": {
            "webhook_configured": bool(settings.gitlab_webhook_token),
            "event": "Pipeline Hook",
            "sha_binding": True,
            "last_event_type": last_event.event_type if last_event else None,
            "last_external_id": last_event.external_id if last_event else None,
        },
        "executor": {
            "mode": settings.executor_mode,
            "transport": "signed-http" if settings.executor_mode == "http" else "in-process",
            "request_auth": "timestamped HMAC-SHA256" if settings.executor_mode == "http" else "local",
        },
        "database": {"dialect": engine.dialect.name},
    }


@app.post("/api/demo/bootstrap")
def demo_bootstrap(user: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    _demo_only()
    for model in (ExecutionReceipt, Approval, LiveTarget, DeploymentEpoch):
        db.query(model).delete()
    db.commit()
    payload = EpochCreate(
        project="payments-api",
        environment="prod",
        commit_sha="8f375e7b64f6d20a3c1a1b2a6f9a1d9e2f7c1234",
        artifact_digest="sha256:3a7d5d6259081b92f69359685c9b0f3f3f2ad7b3ce84b3ae6a711a3fa2d0ef77",
        config_hash="cfg:2e9d35a12347bd18bb3c9dcb7a4c8701",
        pipeline_id="7421",
    )
    epoch = create_epoch(db, payload, user.username)
    target = TargetObservation(**epoch_identity(epoch))
    upsert_target(db, target)
    return epoch_view(db, epoch)


@app.post("/api/demo/gitlab-success/{epoch_id}")
def demo_gitlab_success(epoch_id: str, user: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    _demo_only()
    epoch = _epoch_or_404(db, epoch_id)
    payload = {
        "object_kind": "pipeline",
        "object_attributes": {"id": int(epoch.pipeline_id), "status": "success", "sha": epoch.commit_sha},
        "project": {"path_with_namespace": f"demo/{epoch.project}"},
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_hash = hashlib.sha256(raw).hexdigest()
    event = db.query(WebhookEvent).filter(WebhookEvent.payload_hash == payload_hash).one_or_none()
    if event is None:
        db.add(WebhookEvent(
            provider="gitlab", event_type="Pipeline Hook", external_id=epoch.pipeline_id, payload_hash=payload_hash
        ))
    apply_gitlab_pipeline_event(
        db, pipeline_id=epoch.pipeline_id, status="success", pipeline_sha=epoch.commit_sha
    )
    db.commit()
    db.refresh(epoch)
    return epoch_view(db, epoch)


@app.post("/api/demo/drift/{epoch_id}")
def demo_drift(epoch_id: str, payload: DriftRequest, user: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    _demo_only()
    epoch = _epoch_or_404(db, epoch_id)
    if payload.field not in {"commit_sha", "artifact_digest", "config_hash"}:
        raise HTTPException(status_code=400, detail="unsupported drift field")
    target = db.query(LiveTarget).filter(LiveTarget.project == epoch.project, LiveTarget.environment == epoch.environment).one_or_none()
    if target is None:
        raise HTTPException(status_code=409, detail="target missing")
    setattr(target, payload.field, payload.value)
    db.commit()
    observed = {
        "project": target.project, "environment": target.environment, "commit_sha": target.commit_sha,
        "artifact_digest": target.artifact_digest, "config_hash": target.config_hash,
    }
    sync_executor_observation(observed)
    return {"field": payload.field, "value": payload.value, "observed_fingerprint": fingerprint(observed)}


def _epoch_or_404(db: Session, epoch_id: str) -> DeploymentEpoch:
    row = db.get(DeploymentEpoch, epoch_id)
    if row is None:
        raise HTTPException(status_code=404, detail="epoch not found")
    return row


def epoch_view(db: Session, row: DeploymentEpoch) -> dict:
    approval = db.query(Approval).filter(Approval.epoch_id == row.id).one_or_none()
    return {
        "id": row.id,
        "project": row.project,
        "environment": row.environment,
        "commit_sha": row.commit_sha,
        "artifact_digest": row.artifact_digest,
        "config_hash": row.config_hash,
        "pipeline_id": row.pipeline_id,
        "pipeline_status": row.pipeline_status,
        "fingerprint": row.fingerprint,
        "state": row.state,
        "created_by": row.created_by,
        "approved_by": approval.approver if approval else None,
        "created_at": row.created_at,
    }
