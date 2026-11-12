-- Migration 015: metadata-first (just-in-time) queue, single EDU480 profile,
-- output naming, support-contact routing, moderation and dashboard timestamps.
--
-- Design notes
-- - A job row is now created BEFORE anything is downloaded. Its source is
--   described by Telegram metadata only (file_id / file_unique_id / reported
--   size / duration / dimensions) stored on a metadata-only media_assets row
--   (sha256 stays NULL until a worker downloads and hashes the file).
-- - jobs.status keeps its coarse values (queued | processing | completed |
--   failed | cancelled); jobs.stage carries the fine-grained lifecycle
--   (queued, reserved, downloading, probing, checking, encoding, validating,
--   uploading, delivering, completed, failed, cancelled).
-- - Lease columns (worker_id, lease_expires_at) make ownership explicit so a
--   crashed / restarted worker's job is recovered instead of hanging, and so
--   additional processing servers can later claim from the same table.

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS output_name TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS source_filename TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS chat_id BIGINT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS worker_id TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS reserved_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS download_started_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS download_done_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS encode_started_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS encode_done_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS upload_started_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS upload_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS cancel_reason TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS log_chat_id BIGINT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS log_message_id BIGINT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS decision TEXT;

-- Queue scans: oldest eligible job first, within priority.
CREATE INDEX IF NOT EXISTS idx_jobs_queue_order
    ON jobs (priority DESC, enqueued_at) WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS idx_jobs_completed_at ON jobs (completed_at DESC);
CREATE INDEX IF NOT EXISTS idx_media_unique_id ON media_assets (tg_file_unique_id);

-- Early recognition of known outputs / sources by Telegram file_unique_id.
CREATE INDEX IF NOT EXISTS idx_archive_file_unique ON archive_records (file_unique_id);

-- Video submissions waiting for their output filename. One row per received
-- video; the user's text answer is matched to exactly one draft (the one whose
-- prompt is active), never to "whatever was pending".
CREATE TABLE IF NOT EXISTS intake_drafts (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tg_id             BIGINT NOT NULL,
    chat_id           BIGINT NOT NULL,
    source_message_id BIGINT NOT NULL,
    prompt_message_id BIGINT,
    file_id           TEXT NOT NULL,
    file_unique_id    TEXT NOT NULL,
    size_bytes        BIGINT NOT NULL DEFAULT 0,
    filename          TEXT,
    mime              TEXT,
    duration_s        DOUBLE PRECISION,
    width             INTEGER,
    height            INTEGER,
    status            TEXT NOT NULL DEFAULT 'waiting',
    -- waiting (behind another prompt) | awaiting_name | submitted | cancelled | expired
    job_id            UUID,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Telegram may redeliver the same update: one draft per source message.
CREATE UNIQUE INDEX IF NOT EXISTS uq_draft_source
    ON intake_drafts (chat_id, source_message_id);
-- At most one active filename prompt per user.
CREATE UNIQUE INDEX IF NOT EXISTS uq_draft_active_prompt
    ON intake_drafts (tg_id) WHERE status = 'awaiting_name';
CREATE INDEX IF NOT EXISTS idx_draft_user_open
    ON intake_drafts (tg_id, created_at) WHERE status IN ('waiting', 'awaiting_name');

-- Owner <-> user support conversations (explicit contact-management flow only).
CREATE TABLE IF NOT EXISTS support_messages (
    id              BIGSERIAL PRIMARY KEY,
    user_tg_id      BIGINT NOT NULL,
    direction       TEXT NOT NULL,            -- 'in' (user -> owner) | 'out' (owner -> user)
    owner_tg_id     BIGINT NOT NULL,
    user_message_id BIGINT,
    owner_message_id BIGINT,                  -- copy / header message in the owner chat
    header_message_id BIGINT,
    kind            TEXT,
    text_preview    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_support_user ON support_messages (user_tg_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_owner_msg ON support_messages (owner_tg_id, owner_message_id);
CREATE INDEX IF NOT EXISTS idx_support_header_msg ON support_messages (owner_tg_id, header_message_id);

-- Moderation history (explicit owner decisions only).
CREATE TABLE IF NOT EXISTS moderation_actions (
    id            BIGSERIAL PRIMARY KEY,
    job_id        UUID,
    target_tg_id  BIGINT NOT NULL,
    action        TEXT NOT NULL,              -- remove_and_ban | unban
    actor_tg_id   BIGINT,
    job_status_before TEXT,
    job_stage_before  TEXT,
    details       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_moderation_target ON moderation_actions (target_tg_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_moderation_job_action
    ON moderation_actions (job_id, action) WHERE job_id IS NOT NULL;

ALTER TABLE users ADD COLUMN IF NOT EXISTS banned_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS ban_reason TEXT;

-- ---------------------------------------------------------------------------
-- Single-profile migration (EDU480 v2).
-- Decision for jobs that exist at upgrade time:
--   * queued / deferred jobs that never reached Encore are converted to
--     EDU480 v2 (they have not consumed any encode time yet);
--   * jobs already running in Encore finish with the configuration they
--     started with (cancelling them would waste the work already done).
-- ---------------------------------------------------------------------------
UPDATE jobs SET status = 'queued', stage = 'queued'
WHERE status = 'deferred';

UPDATE jobs
SET profile = 'edu480', effective_profile = 'edu480', profile_version = 2,
    profile_params = NULL, updated_at = now()
WHERE status = 'queued' AND encore_job_id IS NULL
  AND (profile <> 'edu480' OR profile_version <> 2)
  AND NOT EXISTS (
      SELECT 1 FROM jobs o
      WHERE o.media_id = jobs.media_id AND o.id <> jobs.id
        AND o.profile = 'edu480' AND o.profile_version = 2
        AND o.status IN ('queued', 'processing'));

INSERT INTO profiles(key, encore_name, title, description, version, active)
VALUES ('edu480', 'edu480', 'EDU480',
        'Educational 480p: no-upscale Lanczos to 480p short side, fps cap, x264 CRF', 2, TRUE)
ON CONFLICT (key) DO UPDATE
SET version = 2, active = TRUE, title = 'EDU480',
    description = EXCLUDED.description;

UPDATE profiles SET active = FALSE WHERE key <> 'edu480';
