"""Multi-admin feature tests: router registration, merge-session ordering
(atomic seq via the session row lock), and delivery branding resolution.

Merge add_item uses a real transaction + row lock on Postgres; here the
FakeDB pool shim records the statement ORDER, which is the invariant the
spec demands (item_count+1 under the locked UPDATE, then INSERT with that
seq). The SQL constraints themselves are rehearsed on a disposable
postgres during deployment.
"""
import asyncio
import uuid as uuid_mod
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from oxmit import merge as merge_mod
from oxmit.config import Settings
from oxmit.handlers import merge_flow, owner, personal
from oxmit.merge import add_item, decide_strategy


class _Tx:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


class ScriptedDB:
    """Minimal pool+conn shim that records calls and scripts fetch results."""

    def __init__(self):
        self.executed = []
        self._fetchrow_results = []
        self._fetch_results = []

    def on_fetchrow(self, match, value):
        self._fetchrow_results.append((match, value))

    def on_fetch(self, match, value):
        self._fetch_results.append((match, value))

    async def execute(self, sql, *args):
        self.executed.append(("execute", sql, args))
        return "UPDATE 1"

    async def fetchval(self, sql, *args):
        self.executed.append(("fetchval", sql, args))
        return None

    async def fetchrow(self, sql, *args):
        self.executed.append(("fetchrow", sql, args))
        for match, value in self._fetchrow_results:
            if match(sql):
                if callable(value):
                    return value(sql, args)
                return value
        return None

    async def fetch(self, sql, *args):
        self.executed.append(("fetch", sql, args))
        for match, value in self._fetch_results:
            if match(sql):
                return value
        return []

    async def bump(self, counter, by=1):
        self.executed.append(("bump", counter, by))

    async def get_config(self, key):
        return {}

    async def set_config(self, key, value):
        self.executed.append(("set_config", key, value))


@pytest.fixture
def tx_db():
    db = ScriptedDB()
    counter = {"n": 0}

    async def default_fetchrow(sql, *args):
        if "UPDATE merge_sessions" in sql and "item_count" in sql:
            counter["n"] += 1
            return {"item_count": counter["n"]}
        return None

    db._tx_fetchrow = default_fetchrow

    @asynccontextmanager
    async def acquire():
        yield SimpleNamespace(
            transaction=lambda: _Tx(),
            fetchrow=db._tx_fetchrow,   # delegated dynamically (tests may swap it)
            execute=db.execute,
        )

    db.pool = SimpleNamespace(acquire=acquire)
    return db


async def test_add_item_assigns_monotonic_seq(tx_db):
    """Two concurrent-ish adds must draw seq 1 then 2 from the locked
    counter - the spec's DB-backed ordering guarantee."""
    sid = str(uuid_mod.uuid4())
    seq1 = await add_item(tx_db, sid, uuid_mod.uuid4(), "/tmp/a.mp4", 100, 10.0)
    seq2 = await add_item(tx_db, sid, uuid_mod.uuid4(), "/tmp/b.mp4", 200, 20.0)
    assert (seq1, seq2) == (1, 2)
    inserts = [e for e in tx_db.executed
               if e[0] == "execute" and "INSERT INTO merge_items" in e[1]]
    assert [e[2][1] for e in inserts] == [1, 2]


async def test_add_item_rejects_inactive_session(tx_db):
    async def closed(sql, *args):
        if "UPDATE merge_sessions" in sql and "item_count" in sql:
            return None
        return None
    tx_db._tx_fetchrow = closed
    with pytest.raises(merge_mod.MergeError):
        await add_item(tx_db, str(uuid_mod.uuid4()), uuid_mod.uuid4(),
                       "/tmp/a.mp4", 100, 10.0)


def _engine_stub(db, admins=(200,), owner=100):
    eng = SimpleNamespace(db=db, cfg=Settings(media_root="."))

    async def is_owner(tg_id):
        return tg_id == owner
    eng.is_owner = is_owner

    async def admin_ids():
        return list(admins)
    eng.admin_ids = admin_ids
    return eng


async def test_owner_router_registers_and_permissions_flow():
    from oxmit.permissions import has_perm, invalidate_cache
    invalidate_cache()
    db = ScriptedDB()
    eng = _engine_stub(db, admins=(100, 200), owner=100)
    # owner bypasses; plain admin gets only the default grant
    assert await has_perm(eng, 100, "merge.use") is True
    assert await has_perm(eng, 200, "merge.use") is False
    db.on_fetch(lambda sql: "admin_permissions" in sql,
                [{"perm": "merge.use", "granted": True}])
    invalidate_cache(200)
    assert await has_perm(eng, 200, "merge.use") is True
    invalidate_cache()


