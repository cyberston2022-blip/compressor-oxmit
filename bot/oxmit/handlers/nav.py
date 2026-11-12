"""Unified role-aware navigation: /menu, /help, /myjobs, /branding.

The hub is a discovery + status layer over the existing media-first flow —
sending a video still enters compression directly, exactly as before
(spec §7/§16). Every menu row reflects REAL permissions via
`permissions.has_perm`; visibility is a courtesy, the backend stays the
boundary. All callbacks live in the NEW `menu:` / `den:` namespaces —
no existing namespace is touched.
"""
from __future__ import annotations

import time

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
from ..texts import tr
from .common import ensure_user

log = get_logger("oxmit.nav")

_HOME_ROW = [InlineKeyboardButton(text=tr("nav_btn_home", "fa"),
                                  callback_data="menu:home")]


async def send_denial(engine, db, chat_id: int, tg_id: int, perm: str) -> None:
    """Actionable permission denial (spec §25/E15): explain + request button.

    The request only NOTIFIES the Owner (rate-limited via audit_log); it
    never grants anything — `permissions.has_perm` remains the boundary.
    """
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tr("den_btn_request", "fa"),
                              callback_data=f"den:req:{perm}")],
        [InlineKeyboardButton(text=tr("nav_btn_home", "fa"),
                              callback_data="menu:home")],
    ])
    text = tr("den_text", "fa", perm=perms.PERM_LABELS_FA.get(perm, perm))
    try:
        await engine.bot.send_message(chat_id, text, reply_markup=kb)
    except TelegramAPIError as exc:
        log.warning("denial message failed", extra={"detail": str(exc)[:120]})


