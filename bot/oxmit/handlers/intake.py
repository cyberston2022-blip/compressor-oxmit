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
from ..decision_engine import is_already_compressed, select_educational_resolution
from ..engine import AdmissionError, _as_uuid
from ..estimate import estimate_output_bytes
from ..log import get_logger
from ..media import human_size
from ..profiles import BY_KEY, PROFILES
from ..texts import reject_text, tr
from .common import ensure_user, is_admin

log = get_logger("oxmit.intake")

VIDEO_DOCS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".ts", ".m2ts", ".flv",
              ".wmv", ".mpg", ".mpeg", ".m4v", ".3gp"}

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# per-user callback throttle (UX-01/02): a 0.6s gap kills double-tap storms
# that re-ran DB lookups / re-sent multi-GB files (Argons plugins/query.py).
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
                    queue_note = "\n📍 " + tr("queue_position", lang, n=pos)
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

        # --- Pre-analysis: Check if already compressed ---
        probe_dict = {
            "width": pick.width,
            "height": pick.height,
            "duration_s": pick.duration,
            "bitrate": int(pick.size * 8 / pick.duration) if (pick.duration and pick.size) else 0,
        }
        already_comp, comp_reason = is_already_compressed(probe_dict, pick.size)

        if already_comp:
            percent_pending.pop(pick.tg_id, None)
            video_pending[pick.tg_id] = pick
            warn_card = tr("already_compressed_warning", lang, reason=comp_reason)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=tr("btn_rostam", lang), callback_data="cmp:rostam")],
                [InlineKeyboardButton(text=tr("btn_send_original", lang), callback_data="cmp:remux")],
                [InlineKeyboardButton(text=tr("btn_cancel_job", lang), callback_data="cmp:stop")],
            ])
            await message.answer(f"{card}\n\n{warn_card}", reply_markup=kb)
            return

        # --- Dynamic predictions for Glass Panel ---
        tw480, th480, _ = select_educational_resolution(pick.width or 1920, pick.height or 1080)
        tw480, th480 = (tw480 or 854), (th480 or 480)
        out_pix_480 = float(tw480 * th480)
        dur = pick.duration or 60.0
        low_480, high_480 = estimate_output_bytes(
            dur, out_pix_480, "h264", 25, audio_kbps=64.0, source_bytes=pick.size
        )
        mid_480 = (low_480 + high_480) / 2 if high_480 > 0 else (pick.size * 0.3)
        cut_480 = max(10, min(95, round((1.0 - mid_480 / pick.size) * 100))) if pick.size > 0 else 75
        mb_480 = max(1, round(mid_480 / (1024 * 1024)))

        tw360, th360 = (640, 360) if min(pick.width or 1920, pick.height or 1080) > 360 else (pick.width or 640, pick.height or 360)
        out_pix_360 = float(tw360 * th360)
        low_360, high_360 = estimate_output_bytes(
            dur, out_pix_360, "h264", 26, audio_kbps=48.0, source_bytes=pick.size
        )
        mid_360 = (low_360 + high_360) / 2 if high_360 > 0 else (pick.size * 0.18)
        cut_360 = max(15, min(97, round((1.0 - mid_360 / pick.size) * 100))) if pick.size > 0 else 85
        mb_360 = max(1, round(mid_360 / (1024 * 1024)))

        btn_480_text = tr("btn_edu480", lang, cut=cut_480, mb=mb_480)
        btn_360_text = tr("btn_edu360", lang, cut=cut_360, mb=mb_360)
        btn_cust_text = tr("btn_custom_target", lang)
        btn_level_text = tr("btn_compress", lang) + " (درجه ۱-۲۰)"

        panel_kb = [
            [InlineKeyboardButton(text=btn_480_text, callback_data="cmp:edu480")],
            [InlineKeyboardButton(text=btn_360_text, callback_data="cmp:edu360")],
            [InlineKeyboardButton(text=btn_cust_text, callback_data="cmp:cust_prompt")],
            [InlineKeyboardButton(text=btn_level_text, callback_data="cmp:go")],
        ]

        if admin_user:
            percent_pending.pop(pick.tg_id, None)
            video_pending[pick.tg_id] = pick
            key = _register_pending(pick)
            kb = _kb_profile_grid("pk", key, lang)
            for row in reversed(panel_kb):
                kb.inline_keyboard.insert(0, row)
            await message.answer(card + "\n\n" + tr("choose_profile_for", lang), reply_markup=kb)
            return

        percent_pending.pop(pick.tg_id, None)
        video_pending[pick.tg_id] = pick
        await message.answer(
            card + "\n\n" + tr("choose_profile_for", lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=panel_kb),
        )

    # ---- educational button handlers (480p and 360p) ----
    @router.callback_query(F.data.in_({"cmp:edu", "cmp:edu480", "cmp:edu360"}))
    async def on_compress_edu_btn(callback: CallbackQuery):
        if _throttled(callback):
            await callback.answer()
            return
        pick = video_pending.get(callback.from_user.id)
        lang = await engine._lang(callback.from_user.id)
        if pick is None:
            await callback.answer(tr("cancel_expired", lang), show_alert=True)
            return
        await callback.answer()
        percent_pending.pop(callback.from_user.id, None)
        try:
            await engine.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                reply_markup=None,
            )
        except TelegramAPIError:
            pass
        target_prof = "edu360" if callback.data == "cmp:edu360" else "edu480"
        await submit_now(pick, target_prof)

    # ---- Rostam & Siavash extreme compression handler ----
    @router.callback_query(F.data == "cmp:rostam")
    async def on_compress_rostam_btn(callback: CallbackQuery):
        if _throttled(callback):
            await callback.answer()
            return
        pick = video_pending.get(callback.from_user.id)
        lang = await engine._lang(callback.from_user.id)
        if pick is None:
            await callback.answer(tr("cancel_expired", lang), show_alert=True)
            return
        await callback.answer()
        percent_pending.pop(callback.from_user.id, None)
        try:
            await engine.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                reply_markup=None,
            )
        except TelegramAPIError:
            pass
        await submit_now(pick, "rostam")

    # ---- Remux (send original) handler ----
    @router.callback_query(F.data == "cmp:remux")
    async def on_compress_remux_btn(callback: CallbackQuery):
        if _throttled(callback):
            await callback.answer()
            return
        pick = video_pending.get(callback.from_user.id)
        lang = await engine._lang(callback.from_user.id)
        if pick is None:
            await callback.answer(tr("cancel_expired", lang), show_alert=True)
            return
        await callback.answer()
        percent_pending.pop(callback.from_user.id, None)
        try:
            await engine.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                reply_markup=None,
            )
        except TelegramAPIError:
            pass
        await submit_now(pick, "remux")

    # ---- custom size prompt handler (for all users) ----
    @router.callback_query(F.data == "cmp:cust_prompt")
    async def on_custom_prompt_btn(callback: CallbackQuery):
        if _throttled(callback):
            await callback.answer()
            return
        pick = video_pending.get(callback.from_user.id)
        lang = await engine._lang(callback.from_user.id)
        if pick is None:
            await callback.answer(tr("cancel_expired", lang), show_alert=True)
            return
        await callback.answer()
        pending_custom[callback.from_user.id] = (pick, time.time())
        try:
            await engine.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                reply_markup=None,
            )
        except TelegramAPIError:
            pass

        # Quick size choice buttons
        src_mb = int(pick.size / (1024 * 1024)) if pick.size else 500
        cands = [50, 100, 200, 400]
        quick_mbs = [m for m in cands if m < src_mb]
        if not quick_mbs:
            quick_mbs = [max(10, src_mb // 2)]

        kb_rows = []
        quick_row = [
            InlineKeyboardButton(text=f"{m} MB", callback_data=f"cset:{m}")
            for m in quick_mbs
        ]
        if quick_row:
            kb_rows.append(quick_row)
        kb_rows.append([InlineKeyboardButton(text=tr("btn_cancel_job", lang), callback_data="cmp:stop")])

        await callback.message.answer(
            tr("custom_target_prompt", lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
        )

    # ---- quick custom size selection callback (cset:<mb>) ----
    @router.callback_query(F.data.startswith("cset:"))
    async def on_custom_quick_set(callback: CallbackQuery):
        if _throttled(callback):
            await callback.answer()
            return
        target_mb_str = callback.data.split(":", 1)[1]
        try:
            target_mb = int(target_mb_str)
        except ValueError:
            await callback.answer()
            return
        entry = pending_custom.pop(callback.from_user.id, None)
        pick = entry[0] if entry else video_pending.get(callback.from_user.id)
        lang = await engine._lang(callback.from_user.id)
        if pick is None:
            await callback.answer(tr("cancel_expired", lang), show_alert=True)
            return
        await callback.answer()
        try:
            await engine.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                reply_markup=None,
            )
        except TelegramAPIError:
            pass
        await submit_now(pick, "custom", target_mb=target_mb)

    # ---- compress button -> ask for the compression level ----
    @router.callback_query(F.data == "cmp:go")
    async def on_compress_btn(callback: CallbackQuery):
        if callback.message is None:
            return
        pick = video_pending.get(callback.from_user.id)
        lang = await engine._lang(callback.from_user.id)
        if pick is None:
            await callback.answer(tr("cancel_expired", lang), show_alert=True)
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
        await callback.message.answer(
            tr("level_prompt", lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=tr("btn_cancel", lang),
                                     callback_data="cmp:stop"),
            ]]),
        )

    # ---- cancel exit for the level / custom-size prompt (UX-05) ----
    @router.callback_query(F.data == "cmp:stop")
    async def on_compress_stop(callback: CallbackQuery):
        if _throttled(callback):
            await callback.answer()
            return
        lang = await engine._lang(callback.from_user.id)
        percent_pending.pop(callback.from_user.id, None)
        pending_custom.pop(callback.from_user.id, None)
        await callback.answer(tr("pending_cancelled", lang))
        if callback.message is not None:
            try:
                await callback.message.delete()
            except TelegramAPIError:
                pass

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

    # ---- cancel button on the progress card (UX-01: cheap checks first,
    # then an instant ack, then the actual cancel) ----
    @router.callback_query(F.data.startswith("canc:"))
    async def on_cancel_btn(callback: CallbackQuery):
        if _throttled(callback):
            await callback.answer()
            return
        job_id = callback.data.split(":", 1)[1]
        row = await db.fetchrow("SELECT * FROM jobs WHERE id = $1", _as_uuid(job_id))
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
        await engine.cancel_job(row)

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
