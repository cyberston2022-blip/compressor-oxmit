#!/usr/bin/env bash
set -e
for f in /opt/oxmit/bot/oxmit/migrations/*.sql; do
  docker exec -i oxmit-mig12-test psql -U oxmit -d oxmit -v ON_ERROR_STOP=1 -q < "$f" || { echo "FAILED: $f"; exit 1; }
done
echo "FRESH_001_012_OK"
docker exec oxmit-mig12-test psql -U oxmit -d oxmit -t -c \
  "SELECT count(*) FROM schema_migrations; SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
# restore the real dump on top of a SECOND container to test 011+012 over prod data
