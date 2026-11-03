"""Media intake: info card, percent-based compression, admin profile tools.

User flow: video -> info card with a single compress button -> user sends a
number 1..20 (size reduction percent) -> job runs on the `custom` profile with
a computed target bitrate. Admins additionally get the full profile grid.
"""
from __future__ import annotations

import time
import uuid as uuid_mod
from dataclasses import dataclass, field

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from .. import forcesub
from .. import media as media_mod
from ..engine import AdmissionError, _as_uuid
from ..log import get_logger
from ..media import human_size
from ..profiles import BY_KEY, PROFILES
from ..texts import reject_text, tr
from .common import ensure_user, is_admin

log = get_logger("oxmit.intake")

VIDEO_DOCS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".ts", ".m2ts", ".flv",
              ".wmv", ".mpg", ".mpeg", ".m4v", ".3gp"}

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


@dataclass
class PendingPick:
    file_id: str
    file_unique_id: str
    size: int
    filename: str | None
    chat_id: int
    tg_id: int
    source_msg_id: int
    duration: int | None = None
    width: int | None = None
    height: int | None = None
    mime: str | None = None
    created: float = field(default_factory=time.time)


def _parse_level(raw: str) -> int | None:
    """Accept 15, ۱۵, «15 درصد»/«درجه 15»/15% -> int in 1..20, else None."""
    text = (raw or "").strip().lower().translate(_PERSIAN_DIGITS)
    for token in ("درصد", "درجه", "percent", "level", "%"):
        text = text.replace(token, " ").strip()
    try:
        value = int(float(text))
    except (TypeError, ValueError):
        return None
    return value if 1 <= value <= 20 else None


