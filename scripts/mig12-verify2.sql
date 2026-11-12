SELECT (SELECT count(*) FROM information_schema.columns WHERE table_name='admin_settings') AS admin_settings_cols,
       (SELECT count(*) FROM information_schema.columns WHERE table_name='admin_permissions') AS admin_permissions_cols,
       (SELECT count(*) FROM information_schema.columns WHERE table_name='merge_sessions') AS merge_sessions_cols,
       (SELECT count(*) FROM information_schema.columns WHERE table_name='merge_items') AS merge_items_cols,
       (SELECT count(*) FROM information_schema.columns WHERE table_name='jobs' AND column_name IN ('personal_thumb_path','personal_caption','caption_mode','watermark_json','job_kind')) AS job_snapshot_cols;
-- atomic seq ordering: simulate two locked adds
INSERT INTO users(tg_id) VALUES (42);
INSERT INTO merge_sessions(tg_id, chat_id) VALUES (42, 42);
UPDATE merge_sessions SET item_count = item_count + 1 WHERE tg_id = 42 AND status='collecting' RETURNING item_count;
UPDATE merge_sessions SET item_count = item_count + 1 WHERE tg_id = 42 AND status='collecting' RETURNING item_count;
INSERT INTO merge_sessions(tg_id, chat_id) VALUES (42, 43);
