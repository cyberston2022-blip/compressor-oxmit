SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;
SELECT count(*) AS migration_rows FROM (SELECT 1) x WHERE EXISTS (SELECT 1 FROM pg_tables WHERE tablename='schema_migrations');
