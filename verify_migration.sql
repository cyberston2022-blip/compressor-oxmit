SELECT (SELECT count(*) FROM media_assets WHERE is_derivative) AS derivatives,
       (SELECT count(*) FROM counters WHERE name IN ('cache_offers','cache_accepted','degraded_source_fallbacks')) AS new_counters,
       (SELECT count(*) FROM information_schema.columns WHERE table_name='jobs' AND column_name='source_degraded') AS degraded_col,
       (SELECT count(*) FROM information_schema.columns WHERE table_name='archive_records' AND column_name IN ('reuse_count','last_reused_at')) AS reuse_cols,
       (SELECT count(*) FROM pg_indexes WHERE indexname='idx_archive_source') AS idx,
       (SELECT count(*) FROM schema_migrations) AS migrations;
-- sanity: find_cached_versions query works on real data
SELECT ar.profile, count(*) AS parts, max(mo.width) AS max_w
FROM archive_records ar
JOIN media_assets ms ON ms.id = ar.source_media_id
LEFT JOIN media_assets mo ON mo.id = ar.output_media_id
WHERE ms.sha256 IN (SELECT sha256 FROM media_assets WHERE sha256 IS NOT NULL LIMIT 3)
  AND ar.status IN ('active','no_gain')
GROUP BY ar.profile ORDER BY 2 DESC LIMIT 5;
