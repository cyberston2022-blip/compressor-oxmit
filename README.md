# Oxmit: Telegram Educational Video Compression

Oxmit is a production Telegram bot that compresses educational videos (lectures, classroom recordings, slides, whiteboards and screen recordings). The goal is a much smaller file in which the text stays readable and speech stays clear.

Encoding runs on the official [SVT Encore](https://github.com/svt/encore) engine (v1.0.0, FFmpeg/x264). Large files go through the official Telegram Local Bot API server. Every result is archived in a private Telegram channel and reused instead of being encoded again.

> Persian: کاربر ویدیو را می‌فرستد، نام فایل خروجی را می‌نویسد و ویدیو بدون دانلود در صف پایدار ثبت می‌شود. فقط وقتی نوبتش برسد دانلود و با پروفایل واحد **EDU480** فشرده می‌شود و نتیجه با نام دلخواه تحویل داده می‌شود. مالک از طریق داشبورد وب و کانال خصوصی همه‌چیز را می‌بیند و می‌تواند محتوای نامناسب را حذف و کاربر را مسدود کند.

---

## Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Job lifecycle](#job-lifecycle)
4. [The EDU480 profile](#the-edu480-profile)
5. [Requirements](#requirements)
6. [Fresh installation](#fresh-installation)
7. [Upgrading an existing deployment](#upgrading-an-existing-deployment)
8. [Configuration reference](#configuration-reference)
9. [Using the bot (users)](#using-the-bot-users)
10. [Owner and administrator guide](#owner-and-administrator-guide)
11. [Web dashboard](#web-dashboard)
12. [Duplicate detection and reuse](#duplicate-detection-and-reuse)
13. [Limits, fairness and disk safety](#limits-fairness-and-disk-safety)
14. [Operations](#operations)
15. [Testing and benchmarking](#testing-and-benchmarking)
16. [Project structure](#project-structure)
17. [Troubleshooting](#troubleshooting)
18. [Further documentation](#further-documentation)
19. [License and attribution](#license-and-attribution)

---

## Features

**Processing**
- **Metadata-first, just-in-time queue.** Submitting a video creates a database row only. The video is downloaded only when a worker claims the job, so waiting jobs use no disk.
- **Persistent queue of 5000+ jobs.** It survives restarts. Claims are atomic (`FOR UPDATE SKIP LOCKED`) and ownership is tracked with leases and heartbeats.
- **Fair FIFO scheduling.** A user who already has a running job is scheduled behind users who have none.
- **One compression profile, EDU480.** It keeps text legible and speech clear, never upscales, and caps the frame rate. Sources that already comply are remuxed in seconds instead of re-encoded.
- **No duplicate work.** Known files and the bot's own outputs are recognised before download. Exact duplicates are recognised by SHA-256 before encoding. Concurrent identical submissions share one job.
- **Uploads are resilient.** A failed upload is retried with backoff and never triggers a second encode.
- **Disk hygiene.** Sources are staged with a symlink instead of a copy. Local Bot API sources are deleted after use. Temporary files are cleaned per job. Disk space is checked before each download.

**Users**
- The bot asks for the **output file name** right after a video is sent. Persian and English are accepted, any typed extension is ignored, and the result is always `.mp4`.
- A live **queue card** shows position, jobs ahead, active workers and an ETA range based on measured throughput.
- Live **stage cards** follow the real stages: download, analysis, duplicate check, encode (real %), validation, upload.
- **📨 Contact management.** A message sent through it reaches the owner only, and the owner replies through the bot.

**Owner and administrators**
- **Private activity channel.** One record per job identifies the requester and carries a **"Remove video and ban user"** action.
- **Telegram panels.** `/admin` for operations and `/owner` for full control with granular per-admin permissions.
- **Web dashboard** (`/panel`). Shows active jobs, the queue, completed, failed and cancelled jobs, users, moderation history and system health, with search and filters.
- **Mandatory channel membership.** Only the owner can manage it unless the owner explicitly grants the permission to an admin.

---

## Architecture

```
Telegram users
   │
   ▼
bot  (Python 3.12, aiogram 3, asyncpg, aiohttp)
   ├── telegram-bot-api   official tdlib Local Bot API (--local: big files, local paths)
   ├── PostgreSQL 17      users, media, jobs (the queue), archive, deliveries, audit, moderation
   ├── Encore REST API    encore-web (API-only, basic auth)
   │      └── Redis 8     Encore's own job store (holds at most ENCODE_SLOTS jobs)
   │      └── encore-worker × N   FFmpeg/x264 encoders (CPU quota tuned live by the bot)
   ├── shared /media      incoming (symlinks) · out (results) · tmp
   ├── private archive channel   canonical storage of every result + per-job activity record
   └── web panel :8081 (published as :8090)  + internal API :8080
```

| Component | Role |
|---|---|
| `bot/` | Application: intake, queue and dispatcher, pipeline, delivery, panels, dashboard |
| `deploy/encore/profiles/` | Encore profiles (YAML, SpEL-templated per job). `edu480.yml` is the active one |
| `deploy/telegram-bot-api/` | Dockerfile for the official Local Bot API server (pinned commit) |
| `deploy/wrapper/ffmpeg` | Static FFmpeg 7.0.2 override for the Encore workers (tolerates damaged sources) |
| `scripts/` | Backup, load test, EDU480 benchmark, SQL maintenance helpers |
| `reports/`, `docs/` | Audits, benchmarks, runbooks |

The **database, not Encore's Redis queue, is the real queue.** The bot hands Encore only as many jobs as there are encode slots.

---

## Job lifecycle

```
video received ─► metadata validation (size, duration, mime; NO download)
              ─► name prompt (persistent draft) ─► name normalized
              ─► job row QUEUED + activity record in the private channel
                    ├ known Telegram file / own output?  ─► deliver archived result (no download)
                    └ same file already queued/running?  ─► join that job
dispatcher (every 5 s and on every event; slot free + disk OK):
              ─► RESERVED ─► DOWNLOADING (Local Bot API getFile)
              ─► PROBING (ffprobe) ─► CHECKING (SHA-256: exact duplicate / own output)
              ─► compliant source? REMUX : ENCODING (EDU480 on an Encore worker)
encode done   ─► slot freed (next download starts) ─► VALIDATING
              ─► UPLOADING to archive (file://, retried, never re-encoded)
              ─► DELIVERING (copy_message, no "forwarded from") ─► COMPLETED
              ─► temp files + Local Bot API source removed
```

| `jobs.status` | `jobs.stage` values |
|---|---|
| `queued` | `queued` |
| `processing` | `reserved`, `downloading`, `probing`, `checking`, `encoding`, `validating`, `uploading`, `upload_retry` |
| `completed` / `failed` / `cancelled` | the same name |

Every transition is a conditional `UPDATE … WHERE status IN (…)`. A job can never be claimed twice, cancelled and completed at the same time, or restarted after cancellation.

**Recovery after a restart:**
- Jobs that were downloading or probing go back to `queued`. An already-downloaded source is reused.
- Jobs already in Encore are reconciled by the poller.
- Finished encodes resume their upload from the existing output.

---

## The EDU480 profile

EDU480 is the **only** active compression profile (profile version 2). The geometry and fps filters are computed per job from the real ffprobe result (`bot/oxmit/edu480.py`) and passed to Encore as `profileParams`. That way the YAML never guesses dimensions.

| Setting | Value (env override) |
|---|---|
| Codec | H.264 (libx264), yuv420p, MP4 with `+faststart` |
| Resolution | **Short side 480**, Lanczos, aspect ratio preserved, even dimensions, **never upscaled** (1920×1080 → 854×480, portrait 1080×1920 → 480×854, 4:3 → 640×480) |
| Frame rate | Capped at 30 fps (`EDU480_MAX_FPS`) |
| Rate control | CRF 25 (`EDU480_CRF`), preset `veryfast` (`EDU480_PRESET`), aq-mode 3, rc-lookahead 40 |
| Audio | AAC 64 kbit/s (`EDU480_AUDIO_KBPS`) |
| Skip encoding | Short side ≤480, H.264, yuv420p, AAC or no audio, within the fps cap, video bitrate ≤ `EDU480_COMPLIANT_KBPS` (700) → remux only |
| Threads | `FFMPEG_THREADS_SINGLE` / `FFMPEG_THREADS_MULTI` per job. The worker CPU quota is tuned live (7 cores for one job, 3.2 each for two) |

If an encode fails because the source is damaged, the job is retried on EDU480 with `+genpts+discardcorrupt`, then with async audio resampling. It never falls back to a different profile.

Measure before changing these values. Run `scripts/bench_edu480.py` on real samples (see [Testing and benchmarking](#testing-and-benchmarking)).

---

## Requirements

- Docker Engine with the Compose plugin
- A Telegram bot token, plus `api_id` / `api_hash` (from <https://my.telegram.org>) for the Local Bot API server
- A **private channel** where the bot is an administrator with post rights (archive and activity records)
- Tested baseline: 8 vCPU, 16 GB RAM, ~620 GB SSD (Ubuntu 24.04)

---

## Fresh installation

```bash
sudo mkdir -p /opt/oxmit && sudo chown "$USER" /opt/oxmit
git clone https://github.com/Abolfazlhadadian/compressor-oxmit /opt/oxmit
cd /opt/oxmit
cp .env.example .env && chmod 600 .env       # fill in real values (see below)
mkdir -p media/incoming media/out media/tmp media/test
```

**One-time Local Bot API migration.** The bot works only through the local server. Log the token out of the cloud Bot API before the first start:

```bash
curl "https://api.telegram.org/bot<token>/logOut"
```

```bash
docker compose build          # telegram-bot-api + bot images
docker compose up -d
```

Then:
1. Set `OWNER_TELEGRAM_ID` in `.env`. That account is the owner, the only recipient of support messages, and the only identity that may moderate.
2. Set the archive channel. Use one of:
   - `/setarchive -100XXXXXXXXXX`
   - forward any message from the channel to the bot
   - post in the channel and confirm the proposal the bot sends you
3. Optionally set `LOG_CHANNEL_ID` to use a separate private activity/moderation channel. The default is the archive channel.
4. Send `/start`. With `ADMIN_TELEGRAM_IDS` empty and `OWNER_CLAIM=true`, the first user becomes the admin.

Migrations in `bot/oxmit/migrations/` are applied automatically each time the bot starts.

---

## Upgrading an existing deployment

```bash
cd /opt/oxmit
./scripts/backup.sh                          # always back up the DB first
git pull
# merge any new keys from .env.example into .env
docker compose build bot
docker compose up -d                         # recreates changed services
```

- Recreate `encore-worker` and `telegram-bot-api` only when no encode is running: they carry mounts the bot relies on. The `/media` read-only mount on the API server is used for `file://` uploads, and the `botapi_data` mount on the workers for symlink staging.
- **Upgrading to v3 (migration 015)** does the following:
  - converts queued jobs that never reached Encore to EDU480 v2;
  - lets jobs already encoding finish with their original settings;
  - deactivates every other profile.

  Details: [`reports/architecture-v3/README.md`](reports/architecture-v3/README.md).

---

## Configuration reference

All settings come from `.env` (template: [`.env.example`](.env.example)). The bot refuses to start on an invalid configuration and lists every problem it found. The main keys:

**Telegram and identity**

| Key | Meaning |
|---|---|
| `BOT_TOKEN`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | Bot credentials and Local Bot API credentials |
| `OWNER_TELEGRAM_ID` | **Owner**: support recipient, moderation, owner panel |
| `ADMIN_TELEGRAM_IDS` | Extra admins (comma-separated). Admins can also be promoted in `/owner` |
| `ARCHIVE_CHANNEL_ID` | Private archive channel (or set it at runtime) |
| `LOG_CHANNEL_ID` | Private activity/moderation channel (default: archive channel) |
| `LOCAL_BOT_API_BASE`, `MAX_UPLOAD_MB` | Local Bot API URL, upload limit (2000) |

**Queue and dispatcher**

| Key | Default | Meaning |
|---|---|---|
| `MAX_QUEUED_JOBS` | 5000 | Capacity of the persistent queue (job records, not files) |
| `WORKER_REPLICAS` / `WORKER_CONTAINER_NAMES` | 2 | Encore worker count and container names (must match compose) |
| `ENCODE_SLOTS` | 0 (= replicas) | Jobs between claim and end of encode |
| `PREFETCH_JOBS` | 0 | Extra jobs downloaded ahead of a free encoder (0 = strict just-in-time) |
| `LEASE_MINUTES` | 20 | Ownership lease. Expired pre-encode jobs are requeued |
| `UPLOAD_RETRIES` | 5 | Archive upload retries with backoff (never re-encodes) |
| `JOB_RETRIES`, `STUCK_MINUTES` | 2, 90 | Transient-failure retries, stuck-encode watchdog |
| `PROGRESS_EDIT_SECONDS` | 4 | Minimum interval between edits of one status message |
| `NAMING_TIMEOUT_MIN` | 30 | Unanswered name prompts expire after this long |
| `SUPPORT_SESSION_MIN` | 10 | How long a contact-management session stays open |

**Per-user limits.** These are the tier defaults; they become editable in `/admin` → limits after the first start.

| Key | Normal / VIP | Meaning |
|---|---|---|
| `MAX_PENDING_PER_USER` / `VIP_MAX_PENDING_PER_USER` | 10 / 30 | Queued plus running jobs per user |
| `MAX_ACTIVE_PER_USER` / `VIP_MAX_ACTIVE_PER_USER` | 1 / 2 | Concurrent processing (soft, used for fairness) |
| `MAX_JOBS_PER_HOUR_PER_USER` / `VIP_…` | 10 / 30 | Hourly submissions |
| `MAX_JOBS_PER_DAY` | 30 | Daily submissions |
| `NORMAL_MAX_SOURCE_GB` / `VIP_MAX_SOURCE_GB` | 4 / 4 | Source size limit |
| `NORMAL_MAX_DURATION_MIN` / `VIP_MAX_DURATION_MIN` | 360 / 720 | Duration limit (6 h / 12 h) |
| `NORMAL_DAILY_QUOTA_GB` / `VIP_DAILY_QUOTA_GB` | 5 / 20 | Source gigabytes per 24 h |

**Storage and disk**

| Key | Default | Meaning |
|---|---|---|
| `MEDIA_HOST_DIR` | `/opt/oxmit/media` | Shared media directory on the host |
| `ADMISSION_NEED_FACTOR`, `ADMISSION_FLOOR_GB` | 2.2, 5 | Disk needed before a job is downloaded = source × factor + floor |
| `DISK_MIN_FREE_GB`, `DISK_PAUSE_FREE_GB` | 40, 20 | Auto-resume / auto-pause thresholds |
| `WORKERS_READ_BOTAPI` | true (env example) | Symlink staging instead of copying sources |
| `BOTAPI_READS_MEDIA` | true (env example) | Upload results with `file://`; falls back to a normal upload |
| `DELETE_BOTAPI_SOURCE` | true | Delete Local Bot API sources once no active job needs them |
| `TMP_RETENTION_HOURS` | 24 | Retention for abandoned temp files (and kept outputs of failed uploads) |
| `SPLIT_UPLOAD`, `SPLIT_SAFETY` | true, 0.85 | Split outputs larger than the upload limit into playable parts |
| `NO_GAIN_THRESHOLD` | 0.98 | An output ≥ 98% of the source size counts as no gain, and the original is delivered |

**EDU480**: `EDU480_CRF`, `EDU480_PRESET`, `EDU480_MAX_FPS`, `EDU480_AUDIO_KBPS`, `EDU480_COMPLIANT_KBPS`. See [The EDU480 profile](#the-edu480-profile).

**Secrets and internal**

| Key | Meaning |
|---|---|
| `POSTGRES_*`, `ENCRE_PASSWORD` | Database and Encore credentials |
| `INTERNAL_SECRET` | Signs Encore completion callbacks |
| `ADMIN_PANEL_TOKEN` | Web panel token (empty = panel disabled). Token login = owner role |
| `PANEL_PUBLIC_URL` | Base URL used in the one-time links `/panel` sends to admins |
| `ENABLE_TEST_API` + `ENABLE_TEST_API_CONFIRM` | Test harness endpoints. Off by default and double-gated |

---

## Using the bot (users)

1. Send `/start`. The welcome message has **📨 ارتباط با مدیریت**, **📋 My jobs** and **🧭 Menu** buttons.
2. Send a video, either as a video or as a video file/document, up to your size limit.
3. The bot asks for the **output file name**. Type a Persian or English name; no extension is needed. Alternatively press **📎 Keep original name** or **✖️ Cancel this video**.

   | You type | You receive |
   |---|---|
   | `University Lecture 01` | `University Lecture 01.mp4` |
   | `درس مهندسی برق` | `درس مهندسی برق.mp4` |
   | `Lecture 01.mkv` | `Lecture 01.mp4` |

   If you send several videos, the bot asks for their names one at a time, in order. Replying directly to a specific prompt names that video.
4. The same message becomes the **queue card**: position, jobs ahead, active workers and estimated waiting time. The note "not downloaded yet" means exactly that: the video is fetched only when its turn comes.
5. When processing starts, the card follows the real stages until the compressed video arrives with the name you chose.
6. Cards include **Cancel**. Failed jobs show **Retry** and **Error details**. A delivery that failed shows **Redeliver**.

Other commands: `/menu`, `/myjobs`, `/settings` (language, delivery as video or file, notifications), `/contact` (or `/support`), `/help`.

**Contact management.** Press **📨 ارتباط با مدیریت** (or send `/contact`), then send one message: text, photo, voice or file. It is delivered to the owner only, and the reply arrives in the same chat. Ordinary messages are never forwarded to anyone.

---

## Owner and administrator guide

### Commands

| Command | Who | Purpose |
|---|---|---|
| `/admin` | admins | Operations panel: stats, health, pause/resume intake, queue, live monitor, errors, cleanup, global thumbnail, users (VIP, ban, per-user limits, message), tier limits, broadcast, ban |
| `/owner` | owner | Admins (add, remove, per-feature permissions), VIP users, permission matrix, audit of role and permission changes |
| `/panel` | admins | Sends a 10-minute one-time link to the web dashboard |
| `/setarchive <id>` | admins | Set the archive channel |
| `/retry <job-prefix>` | admins | Requeue a failed job |
| `/branding`, `/thumb`, `/wm`, `/cap` | admins with the permission | Personal thumbnail, watermark, caption |
| `/merge` | admins with the permission | Merge clips (merge + compress goes through the normal EDU480 queue) |

### Permissions (granted per admin in `/owner`; the owner always has everything)

| Permission | Default for admins |
|---|---|
| `compression.use` | granted |
| `thumbnail.use`, `watermark.use`, `caption.use`, `merge.use`, `merge_compress.use` | denied |
| `forcesub.manage` (mandatory membership settings) | **denied: owner-only unless granted** |

Permissions are checked on every command, callback and text input, not only by hiding buttons. Revoking one takes effect within seconds.

### Support messages

User messages sent through contact management arrive in the **owner's** private chat as a header (name, @username, ID) followed by a copy of the message. To answer, press **↩️ پاسخ** and type, or simply use Telegram's *reply* on the copied message. The answer goes to that user. The owner receives a confirmation, not a copy. Admins are never involved. Every message is stored in `support_messages`.

### Private activity channel and moderation

Every accepted job posts one record to the activity channel. It is a Telegram-side copy of the user's video, so the server downloads nothing for it. The record carries:
- the requester's display name, @username and Telegram ID;
- the job ID;
- the original and output file names;
- size, duration and submission time;
- the profile;
- the current status, which is updated as the job progresses.

**🗑 Remove video and ban user** works for the owner only and asks for a confirmation. Running it does all of the following:
- bans the user permanently;
- cancels **all** of that user's queued and running jobs, at every layer:
  - the database;
  - an active download;
  - the FFmpeg process in Encore;
- deletes only those jobs' files;
- blocks the archived result so it is never reused;
- removes the video from the channel and leaves a text record.

The action is idempotent and is recorded in `moderation_actions` and `audit_log`. The same action is available in the web dashboard. If the job was already delivered, the record says so; the delivery is not pretended away.

### Mandatory channel membership

`/admin` → 🔒 appears only for the owner and for admins granted `forcesub.manage`. Send `@channel`, `-100id`, a `t.me` link, or `-100id | invite-link`. Send `off` to disable it.

---

## Web dashboard

Run `/panel` in the bot to get a one-time link. Alternatively open `https://<server>:8090/panel` and log in with `ADMIN_PANEL_TOKEN`; token login gets the owner role.

| View | Content |
|---|---|
| Overview cards | Queued and capacity, busy and total workers, completed (1 h / 24 h), failed (24 h), average wait and processing time, CPU, RAM, free disk |
| Active | Each running job: user, video (name, size, duration, resolution, codec, fps), stage and progress, submitted time, waiting and processing time, worker |
| Queue | Every waiting job with its exact position and jobs ahead |
| Completed / Failed / Cancelled | Output size and reduction, delivery time / error category and message / cancel reason |
| Users | Requests in the last 24 h (with a **heavy submitter** flag), pending, done, failed, volume, last activity, ban status |
| Moderation | History of remove-and-ban actions and the list of banned users |
| System | Encode slots and what occupies them, stage counts, Encore queue, active profile, uptime |

- **Search and filters:** job ID or file name, user ID or @username, date range. Results are paged.
- **Job detail:** clicking a row shows every field, the full timeline (submitted → reserved → download → encode → upload → delivered), requesters and deliveries.
- **Refresh:** every 4 s for live views.
- **Owner-only actions:** remove-and-ban and admin promotion are enforced server-side.
- **Sensitive data:** no media is ever served and no server paths are exposed.
- **Old panel:** still available at `/panel/legacy`.

---

## Duplicate detection and reuse

| Layer | When | What happens |
|---|---|---|
| Early, by Telegram `file_unique_id` | At submission, **no download** | One of the bot's own EDU480 outputs, or a source compressed before, gets the archived result delivered immediately |
| In-flight | At submission | The same Telegram file is already queued or running: the new requester joins that job and both receive the result |
| Exact SHA-256 | After download, before encoding | Same bytes as a previous source, or as one of our outputs: deliver, skip the encode |
| Compliance | After probing | Already EDU480-compliant: remux only |
| No gain | After encoding | Output not smaller: the original is delivered with an explanation |

Results are delivered with `copy_message`. Users never see a "Forwarded from" header pointing at the private channel. Different profiles and profile versions are separate outputs. EDU480 v1 archives are reused only if their real output is ≤480p.

---

## Limits, fairness and disk safety

- **Queue capacity counts accepted job records, not files.** When the queue is genuinely full, the user is told plainly that the request was **not** accepted.
- **Intake does not check disk:** waiting jobs use none. The dispatcher starts a download only if `free − reserved ≥ source × ADMISSION_NEED_FACTOR + ADMISSION_FLOOR_GB`. If not, the queue simply waits and admins get one alert per hour.
- **Fairness:** among queued jobs, users with nothing running go first. With no one else waiting, one user may use every slot.
- **Long videos:** the duration limit per tier is 6 h normal, 12 h VIP. Very long videos still occupy only one slot.

---

## Operations

```bash
docker compose ps                         # service health
docker compose logs -f bot                # JSON-line logs of the bot
docker compose logs -f encore-worker      # FFmpeg / transcode logs
docker compose restart bot                # restart the bot only (queue survives)
./scripts/backup.sh                       # manual DB backup (alerts on failure)
```

Useful SQL (`docker compose exec postgres psql -U oxmit oxmit`):

```sql
SELECT status, stage, count(*) FROM jobs GROUP BY 1, 2 ORDER BY 1, 2;     -- pipeline snapshot
SELECT id, requester_tg_id, stage, reserved_at FROM jobs WHERE status = 'processing';
SELECT * FROM moderation_actions ORDER BY created_at DESC LIMIT 20;
```

A full runbook (disk management, restart recovery, upgrading Encore) is in [`docs/operations.md`](docs/operations.md). Backup and restore steps are in [`docs/backup-restore.md`](docs/backup-restore.md).

---

## Testing and benchmarking

```bash
pip install -r bot/requirements.txt -r bot/requirements-dev.txt
python -m pytest -q                       # unit tests (no services needed)
```

**PostgreSQL integration tests** (`tests/test_integration_*_pg.py`). They need PostgreSQL ≥ 13 and `ffmpeg`. They drive the real lifecycle:
- registration, fair dispatch, download, probe, EDU480 submission;
- upload retry without re-encode, copy delivery, cleanup, early reuse;
- moderation, restart recovery;
- the naming flow, support routing, the web dashboard over HTTP.

```bash
OXMIT_TEST_PG_DSN="postgresql://postgres@localhost/oxmit" python -m pytest -q
```

Each test creates and drops its own database.

**EDU480 benchmark.** Run it on real samples on the production server:

```bash
python3 scripts/bench_edu480.py lecture.mp4 whiteboard.mkv screen.mp4 --threads 3 \
    --variants "veryfast:25:30" "faster:25:30" "veryfast:27:30"
```

It reports wall time, real-time factor, CPU seconds per media minute, output size and ratio, and SSIM, and writes a CSV.

**End-to-end load tests** against a running stack. These require the test API to be enabled:

```bash
python3 scripts/loadtest.py --token <INTERNAL_TEST_TOKEN> --mode pipeline
python3 scripts/loadtest.py --token <INTERNAL_TEST_TOKEN> --mode burst --n 4
```

---

## Project structure

```
bot/oxmit/
  bot.py              entry point: wiring, routers, poller/sweeper loops
  config.py           env settings + validation
  db.py               asyncpg pool + automatic migrations
  engine.py           JobEngine: admission, completion, archive upload, delivery
  jobqueue.py         queue: registration, ETA, dispatcher, pipeline, moderation, recovery
  edu480.py           EDU480 profile, output naming, transcode decision, ETA model
  archive.py          archive captions + delivery chain (copy → file_id → upload)
  dedup.py            duplicate queries (exact / fuzzy / similarity)
  encore_client.py    SVT Encore REST client
  media.py            ffprobe, hashing, remux, thumbnails, redaction of token paths
  permissions.py      owner-managed per-admin permissions
  webpanel.py         panel auth (token / one-time link), sessions, CSRF, legacy APIs
  dashboard.py        dashboard v3 data APIs        dashboard_page.py  its HTML/JS
  internal_api.py     health, Encore callback, test harness
  handlers/
    intake.py         video → name prompt → queue; job buttons; archive setup
    support.py        contact management (user → owner, owner → user)
    moderation.py     channel "remove video & ban user"
    menu.py nav.py settings.py   /start, /menu, /help, /myjobs, /settings
    adminpanel.py admin.py owner.py personal.py merge_flow.py
  migrations/         001 … 015 (applied in order on start)
deploy/               encore profiles, Local Bot API Dockerfile, ffmpeg wrapper
scripts/              backup, load test, benchmark, SQL helpers
tests/                unit + PostgreSQL integration tests
reports/, docs/       audits, benchmarks, runbooks, architecture
```

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Jobs stay queued and nothing starts | Disk: the dispatcher waits for `free − reserved ≥ need` (admin alert, dashboard → System). Encore health: `/admin` → 🩺. Workers: `docker compose ps` |
| "Archive channel not configured" | `/setarchive -100…` and make sure the bot is an admin with post rights |
| Uploads stuck in `upload_retry` | Local Bot API logs. Check that `/media` is mounted read-only in `telegram-bot-api` if `BOTAPI_READS_MEDIA=true` (it falls back automatically) |
| Encore cannot read the source | `WORKERS_READ_BOTAPI=true` needs the `botapi_data` mount on `encore-worker` (recreate the workers), or set it to `false` to copy instead |
| Support messages not arriving | `OWNER_TELEGRAM_ID` must be set and that account must have started the bot |
| Web panel says unauthorized | `ADMIN_PANEL_TOKEN` set? One-time links expire after 10 min and work once |

More: [`docs/troubleshooting.md`](docs/troubleshooting.md).

---

## Further documentation

- [`reports/architecture-v3/README.md`](reports/architecture-v3/README.md): current architecture, root-cause review, requirement-to-code map, deployment steps, known limitations
- [`docs/operations.md`](docs/operations.md), [`docs/backup-restore.md`](docs/backup-restore.md), [`docs/troubleshooting.md`](docs/troubleshooting.md): runbooks
- `docs/` and `reports/` (other files): historical audits and benchmarks. Documents dated before v3 describe the earlier multi-profile, download-first design.

---

## License and attribution

- **SVT Encore**: EUPL-1.2-or-later, used unmodified as the transcoding engine
- **tdlib/telegram-bot-api**: built from official source (pinned commit)
- **FFmpeg** (static 7.0.2 wrapper for the workers): see [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md)
- This repository: application code around those components
