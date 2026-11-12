# Architecture v3: just-in-time queue, single EDU480 profile, moderation and support routing

This report covers the full source review behind this change and maps each requirement in the three specification documents to the code that implements it. It also lists the deployment steps and what still needs measuring on the production server.

## 1. Root causes found in the source review

| # | Finding | Where (before) | Effect in production |
|---|---|---|---|
| R1 | **Download before queue.** `handle_submission` called `bot.get_file()` (with the Local Bot API this downloads the whole file), then SHA-256 and ffprobe, and only then inserted the job row. | `engine.handle_submission` | Every waiting job held its full source on disk. The queue caused the disk exhaustion. |
| R2 | **No real queue.** Every queued job was submitted to Encore immediately (`poll_once` spawned `run_job` for every queued row), so Encore's Redis list was the actual queue. | `engine.poll_once` / `run_job` | The bot had no scheduling control: no fairness, no disk-aware start, no meaningful queue position. |
| R3 | **Small hard cap.** `MAX_QUEUED_JOBS=50` (spec mentions 20) combined with the disk gate at intake. | `config.py`, `check_admission` | Submissions were rejected or deferred because of disk use, not queue capacity. |
| R4 | **"EDU480" silently became 360p.** `decision_engine.make_decision` routed sources whose short side was ≤480 to the `edu360` profile. The 360p button was also still offered. | `decision_engine.py`, `intake.py` | The 360p profile was still active. |
| R5 | **EDU480 geometry was wrong.** `edu480.yml` scaled to a fixed width of 854: portrait 1080×1920 became 854×1518, and 4:3 or sub-480p sources were upscaled. | `deploy/encore/profiles/edu480.yml` | Larger, slower output that was not 480p for portrait and 4:3 sources. |
| R6 | **Upload failure meant a re-encode.** An archive upload error called `fail_job`, which deleted the output, so a retry encoded again. | `complete_job` | Wasted CPU after transient Telegram errors. |
| R7 | **Completion race.** The completion claim excluded only the `completing` stage. Once the job moved to `validating`, the next 5-second poll could claim it again and run a second completion in parallel. | `complete_job` | Duplicate uploads and deleted part files (the cause behind the earlier `part001.mp4` error). |
| R8 | **Forward attribution.** Delivery used `forward_message` first, so users saw "Forwarded from <private channel>". | `archive.deliver_result` | The private storage channel was exposed to users. |
| R9 | **Local Bot API sources never deleted.** Downloaded sources stayed in `botapi_data` permanently. | (missing) | Unbounded disk growth. |
| R10 | **Staging copy.** `WORKERS_READ_BOTAPI` existed but was not implemented, so every source was copied a second time (EXDEV prevents hardlinks). | `_stage_source` | A 4 GB source used 8 GB of disk. |
| R11 | **Support routing lost.** The contact-management code is not in the surviving source. Admin "message user" was send-only. | (missing) | The owner and admin copy behaviour described in the spec could not be fixed in place. It was rebuilt. |
| R12 | **Force-sub visible to every admin.** `adm:fsub` checked only `is_admin`. | `adminpanel.py` | Any admin could change mandatory membership. |
| R13 | **Web panel had no identity.** One shared token meant every session was the anonymous "panel-admin", so owner and admin could not be told apart. | `webpanel.py` | No basis for owner-only actions on the web. |
| R14 | **Merge clip crash.** `merge_flow.py` used undefined `media_mod` and `lang`, so every accepted clip raised `NameError`. | `handlers/merge_flow.py` | The merge feature was broken. |
| R15 | **`Record.keys()` misuse.** It is a one-shot iterator; a second `in keys` test was always False. | `engine._progress_text` (+ new code) | Silent wrong branches. |
| R16 | **Dead stub modules.** `downloader.py`, `uploader.py`, `progress_manager.py`, `progress_cards.py` and `buttons.py` were never imported. They advertised a "JIT pipeline" that did not exist, plus 360p and Rostam buttons. | removed | Misleading code. |

## 2. New lifecycle

```
Telegram video ──► metadata validation (size, duration, mime; no download)
               ──► intake_drafts row ──► "type the output name" prompt
               ──► name normalized ──► jobs row (QUEUED) + channel record
                     │  early recognition by file_unique_id (no download):
                     │    our own EDU480 output / already-compressed source ──► copy result
                     │    same file already queued ──► join that job
dispatcher (every 5 s + on events)
   claim: UPDATE … WHERE id = (SELECT … FOR UPDATE SKIP LOCKED)    fair FIFO
   only while busy slots < ENCODE_SLOTS (+PREFETCH) and disk free ≥ need
               ──► RESERVED ─► DOWNLOADING (getFile) ─► PROBING (ffprobe)
               ──► CHECKING (SHA-256: exact duplicate / own output ─► deliver, skip encode)
               ──► decide: compliant ≤480p H.264/AAC low bitrate ─► REMUX (seconds)
                           else ─► ENCODING on Encore with exact EDU480 filters
encode finished ─► slot freed (next download starts) ─► VALIDATING
               ──► UPLOADING to archive (file://, retried with backoff, never re-encoded)
               ──► DELIVERING via copy_message to every requester
               ──► COMPLETED: temp dirs + Local Bot API source deleted
```

