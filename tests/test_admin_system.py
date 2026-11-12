"""Phase 2: admin promote/demote rules (owner guard, last-admin guard) and
the admin-scoped command menu."""
from types import SimpleNamespace

import pytest

from oxmit.config import Settings
from oxmit.engine import JobEngine
from tests.conftest import FakeDB, StubEncre


def _engine(fake_db, owner=100):
    cfg = Settings(media_root=".", owner_telegram_id=owner)
    bot = SimpleNamespace(set_my_commands=None)

    async def set_my_commands(cmds, scope=None):
        bot.calls.append((len(cmds), scope))

    bot.calls = []
    bot.set_my_commands = set_my_commands
    return JobEngine(fake_db, cfg, bot, StubEncre())


def _admins(fake_db, ids):
    fake_db.on_fetch(lambda sql: "SELECT tg_id FROM users WHERE is_admin" in sql,
                     [{"tg_id": i} for i in ids])


async def test_promote_ok_and_audited(fake_db):
    eng = _engine(fake_db)
    fake_db.on_fetchrow(lambda sql: "FROM users WHERE tg_id" in sql, {"tg_id": 7})
    ok, why = await eng.promote_admin("admin:100", 7)
    assert ok and why == "ok"
    assert fake_db.bumps() == []
    assert any("audit_log" in e[1] and e[2][2] == "admin.promote"
               for e in fake_db.executed if e[0] == "execute")


async def test_promote_unknown_user(fake_db):
    eng = _engine(fake_db)
    ok, why = await eng.promote_admin("admin:100", 7)
    assert not ok and why == "user_not_found"


async def test_promote_already_admin(fake_db):
    eng = _engine(fake_db)
    fake_db.on_fetchrow(lambda sql: "FROM users WHERE tg_id" in sql, {"tg_id": 7})
    _admins(fake_db, [7])
    ok, why = await eng.promote_admin("admin:100", 7)
    assert not ok and why == "already_admin"


async def test_demote_owner_blocked(fake_db):
    eng = _engine(fake_db, owner=100)
    ok, why = await eng.demote_admin("admin:100", 100)
    assert not ok and why == "is_owner"


async def test_demote_last_admin_blocked(fake_db):
    eng = _engine(fake_db, owner=100)
    _admins(fake_db, [7])
    ok, why = await eng.demote_admin("admin:100", 7)
    assert not ok and why == "last_admin"


async def test_demote_ok_when_two_admins(fake_db):
    eng = _engine(fake_db, owner=100)
    _admins(fake_db, [7, 100])
    ok, why = await eng.demote_admin("admin:100", 7)
    assert ok and why == "ok"
    assert any("audit_log" in e[1] and e[2][2] == "admin.demote"
               for e in fake_db.executed if e[0] == "execute")


async def test_refresh_admin_commands_scopes(fake_db):
    eng = _engine(fake_db)
    _admins(fake_db, [7, 100])
    await eng.refresh_admin_commands()
    # default scope (5 nav cmds); private scope per admin = 5 + 7 admin
    # entries = 12; the owner's own scope adds /owner -> 13
    assert eng.bot.calls[0] == (5, None)
    assert eng.bot.calls[1] == (12, eng.bot.calls[1][1])
    assert eng.bot.calls[2] == (13, eng.bot.calls[2][1])
    assert len(eng.bot.calls) == 3


def test_stage_tracker_marks_current_stage(engine):
    row = {"id": "11111111-1111-4111-8111-111111111111", "status": "processing",
           "stage": "encoding", "profile": "level", "source_duration": 60,
           "enqueued_at": None, "started_at": None, "progress": 40}
    text = engine._progress_text(row, "fa", None)
    assert "⚙️⏳" in text          # encoding is current
    assert "🧾✅" in text          # queued already done
    assert "📬　" in text          # delivery pending


def test_stage_tracker_with_queue_position(engine):
    row = {"id": "11111111-1111-4111-8111-111111111111", "status": "queued",
           "stage": "queued", "profile": "level", "source_duration": 60,
           "enqueued_at": None, "started_at": None, "progress": 0}
    text = engine._progress_text(row, "fa", {"queue_pos": 3})
    assert "🧾⏳" in text
    assert "موقعیت شما در صف: 3" in text
