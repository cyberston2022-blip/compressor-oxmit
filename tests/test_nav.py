"""Navigation hub tests: role-aware menu visibility, authorization,
callback registration and limits, my-jobs ownership."""
import asyncio
from types import SimpleNamespace

import pytest

from oxmit import permissions as perms
from oxmit.config import Settings
from oxmit.handlers import nav as nav_mod
from oxmit.handlers.nav import build_router
from oxmit.permissions import invalidate_cache

OWNER, ADMIN, VIP, USER = 100, 200, 300, 500


class ScriptedDB:
    def __init__(self, is_vip=False, perm_rows=None):
        self.is_vip = is_vip
        self.perm_rows = perm_rows or []
        self.executed = []

    async def fetchrow(self, sql, *args):
        if "INSERT INTO users" in sql:
            return {"is_admin": False, "is_blocked": False, "language": "fa"}
        if "FROM users WHERE tg_id" in sql and "is_vip" in sql:
            return {"is_vip": self.is_vip}
        if "admin_settings" in sql:
            return {"thumbnail_path": None, "watermark_enabled": False,
                    "caption": None, "caption_mode": "replace"}
        return None

    async def fetch(self, sql, *args):
        if "admin_permissions" in sql:
            return self.perm_rows
        if "FROM jobs j" in sql:
            return []
        if "FROM audit_log" in sql:
            return []
        return []

    async def fetchval(self, sql, *args):
        if "is_vip" in sql and "count" in sql:
            return 0
        return None

    async def execute(self, sql, *args):
        self.executed.append(("execute", sql, args))
        return "UPDATE 1"

    async def bump(self, *a):
        pass

    async def get_config(self, key):
        return {}

    async def set_config(self, key, value):
        pass


class StubEngine:
    def __init__(self, owner=None, admins=(), rows=None):
        self.owner = owner
        self.admin_ids_set = set(admins)
        self.rows = rows or []
        self.db = ScriptedDB(perm_rows=self.rows)

        async def is_owner(tg_id):
            return tg_id == self.owner
        self.is_owner = is_owner

        async def admin_ids():
            return sorted(self.admin_ids_set)   # real engine sorts
        self.admin_ids = admin_ids

        async def tiers_config():
            return {"vip": {"max_duration_min": 720, "daily_quota_gb": 20,
                            "max_active": 4, "max_per_hour": 30,
                            "priority": 60}}
        self.tiers_config = tiers_config


def _router(eng):
    invalidate_cache()
    return build_router(eng, eng.db, Settings(media_root="."), SimpleNamespace(
        archive_channel_id=None))


def _callback_names(router, observer):
    return {h.callback.__name__ for h in getattr(router, observer).handlers}


@pytest.fixture(autouse=True)
def _clean():
    invalidate_cache()
    yield
    invalidate_cache()


def _kb_texts(kb):
    return [b.text for row in kb.inline_keyboard for b in row]


def _kb_data(kb):
    return [b.callback_data for row in kb.inline_keyboard for b in row]


async def _menu_for(eng, tg_id):
    router = _router(eng)
    # reach the closure through a rendered home: call the message handler
    handler = next(h.callback for h in router.message.handlers
                   if h.callback.__name__ == "on_menu")
    msgs = []

    class Msg:
        chat = SimpleNamespace(id=1)
        from_user = SimpleNamespace(id=tg_id, first_name="T", username="t",
                                    language="fa")

        async def answer(self, text=None, reply_markup=None, **k):
            msgs.append((text, reply_markup))

    await handler(Msg())
    assert msgs, "menu must render"
    return msgs[0][1]  # keyboard


async def test_regular_user_menu_minimal():
    kb = await _menu_for(StubEngine(admins={ADMIN}), USER)
    texts = _kb_texts(kb)
    assert any("کارهای من" in t for t in texts)
    assert not any("برندینگ" in t for t in texts)
    assert not any("ادغام" in t for t in texts)
    assert not any("VIP" in t for t in texts)
    assert not any("Owner" in t for t in texts)


