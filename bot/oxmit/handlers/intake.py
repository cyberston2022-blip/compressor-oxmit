"""Media intake: video -> output filename -> persistent queue (no download).

Flow (spec "file renaming at the beginning of the workflow"):
1. The user sends a video. Only Telegram metadata is inspected (size,
   duration, dimensions, mime); NOTHING is downloaded.
2. A persistent draft row is created and the bot asks for the output file
   name (Persian or English, no extension).
3. The answer is normalized (edu480.normalize_output_name) and the job is
   registered in the queue with that name; the prompt message becomes the
   live queue/progress card.

Draft matching is deterministic: each user has at most ONE active filename
prompt (DB partial unique index). Further videos wait behind it and are
prompted one after another, so a name can never land on the wrong video.
A reply to a specific prompt targets that draft explicitly. Drafts expire
after NAMING_TIMEOUT_MIN and survive restarts (they live in PostgreSQL).

The only compression profile is EDU480 - there is no profile picker.
"""
from __future__ import annotations

import time
import uuid as uuid_mod

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from .. import edu480
from .. import forcesub
from .. import media as media_mod
from ..engine import AdmissionError, _as_uuid
from ..log import get_logger
from ..media import human_size
from ..texts import reject_text, tr
from .common import ensure_user, is_admin

log = get_logger("oxmit.intake")

VIDEO_DOCS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".ts", ".m2ts", ".flv",
              ".wmv", ".mpg", ".mpeg", ".m4v", ".3gp"}

# per-user callback throttle (UX-01/02): a 0.6s gap kills double-tap storms.
_last_cb: dict[int, float] = {}


def _throttled(callback: CallbackQuery) -> bool:
    """True when the same user pressed a button within the last 0.6s."""
    now = time.monotonic()
    uid = callback.from_user.id
    if now - _last_cb.get(uid, 0.0) < 0.6:
        return True
    if len(_last_cb) > 5000:
        _last_cb.clear()
    _last_cb[uid] = now
    return False


def _clock(seconds) -> str:
    if not seconds:
        return "?"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def extract_media(message: Message) -> dict | None:
    """Telegram metadata of a video / video document, or None."""
    video = message.video
    document = message.document
    if document is not None:
        name = document.file_name or "file"
        mime = (document.mime_type or "").lower()
        suffix = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
        if not mime.startswith("video/") and suffix not in VIDEO_DOCS:
            return None
        return {"file_id": document.file_id, "file_unique_id": document.file_unique_id,
                "size": document.file_size or 0, "filename": name, "mime": mime or suffix,
                "duration": None, "width": None, "height": None}
    if video is None:
        return None
    return {"file_id": video.file_id, "file_unique_id": video.file_unique_id,
            "size": video.file_size or 0, "filename": video.file_name or "video.mp4",
            "mime": video.mime_type or "", "duration": video.duration,
            "width": video.width, "height": video.height}


