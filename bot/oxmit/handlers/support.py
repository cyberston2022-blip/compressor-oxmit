"""Contact-management (support) routing: user -> OWNER only, owner -> user.

Routing rules (each enforced by a filter, not by handler order luck):
- Only a user who explicitly opened "📨 Contact management" has an open
  support session; ONLY their next message (any media type, not a command)
  is copied to the owner. Ordinary messages never reach the owner or admins.
- The recipient is the configured owner (OWNER_TELEGRAM_ID), never the
  admin list. The owner cannot open a session to themselves.
- Owner replies are an OUTGOING operation: they are triggered only by the
  owner pressing "↩️ Reply" on a support message or replying (Telegram
  reply) to the copied support message. The target user comes from the
  database row, never from free text, so the owner never receives a copy of
  their own message and a reply cannot land on the wrong user.
- Sessions expire (SUPPORT_SESSION_MIN) and close after one message; any
  command or the cancel button also closes them, so they never interfere
  with video submissions.
Every message is persisted in support_messages (direction in/out).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..log import get_logger
from ..texts import tr
from .common import ensure_user

log = get_logger("oxmit.support")

MAX_IN_PER_HOUR = 6


def contact_button(lang: str = "fa") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=tr("btn_contact", lang), callback_data="sup:open")


async def owner_id(engine, cfg) -> int | None:
    if cfg.owner_telegram_id:
        return cfg.owner_telegram_id
    admins = await engine.admin_ids()
    return admins[0] if admins else None


def build_router(engine, db, cfg, state) -> Router:
    router = Router(name="support")
    sessions: dict[int, float] = {}            # user tg_id -> expiry (monotonic)
    owner_pending: dict[int, tuple[int, float, int | None]] = {}  # owner -> (user, exp, prompt msg)

    def _cancel_kb(lang: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=tr("btn_cancel", lang), callback_data="sup:cancel")]])

    async def _open(uid: int, chat_id: int, lang: str) -> None:
        oid = await owner_id(engine, cfg)
        if oid is None:
            await engine.bot.send_message(chat_id, tr("sup_no_owner", lang))
            return
        if uid == oid:
            await engine.bot.send_message(chat_id, tr("sup_is_owner", lang))
            return
        mins = max(1, int(cfg.support_session_min))
        sessions[uid] = time.monotonic() + mins * 60
        await engine.bot.send_message(chat_id, tr("sup_open", lang, mins=mins),
                                      reply_markup=_cancel_kb(lang))

    @router.callback_query(F.data == "sup:open")
    async def on_open(cb: CallbackQuery):
        if cb.from_user is None or cb.message is None:
            return
        user = await ensure_user(db, cb.from_user)
        lang = user["language"] or "fa"
        if user["is_blocked"]:
            await cb.answer(tr("admin_denied", lang), show_alert=True)
            return
        await cb.answer()
        await _open(cb.from_user.id, cb.message.chat.id, lang)

    @router.message(F.text.in_({"/contact", "/support"}))
    async def on_open_cmd(message: Message):
        if message.from_user is None:
            return
        user = await ensure_user(db, message.from_user)
        if user["is_blocked"]:
            return
        await _open(message.from_user.id, message.chat.id, user["language"] or "fa")

    @router.callback_query(F.data == "sup:cancel")
    async def on_cancel(cb: CallbackQuery):
        sessions.pop(cb.from_user.id, None)
        owner_pending.pop(cb.from_user.id, None)
        await cb.answer(tr("sup_cancelled", await engine._lang(cb.from_user.id)))
        if cb.message is not None:
            try:
                await cb.message.edit_reply_markup(reply_markup=None)
            except TelegramAPIError:
                pass

    # ------------------------------------------------------------------
    # user -> owner
    # ------------------------------------------------------------------
    def _in_session(message: Message) -> bool:
        if message.from_user is None or message.chat.type != "private":
            return False
        exp = sessions.get(message.from_user.id)
        if exp is None:
            return False
        if time.monotonic() > exp:
            sessions.pop(message.from_user.id, None)
            return False
        if message.text and message.text.startswith("/"):
            sessions.pop(message.from_user.id, None)  # commands close the session
            return False
        return True

    @router.message(_in_session)
    async def on_user_message(message: Message):
        uid = message.from_user.id
        sessions.pop(uid, None)  # one message per explicit open (clear end state)
        lang = await engine._lang(uid)
        oid = await owner_id(engine, cfg)
        if oid is None or oid == uid:
            return
        recent = await db.fetchval(
            "SELECT count(*) FROM support_messages WHERE user_tg_id = $1 "
            "AND direction = 'in' AND created_at > now() - interval '1 hour'", uid)
        if int(recent or 0) >= MAX_IN_PER_HOUR:
            await message.answer(tr("sup_rate", lang))
            return
        row = await db.fetchrow("SELECT first_name, username FROM users WHERE tg_id = $1", uid)
        mid = await db.fetchval(
            "INSERT INTO support_messages(user_tg_id, direction, owner_tg_id, "
            "user_message_id, kind, text_preview) VALUES ($1,'in',$2,$3,$4,$5) RETURNING id",
            uid, oid, message.message_id, message.content_type,
            (message.text or message.caption or "")[:500])
        header = tr("sup_owner_header", "fa", mid=mid,
                    name=((row["first_name"] if row else None) or "?")[:40],
                    uname=f"@{row['username']}" if row and row["username"] else "",
                    uid=uid, ts=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=tr("sup_btn_reply", "fa"), callback_data=f"sup:r:{mid}")]])
        try:
            head = await engine.bot.send_message(oid, header, reply_markup=kb)
            copied = await engine.bot.copy_message(
                chat_id=oid, from_chat_id=message.chat.id, message_id=message.message_id,
                reply_to_message_id=head.message_id)
        except TelegramAPIError as exc:
            log.warning("support delivery to owner failed", extra={"detail": str(exc)[:120]})
            await db.execute("DELETE FROM support_messages WHERE id = $1", mid)
            await message.answer(tr("sup_failed", lang))
            return
        await db.execute(
            "UPDATE support_messages SET header_message_id = $2, owner_message_id = $3 "
            "WHERE id = $1", mid, head.message_id, copied.message_id)
        await db.bump("support_in")
        await message.answer(tr("sup_sent", lang))

    # ------------------------------------------------------------------
    # owner -> user
    # ------------------------------------------------------------------
    async def _is_owner(uid: int) -> bool:
        oid = await owner_id(engine, cfg)
        return oid is not None and uid == oid

    @router.callback_query(F.data.startswith("sup:r:"))
    async def on_reply_btn(cb: CallbackQuery):
        if not await _is_owner(cb.from_user.id):
            await cb.answer(tr("admin_denied", "fa"), show_alert=True)
            return
        try:
            mid = int(cb.data.split(":", 2)[2])
        except (TypeError, ValueError):
            await cb.answer()
            return
        row = await db.fetchrow(
            "SELECT s.user_tg_id, u.first_name FROM support_messages s "
            "LEFT JOIN users u ON u.tg_id = s.user_tg_id WHERE s.id = $1 AND s.direction = 'in'",
            mid)
        if row is None:
            await cb.answer(tr("cancel_expired", "fa"), show_alert=True)
            return
        await cb.answer()
        prompt = await engine.bot.send_message(
            cb.from_user.id,
            tr("sup_reply_prompt", "fa", name=row["first_name"] or "?", uid=row["user_tg_id"]),
            reply_markup=_cancel_kb("fa"))
        owner_pending[cb.from_user.id] = (row["user_tg_id"], time.monotonic() + 900,
                                          prompt.message_id)

    async def _owner_reply_target(message: Message):
        """Filter: owner message that is explicitly a reply -> {'target': uid}."""
        if message.from_user is None or message.chat.type != "private":
            return False
        if message.text and message.text.startswith("/"):
            if message.text.startswith("/cancel"):
                owner_pending.pop(message.from_user.id, None)
            return False
        pend = owner_pending.get(message.from_user.id)
        if pend and time.monotonic() < pend[1]:
            if not await _is_owner(message.from_user.id):
                return False
            return {"target": pend[0], "prompt_id": pend[2]}
        reply = message.reply_to_message
        if reply is None or not await _is_owner(message.from_user.id):
            return False
        uid = await db.fetchval(
            "SELECT user_tg_id FROM support_messages WHERE owner_tg_id = $1 "
            "AND direction = 'in' AND (owner_message_id = $2 OR header_message_id = $2)",
            message.from_user.id, reply.message_id)
        return {"target": uid, "prompt_id": None} if uid else False

    @router.message(_owner_reply_target)
    async def on_owner_reply(message: Message, target: int, prompt_id):
        owner_pending.pop(message.from_user.id, None)
        lang = await engine._lang(target)
        try:
            if message.text:
                sent = await engine.bot.send_message(
                    target, f"{tr('sup_reply_header', lang)}\n\n{message.text}")
            else:
                await engine.bot.send_message(target, tr("sup_reply_header", lang))
                sent = await engine.bot.copy_message(
                    chat_id=target, from_chat_id=message.chat.id,
                    message_id=message.message_id)
        except TelegramAPIError as exc:
            log.info("owner reply failed", extra={"detail": str(exc)[:120]})
            await message.answer(tr("sup_reply_failed", "fa"))
            return
        await db.execute(
            "INSERT INTO support_messages(user_tg_id, direction, owner_tg_id, "
            "user_message_id, owner_message_id, kind, text_preview) "
            "VALUES ($1,'out',$2,$3,$4,$5,$6)",
            target, message.from_user.id, sent.message_id, message.message_id,
            message.content_type, (message.text or message.caption or "")[:500])
        await db.bump("support_out")
        # Confirmation only (edit the prompt) - never a copy of the message.
        if prompt_id:
            await engine.edit_status_sync(message.chat.id, prompt_id,
                                          tr("sup_reply_sent", "fa", uid=target))
        else:
            await message.reply(tr("sup_reply_sent", "fa", uid=target))

    async def sweep_pending() -> None:
        now = time.monotonic()
        for uid in [u for u, exp in sessions.items() if exp < now]:
            sessions.pop(uid, None)
        for uid in [u for u, p in owner_pending.items() if p[1] < now]:
            owner_pending.pop(uid, None)

    router.sweep_pending = sweep_pending  # type: ignore[attr-defined]
    router.sessions = sessions  # type: ignore[attr-defined]  (tests)
    return router