def build_router(engine, db, cfg, state) -> Router:
    router = Router(name="intake")
    video_pending: dict[int, PendingPick] = {}    # tg_id -> pick, compress button shown
    percent_pending: dict[int, PendingPick] = {}  # tg_id -> pick, waiting for a number
    pending: dict[str, PendingPick] = {}          # admin profile-grid keys
    pending_custom: dict[int, tuple[PendingPick, float]] = {}  # admin target size

    def _kb_profile_grid(prefix: str, key_id: str, lang: str) -> InlineKeyboardMarkup:
        rows = []
        row = []
        for p in PROFILES:
            if p.key == "custom":
                continue
            row.append(InlineKeyboardButton(text=p.title_fa, callback_data=f"{prefix}:{key_id}:{p.key}"))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([
            InlineKeyboardButton(text=tr("btn_custom_size", lang),
                                 callback_data=f"{prefix}:{key_id}:custom"),
        ])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _cancel_kb(job_id: str, lang: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=tr("btn_cancel_job", lang),
                                 callback_data=f"canc:{job_id}"),
        ]])

    def _reject(code: str, lang: str, **fmt) -> str:
        return reject_text(code, lang, **fmt)

    async def submit_now(pick: PendingPick, profile_key: str,
                         target_mb: int | None = None, level: int | None = None) -> None:
        user = await db.fetchrow("SELECT language FROM users WHERE tg_id = $1", pick.tg_id)
        lang = (user["language"] if user else None) or "fa"
        status = None
        try:
            status = await engine.bot.send_message(pick.chat_id, "⏳ …")
        except TelegramAPIError:
            pass
        try:
            result = await engine.handle_submission(
                tg_id=pick.tg_id,
                chat_id=pick.chat_id,
                source_msg_id=pick.source_msg_id,
                status_msg_id=status.message_id if status else None,
                size_bytes=pick.size,
                filename=pick.filename,
                profile_key=profile_key,
                file_id=pick.file_id,
                file_unique_id=pick.file_unique_id,
                target_mb=target_mb,
                compress_level=level,
            )
        except AdmissionError as exc:
            text = _reject(exc.code, lang, **exc.fmt)
            if status:
                await engine.edit_status_sync(pick.chat_id, status.message_id, text)
            else:
                try:
                    await engine.bot.send_message(pick.chat_id, text)
                except TelegramAPIError:
                    pass
            return
        except Exception:  # noqa: BLE001 - never leave the user in silence
            log.exception("submission crashed", extra={"user_id": pick.tg_id,
                                                       "profile": profile_key})
            text = tr("submit_error", lang)
            if status:
                await engine.edit_status_sync(pick.chat_id, status.message_id, text)
            else:
                try:
                    await engine.bot.send_message(pick.chat_id, text)
                except TelegramAPIError:
                    pass
            return
        outcome = result["outcome"]
        queue_note = ""
        if outcome == "queued" and result.get("job_id"):
            try:
                pos = await db.fetchval(
                    """
                    SELECT count(*) FROM jobs
                    WHERE status IN ('queued','deferred')
                      AND (priority > (SELECT priority FROM jobs WHERE id = $1::uuid)
                           OR (priority = (SELECT priority FROM jobs WHERE id = $1::uuid)
                               AND enqueued_at < (SELECT enqueued_at FROM jobs
                                                  WHERE id = $1::uuid)))
                    """,
                    _as_uuid(result["job_id"]),
                )
                if pos:
                    queue_note = "\n📍 " + tr("queue_position", "fa", n=pos)
            except Exception:  # noqa: BLE001 - informational only
                queue_note = ""
        if outcome == "joined" and status:
            await engine.edit_status_sync(pick.chat_id, status.message_id,
                                          tr("status_joined", lang))
        elif outcome == "reused" and status:
            await engine.edit_status_sync(pick.chat_id, status.message_id,
                                          tr("status_reused", lang))
        elif outcome == "queued" and status and level is not None:
            estimate = result.get("estimate") or ""
            text = tr("level_accepted", lang, level=level)
            if estimate:
                text += "\n" + estimate
            text += queue_note
            try:
                await engine.bot.edit_message_text(
                    chat_id=pick.chat_id, message_id=status.message_id,
                    text=text,
                    reply_markup=_cancel_kb(result["job_id"], lang),
                )
            except TelegramAPIError:
                pass
        elif outcome == "deferred" and status:
            note = ""
            if result.get("estimate"):
                note = "\n" + result["estimate"] + "\n"
            await engine.edit_status_sync(pick.chat_id, status.message_id,
                                          tr("status_deferred", lang) + note)
        elif outcome == "queued" and status:
            # non-custom profiles (admins)
            estimate = result.get("estimate") or ""
            try:
                await engine.bot.edit_message_text(
                    chat_id=pick.chat_id, message_id=status.message_id,
                    text=tr("status_queued_hint", lang)
                         + (("\n" + estimate) if estimate else "") + queue_note,
                    reply_markup=_cancel_kb(result["job_id"], lang),
                )
            except TelegramAPIError:
                pass

    def _register_pending(pick: PendingPick) -> str:
        key = uuid_mod.uuid4().hex[:10]
        pending[key] = pick
        return key

    def _extract_media(message: Message) -> PendingPick | None:
        video = message.video
        document = message.document
        if document is not None:
            name = document.file_name or "file"
            mime = (document.mime_type or "").lower()
            suffix = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
            if not mime.startswith("video/") and suffix not in VIDEO_DOCS:
                return None
            return PendingPick(
                file_id=document.file_id, file_unique_id=document.file_unique_id,
                size=document.file_size or 0, filename=name,
                chat_id=message.chat.id, tg_id=message.from_user.id,
                source_msg_id=message.message_id, mime=mime or suffix,
            )
        if video is None:
            return None
        return PendingPick(
            file_id=video.file_id, file_unique_id=video.file_unique_id,
            size=video.file_size or 0, filename=video.file_name or "video.mp4",
            chat_id=message.chat.id, tg_id=message.from_user.id,
            source_msg_id=message.message_id,
            duration=video.duration, width=video.width, height=video.height,
            mime=(video.mime_type or ""),
        )

    @router.message(F.video | F.document)
    async def on_media(message: Message):
        if message.from_user is None:
            return
        user = await ensure_user(db, message.from_user)
        if user["is_blocked"]:
            return
        lang = user["language"] or "fa"
        pick = _extract_media(message)
        if pick is None:
            return

        admin_user = await is_admin(db, cfg, message.from_user.id)
        if not state.archive_channel_id:
            await message.answer(
                tr("archive_setup_admin", lang) if admin_user
                else _reject("archive_not_configured", lang)
            )
            return

        block = await forcesub.gate(engine, db, pick.tg_id, is_admin_user=admin_user)
        if block is not None:
            await message.answer(tr("fsub_required", lang),
                                 reply_markup=forcesub.join_markup(block, lang))
            return

        if not admin_user:
            limits = await engine.effective_limits(message.from_user.id)
            if pick.size > limits["max_source_bytes"]:
                await message.answer(_reject(
                    "too_large_tier", lang,
                    max_gb=limits["max_source_bytes"] // 1024**3))
                return
            max_dur = limits["max_duration_s"]
            if max_dur and pick.duration and pick.duration > max_dur:
                hours = max_dur / 3600
                await message.answer(_reject(
                    "too_long", lang,
                    max_h=f"{hours:.0f} ساعت" if hours >= 1 else f"{max_dur / 60:.0f} دقیقه"))
                return

        # --- info card (Telegram metadata only; nothing is invented) ---
        dur = None
        if pick.duration:
            dur = time.strftime("%H:%M:%S", time.gmtime(pick.duration))
        res = (f"{pick.width}×{pick.height}" if pick.width and pick.height
               else tr("info_unavailable", lang))
        kind = tr("info_kind_video", lang) if message.video else tr("info_kind_doc", lang)
        card = tr(
            "info_card", lang,
            name=(pick.filename or "?")[:48],
            size=human_size(pick.size),
            limit_note="",
            dur=dur or tr("info_unavailable", lang),
            res=res,
            codec=(pick.mime or tr("info_unavailable", lang))[:24],
            kind=kind,
        )

        if admin_user:
            percent_pending.pop(pick.tg_id, None)
            video_pending[pick.tg_id] = pick  # also powers the level button
            key = _register_pending(pick)
            kb = _kb_profile_grid("pk", key, lang)
            kb.inline_keyboard.insert(0, [InlineKeyboardButton(
                text=tr("btn_compress", lang) + " (درجه)", callback_data="cmp:go")])
            await message.answer(card + "\n\n" + tr("choose_profile_for", lang),
                                 reply_markup=kb)
            return

        percent_pending.pop(pick.tg_id, None)
        video_pending[pick.tg_id] = pick
        await message.answer(
            card + "\n\n" + tr("choose_profile_for", lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=tr("btn_compress", lang),
                                     callback_data="cmp:go"),
            ]]),
        )

    # ---- compress button -> ask for the compression level ----
    @router.callback_query(F.data == "cmp:go")
    async def on_compress_btn(callback: CallbackQuery):
        if callback.message is None:
            return
        pick = video_pending.get(callback.from_user.id)
        if pick is None:
            await callback.answer(tr("cancel_expired", "fa"), show_alert=True)
            return
        await callback.answer()
        percent_pending[callback.from_user.id] = pick
        try:
            await engine.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                reply_markup=None,
            )
        except TelegramAPIError:
            pass
        await callback.message.answer(tr("level_prompt", "fa"))

    def _waiting_percent(message: Message) -> bool:
        return message.from_user is not None and message.from_user.id in percent_pending

    @router.message(F.text, _waiting_percent)
    async def on_percent_text(message: Message):
        pick = percent_pending.pop(message.from_user.id, None)
        if pick is None:
            return
        lang_row = await db.fetchrow("SELECT language FROM users WHERE tg_id = $1",
                                     message.from_user.id)
        lang = lang_row["language"] or "fa"
        level = _parse_level(message.text or "")
        if level is None:
            percent_pending[message.from_user.id] = pick
            await message.answer(tr("level_invalid", lang))
            return
        await submit_now(pick, "level", level=level)

    # ---- admin: profile picked from the grid ----
    @router.callback_query(F.data.startswith("pk:"))
    async def on_profile_pick(callback: CallbackQuery):
        await callback.answer()
        try:
            _, key_id, profile_key = callback.data.split(":", 2)
        except ValueError:
            return
        pick = pending.pop(key_id, None)
        if pick is None or callback.message is None:
            return
        if profile_key not in BY_KEY:
            return
        lang = await db.fetchval("SELECT language FROM users WHERE tg_id = $1", pick.tg_id) or "fa"
        try:
            await engine.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                reply_markup=None,
            )
        except TelegramAPIError:
            pass
        if profile_key == "custom":
            pending_custom[pick.tg_id] = (pick, time.time())
            await callback.message.answer(tr("custom_size_prompt", lang))
            return
        await submit_now(pick, profile_key)

    # ---- admin: custom target size: next numeric message ----
    def _has_custom_pending(message: Message) -> bool:
        p = pending_custom.get(message.from_user.id)
        return bool(p) and time.time() - p[1] < 600

    @router.message(F.text, _has_custom_pending)
    async def on_custom_size(message: Message):
        pick, _ts = pending_custom.pop(message.from_user.id, None)
        lang = await db.fetchval("SELECT language FROM users WHERE tg_id = $1", pick.tg_id) or "fa"
        raw = (message.text or "").strip().replace(",", "").lower()
        try:
            if raw.endswith("gb") or raw.endswith("g"):
                target_mb = int(float(raw.rstrip("gb").rstrip("g")) * 1024)
            elif raw.endswith("mb") or raw.endswith("m"):
                target_mb = int(float(raw.rstrip("mb").rstrip("m")))
            else:
                target_mb = int(float(raw))
        except ValueError:
            await message.answer(_reject("bad_target", lang, detail=raw[:20]))
            return
        if not (cfg.target_min_mb <= target_mb <= cfg.target_max_gb * 1024):
            await message.answer(_reject(
                "bad_target", lang,
                detail=f"{cfg.target_min_mb}MB..{cfg.target_max_gb}GB"))
            return
        if pick.size and target_mb * 1024 * 1024 >= pick.size:
            await message.answer(_reject(
                "bad_target", lang, detail=f"<= source {human_size(pick.size)}"))
            return
        await submit_now(pick, "custom", target_mb=target_mb)

    # ---- failure recovery buttons ----
    @router.callback_query(F.data.startswith("rtry:"))
    async def on_retry(callback: CallbackQuery):
        await callback.answer()
        job_id = callback.data.split(":", 1)[1]
        ok, info = await engine.retry_user_job(job_id, callback.from_user.id)
        if not ok:
            await callback.message.answer(tr("retry_not_allowed", "fa"))
        else:
            await callback.message.answer(tr("retry_started", "fa", job=info))

    @router.callback_query(F.data.startswith("errd:"))
    async def on_error_details(callback: CallbackQuery):
        await callback.answer()
        job_id = callback.data.split(":", 1)[1]
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
            msg = tr("err_details_none", "fa")
        await callback.message.answer(f"ℹ️ [{cat}]\n{msg}")

    # ---- cancel button on the progress card ----
    @router.callback_query(F.data.startswith("canc:"))
    async def on_cancel_btn(callback: CallbackQuery):
        job_id = callback.data.split(":", 1)[1]
        row = await db.fetchrow("SELECT * FROM jobs WHERE id = $1", _as_uuid(job_id))
        if not row:
            await callback.answer(tr("job_gone", "fa"), show_alert=True)
            return
        if row["requester_tg_id"] != callback.from_user.id and not await is_admin(
            db, cfg, callback.from_user.id
        ):
            await callback.answer(tr("admin_denied", "fa"), show_alert=True)
            return
        ok = await engine.cancel_job(row)
        if ok:
            await callback.answer(tr("cancelled", "fa", job=str(row["id"])[:8]),
                                  show_alert=True)
        else:
            await callback.answer(tr("nothing_to_cancel", "fa"), show_alert=True)

    # ---- library-style redeliver button (job-based) ----
    @router.callback_query(F.data.startswith("rdl:"))
    async def on_redeliver(callback: CallbackQuery):
        await callback.answer()
        job_id = callback.data.split(":", 1)[1]
        if callback.message is None:
            return
        lang = await db.fetchval(
            "SELECT language FROM users WHERE tg_id = $1", callback.from_user.id
        ) or "fa"
        ok, method = await engine.redeliver(job_id, callback.message.chat.id,
                                            callback.from_user.id)
        if not ok:
            await callback.message.answer(tr("status_delivery_failed", lang))

    # ---- archive channel discovery ----
    @router.channel_post()
    async def on_channel_post(message: Message):
        if state.archive_channel_id:
            return
        chat = message.chat
        if chat.type != "channel":
            return
        try:
            me = await engine.bot.get_me()
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
        state.archive_channel_id = chat.id
        await db.set_config("archive_channel_id", chat.id)
        log.info("archive channel discovered", extra={"detail": str(chat.id)})
        for admin in await engine.admin_ids():
            try:
                await engine.bot.send_message(
                    admin, tr("archive_configured", "fa",
                              channel=chat.id, title=chat.title or "?")
                )
            except TelegramAPIError:
                pass

    @router.message(F.forward_origin)
    async def on_forward(message: Message):
        origin = message.forward_origin
        chat = getattr(origin, "chat", None)
        if chat is None or chat.type != "channel":
            return
        if not await is_admin(db, cfg, message.from_user.id):
            return
        if state.archive_channel_id == chat.id:
            await message.answer(tr("archive_configured", "fa",
                                    channel=chat.id, title=chat.title or "?"))
            return
        pending_archive_chat["chat"] = chat
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📌 تنظیم به‌عنوان کانال آرشیو",
                                 callback_data="setarch:yes")
        ]])
        await message.answer(
            f"این پیام از کانال «{chat.title or chat.id}» فوروارد شده است.",
            reply_markup=kb,
        )

    pending_archive_chat: dict = {}

    @router.callback_query(F.data == "setarch:yes")
    async def _set_archive(cb: CallbackQuery):
        await cb.answer()
        chat = pending_archive_chat.get("chat")
        if chat is None or cb.message is None:
            return
        try:
            me = await engine.bot.get_me()
            member = await engine.bot.get_chat_member(chat.id, me.id)
            if member.status != "administrator" or not getattr(
                member, "can_post_messages", False
            ):
                await cb.message.answer(tr("archive_verify_failed", "fa",
                                           error="bot is not admin with post rights"))
                return
            test = await engine.bot.send_message(chat.id, "✅ Oxmit archive test")
            await engine.bot.delete_message(chat.id, test.message_id)
        except TelegramAPIError as exc:
            await cb.message.answer(tr("archive_verify_failed", "fa",
                                       error=str(exc)[:120]))
            return
        state.archive_channel_id = chat.id
        await db.set_config("archive_channel_id", chat.id)
        await cb.message.answer(tr("archive_configured", "fa",
                                   channel=chat.id, title=chat.title or "?"))

    async def sweep_pending() -> None:
        cutoff = time.time() - 3600
        for uid in [u for u, p in video_pending.items() if p.created < cutoff]:
            video_pending.pop(uid, None)
        for uid in [u for u, p in percent_pending.items() if p.created < cutoff]:
            percent_pending.pop(uid, None)
        for key in [k for k, v in pending.items() if v.created < cutoff]:
            pending.pop(key, None)
        now = time.time()
        for uid in [u for u, (_, t) in pending_custom.items() if now - t > 600]:
            pending_custom.pop(uid, None)

    router.sweep_pending = sweep_pending  # type: ignore[attr-defined]
    return router
