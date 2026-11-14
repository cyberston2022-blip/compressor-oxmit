"""Regression tests for the channel-membership gate (force-join).

Covers: target normalization, resolution (id/username/invite-link),
invite-link verification of captured chats, membership verdicts + caching,
middleware pass/block semantics (owner bypass, recheck bypass, fail-closed
on API errors), the recheck flow, and panel config validation.
"""
import time
from types import SimpleNamespace

from oxmit.gate import (
    ChannelGateMiddleware,
    GateService,
    normalize_gate_target,
)
from oxmit.panel.bot_manager import update_bot_config


class FakeDB:
    def __init__(self):
        self.cfg = {}

    async def get_config(self, key):
        return self.cfg.get(key)

    async def set_config(self, key, value):
        self.cfg[key] = value


def make_state(gate_channel="", gate_channel_id=""):
    return SimpleNamespace(gate_channel=gate_channel,
                           gate_channel_id=gate_channel_id)


class StubChat:
    def __init__(self, cid, username=None, invite_link=None):
        self.id = cid
        self.username = username
        self.invite_link = invite_link  # ChatInviteLink-like or str


class StubBot:
    """get_chat: numeric ids resolve from self.chats; invite links never do
    (mirrors Bot API). get_chat_member: status from self.members, 'ERROR'
    raises (simulates a Telegram API failure)."""

    def __init__(self, chats=None, members=None):
        self.chats = chats or {}
        self.members = members or {}
        self.member_calls = 0

    async def get_chat(self, cid):
        if isinstance(cid, str) and "t.me/+" in cid:
            raise RuntimeError("Chat not found")
        if isinstance(cid, str) and cid.startswith("@"):
            for chat in self.chats.values():
                if (chat.username or "").lower() == cid[1:].lower():
                    return chat
            raise RuntimeError("Chat not found")
        chat = self.chats.get(int(cid))
        if chat is None:
            raise RuntimeError("Chat not found")
        return chat

    async def get_chat_member(self, chat_id, user_id):
        self.member_calls += 1
        status = self.members.get((int(chat_id), int(user_id)))
        if status == "ERROR":
            raise RuntimeError("Telegram API hiccup")
        if status is None:
            raise RuntimeError("participant not found")
        return SimpleNamespace(status=status)


class Recorder:
    def __init__(self):
        self.answers = []

    async def __call__(self, text=None, reply_markup=None, show_alert=False):
        self.answers.append({"text": text, "reply_markup": reply_markup,
                             "show_alert": show_alert})


# ---------------------------------------------------------------------------
# normalize_gate_target
# ---------------------------------------------------------------------------

def test_normalize_invite_link_variants():
    for raw in ("https://t.me/+-Lkgkp87SB0zMDA8", "t.me/+-Lkgkp87SB0zMDA8",
                "https://telegram.me/joinchat/-Lkgkp87SB0zMDA8",
                "  https://t.me/+Lkgkp87SB0zMDA8  "):
        kind, val = normalize_gate_target(raw)
        assert kind == "invite", raw
        assert val == "https://t.me/+-Lkgkp87SB0zMDA8" or val.endswith(
            "Lkgkp87SB0zMDA8")


def test_normalize_username_and_id_and_off():
    assert normalize_gate_target("@my_chan") == ("username", "@my_chan")
    assert normalize_gate_target("-1001234567890") == ("id", "-1001234567890")
    assert normalize_gate_target("") == ("off", "")
    assert normalize_gate_target(None) == ("off", "")
    assert normalize_gate_target("hello world!!") == ("invalid", "hello world!!")
    # a bare word is not accepted (avoid ambiguity)
    assert normalize_gate_target("justword") == ("invalid", "justword")


# ---------------------------------------------------------------------------
# GateService resolution
# ---------------------------------------------------------------------------

async def test_resolve_numeric_id_persists():
    db, state = FakeDB(), make_state("-100555")
    gate = GateService(db, state)
    cid = await gate.resolve(StubBot())
    assert cid == "-100555"
    assert state.gate_channel_id == "-100555"
    assert db.cfg["gate_channel_id"] == "-100555"


async def test_resolve_username_via_get_chat():
    db, state = FakeDB(), make_state("@my_chan")
    gate = GateService(db, state)
    bot = StubBot(chats={-100111: StubChat(-100111, username="my_chan")})
    cid = await gate.resolve(bot)
    assert cid == "-100111"
    assert state.gate_channel_id == "-100111"


