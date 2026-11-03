-- Multi-part archive support for outputs exceeding the Telegram upload limit.

ALTER TABLE archive_records
    ADD COLUMN IF NOT EXISTS part_index INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS part_total INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS split_of UUID REFERENCES archive_records(id);

DROP INDEX IF EXISTS uq_archive_src_profile;
CREATE UNIQUE INDEX uq_archive_src_profile_part
    ON archive_records (source_media_id, profile, profile_version, part_index)
    WHERE status IN ('active', 'no_gain');
