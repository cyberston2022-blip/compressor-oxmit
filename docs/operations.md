# Operations Runbook

## Service layout (docker compose project `oxmit`)

| Service | Image | Purpose | Ports |
|---|---|---|---|
| redis | redis:8.6-alpine | Encore queues + job store (AOF) | internal |
| postgres | postgres:17-alpine | app database | internal |
| encore-web | ghcr.io/svt/encore-web:1.0.0 | REST API (basic auth, API-only) | 127.0.0.1:8080 |
| encore-worker | ghcr.io/svt/encore-worker:1.0.0 | transcodes one queue until empty, exits, restarts | internal |
| telegram-bot-api | built from tdlib pinned commit | local Bot API (--local) | internal |
| bot | oxmit/bot:local | aiogram bot + internal API | 127.0.0.1:8090 |

All inter-service traffic stays on the internal docker network. Only SSH is
publicly reachable; 8080/8090 are bound to 127.0.0.1 for diagnostics.

## Environment / secrets

- `/opt/oxmit/.env` (chmod 600) — all secrets. Never commit. Never log.
- Encore basic-auth credentials: `ENCRE_USER` / `ENCRE_PASSWORD`.
- Postgres: `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`.

## Common tasks

```bash
cd /opt/oxmit
docker compose ps
docker compose logs --tail 100 bot
docker compose logs --tail 100 encore-worker
docker compose logs --tail 100 telegram-bot-api

# restart one service
docker compose restart bot

# update the deployment
docker compose pull && docker compose build bot && docker compose up -d

# run database migrations (automatic on bot start; to re-check)
docker compose exec bot python -c "import asyncio; from oxmit.db import Database; from oxmit.config import load_settings; \
  asyncio.run((lambda: (lambda d: (d.connect(), d.close()))(Database(load_settings().pg_dsn)) )())"
```

## Queue / job inspection

```bash
docker compose exec postgres psql -U oxmit -d oxmit -c \
  "SELECT status, count(*) FROM jobs GROUP BY status;"
docker compose exec postgres psql -U oxmit -d oxmit -c \
  "SELECT id, status, profile, progress, retries, error_category FROM jobs ORDER BY enqueued_at DESC LIMIT 10;"
curl -s -u bot:$ENCRE_PASSWORD http://127.0.0.1:8080/queueCount
curl -s -u bot:$ENCRE_PASSWORD http://127.0.0.1:8080/actuator/health
```

## Disk management

- Media dirs: `/opt/oxmit/media/{incoming,out,tmp,test}` — cleaned automatically
  (retention `TMP_RETENTION_HOURS=24`, sweep every 10 min; active jobs protected).
- Admission rejects jobs below `DISK_MIN_FREE_GB=40`, auto-pauses below 20GB and
  auto-resumes when space recovers.
- `du -sh /opt/oxmit/media/*` to inspect.

## Bot restart recovery

Queued jobs without an Encore job are re-submitted on startup; running jobs are
reconciled against Encore (poll every 10s + progress callbacks). Jobs stuck
without progress for `STUCK_MINUTES` are cancelled and retried (`JOB_RETRIES`).

## Upgrading Encore

```bash
# pin a new tag in docker-compose.yml (encore-web, encore-worker), then:
docker compose pull && docker compose up -d
```

Read upstream release notes first: Redis data model changed between 0.2.x and
1.0.0 — never mix versions against one Redis; this deployment pins 1.0.0 with
prefix isolation available via `ENCORE_SETTINGS_REDIS_PREFIX` if ever needed.

## Telegram notes

- The bot token is logged in ONLY on the local Bot API server (cloud `logOut`
  executed once at setup). Do not call cloud API with this token afterwards.
- Local server caps uploads at 2000MB (documented); downloads are unlimited.
- The archive channel must keep the bot as admin with post permission.
