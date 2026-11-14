"""Regression tests for the 2026-11-14 stabilization release (MEGA TASK 06).

Covers: bot-api file readability at staging (P0 production bug), canonical
Owner identity (fail-closed, no hardcode / no first-admin), duration never
rendered as 00:00:00, non-blocking reuse delivery, predictive no-gain
guard, removed unsafe panel endpoints, config validation.
"""
import asyncio
import json
import os
import stat
from types import SimpleNamespace

import pytest

from oxmit import archive as archive_mod
from oxmit import edu480
from oxmit.panel.bot_manager import get_bot_config, update_bot_config
from oxmit.panel.security import is_owner_session, require_owner  # noqa: F401


# ---------------------------------------------------------------------------
# FIX-1: bot-api staging readability (root cause of the failed real job:
# bot-api creates dirs 0750 / files 0600; the worker reads them as uid 1000)
# ---------------------------------------------------------------------------

async def test_make_botapi_readable_chmods_dirs_and_file(engine, tmp_path):
    botapi = tmp_path / "botapi"
    tokdir = botapi / "token-dir"
    videos = tokdir / "videos"
    videos.mkdir(parents=True)
    f = videos / "file_0.mp4"
    f.write_bytes(b"x" * 10)
    os.chmod(botapi, 0o750)
    os.chmod(tokdir, 0o750)
    os.chmod(videos, 0o750)
    os.chmod(f, 0o600)
    engine.cfg.botapi_dir = str(botapi)

    engine._make_botapi_readable(f)

    assert stat.S_IMODE(videos.stat().st_mode) == 0o777
    assert stat.S_IMODE(tokdir.stat().st_mode) == 0o777
    # the botapi mount root itself stays 750 (it is outside the token tree;
    # in production it is the volume mountpoint created by docker)
    assert stat.S_IMODE(botapi.stat().st_mode) == 0o750
    assert stat.S_IMODE(f.stat().st_mode) == 0o644


async def test_make_botapi_readable_never_touches_outside_botapi(engine, tmp_path):
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"x")
    os.chmod(outside, 0o600)
    engine.cfg.botapi_dir = str(tmp_path / "botapi")   # different tree

    engine._make_botapi_readable(outside)

    assert stat.S_IMODE(outside.stat().st_mode) == 0o600


async def test_stage_source_symlink_grants_worker_read(engine, tmp_path):
    botapi = tmp_path / "botapi"
    tokdir = botapi / "token-dir"
    videos = tokdir / "videos"
    videos.mkdir(parents=True)
    src = videos / "file_0.mp4"
    src.write_bytes(b"video-bytes")
    os.chmod(tokdir, 0o750)
    os.chmod(videos, 0o750)
    os.chmod(src, 0o600)
    engine.cfg.botapi_dir = str(botapi)
    engine.cfg.workers_read_botapi = True

    staged = await engine._stage_source("job-x", src, "clip.mp4")

    from pathlib import Path
    staged_p = Path(staged)
    assert staged_p.is_symlink()
    # the worker (uid 1000) resolves the symlink target through its ro mount;
    # with the chmods applied the chain must be traversal+read accessible:
    assert stat.S_IMODE(src.stat().st_mode) == 0o644
    assert stat.S_IMODE(videos.stat().st_mode) == 0o777
    assert staged_p.read_bytes() == b"video-bytes"


# ---------------------------------------------------------------------------
# FIX-2: canonical Owner identity — fail closed, no hardcode, no fallback
# ---------------------------------------------------------------------------

def test_is_owner_session_fail_closed_without_owner_config():
    session = {"role": "owner", "tg_id": None, "actor": "owner:token"}
    assert is_owner_session(session, None) is False
    assert is_owner_session(session, 0) is False


def test_is_owner_session_matches_configured_owner_only():
    session = {"role": "owner", "tg_id": 424242, "actor": "owner:424242"}
    assert is_owner_session(session, 424242) is True
    assert is_owner_session(session, 999999) is False


def test_is_owner_session_rejects_non_owner_role():
    session = {"role": "admin", "tg_id": 424242, "actor": "admin:424242"}
    assert is_owner_session(session, 424242) is False


async def test_engine_is_owner_has_no_first_admin_fallback(engine):
    # Even when administrators exist in the DB, without OWNER_TELEGRAM_ID
    # nobody is the owner (no privilege elevation via insertion order).
    engine.cfg.owner_telegram_id = 0
    engine.db.on_fetch(lambda sql: "FROM users WHERE is_admin" in sql,
                       [{"tg_id": 111}])
    assert await engine.is_owner(111) is False
    engine.cfg.owner_telegram_id = 424242
    assert await engine.is_owner(424242) is True
    assert await engine.is_owner(111) is False


