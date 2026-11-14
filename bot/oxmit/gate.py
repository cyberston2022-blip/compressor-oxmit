"""Channel-membership access gate (force-join).

Restricts bot usage to members of one configured Telegram channel
(`app_config` key ``gate_channel``). The bot must itself be a member/admin
of that channel so membership can be queried with ``getChatMember``.

Target forms:
  * numeric chat id (``-100...``)        -> resolvable directly
  * public @username                     -> resolvable via getChat
  * private invite link (``t.me/+...``)  -> NOT resolvable via Bot API;
    resolved from live channel events (``channel_post`` / ``chat_member``
    updates) or an owner forward, verified against the chat's primary
    invite link before it is trusted.

The resolved numeric id is persisted in ``app_config`` as
``gate_channel_id``. Membership verdicts are cached briefly so the gate
never turns into a per-message API storm; unknown outcomes (Telegram API
errors) fail closed with a retry hint, consistent with the project's
fail-closed convention.
"""

from __future__ import annotations

import re
import time

from aiogram import Bot, BaseMiddleware, Router, F
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .log import get_logger
from .texts import tr

log = get_logger("oxmit.gate")

_MEMBER_OK = ("creator", "administrator", "member", "restricted")

# invite link forms: https://t.me/+<hash>, t.me/+<hash>, t.me/joinchat/<hash>
_INVITE_RE = re.compile(
    r"^(?:https?://)?(?:t\.me|telegram\.me)/(?:\+|joinchat/)([A-Za-z0-9_-]+)$"
)
_USERNAME_RE = re.compile(r"^@?([A-Za-z0-9_]{5,64})$")


def normalize_gate_target(raw) -> tuple[str, str]:
    """Parse a gate target into (kind, canonical_value).

    kind: off | id | username | invite | invalid
    """
    raw = str(raw or "").strip()
    if not raw:
        return "off", ""
    raw = raw.strip('"').strip()
    if not raw:
        return "off", ""
    if re.fullmatch(r"-?\d{6,}", raw):
        return "id", str(int(raw))
    m = _INVITE_RE.match(raw)
    if m:
        return "invite", f"https://t.me/+{m.group(1)}"
    m = _USERNAME_RE.match(raw)
    if raw.startswith("@"):
        return "username", f"@{m.group(1)}"
    return "invalid", raw


def _invite_hash(link: str) -> str:
    m = _INVITE_RE.match(str(link or "").strip())
    return m.group(1) if m else ""


