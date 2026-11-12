"""End-to-end lifecycle against a REAL PostgreSQL (opt-in).

Runs every migration, then drives the actual engine code: metadata-only
registration, in-flight join, fair dispatch, JIT download (stub Telegram),
ffprobe of a real generated video, EDU480 Encore submission (stub Encore),
completion with a real FFmpeg output, archive upload + copy delivery,
source cleanup, moderation and the dashboard queries.

    OXMIT_TEST_PG_DSN=postgresql://postgres@/oxmit?host=/var/tmp/oxsock&port=55432 pytest tests/test_integration_pg.py

Each run uses a fresh schema-less database it creates and drops.
"""
import asyncio
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

DSN = os.getenv("OXMIT_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(
    not DSN or not shutil.which("ffmpeg"),
    reason="set OXMIT_TEST_PG_DSN (and have ffmpeg) to run the PostgreSQL integration test")


class StubBot:
    """Records Telegram calls; get_file 'downloads' by copying a fixture."""

    def __init__(self, botapi_dir: Path, fixture: Path):
        self.calls = []
        self.botapi_dir = botapi_dir
        self.fixture = fixture
        self.fail_uploads = 0
        self._mid = 1000

    def _msg(self, **kw):
        self._mid += 1
        return SimpleNamespace(message_id=self._mid, **kw)

    async def get_file(self, file_id):
        self.calls.append(("get_file", file_id))
        rel = f"TOKEN/videos/{file_id}.mp4"
        dst = self.botapi_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.fixture, dst)
        return SimpleNamespace(file_path=rel)

    async def send_video(self, **kw):
        self.calls.append(("send_video", kw.get("chat_id")))
        if self.fail_uploads > 0:
            self.fail_uploads -= 1
            from aiogram.exceptions import TelegramNetworkError
            raise TelegramNetworkError(method=None, message="simulated network error")
        return self._msg(video=SimpleNamespace(file_id="OUTFID", file_unique_id="OUTUNIQ"))

    async def copy_message(self, **kw):
        self.calls.append(("copy_message", kw.get("chat_id"), kw.get("from_chat_id")))
        return self._msg()

    async def forward_message(self, **kw):
        self.calls.append(("forward_message", kw.get("chat_id")))
        return self._msg()

    def __getattr__(self, name):
        async def _rec(*a, **kw):
            self.calls.append((name, a, kw))
            return self._msg()
        return _rec


class StubEncre:
    def __init__(self):
        self.submitted = []
        self.cancelled = []

    async def submit_job(self, **kw):
        self.submitted.append(kw)
        return f"enc-{len(self.submitted)}"

    async def cancel_job(self, encore_id):
        self.cancelled.append(encore_id)

    async def queue_count(self):
        return 0


def _make_video(path: Path, w=1280, h=720, fps=60, seconds=2):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc2=size={w}x{h}:rate={fps}", "-f", "lavfi", "-i",
                    "sine=frequency=440", "-t", str(seconds), "-c:v", "libx264",
                    "-preset", "ultrafast", "-b:v", "3M", "-c:a", "aac", "-shortest",
                    str(path)], check=True)


@pytest.fixture
async def env(tmp_path):
    import asyncpg

    from oxmit.config import Settings
    from oxmit.db import Database
    from oxmit.engine import JobEngine

    dbname = "oxit_" + uuid.uuid4().hex[:8]
    admin = await asyncpg.connect(DSN)
    await admin.execute(f"CREATE DATABASE {dbname}")
    dsn = DSN.replace("/oxmit", f"/{dbname}")
    db = Database(dsn)
    await db.connect()  # runs ALL migrations incl. 015
    botapi = tmp_path / "botapi"
    fixture = tmp_path / "fixture.mp4"
    _make_video(fixture)
    cfg = Settings(media_root=str(tmp_path / "media"), botapi_dir=str(botapi),
                   worker_replicas=2, owner_telegram_id=1, max_jobs_per_day=100,
                   workers_read_botapi=True)
    for d in ("incoming", "out", "tmp"):
        Path(cfg.media_root, d).mkdir(parents=True, exist_ok=True)
    bot = StubBot(botapi, fixture)
    encre = StubEncre()
    engine = JobEngine(db, cfg, bot, encre)
    engine.state.archive_channel_id = -1001
    engine._disk_free = lambda: 500 * 1024**3
    engine.kick_dispatch = lambda: None  # tests drive dispatch explicitly
    for uid, name in ((1, "owner"), (10, "alice"), (20, "bob")):
        await db.execute("INSERT INTO users(tg_id, first_name, username, is_admin) "
                         "VALUES ($1,$2,$2,$3)", uid, name, uid == 1)
    yield SimpleNamespace(db=db, engine=engine, bot=bot, encre=encre, cfg=cfg)
    for t in list(engine._bg_tasks):
        t.cancel()
    await asyncio.gather(*engine._bg_tasks, return_exceptions=True)
    await db.close()
    await admin.execute(f"DROP DATABASE {dbname}")
    await admin.close()


