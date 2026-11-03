-- Oxmit initial schema: users, media assets, profiles, jobs, archives, deliveries.

CREATE TABLE users (
    tg_id           BIGINT PRIMARY KEY,
    first_name      TEXT,
    username        TEXT,
    is_admin        BOOLEAN NOT NULL DEFAULT FALSE,
    is_blocked      BOOLEAN NOT NULL DEFAULT FALSE,
    default_profile TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    total_requests  BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE media_assets (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sha256           TEXT,
    size_bytes       BIGINT NOT NULL,
    filename         TEXT,
    duration_s       DOUBLE PRECISION,
    width            INTEGER,
    height           INTEGER,
    fps              DOUBLE PRECISION,
    vcodec           TEXT,
    acodec           TEXT,
    audio_channels   INTEGER,
    container        TEXT,
    bitrate          BIGINT,
    tg_file_id       TEXT,
    tg_file_unique_id TEXT,
    probe            JSONB,
    phash            JSONB,
    fingerprinted    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_media_sha ON media_assets (sha256);
CREATE INDEX idx_media_duration ON media_assets (duration_s);
CREATE INDEX idx_media_fingerprinted ON media_assets (fingerprinted) WHERE fingerprinted;

CREATE TABLE profiles (
    key             TEXT PRIMARY KEY,
    encore_name     TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    version         INTEGER NOT NULL DEFAULT 1,
    active          BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE jobs (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requester_tg_id    BIGINT NOT NULL,
    media_id           UUID REFERENCES media_assets(id),
    profile            TEXT NOT NULL,
    profile_version    INTEGER NOT NULL DEFAULT 1,
    effective_profile  TEXT,
    status             TEXT NOT NULL DEFAULT 'queued',
    -- queued | processing | completed | failed | cancelled
    priority           INTEGER NOT NULL DEFAULT 50,
    encore_job_id      TEXT,
    progress           INTEGER NOT NULL DEFAULT 0,
    progress_changed_at TIMESTAMPTZ,
    retries            INTEGER NOT NULL DEFAULT 0,
    error_category     TEXT,
    error_message      TEXT,
    source_size        BIGINT,
    output_size        BIGINT,
    output_media_id    UUID REFERENCES media_assets(id),
    reuse_of           UUID,
    is_no_gain         BOOLEAN NOT NULL DEFAULT FALSE,
    archived           BOOLEAN,
    source_path        TEXT,
    source_message_id  BIGINT,
    status_message_id  BIGINT,
    enqueued_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at         TIMESTAMPTZ,
    completed_at       TIMESTAMPTZ,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Cross-process in-flight dedup: one active encode per (source, profile).
CREATE UNIQUE INDEX uq_active_media_profile
    ON jobs (media_id, profile, profile_version)
    WHERE status IN ('queued', 'processing');
CREATE INDEX idx_jobs_status ON jobs (status);
CREATE INDEX idx_jobs_user ON jobs (requester_tg_id, enqueued_at DESC);

CREATE TABLE job_requesters (
    job_id            UUID REFERENCES jobs(id),
    tg_id             BIGINT NOT NULL,
    chat_id           BIGINT NOT NULL,
    source_message_id BIGINT,
    status_message_id BIGINT,
    delivered         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (job_id, tg_id)
);
CREATE INDEX idx_job_req_delivery ON job_requesters (job_id) WHERE delivered = FALSE;

CREATE TABLE archive_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_media_id UUID REFERENCES media_assets(id),
    output_media_id UUID REFERENCES media_assets(id),
    profile         TEXT NOT NULL,
    profile_version INTEGER NOT NULL DEFAULT 1,
    channel_id      BIGINT NOT NULL,
    message_id      BIGINT NOT NULL DEFAULT 0,
    file_unique_id  TEXT,
    permalink       TEXT,
    status          TEXT NOT NULL DEFAULT 'active',
    -- active | no_gain | missing | blocked
    sha256          TEXT,
    validated       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- One reusable result per (source, profile, version).
CREATE UNIQUE INDEX uq_archive_src_profile
    ON archive_records (source_media_id, profile, profile_version)
    WHERE status IN ('active', 'no_gain');

CREATE TABLE deliveries (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    archive_id  UUID REFERENCES archive_records(id),
    job_id      UUID REFERENCES jobs(id),
    tg_id       BIGINT NOT NULL,
    chat_id     BIGINT NOT NULL,
    message_id  BIGINT,
    method      TEXT,
    status      TEXT NOT NULL,
    error       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_deliveries_job ON deliveries (job_id);

CREATE TABLE app_config (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE counters (
    name  TEXT PRIMARY KEY,
    value BIGINT NOT NULL DEFAULT 0
);

INSERT INTO counters(name) VALUES
    ('requests_total'), ('jobs_encoded'), ('jobs_failed'), ('jobs_cancelled'),
    ('dedup_exact_reuse'), ('dedup_inflight_joined'), ('dedup_similarity_reuse'),
    ('no_gain_events'), ('bytes_in'), ('bytes_out'), ('bytes_saved'),
    ('deliveries_ok'), ('deliveries_failed'), ('archive_blocked'), ('archive_missing_detected');

INSERT INTO profiles(key, encore_name, title, description, version) VALUES
    ('balanced', 'balanced', 'Balanced', 'H.264 CRF22 - good quality/size/speed balance', 1),
    ('highq',    'highq',    'High quality', 'H.264 CRF19 - keeps visual quality', 1),
    ('small',    'small',    'Smaller file', 'HEVC/H.265 CRF27 - smaller, slower', 1),
    ('maxcomp',  'maxcomp',  'Max compression', 'HEVC/H.265 CRF30 medium - smallest, slowest', 1),
    ('tgcompat', 'tgcompat', 'Telegram compat', 'H.264 High + AAC + faststart', 1),
    ('r1080',    'r1080',    '1080p', 'Scale to 1080p (never upscales)', 1),
    ('r720',     'r720',     '720p', 'Scale to 720p (never upscales)', 1),
    ('r480',     'r480',     '480p', 'Scale to 480p (never upscales)', 1);
