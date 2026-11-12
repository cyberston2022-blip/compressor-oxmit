"""Start command: greeting + first-run admin bootstrap + force-sub gate."""
from __future__ import annotations

from collections import deque

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from .. import forcesub
from .. import webpanel
from ..log import get_logger
from ..texts import tr
from .common import ensure_user, is_admin

log = get_logger("oxmit.menu")


def build_router(engine, db, cfg, state) -> Router:
    router = Router(name="menu")
    mint_history: dict[int, deque] = {}  # admin tg id -> one-time link mint times

    @router.message(F.text.startswith("/start"))
    async def on_start(message: Message):
        if message.from_user is None:
            return
        user = await ensure_user(db, message.from_user)
        lang = user["language"] or "fa"
        admins = await engine.admin_ids()
        first = not admins and cfg.owner_claim
        if first:
            # Conditional write: two concurrent first-run /start tasks must
            # not both mint an owner. (A truly simultaneous race can still
            # slip through READ COMMITTED; operators can /demote — accepted,
            # owner_claim is opt-in and first-run only.)
            await db.execute(
                "UPDATE users SET is_admin = TRUE WHERE tg_id = $1 "
                "AND NOT EXISTS (SELECT 1 FROM users WHERE is_admin)",
                message.from_user.id,
            )
            engine.invalidate_lang(message.from_user.id)
            log.warning("bootstrap admin claimed", extra={"user_id": message.from_user.id})
        admin_user = first or await is_admin(db, cfg, message.from_user.id)
        block = await forcesub.gate(engine, db, message.from_user.id,
                                    is_admin_user=admin_user)
        if block is not None:
            await message.answer(tr("fsub_required", lang),
                                 reply_markup=forcesub.join_markup(block, lang))
            return
        if not state.archive_channel_id and admin_user:
            await message.answer(tr("archive_setup_admin", lang))
        await message.answer(
            tr("welcome", lang, name=message.from_user.first_name or "",
               max_gb=cfg.max_source_bytes // 1024**3),
        )

    @router.message(F.text.startswith("/panel"))
    async def on_panel(message: Message):
        if message.from_user is None:
            return
        if not await is_admin(db, cfg, message.from_user.id):
            return
        url = cfg.panel_public_url
        token = cfg.internal_panel_token or ""
        if not url or not token:
            await message.answer(
                "🌐 پنل وب هنوز تنظیم نشده — PANEL_PUBLIC_URL و ADMIN_PANEL_TOKEN "
                "باید در .env سرور ست شده باشند.")
            return
        base = url.rstrip("/")
        if base.endswith("/panel"):
            base = base[: -len("/panel")]
        link = webpanel.mint_one_time_link(message.from_user.id, mint_history, base)
        if link is None:
            await message.answer(
                "⏳ زیادتر از حد لینک ساختی — ۱۰ دقیقه دیگر دوباره /panel بزنید.")
            return
        await message.answer(
            "🔗 ورود یک‌بارمصرف به پنل مدیریت (۱۰ دقیقه اعتبار دارد):\n" + link +
            "\n\n⚠️ لینک فقط یک‌بار کار می‌کند — آن را در گروه/کانال فوروارد نکنید."
            "\nاگر لینک منقضی شد دوباره /panel بزنید یا توکن را در فرم وارد کن.")
        log.info("one-time panel link minted", extra={"user_id": message.from_user.id})

    @router.callback_query(F.data == "fsub:check")
    async def on_fsub_check(callback: CallbackQuery):
        forcesub.clear_cache()
        block = await forcesub.gate(engine, db, callback.from_user.id,
                                    is_admin_user=await is_admin(db, cfg,
                                                                 callback.from_user.id))
        if block is None:
            await callback.answer()
            try:
                await callback.message.edit_text(tr("fsub_ok", "fa"))
            except Exception:  # noqa: BLE001
                pass
        else:
            # Single answer per query: answering twice raises
            # TelegramBadRequest and the alert never reaches the user.
            await callback.answer(tr("fsub_still_not", "fa"), show_alert=True)

    return router