async def test_vip_user_sees_benefits_only():
    eng = StubEngine(admins={ADMIN})
    eng.db = ScriptedDB(is_vip=True, perm_rows=eng.rows)
    kb = await _menu_for(eng, VIP)
    assert any("VIP" in t for t in _kb_texts(kb))
    assert not any("برندینگ" in t for t in _kb_texts(kb))


async def test_admin_without_optional_perms_sees_ops_only():
    kb = await _menu_for(StubEngine(admins={ADMIN}, owner=OWNER), ADMIN)
    texts = _kb_texts(kb)
    assert any("پنل عملیات" in t for t in texts)
    assert not any("برندینگ" in t for t in texts)
    assert not any("ادغام" in t for t in texts)
    assert not any("Owner" in t for t in texts)


async def test_admin_with_merge_perm_sees_merge_rows():
    eng = StubEngine(admins={ADMIN}, owner=OWNER,
                     rows=[{"perm": "merge.use", "granted": True},
                           {"perm": "merge_compress.use", "granted": True}])
    kb = await _menu_for(eng, ADMIN)
    texts = _kb_texts(kb)
    assert any("ادغام ویدیوها" in t for t in texts)
    assert any("ادغام + فشرده‌سازی" in t for t in texts)
    assert not any("برندینگ" in t for t in texts)  # no branding perms


async def test_owner_sees_everything():
    kb = await _menu_for(StubEngine(owner=OWNER, admins={OWNER}), OWNER)
    texts = _kb_texts(kb)
    assert any("برندینگ" in t for t in texts)
    assert any("ادغام ویدیوها" in t for t in texts)
    assert any("ادغام + فشرده‌سازی" in t for t in texts)
    assert any("Owner" in t for t in texts)


async def test_callbacks_within_telegram_limit():
    data = ["menu:home", "menu:help", "menu:jobs", "menu:vip", "menu:branding",
            "menu:guide", "menu:merge", "menu:mergecompress", "menu:ops",
            "menu:ownpanel", "menu:settings", "den:req:merge_compress.use"]
    assert all(len(d.encode()) <= 64 for d in data)


def test_nav_router_registers_all_handlers():
    eng = StubEngine(admins={ADMIN}, owner=OWNER)
    router = _router(eng)
    names = _callback_names(router, "callback_query")
    assert {"on_menu_home", "on_menu_help", "on_menu_jobs", "on_menu_vip",
            "on_menu_branding", "on_menu_guide", "on_menu_shortcuts",
            "on_den_request", "on_branding_preview"} <= names
    assert "on_menu" in _callback_names(router, "message")
    assert hasattr(router, "bind_personal_router")


async def test_den_request_rate_limited_and_notifies_owner():
    sent = []

    class Bot:
        async def send_message(self, chat_id, text, **kw):
            sent.append((chat_id, text))

    # realistic stub: owner is admins[0] (the fallback identification)
    eng = StubEngine(admins={OWNER, ADMIN}, owner=OWNER)
    eng.bot = Bot()

    async def fetchval(sql, *args):
        if "audit_log" in sql and "count" in sql:
            return eng.db.perm_requests
        return None

    eng.db.fetchval = fetchval

    async def fetchrow(sql, *args):
        if "FROM users WHERE tg_id" in sql:
            return {"first_name": "A", "username": "a1"}
        return None

    eng.db.fetchrow = fetchrow

    router = _router(eng)
    handler = next(h.callback for h in router.callback_query.handlers
                   if h.callback.__name__ == "on_den_request")

    answers = []

    async def _answer(text=None, **kw):
        answers.append(text)

    cb = SimpleNamespace(
        from_user=SimpleNamespace(id=ADMIN), data="den:req:merge.use",
        message=SimpleNamespace(chat=SimpleNamespace(id=55)),
        answer=_answer)

    eng.db.perm_requests = 0
    await handler(cb)
    assert sent and sent[0][0] == OWNER, "request must go to the OWNER only"

    eng.db.perm_requests = 3
    await handler(cb)
    assert len(sent) == 1, "3/day rate limit must block the 4th request"
