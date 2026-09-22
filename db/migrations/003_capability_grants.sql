CREATE TABLE IF NOT EXISTS capability_grants (
  id VARCHAR(36) PRIMARY KEY,
  epoch_id VARCHAR(36) NOT NULL REFERENCES deployment_epochs(id) ON DELETE CASCADE,
  actor_type VARCHAR(32) NOT NULL,
  actor_id VARCHAR(120) NOT NULL,
  project VARCHAR(120) NOT NULL,
  environment VARCHAR(32) NOT NULL,
  action VARCHAR(40) NOT NULL,
  fingerprint CHAR(64) NOT NULL,
  issued_by VARCHAR(80) NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_capability_epoch_created ON capability_grants(epoch_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_capability_actor ON capability_grants(actor_type, actor_id);
CREATE INDEX IF NOT EXISTS ix_capability_expiry ON capability_grants(expires_at);
