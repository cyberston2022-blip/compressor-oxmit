# Oxmit — Telegram Video Compression Platform (SVT Encore)

Production Telegram bot that compresses user videos with the official
[SVT Encore](https://github.com/svt/encore) transcoding engine (v1.0.0),
deduplicates sources, archives every result in a private Telegram channel and
delivers results back to users.

## Architecture

```
Telegram users
  → bot (aiogram 3, long polling)
      → telegram-bot-api (official tdlib local server, --local)
      → PostgreSQL (users, media, jobs, archives, deliveries, counters)
      → Encore REST API (encore-web, basic auth, API-only mode)
          → Redis 8 (queues + job store, AOF persistence)
          → encore-worker pool (bounded replicas, FFmpeg)
      → shared /media volume (incoming + output, no S3 needed)
  → private archive channel (canonical storage)
  → delivery: forward → copy → file_id chain
```

Components:
- `bot/` — Python bot application (aiogram 3 + asyncpg + httpx + aiohttp + Pillow)
- `deploy/encore/profiles/` — Encore transcoding profiles (YAML, official format)
- `deploy/telegram-bot-api/` — Dockerfile for the official tdlib Local Bot API server
- `scripts/` — backup, load/functional tests
- `docs/` — operations, profiles, backup/restore, troubleshooting

## Requirements

- Docker Engine + Compose plugin
- Telegram bot token, `api_id`/`api_hash` (for the local Bot API server)
- A private channel where the bot is admin with post permission
- ~620GB SSD, 8 vCPU, 16GB RAM (tested baseline)

## Deploy

```bash
sudo mkdir -p /opt/oxmit && sudo chown $USER /opt/oxmit
cp -r oxmit /opt/oxmit && cd /opt/oxmit
cp .env.example .env && chmod 600 .env   # fill real values
mkdir -p media/incoming media/out media/tmp media/test
docker compose build          # builds telegram-bot-api + bot images
docker compose up -d
```

Then:
1. Add the bot as **admin** (post messages) to your private archive channel.
2. Set the archive channel: `/setarchive -100XXXXXXXXXX` **or** forward any
   channel message to the bot **or** post anything in the channel (auto-discovery).
3. First user to `/start` becomes the admin when `ADMIN_TELEGRAM_IDS` is empty.

### Local Bot API migration (one-time, required)

The bot only works through the local Bot API server (large files). Before the
first bot start, log the bot out of the cloud Bot API:

```bash
curl "https://api.telegram.org/bot<token>/logOut"
docker compose up -d
```

After `logOut`, the token only works against the local server — this is the
documented, expected behaviour. Recovery = keep the `telegram-bot-api`
container running (its session persists in the `botapi_data` volume).

## Daily operations

```bash
docker compose ps                        # service health
docker compose logs -f bot               # bot logs (JSON lines)
docker compose logs -f encore-worker     # transcode logs
docker compose restart bot               # restart bot only
docker compose pull && docker compose up -d   # update upstream images
./scripts/backup.sh                      # manual DB backup
```

See `docs/operations.md` for the full runbook, `docs/backup-restore.md`,
`docs/troubleshooting.md`, `docs/profiles.md`.

## Bot commands

User: `/start` — that is all. Users send a video, get an info card
(name, size, duration, resolution), press **🎬 فشرده‌سازی** and send a number
**1–20** (compression level). The level maps to x264 CRF 18–28: the encoder is
content-adaptive, so the achieved size reduction depends on the video (level
20 ≈ up to ~60% smaller on typical content) while the CRF ceiling keeps the
result watchable — visibly compressed, never mushy. Progress card includes a
cancel button. If the encode yields no real size benefit (already-compressed
source), the original is delivered with an explanation (no-gain policy).

Admin: `/admin` (button panel: stats, health, pause, queue, errors, cleanup,
ban, broadcast, user management, tier limits, global thumbnail, live monitor),
`/setarchive <id>`, `/retry <id>`.

Admin extras:
- **User management** (`👤 کاربر`): VIP toggle, ban/unban, per-user custom
  limits (size / duration / daily quota).
- **Tier limits** (`🎚 محدودیت‌ها`): edit `normal`/`vip` tiers live
  (`tier.key=value`, keys: `max_source_gb`, `max_duration_min`,
  `daily_quota_gb`, `max_active`, `max_per_hour`). VIP jobs also get queue
  priority (60 vs 50).
- **Global thumbnail** (`🖼 تامبنیل`): send a photo; it is applied to every
  freshly-uploaded delivered/archived video.
- **Live monitor** (`📡 مانیتور`): auto-refreshing in-chat task list with
  progress bars, per-user info and elapsed time.
- **Forced membership** (`🔒 عضویت اجباری`): set a channel (`@name`, `-100id`
  or a t.me link, optionally `-100id | invite-link`); users must join it
  before `/start` or video intake works (`off` disables). Admins are exempt;
  the bot verifies the channel at set time (it must be an admin there) and
  membership checks are cached for 5 minutes.

## Web monitoring panel

`http://127.0.0.1:8090/panel` (localhost-only like the rest of the stack).
Login token: `ADMIN_PANEL_TOKEN` from `.env` (empty = panel disabled). Access
from your machine via SSH tunnel:

```bash
ssh -L 8090:127.0.0.1:8090 ubuntu@<server>
# then open http://127.0.0.1:8090/panel
```

Read-only dashboard, fully offline (no CDN dependencies): a **live badge**
(real WebSocket push every 3s with automatic polling fallback), colored stat
cards (active jobs / RAM / CPU / disk with load and core info), a
**processing trend** area chart with 24h/7d/30d tabs and totals, **live task
rows** (filename, size, user, VIP badge, big percent, animated striped bar,
stage, elapsed time, encoding speed), and a numbered **users** list with VIP
and ban status.

## Limits (defaults, all configurable)

- Source: up to 4GB via local Bot API (downloads unlimited); output delivery
  up to 2000MB, larger outputs are split into playable parts
- **Tiers** (editable in `/admin`): normal = 4GB / 2h / 5GB daily quota /
  2 active / 10 per hour; VIP = 4GB / 6h / 20GB daily / 4 active / 30 per hour
  (seed values, per-user overrides supported)
- 50 queued jobs globally; disk guards: reject below 40GB free, auto-pause
  below 20GB

## Duplicate detection

1. **Exact** — SHA-256 of source + profile + version → reuse archived result
2. **Fuzzy** — (size + normalized filename + duration ±2s) match for level and
   custom (percent) requests → deliver the previous compressed result of the
   same video, even if the bytes differ (re-muxed/re-uploaded copies)
3. **In-flight** — same source/profile while queued/running → join the job
   (Postgres advisory lock + partial unique index, cross-process safe)
4. **Similar** — perceptual frame hashes (8×8 ahash, 8 frames) + duration
   window, conservative thresholds, only against archived results

## Testing

```bash
python3 scripts/loadtest.py --token <INTERNAL_TEST_TOKEN> --mode pipeline
python3 scripts/loadtest.py --token <INTERNAL_TEST_TOKEN> --mode dedup
python3 scripts/loadtest.py --token <INTERNAL_TEST_TOKEN> --mode burst --n 4
```

## License / attribution

- SVT Encore: EUPL-1.2-or-later — used unmodified as the transcoding engine
- tdlib/telegram-bot-api: built from official source (pinned commit)
- This repository: application glue only
