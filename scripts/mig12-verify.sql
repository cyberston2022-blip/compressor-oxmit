SELECT (SELECT count(*) FROM schema_migrations) AS migrations,
       (SELECT count(*) FROM information_schema.tables WHERE table_schema='public') AS tables,
       (SELECT count(*) FROM information_schema.columns WHERE table_name='admin_settings') AS admin_settings_cols,
       (SELECT count(*) FROM information_schema.columns WHERE table_name='admin_permissions') AS admin_permissions_cols,
       (SELECT count(*) FROM information_schema.columns WHERE table_name='merge_sessions') AS merge_sessions_cols,
       (SELECT count(*) FROM information_schema.columns WHERE table_name='merge_items') AS merge_items_cols,
       (SELECT count(*) FROM information_schema.columns WHERE table_name='jobs' AND column_name IN ('personal_thumb_path','personal_caption','caption_mode','watermark_json','job_kind')) AS job_snapshot_cols;