async def test_support_owner_routing_is_config_only(engine, fake_db):
    from oxmit.handlers import support as support_mod
    cfg = SimpleNamespace(owner_telegram_id=0)
    assert await support_mod.owner_id(engine, cfg) is None
    cfg = SimpleNamespace(owner_telegram_id=555)
    assert await support_mod.owner_id(engine, cfg) == 555


# ---------------------------------------------------------------------------
# FIX-4: unknown duration must never render as 00:00:00
# ---------------------------------------------------------------------------

def test_summary_text_unknown_duration(engine):
    text = engine._summary_text(
        "fa", job_id="abcdef12", profile="edu480", filename="v.mp4",
        source_size=1000, output_size=900,
        probe={"width": 640, "height": 480},   # no duration_s at all
        started=None, completed=None, new=True,
    )
    assert "نامشخص" in text
    assert "00:00" not in text
    assert ":00" not in text.split("مدت")[1].split("\n")[0]


def test_summary_text_known_duration(engine):
    text = engine._summary_text(
        "fa", job_id="abcdef12", profile="edu480", filename="v.mp4",
        source_size=1000, output_size=900,
        probe={"width": 640, "height": 480, "duration_s": 125.0},
        started=None, completed=None, new=True,
    )
    assert "2:05" in text


def test_build_caption_unknown_duration():
    cap = archive_mod.build_caption(
        "v.mp4", "EDU480", {"width": 640, "height": 480, "vcodec": "h264",
                            "acodec": "aac", "duration_s": None},
        source_size=1000, output_size=500, job_short="abcd1234",
    )
    assert "نامشخص" in cap
    assert "0:00" not in cap


# ---------------------------------------------------------------------------
# FIX-5: archive reuse delivery must not block the intake naming loop
# ---------------------------------------------------------------------------

class ReuseStubBot:
    """Minimal bot stub: records send calls instead of hitting Telegram."""

    def __init__(self):
        self.sends = []

    async def copy_message(self, **kw):
        self.sends.append(("copy_message", kw.get("chat_id")))
        return SimpleNamespace(message_id=321)

    async def send_video(self, **kw):
        self.sends.append(("send_video", kw.get("chat_id")))
        return SimpleNamespace(message_id=322, video=SimpleNamespace(file_id="f"))

    async def edit_message_text(self, **kw):
        self.sends.append(("edit", kw.get("chat_id")))
        return SimpleNamespace(message_id=1)

    async def edit_message_caption(self, **kw):
        return SimpleNamespace(message_id=1)


async def test_reuse_archive_returns_without_delivering_inline(engine, fake_db):
    engine.bot = ReuseStubBot()
    fake_db.on_fetch(
        lambda sql: "FROM archive_records ar" in sql and "JOIN media_assets ms" in sql,
        [{
            "id": "aaaaaaaa-0000-0000-0000-000000000000",
            "source_media_id": "bbbbbbbb-0000-0000-0000-000000000001",
            "output_media_id": "bbbbbbbb-0000-0000-0000-000000000002",
            "channel_id": -100123, "message_id": 77, "status": "active",
            "file_unique_id": "u1", "created_at": None, "part_index": 0,
            "part_total": 1, "profile_version": 2,
            "source_sha256": "s" * 64, "output_size": 123,
            "output_tg_file_id": "out-file-id", "source_tg_file_id": "src-file-id",
            "source_size": 5000,
        }])
    fake_db.on_fetchval(lambda sql: "INSERT INTO jobs" in sql,
                        "cccccccc-0000-0000-0000-000000000000")
    fake_db.on_fetchval(lambda sql: "SELECT language FROM users" in sql, "fa")
    fake_db.on_fetchrow(lambda sql: "SELECT language, delivery_style" in sql,
                        {"language": "fa", "delivery_style": "video",
                         "notify_done": True, "show_meta": True,
                         "thumbnail_file_id": None})

    class FakeRecord(dict):
        pass

    part = FakeRecord({
        "id": "aaaaaaaa-0000-0000-0000-000000000000",
        "source_media_id": "bbbbbbbb-0000-0000-0000-000000000001",
        "output_media_id": "bbbbbbbb-0000-0000-0000-000000000002",
        "channel_id": -100123, "message_id": 77, "status": "active",
        "file_unique_id": "u1", "created_at": None, "part_index": 0,
        "part_total": 1, "profile_version": 2, "source_sha256": "s" * 64,
        "output_size": 123, "output_tg_file_id": "out-file-id",
        "source_tg_file_id": "src-file-id", "source_size": 5000,
        "message_id": 77,
    })

    result = await engine._reuse_archive(
        [part], tg_id=7, chat_id=100, status_msg_id=55,
        profile_key="edu480", sha="s" * 64, size_bytes=5000,
        reuse_kind="exact",
    )

    # The call returns immediately: no Telegram send happened inline.
    assert result["outcome"] == "reused"
    assert result["delivered"] is False
    assert engine.bot.sends == []

    # Let the spawned delivery task run:
    for _ in range(5):
        await asyncio.sleep(0)
    assert any(s[0] == "copy_message" and s[1] == 100 for s in engine.bot.sends), \
        "the background task must deliver the archived result"
    # Deliveries row written by the task (with the post-send message id):
    assert any("INSERT INTO deliveries" in e[1] for e in fake_db.executed)
    assert any(e[0] == "bump" and e[1] == "deliveries_ok" for e in fake_db.executed)