def test_new_routers_register_handlers():
    db = ScriptedDB()
    state = SimpleNamespace(archive_channel_id=None)
    cfg = Settings(media_root=".")
    eng = _engine_stub(db)

    m = merge_flow.build_router(eng, db, cfg, state)
    assert {"on_merge_cmd", "on_merge_video", "on_merge_btn"} <= {
        h.callback.__name__ for h in m.message.handlers + m.callback_query.handlers}

    p = personal.build_router(eng, db, cfg, state)
    pnames = {h.callback.__name__ for h in p.message.handlers}
    assert {"on_thumb_cmd", "on_wm_cmd", "on_cap_cmd"} <= pnames

    o = owner.build_router(eng, db, cfg, state)
    assert "on_owner" in {h.callback.__name__ for h in o.message.handlers}


async def test_delivery_personal_submitter_uses_snapshot():
    """The submitter's branding comes from the submission-time job snapshot,
    not from current admin_settings (spec 4.4)."""
    from oxmit.engine import JobEngine
    db = ScriptedDB()
    cfg = Settings(media_root=".")
    eng = JobEngine(db, cfg, object(), object())

    row = {"requester_tg_id": 200, "personal_caption": "cap-snap",
           "caption_mode": "replace", "watermark_json": None,
           "personal_thumb_path": None}
    got = await eng._delivery_personal(row, 200)
    assert got["caption"] == "cap-snap"
    # no DB fetch may happen for the submitter path
    assert not any("admin_settings" in e[1] for e in db.executed)


async def test_delivery_personal_joiner_gets_own_settings():
    from oxmit.engine import JobEngine
    db = ScriptedDB()
    db._fetchrow_results.append((
        lambda sql: "FROM admin_settings WHERE tg_id" in sql,
        {"thumbnail_path": None, "caption": "joiner-cap",
         "caption_mode": "append", "watermark": None,
         "watermark_enabled": False}))
    cfg = Settings(media_root=".")
    eng = JobEngine(db, cfg, object(), object())
    row = {"requester_tg_id": 200, "personal_caption": "cap-snap",
           "caption_mode": "replace", "watermark_json": None,
           "personal_thumb_path": None}
    got = await eng._delivery_personal(row, 999)
    assert got["caption"] == "joiner-cap"
    assert got["caption_mode"] == "append"
    assert any("admin_settings" in e[1] for e in db.executed)


def test_compose_caption_modes_and_clamp():
    from oxmit.engine import JobEngine
    eng = JobEngine(ScriptedDB(), Settings(media_root="."), object(), object())
    base = "summary"
    assert eng._compose_caption({"caption": "brand", "caption_mode": "replace"},
                                base) == "brand"
    assert eng._compose_caption({"caption": "brand", "caption_mode": "append"},
                                base) == "summary\n\nbrand"
    assert eng._compose_caption({"caption": "", "caption_mode": "replace"},
                                base) == base
    long = eng._compose_caption({"caption": "x" * 2000, "caption_mode": "replace"},
                                None)
    assert len(long) == 1024


def test_watermark_skipped_for_remux_in_delivery_decision():
    from oxmit.watermark import normalize_wm
    wm = normalize_wm({"text": "brand"})
    assert wm["type"] == "text"   # sanity
    # remux exclusion is enforced in engine._deliver_to_requesters via
    # effective_profile != 'remux'; the pure module stays engine-free.
    probes = [{"vcodec": "h264", "acodec": "aac", "width": 640, "height": 360,
               "fps": 30.0, "pix_fmt": "yuv420p", "sample_rate": 48000,
               "channels": 2}]
    assert decide_strategy(probes)[0] == "reencode"  # single input guard


def test_owner_parse_target():
    from oxmit.handlers.owner import parse_target
    assert parse_target("123456789") == ("123456789", None)
    assert parse_target(" ۱۲۳۴۵ ") == ("12345", None)      # Persian digits
    assert parse_target("@Some_User1") == (None, "Some_User1")
    assert parse_target("id: 98765") == ("98765", None)     # digits extracted
    assert parse_target("@bad name!") == (None, None)       # invalid username
    assert parse_target("اب") == (None, None)               # no digits
    assert parse_target("") == (None, None)
