-- Multi-admin feature integration: per-admin personal settings, Owner-managed
-- permissions, and database-backed merge sessions with strict ordering.
--
-- Design notes:
-- - admin_settings is one row per user (any user may have a row; only
--   permission holders reach the setters). Personal thumbnail stores a
--   server-side file path; watermark config is a JSONB blob whose keys are
--   the verified Argon-derived options; caption is Telegram-side text.
-- - admin_permissions is a scalable grant/revoke table, NOT hardcoded checks.
--   Secure default: a new admin gets compression.use=true, everything else
--   false unless the Owner grants it. Owner bypasses every check in code.
-- - merge ordering is enforced by merge_items.seq with a UNIQUE
--   (session_id, seq) constraint and atomic sequence assignment
--   (item_count + 1 under a transaction with the session row locked).
-- - jobs gains submission-time snapshots (personal thumbnail path, caption,
--   caption mode, watermark config) so a job never re-reads mutable
--   per-admin config while processing, and simultaneous jobs from different
--   admins cannot interfere (spec section 4.4).

CREATE TABLE IF NOT EXISTS admin_settings (
    tg_id             BIGINT PRIMARY KEY REFERENCES users(tg_id) ON DELETE CASCADE,
    thumbnail_path    TEXT,
    watermark         JSONB,
    watermark_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    caption           TEXT,
    caption_mode      TEXT NOT NULL DEFAULT 'replace',
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS admin_permissions (
    tg_id      BIGINT NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    perm       TEXT NOT NULL,
    granted    BOOLEAN NOT NULL DEFAULT TRUE,
    granted_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tg_id, perm)
);
CREATE INDEX IF NOT EXISTS idx_admin_permissions_perm ON admin_permissions (perm, granted);

CREATE TABLE IF NOT EXISTS merge_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tg_id           BIGINT NOT NULL REFERENCES users(tg_id),
    chat_id         BIGINT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'collecting',
    -- collecting | merging | compressing | completed | failed | cancelled
    compress        BOOLEAN NOT NULL DEFAULT FALSE,
    profile         TEXT,
    target_mb       INTEGER,
    item_count      INTEGER NOT NULL DEFAULT 0,
    total_bytes     BIGINT NOT NULL DEFAULT 0,
    result_path     TEXT,
    output_media_id UUID,
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- One active session per user: a second "start merge" cannot fork state.
CREATE UNIQUE INDEX IF NOT EXISTS uq_merge_active_user
    ON merge_sessions (tg_id) WHERE status IN ('collecting', 'merging', 'compressing');

CREATE TABLE IF NOT EXISTS merge_items (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL REFERENCES merge_sessions(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    media_id    UUID NOT NULL REFERENCES media_assets(id),
    staged_path TEXT,
    size_bytes  BIGINT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_merge_items_session ON merge_items (session_id, seq);

-- Submission-time snapshots on jobs (never re-read mutable admin config
-- while a job runs).
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS personal_thumb_path TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS personal_caption TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS caption_mode TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS watermark_json TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS job_kind TEXT NOT NULL DEFAULT 'compress';

INSERT INTO counters(name) VALUES
    ('merges_completed'), ('merges_failed'), ('watermark_jobs'),
    ('personal_thumb_jobs'), ('personal_caption_jobs')
ON CONFLICT (name) DO NOTHING;
