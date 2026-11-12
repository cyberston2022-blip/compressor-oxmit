"""Video merge + merge+compress flow (spec 7 / 8).

Session lifecycle (all state in Postgres, survives restarts):
    /merge            -> opens a 'collecting' session (one per user, DB-enforced)
    <video>           -> probe + hash (engine.register_media) + staged copy,
                         seq assigned atomically by merge.add_item
    mrg:list          -> show ordered items
    mrg:done|/merge_done   -> >=2 items -> status 'merging' -> engine.merge_job
    mrg:cancel|/merge_cancel -> cancel + staged-file cleanup

The router's video handler is gated by an ASYNC FILTER on the DB: without an
active session the update falls through to the normal intake router, so the
merge feature never disturbs the standard compression flow.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from .. import merge as merge_mod
from .. import permissions as perms
from ..log import get_logger
from ..texts import tr
from .common import is_admin
from .nav import send_denial

log = get_logger("oxmit.mergeflow")

MAX_ITEMS = 50
_LAST_CB: dict[int, float] = {}


def _throttled(cb: CallbackQuery) -> bool:
    import time as _t
    now = _t.monotonic()
    uid = cb.from_user.id
    if now - _LAST_CB.get(uid, 0.0) < 0.6:
        return True
    if len(_LAST_CB) > 5000:
        _LAST_CB.clear()
    _LAST_CB[uid] = now
    return False


def build_router(engine, db, cfg, state) -> Router:
    router = Router(name="mergeflow")

    async def _active_session(tg_id: int) -> dict | None:
        return await merge_mod.get_active_session(db, tg_id)

    async def _has_collecting(message: Message) -> bool:
        if message.from_user is None:
            return False
        s = await _active_session(message.from_user.id)
        return bool(s) and s["status"] == "collecting"

    def _session_kb(lang: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tr("mrg_btn_list", lang), callback_data="mrg:list")],
            [InlineKeyboardButton(text=tr("mrg_btn_done", lang), callback_data="mrg:done"),
             InlineKeyboardButton(text=tr("btn_cancel_job", lang), callback_data="mrg:cancel")],
        ])

    def _session_text(sess: dict, lang: str) -> str:
        note = ""
        if sess["compress"]:
            note = "\n" + tr("mrg_compress_note", lang,
                             profile=sess["profile"] or "edu480",
                             target=(f" | هدف {sess['target_mb']}MB"
                                     if sess["target_mb"] else ""))
        return tr("mrg_session", lang, n=sess["item_count"]) + note

    # ------------------------------------------------------------------
    # commands
    # ------------------------------------------------------------------
    @router.message(F.text.startswith("/merge_cancel"))
    async def on_merge_cancel_cmd(message: Message):
        if message.from_user is None:
            return
        sess = await _active_session(message.from_user.id)
        if not sess:
            return
        await _do_cancel(message.from_user.id, sess, message.chat.id)

    @router.message(F.text.startswith("/merge_done"))
    async def on_merge_done_cmd(message: Message):
        if message.from_user is None:
            return
        sess = await _active_session(message.from_user.id)
        if not sess:
            return
        await _do_finish(message.from_user.id, sess, message.chat.id)

    @router.message(F.text.startswith("/merge_list"))
    async def on_merge_list_cmd(message: Message):
        if message.from_user is None:
            return
        sess = await _active_session(message.from_user.id)
        if not sess:
            return
        await message.answer(await _items_text(sess))

    @router.message(F.text.startswith("/merge"))
    async def on_merge_cmd(message: Message):
        if message.from_user is None:
            return
        uid = message.from_user.id
        if not await is_admin(db, cfg, uid):
            return
        raw = (message.text or "").strip().lower()
        compress = raw.endswith("compress") or "compress" in raw
        perm = "merge_compress.use" if compress else "merge.use"
        if not await perms.has_perm(engine, uid, perm):
            await message.answer(tr("perm_denied", "fa",
                                    perm=perms.PERM_LABELS_FA[perm]))
            return
        existing = await _active_session(uid)
        if existing:
            await message.answer(_session_text(existing, "fa"),
                                 reply_markup=_session_kb("fa"))
            return
        # profile policy: merge+compress runs the STANDARD compression flow;
        # default edu480, custom target via /merge compress <mb>.
        profile = "edu480"
        target_mb = None
        if compress:
            parts = raw.split()
            for p in parts[1:]:
                if p.isdigit():
                    target_mb = max(5, min(8192, int(p)))
                    break
        try:
            sess = await merge_mod.create_session(
                db, uid, message.chat.id, compress=compress,
                profile=profile, target_mb=target_mb)
        except Exception:  # noqa: BLE001 - unique violation = already active
            await message.answer(tr("mrg_already_active", "fa"))
            return
        await message.answer(
            tr("mrg_started", "fa",
               kind=tr("mrg_kind_compress", "fa") if compress
               else tr("mrg_kind_merge", "fa"))
            + "\n" + tr("mrg_rules", "fa", maxn=MAX_ITEMS),
            reply_markup=_session_kb("fa"))
        log.info("merge session opened", extra={
            "detail": f"session={sess['id'][:8]} user={uid} compress={compress}"})

    # ------------------------------------------------------------------
    # video capture during an active collecting session (filter-gated)
    # ------------------------------------------------------------------
    @router.message(F.video | F.document, _has_collecting)
    async def on_merge_video(message: Message):
        if message.from_user is None:
            return
        uid = message.from_user.id
        sess = await _active_session(uid)
        if not sess or sess["status"] != "collecting":
            return
        if sess["item_count"] >= MAX_ITEMS:
            await message.answer(tr("mrg_max_items", "fa", maxn=MAX_ITEMS))
            return
        doc = message.document
        video = message.video
        if doc is not None:
            file_id, size, name = doc.file_id, doc.file_size or 0, doc.file_name or "video.mp4"
        elif video is not None:
            file_id, size, name = video.file_id, video.file_size or 0, video.file_name or "video.mp4"
        else:
            return
        status = None
        try:
            status = await engine.bot.send_message(message.chat.id, "⏳ …")
        except TelegramAPIError:
            pass
        try:
            tg_file = await engine.bot.get_file(file_id)
        except TelegramAPIError as exc:
            await _edit(status, message, tr("mrg_download_failed", "fa"))
            return
        src = await engine.resolve_local_path(tg_file.file_path)
        if src is None:
            await _edit(status, message, tr("mrg_download_failed", "fa"))
            return
        try:
            media_id, _sha, probe, stable = await engine.register_media(
                src_path=src, size_bytes=size, filename=name,
                tg_file_id=file_id, tg_file_unique_id=None)
        except Exception:  # noqa: BLE001 - invalid media
            await _edit(status, message, tr("mrg_invalid_video", "fa"))
            return
        # Stage a stable copy: bot-api files can be evicted; the merge needs
        # every input alive until it runs (staged under the session dir with
        # the assigned sequence as the name).
        stage_dir = f"{cfg.media_incoming}/merge-{sess['id'][:8]}"
        try:
            seq = await merge_mod.add_item(
                db, sess["id"], media_id, "", size, probe.get("duration_s"))
        except merge_mod.MergeError:
            await _edit(status, message, tr("mrg_session_closed", "fa"))
            return
        from pathlib import Path
        staged = Path(stage_dir) / f"{seq:03d}-{media_mod.sanitize_filename(name, 50)}"
        staged.parent.mkdir(parents=True, exist_ok=True)
        try:
            await asyncio.to_thread(shutil.copyfile, stable, str(staged))
        except OSError:
            await merge_mod.set_status(db, sess["id"], "failed",
                                       "staging copy failed")
            await _edit(status, message, tr("mrg_stage_failed", "fa"))
            return
        await db.execute(
            "UPDATE merge_items SET staged_path = $2 WHERE session_id = $1 "
            "AND seq = $3",
            sess["id"], str(staged), seq,
        )
        await db.execute(
            "UPDATE merge_sessions SET updated_at = now() WHERE id = $1",
            sess["id"])
        # UX (spec §11.3/§11.4): the active-session banner + the REAL order
        # (from merge_items.seq) on every accepted upload.
        items = await merge_mod.list_items(db, sess["id"])
        order_lines = " → ".join(
            f"{it['seq']}. {(it['filename'] or '?')[:24]}" for it in items[:8])
        more = f" … (+{len(items) - 8})" if len(items) > 8 else ""
        text = "\n".join([
            tr("mrg_banner", lang),
            tr("mrg_added", lang, seq=seq, n=sess["item_count"] + 1,
               name=media_mod.sanitize_filename(name, 32)),
            tr("mrg_total_size", lang, n=len(items),
               size=media_mod.human_size(sum((it["size_bytes"] or 0) for it in items))),
            tr("mrg_order_title", lang),
            order_lines + more,
            tr("mrg_waiting_next", lang),
        ])
        if status:
            await engine.edit_status_sync(message.chat.id, status.message_id, text)
        else:
            await message.answer(text)

    # ------------------------------------------------------------------
    # buttons
    # ------------------------------------------------------------------
    @router.callback_query(F.data.startswith("mg:compress:"))
    async def on_mg_compress_this(cb: CallbackQuery):
        """Compress an EXISTING completed merge result (spec §12.5).

        Ownership + permission + file-availability are all re-checked here;
        the merged file then goes through the standard handle_submission
        pipeline (admission, dedup, cache-offer, queue, delivery)."""
        if _throttled(cb) or cb.message is None:
            return
        uid = cb.from_user.id
        sid = cb.data.split(":", 2)[2]
        sess = await merge_mod.get_session(db, sid)
        if not sess or sess["tg_id"] != uid or sess["status"] != "completed" \
                or not sess["result_path"]:
            await cb.answer(tr("mrg_compress_btn_denied", "fa"), show_alert=True)
            return
        if not await perms.has_perm(engine, uid, "merge_compress.use"):
            await cb.answer(tr("perm_denied", "fa",
                               perm=perms.PERM_LABELS_FA["merge_compress.use"]),
                            show_alert=True)
            await send_denial(engine, db, cb.message.chat.id, uid,
                              "merge_compress.use")
            return
        from pathlib import Path
        result = Path(sess["result_path"])
        if not result.is_file():
            await cb.answer(tr("mrg_compress_unavailable", "fa"), show_alert=True)
            return
        await cb.answer(tr("mrg_compress_started", "fa"))
        await engine.handle_submission(
            tg_id=uid, chat_id=cb.message.chat.id, source_msg_id=None,
            status_msg_id=None, size_bytes=result.stat().st_size,
            filename="merged.mp4", profile_key=sess["profile"] or "edu480",
            local_path=str(result), target_mb=sess["target_mb"],
        )

    @router.callback_query(F.data.startswith("mrg:"))
    async def on_merge_btn(cb: CallbackQuery):
        uid = cb.from_user.id
        if not cb.message:
            return
        sess = await _active_session(uid)
        action = cb.data.split(":", 1)[1]
        if not sess:
            await cb.answer(tr("mrg_no_session", "fa"), show_alert=True)
            return
        if action == "list":
            await cb.answer()
            await cb.message.answer(await _items_text(sess))
            return
        if action == "cancel":
            await _do_cancel(uid, sess, cb.message.chat.id)
            await cb.answer(tr("mrg_cancelled", "fa"))
            try:
                await cb.message.delete()
            except TelegramAPIError:
                pass
            return
        if action == "done":
            await cb.answer()
            await _do_finish(uid, sess, cb.message.chat.id)
            return
        await cb.answer()

    # ------------------------------------------------------------------
    # shared actions
    # ------------------------------------------------------------------
    async def _edit(status, message: Message, text: str) -> None:
        if status:
            await engine.edit_status_sync(message.chat.id, status.message_id, text)
        else:
            await message.answer(text)

    async def _items_text(sess: dict) -> str:
        items = await merge_mod.list_items(db, sess["id"])
        lines = [tr("mrg_items_title", "fa", n=len(items))]
        for it in items:
            lines.append(tr("mrg_item_line", "fa", seq=it["seq"],
                            name=(it["filename"] or "?")[:36],
                            dur=(f"{it['duration_s']:.0f}s" if it["duration_s"] else "?")))
        return "\n".join(lines[:MAX_ITEMS + 2])

    async def _do_cancel(uid: int, sess: dict, chat_id: int) -> None:
        if sess["status"] not in ("collecting",):
            await engine.bot.send_message(chat_id, tr("mrg_not_cancellable", "fa"))
            return
        await merge_mod.set_status(db, sess["id"], "cancelled", "by user")
        try:
            await merge_mod.cleanup_session_files(db, sess["id"])
        except Exception:  # noqa: BLE001 - cleanup is best-effort
            log.warning("merge cleanup failed", extra={"detail": sess["id"][:8]})
        await engine.bot.send_message(chat_id, tr("mrg_cancelled_msg", "fa"))

    async def _do_finish(uid: int, sess: dict, chat_id: int) -> None:
        if sess["status"] != "collecting":
            await engine.bot.send_message(chat_id, tr("mrg_already_running", "fa"))
            return
        if sess["item_count"] < 2:
            await engine.bot.send_message(chat_id, tr("mrg_need_two", "fa"))
            return
        perm = "merge_compress.use" if sess["compress"] else "merge.use"
        if not await perms.has_perm(engine, uid, perm):
            await engine.bot.send_message(
                chat_id, tr("perm_denied", "fa", perm=perms.PERM_LABELS_FA[perm]))
            return
        await merge_mod.set_status(db, sess["id"], "merging")
        await engine.bot.send_message(
            chat_id, tr("mrg_started_processing", "fa",
                        n=sess["item_count"],
                        kind=tr("mrg_kind_compress", "fa") if sess["compress"]
                        else tr("mrg_kind_merge", "fa")))
        engine.spawn(engine.merge_job(sess["id"]))

    async def sweep_pending() -> None:
        # expire abandoned collecting sessions (24h) + cleanup staged files
        try:
            stale = await merge_mod.fail_stale_sessions(db, stale_hours=24)
            if stale:
                log.info("stale merge sessions cancelled", extra={"detail": str(stale)})
        except Exception:  # noqa: BLE001 - sweep is best-effort
            pass

    router.sweep_pending = sweep_pending  # type: ignore[attr-defined]
    return router