def build_router(engine, db, cfg, state) -> Router:
    router = Router(name="nav")

    # ------------------------------------------------------------------
    # role-aware menu builder (single source of truth for the hub)
    # ------------------------------------------------------------------
    async def build_role_menu(tg_id: int) -> tuple[str, InlineKeyboardMarkup]:
        owner = await engine.is_owner(tg_id)
        admin = owner or tg_id in await engine.admin_ids()
        row = await db.fetchrow("SELECT is_vip FROM users WHERE tg_id = $1", tg_id)
        vip = bool(row and row["is_vip"])

        pmap: dict[str, bool] | None = None
        if admin:
            pmap = await perms.effective_perms(engine, tg_id)

        lines = ["🧭 " + tr("nav_title", "fa"), "━━━━━━━━━━━━━━━"]
        if vip:
            lines.append(tr("nav_vip_badge", "fa"))
        lines.append(tr("nav_hint", "fa"))
        kb: list[list[InlineKeyboardButton]] = [
            [InlineKeyboardButton(text=tr("nav_btn_guide", "fa"),
                                  callback_data="menu:guide")],
            [InlineKeyboardButton(text=tr("nav_btn_jobs", "fa"),
                                  callback_data="menu:jobs")],
        ]
        if vip:
            kb.append([InlineKeyboardButton(text=tr("nav_btn_vip", "fa"),
                                            callback_data="menu:vip")])
        if pmap is not None:
            branding = any(pmap[p] for p in
                           ("thumbnail.use", "watermark.use", "caption.use"))
            if branding:
                kb.append([InlineKeyboardButton(
                    text=tr("nav_btn_branding", "fa"),
                    callback_data="menu:branding")])
            if pmap["merge.use"]:
                kb.append([InlineKeyboardButton(
                    text=tr("nav_btn_merge", "fa"), callback_data="menu:merge")])
            if pmap["merge_compress.use"]:
                kb.append([InlineKeyboardButton(
                    text=tr("nav_btn_mergecompress", "fa"),
                    callback_data="menu:mergecompress")])
            kb.append([InlineKeyboardButton(text=tr("nav_btn_ops", "fa"),
                                            callback_data="menu:ops")])
        if owner:
            kb.append([InlineKeyboardButton(text=tr("nav_btn_owner", "fa"),
                                            callback_data="menu:ownpanel")])
        kb.append([InlineKeyboardButton(text=tr("nav_btn_settings", "fa"),
                                        callback_data="menu:settings"),
                   InlineKeyboardButton(text=tr("nav_btn_help", "fa"),
                                        callback_data="menu:help")])
        return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=kb)

    async def _show_home(msg_or_cb, edit: bool) -> None:
        uid = _uid_of(msg_or_cb)
        if uid is None:
            return
        text, kb = await build_role_menu(uid)
        msg = msg_or_cb.message if hasattr(msg_or_cb, "message") else msg_or_cb
        try:
            if edit and msg is not None:
                await msg.edit_text(text, reply_markup=kb)
            elif msg is not None:
                await msg.answer(text, reply_markup=kb)
        except TelegramAPIError:
            pass

    def _uid_of(obj) -> int | None:
        if hasattr(obj, "from_user") and obj.from_user is not None:
            return obj.from_user.id
        return None

    # ------------------------------------------------------------------
    # /menu
    # ------------------------------------------------------------------
    @router.message(F.text.startswith("/menu"))
    async def on_menu(message: Message):
        if message.from_user is None:
            return
        await ensure_user(db, message.from_user)
        await _show_home(message, edit=False)

    @router.callback_query(F.data == "menu:home")
    async def on_menu_home(cb: CallbackQuery):
        if cb.from_user is None:
            return
        await cb.answer()
        await _show_home(cb, edit=True)

    # ------------------------------------------------------------------
    # guide + help (static, honest)
    # ------------------------------------------------------------------
    @router.callback_query(F.data == "menu:guide")
    async def on_menu_guide(cb: CallbackQuery):
        if cb.from_user is None:
            return
        await cb.answer()
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tr("btn_back", "fa"),
                                  callback_data="menu:home")]])
        await _edit(cb, tr("nav_guide", "fa"), kb)

    @router.message(F.text.startswith("/help"))
    async def on_help(message: Message):
        if message.from_user is None:
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tr("nav_btn_menu", "fa"),
                                  callback_data="menu:home")]])
        await message.answer(tr("nav_help", "fa"), reply_markup=kb)

    @router.callback_query(F.data == "menu:help")
    async def on_menu_help(cb: CallbackQuery):
        if cb.from_user is None:
            return
        await cb.answer()
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tr("nav_btn_menu", "fa"),
                                  callback_data="menu:home")]])
        await _edit(cb, tr("nav_help", "fa"), kb)

    # ------------------------------------------------------------------
    # my jobs (own rows only, parameterized, safe prefix ids)
    # ------------------------------------------------------------------
    _STATUS_VIEW = {
        "queued": ("🟡", "nav_st_queued"),
        "deferred": ("🕓", "nav_st_deferred"),
        "processing": ("⚙️", "nav_st_processing"),
        "completed": ("🟢", "nav_st_completed"),
        "failed": ("🔴", "nav_st_failed"),
        "cancelled": ("🚫", "nav_st_cancelled"),
    }

    async def _jobs_text(tg_id: int) -> str:
        rows = await db.fetch(
            """
            SELECT j.id, j.status, j.progress, j.profile, m.filename
            FROM jobs j
            LEFT JOIN media_assets m ON m.id = j.media_id
            WHERE j.requester_tg_id = $1
               OR EXISTS (SELECT 1 FROM job_requesters jr
                          WHERE jr.job_id = j.id AND jr.tg_id = $1)
            ORDER BY j.enqueued_at DESC
            LIMIT 5
            """,
            tg_id,
        )
        lines = [tr("nav_jobs_title", "fa"), "━━━━━━━━━━━━━━━"]
        if not rows:
            lines.append(tr("nav_jobs_empty", "fa"))
        for r in rows:
            icon, key = _STATUS_VIEW.get(r["status"], ("•", "nav_st_queued"))
            name = (r["filename"] or tr("nav_jobs_noname", "fa"))[:32]
            lines.append(f"{icon} {name}")
            lines.append(f"   {tr(key, 'fa')} | {r['profile']} | `{r['id'][:8]}`")
        return "\n".join(lines)

    async def _show_jobs(msg_or_cb, edit: bool) -> None:
        uid = _uid_of(msg_or_cb)
        if uid is None:
            return
        text = await _jobs_text(uid)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tr("nav_btn_refresh", "fa"),
                                  callback_data="menu:jobs"),
             InlineKeyboardButton(text=tr("nav_btn_home", "fa"),
                                  callback_data="menu:home")]])
        msg = msg_or_cb.message if hasattr(msg_or_cb, "message") else msg_or_cb
        try:
            if edit and msg is not None:
                await msg.edit_text(text, reply_markup=kb)
            elif msg is not None:
                await msg.answer(text, reply_markup=kb)
        except TelegramAPIError:
            pass

    @router.message(F.text.startswith("/myjobs"))
    async def on_myjobs(message: Message):
        if message.from_user is None:
            return
        await _show_jobs(message, edit=False)

    @router.callback_query(F.data == "menu:jobs")
    async def on_menu_jobs(cb: CallbackQuery):
        if cb.from_user is None:
            return
        await cb.answer()
        await _show_jobs(cb, edit=True)

    # ------------------------------------------------------------------
    # VIP benefits (real tier values, no invented usage data)
    # ------------------------------------------------------------------
    @router.callback_query(F.data == "menu:vip")
    async def on_menu_vip(cb: CallbackQuery):
        if cb.from_user is None:
            return
        await cb.answer()
        try:
            tiers = (await engine.tiers_config()).get("vip") or {}
        except Exception:  # noqa: BLE001 - display only
            tiers = {}
        text = tr("nav_vip_screen", "fa",
                  hours=round((tiers.get("max_duration_min") or 720) / 60),
                  quota=tiers.get("daily_quota_gb") or 20,
                  active=tiers.get("max_active") or 4,
                  hourly=tiers.get("max_per_hour") or 30,
                  prio=tiers.get("priority") or 60)
        kb = InlineKeyboardMarkup(inline_keyboard=[_HOME_ROW])
        await _edit(cb, text, kb)

    # ------------------------------------------------------------------
    # branding hub + unified-ish preview (honest approximations)
    # ------------------------------------------------------------------
    @router.message(F.text.startswith("/branding"))
    async def on_branding_cmd(message: Message):
        if message.from_user is None:
            return
        await _show_branding(message, edit=False)

    @router.callback_query(F.data == "menu:branding")
    async def on_menu_branding(cb: CallbackQuery):
        if cb.from_user is None:
            return
        await cb.answer()
        await _show_branding(cb, edit=True)

    async def _show_branding(msg_or_cb, edit: bool) -> None:
        uid = _uid_of(msg_or_cb)
        if uid is None:
            return
        pmap = await perms.effective_perms(engine, uid)
        kb_rows: list[list[InlineKeyboardButton]] = []
        if pmap["thumbnail.use"]:
            kb_rows.append([InlineKeyboardButton(text=tr("nav_b_thumb", "fa"),
                                                 callback_data="pr:thumb")])
        if pmap["watermark.use"]:
            kb_rows.append([InlineKeyboardButton(text=tr("nav_b_wm", "fa"),
                                                 callback_data="pr:wm")])
        if pmap["caption.use"]:
            kb_rows.append([InlineKeyboardButton(text=tr("nav_b_cap", "fa"),
                                                 callback_data="pr:cap")])
        if not kb_rows:
            await _deny_message(msg_or_cb, "thumbnail.use")
            return
        kb_rows.append([InlineKeyboardButton(text=tr("nav_b_preview", "fa"),
                                             callback_data="menu:bpreview")])
        kb_rows.append(_HOME_ROW)
        snap = await db.fetchrow(
            """
            SELECT thumbnail_path, watermark_enabled, caption, caption_mode
            FROM admin_settings WHERE tg_id = $1
            """,
            uid,
        )
        thumb_set = bool(snap and snap["thumbnail_path"]
                         and media_mod.Path(snap["thumbnail_path"]).is_file())
        wm_on = bool(snap and snap["watermark_enabled"])
        cap_set = bool(snap and snap["caption"])
        text = "\n".join([
            "🎨 " + tr("nav_branding_title", "fa"),
            "━━━━━━━━━━━━━━━",
            tr("nav_branding_thumb", "fa",
               state="✅" if thumb_set else "—"),
            tr("nav_branding_wm", "fa", state="✅ فعال" if wm_on else "— غیرفعال"),
            tr("nav_branding_cap", "fa",
               state="✅" if cap_set else "—",
               mode=tr("cap_mode_" + ((snap["caption_mode"] if snap else None)
                                      or "replace"), "fa")),
            "",
            tr("nav_branding_info", "fa"),
            tr("nav_branding_splitwarn", "fa"),
        ])
        msg = msg_or_cb.message if hasattr(msg_or_cb, "message") else msg_or_cb
        try:
            if edit and msg is not None:
                await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=kb_rows))
            elif msg is not None:
                await msg.answer(text, reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=kb_rows))
        except TelegramAPIError:
            pass

    @router.callback_query(F.data == "menu:bpreview")
    async def on_branding_preview(cb: CallbackQuery):
        if cb.from_user is None or cb.message is None:
            return
        uid = cb.from_user.id
        pmap = await perms.effective_perms(engine, uid)
        if not any(pmap[p] for p in ("thumbnail.use", "watermark.use", "caption.use")):
            await cb.answer(tr("perm_denied", "fa",
                               perm=perms.PERM_LABELS_FA["thumbnail.use"]),
                            show_alert=True)
            return
        await cb.answer(tr("nav_preview_rendering", "fa"))
        snap = await db.fetchrow(
            """
            SELECT thumbnail_path, watermark, watermark_enabled, caption
            FROM admin_settings WHERE tg_id = $1
            """,
            uid,
        )
        # 1) personal thumbnail (the real stored asset — honestly labeled)
        if snap and snap["thumbnail_path"]:
            try:
                from aiogram.types import FSInputFile
                from pathlib import Path as _P
                if _P(snap["thumbnail_path"]).is_file():
                    await engine.bot.send_photo(
                        cb.message.chat.id, FSInputFile(snap["thumbnail_path"]),
                        caption=tr("nav_preview_thumb", "fa"))
            except TelegramAPIError:
                pass
        # 2) watermark preview (existing renderer, white canvas - labeled)
        if snap and snap["watermark_enabled"] and snap["watermark"]:
            pr_router_personal = getattr(_personal_router_ref, "api_render_wm_preview",
                                         None)
            if pr_router_personal is not None:
                try:
                    await pr_router_personal(cb.message.chat.id, uid,
                                             caption=tr("nav_preview_wm", "fa"))
                except TelegramAPIError:
                    pass
        # 3) caption preview (text only - it is a Telegram-side caption)
        if snap and snap["caption"]:
            try:
                await engine.bot.send_message(
                    cb.message.chat.id,
                    tr("nav_preview_cap", "fa", caption=snap["caption"][:300]))
            except TelegramAPIError:
                pass

    # personal router bridge (set by bot.py after routers are built)
    _personal_router_ref = None

    def bind_personal_router(personal_router) -> None:
        nonlocal _personal_router_ref
        _personal_router_ref = personal_router

    router.bind_personal_router = bind_personal_router  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # menu shortcuts into existing flows
    # ------------------------------------------------------------------
    @router.callback_query(F.data.in_({"menu:merge", "menu:mergecompress",
                                       "menu:ops", "menu:ownpanel",
                                       "menu:settings"}))
    async def on_menu_shortcuts(cb: CallbackQuery):
        if cb.from_user is None:
            return
        uid = cb.from_user.id
        action = cb.data.split(":", 1)[1]
        if action in ("merge", "mergecompress"):
            perm = "merge.use" if action == "merge" else "merge_compress.use"
            if not await perms.has_perm(engine, uid, perm):
                await _deny_message(cb, perm)
                return
            cmd = "/merge" if action == "merge" else "/merge compress"
            await cb.answer()
            await _send_hint(cb, tr("nav_send_command", "fa", cmd=cmd))
            return
        if action == "ops":
            if uid not in await engine.admin_ids():
                await cb.answer(tr("admin_denied", "fa"), show_alert=True)
                return
            await cb.answer()
            await _send_hint(cb, tr("nav_send_command", "fa", cmd="/admin"))
            return
        if action == "ownpanel":
            if not await engine.is_owner(uid):
                await cb.answer(tr("admin_denied", "fa"), show_alert=True)
                return
            await cb.answer()
            await _send_hint(cb, tr("nav_send_command", "fa", cmd="/owner"))
            return
        # settings: open the real settings screen via its own router command
        await cb.answer()
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tr("nav_btn_home", "fa"),
                                  callback_data="menu:home")]])
        await _edit(cb, tr("nav_settings_hint", "fa"), kb)

    # ------------------------------------------------------------------
    # permission denial helper + request-to-owner workflow (P1)
    # ------------------------------------------------------------------
    async def _deny_message(msg_or_cb, perm: str) -> None:
        chat_id = _chat_id_of(msg_or_cb)
        uid = _uid_of(msg_or_cb)
        if chat_id is not None and uid is not None:
            await send_denial(engine, db, chat_id, uid, perm)

    def _chat_id_of(obj) -> int | None:
        msg = getattr(obj, "message", None) or obj
        chat = getattr(msg, "chat", None)
        return chat.id if chat else None

    async def _send_hint(cb: CallbackQuery, text: str) -> None:
        if cb.message is not None:
            try:
                await cb.message.answer(text)
            except TelegramAPIError:
                pass

    async def _edit(cb: CallbackQuery, text: str,
                    kb: InlineKeyboardMarkup) -> None:
        try:
            if cb.message is not None and cb.message.text is not None:
                await cb.message.edit_text(text, reply_markup=kb)
            elif cb.message is not None:
                await cb.message.answer(text, reply_markup=kb)
        except TelegramAPIError:
            pass

    _DEN_RATE_LIMIT_PER_DAY = 3

    @router.callback_query(F.data.startswith("den:req:"))
    async def on_den_request(cb: CallbackQuery):
        if cb.from_user is None:
            return
        uid = cb.from_user.id
        perm = cb.data.split(":", 2)[2] if cb.data.count(":") >= 2 else ""
        if perm not in perms.PERMS:
            await cb.answer()
            return
        if await perms.has_perm(engine, uid, perm):
            await cb.answer(tr("den_already_granted", "fa"), show_alert=True)
            return
        if uid not in await engine.admin_ids():
            await cb.answer(tr("admin_denied", "fa"), show_alert=True)
            return
        # DB-backed anti-spam: count this admin's requests in the last 24h
        recent = await db.fetchval(
            """
            SELECT count(*) FROM audit_log
            WHERE actor = $1 AND action = 'admin.perm_request'
              AND ts > now() - interval '24 hours'
            """,
            f"admin:{uid}",
        ) or 0
        if int(recent) >= _DEN_RATE_LIMIT_PER_DAY:
            await cb.answer(tr("den_rate_limited", "fa"), show_alert=True)
            return
        owner_id = cfg.owner_telegram_id
        if not owner_id:
            admins = await engine.admin_ids()
            owner_id = admins[0] if admins else None
        if owner_id is None:
            await cb.answer(tr("den_no_owner", "fa"), show_alert=True)
            return
        name_row = await db.fetchrow(
            "SELECT first_name, username FROM users WHERE tg_id = $1", uid)
        name = (name_row["first_name"] if name_row else None) or str(uid)
        uname = f"@{name_row['username']}" if name_row and name_row["username"] else ""
        try:
            await engine.bot.send_message(
                owner_id,
                tr("den_owner_msg", "fa", name=name, uid=uid, uname=uname,
                   perm=perms.PERM_LABELS_FA.get(perm, perm)),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text=tr("own_btn_perm_open", "fa"),
                                         callback_data=f"ownadm:{uid}")]]),
            )
        except TelegramAPIError as exc:
            log.warning("perm request delivery failed",
                        extra={"detail": str(exc)[:120]})
            await cb.answer(tr("den_failed", "fa"), show_alert=True)
            return
        await audit_mod.log_action(db, f"admin:{uid}", "admin",
                                   "admin.perm_request", uid, perm,
                                   source="telegram")
        await cb.answer(tr("den_sent", "fa"), show_alert=True)

    async def sweep_pending() -> None:
        return None

    router.sweep_pending = sweep_pending  # type: ignore[attr-defined]
    return router
