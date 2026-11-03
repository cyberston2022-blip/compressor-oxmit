-- Per-user tiers and limits: VIP flag + per-user overrides (NULL = tier default).

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_vip BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS max_source_gb INTEGER,
    ADD COLUMN IF NOT EXISTS max_duration_min INTEGER,
    ADD COLUMN IF NOT EXISTS daily_quota_gb INTEGER;
