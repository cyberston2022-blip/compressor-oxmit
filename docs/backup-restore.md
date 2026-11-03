# Backup & Restore

## What is backed up

- PostgreSQL (all tables: users, media_assets, jobs, archive_records,
  deliveries, counters, app_config) — the authoritative metadata
- `deploy/` config + `docker-compose.yml` (`.env` intentionally excluded from
  archives; store a copy in your password manager)

Completed videos themselves are NOT stored on the VPS long-term: the canonical
copy lives in the private archive channel; local temp files expire after 24h.

## Automated backup

```bash
sudo tee /etc/cron.d/oxmit-backup >/dev/null <<'EOF'
0 3 * * * ubuntu /opt/oxmit/scripts/backup.sh >> /opt/oxmit/backups/backup.log 2>&1
EOF
sudo chmod 644 /etc/cron.d/oxmit-backup
```

Backups land in `/opt/oxmit/backups/`, 14-day retention.

## Restore procedure

```bash
cd /opt/oxmit
docker compose down bot            # stop writers
gunzip -c backups/oxmit-db-YYYYMMDD-HHMMSS.sql.gz \
  | docker compose exec -T postgres psql -U oxmit -d oxmit
docker compose up -d bot
```

Full rebuild from backup on a fresh server:

1. Install Docker, copy the project + `.env` + latest `*.sql.gz`.
2. `docker compose up -d redis postgres encore-web encore-worker telegram-bot-api`
3. Restore the dump (above), then `docker compose up -d bot`.
4. Re-add the bot to the archive channel if the bot/DB identity changed.

Archive records reference channel+message IDs — those survive as long as the
Telegram channel exists; delivery falls back gracefully when a message is gone
(record marked `missing`, counted, admin notified).
