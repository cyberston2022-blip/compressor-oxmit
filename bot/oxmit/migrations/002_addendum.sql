-- Addendum features: user preferences, job stages, per-job input params, custom profile.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'fa',
    ADD COLUMN IF NOT EXISTS ask_each_time BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS notify_done BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS show_meta BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS delivery_style TEXT NOT NULL DEFAULT 'video',
    ADD COLUMN IF NOT EXISTS thumbnail_file_id TEXT;

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS stage TEXT,
    ADD COLUMN IF NOT EXISTS input_params JSONB,
    ADD COLUMN IF NOT EXISTS profile_params JSONB;

INSERT INTO profiles(key, encore_name, title, description, version) VALUES
    ('custom', 'custom', 'Custom target size', 'Bitrate computed from requested target size', 1)
ON CONFLICT (key) DO NOTHING;