# ---------------------------------------------------------------------------
# FIX-7: deterministic predictive no-gain guard
# ---------------------------------------------------------------------------

class GuardCfg:
    encode_predict_guard = True
    predict_no_gain_ratio = 0.98
    edu480_crf = 25
    edu480_audio_kbps = 64
    edu480_max_fps = 30
    edu480_compliant_kbps = 700


def _probe(w, h, fps, dur, video_kbps):
    return {"width": w, "height": h, "fps": fps, "duration_s": dur,
            "bitrate": video_kbps * 1000, "vcodec": "h264",
            "pix_fmt": "yuv420p", "acodec": "aac"}


def test_predict_guard_1080p_high_bitrate_still_encodes():
    # 1080p60 6 Mbps: EDU480 predicted output is far below the source.
    probe = _probe(1920, 1080, 30, 600.0, 6000)
    decision = edu480.predict_guard(probe, 450_000_000, GuardCfg())
    assert decision is None


def test_predict_guard_low_bpp_480p_delivers_source():
    # 480p at ~800 kbps: EDU480 target bitrate is ~ the same -> no-gain.
    probe = _probe(854, 480, 30, 60.0, 800)
    size = int(800 * 1000 / 8 * 60)   # ~6 MB
    decision = edu480.predict_guard(probe, size, GuardCfg())
    assert decision is not None
    assert decision.action == "deliver_source"
    assert "no-gain" in decision.reason


def test_predict_guard_disabled():
    cfg = GuardCfg()
    cfg.encode_predict_guard = False
    probe = _probe(854, 480, 30, 60.0, 800)
    size = int(800 * 1000 / 8 * 60)
    assert edu480.predict_guard(probe, size, cfg) is None


def test_predict_guard_never_fires_on_unknown_size():
    probe = _probe(854, 480, 30, 60.0, 800)
    assert edu480.predict_guard(probe, 0, GuardCfg()) is None


def test_edu480_compliant_source_is_remux_not_guard():
    # compliant sources route to remux BEFORE the guard is consulted
    probe = _probe(854, 480, 30, 60.0, 700)
    probe["pix_fmt"] = "yuv420p"
    d = edu480.decide(probe, int(700 * 1000 / 8 * 60), GuardCfg())
    assert d.action == "remux"


# ---------------------------------------------------------------------------
# FIX-3: panel config API is allowlisted (no arbitrary app_config writes,
# no private identifiers echoed to the browser)
# ---------------------------------------------------------------------------

class ConfigDB:
    def __init__(self):
        self.rows = [
            {"key": "access_mode", "value": '"private"'},
            {"key": "archive_channel_id", "value": "-1001234567890"},
            {"key": "limits", "value": '{"normal": {"max_per_hour": 10}}'},
            {"key": "paused", "value": "false"},
        ]
        self.written = []

    async def fetch(self, sql):
        return self.rows

    async def set_config(self, key, value):
        self.written.append((key, value))


async def test_get_bot_config_filters_private_keys():
    db = ConfigDB()
    state = SimpleNamespace(access_mode="private", paused=False, global_thumb=None)
    cfg = await get_bot_config(db, state)
    assert "archive_channel_id" not in cfg
    assert "limits" not in cfg
    assert cfg["access_mode"] == "private"
    assert cfg["paused"] is False


async def test_update_bot_config_rejects_unknown_keys():
    db = ConfigDB()
    state = SimpleNamespace(access_mode="private", paused=False, global_thumb=None)
    res = await update_bot_config(db, state, {"archive_channel_id": "-100evil"},
                                  actor="owner:1")
    assert res["status"] == "error"
    assert db.written == []


async def test_update_bot_config_accepts_allowlisted_keys():
    db = ConfigDB()
    state = SimpleNamespace(access_mode="private", paused=False, global_thumb=None)
    res = await update_bot_config(db, state, {"paused": True}, actor="owner:1")
    assert res["status"] == "ok"
    assert db.written == [("paused", True)]
    assert state.paused is True


# ---------------------------------------------------------------------------
# config validation
# ---------------------------------------------------------------------------

def test_predict_ratio_validation_bounds():
    from oxmit.config import Settings
    bad = Settings(predict_no_gain_ratio=1.5)
    errs = bad.validate()
    assert any("PREDICT_NO_GAIN_RATIO" in e for e in errs)
    good = Settings(predict_no_gain_ratio=0.98)
    assert all("PREDICT_NO_GAIN_RATIO" not in e for e in good.validate())
