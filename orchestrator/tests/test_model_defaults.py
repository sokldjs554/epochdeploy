from app.db import SessionLocal
from app.models import DeploymentEpoch


def test_deployment_epoch_pipeline_status_defaults_pending():
    db = SessionLocal()
    try:
        row = DeploymentEpoch(
            id="11111111-1111-1111-1111-111111111111",
            project="payments-api",
            environment="prod",
            commit_sha="abcdef1",
            artifact_digest="sha256:" + "1" * 64,
            config_hash="cfg:" + "2" * 32,
            pipeline_id="7421",
            fingerprint="0" * 64,
            created_by="operator",
        )
        db.add(row)
        db.flush()
        assert row.pipeline_status == "pending"
    finally:
        db.rollback()
        db.close()
