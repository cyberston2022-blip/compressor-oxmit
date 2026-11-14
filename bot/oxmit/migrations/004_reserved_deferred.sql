-- Disk reservation accounting + deferred admission (pattern: ArgonsEncoder,
-- reimplemented independently on PostgreSQL-authoritative state).

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS reserved_bytes BIGINT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_jobs_deferred ON jobs (enqueued_at) WHERE status = 'deferred';
