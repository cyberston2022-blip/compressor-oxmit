"""Handler-level flows against a REAL PostgreSQL (opt-in, see
test_integration_pg.py): filename-first intake with multiple videos, and
owner-only support routing in both directions."""
import uuid
from types import SimpleNamespace

import pytest

from tests.test_integration_pg import DSN, StubBot, StubEncre, _make_video  # noqa: F401

pytestmark = pytest.mark.skipif(not DSN, reason="set OXMIT_TEST_PG_DSN")


def _handler(router, observer, name):
    for h in getattr(router, observer).handlers:
        if h.callback.__name__ == name:
            return h
    raise KeyError(name)


class Msg:
    _next = 500

    def __init__(self, uid, *, text=None, video=None, reply_to=None, chat_type="private"):
        Msg._next += 1
        self.message_id = Msg._next
        self.from_user = SimpleNamespace(id=uid, first_name=f"u{uid}", username=f"user{uid}")
        self.chat = SimpleNamespace(id=uid, type=chat_type)
        self.text = text
        self.caption = None
        self.video = video
        self.document = None
        self.reply_to_message = reply_to
        self.content_type = "text" if text else "video"
        self.answers = []

    async def answer(self, text, **kw):
        self.answers.append(text)

    async def reply(self, text, **kw):
        self.answers.append(text)


def _video(n):
    return SimpleNamespace(file_id=f"F{n}", file_unique_id=f"U{n}", file_size=10 << 20,
                           file_name=f"clip{n}.mp4", duration=60, width=1280, height=720,
                           mime_type="video/mp4")


@pytest.fixture
async def henv(tmp_path):
    import asyncpg

    from oxmit.config import Settings
    from oxmit.db import Database
    from oxmit.engine import JobEngine

    dbname = "oxh_" + uuid.uuid4().hex[:8]
    admin = await asyncpg.connect(DSN)
    await admin.execute(f"CREATE DATABASE {dbname}")
    db = Database(DSN.replace("/oxmit", f"/{dbname}"))
    await db.connect()
    cfg = Settings(media_root=str(tmp_path), botapi_dir=str(tmp_path / "b"),
                   owner_telegram_id=1, max_jobs_per_day=100)
    bot = StubBot(tmp_path, tmp_path / "x.mp4")
    engine = JobEngine(db, cfg, bot, StubEncre())
    engine.state.archive_channel_id = -1001
    engine.kick_dispatch = lambda: None
    await db.execute("INSERT INTO users(tg_id, first_name, is_admin) VALUES (1, 'owner', TRUE), "
                     "(2, 'admin2', TRUE)")
    yield SimpleNamespace(db=db, engine=engine, bot=bot, cfg=cfg, state=engine.state)
    for t in list(engine._bg_tasks):
        t.cancel()
    await db.close()
    await admin.execute(f"DROP DATABASE {dbname}")
    await admin.close()


async def test_naming_flow_multiple_videos(henv):
    from oxmit.handlers import intake
    r = intake.build_router(henv.engine, henv.db, henv.cfg, henv.state)
    on_media = _handler(r, "message", "on_media").callback
    name_h = _handler(r, "message", "on_name_text")
    v1, v2 = Msg(50, video=_video(1)), Msg(50, video=_video(2))
    await on_media(v1)
    await on_media(v2)
    await on_media(v1)  # duplicate Telegram update -> ignored
    drafts = await henv.db.fetch("SELECT status, source_message_id FROM intake_drafts "
                                 "ORDER BY created_at")
    assert [d["status"] for d in drafts] == ["awaiting_name", "waiting"]
    assert await henv.db.fetchval("SELECT count(*) FROM jobs") == 0  # nothing queued yet
    # first answer names the FIRST video (with a typed extension stripped)
    t = Msg(50, text="Lecture 01.mkv")
    data = await name_h.filters[1].callback(t)
    await name_h.callback(t, **data)
    job = await henv.db.fetchrow("SELECT output_name, source_message_id FROM jobs")
    assert job["output_name"] == "Lecture 01" and job["source_message_id"] == v1.message_id
    # second video is now the active prompt; Persian name goes to it
    t2 = Msg(50, text="درس دانشگاه.mp4")
    data = await name_h.filters[1].callback(t2)
    await name_h.callback(t2, **data)
    names = {r["source_message_id"]: r["output_name"] for r in
             await henv.db.fetch("SELECT source_message_id, output_name FROM jobs")}
    assert names == {v1.message_id: "Lecture 01", v2.message_id: "درس دانشگاه"}
    # no open draft -> ordinary text is NOT treated as a filename
    assert await name_h.filters[1].callback(Msg(50, text="hello")) is False
    # commands are never captured
    assert await name_h.filters[1].callback(Msg(50, text="/start")) is False


async def test_support_routes_only_to_owner(henv):
    from oxmit.handlers import support
    r = support.build_router(henv.engine, henv.db, henv.cfg, henv.state)
    user_h = _handler(r, "message", "on_user_message")
    owner_h = _handler(r, "message", "on_owner_reply")
    await henv.db.execute("INSERT INTO users(tg_id, first_name) VALUES (77, 'student')")
    # ordinary message without opening contact: not routed
    assert user_h.filters[0].callback(Msg(77, text="hi")) is False
    r.sessions[77] = 10 ** 12  # user pressed "contact management"
    m = Msg(77, text="I have a question")
    assert user_h.filters[0].callback(m) is True
    henv.bot.calls.clear()
    await user_h.callback(m)
    sent_to = [c for c in henv.bot.calls if c[0] in ("send_message", "copy_message")]
    # header (send_message) + copy, BOTH to the owner (1) - never admin 2
    assert any(c[0] == "copy_message" and c[1] == 1 for c in sent_to)
    assert all((c[1][0] if c[0] == "send_message" else c[1]) == 1 for c in sent_to)
    assert 77 not in r.sessions  # session closed after one message
    row = await henv.db.fetchrow("SELECT * FROM support_messages WHERE direction='in'")
    assert row["owner_tg_id"] == 1 and row["owner_message_id"]
    # owner replies (Telegram reply to the copied message) -> goes to the user
    henv.bot.calls.clear()
    reply = Msg(1, text="Here is the answer",
                reply_to=SimpleNamespace(message_id=row["owner_message_id"]))
    data = await owner_h.filters[0].callback(reply)
    assert data == {"target": 77, "prompt_id": None}
    await owner_h.callback(reply, **data)
    sends = [c for c in henv.bot.calls if c[0] == "send_message"]
    assert sends and sends[0][1][0] == 77  # delivered to the user, not echoed to owner
    assert await henv.db.fetchval("SELECT count(*) FROM support_messages WHERE direction='out'") == 1
    # an admin replying to the same message is NOT routed
    adm = Msg(2, text="x", reply_to=SimpleNamespace(message_id=row["owner_message_id"]))
    assert await owner_h.filters[0].callback(adm) is False
    # the owner's ordinary messages are never treated as support input
    assert await owner_h.filters[0].callback(Msg(1, text="random")) is False