class GateService:
    """Resolution + membership checks for the channel gate."""

    MEMBER_TTL = 300.0     # member verdicts are stable; cache 5 minutes
    NONMEMBER_TTL = 30.0   # short TTL so the recheck button feels live
    RESOLVE_RETRY = 60.0   # lazy re-resolve backoff while unresolved
    MAX_CACHE = 20000      # hard bound on the verdict cache

    def __init__(self, db, state) -> None:
        self.db = db
        self.state = state
        self._cache: dict[int, tuple[bool, float]] = {}
        self._last_resolve_fail = 0.0

    # ------------------------------------------------------------------
    @property
    def target(self) -> str:
        return str(getattr(self.state, "gate_channel", "") or "")

    @property
    def active(self) -> bool:
        return bool(normalize_gate_target(self.target)[0] not in ("off", "invalid")
                    and self.target)

    @property
    def resolved_id(self) -> str:
        return str(getattr(self.state, "gate_channel_id", "") or "")

    def join_url(self) -> str | None:
        """Public URL for the join button (invite link or public username)."""
        kind, value = normalize_gate_target(self.target)
        if kind == "invite":
            return value
        if kind == "username":
            return f"https://t.me/{value.lstrip('@')}"
        return None

    # ------------------------------------------------------------------
    async def _persist_id(self, chat_id: str) -> None:
        self.state.gate_channel_id = str(chat_id)
        await self.db.set_config("gate_channel_id", str(chat_id))

    async def resolve(self, bot: Bot) -> str | None:
        """Resolve the configured target to a numeric chat id (best effort)."""
        kind, value = normalize_gate_target(self.target)
        if kind == "off":
            return None
        if kind == "id":
            await self._persist_id(value)
            return value
        try:
            chat = await bot.get_chat(value)
        except Exception:  # noqa: BLE001 - invite links are not resolvable
            return None
        if kind == "username":
            if (getattr(chat, "username", "") or "").lstrip("@").lower() != \
                    value.lstrip("@").lower():
                return None
        await self._persist_id(str(chat.id))
        return str(chat.id)

    async def chat_id(self, bot: Bot) -> str | None:
        """Resolved id with lazy re-resolve (bounded retry backoff)."""
        cid = self.resolved_id
        if cid:
            return cid
        if time.monotonic() - self._last_resolve_fail < self.RESOLVE_RETRY:
            return None
        cid = await self.resolve(bot)
        if not cid:
            self._last_resolve_fail = time.monotonic()
        return cid

    # ------------------------------------------------------------------
    async def verify_candidate(self, bot: Bot, chat_id: int | str,
                               trusted: bool = False) -> bool:
        """Verify a captured chat really is the configured gate channel.

        trusted=True (owner forward of a channel post) additionally accepts
        a channel where the bot itself is admin, when the primary invite
        link is not visible (bot without can_invite_users right) - the
        owner's explicit forward is the authoritative signal then. The
        archive channel is always rejected: the bot is admin there too and
        an owner forwarding an archive post must not gate on it.
        """
        kind, value = normalize_gate_target(self.target)
        if kind in ("off", "invalid"):
            return False
        try:
            full = await bot.get_chat(int(chat_id))
        except Exception:  # noqa: BLE001
            return False
        if kind == "id":
            return str(full.id) == str(int(value))
        if kind == "username":
            return (getattr(full, "username", "") or "").lstrip("@").lower() == \
                value.lstrip("@").lower()
        link = getattr(full, "invite_link", None)
        link_str = getattr(link, "invite_link", None) or link
        if isinstance(link_str, str) and _invite_hash(value) and \
                _invite_hash(link_str) == _invite_hash(value):
            return True
        if not trusted:
            return False
        arch = getattr(self.state, "archive_channel_id", None)
        if arch and str(chat_id) == str(arch):
            log.warning("trusted capture rejected: chat is the archive channel")
            return False
        try:
            member = await bot.get_chat_member(int(chat_id), bot.id)
            return getattr(member, "status", "") == "administrator"
        except Exception:  # noqa: BLE001
            return False

    async def note_channel_event(self, bot: Bot, chat_id: int | str,
                                 trusted: bool = False) -> bool:
        """Try to capture the gate channel id from a live channel event."""
        if not self.active or self.resolved_id:
            return False
        if not await self.verify_candidate(bot, chat_id, trusted=trusted):
            return False
        log.info("gate channel resolved from channel event",
                 extra={"detail": f"chat={chat_id} trusted={trusted}"})
        await self._persist_id(str(chat_id))
        return True

    # ------------------------------------------------------------------
    async def is_member(self, bot: Bot, tg_id: int) -> bool | None:
        """True/False verdict, or None when Telegram cannot be consulted."""
        now = time.monotonic()
        hit = self._cache.get(tg_id)
        if hit and hit[1] > now:
            return hit[0]
        cid = await self.chat_id(bot)
        if not cid:
            return None
        try:
            member = await bot.get_chat_member(int(cid), int(tg_id))
        except Exception:  # noqa: BLE001 - transient API / bot-not-admin
            log.warning("gate membership check failed",
                        extra={"detail": f"tg_id={tg_id}"})
            return None
        status = getattr(member, "status", "left")
        ok = status in _MEMBER_OK
        ttl = self.MEMBER_TTL if ok else self.NONMEMBER_TTL
        if len(self._cache) > self.MAX_CACHE:
            self._cache.clear()
        self._cache[int(tg_id)] = (ok, now + ttl)
        return ok

    def invalidate(self, tg_id: int) -> None:
        self._cache.pop(int(tg_id), None)

    def invalidate_all(self) -> None:
        self._cache.clear()

    # ------------------------------------------------------------------
    async def set_target(self, value: str) -> tuple[str, str]:
        """Persist a new target (kind, canonical). Clears stale resolution."""
        kind, canonical = normalize_gate_target(value)
        if kind == "invalid":
            return kind, canonical
        self.state.gate_channel = canonical
        await self.db.set_config("gate_channel", canonical)
        self.state.gate_channel_id = ""
        await self.db.set_config("gate_channel_id", "")
        self.invalidate_all()
        self._last_resolve_fail = 0.0
        return kind, canonical

    async def disable(self) -> None:
        self.state.gate_channel = ""
        self.state.gate_channel_id = ""
        await self.db.set_config("gate_channel", "")
        await self.db.set_config("gate_channel_id", "")
        self.invalidate_all()


