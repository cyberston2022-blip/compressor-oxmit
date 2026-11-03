# Troubleshooting

## Bot offline

```bash
docker compose ps                       # container states + health
docker compose logs --tail 200 bot
```

- `cannot reach local bot api server` → check `telegram-bot-api` container and
  `LOCAL_BOT_API_BASE`; the token must be logged out of cloud (one-time logOut).
- `401 Unauthorized` from Telegram → token revoked; update `BOT_TOKEN`.

## Jobs stuck queued

- Encore API down? `curl -u bot:$ENCRE_PASSWORD http://127.0.0.1:8080/actuator/health`
- Workers up? `docker compose ps encore-worker` — workers exit after draining
  the queue and are restarted by Docker; `RestartCount` rising is normal.
- Redis persistence intact? `docker compose logs redis`.

## Jobs failing

```bash
docker compose exec postgres psql -U oxmit -d oxmit -c \
  "SELECT id, error_category, left(error_message, 120) FROM jobs WHERE status='failed' ORDER BY completed_at DESC LIMIT 5;"
```

| category | meaning | action |
|---|---|---|
| validation | output failed ffprobe checks | inspect worker logs, maybe codec issue |
| ffmpeg | encore reported failure | see encore-worker logs |
| archive | upload to archive channel failed | bot still admin of channel? disk? |
| disk | disk guard tripped | free space or raise thresholds |
| source_unavailable | Telegram source vanished | user re-sends file |
| stuck | no progress for STUCK_MINUTES | check worker CPU/mem limits |

## Large uploads rejected

- Local Bot API upload cap = 2000MB (`MAX_UPLOAD_MB`): outputs above the cap
  are kept on disk and reported; sources are downloads (unlimited).
- `getFile` path unreadable → the `botapi_data` volume must be mounted at the
  same path in both `telegram-bot-api` and `bot` containers.

## Archive channel problems

- `/health` shows `archive: not configured` → `/setarchive -100…` or forward a
  channel message to the bot.
- Uploads fail with "not admin" → re-add bot as admin with *Post Messages*.

## Database maintenance

```bash
docker compose exec postgres psql -U oxmit -d oxmit -c "VACUUM ANALYZE;"
docker compose exec postgres psql -U oxmit -d oxmit -c "SELECT * FROM counters ORDER BY name;"
```

## Emergency: reset queues (keep data)

```bash
docker compose exec redis redis-cli FLUSHDB   # drops Encore job queue only
docker compose exec postgres psql -U oxmit -d oxmit -c \
  "UPDATE jobs SET status='failed', error_category='reset' WHERE status IN ('queued','processing');"
```
