"""Owner moderation from the private activity channel.

Every job's channel record carries "🗑 Remove video & ban user". The button
works only for the owner (verified here on every callback - the button
being visible in the channel is not the authorization) and requires an
explicit confirmation tap. The actual work is engine.moderate_job (idempotent,
coordinated cancellation and cleanup).
"""
from __future__ import annotations

import uuid

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from ..log import get_logger
from ..texts import tr

log = get_logger("oxmit.moderation")


def build_router(engine, db, cfg, state) -> Router:
    router = Router(name="moderation")

    def _job(cb: CallbackQuery) -> str | None:
        try:
            jid = cb.data.split(":", 2)[2]
            uuid.UUID(jid)
            return jid
        except (IndexError, ValueError):
            return None

    async def _owner(cb: CallbackQuery) -> bool:
        if cb.from_user is None or not await engine.is_owner(cb.from_user.id):
            await cb.answer(tr("mod_only_owner", "fa"), show_alert=True)
            return False
        return True

    @router.callback_query(F.data.startswith("mod:ask:"))
    async def on_ask(cb: CallbackQuery):
        jid = _job(cb)
        if jid is None or not await _owner(cb):
            return
        await cb.answer()
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tr("mod_btn_confirm", "fa"), callback_data=f"mod:ok:{jid}")],
            [InlineKeyboardButton(text=tr("mod_btn_abort", "fa"), callback_data=f"mod:no:{jid}")],
        ])
        try:
            await cb.message.edit_reply_markup(reply_markup=kb)
        except (TelegramAPIError, AttributeError):
            pass

    @router.callback_query(F.data.startswith("mod:no:"))
    async def on_abort(cb: CallbackQuery):
        jid = _job(cb)
        if jid is None or not await _owner(cb):
            return
        await cb.answer()
        try:
            await cb.message.edit_reply_markup(reply_markup=engine._mod_kb(jid))
        except (TelegramAPIError, AttributeError):
            pass

    @router.callback_query(F.data.startswith("mod:ok:"))
    async def on_confirm(cb: CallbackQuery):
        jid = _job(cb)
        if jid is None or not await _owner(cb):
            return
        res = await engine.moderate_job(jid, cb.from_user.id)
        if not res.get("ok"):
            await cb.answer(str(res.get("why")), show_alert=True)
            return
        await cb.answer(tr("mod_already" if res.get("already") else "mod_done", "fa"),
                        show_alert=True)
        log.warning("moderation applied", extra={
            "job_id": jid, "user_id": res.get("target"),
            "detail": f"status_before={res.get('status_before')} already={res.get('already')}"})

    return router