def _join_keyboard(gate: GateService) -> InlineKeyboardMarkup | None:
    url = gate.join_url()
    rows = []
    if url:
        rows.append([InlineKeyboardButton(text=tr("gate_btn_join"), url=url)])
    rows.append([InlineKeyboardButton(text=tr("gate_btn_check"),
                                      callback_data="gate:recheck")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


class ChannelGateMiddleware(BaseMiddleware):
    """Outer middleware: only channel members reach the handlers.

    Duck-typed event detection (callback queries carry ``data``) matches
    the SimpleNamespace-stub convention used across the test suite.
    """

    def __init__(self, cfg, state, gate: GateService) -> None:
        self.cfg = cfg
        self.state = state
        self.gate = gate

    def _is_privileged(self, tg_id: int) -> bool:
        owner = getattr(self.cfg, "owner_telegram_id", None)
        if owner and tg_id == owner:
            return True
        return tg_id in (getattr(self.cfg, "admin_ids", None) or [])

    async def __call__(self, handler, event, data: dict):
        if not self.gate.active:
            return await handler(event, data)
        user = getattr(event, "from_user", None)
        if user is None or getattr(user, "is_bot", False):
            return await handler(event, data)
        if self._is_privileged(user.id):
            return await handler(event, data)
        is_callback = hasattr(event, "data")
        if is_callback and (event.data or "") == "gate:recheck":
            return await handler(event, data)
        bot = data.get("bot")
        verdict = await self.gate.is_member(bot, user.id)
        if verdict is True:
            return await handler(event, data)
        if verdict is False:
            kb = _join_keyboard(self.gate)
            if not is_callback:
                await event.answer(tr("gate_join_required"), reply_markup=kb)
            else:
                await event.answer(tr("gate_not_member_yet"), show_alert=True)
            return
        # Unknown (API error / gate unresolved): fail closed, allow retry.
        log.error("gate cannot verify membership - blocking user",
                  extra={"detail": f"tg_id={user.id} resolved={bool(self.gate.resolved_id)}"})
        kb = _join_keyboard(self.gate)
        if not is_callback:
            await event.answer(tr("gate_check_error"), reply_markup=kb)
        else:
            await event.answer(tr("gate_check_error"), show_alert=True)
        return


def build_gate_router(engine, db, cfg, state, gate: GateService) -> Router:
    """Capture + owner-management router. Must be registered FIRST so the
    capture handlers win over intake's channel_post archive discovery."""
    router = Router(name="gate")

    @router.callback_query(F.data == "gate:recheck")
    async def on_recheck(event, bot: Bot):
        gate.invalidate(event.from_user.id)
        verdict = await gate.is_member(bot, event.from_user.id)
        if verdict is True:
            await event.answer(tr("gate_membership_ok"), show_alert=True)
            if getattr(event, "message", None):
                chat_id = getattr(event.message, "chat", None)
                if chat_id:
                    try:
                        await bot.send_message(chat_id.id, tr("gate_membership_ok"))
                    except Exception:  # noqa: BLE001
                        pass
        elif verdict is False:
            await event.answer(tr("gate_not_member_yet"), show_alert=True)
        else:
            await event.answer(tr("gate_check_error"), show_alert=True)

    # --- resolution capture -------------------------------------------
    @router.channel_post()
    async def on_channel_post(event, bot: Bot):
        act = gate.active and not gate.resolved_id
        if act and event.chat.type == "channel":
            try:
                await gate.note_channel_event(bot, event.chat.id)
            except Exception:  # noqa: BLE001
                log.exception("gate capture failed")
        raise SkipHandler  # archive discovery (intake) still sees the post

    @router.chat_member()
    async def on_chat_member(event, bot: Bot):
        if gate.active and not gate.resolved_id and event.chat.type == "channel":
            try:
                await gate.note_channel_event(bot, event.chat.id)
            except Exception:  # noqa: BLE001
                log.exception("gate capture failed")

    @router.message(Command("gate"))
    async def on_gate_cmd(event, bot: Bot):
        if not await engine.is_owner(event.from_user.id):
            return
        args = (event.get_args() or "").split()
        if not args:
            kind, value = normalize_gate_target(gate.target)
            cid = gate.resolved_id or "-"
            await event.answer(tr("gate_status", target=value or "-", kind=kind,
                                  cid=cid, active="yes" if gate.active else "no"))
            return
        cmd, *rest = args
        if cmd == "off":
            await gate.disable()
            await event.answer(tr("gate_off_done"))
            return
        if cmd in ("set", "check"):
            if cmd == "set":
                if not rest:
                    await event.answer(tr("gate_set_invalid"))
                    return
                kind, canonical = await gate.set_target(" ".join(rest))
                if kind == "invalid":
                    await event.answer(tr("gate_set_invalid"))
                    return
                await event.answer(tr("gate_set_ok", kind=kind, value=canonical))
            cid = await gate.resolve(bot)
            if cid:
                verdict = await gate.is_member(bot, event.from_user.id)
                verdict_txt = {True: "member", False: "NOT a member",
                               None: "check unavailable"}[verdict]
                await event.answer(tr("gate_resolved", cid=cid,
                                      verdict=verdict_txt))
                if verdict is not None:
                    gate.invalidate(event.from_user.id)
            else:
                await event.answer(tr("gate_unresolved"))
            return
        await event.answer(tr("gate_set_invalid"))

    # Owner forward capture while unresolved (fastest deterministic path:
    # forward any post of the gate channel to the bot).
    @router.message(F.forward_origin.chat | F.forward_from_chat)
    async def on_forward(event, bot: Bot):
        if not gate.active or gate.resolved_id:
            raise SkipHandler
        if not await engine.is_owner(event.from_user.id):
            raise SkipHandler
        chat = None
        origin = getattr(event, "forward_origin", None)
        if origin is not None and hasattr(origin, "chat"):
            chat = origin.chat
        chat = chat or getattr(event, "forward_from_chat", None)
        if chat is None or getattr(chat, "type", "") != "channel":
            raise SkipHandler
        try:
            resolved = await gate.note_channel_event(bot, chat.id, trusted=True)
        except Exception:  # noqa: BLE001
            log.exception("gate forward capture failed")
            resolved = False
        await event.answer(tr("gate_capture_ok", cid=chat.id) if resolved
                           else tr("gate_capture_mismatch"))
        raise SkipHandler  # a forwarded video still reaches intake

    return router
