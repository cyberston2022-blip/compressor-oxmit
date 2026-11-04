"""Tests for engine task exception reporting, source refetching, and thumbnail cleanup."""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from oxmit.config import Settings
from oxmit.engine import JobEngine


@pytest.mark.asyncio
async def test_spawn_logs_exception(fake_db, tmp_path, caplog):
    cfg = Settings(media_root=str(tmp_path))
    eng = JobEngine(fake_db, cfg, object(), object())

    async def _failing_coro():
        await asyncio.sleep(0.01)
        raise ValueError("test-spawn-crash")

    eng.spawn(_failing_coro())
    await asyncio.sleep(0.05)

    assert any("unhandled exception in spawned task" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_cleanup_job_dirs_removes_thumbnail(fake_db, tmp_path):
    cfg = Settings(media_root=str(tmp_path))
    eng = JobEngine(fake_db, cfg, object(), object())

    thumb_dir = Path(cfg.media_tmp)
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb = thumb_dir / "thumb-testjob12345.jpg"
    thumb.write_bytes(b"dummy-thumb")

    await eng._cleanup_job_dirs("testjob12345678", keep_output=False)
    assert not thumb.exists(), "thumb file must be removed by _cleanup_job_dirs"


@pytest.mark.asyncio
async def test_refetch_source_updates_jobs_table(fake_db, tmp_path):
    cfg = Settings(media_root=str(tmp_path))
    bot = MagicMock()
    botapi_src = tmp_path / "botapi" / "videos" / "file.mp4"
    botapi_src.parent.mkdir(parents=True, exist_ok=True)
    botapi_src.write_bytes(b"video-bytes")

    tg_file = MagicMock()
    tg_file.file_path = str(botapi_src)
    bot.get_file = AsyncMock(return_value=tg_file)

    eng = JobEngine(fake_db, cfg, bot, object())
    eng.resolve_local_path = AsyncMock(return_value=botapi_src)

    fake_db.on_fetchrow(
        lambda sql: "FROM media_assets" in sql,
        {"tg_file_id": "file-123", "filename": "sample.mp4"},
    )

    row = {"id": "11111111-1111-1111-1111-111111111111", "media_id": "22222222-2222-2222-2222-222222222222"}
    stable = await eng._refetch_source(row)
    assert stable is not None
    assert stable.is_file()

    # Verify both media_assets and jobs were updated
    updates = [e for e in fake_db.executed if e[0] == "execute"]
    assert any("UPDATE media_assets SET sha256" in u[1] for u in updates)
    assert any("UPDATE jobs SET source_path" in u[1] for u in updates)
