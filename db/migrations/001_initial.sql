-- PostgreSQL 16 reference schema. SQLAlchemy creates the same logical model in local mode.
CREATE TABLE IF NOT EXISTS users (
  id BIGSERIAL PRIMARY KEY,
  username VARCHAR(80) NOT NULL UNIQUE,
  password_hash VARCHAR(256) NOT NULL,
  role VARCHAR(32) NOT NULL CHECK (role IN ('operator','approver','admin')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS deployment_epochs (
  id VARCHAR(36) PRIMARY KEY,
  project VARCHAR(120) NOT NULL,
  environment VARCHAR(32) NOT NULL,
  commit_sha VARCHAR(64) NOT NULL,
  artifact_digest VARCHAR(128) NOT NULL,
  config_hash VARCHAR(128) NOT NULL,
  pipeline_id VARCHAR(80) NOT NULL,
  pipeline_status VARCHAR(24) NOT NULL DEFAULT 'pending',
  fingerprint CHAR(64) NOT NULL,
  state VARCHAR(24) NOT NULL DEFAULT 'DRAFT',
  created_by VARCHAR(80) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (state IN ('DRAFT','APPROVED','EXECUTED','DENIED_STALE'))
);
CREATE INDEX IF NOT EXISTS ix_epoch_project_env_created ON deployment_epochs(project, environment, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_epoch_pipeline_id ON deployment_epochs(pipeline_id);
CREATE INDEX IF NOT EXISTS ix_epoch_state ON deployment_epochs(state);

CREATE TABLE IF NOT EXISTS approvals (
  id BIGSERIAL PRIMARY KEY,
  epoch_id VARCHAR(36) NOT NULL UNIQUE REFERENCES deployment_epochs(id) ON DELETE CASCADE,
  approver VARCHAR(80) NOT NULL,
  approved_fingerprint CHAR(64) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS live_targets (
  id BIGSERIAL PRIMARY KEY,
  project VARCHAR(120) NOT NULL,
  environment VARCHAR(32) NOT NULL,
  commit_sha VARCHAR(64) NOT NULL,
  artifact_digest VARCHAR(128) NOT NULL,
  config_hash VARCHAR(128) NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(project, environment)
);

CREATE TABLE IF NOT EXISTS artifact_evidence (
  id BIGSERIAL PRIMARY KEY,
  epoch_id VARCHAR(36) NOT NULL REFERENCES deployment_epochs(id) ON DELETE CASCADE,
  kind VARCHAR(40) NOT NULL,
  filename VARCHAR(255) NOT NULL,
  sha256 CHAR(64) NOT NULL,
  content_type VARCHAR(120) NOT NULL,
  size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
  storage_path VARCHAR(512) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_evidence_epoch ON artifact_evidence(epoch_id);

CREATE TABLE IF NOT EXISTS execution_receipts (
  id BIGSERIAL PRIMARY KEY,
  epoch_id VARCHAR(36) NOT NULL REFERENCES deployment_epochs(id) ON DELETE CASCADE,
  outcome VARCHAR(32) NOT NULL CHECK (outcome IN ('EXECUTED','DENIED_STALE')),
  expected_fingerprint CHAR(64) NOT NULL,
  observed_fingerprint CHAR(64) NOT NULL,
  reason TEXT NOT NULL,
  idempotency_key VARCHAR(120) NOT NULL,
  differences_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  latency_ms INTEGER NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(epoch_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS ix_receipt_epoch_created ON execution_receipts(epoch_id, created_at DESC);

CREATE TABLE IF NOT EXISTS webhook_events (
  id BIGSERIAL PRIMARY KEY,
  provider VARCHAR(32) NOT NULL,
  event_type VARCHAR(80) NOT NULL,
  external_id VARCHAR(120) NOT NULL DEFAULT '',
  payload_hash CHAR(64) NOT NULL UNIQUE,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS outbox_events (
  id BIGSERIAL PRIMARY KEY,
  topic VARCHAR(120) NOT NULL,
  payload JSONB NOT NULL,
  published BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_outbox_unpublished ON outbox_events(created_at) WHERE published = FALSE;