async def test_resolve_username_mismatch_rejected():
    db, state = FakeDB(), make_state("@my_chan")
    gate = GateService(db, state)
    bot = StubBot(chats={-100111: StubChat(-100111, username="other")})
    assert await gate.resolve(bot) is None
    assert state.gate_channel_id == ""


async def test_resolve_invite_link_not_directly_resolvable():
    db, state = FakeDB(), make_state("https://t.me/+abc123")
    gate = GateService(db, state)
    assert await gate.resolve(StubBot()) is None
    assert state.gate_channel_id == ""


async def test_verify_candidate_by_primary_invite_link():
    db, state = FakeDB(), make_state("https://t.me/+abc123")
    gate = GateService(db, state)
    ok_chat = StubChat(-100222, invite_link=SimpleNamespace(
        invite_link="https://t.me/+abc123"))
    bad_chat = StubChat(-100333, invite_link=SimpleNamespace(
        invite_link="https://t.me/+other999"))
    no_link_chat = StubChat(-100444)
    bot = StubBot(chats={-100222: ok_chat, -100333: bad_chat,
                         -100444: no_link_chat})
    assert await gate.verify_candidate(bot, -100222) is True
    assert await gate.verify_candidate(bot, -100333) is False
    assert await gate.verify_candidate(bot, -100444) is False


async def test_note_channel_event_resolves_and_persists():
    db, state = FakeDB(), make_state("https://t.me/+abc123")
    gate = GateService(db, state)
    bot = StubBot(chats={-100222: StubChat(
        -100222, invite_link=SimpleNamespace(invite_link="https://t.me/+abc123"))})
    resolved = await gate.note_channel_event(bot, -100222)
    assert resolved is True
    assert state.gate_channel_id == "-100222"
    assert db.cfg["gate_channel_id"] == "-100222"
    # second event is a no-op once resolved
    assert await gate.note_channel_event(bot, -100333) is False


async def test_set_target_clears_stale_resolution():
    db, state = FakeDB(), make_state("-100555", "-100555")
    gate = GateService(db, state)
    kind, canonical = await gate.set_target("https://t.me/+newlink")
    assert (kind, canonical) == ("invite", "https://t.me/+newlink")
    assert state.gate_channel == "https://t.me/+newlink"
    assert state.gate_channel_id == ""
    kind, _ = await gate.set_target("junk!!")
    assert kind == "invalid"
    await gate.disable()
    assert state.gate_channel == "" and state.gate_channel_id == ""


# ---------------------------------------------------------------------------
# membership verdicts + cache
# ---------------------------------------------------------------------------

def member_gate(members):
    db = FakeDB()
    state = make_state("-100555", "-100555")
    return GateService(db, state), StubBot(members=members), state


async def test_is_member_verdicts():
    gate, bot, _ = member_gate({
        (-100555, 1): "member",
        (-100555, 2): "administrator",
        (-100555, 3): "creator",
        (-100555, 4): "restricted",
        (-100555, 5): "left",
        (-100555, 6): "kicked",
        (-100555, 7): "ERROR",
        (-100555, 8): None,  # not found -> unknown? raises -> None
    })
    assert await gate.is_member(bot, 1) is True
    assert await gate.is_member(bot, 2) is True
    assert await gate.is_member(bot, 3) is True
    assert await gate.is_member(bot, 4) is True
    assert await gate.is_member(bot, 5) is False
    assert await gate.is_member(bot, 6) is False
    assert await gate.is_member(bot, 7) is None
    assert await gate.is_member(bot, 8) is None


async def test_membership_cache_avoids_api_calls():
    gate, bot, _ = member_gate({(-100555, 1): "member", (-100555, 2): "left"})
    assert await gate.is_member(bot, 1) is True
    calls = bot.member_calls
    assert await gate.is_member(bot, 1) is True
    assert bot.member_calls == calls  # served from cache
    gate.invalidate(1)
    assert await gate.is_member(bot, 1) is True
    assert bot.member_calls == calls + 1


async def test_nonmember_cache_short_ttl_expires():
    gate, bot, _ = member_gate({(-100555, 2): "left"})
    assert await gate.is_member(bot, 2) is False
    # age the entry past the non-member TTL
    gate._cache[2] = (False, time.monotonic() - 31)
    bot.member_calls = 0
    assert await gate.is_member(bot, 2) is False
    assert bot.member_calls == 1


async def test_is_member_none_when_gate_unresolved():
    db, state = FakeDB(), make_state("https://t.me/+abc123")
    gate = GateService(db, state)
    assert await gate.is_member(StubBot(), 1) is None


