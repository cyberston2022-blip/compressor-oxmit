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


