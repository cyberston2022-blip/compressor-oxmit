-- Administrator promotion is configuration-driven: set ADMIN_TELEGRAM_IDS in
-- .env (comma-separated numeric IDs). No hardcoded personal IDs in source
-- (SEC-2). This file previously inserted a fixed admin ID; deployments that
-- already applied it keep their rows, fresh deployments create none.

SELECT 1;
