-- Migration 017: Audit Hardening, Pipeline Columns & Lifecycle Consistency

-- Ensure all lifecycle and metrics columns exist in jobs table
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS source_path TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS work_dir TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS current_fps DOUBLE PRECISION DEFAULT 0.0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS current_speed_factor DOUBLE PRECISION DEFAULT 0.0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS last_tele_update_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS last_tele_hash TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS last_reported_queue_pos INTEGER DEFAULT 0;

-- Custom per-user queue limit
ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_queue_limit INTEGER DEFAULT NULL;

-- High-performance indexes for Active-Aware Deficit Fair-Share Scheduling & Lock Contention
CREATE INDEX IF NOT EXISTS idx_jobs_active_user_load ON jobs (requester_tg_id) WHERE status = 'processing';
CREATE INDEX IF NOT EXISTS idx_jobs_status_stage ON jobs (status, stage);
CREATE INDEX IF NOT EXISTS idx_jobs_media_active ON jobs (media_id, profile, profile_version) WHERE status IN ('queued', 'processing');
