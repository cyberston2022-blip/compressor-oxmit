# Oxmit Engineering Report — Audit, Reengineering & Optimization
**Date:** 2026-11-05 · **Scope:** full codebase audit + implemented fixes · **Baseline:** `performance/size-speed-optimization` @ `ec16406` + uncommitted tuning work
**Companion doc:** [docs/architecture-current.md](../docs/architecture-current.md) (5 as-built Mermaid diagrams with file:line citations)

---

## A. Executive Summary

**What the project was.** A single-process Telegram video-compression bot (Python 3.12, aiogram 3, asyncpg, aiohttp, httpx) that accepts up to 4 GB videos via a self-hosted Local Bot API, probes/hashes them in place, deduplicates against a private Telegram archive channel used as object storage, encodes via SVT Encore (Redis-backed, drain-mode workers, static ffmpeg 7.0.2), validates/archives/delivers results, with Postgres as the single source of truth.

**Strengths found (and preserved).** Postgres-delegated concurrency (advisory locks, partial unique indexes, conditional claims), aggressive secret redaction, `compare_digest` everywhere, fail-fast config validation, bounded rate-limit maps, a real regression-test suite, and a self-correcting report culture in `docs/`.

**Most important weaknesses found.**
1. **The primary "compression level 1–20" flow was dead** — an earlier editing accident merged `@router.message(F.text, _waiting_percent)` onto the previous line where `@` parses as matrix-multiply; the module imported fine, so nothing caught it. *(Introduced during this session's own editing — caught by audit, fixed, regression-pinned.)*
2. **Dashboard "cancel" button 500'd** (truncated 8-char id → Postgres uuid cast error).
3. **Panel could serve plain HTTP on a public port** when TLS certs are absent (one-time login key in cleartext).
4. **Panel session store was split-brained** across two aiohttp apps (revocation/logout incomplete).
5. **Test API submit was an arbitrary-file-read primitive** for a leaked static token.
6. `fsub:check` double-answered callbacks (alert unreachable); admin `pk:` grid lacked ownership checks; broadcast sweep crashed every 10 min (`float - str`); custom-size parser crashed on `inf`/`۱e400` and rejected Persian digits; `bot.py` shutdown orphaned in-flight engine tasks; 8 config fields accepted zero/negative values; ~60 lines of byte-identical handler duplication; emoji corruption (`???`) in the progress tracker predating all snapshots.

**What was improved.** All of the above (20 fixes, listed in §F), plus the previously deployed cache-offer/deduplication feature (interactive reuse, quality hierarchy, degraded-source fallback). 145/145 tests pass locally and on the server. **Deployed AND activated on production** (image rebuilt, container recreated, migration 011 applied, healthz green) with owner approval on 2026-11-05 ~19:46 UTC; rollback image tagged `oxmit/bot:rollback-20261105`.

**Remaining limitations.** See §I.

---

## B. Initial Architecture

Reconstructed from source with per-claim citations in **[docs/architecture-current.md](../docs/architecture-current.md)** — five as-built diagrams:
1. **System architecture** (containers, modules, trust boundaries: public 8090, docker.sock, token-bearing botapi paths)
2. **Execution lifecycle** (update → intake → admission → 4-layer dedup + cache-offer → job → run_job → reconcile → complete_job → delivery → cleanup, with failure branches)
3. **Video processing pipeline** (`is_already_compressed` → `decision_engine.make_decision` → `resolve_variant`/`quality.py` → profile params → remux eligibility)
4. **Async/concurrency inventory** (12-row lock table: advisory locks, partial unique indexes, completion lease, semaphores, queue maxsizes)
5. **Error handling & recovery** (transient vs permanent categories, mux-repair ladder, atomic retry claims, startup recovery, counter reconciliation)

**Documented docs-vs-code contradictions** (unchanged, flagged): README says the panel is "read-only" (it mutates), "localhost-only" (port 8090 is public), compose comment says botapi "runs as root" (Dockerfile sets `USER 1000`).

## C. Identified Problems (categorized)

**Critical**
| Problem | Evidence | Impact |
|---|---|---|
| Level 1–20 flow dead (decorator merged into `return` line) | intake.py:803 (fixed); AST-verified | Users pressing «فشرده‌سازی درجه ۱-۲۰» and typing a number got permanent silence |
| Dashboard cancel always 500s | webpanel.py:209/1150/601 | Core admin action broken |
| Plain-HTTP admin panel on public port when certs missing | internal_api.py:283-293 + compose `8090:8081` | One-time login key interceptable → full admin session |

**High**
| Problem | Evidence |
|---|---|
| Panel sessions split-brained across two apps (revocation/logout incomplete, lockout budget doubled) | webpanel.py:359, internal_api.py:48/280 |
| Test-API `submit`: arbitrary file read+exfiltrate with leaked token | internal_api.py:179-196 |
| `pk:` grid callback: no ownership/throttle (group members could spend admin quota / hijack `pending_custom`) | intake.py:819-844 |
| `fsub:check` double `callback.answer()` → alert never shown, update errors | menu.py:76-89 |
| Broadcast sweep TypeError every 600 s (`float - str`) | adminpanel.py:999 |
| Engine `_bg_tasks` never cancelled at shutdown → jobs stuck in `processing` | bot.py:157-179 |

**Medium**
`on_custom_size` OverflowError + Persian digits rejected; `_parse_level` OverflowError; broadcast text >4096 fails for all recipients; first-run admin bootstrap race; tier-stepper lost-update via 60 s cache; `from_user` None guards missing (3 sites); config `validate()` missing ranges on 8 fields; `.env.example` drift (11 vars incl. `OWNER_CLAIM`, `CACHE_OFFER`); WS survives session revocation; `ban/vip`/`audit limit`/`test_gen` input validation gaps.

**Low**
~60 lines duplicated `cmp:*` handlers; `except Exception: pass` in 9+ adminpanel sites (swallows non-Telegram errors); language fetched via raw SQL bypassing `_lang` cache; fsub not audited; `bgo` drops text when busy; `rdl:` misleading failure message; ~18 dead texts.py keys + hardcoded panel strings; literal `**` markdown shown to users; docker-SDK private-API usage in resources.py; tuner partial-update forgotten; return annotation + stale log message in internal_api.

**Docs/architecture notes (recorded, not changed):** `jobs.source_path` persists token-bearing bot-api paths (redaction covers logs only); `decision_engine` adaptive-resolution/audio-copy outputs computed but never consumed; `custom_2pass` unreachable; docker.sock = root-equivalent trust boundary (needed only by the CPU tuner).

## D. Final Architecture

As-built diagrams (now including this session's changes) live in **[docs/architecture-current.md](../docs/architecture-current.md)**. Structural shape is deliberately unchanged — the system was already sound at the architecture level; the work was bug/consistency/hardening, not a rewrite. Incremental target-architecture proposals (9 items, S/M/L effort, incl. removing docker.sock via a scoped sidecar, splitting `engine.py`, formalizing the job state machine) are in §7 of that document.

## E. Design Patterns & Engineering Decisions

**Kept (already in place, validated):** Producer–Consumer (fingerprinter queue), Worker Pool via Encore, atomic claim/fencing-lease for completion, advisory-lock serialization, repository-ish `Database` wrapper, fail-fast config object.
**Introduced this session:** centralized pure-function quality hierarchy (`quality.py` — Strategy-like profile ranking without new abstractions); dispatch-table handler instead of copy-paste trio; shared session store (singleton state across two apps); fail-closed TLS bind.
**Considered and rejected:** full `engine.py` split into services (high regression risk with uncommitted user work in flight — scheduled as debt); pydantic schemas for settings (dataclass + validate() is adequate; no new dependency); Redis-based job queue (Postgres already authoritative; Redis belongs to Encore); a global aiogram error middleware (worthwhile, but touching every handler's error contract — listed as debt).

## F. Implemented Changes (this audit round)

| File | Change | Why / Problem solved |
|---|---|---|
| `bot/oxmit/handlers/intake.py` | **CRITICAL:** restore `@router.message` decorator to its own line; `pk:` ownership+throttle; 3 duplicated `cmp:*` handlers → one dispatch-table handler; `cmp:go` throttle; `_parse_level` catches `OverflowError`; `on_custom_size` Persian digits + `OverflowError`; `on_forward` from_user guard | Level flow dead; group-context privilege gap; crashes on `inf`/`۱e400`; inconsistent UX for Persian-speaking users |
| `bot/oxmit/handlers/menu.py` | `fsub:check` single-answer; conditional bootstrap `UPDATE ... AND NOT EXISTS (SELECT 1 FROM users WHERE is_admin)` | Alert unreachable; two-owner race |
| `bot/oxmit/handlers/adminpanel.py` | `bcast_text` stores `(text, ts)`; sweep fixed; 3800-char clamp at preview; `bgo` pops after running-check; fsub audited; `on_admin` from_user guard | Sweep crash; all-recipient broadcast failure; silent loss; audit parity |
| `bot/oxmit/handlers/admin.py` | `guard` from_user guard | AttributeError on channel-auto posts |
| `bot/oxmit/webpanel.py` | `active_data` returns full `id`; dashboard cancel uses it; `job_action` validates uuid (400 not 500); shared session store compatible; WS re-checks session each iteration; `audit_list` limit guarded; `ban/vip` 404 on missing user; truthful log line; `import uuid` | Broken admin cancel; split-brain sessions; revoked-WS data leak; 500s on bad input |
| `bot/oxmit/internal_api.py` | TLS fail-closed (no certs → loopback bind + warning); `test_submit` path contained to `cfg.media_test` + `tg_id` validation; `test_gen` `secs` validation + clamp; shared session store injection via `build_app(..., shared_sessions)` (before `webpanel.setup`'s `setdefault`); return annotation fixed | Cleartext admin panel; arbitrary-file-read primitive; 500s; split-brain sessions |
| `bot/oxmit/bot.py` | `finally` cancels + awaits `engine._bg_tasks` before closing pool/session | Jobs stuck in `processing` after shutdown |
| `bot/oxmit/config.py` | 8 new range validations (need-factor, progress-edit, upload MB, min kbps, retention, sim-tolerance, segment-min, source GB) | Silent misconfiguration |
| `bot/oxmit/resources.py` | `container.update(**payload)` public API; `_last` set only when ALL workers updated (partial update retried); top-level `asyncio` import; dead `CPU_PERIOD` removed | SDK-version brittleness; forgotten failed container |
| `tests/test_router_registration.py` | **NEW** — pins every business-critical handler by registration (`on_percent_text`, `on_media`, cache-offer trio, job callbacks) | The decorator-death bug class |
| `tests/test_resources.py` | Fake adapted to public `container.update` API; **NEW** partial-update retry test | Interface change; regression pin |
| *(Previous round, already deployed)* | `quality.py`, `011_cache_reuse.sql`, dedup/engine/intake/texts/config cache-offer feature; emoji-corruption restoration | Interactive dedup + quality hierarchy (see prior report) |

**Removed:** dead `cmp:edu` alias, dead `CPU_PERIOD`. Nothing else removed; no behavior removed.

## G. Performance Results

Encoding-path performance was **not changed** this round (bug/hardening only), so encode throughput was re-measured fresh as a baseline rather than claimed as an improvement. All measurements are real, taken on the production server (idle, load 0.01–0.06) by a separate read-only benchmark agent; encodes ran under `nice -n 10` with the exact static ffmpeg 7.0.2 binary the workers use, each config run twice (r1/r2 within ~4%, byte-identical outputs per config).

**Synthetic encode benchmark** (1080p, 10 s testsrc2 clip, 10,010,131 B in):

| Config (production parameters) | Wall (s) | CPU-s used | Avg cores | Output size | Ratio vs input |
|---|---:|---:|---:|---:|---:|
| x264 `faster` CRF23, `-threads 6` | 4.09 / 3.95 | 18.8 | 4.6–4.8 | 6,430,344 B | 1.56× |
| x264 `veryfast` CRF22, `-threads 6` | 2.55 / 2.57 | 13.1 | 5.1 | 6,479,421 B | 1.54× |
| x265 `superfast` CRF30, `pools=6:frame-threads=3` | 4.29 / 4.26 | 26.8 | 6.2–6.3 | 2,784,900 B | 3.60× |
| Remux (`-c copy`) | 0.02 / 0.02 | 0.03 | — | 10,010,131 B | 1.00× |

**Honesty notes (measured, not projected):** `testsrc2` is synthetic and compresses far easier than real footage — the ratios/fps are NOT representative; clips were video-only so audio-transcode cost is excluded; NOT MEASURED: real-footage encodes, disk I/O throughput. x265 hit 3.6× size ratio at ~6.3 cores — the `pools=6:frame-threads=3` sizing saturates the 8-vCPU box almost exactly as the earlier `reports/optimization` campaign predicted.

**Database hot-query timings** (production postgres, `EXPLAIN ANALYZE` ×2; tables: media_assets 993, archive_records 153, jobs 213):

| Query (as called by the bot) | Exec time | Plan |
|---|---:|---|
| Reusable-parts (sha + profile + version) | 0.20–0.30 ms | `idx_media_sha` bitmap; archive side seq-scan (only 153 rows — planner is right today) |
| Cached-versions (cross-profile offer query) | 0.20–0.22 ms | `idx_media_sha`; sub-ms as designed |
| Fuzzy dedup (±2% size + name + duration) | 0.12–0.13 ms | `BitmapAnd(idx_media_duration, idx_media_fuzzy)` |
| Queue-position (3-subquery intake query) | 0.05 ms | pk lookups; subqueries skipped on empty queue (idle-state caveat noted) |

All dedup/cache-offer queries are sub-millisecond at current scale; the partial unique index will start mattering as `archive_records` grows.

**Runtime snapshot:** bot 303 MiB, disk 31/619 GB (5%), RAM 1.5/15.6 GB used. Anomaly worth knowing: `botapi_data` volume is only 140 KB despite 68 GB lifetime ingress — downloaded sources are evicted after processing (matches the in-place hash + `_refetch_source` design).

| Metric | Original | Improved | Difference |
|---|---:|---:|---:|
| Processing time | unchanged pipeline (baseline table above) | — | no encoding change this round |
| Output size | unchanged pipeline | — | — |
| CPU usage | unchanged pipeline | — | — |
| Peak RAM | bot 303 MiB observed | — | — |
| Queue waiting time | queue-position query 0.05 ms (idle) | — | — |
| Failure rate | 193 ok / 17 failed lifetime, 0 failures today | — | — |
| **Bugs shipped to users** | level-flow dead, cancel 500, sweep crash every 10 min | 0 | fixed |
| **Hot DB queries** | sub-ms before and after | — | — |

## H. Testing Results

| Suite | Local (Windows venv) | Server (/tmp/oxmit-test-venv) |
|---|---|---|
| Full suite `pytest tests -q` | **145 passed / 0 failed** | **145 passed / 0 failed** |
| New this round | +5 (4 router-registration, 1 tuner-retry) | same |

- Suite growth this session: 116 → 145 (+ cache-offer/quality tests from the previous round).
- Migration `011_cache_reuse.sql`: applied to a disposable postgres:17 restored from the **real production dump** — verified backfill (166 derivatives flagged), new columns/index/counters, idempotent re-apply. **Applied to production on 2026-11-05 19:40 UTC** during the approved container rebuild (11/11 migrations).
- **Production activation (owner-approved):** `oxmit/bot:local` image rebuilt (previous image tagged `oxmit/bot:rollback-20261105`), container recreated. Verified post-deploy: new log lines active, healthz all-green (`postgres/encore/bot_api/redis ok`), a recovered in-flight job completed its encode under the new code, CPU tuner active with **zero** failed updates.
- One self-caught regression during rollout: the audit's suggested `container.update(NanoCPUs=...)` does not exist in docker-py 7.x (`update_container` exposes only cpu_period/quota, which conflict with compose-set NanoCPUs). Reverted to the deliberate low-level `NanoCPUs` post (now documented in-code), kept the partial-update retry. Lesson recorded: audit suggestions are hypotheses until validated against the installed dependency versions.
- Not executed: live end-to-end cache-offer interaction over Telegram (the feature path is covered by 24 unit/integration-style tests; a real user upload will exercise it next), browser-based panel test.

## I. Remaining Technical Debt

1. **`jobs.source_path` stores token-bearing bot-api paths** — redaction covers logs/errors, not the column. Fix = resolve paths from `media_id` at run time (touches staging/refetch; medium risk) — deliberately deferred.
2. **`engine.py` (2,837 lines) remains a god-object** — split plan exists (architecture doc §7); blocked on committing the in-flight uncommitted tuning work first.
3. **Panel login-throttle state still duplicated** per app (lockout budget effectively doubled) — sessions were unified; throttles need the same treatment.
4. **Dead decision_engine outputs** (adaptive-resolution/audio-copy computed, never consumed; `custom_2pass` unreachable) — user's uncommitted work in this area; left untouched.
5. **No CI** — tests must be run manually (venv recipe documented); containerized test target still outstanding.
6. **No git remote / backups host-local** — single point of failure on the Lightsail box (operational, not code).
7. `.env.example` drift (11 vars) — flagged, not yet fixed.
8. ~18 dead texts.py keys + hardcoded panel strings + `except Exception: pass` normalization — cosmetic sweep deferred.

## J. Production Readiness Assessment

| Dimension | Rating | Evidence |
|---|---|---|
| Architecture | **B+** | Sound single-node design, Postgres-delegated concurrency; god-object engine holds it back |
| Reliability | **B+** (was C+) | Dead primary flow + sweep crash + stuck-on-shutdown all fixed; recovery paths verified |
| Performance | **B+** | Encode path already measured/tuned in prior campaigns; DB hot-query indexes verified this round (results pending) |
| Security | **B** (was C+) | TLS fail-closed, file-read containment, session unification, ownership checks; docker.sock + public panel remain inherent trade-offs (documented) |
| Scalability | **B−** | Worker tier scales; bot is single-process by design (adequate for one server) |
| Maintainability | **B** | 145-test suite with regression pins; duplication reduced; god-object + dead code remain |
| Testing | **B+** | 145/145 local+server, migration tested on real-data copy; no CI, no E2E |
| Observability | **B** | Structured JSON logging, audit trail, healthz; misleading messages fixed |

**Overall: production-ready for its actual scale (single-server community bot), conditional on:** (1) restarting the bot container to activate all deployed fixes, (2) adding a git remote + off-host backups.

## K. Final Recommendations (high-value only)

1. **Restart `oxmit-bot` to activate the deployed fixes** (the CRITICAL level-flow fix matters to every user; migration is idempotent and was rehearsed on a real dump). Approve and it happens.
2. **Commit everything + add a git remote** — the repo's only copy is this server, with days of uncommitted work (yours and the fixes).
3. **Set `BACKUP_RCLONE_TARGET`** — backups currently live only on the same disk they protect.
4. Add a **containerized CI job** running `pytest tests -q` (the suite is now regression-pinned enough to gate deploys).
5. Schedule the `engine.py` split and `source_path` de-tokenization as the next refactor round — after committing, so there's a clean revert point.
