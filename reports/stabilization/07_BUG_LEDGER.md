# Bug Ledger & Findings

### BUG-001 [CRITICAL] — FFmpeg wrapper missing executable mode (+x)
- **Status:** FIXED
- **Impact:** Blocked 100% of encoding jobs on 2026-11-04.
- **Fix:** chmod +x and git update-index --chmod=+x deploy/wrapper/ffmpeg.

### BUG-002 [HIGH] — Ungraceful shutdown in bot.py
- **Status:** FIXED
- **Impact:** Stale asyncpg interface errors and dangling web runners on stop.
- **Fix:** Cancel background tasks, cleanup aiohttp runners, close bot session.

### BUG-003 [MEDIUM] — Destination files left on failed FFmpeg remux/thumbnail
- **Status:** FIXED
- **Impact:** Disk clutter and risk of treating 0-byte files as valid outputs.
- **Fix:** Added missing_ok=True unlinking in error and timeout paths.

### BUG-004 [MEDIUM] — Silent task exceptions in JobEngine.spawn
- **Status:** FIXED
- **Impact:** Unretrieved background task exceptions in asyncio loop.
- **Fix:** Added done callback logging unhandled exceptions.

### BUG-005 [MEDIUM] — Lingering thumbnail files in media_tmp
- **Status:** FIXED
- **Impact:** Thumbnails remained until 24h sweep instead of immediate cleanup.
- **Fix:** Added immediate unlinking in _cleanup_job_dirs.

### BUG-006 [MEDIUM] — Vanished source refetch omitted jobs.source_path update
- **Status:** FIXED
- **Impact:** Retrying jobs after vanished source pointed to old invalid path.
- **Fix:** Added UPDATE jobs SET source_path = $2.

### BUG-007 [LOW] — Potential AttributeError in admin message filter
- **Status:** FIXED
- **Impact:** Channel posts could cause NoneType error on from_user.id.
- **Fix:** Guarded with if not message.from_user: return False.
