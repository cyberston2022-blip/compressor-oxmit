"""Minimal user settings: language, delivery style, completion notifications.

Restores the three toggles whose DB columns and delivery code paths survived
the 2026-10-29 flow redesign without any UI (F-21/F-22).
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..log import get_logger
from ..texts import tr
from .common import ensure_user

log = get_logger("oxmit.settings")


def build_router(engine, db, cfg, state) -> Router:
    router = Router(name="settings")

    def _kb(row) -> InlineKeyboardMarkup:
        lang = "English ✅" if row["language"] == "en" else "فارسی ✅"
        style = "📁 فایل ✅" if row["delivery_style"] == "doc" else "🎬 ویدیو ✅"
        notify = "روشن ✅" if row["notify_done"] else "خاموش"
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🌐 زبان: {lang}", callback_data="set:lang")],
            [InlineKeyboardButton(text=f"📬 سبک تحویل: {style}", callback_data="set:style")],
            [InlineKeyboardButton(text=f"🔔 اعلان نتیجه: {notify}", callback_data="set:notify")],
        ])

    @router.message(F.text.startswith("/settings"))
    async def on_settings(message: Message):
        if message.from_user is None:
            return
        row = await ensure_user(db, message.from_user)
        await message.answer(
            tr("settings_title", row["language"] or "fa"),
            reply_markup=_kb(row),
        )

    @router.callback_query(F.data.startswith("set:"))
    async def on_toggle(callback: CallbackQuery):
        if callback.message is None or callback.from_user is None:
            return
        key = callback.data.split(":")[1] if callback.data else ""
        row = await db.fetchrow("SELECT * FROM users WHERE tg_id = $1", callback.from_user.id)
        if row is None or key not in ("lang", "style", "notify"):
            await callback.answer()
            return
        if key == "lang":
            new = "en" if row["language"] == "fa" else "fa"
            await db.execute("UPDATE users SET language = $2 WHERE tg_id = $1",
                             row["tg_id"], new)
            engine.invalidate_lang(row["tg_id"])
        elif key == "style":
            new = "doc" if row["delivery_style"] != "doc" else "video"
            await db.execute("UPDATE users SET delivery_style = $2 WHERE tg_id = $1",
                             row["tg_id"], new)
        else:
            new = not row["notify_done"]
            await db.execute("UPDATE users SET notify_done = $2 WHERE tg_id = $1",
                             row["tg_id"], new)
        await callback.answer()
        fresh = await db.fetchrow("SELECT * FROM users WHERE tg_id = $1", row["tg_id"])
        try:
            await callback.message.edit_reply_markup(reply_markup=_kb(fresh))
        except TelegramAPIError:
            pass

    return router
