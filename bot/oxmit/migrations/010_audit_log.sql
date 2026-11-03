-- NEW-005 (panel v2): immutable admin action log. Every mutating action from
-- the web panel and the Telegram admin panel is recorded here. No updates,
-- no deletes by application code.

CREATE TABLE IF NOT EXISTS audit_log (
    id      BIGSERIAL PRIMARY KEY,
    ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor   TEXT NOT NULL,
    role    TEXT,
    action  TEXT NOT NULL,
    target  TEXT,
    details TEXT,
    source  TEXT NOT NULL DEFAULT 'web',
    ip      TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log (action);
