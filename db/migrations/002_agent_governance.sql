CREATE TABLE IF NOT EXISTS change_requests (
  id VARCHAR(36) PRIMARY KEY,
  epoch_id VARCHAR(36) NOT NULL UNIQUE REFERENCES deployment_epochs(id) ON DELETE CASCADE,
  external_ref VARCHAR(120) NOT NULL,
  reason TEXT NOT NULL,
  actor_type VARCHAR(32) NOT NULL,
  actor_id VARCHAR(120) NOT NULL,
  requested_by VARCHAR(80) NOT NULL,
  action VARCHAR(40) NOT NULL DEFAULT 'deploy',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_change_request_external_ref ON change_requests(external_ref);
CREATE INDEX IF NOT EXISTS ix_change_request_actor ON change_requests(actor_type, actor_id);

CREATE TABLE IF NOT EXISTS passport_events (
  id BIGSERIAL PRIMARY KEY,
  epoch_id VARCHAR(36) NOT NULL REFERENCES deployment_epochs(id) ON DELETE CASCADE,
  event_type VARCHAR(64) NOT NULL,
  actor_type VARCHAR(32) NOT NULL,
  actor_id VARCHAR(120) NOT NULL,
  summary VARCHAR(255) NOT NULL,
  details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_passport_epoch_created ON passport_events(epoch_id, created_at);
CREATE INDEX IF NOT EXISTS ix_passport_event_type ON passport_events(event_type);
