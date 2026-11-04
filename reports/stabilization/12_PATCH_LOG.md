# Patch Log

1. **`deploy/wrapper/ffmpeg`**: Staged file mode change to `100755` (`+x`).
2. **`bot/oxmit/media.py`**: Added file unlinking in `remux_to_mp4`, `download_thumbnail`, and `extract_thumbnail`.
3. **`bot/oxmit/engine.py`**: Added unhandled exception logging in `spawn`, immediate thumbnail purge in `_cleanup_job_dirs`, and `jobs.source_path` update in `_refetch_source`.
4. **`bot/oxmit/handlers/adminpanel.py`**: Added `from_user` None guard in `_has_pending`.
5. **`bot/oxmit/internal_api.py` & `bot/oxmit/bot.py`**: Returned both app runners and added graceful cancellation and cleanup in shutdown sequence.
6. **`tests/test_engine_fixes.py`**: Removed obsolete `xfail` markers.
7. **`tests/`**: Added 17 new regression and unit tests.
