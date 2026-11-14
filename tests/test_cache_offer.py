"""Cache delivery helper (deliver_cached_offer): explicit acceptance
delivery of an already-archived result.

Engine-level tests on JobEngine + FakeDB; Telegram and ffprobe boundaries
are stubbed. The FakeDB gains a minimal pool.acquire() shim because
handle_submission runs its dedup checks inside a real transaction.
"""
import asyncio
import uuid as uuid_mod
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from oxmit.media import MediaError  # noqa: F401  (import path sanity)

SHA = "a" * 64
MEDIA_ID = uuid_mod.uuid4()


# ---------------------------------------------------------------------------
# FakeDB transaction shim
# ---------------------------------------------------------------------------

class _FakeConn:
    def __init__(self, db):
        self.db = db

    @asynccontextmanager
    async def transaction(self):
        yield

    async def execute(self, sql, *args):
        return await self.db.execute(sql, *args)

    async def fetchval(self, sql, *args):
        return await self.db.fetchval(sql, *args)

    async def fetch(self, sql, *args):
        return await self.db.fetch(sql, *args)

    async def fetchrow(self, sql, *args):
        return await self.db.fetchrow(sql, *args)


@pytest.fixture
def tx_db(fake_db):
    """FakeDB with a pool.acquire() that yields a conn delegating to it."""

    @asynccontextmanager
    async def acquire():
        yield _FakeConn(fake_db)

    fake_db.pool = SimpleNamespace(acquire=acquire)
    return fake_db


class StubBot:
    def __init__(self, file_path="downloads/source.mp4", fail_get_file=False):
        self.file_path = file_path
        self.fail_get_file = fail_get_file
        self.get_file_calls = []

    async def get_file(self, file_id):
        self.get_file_calls.append(file_id)
        if self.fail_get_file:
            from aiogram.exceptions import TelegramAPIError
            raise TelegramAPIError("getFile", "file not found")
        return SimpleNamespace(file_path=self.file_path)


def _users_row():
    return {"language": "fa", "is_blocked": False, "is_vip": False,
            "max_source_gb": None, "max_duration_min": None,
            "daily_quota_gb": None}


def _script_admission(fake_db):
    fake_db.on_fetchrow(lambda sql: "FROM users" in sql, _users_row())
    fake_db.on_fetchval(lambda sql: "status IN ('queued','processing','deferred')" in sql, 0)
    fake_db.on_fetchval(lambda sql: "interval '1 hour'" in sql, 0)
    fake_db.on_fetchval(lambda sql: "interval '24 hours'" in sql and "sum" not in sql, 0)
    fake_db.on_fetchval(
        lambda sql: "status IN ('queued','processing','deferred','completed')" in sql, 0)
    fake_db.on_fetchval(lambda sql: "sum(source_size)" in sql, 0)
    fake_db.on_fetchval(lambda sql: "status = 'queued'" in sql, 0)
    fake_db.on_fetchval(lambda sql: "sum(reserved_bytes)" in sql, 0)


def _probe(**over):
    base = {"duration_s": 600.0, "width": 1920, "height": 1080, "fps": 30.0,
            "vcodec": "h264", "acodec": "aac", "audio_channels": 2,
            "container": "mp4", "bitrate": 4_000_000, "size_bytes": 3 * 1024**3}
    base.update(over)
    return base


def _archive_row(**over):
    row = {"id": uuid_mod.uuid4(), "source_media_id": MEDIA_ID,
           "output_media_id": uuid_mod.uuid4(), "channel_id": -100,
           "message_id": 55, "status": "active", "file_unique_id": "u",
           "created_at": 0, "part_index": 0, "part_total": 1,
           "source_sha256": SHA, "output_size": 80 * 1024**2,
           "output_tg_file_id": "out-fid", "source_tg_file_id": "src-fid",
           "source_size": 3 * 1024**3}
    row.update(over)
    return row