Key properties:

- **Queue capacity counts job records, not files.** Up to `MAX_QUEUED_JOBS` (default 5000) jobs can wait while using no disk at all. Disk admission happens per claim (`ADMISSION_NEED_FACTOR`).
- **Concurrency model.** A slot is held from claim until the encode finishes; validation, upload and delivery run outside it. Encore never holds more than `ENCODE_SLOTS` jobs. The existing `WorkerCpuTuner` keeps sharing the CPU budget between active workers (7 cores for one job, 3.2 each for two).
- **Fairness.** Users with a job already in a slot sort behind users with none. Spare capacity is still used when nobody else is waiting.
- **Leases.** `worker_id` and `lease_expires_at` are set at claim and refreshed by a heartbeat. The reaper requeues pre-encode work whose owner died. On startup, interrupted downloads are requeued (an already-downloaded source is reused) and finished encodes resume their upload. Claims are `SKIP LOCKED`, so a second server can claim from the same table: this is the multi-server upgrade path.
- **Atomic transitions.** Every state change is a conditional `UPDATE … WHERE status IN (…)`. Claim, cancel, complete and fail cannot overlap.

## 3. Requirement → implementation map

| Requirement | Implementation |
|---|---|
| Metadata-first registration; download only when a worker is ready | `jobqueue.register_job`, `dispatch_once`, `_acquire_source` |
| Persistent queue, at least 5000 jobs, survives restarts | `jobs` table, `MAX_QUEUED_JOBS=5000`, `recover_queue_on_startup` |
| Clear message when the queue is genuinely full | `AdmissionError("queue_full", cap=…)`, text says the request was *not* accepted |
| Per-user limits | `max_pending` (tier, admin-editable), hourly/daily caps, fair dispatch |
| Queue position, jobs ahead, ETA from real throughput | `queue_info`, `throughput_rate` (rolling over the last 50 completed jobs), `edu480.eta_range`; cards refreshed with throttling (`refresh_queue_cards`, at most once a minute per card, bounded per cycle) |
| Stage-accurate progress (no fake 0% while queued) | `stage_card_text`: queued / reserved / downloading / probing / checking / encoding (real Encore %) / validating / uploading / upload-retry |
| Single EDU480 profile; old 360p removed | intake has no profile picker; `handle_submission` maps any legacy profile to EDU480; migration 015 converts queued non-EDU480 jobs and deactivates other profiles |
| EDU480 quality definition | `edu480.py` + `edu480.yml` v2: short side 480, Lanczos, no upscale, even dimensions, fps cap 30, x264 CRF 25 veryfast, aq-mode 3, AAC 64k; filters passed per job |
| Profile versioning | `profile_version = 2` on every job; archive reuse accepts v1 outputs only if their output is ≤480p |
| Do not re-compress already processed or compliant videos | early `file_unique_id` match (own outputs and known sources), SHA-256 match after download, `edu480.decide` (remux when compliant), existing no-gain policy |
| Upload failure must not re-encode | `schedule_upload_retry` / `resume_upload`; `fail_job` keeps the output for category `upload`; user Retry re-uploads only |
| Temp file safety and disk protection | per-job dirs, symlink staging (no copy), Local Bot API source deletion guarded by "no other active job uses it", disk check per claim, admin alert when the queue is held |
| File renaming at the start (Persian/English, extension ignored, sanitized) | `handlers/intake.py` drafts + `edu480.normalize_output_name` (traversal, invalid characters, bidi spoofing, ZWNJ kept, 100 chars / 200 bytes) |
| Name assigned to the correct video | one active prompt per user (partial unique index), later videos wait in FIFO order, an explicit reply targets a specific draft, duplicate updates are ignored, drafts expire after `NAMING_TIMEOUT_MIN` |
| Support routing to the owner only; owner replies; no echo | `handlers/support.py`: explicit sessions, owner-only recipient, reply button or native reply mapped through `support_messages`, admins never routed, sessions close after one message |
| Contact-management menu item | `/start` welcome and `/menu` show **📨 ارتباط با مدیریت**; `/contact` also works |
| Channel record identifying the requester | `post_log_record`: Telegram-side `copy_message` of the user's video (no server download) with name, @username, ID, job ID, file names, size, duration, time, profile and status; caption updated on each transition |
| Remove video and ban user | channel button (owner-only, two-step confirm) and web drawer (owner-only, CSRF) both call `engine.moderate_job`: idempotent; cancels every active job of the user at the DB, pipeline task, Encore/FFmpeg and file levels; blocks archived outputs from reuse and deletes them from the channel; persistent ban; `moderation_actions` and `audit_log` records |
| Race: worker starts the job right after removal | claim needs `status='queued'`; the pipeline re-checks ownership between stages; an Encore submission that loses the race cancels the Encore job it just created |
| Force-sub owner-only by default, grantable | new permission `forcesub.manage` (not in default grants), checked on the menu, the callback and the text-input mutation |
| Web dashboard | `/panel` (v3): active, queue (with positions), completed, failed, cancelled, users (24 h activity, heavy-submitter flag), moderation history and banned list, system (slots, CPU, RAM, disk, throughput, average wait and processing). Search by job ID or file name and by user ID or @username, date range, paging, job drawer with full timeline, live refresh every 4 s. The old panel stays at `/panel/legacy`. |
| No downloads or sensitive paths exposed in the panel | no media endpoints; token-bearing paths are never serialized; owner-only actions enforced server-side (the session role comes from the one-time-link identity) |
| Delivery without forward attribution | `archive.deliver_result` uses `copy_message`, never `forward_message` |

