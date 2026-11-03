"""Admin commands kept as text commands: /setarchive /retry (panel has the rest)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from ..log import get_logger
from ..texts import tr
from .common import is_admin

log = get_logger("oxmit.admin")


def build_router(engine, db, cfg, state) -> Router:
    router = Router(name="admin")

    async def guard(message: Message) -> bool:
        if not await is_admin(db, cfg, message.from_user.id):
            await message.answer(tr("admin_denied"))
            return False
        return True

    @router.message(F.text.startswith("/retry"))
    async def on_retry(message: Message):
        if not await guard(message):
            return
        parts = (message.text or "").split()
        if len(parts) < 2:
            await message.answer("استفاده: /retry <job_id>")
            return
        prefix = parts[1].strip()
        row = await db.fetchrow(
            "SELECT * FROM jobs WHERE id::text LIKE $1 || '%' AND status = 'failed' "
            "ORDER BY enqueued_at DESC LIMIT 1",
            prefix,
        )
        if not row:
            await message.answer(tr("retry_not_allowed", "fa"))
            return
        await db.execute(
            "UPDATE jobs SET status='queued', retries=0, encore_job_id=NULL, progress=0, "
            "error_category=NULL, error_message=NULL, updated_at=now(), stage='queued' "
            "WHERE id=$1",
            row["id"],
        )
        engine.spawn(engine.run_job(str(row["id"])))
        await message.answer(tr("admin_retry_ok", "fa", job=str(row["id"])[:8]))

    @router.message(F.text.startswith("/setarchive"))
    async def on_setarchive(message: Message):
        if not await guard(message):
            return
        parts = (message.text or "").split()
        if len(parts) < 2:
            await message.answer("استفاده: /setarchive -100XXXXXXXXXX")
            return
        try:
            chat_id = int(parts[1].strip())
        except ValueError:
            await message.answer("شناسهٔ عددی نامعتبر است.")
            return
        try:
            chat = await engine.bot.get_chat(chat_id)
            me = await engine.bot.get_me()
            member = await engine.bot.get_chat_member(chat_id, me.id)
            if member.status != "administrator" or not getattr(
                member, "can_post_messages", False
            ):
                await message.answer(tr("archive_verify_failed", "fa",
                                        error="bot is not admin with post rights"))
                return
            test = await engine.bot.send_message(chat_id, "✅ Oxmit archive test")
            await engine.bot.delete_message(chat_id, test.message_id)
        except Exception as exc:  # noqa: BLE001
            await message.answer(tr("archive_verify_failed", "fa", error=str(exc)[:150]))
            return
        state.archive_channel_id = chat_id
        await db.set_config("archive_channel_id", chat_id)
        log.info("archive channel set", extra={"detail": str(chat_id)})
        await message.answer(tr("archive_configured", "fa",
                                channel=chat_id, title=chat.title or "?"))

    return router