def _cached_row(profile="r480", **over):
    row = {"id": uuid_mod.uuid4(), "profile": profile, "profile_version": 1,
           "status": "active", "part_index": 0, "part_total": 1,
           "created_at": 1, "out_w": 854, "out_h": 480, "out_duration": 600.0,
           "out_size": 85 * 1024**2, "out_vcodec": "h264", "out_acodec": "aac",
           "out_bitrate": 900_000, "out_tg_file_id": "out-fid"}
    row.update(over)
    return row


async def _drain_bg(engine):
    for _ in range(3):
        await asyncio.sleep(0)
    for t in list(engine._bg_tasks):
        try:
            await asyncio.wait_for(t, timeout=1)
        except Exception:  # noqa: BLE001 - background best-effort
            pass


@pytest.fixture
def media_env(engine, tx_db, monkeypatch, tmp_path):
    """Stub every boundary handle_submission touches before dedup."""
    engine.state.archive_channel_id = -100123
    src = tmp_path / "source.mp4"
    src.write_bytes(b"0" * 1024)

    async def fake_probe(path):
        return _probe()

    async def fake_sha(path):
        return SHA

    monkeypatch.setattr("oxmit.media.probe_video", fake_probe)
    monkeypatch.setattr("oxmit.media.sha256_file", fake_sha)
    engine.bot = StubBot()

    async def fake_resolve(file_path):
        return src

    monkeypatch.setattr(engine, "resolve_local_path", fake_resolve)
    monkeypatch.setattr(engine, "_disk_free", lambda: 1 << 40)
    tx_db.on_fetchval(lambda sql: "INSERT INTO media_assets" in sql, MEDIA_ID)
    return src


# Interactive multi-profile cache offers were removed with the single
# EDU480 profile (cached results are now delivered directly, see
# test_integration_pg.py). The explicit-acceptance delivery helper
# remains and is covered here.

async def test_deliver_cached_offer_accepts_and_bumps(engine, fake_db):
    engine.bot = StubBot()
    fake_db.on_fetch(
        lambda sql: "FROM archive_records ar" in sql, [_archive_row()])
    fake_db.on_fetchval(lambda sql: "SELECT language FROM users" in sql, "fa")
    fake_db.on_fetchrow(lambda sql: "SELECT language, delivery_style" in sql,
                        {"language": "fa", "delivery_style": "video",
                         "notify_done": True, "show_meta": True,
                         "thumbnail_file_id": None})
    result = await engine.deliver_cached_offer(
        sha=SHA, profile_key="r480", profile_version=1, reuse_kind="exact",
        tg_id=7, chat_id=None, status_msg_id=None, size_bytes=3 * 1024**3,
    )
    # chat_id=None skips the background delivery entirely; the reuse
    # bookkeeping (job row, reuse_count, dedup counter) still runs sync:
    assert result["outcome"] == "reused"
    assert result["delivered"] is False
    # The user explicitly accepted the offer, so acceptance is counted even
    # though the delivery itself is scheduled (2026-11-14 stabilization):
    assert any(e[1] == "cache_accepted" for e in fake_db.bumps()), \
        "explicit acceptance must count cache_accepted"
    assert any("reuse_count = reuse_count + 1" in e[1] for e in fake_db.executed)
    assert any(e[1] == "dedup_exact_reuse" for e in fake_db.bumps())


async def test_deliver_cached_offer_gone_when_archive_invalidated(engine, fake_db):
    engine.bot = StubBot()
    fake_db.on_fetch(lambda sql: "FROM archive_records ar" in sql, [])
    result = await engine.deliver_cached_offer(
        sha=SHA, profile_key="r480", profile_version=1, reuse_kind="exact",
        tg_id=7, chat_id=100, status_msg_id=None, size_bytes=3 * 1024**3,
    )
    assert result["outcome"] == "cache_gone"
    assert not any("INSERT INTO jobs" in e[1] for e in fake_db.executed)
    assert not any(e[1] == "cache_accepted" for e in fake_db.bumps())
