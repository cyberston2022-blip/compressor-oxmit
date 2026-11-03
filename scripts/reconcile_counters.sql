-- NEW-001: manual counter reconciliation (the bot also runs this at startup).
-- Recomputes lifecycle counters from actual row state. Event counters
-- (requests_total, bytes_*, dedup_*, level_escalations,
-- archive_missing_detected) are intentionally left untouched.

UPDATE counters SET value = (SELECT count(*) FROM jobs
    WHERE status = 'completed' AND reuse_of IS NULL)
WHERE name = 'jobs_encoded';

UPDATE counters SET value = (SELECT count(*) FROM jobs WHERE status = 'failed')
WHERE name = 'jobs_failed';

UPDATE counters SET value = (SELECT count(*) FROM jobs WHERE status = 'cancelled')
WHERE name = 'jobs_cancelled';

UPDATE counters SET value = (SELECT count(*) FROM jobs
    WHERE is_no_gain AND status = 'completed' AND reuse_of IS NULL)
WHERE name = 'no_gain_events';

UPDATE counters SET value = (SELECT count(*) FROM jobs
    WHERE status = 'completed' AND archived IS FALSE AND NOT is_no_gain AND reuse_of IS NULL)
WHERE name = 'archive_blocked';

UPDATE counters SET value = (SELECT count(*) FROM deliveries WHERE status = 'ok')
WHERE name = 'deliveries_ok';

UPDATE counters SET value = (SELECT count(*) FROM deliveries WHERE status = 'failed')
WHERE name = 'deliveries_failed';
