-- Cache-reuse feature: derivative identity, reuse statistics, degraded-source
-- fallback. Sources keep is_derivative = FALSE; encode outputs stored as
-- media_assets are marked TRUE so the data model can distinguish original
-- uploads from compressed derivatives (same source identity, many versions).

ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS is_derivative BOOLEAN NOT NULL DEFAULT FALSE;

-- Backfill: anything referenced as an encode output is a derivative.
UPDATE media_assets m
SET is_derivative = TRUE
WHERE m.is_derivative = FALSE
  AND (
    m.id IN (SELECT output_media_id FROM archive_records WHERE output_media_id IS NOT NULL)
    OR m.id IN (SELECT output_media_id FROM jobs WHERE output_media_id IS NOT NULL)
  );

-- Reuse statistics per cached version: incremented on every cache-hit delivery.
ALTER TABLE archive_records ADD COLUMN IF NOT EXISTS reuse_count BIGINT NOT NULL DEFAULT 0;
ALTER TABLE archive_records ADD COLUMN IF NOT EXISTS last_reused_at TIMESTAMPTZ;

-- Cross-profile lookup of all cached versions of one source.
CREATE INDEX IF NOT EXISTS idx_archive_source ON archive_records (source_media_id);

-- Fallback encoding: when the original source file is gone, the job may be
-- served from the best archived derivative (never upscaling it).
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS source_degraded BOOLEAN NOT NULL DEFAULT FALSE;

INSERT INTO counters(name) VALUES
    ('cache_offers'), ('cache_accepted'), ('degraded_source_fallbacks')
ON CONFLICT (name) DO NOTHING;