async def _register(engine, tg, n, size=50 << 20, dur=120.0):
    return await engine.register_job(
        tg_id=tg, chat_id=tg, source_msg_id=100 + n, status_msg_id=200 + n,
        file_id=f"FID{tg}_{n}", file_unique_id=f"UQ{tg}_{n}", size_bytes=size,
        filename=f"lecture {n}.mkv", mime="video/x-matroska", duration_s=dur,
        width=1280, height=720, output_name=f"درس {n}.mp4")


async def _settle(engine):
    for _ in range(50):
        await asyncio.sleep(0.05)
        if not engine._pipelines:
            break


async def test_full_lifecycle(env):
    e, db = env.engine, env.db
    # --- registration is metadata only (no getFile) ---------------------
    r1 = await _register(e, 10, 1)
    r2 = await _register(e, 10, 2)
    r3 = await _register(e, 20, 1)
    assert [r["outcome"] for r in (r1, r2, r3)] == ["queued"] * 3
    assert not [c for c in env.bot.calls if c[0] == "get_file"]
    assert (r1["position"], r2["position"], r3["position"]) == (1, 2, 3)
    assert r3["ahead"] == 2 and r3["eta_high"] >= r3["eta_low"] > 0
    row = await db.fetchrow("SELECT output_name, source_filename, profile, profile_version "
                            "FROM jobs WHERE id = $1", uuid.UUID(r1["job_id"]))
    assert row["output_name"] == "درس 1" and row["profile"] == "edu480"
    assert row["profile_version"] == 2 and row["source_filename"] == "lecture 1.mkv"
    # same Telegram file again -> joins the in-flight job, no new row
    j = await e.register_job(tg_id=20, chat_id=20, source_msg_id=999, status_msg_id=998,
                             file_id="FIDX", file_unique_id="UQ10_1", size_bytes=1,
                             filename="x.mp4", output_name="x")
    assert j == {"outcome": "joined", "job_id": r1["job_id"]}

    # --- fair dispatch: alice#1, then bob (alice already has a slot) -----
    e.cfg.encode_slots = 2
    e._pipelines.clear()
    claimed = await e.dispatch_once()
    assert claimed == 2
    rows = await db.fetch("SELECT id, requester_tg_id FROM jobs WHERE status='processing'")
    assert sorted(r["requester_tg_id"] for r in rows) == [10, 20]
    await _settle(e)
    # pipeline downloaded, probed, hashed and submitted EDU480 to Encore
    assert len(env.encre.submitted) == 2
    sub = env.encre.submitted[0]
    assert sub["profile"] == "edu480"
    assert sub["profile_params"]["vf"] == "scale=854:480:flags=lanczos"
    assert sub["profile_params"]["fpsf"] == "fps=30"
    assert "TOKEN" not in sub["input_uri"]  # token-bearing path never reaches Encore
    assert Path(sub["input_uri"]).is_symlink()
    st = await db.fetchrow("SELECT stage, encode_started_at, download_done_at FROM jobs "
                           "WHERE id = $1", uuid.UUID(r1["job_id"]))
    assert st["stage"] == "encoding" and st["encode_started_at"] and st["download_done_at"]
    # slots full -> nothing more claimed
    assert await e.dispatch_once() == 0

    # --- dashboard queries run on real SQL --------------------------------
    from oxmit import dashboard
    for view in dashboard.VIEWS:
        data = await dashboard.jobs_view(db, view, q=None, user=None)
        assert "items" in data
    q = await dashboard.jobs_view(db, "queue")
    assert q["total"] == 1 and q["items"][0]["position"] == 1
    flt = await dashboard.jobs_view(db, "all", user="@alice", q="lecture", dfrom="2000-01-01")
    assert flt["total"] == 2
    assert (await dashboard.users_view(db))["items"]
    sysv = await dashboard.system_view(e, db, e.cfg, e.state)
    assert sysv["slots_busy"] == 2 and sysv["queued"] == 1
    assert (await dashboard.job_detail(db, r1["job_id"]))["requesters"]

    # --- completion: upload fails once -> retried WITHOUT re-encode -------
    del e.kick_dispatch  # real auto-dispatch from here on
    jid = r1["job_id"]
    out = Path(e.cfg.media_out) / jid
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(env.bot.fixture), "-vf",
                    "scale=854:480,fps=30", "-c:v", "libx264", "-preset", "ultrafast",
                    "-crf", "35", "-c:a", "aac", "-b:a", "64k", str(out / "out.mp4")], check=True)
    env.bot.fail_uploads = 3  # _archive_upload's own 3 attempts all fail
    orig_sleep = asyncio.sleep

    async def fast_sleep(s, *a, **k):
        await orig_sleep(0)
    asyncio.sleep = fast_sleep
    try:
        full = await db.fetchrow("SELECT j.*, m.duration_s AS source_duration FROM jobs j "
                                 "JOIN media_assets m ON m.id = j.media_id WHERE j.id = $1",
                                 uuid.UUID(jid))
        await e.complete_job(full, {"id": "enc-1"})
        st = await db.fetchrow("SELECT status, stage, upload_attempts FROM jobs WHERE id=$1",
                               uuid.UUID(jid))
        assert (st["status"], st["stage"], st["upload_attempts"]) == ("processing", "upload_retry", 1)
        assert (out / "درس 1.mp4").is_file()  # output kept for the retry
        # the slot was freed at encode end: the queued job got claimed
        assert await db.fetchval("SELECT count(*) FROM jobs WHERE status='queued'") == 0
        for _ in range(100):  # scheduled resume_upload runs
            await orig_sleep(0.02)
            if await db.fetchval("SELECT delivered_at FROM jobs WHERE id=$1", uuid.UUID(jid)):
                break
    finally:
        asyncio.sleep = orig_sleep
    done = await db.fetchrow("SELECT * FROM jobs WHERE id = $1", uuid.UUID(jid))
    assert done["status"] == "completed" and done["delivered_at"] is not None
    assert len(env.encre.submitted) == 3  # 2 initial + claimed queued job; no re-encode of jid
    # delivered by copy (never forward), to BOTH requesters (alice + joined bob)
    copies = [c for c in env.bot.calls if c[0] == "copy_message" and c[2] == -1001]
    assert {c[1] for c in copies} >= {10, 20}
    assert not [c for c in env.bot.calls if c[0] == "forward_message"]
    ar = await db.fetchrow("SELECT * FROM archive_records WHERE output_media_id = $1",
                           done["output_media_id"])
    assert ar["status"] == "active" and ar["profile"] == "edu480"
    # Local Bot API source deleted after delivery
    assert not Path(done["source_path"]).exists()

    # --- early recognition: same Telegram file later -> reuse, no download
    gets = len([c for c in env.bot.calls if c[0] == "get_file"])
    reuse = await e.register_job(tg_id=20, chat_id=20, source_msg_id=5000, status_msg_id=5001,
                                 file_id="FIDZ", file_unique_id="UQ10_1", size_bytes=1,
                                 filename="again.mp4", output_name="again")
    assert reuse["outcome"] == "reused"
    # our own output sent back -> recognized as known output
    known = await e.register_job(tg_id=20, chat_id=20, source_msg_id=5002, status_msg_id=5003,
                                 file_id="OUTFID", file_unique_id="OUTUNIQ", size_bytes=1,
                                 filename="out.mp4", output_name="o")
    assert known["outcome"] == "reused" and known["kind"] == "known_output"
    assert len([c for c in env.bot.calls if c[0] == "get_file"]) == gets

    # --- moderation: remove + ban, idempotent, cancels the encode ---------
    bob_job = await db.fetchrow("SELECT id, encore_job_id FROM jobs WHERE requester_tg_id=20 "
                                "AND status='processing'")
    res = await e.moderate_job(str(bob_job["id"]), 1)
    assert res["ok"] and not res["already"]
    assert await db.fetchval("SELECT is_blocked FROM users WHERE tg_id=20")
    assert await db.fetchval("SELECT status FROM jobs WHERE id=$1", bob_job["id"]) == "cancelled"
    assert bob_job["encore_job_id"] in env.encre.cancelled
    again = await e.moderate_job(str(bob_job["id"]), 1)
    assert again["ok"] and again["already"]
    assert await db.fetchval("SELECT count(*) FROM moderation_actions") == 1
    from oxmit.engine import AdmissionError
    with pytest.raises(AdmissionError) as exc:
        await _register(e, 20, 9)
    assert exc.value.code == "blocked_user"
    mv = await dashboard.moderation_view(db)
    assert mv["actions"][0]["status_before"] == "processing" and mv["banned"]