def build_router(engine, db, cfg, state) -> Router:
    router = Router(name="intake")

    def _reject(code: str, lang: str, **fmt) -> str:
        return reject_text(code, lang, **fmt)

    def _name_kb(draft_id, lang: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tr("btn_keep_name", lang),
                                  callback_data=f"nm:keep:{draft_id}")],
            [InlineKeyboardButton(text=tr("btn_cancel_video", lang),
                                  callback_data=f"nm:cancel:{draft_id}")],
        ])

    # ------------------------------------------------------------------
    # drafts
    # ------------------------------------------------------------------
    async def _prompt_draft(draft) -> None:
        """Make `draft` the user's single active naming prompt."""
        lang = await engine._lang(draft["tg_id"])
        ok = await db.fetchval(
            "UPDATE intake_drafts SET status = 'awaiting_name', updated_at = now() "
            "WHERE id = $1 AND status = 'waiting' "
            "AND NOT EXISTS (SELECT 1 FROM intake_drafts d WHERE d.tg_id = $2 "
            "                AND d.status = 'awaiting_name') RETURNING id",
            draft["id"], draft["tg_id"])
        if not ok:
            return
        text = tr("name_prompt", lang, src=(draft["filename"] or "?")[:60],
                  size=human_size(draft["size_bytes"]), dur=_clock(draft["duration_s"]))
        try:
            msg = await engine.bot.send_message(
                draft["chat_id"], text, reply_markup=_name_kb(draft["id"], lang),
                reply_to_message_id=draft["source_message_id"])
        except TelegramAPIError:
            try:
                msg = await engine.bot.send_message(
                    draft["chat_id"], text, reply_markup=_name_kb(draft["id"], lang))
            except TelegramAPIError:
                return
        await db.execute(
            "UPDATE intake_drafts SET prompt_message_id = $2 WHERE id = $1",
            draft["id"], msg.message_id)

    async def _promote_next(tg_id: int) -> None:
        nxt = await db.fetchrow(
            "SELECT * FROM intake_drafts WHERE tg_id = $1 AND status = 'waiting' "
            "ORDER BY created_at LIMIT 1", tg_id)
        if nxt is not None:
            await _prompt_draft(nxt)

    async def _submit_draft(draft, raw_name: str | None, lang: str) -> None:
        """Atomically consume the draft and register the job (still no download)."""
        stem = edu480.normalize_output_name(raw_name) if raw_name is not None else \
            edu480.normalize_output_name(draft["filename"])
        if stem is None:
            stem = "video"
        taken = await db.fetchval(
            "UPDATE intake_drafts SET status = 'submitted', updated_at = now() "
            "WHERE id = $1 AND status IN ('awaiting_name', 'waiting') RETURNING id",
            draft["id"])
        if not taken:
            return  # double tap / duplicate update: already handled
        chat_id = draft["chat_id"]
        status_id = draft["prompt_message_id"]
        out_name = stem + ".mp4"
        if status_id:
            await engine.edit_status_sync(
                chat_id, status_id, tr("name_accepted", lang, name=out_name) + "\n⏳ …")
        else:
            try:
                m = await engine.bot.send_message(chat_id, tr("name_accepted", lang, name=out_name))
                status_id = m.message_id
            except TelegramAPIError:
                status_id = None
        try:
            result = await engine.register_job(
                tg_id=draft["tg_id"], chat_id=chat_id,
                source_msg_id=draft["source_message_id"], status_msg_id=status_id,
                file_id=draft["file_id"], file_unique_id=draft["file_unique_id"],
                size_bytes=int(draft["size_bytes"] or 0), filename=draft["filename"],
                mime=draft["mime"], duration_s=draft["duration_s"],
                width=draft["width"], height=draft["height"], output_name=stem)
        except AdmissionError as exc:
            await db.execute("UPDATE intake_drafts SET status = 'cancelled' WHERE id = $1",
                             draft["id"])
            await engine.edit_status_sync(chat_id, status_id, _reject(exc.code, lang, **exc.fmt))
            await _promote_next(draft["tg_id"])
            return
        except Exception:  # noqa: BLE001 - never leave the user in silence
            log.exception("registration crashed", extra={"user_id": draft["tg_id"]})
            await db.execute("UPDATE intake_drafts SET status = 'cancelled' WHERE id = $1",
                             draft["id"])
            await engine.edit_status_sync(chat_id, status_id, tr("submit_error", lang))
            await _promote_next(draft["tg_id"])
            return
        job_id = result.get("job_id")
        if job_id:
            await db.execute("UPDATE intake_drafts SET job_id = $2 WHERE id = $1",
                             draft["id"], _as_uuid(job_id))
        outcome = result.get("outcome")
        if outcome == "queued" and status_id:
            text = engine.queue_card_text(
                lang, name=out_name, size=int(draft["size_bytes"] or 0),
                dur=draft["duration_s"], job_id=job_id, info=result)
            try:
                await engine.bot.edit_message_text(
                    chat_id=chat_id, message_id=status_id, text=text,
                    reply_markup=engine._job_kb(job_id, lang))
            except TelegramAPIError:
                pass
        elif outcome == "joined" and status_id:
            await engine.edit_status_sync(chat_id, status_id, tr("status_joined", lang))
        elif outcome == "reused" and result.get("kind") == "known_output":
            try:
                await engine.bot.send_message(chat_id, tr("known_output", lang))
            except TelegramAPIError:
                pass
        await _promote_next(draft["tg_id"])

    # ------------------------------------------------------------------
    # video received
    # ------------------------------------------------------------------
    @router.message(F.video | F.document)
    async def on_media(message: Message):
        if message.from_user is None:
            return
        user = await ensure_user(db, message.from_user)
        lang = user["language"] or "fa"
        if user["is_blocked"]:
            await message.answer(_reject("blocked_user", lang))
            return
        pick = extract_media(message)
        if pick is None:
            return
        admin_user = await is_admin(db, cfg, message.from_user.id)
        if not state.archive_channel_id:
            await message.answer(
                tr("archive_setup_admin", lang) if admin_user
                else _reject("archive_not_configured", lang))
            return
        block = await forcesub.gate(engine, db, message.from_user.id, is_admin_user=admin_user)
        if block is not None:
            await message.answer(tr("fsub_required", lang),
                                 reply_markup=forcesub.join_markup(block, lang))
            return
        if state.paused:
            await message.answer(_reject("paused", lang))
            return
        # Lightweight validation on Telegram metadata (no download).
        if not admin_user:
            limits = await engine.effective_limits(message.from_user.id)
            if pick["size"] > limits["max_source_bytes"]:
                await message.answer(_reject("too_large_tier", lang,
                                             max_gb=limits["max_source_bytes"] // 1024**3))
                return
            max_dur = limits["max_duration_s"]
            if max_dur and pick["duration"] and pick["duration"] > max_dur:
                hours = max_dur / 3600
                await message.answer(_reject(
                    "too_long", lang,
                    max_h=f"{hours:.0f} ساعت" if hours >= 1 else f"{max_dur / 60:.0f} دقیقه"))
                return
        draft_id = await db.fetchval(
            """
            INSERT INTO intake_drafts(tg_id, chat_id, source_message_id, file_id,
                file_unique_id, size_bytes, filename, mime, duration_s, width, height)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            ON CONFLICT (chat_id, source_message_id) DO NOTHING RETURNING id
            """,
            message.from_user.id, message.chat.id, message.message_id, pick["file_id"],
            pick["file_unique_id"], int(pick["size"] or 0), pick["filename"],
            (pick["mime"] or "")[:64], pick["duration"], pick["width"], pick["height"])
        if draft_id is None:
            return  # duplicate Telegram update for the same message
        draft = await db.fetchrow("SELECT * FROM intake_drafts WHERE id = $1", draft_id)
        active = await db.fetchval(
            "SELECT id FROM intake_drafts WHERE tg_id = $1 AND status = 'awaiting_name'",
            message.from_user.id)
        if active is not None:
            await message.answer(tr("name_waiting_turn", lang,
                                    src=(pick["filename"] or "?")[:60]))
            return
        await _prompt_draft(draft)

    # ------------------------------------------------------------------
    # filename answer
    # ------------------------------------------------------------------
    async def _draft_for_text(message: Message):
        """The draft this text answers, or None (then the text is ignored here)."""
        if message.from_user is None or not message.text or message.text.startswith("/"):
            return None
        uid = message.from_user.id
        reply = message.reply_to_message
        if reply is not None:
            d = await db.fetchrow(
                "SELECT * FROM intake_drafts WHERE tg_id = $1 "
                "AND status IN ('awaiting_name','waiting') "
                "AND (prompt_message_id = $2 OR source_message_id = $2) "
                "AND chat_id = $3",
                uid, reply.message_id, message.chat.id)
            if d is not None:
                return d
        return await db.fetchrow(
            "SELECT * FROM intake_drafts WHERE tg_id = $1 AND status = 'awaiting_name' "
            "AND chat_id = $2", uid, message.chat.id)

    async def _awaiting_name(message: Message):
        draft = await _draft_for_text(message)
        return {"draft": draft} if draft is not None else False

    @router.message(F.text, _awaiting_name)
    async def on_name_text(message: Message, draft):
        lang = await engine._lang(message.from_user.id)
        stem = edu480.normalize_output_name(message.text)
        if stem is None:
            await message.answer(tr("name_invalid", lang))
            return
        await _submit_draft(draft, message.text, lang)

    @router.callback_query(F.data.startswith("nm:"))
    async def on_name_button(callback: CallbackQuery):
        if _throttled(callback):
            await callback.answer()
            return
        try:
            _, action, draft_id = callback.data.split(":", 2)
            did = uuid_mod.UUID(draft_id)
        except ValueError:
            await callback.answer()
            return
        draft = await db.fetchrow("SELECT * FROM intake_drafts WHERE id = $1", did)
        lang = await engine._lang(callback.from_user.id)
        if draft is None or draft["tg_id"] != callback.from_user.id:
            await callback.answer(tr("admin_denied", lang), show_alert=True)
            return
        if draft["status"] not in ("awaiting_name", "waiting"):
            await callback.answer(tr("cancel_expired", lang), show_alert=True)
            return
        await callback.answer()
        if action == "keep":
            await _submit_draft(draft, None, lang)
        elif action == "cancel":
            ok = await db.fetchval(
                "UPDATE intake_drafts SET status = 'cancelled', updated_at = now() "
                "WHERE id = $1 AND status IN ('awaiting_name','waiting') RETURNING id", did)
            if ok and callback.message is not None:
                try:
                    await callback.message.edit_text(tr("draft_cancelled", lang))
                except TelegramAPIError:
                    pass
            await _promote_next(draft["tg_id"])

    # ---- cancel button on the queue/progress card ----
    @router.callback_query(F.data.startswith("canc:"))
    async def on_cancel_btn(callback: CallbackQuery):
        if _throttled(callback):
            await callback.answer()
            return
        job_id = callback.data.split(":", 1)[1]
        try:
            row = await db.fetchrow("SELECT * FROM jobs WHERE id = $1", _as_uuid(job_id))
        except ValueError:
            row = None
        if not row:
            await callback.answer(tr("job_gone", "fa"), show_alert=True)
            return
        lang = await engine._lang(callback.from_user.id)
        if row["requester_tg_id"] != callback.from_user.id and not await is_admin(
            db, cfg, callback.from_user.id
        ):
            await callback.answer(tr("admin_denied", lang), show_alert=True)
            return
        await callback.answer(tr("cancelling", lang))
        await engine.cancel_job(row, by_admin=row["requester_tg_id"] != callback.from_user.id)

    # ---- failure recovery buttons ----
    @router.callback_query(F.data.startswith("rtry:"))
    async def on_retry(callback: CallbackQuery):
        if _throttled(callback):
            await callback.answer()
            return
        await callback.answer()
        job_id = callback.data.split(":", 1)[1]
        lang = await engine._lang(callback.from_user.id)
        ok, info = await engine.retry_user_job(job_id, callback.from_user.id)
        if not ok:
            await callback.message.answer(tr("retry_not_allowed", lang))
        else:
            await callback.message.answer(tr("retry_started", lang, job=info))

    @router.callback_query(F.data.startswith("errd:"))
    async def on_error_details(callback: CallbackQuery):
        if _throttled(callback):
            await callback.answer()
            return
        await callback.answer()
        job_id = callback.data.split(":", 1)[1]
        lang = await engine._lang(callback.from_user.id)
        row = await db.fetchrow(
            "SELECT requester_tg_id, error_category, error_message FROM jobs WHERE id = $1",
            _as_uuid(job_id),
        )
        if not row:
            return
        if row["requester_tg_id"] != callback.from_user.id and not await is_admin(
            db, cfg, callback.from_user.id
        ):
            return
        cat = row["error_category"] or "-"
        msg = media_mod.redact((row["error_message"] or "")).replace("`", "'")[:400]
        if not msg:
            msg = tr("err_details_none", lang)
        await callback.message.answer(f"ℹ️ [{cat}]\n{msg}")

    # ---- library-style redeliver button (job-based) ----
    @router.callback_query(F.data.startswith("rdl:"))
    async def on_redeliver(callback: CallbackQuery):
        if _throttled(callback):
            await callback.answer()
            return
        await callback.answer()
        job_id = callback.data.split(":", 1)[1]
        if callback.message is None:
            return
        lang = await engine._lang(callback.from_user.id)
        ok, method = await engine.redeliver(job_id, callback.message.chat.id,
                                            callback.from_user.id)
        if not ok:
            await callback.message.answer(tr("status_delivery_failed", lang))

    # ---- archive channel discovery (SPEC-05: propose + per-admin confirm,
    # never auto-claim) ----
    pending_archive_chat: dict[int, tuple[str, object, float]] = {}  # admin -> (key, chat, ts)

    def _archive_confirm_kb(key: str, lang: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=tr("btn_confirm_archive", lang),
                                 callback_data=f"setarch:{key}"),
            InlineKeyboardButton(text=tr("btn_cancel", lang),
                                 callback_data="setarch:no"),
        ]])

    @router.channel_post()
    async def on_channel_post(message: Message):
        if state.archive_channel_id:
            return
        chat = message.chat
        if chat.type != "channel":
            return
        try:
            me = await engine.get_me_cached()
            member = await engine.bot.get_chat_member(chat.id, me.id)
            if member.status != "administrator" or not getattr(
                member, "can_post_messages", False
            ):
                return
            test = await engine.bot.send_message(chat.id, "✅ Oxmit archive test")
            await engine.bot.delete_message(chat.id, test.message_id)
        except TelegramAPIError as exc:
            log.warning("archive discovery failed", extra={"detail": str(exc)[:200]})
            return
        key = uuid_mod.uuid4().hex[:8]
        for admin in await engine.admin_ids():
            lang = await engine._lang(admin)
            pending_archive_chat[admin] = (key, chat, time.time())
            try:
                await engine.bot.send_message(
                    admin, tr("archive_proposal", lang,
                              channel=chat.title or "?"),
                    reply_markup=_archive_confirm_kb(key, lang),
                )
            except TelegramAPIError:
                pass

    @router.message(F.forward_origin)
    async def on_forward(message: Message):
        if message.from_user is None:
            return  # auto-forward from a linked channel has no from_user
        origin = message.forward_origin
        chat = getattr(origin, "chat", None)
        if chat is None or chat.type != "channel":
            return
        if not await is_admin(db, cfg, message.from_user.id):
            return
        lang = await engine._lang(message.from_user.id)
        if state.archive_channel_id == chat.id:
            await message.answer(tr("archive_configured", lang,
                                    channel=chat.id, title=chat.title or "?"))
            return
        key = uuid_mod.uuid4().hex[:8]
        pending_archive_chat[message.from_user.id] = (key, chat, time.time())
        await message.answer(
            tr("archive_fwd_detected", lang, channel=chat.title or chat.id),
            reply_markup=_archive_confirm_kb(key, lang),
        )

    @router.callback_query(F.data.startswith("setarch:"))
    async def _set_archive(cb: CallbackQuery):
        if _throttled(cb):
            await cb.answer()
            return
        action = cb.data.split(":", 1)[1]
        lang = await engine._lang(cb.from_user.id)
        if action == "no":
            pending_archive_chat.pop(cb.from_user.id, None)
            await cb.answer(tr("pending_cancelled", lang))
            return
        # Pop FIRST: one confirmation per pending entry; only the presser's
        # own entry counts (no cross-admin races, SPEC-05).
        entry = pending_archive_chat.pop(cb.from_user.id, None)
        if entry is None or cb.message is None or action != entry[0]:
            await cb.answer(tr("cancel_expired", lang), show_alert=True)
            return
        key, chat, ts = entry
        if time.time() - ts > 1800:
            await cb.answer(tr("cancel_expired", lang), show_alert=True)
            return
        try:
            me = await engine.get_me_cached()
            member = await engine.bot.get_chat_member(chat.id, me.id)
            if member.status != "administrator" or not getattr(
                member, "can_post_messages", False
            ):
                await cb.message.answer(tr("archive_verify_failed", lang,
                                           error="bot is not admin with post rights"))
                return
            test = await engine.bot.send_message(chat.id, "✅ Oxmit archive test")
            await engine.bot.delete_message(chat.id, test.message_id)
        except TelegramAPIError as exc:
            await cb.message.answer(tr("archive_verify_failed", lang,
                                       error=str(exc)[:120]))
            return
        state.archive_channel_id = chat.id
        await db.set_config("archive_channel_id", chat.id)
        log.info("archive channel confirmed", extra={"detail": str(chat.id)})
        for uid in [u for u, (k, _c, _t) in pending_archive_chat.items() if k == key]:
            pending_archive_chat.pop(uid, None)
        await cb.message.answer(tr("archive_configured", lang,
                                   channel=chat.id, title=chat.title or "?"))

    async def sweep_pending() -> None:
        # Expire unanswered naming prompts (persistent drafts) and move each
        # user's next waiting video up.
        mins = max(1, int(cfg.naming_timeout_min))
        expired = await db.fetch(
            "UPDATE intake_drafts SET status = 'expired', updated_at = now() "
            "WHERE (status = 'awaiting_name' AND updated_at < now() - make_interval(mins => $1)) "
            "   OR (status = 'waiting' AND created_at < now() - make_interval(mins => $1 * 4)) "
            "RETURNING tg_id, chat_id, prompt_message_id", mins)
        users = set()
        for r in expired:
            users.add(r["tg_id"])
            if r["prompt_message_id"]:
                await engine.edit_status_sync(r["chat_id"], r["prompt_message_id"],
                                              tr("name_expired", await engine._lang(r["tg_id"])))
        for uid in users:
            await _promote_next(uid)
        now = time.time()
        # archive proposals: 30-minute confirm window (SPEC-05)
        for uid in [u for u, (_k, _c, t) in pending_archive_chat.items()
                    if now - t > 1800]:
            pending_archive_chat.pop(uid, None)
        # callback throttle map (UX-01): keep it bounded
        mono = time.monotonic()
        for uid in [u for u, t in _last_cb.items() if mono - t > 60]:
            _last_cb.pop(uid, None)

    router.sweep_pending = sweep_pending  # type: ignore[attr-defined]
    return router