## 4. Verification

- `pytest`: **231 passed** without a database, plus **7 PostgreSQL integration tests** (`tests/test_integration_*_pg.py`, run with `OXMIT_TEST_PG_DSN=…`). All 238 pass against PostgreSQL 16. The integration tests run every migration including 015, then drive the real code end to end:
  - metadata-only registration;
  - in-flight join;
  - fair two-slot dispatch;
  - JIT download, ffprobe and SHA-256 on a real generated video;
  - EDU480 submission (`scale=854:480`, `fps=30`, symlinked token-free input);
  - completion with a forced upload failure, then a retry without re-encode;
  - copy delivery to two requesters;
  - source deletion;
  - early `file_unique_id` reuse and own-output recognition;
  - moderation of a running and of a queued job, with idempotency;
  - restart recovery;
  - the queue-full message;
  - the naming flow with two videos, Persian names and typed extensions;
  - owner-only support routing in both directions;
  - the web panel over HTTP (login, role, v3 APIs, CSRF, owner-only moderation).
- The dashboard was rendered in headless Chromium at 1366 px and 390 px, in light and dark mode: no JS errors and no horizontal overflow.
- **EDU480 benchmark (indicative only).** It ran on a synthetic 40 s 1920×1080@60 test pattern in a 4-vCPU container with `scripts/bench_edu480.py --threads 3`:

  | preset | CRF | fps cap | wall s | CPU s per media minute | output MB | SSIM |
  |---|---|---|---|---|---|---|
  | veryfast | 25 | 30 | 6.88 | 25.2 | 2.66 | 0.9935 |
  | faster | 25 | 30 | 7.85 | 28.9 | 2.67 | 0.9942 |
  | superfast | 25 | 30 | 6.00 | 20.8 | 5.71 | 0.9959 |
  | veryfast | 27 | 30 | 6.87 | 24.2 | 2.09 | 0.9919 |
  | veryfast | 25 | 60 (old behaviour) | 7.89 | 28.8 | 3.04 | 0.9920 |

  On this synthetic source the 30 fps cap saved about 13% CPU and 12% size. `veryfast` beats `faster` (same size, 14% slower) and `superfast` (2.1× larger). **These are not production numbers.** Run the script on real lecture, whiteboard and screen samples on the 8-core server before changing `EDU480_CRF` / `EDU480_PRESET`.

## 5. Deployment

1. Back up the database (`scripts/backup.sh`).
2. `git pull` the branch. Migration 015 runs automatically at bot start.
   - It converts queued or deferred jobs that never reached Encore to EDU480 v2.
   - Jobs already running in Encore finish with their original settings.
3. Merge the new keys from `.env.example` into `.env` (`MAX_QUEUED_JOBS=5000`, `WORKERS_READ_BOTAPI=true`, `BOTAPI_READS_MEDIA=true`, `EDU480_*`).
4. Set `OWNER_TELEGRAM_ID`: it is now the **only** recipient of support messages and the only identity allowed to moderate.
5. `docker compose up -d` recreates `telegram-bot-api` (new read-only `/media` mount) and `encore-worker` (botapi mount for symlink staging). Do it when no encode is running.
6. Encore reads `edu480.yml` per job, so the new profile is live for the next submission.
7. Verify by sending one test video: answer the name prompt, check the queue card, the channel record, the dashboard `/panel` and the delivered file name.

## 6. Known limitations and next steps

- **Download progress.** The Local Bot API `getFile` call reports no progress, so the download card shows elapsed time and size, not a fabricated percentage. Upload progress is reported the same way, because aiogram exposes no upload callbacks.
- **Reused results keep the archived file name.** A cached result is delivered by `copy_message` (no re-upload), so it keeps the file name of its first encode. Renaming it would mean re-uploading the file.
- **Merge collects its clips eagerly.** Merge sessions still download each clip when it is added; a merge needs every input. Merge plus compress then goes through the standard queue.
- **Owner/admin message copies.** The exact behaviour described in the spec could not be reproduced because that code was lost. The rebuilt routing is covered by integration tests.
- **Old profiles.** The `decision_engine` profiles other than EDU480 remain in the code for history and tests, but no entry point selects them any more.
- **Multi-server.** The claim, lease and heartbeat model is ready for it. Each server still needs shared `/media` or object storage for outputs, and the dispatcher's slot count should become per-server.