async def test_restart_recovery_requeues_pre_encode(env):
    e, db = env.engine, env.db
    r = await _register(e, 10, 1)
    await db.execute("UPDATE jobs SET status='processing', stage='downloading', "
                     "worker_id='dead:1' WHERE id=$1", uuid.UUID(r["job_id"]))
    await e.recover_queue_on_startup()
    assert await db.fetchval("SELECT status FROM jobs WHERE id=$1",
                             uuid.UUID(r["job_id"])) == "queued"


async def test_queue_capacity_is_records_not_files(env):
    e, db = env.engine, env.db
    e.cfg.max_queued = 3
    for i in range(3):
        await _register(e, 1, i)  # owner = admin: no per-user caps
    from oxmit.engine import AdmissionError
    with pytest.raises(AdmissionError) as exc:
        await _register(e, 1, 99)
    assert exc.value.code == "queue_full"
    assert not list(Path(e.cfg.media_incoming).iterdir())  # nothing downloaded


async def test_moderation_on_queued_job_never_starts(env):
    e, db = env.engine, env.db
    r = await _register(e, 10, 1)
    res = await e.moderate_job(r["job_id"], 1)
    assert res["ok"]
    assert await e.dispatch_once() == 0
    assert not [c for c in env.bot.calls if c[0] == "get_file"]