# ---------------------------------------------------------------------------
# middleware
# ---------------------------------------------------------------------------

def make_event(is_callback=False, tg_id=1000, chat_id=-200):
    ev = SimpleNamespace()
    if is_callback:
        ev.data = "other:action"
        ev.message = SimpleNamespace(chat=SimpleNamespace(id=chat_id))
        ev.answer = Recorder()
    else:
        ev.chat = SimpleNamespace(id=chat_id)
        ev.answer = Recorder()
    ev.from_user = SimpleNamespace(id=tg_id, is_bot=False)
    return ev


def make_mw(gate, owner_id=None, admin_ids=None):
    cfg = SimpleNamespace(owner_telegram_id=owner_id, admin_ids=admin_ids or [])
    return ChannelGateMiddleware(cfg, gate.state, gate)


async def run_mw(mw, event, bot):
    called = []

    async def handler(ev, data):
        called.append(ev)

    await mw(handler, event, {"bot": bot})
    return called


async def test_middleware_passes_when_gate_off():
    gate = GateService(FakeDB(), make_state())
    mw = make_mw(gate)
    ev = make_event()
    called = await run_mw(mw, ev, StubBot())
    assert len(called) == 1
    assert ev.answer.answers == []


async def test_middleware_blocks_nonmember_with_join_kb():
    gate, bot, _ = member_gate({(-100555, 1000): "left"})
    mw = make_mw(gate, owner_id=42)
    ev = make_event(tg_id=1000)
    called = await run_mw(mw, ev, bot)
    assert called == []
    a = ev.answer.answers[0]
    assert "عضو" in a["text"] or "member" in a["text"].lower()
    assert a["reply_markup"] is not None


async def test_middleware_passes_member_and_owner():
    gate, bot, _ = member_gate({(-100555, 1000): "member"})
    mw = make_mw(gate, owner_id=42)
    ev_member = make_event(tg_id=1000)
    ev_owner = make_event(tg_id=42)
    assert len(await run_mw(mw, ev_member, bot)) == 1
    assert len(await run_mw(mw, ev_owner, bot)) == 1
    assert ev_owner.answer.answers == []  # owner bypassed without API check


async def test_middleware_bypasses_recheck_callback():
    gate, bot, _ = member_gate({(-100555, 1000): "left"})
    mw = make_mw(gate, owner_id=42)
    ev = make_event(is_callback=True, tg_id=1000)
    ev.data = "gate:recheck"
    called = await run_mw(mw, ev, bot)
    assert len(called) == 1
    assert ev.answer.answers == []


async def test_middleware_fails_closed_on_api_error():
    gate, bot, _ = member_gate({(-100555, 1000): "ERROR"})
    mw = make_mw(gate, owner_id=42)
    ev = make_event(tg_id=1000)
    called = await run_mw(mw, ev, bot)
    assert called == []
    assert "موقتاً" in ev.answer.answers[0]["text"] or "retry" in \
        ev.answer.answers[0]["text"].lower()


async def test_middleware_nonmember_callback_gets_alert():
    gate, bot, _ = member_gate({(-100555, 1000): "left"})
    mw = make_mw(gate, owner_id=42)
    ev = make_event(is_callback=True, tg_id=1000)
    called = await run_mw(mw, ev, bot)
    assert called == []
    assert ev.answer.answers[0]["show_alert"] is True


# ---------------------------------------------------------------------------
# panel config validation
# ---------------------------------------------------------------------------

async def test_panel_write_gate_channel_validates():
    db, state = FakeDB(), make_state()
    res = await update_bot_config(db, state, {"gate_channel": "junk!!"})
    assert res["status"] == "error"
    res = await update_bot_config(db, state,
                                  {"gate_channel": "https://t.me/+abcdEFG"})
    assert res["status"] == "ok"
    assert state.gate_channel == "https://t.me/+abcdEFG"
    assert state.gate_channel_id == ""
    assert db.cfg["gate_channel"] == "https://t.me/+abcdEFG"
    res = await update_bot_config(db, state, {"gate_channel": "-100999"})
    assert res["status"] == "ok"
    assert state.gate_channel == "-100999"


async def test_panel_rejects_unknown_gate_keys():
    db, state = FakeDB(), make_state()
    res = await update_bot_config(db, state, {"gate_channel_id": "-1001"})
    assert res["status"] == "error"  # resolved id is not browser-writable
