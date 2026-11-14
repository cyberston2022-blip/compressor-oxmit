-- Fuzzy dedup layer: match sources by (size, normalized name, duration window)
-- when the exact SHA-256 does not match (re-muxed/re-uploaded copies).

ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS name_norm TEXT;

UPDATE media_assets SET name_norm = lower(filename)
WHERE name_norm IS NULL AND filename IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_media_fuzzy ON media_assets (size_bytes, name_norm);