async def test_web_dashboard_http(env, monkeypatch):
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    from oxmit import webpanel as wp

    monkeypatch.setattr(wp, "SECURE_COOKIES", False)
    e = env.engine
    e.cfg.internal_panel_token = "tok"
    await _register(e, 10, 1)
    app = web.Application()
    wp.setup(app, e, env.db, e.cfg, e.state)
    async with TestClient(TestServer(app)) as c:
        assert (await c.get("/panel/api/v3/jobs")).status == 401  # no session
        r = await c.post("/panel/login", json={"token": "tok"})
        assert r.status == 200
        page = await (await c.get("/panel")).text()
        assert "panel/api/v3" in page
        me = await (await c.get("/panel/api/v3/me")).json()
        assert me["role"] == "owner"
        q = await (await c.get("/panel/api/v3/jobs?view=queue")).json()
        assert q["total"] == 1 and q["items"][0]["user"]["id"] == 10
        assert "source_path" not in str(q)  # token-bearing paths never exposed
        sysv = await (await c.get("/panel/api/v3/system")).json()
        assert sysv["queued"] == 1
        csrf = c.session.cookie_jar.filter_cookies(c.make_url("/"))["oxmit_csrf"].value
        jid = q["items"][0]["id"]
        # owner may moderate; missing CSRF is rejected
        assert (await c.post(f"/panel/api/v3/job/{jid}/moderate")).status == 401
        r = await c.post(f"/panel/api/v3/job/{jid}/moderate", headers={"X-CSRF": csrf})
        assert r.status == 200 and (await r.json())["ok"]
        # an admin session (one-time link minted by a non-owner) cannot
        for sid, s in app["panel_sessions"].items():
            s["role"] = "admin"
        r = await c.post(f"/panel/api/v3/job/{jid}/moderate", headers={"X-CSRF": csrf})
        assert r.status == 403
