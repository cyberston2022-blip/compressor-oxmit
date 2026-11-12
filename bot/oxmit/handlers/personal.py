"""Personal admin settings: thumbnail, watermark (Argon-derived options),
caption. Every entry point re-checks the Owner-managed permission backend -
hidden buttons are never the security boundary (spec 3.3).

Storage: admin_settings (one row per admin; migration 012). Watermark assets
on disk: media/watermarks/{tg_id}.png + media/watermarks/fonts/{tg_id}.ttf.
Thumbnail assets: media/thumbs/personal/{tg_id}.jpg (320x320 JPEG <200KB).

Interaction style follows the existing bot (pending dicts + inline buttons +
TelegramAPIError guards), not aiogram FSM, to stay consistent.

Entries: /thumb /wm /cap commands AND `pr:thumb|wm|cap` callbacks from the
navigation Branding Center. Watermark options are grouped progressively
(basic / appearance / position / timing) without removing any option.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import time
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from .. import audit as audit_mod
from .. import media as media_mod
from .. import permissions as perms
from ..log import get_logger
from ..texts import normalize_digits, tr
from .common import is_admin
from .nav import send_denial

log = get_logger("oxmit.personal")

_POSITIONS = ("top-left", "top-right", "bottom-left", "bottom-right")
_POSITIONS_FA = {
    "top-left": "بالا-چپ", "top-right": "بالا-راست",
    "bottom-left": "پایین-چپ", "bottom-right": "پایین-راست",
}

_THUMB_Q_LADDER = (4, 7, 11, 16, 23, 31)   # until < 200 KB (Argon behavior)
_THUMB_MAX_BYTES = 200 * 1024


def build_router(engine, db, cfg, state) -> Router:
    router = Router(name="personal")

    # pending inputs: uid -> (kind, created)
    # kinds: thumb_photo | wm_text | wm_size | wm_opacity | wm_border |
    #        wm_scale | wm_margin:<side> | wm_timing:range|interval |
    #        wm_img | wm_font | cap_text
    pending: dict[int, tuple[str, float]] = {}

    async def _require(cb: CallbackQuery, perm: str) -> bool:
        uid = cb.from_user.id
        if not await is_admin(db, cfg, uid):
            await cb.answer(tr("admin_denied", "fa"), show_alert=True)
            return False
        if not await perms.has_perm(engine, uid, perm):
            await cb.answer(tr("perm_denied", "fa",
                               perm=perms.PERM_LABELS_FA[perm]),
                            show_alert=True)
            if cb.message is not None:
                await send_denial(engine, db, cb.message.chat.id, uid, perm)
            return False
        return True

    async def _load_wm(tg_id: int) -> dict:
        row = await db.fetchrow(
            "SELECT watermark FROM admin_settings WHERE tg_id = $1", tg_id)
        raw = None
        if row and row["watermark"]:
            try:
                raw = json.loads(row["watermark"])
            except (ValueError, TypeError):
                raw = None
        from ..watermark import normalize_wm
        return normalize_wm(raw)

    async def _save_wm(tg_id: int, wm: dict) -> None:
        await db.execute(
            """
            INSERT INTO admin_settings(tg_id, watermark, updated_at)
            VALUES ($1, $2::jsonb, now())
            ON CONFLICT (tg_id) DO UPDATE
            SET watermark = $2::jsonb, updated_at = now()
            """,
            tg_id, json.dumps(wm),
        )

    async def _enabled(tg_id: int) -> bool:
        v = await db.fetchval(
            "SELECT watermark_enabled FROM admin_settings WHERE tg_id = $1", tg_id)
        return bool(v)

    async def _set_enabled(tg_id: int, value: bool) -> None:
        await db.execute(
            """
            INSERT INTO admin_settings(tg_id, watermark_enabled, updated_at)
            VALUES ($1, $2, now())
            ON CONFLICT (tg_id) DO UPDATE
            SET watermark_enabled = $2, updated_at = now()
            """,
            tg_id, value,
        )

    # ------------------------------------------------------------------
    # thumbnail (command + pr:thumb entry share this starter)
    # ------------------------------------------------------------------
    async def _start_thumb(uid: int, chat_id: int) -> None:
        pending[uid] = ("thumb_photo", time.time())
        row = await db.fetchrow(
            "SELECT thumbnail_path FROM admin_settings WHERE tg_id = $1", uid)
        cur = row["thumbnail_path"] if row else None
        status = tr("thumb_set", "fa") if (cur and Path(cur).is_file()) \
            else tr("thumb_none", "fa")
        await engine.bot.send_message(
            chat_id,
            tr("thumb_prompt", "fa", current=status),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=tr("btn_thumb_del", "fa"),
                                     callback_data="pthumb:del"),
                InlineKeyboardButton(text=tr("btn_cancel", "fa"),
                                     callback_data="pthumb:no"),
            ]]),
        )

    @router.message(F.text.startswith("/thumb"))
    async def on_thumb_cmd(message: Message):
        if message.from_user is None:
            return
        uid = message.from_user.id
        if not await is_admin(db, cfg, uid):
            return
        if not await perms.has_perm(engine, uid, "thumbnail.use"):
            await message.answer(tr("perm_denied", "fa",
                                    perm=perms.PERM_LABELS_FA["thumbnail.use"]))
            await send_denial(engine, db, message.chat.id, uid, "thumbnail.use")
            return
        await _start_thumb(uid, message.chat.id)

    @router.callback_query(F.data == "pr:thumb")
    async def on_pr_thumb(cb: CallbackQuery):
        if not await _require(cb, "thumbnail.use"):
            return
        await cb.answer()
        await _start_thumb(cb.from_user.id, cb.message.chat.id)

    async def _set_personal_thumb(uid: int, path: str) -> None:
        await db.execute(
            """
            INSERT INTO admin_settings(tg_id, thumbnail_path, updated_at)
            VALUES ($1, $2, now())
            ON CONFLICT (tg_id) DO UPDATE
            SET thumbnail_path = $2, updated_at = now()
            """,
            uid, path,
        )

    @router.message(F.photo, lambda m: pending.get(m.from_user.id, ("",))[0] == "thumb_photo")
    async def on_thumb_photo(message: Message):
        if message.from_user is None:
            return
        pending.pop(message.from_user.id, None)
        uid = message.from_user.id
        try:
            tg_file = await engine.bot.get_file(message.photo[-1].file_id)
        except TelegramAPIError:
            await message.answer(tr("thumb_invalid", "fa"))
            return
        src = await engine.resolve_local_path(tg_file.file_path)
        if src is None:
            await message.answer(tr("thumb_invalid", "fa"))
            return
        out_dir = Path(cfg.media_thumbs) / "personal"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{uid}.jpg"

        def _normalize() -> bool:
            for q in _THUMB_Q_LADDER:
                cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(src),
                       "-frames:v", "1",
                       "-vf", "scale=320:320:force_original_aspect_ratio=decrease",
                       "-q:v", str(q), str(out)]
                proc = subprocess.run(cmd, capture_output=True, timeout=60)
                if proc.returncode == 0 and out.is_file() \
                        and out.stat().st_size < _THUMB_MAX_BYTES:
                    return True
            out.unlink(missing_ok=True)
            return False

        ok = await asyncio.to_thread(_normalize)
        if not ok:
            await message.answer(tr("thumb_invalid", "fa"))
            return
        await _set_personal_thumb(uid, str(out))
        await audit_mod.log_action(db, f"admin:{uid}", "admin", "admin.personal_thumb",
                                   uid, str(out), source="telegram")
        await message.answer(tr("thumb_saved", "fa"))

    @router.callback_query(F.data == "pthumb:del")
    async def on_thumb_del(cb: CallbackQuery):
        if not await _require(cb, "thumbnail.use"):
            return
        uid = cb.from_user.id
        pending.pop(uid, None)
        await db.execute(
            """
            INSERT INTO admin_settings(tg_id, thumbnail_path, updated_at)
            VALUES ($1, NULL, now())
            ON CONFLICT (tg_id) DO UPDATE
            SET thumbnail_path = NULL, updated_at = now()
            """,
            uid,
        )
        await audit_mod.log_action(db, f"admin:{uid}", "admin",
                                   "admin.personal_thumb_del", uid, None,
                                   source="telegram")
        await cb.answer(tr("thumb_deleted", "fa"), show_alert=True)

    @router.callback_query(F.data == "pthumb:no")
    async def on_thumb_cancel(cb: CallbackQuery):
        pending.pop(cb.from_user.id, None)
        await cb.answer(tr("pending_cancelled", "fa"))

    # ------------------------------------------------------------------
    # watermark — grouped navigation (no option removed)
    # ------------------------------------------------------------------
    def _wm_summary(wm: dict, enabled: bool) -> str:
        return tr("wm_summary", "fa",
                  state=("✅" if enabled else "❌"),
                  typ=tr("wm_type_text", "fa") if wm["type"] == "text"
                  else tr("wm_type_image", "fa"),
                  pos=_POSITIONS_FA[wm["position"]],
                  text=wm["text"][:40], size=wm["font_size"],
                  op=int(wm["opacity"] * 100), bop=int(wm["border_opacity"] * 100),
                  scale=int(wm["image_scale"] * 100),
                  timing=tr("wm_timing_" + wm["timing_mode"], "fa"))

    def _wm_main_kb() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tr("btn_wm_g_basic", "fa"),
                                  callback_data="wm:group:basic"),
             InlineKeyboardButton(text=tr("btn_wm_g_look", "fa"),
                                  callback_data="wm:group:look")],
            [InlineKeyboardButton(text=tr("btn_wm_g_pos", "fa"),
                                  callback_data="wm:group:pos"),
             InlineKeyboardButton(text=tr("btn_wm_g_timing", "fa"),
                                  callback_data="wm:group:timing")],
            [InlineKeyboardButton(text=tr("btn_wm_preview", "fa"),
                                  callback_data="wm:preview")],
            [InlineKeyboardButton(text=tr("btn_wm_toggle", "fa"),
                                  callback_data="wm:toggle"),
             InlineKeyboardButton(text=tr("btn_wm_reset", "fa"),
                                  callback_data="wm:reset")],
            [InlineKeyboardButton(text=tr("nav_btn_branding", "fa"),
                                  callback_data="menu:branding")],
        ])

    def _wm_group_kb(group: str) -> InlineKeyboardMarkup:
        if group == "basic":
            rows = [
                [InlineKeyboardButton(text=tr("btn_wm_type", "fa"),
                                      callback_data="wm:type"),
                 InlineKeyboardButton(text=tr("btn_wm_pos", "fa"),
                                      callback_data="wm:pos")],
                [InlineKeyboardButton(text=tr("btn_wm_preview", "fa"),
                                      callback_data="wm:preview")],
            ]
        elif group == "look":
            rows = [
                [InlineKeyboardButton(text=tr("btn_wm_text", "fa"),
                                      callback_data="wm:text"),
                 InlineKeyboardButton(text=tr("btn_wm_size", "fa"),
                                      callback_data="wm:size")],
                [InlineKeyboardButton(text=tr("btn_wm_opacity", "fa"),
                                      callback_data="wm:opacity"),
                 InlineKeyboardButton(text=tr("btn_wm_border", "fa"),
                                      callback_data="wm:border")],
                [InlineKeyboardButton(text=tr("btn_wm_font", "fa"),
                                      callback_data="wm:font")],
            ]
        elif group == "pos":
            rows = [
                [InlineKeyboardButton(text=tr("btn_wm_margins", "fa"),
                                      callback_data="wm:margins")],
            ]
        else:  # timing
            rows = [
                [InlineKeyboardButton(text=tr("btn_wm_timing", "fa"),
                                      callback_data="wm:timing")],
            ]
        rows.append([InlineKeyboardButton(text=tr("btn_back", "fa"),
                                          callback_data="wm:menu")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def _start_wm(uid: int, chat_id: int) -> None:
        wm = await _load_wm(uid)
        enabled = await _enabled(uid)
        await engine.bot.send_message(
            chat_id,
            tr("wm_title", "fa") + "\n\n" + _wm_summary(wm, enabled) + "\n\n"
            + tr("wm_hint", "fa"),
            reply_markup=_wm_main_kb(),
        )

    @router.message(F.text.startswith("/wm"))
    async def on_wm_cmd(message: Message):
        if message.from_user is None:
            return
        uid = message.from_user.id
        if not await is_admin(db, cfg, uid):
            return
        if not await perms.has_perm(engine, uid, "watermark.use"):
            await message.answer(tr("perm_denied", "fa",
                                    perm=perms.PERM_LABELS_FA["watermark.use"]))
            await send_denial(engine, db, message.chat.id, uid, "watermark.use")
            return
        await _start_wm(uid, message.chat.id)

    @router.callback_query(F.data == "pr:wm")
    async def on_pr_wm(cb: CallbackQuery):
        if not await _require(cb, "watermark.use"):
            return
        await cb.answer()
        if cb.message is not None:
            await _start_wm(cb.from_user.id, cb.message.chat.id)

    async def _refresh_wm_main(cb: CallbackQuery) -> None:
        if cb.message is None:
            return
        wm = await _load_wm(cb.from_user.id)
        enabled = await _enabled(cb.from_user.id)
        try:
            await cb.message.edit_text(
                tr("wm_title", "fa") + "\n\n" + _wm_summary(wm, enabled) + "\n\n"
                + tr("wm_hint", "fa"),
                reply_markup=_wm_main_kb())
        except TelegramAPIError:
            pass

    @router.callback_query(F.data.startswith("wm:group:"))
    async def on_wm_group(cb: CallbackQuery):
        if not cb.message or not await _require(cb, "watermark.use"):
            return
        group = cb.data.split(":", 2)[2]
        label = tr("wm_group_" + group, "fa")
        try:
            await cb.message.edit_text(
                tr("wm_group_title", "fa", group=label),
                reply_markup=_wm_group_kb(group))
        except TelegramAPIError:
            pass
        await cb.answer()

    @router.callback_query(F.data.startswith("wm:"))
    async def on_wm_button(cb: CallbackQuery):
        uid = cb.from_user.id
        if not cb.message or not await _require(cb, "watermark.use"):
            return
        action = cb.data.split(":", 1)[1]
        if action == "menu":
            await cb.answer()
            await _refresh_wm_main(cb)
            return
        wm = await _load_wm(uid)

        if action == "type":
            wm["type"] = "image" if wm["type"] == "text" else "text"
            await _save_wm(uid, wm)
            await cb.answer(tr("wm_type_now", "fa",
                               typ=tr("wm_type_" + wm["type"], "fa")))
        elif action == "pos":
            rows = [[InlineKeyboardButton(
                text=_POSITIONS_FA[p] + (" ✅" if wm["position"] == p else ""),
                callback_data=f"wmpos:{p}")] for p in _POSITIONS]
            rows.append([InlineKeyboardButton(text=tr("btn_back", "fa"),
                                              callback_data="wm:group:basic")])
            await cb.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
            await cb.answer()
            return
        elif action in ("text", "size", "opacity", "border", "img", "font"):
            kind = {"text": "wm_text", "size": "wm_size", "opacity": "wm_opacity",
                    "border": "wm_border", "img": "wm_img", "font": "wm_font"}[action]
            pending[uid] = (kind, time.time())
            await cb.answer(tr("wm_send_" + action, "fa"), show_alert=True)
            return
        elif action in ("margins", "timing"):
            await cb.answer()
            sub = _wm_margin_kb() if action == "margins" else _wm_timing_kb()
            try:
                await cb.message.edit_reply_markup(reply_markup=sub)
            except TelegramAPIError:
                pass
            return
        elif action == "preview":
            await cb.answer(tr("wm_preview_rendering", "fa"))
            await _render_preview(cb, uid, wm)
            return
        elif action == "toggle":
            enabled = not await _enabled(uid)
            await _set_enabled(uid, enabled)
            await audit_mod.log_action(db, f"admin:{uid}", "admin",
                                       "admin.wm_toggle", uid, f"enabled={enabled}",
                                       source="telegram")
            await cb.answer(tr("wm_toggled", "fa", state="✅" if enabled else "❌"))
        elif action == "reset":
            from ..watermark import normalize_wm
            await _save_wm(uid, normalize_wm(None))
            await audit_mod.log_action(db, f"admin:{uid}", "admin",
                                       "admin.wm_reset", uid, None,
                                       source="telegram")
            await cb.answer(tr("wm_reset", "fa"))
        else:
            await cb.answer()
            return
        await _refresh_wm_main(cb)

    def _wm_margin_kb() -> InlineKeyboardMarkup:
        rows = [[InlineKeyboardButton(text=tr("btn_wm_m_" + s, "fa"),
                                      callback_data=f"wmm:{s}")]
                for s in ("top", "bottom", "left", "right")]
        rows.append([InlineKeyboardButton(text=tr("btn_back", "fa"),
                                          callback_data="wm:group:pos")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _wm_timing_kb() -> InlineKeyboardMarkup:
        rows = [[InlineKeyboardButton(text=tr("wm_timing_always", "fa"),
                                      callback_data="wmt:always")],
                [InlineKeyboardButton(text=tr("wm_timing_range", "fa"),
                                      callback_data="wmt:range")],
                [InlineKeyboardButton(text=tr("wm_timing_interval", "fa"),
                                      callback_data="wmt:interval")],
                [InlineKeyboardButton(text=tr("btn_back", "fa"),
                                      callback_data="wm:group:timing")]]
        return InlineKeyboardMarkup(inline_keyboard=rows)

    @router.callback_query(F.data.startswith("wmpos:"))
    async def on_wm_pos(cb: CallbackQuery):
        if not cb.message or not await _require(cb, "watermark.use"):
            return
        wm = await _load_wm(cb.from_user.id)
        wm["position"] = cb.data.split(":", 1)[1]
        await _save_wm(cb.from_user.id, wm)
        await cb.answer(tr("wm_saved", "fa"))
        rows = [[InlineKeyboardButton(
            text=_POSITIONS_FA[p] + (" ✅" if wm["position"] == p else ""),
            callback_data=f"wmpos:{p}")] for p in _POSITIONS]
        rows.append([InlineKeyboardButton(text=tr("btn_back", "fa"),
                                          callback_data="wm:group:basic")])
        await cb.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    @router.callback_query(F.data.startswith("wmm:"))
    async def on_wm_margin(cb: CallbackQuery):
        if not cb.message or not await _require(cb, "watermark.use"):
            return
        side = cb.data.split(":", 1)[1]
        pending[cb.from_user.id] = (f"wm_margin:{side}", time.time())
        await cb.answer(tr("wm_send_margin", "fa",
                           side=tr("btn_wm_m_" + side, "fa")), show_alert=True)

    @router.callback_query(F.data.startswith("wmt:"))
    async def on_wm_timing(cb: CallbackQuery):
        if not cb.message or not await _require(cb, "watermark.use"):
            return
        mode = cb.data.split(":", 1)[1]
        if mode == "always":
            wm = await _load_wm(cb.from_user.id)
            wm["timing_mode"] = "always"
            await _save_wm(cb.from_user.id, wm)
            await cb.answer(tr("wm_saved", "fa"))
            try:
                await cb.message.edit_reply_markup(reply_markup=_wm_group_kb("timing"))
            except TelegramAPIError:
                pass
            return
        pending[cb.from_user.id] = (f"wm_timing:{mode}", time.time())
        key = "wm_send_range" if mode == "range" else "wm_send_interval"
        await cb.answer(tr(key, "fa"), show_alert=True)

    async def _render_wm_preview(chat_id: int, uid: int,
                                 caption: str | None = None) -> None:
        """Watermark preview on a white canvas (existing behavior, honestly
        labeled as an approximation). Exposed for the branding hub."""
        wm = await _load_wm(uid)
        img, font = engine._wm_asset_paths(uid)
        from .. import watermark as watermark_mod
        vf = watermark_mod.build_video_filter(wm, image_path=img, font_path=font)
        if vf is None:
            await engine.bot.send_message(chat_id, tr("wm_preview_noimg", "fa"))
            return
        out = Path(cfg.media_tmp) / f"wm-preview-{uid}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error",
               "-f", "lavfi", "-i", "color=c=white:s=1280x720:d=0.1",
               "-frames:v", "1"]
        if watermark_mod.uses_complex_filter(vf):
            cmd += ["-filter_complex", vf, "-map", "[0:v]"]
        else:
            cmd += ["-vf", vf]
        cmd += [str(out)]

        def _run():
            return subprocess.run(cmd, capture_output=True, timeout=60)

        try:
            proc = await asyncio.to_thread(_run)
        except subprocess.TimeoutExpired:
            proc = None
        from aiogram.types import FSInputFile
        if proc is not None and proc.returncode == 0 and out.is_file():
            try:
                await engine.bot.send_photo(chat_id, FSInputFile(str(out)),
                                            caption=caption)
            except TelegramAPIError:
                pass
            finally:
                out.unlink(missing_ok=True)
        else:
            await engine.bot.send_message(chat_id, tr("wm_preview_failed", "fa"))

    async def _render_preview(cb: CallbackQuery, uid: int, wm: dict) -> None:
        if cb.message is None:
            return
        await _render_wm_preview(cb.message.chat.id, uid)

    # exposed for the navigation branding preview (bound in bot.py)
    async def api_render_wm_preview(chat_id: int, uid: int,
                                    caption: str | None = None) -> None:
        await _render_wm_preview(chat_id, uid, caption)

    router.api_render_wm_preview = api_render_wm_preview  # type: ignore[attr-defined]

    # text/number/photo/doc input handler for the wm + cap pending states
    def _has_pending(kind_prefix: str):
        def _check(message: Message) -> bool:
            if message.from_user is None:
                return False
            entry = pending.get(message.from_user.id)
            return bool(entry) and entry[0].startswith(kind_prefix) \
                and time.time() - entry[1] < 600
        return _check

    @router.message(F.photo, _has_pending("wm_img"))
    async def on_wm_img(message: Message):
        if message.from_user is None:
            return
        pending.pop(message.from_user.id, None)
        uid = message.from_user.id
        try:
            tg_file = await engine.bot.get_file(message.photo[-1].file_id)
        except TelegramAPIError:
            await message.answer(tr("wm_upload_failed", "fa"))
            return
        src = await engine.resolve_local_path(tg_file.file_path)
        if src is None:
            await message.answer(tr("wm_upload_failed", "fa"))
            return
        wm_dir = Path(cfg.media_watermarks)
        wm_dir.mkdir(parents=True, exist_ok=True)
        dst = wm_dir / f"{uid}.png"

        def _convert() -> bool:
            cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(src),
                   "-frames:v", "1", str(dst)]
            proc = subprocess.run(cmd, capture_output=True, timeout=60)
            return proc.returncode == 0 and dst.is_file() \
                and dst.stat().st_size <= 5 * 1024 * 1024

        ok = await asyncio.to_thread(_convert)
        if not ok:
            dst.unlink(missing_ok=True)
            await message.answer(tr("wm_upload_failed", "fa"))
            return
        wm = await _load_wm(uid)
        wm["type"] = "image"
        await _save_wm(uid, wm)
        await audit_mod.log_action(db, f"admin:{uid}", "admin", "admin.wm_image",
                                   uid, str(dst), source="telegram")
        await message.answer(tr("wm_img_saved", "fa"))

    @router.message(F.document, _has_pending("wm_font"))
    async def on_wm_font(message: Message):
        if message.from_user is None:
            return
        pending.pop(message.from_user.id, None)
        uid = message.from_user.id
        doc = message.document
        name = (doc.file_name or "").lower()
        if not name.endswith((".ttf", ".otf")) or (doc.file_size or 0) > 5 * 1024 * 1024:
            await message.answer(tr("wm_font_invalid", "fa"))
            return
        try:
            tg_file = await engine.bot.get_file(doc.file_id)
        except TelegramAPIError:
            await message.answer(tr("wm_upload_failed", "fa"))
            return
        src = await engine.resolve_local_path(tg_file.file_path)
        if src is None:
            await message.answer(tr("wm_upload_failed", "fa"))
            return
        font_dir = Path(cfg.media_watermarks) / "fonts"
        font_dir.mkdir(parents=True, exist_ok=True)
        dst = font_dir / f"{uid}.ttf"

        def _copy() -> bool:
            import shutil
            try:
                shutil.copyfile(str(src), str(dst))
                return dst.is_file() and dst.stat().st_size <= 5 * 1024 * 1024
            except OSError:
                return False

        ok = await asyncio.to_thread(_copy)
        if not ok:
            await message.answer(tr("wm_upload_failed", "fa"))
            return
        wm = await _load_wm(uid)
        wm["type"] = "text"
        await _save_wm(uid, wm)
        await audit_mod.log_action(db, f"admin:{uid}", "admin", "admin.wm_font",
                                   uid, str(dst), source="telegram")
        await message.answer(tr("wm_font_saved", "fa"))

    @router.message(F.text, _has_pending("wm_"))
    async def on_wm_text(message: Message):
        if message.from_user is None:
            return
        kind = pending.pop(message.from_user.id)[0]
        uid = message.from_user.id
        raw = normalize_digits((message.text or "").strip())
        wm = await _load_wm(uid)
        try:
            if kind == "wm_text":
                if not raw:
                    raise ValueError
                wm["text"] = raw
            elif kind in ("wm_size", "wm_opacity", "wm_border", "wm_scale"):
                v = float(raw.replace("%", ""))
                if kind == "wm_size":
                    wm["font_size"] = min(100, max(10, int(v)))
                elif kind == "wm_opacity":
                    wm["opacity"] = min(1.0, max(0.1, v / 100))
                elif kind == "wm_scale":
                    wm["image_scale"] = min(1.0, max(0.1, v / 100))
                else:
                    wm["border_opacity"] = min(1.0, max(0.0, v / 100))
            elif kind.startswith("wm_margin:"):
                side = kind.split(":", 1)[1]
                wm[f"margin_{side}"] = min(500, max(0, int(float(raw))))
            elif kind == "wm_timing:range":
                parts = raw.replace("-", " ").split()
                if len(parts) != 2:
                    raise ValueError
                s, e = int(float(parts[0])), int(float(parts[1]))
                if e <= s:
                    raise ValueError
                wm["timing_mode"] = "range"
                wm["start_time"], wm["end_time"] = s, e
            elif kind == "wm_timing:interval":
                parts = raw.replace("-", " ").split()
                if len(parts) != 2:
                    raise ValueError
                dur, per = int(float(parts[0])), int(float(parts[1]))
                if dur >= per:
                    raise ValueError
                wm["timing_mode"] = "interval"
                wm["interval_duration"], wm["interval_period"] = dur, per
            else:
                return
        except (ValueError, OverflowError):
            await message.answer(tr("wm_bad_value", "fa"))
            return
        await _save_wm(uid, wm)
        await audit_mod.log_action(db, f"admin:{uid}", "admin", "admin.wm_edit",
                                   uid, kind, source="telegram")
        await message.answer(tr("wm_saved_msg", "fa"))

    # ------------------------------------------------------------------
    # caption (command + pr:cap entry)
    # ------------------------------------------------------------------
    async def _start_cap(uid: int, chat_id: int) -> None:
        pending[uid] = ("cap_text", time.time())
        row = await db.fetchrow(
            "SELECT caption, caption_mode FROM admin_settings WHERE tg_id = $1", uid)
        cur = (row["caption"] if row else None) or tr("cap_none", "fa")
        mode = (row["caption_mode"] if row else None) or "replace"
        await engine.bot.send_message(
            chat_id,
            tr("cap_prompt", "fa", current=cur[:200],
               mode=tr("cap_mode_" + mode, "fa")),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=tr("btn_cap_mode", "fa"),
                                      callback_data="cap:mode")],
                [InlineKeyboardButton(text=tr("btn_cap_del", "fa"),
                                      callback_data="cap:del"),
                 InlineKeyboardButton(text=tr("btn_cancel", "fa"),
                                      callback_data="cap:no")],
            ]),
        )

    @router.message(F.text.startswith("/cap"))
    async def on_cap_cmd(message: Message):
        if message.from_user is None:
            return
        uid = message.from_user.id
        if not await is_admin(db, cfg, uid):
            return
        if not await perms.has_perm(engine, uid, "caption.use"):
            await message.answer(tr("perm_denied", "fa",
                                    perm=perms.PERM_LABELS_FA["caption.use"]))
            await send_denial(engine, db, message.chat.id, uid, "caption.use")
            return
        await _start_cap(uid, message.chat.id)

    @router.callback_query(F.data == "pr:cap")
    async def on_pr_cap(cb: CallbackQuery):
        if not await _require(cb, "caption.use"):
            return
        await cb.answer()
        if cb.message is not None:
            await _start_cap(cb.from_user.id, cb.message.chat.id)

    @router.message(F.text, _has_pending("cap_text"))
    async def on_cap_text(message: Message):
        if message.from_user is None:
            return
        pending.pop(message.from_user.id, None)
        uid = message.from_user.id
        cap = (message.text or "").strip()[:1000]
        if not cap:
            await message.answer(tr("cap_bad", "fa"))
            return
        row = await db.fetchrow(
            "SELECT caption_mode FROM admin_settings WHERE tg_id = $1", uid)
        mode = (row["caption_mode"] if row else None) or "replace"
        await db.execute(
            """
            INSERT INTO admin_settings(tg_id, caption, caption_mode, updated_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT (tg_id) DO UPDATE
            SET caption = $2, caption_mode = $3, updated_at = now()
            """,
            uid, cap, mode,
        )
        await audit_mod.log_action(db, f"admin:{uid}", "admin", "admin.cap_set",
                                   uid, None, source="telegram")
        await message.answer(tr("cap_saved", "fa"))

    @router.callback_query(F.data.startswith("cap:"))
    async def on_cap_cb(cb: CallbackQuery):
        uid = cb.from_user.id
        if not cb.message or not await _require(cb, "caption.use"):
            return
        action = cb.data.split(":", 1)[1]
        if action == "no":
            pending.pop(uid, None)
            await cb.answer(tr("pending_cancelled", "fa"))
            return
        if action == "del":
            pending.pop(uid, None)
            await db.execute(
                """
                INSERT INTO admin_settings(tg_id, caption, updated_at)
                VALUES ($1, NULL, now())
                ON CONFLICT (tg_id) DO UPDATE
                SET caption = NULL, updated_at = now()
                """,
                uid,
            )
            await audit_mod.log_action(db, f"admin:{uid}", "admin", "admin.cap_del",
                                       uid, None, source="telegram")
            await cb.answer(tr("cap_deleted", "fa"), show_alert=True)
            return
        if action == "mode":
            row = await db.fetchrow(
                "SELECT caption_mode FROM admin_settings WHERE tg_id = $1", uid)
            mode = (row["caption_mode"] if row else None) or "replace"
            new = "append" if mode == "replace" else "replace"
            await db.execute(
                """
                INSERT INTO admin_settings(tg_id, caption_mode, updated_at)
                VALUES ($1, $2, now())
                ON CONFLICT (tg_id) DO UPDATE
                SET caption_mode = $2, updated_at = now()
                """,
                uid, new,
            )
            await cb.answer(tr("cap_mode_now", "fa",
                               mode=tr("cap_mode_" + new, "fa")))

    # housekeeping: expire stale pending inputs
    async def sweep_pending() -> None:
        now = time.time()
        for uid in [u for u, (_k, t) in pending.items() if now - t > 600]:
            pending.pop(uid, None)

    router.sweep_pending = sweep_pending  # type: ignore[attr-defined]
    return router
