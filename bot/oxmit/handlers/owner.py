"""Owner panel — complete Telegram management surface for the bot owner.

Sections (spec 3.2, owner-managed without touching code or the DB):
  👥 Administrators  — list, add (id or @username), demote (with confirm)
  ⭐ VIP users       — list, add, remove
  📊 Overview        — users / admins / VIP / jobs-24h / queue / disk / uptime
  🧾 Recent events   — permission + role changes from audit_log

Every callback re-verifies the Owner (backend is the security boundary),
every mutation is audited, permission changes invalidate the cache so
revocation lands immediately. Explicit grant/revoke buttons are idempotent;
true toggles (VIP/ban) are throttled.
"""
from __future__ import annotations

import re
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
from .. import permissions as perms
from ..log import get_logger
from ..texts import tr

log = get_logger("oxmit.owner")

_DIV = "━━━━━━━━━━━━━━━"
_LAST_CB: dict[int, float] = {}


def _throttled(cb: CallbackQuery) -> bool:
    now = time.monotonic()
    uid = cb.from_user.id
    if now - _LAST_CB.get(uid, 0.0) < 0.6:
        return True
    if len(_LAST_CB) > 5000:
        _LAST_CB.clear()
    _LAST_CB[uid] = now
    return False


def parse_target(raw: str) -> tuple[str | None, str | None]:
    """Owner input -> (numeric_id, username) — exactly one is set."""
    text = (raw or "").strip().translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    if text.startswith("@"):
        uname = text[1:].strip()
        return (None, uname) if re.fullmatch(r"[A-Za-z0-9_]{4,32}", uname) else (None, None)
    digits = re.sub(r"[^0-9]", "", text)
    if digits and len(digits) >= 3:
        return digits, None
    return None, None


def build_router(engine, db, cfg, state) -> Router:
    router = Router(name="owner")

    # pending inputs: uid -> (kind, created)   kind: add_admin | add_vip
    pending: dict[int, tuple[str, float]] = {}

    # ------------------------------------------------------------------
    # data helpers
    # ------------------------------------------------------------------
    async def _user_row(tg_id: int):
        return await db.fetchrow(
            "SELECT tg_id, first_name, username, is_vip, is_blocked, is_admin "
            "FROM users WHERE tg_id = $1", tg_id)

    async def _display_name(tg_id: int) -> str:
        row = await _user_row(tg_id)
        if row and row["first_name"]:
            return f"{row['first_name']} ({tg_id})"
        return str(tg_id)

    async def _counts() -> dict:
        users = await db.fetchval("SELECT count(*) FROM users") or 0
        admins = await db.fetchval(
            "SELECT count(*) FROM users WHERE is_admin") or 0
        vips = await db.fetchval(
            "SELECT count(*) FROM users WHERE is_vip") or 0
        blocked = await db.fetchval(
            "SELECT count(*) FROM users WHERE is_blocked") or 0
        jobs24 = await db.fetchval(
            "SELECT count(*) FROM jobs WHERE enqueued_at > now() - interval '24 hours'") or 0
        queued = await db.fetchval(
            "SELECT count(*) FROM jobs WHERE status IN ('queued','processing','deferred')") or 0
        return {"users": users, "admins": admins, "vips": vips,
                "blocked": blocked, "jobs24": jobs24, "queued": queued}

    async def _find_user(ref: str):
        tg_id, uname = parse_target(ref)
        if tg_id:
            return await _user_row(int(tg_id))
        if uname:
            return await db.fetchrow(
                "SELECT tg_id, first_name, username, is_vip, is_blocked, is_admin "
                "FROM users WHERE lower(username) = $1", uname.lower())
        return None

    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------
    def _main_kb(admins: list[int], vips: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tr("own_btn_admins", "fa", n=len(admins)),
                                  callback_data="own:list")],
            [InlineKeyboardButton(text=tr("own_btn_vip", "fa", n=vips),
                                  callback_data="own:vip")],
            [InlineKeyboardButton(text=tr("own_btn_addadmin", "fa"),
                                  callback_data="own:addadmin")],
            [InlineKeyboardButton(text=tr("own_btn_matrix", "fa"),
                                  callback_data="own:matrix")],
            [InlineKeyboardButton(text=tr("own_btn_audit", "fa"),
                                  callback_data="own:audit")],
            [InlineKeyboardButton(text=tr("own_btn_refresh", "fa"),
                                  callback_data="own:home")],
        ])

    async def _main_text() -> str:
        c = await _counts()
        return "\n".join([
            "👑 " + tr("own_title", "fa"),
            _DIV,
            tr("own_stats", "fa", **c),
            "",
            tr("own_hint", "fa"),
        ])

    async def _send_home(message_or_cb, edit: bool = False) -> None:
        text = await _main_text()
        admins = await engine.admin_ids()
        vips = await db.fetchval("SELECT count(*) FROM users WHERE is_vip") or 0
        kb = _main_kb(admins, vips)
        msg = message_or_cb.message if hasattr(message_or_cb, "message") else message_or_cb
        try:
            if edit and msg is not None:
                await msg.edit_text(text, reply_markup=kb)
            elif msg is not None:
                await msg.answer(text, reply_markup=kb)
        except TelegramAPIError:
            pass

    # ------------------------------------------------------------------
    # /owner — main menu
    # ------------------------------------------------------------------
    @router.message(F.text.startswith("/owner"))
    async def on_owner(message: Message):
        if message.from_user is None:
            return
        if not await engine.is_owner(message.from_user.id):
            return  # silent: do not reveal the command
        pending.pop(message.from_user.id, None)
        await _send_home(message, edit=False)

    @router.callback_query(F.data == "own:home")
    async def on_owner_home(cb: CallbackQuery):
        if not await _owner_ok(cb):
            return
        await _send_home(cb, edit=True)
        await cb.answer()

    async def _owner_ok(cb: CallbackQuery) -> bool:
        if await engine.is_owner(cb.from_user.id):
            return True
        await cb.answer(tr("admin_denied", "fa"), show_alert=True)
        return False

    # ------------------------------------------------------------------
    # read-only permission matrix (spec §15: report view, no mutations)
    # ------------------------------------------------------------------
    @router.callback_query(F.data == "own:matrix")
    async def on_owner_matrix(cb: CallbackQuery):
        if not await _owner_ok(cb) or cb.message is None:
            return
        admins = await engine.admin_ids()
        lines = [tr("own_matrix_title", "fa"), _DIV]
        short = {"compression.use": tr("own_mx_comp", "fa"),
                 "thumbnail.use": tr("own_mx_thumb", "fa"),
                 "watermark.use": tr("own_mx_wm", "fa"),
                 "caption.use": tr("own_mx_cap", "fa"),
                 "merge.use": tr("own_mx_merge", "fa"),
                 "merge_compress.use": tr("own_mx_mergc", "fa")}
        for aid in admins:
            pmap = await perms.effective_perms(engine, aid)
            row = await _user_row(aid)
            name = (row["first_name"] if row else None) or str(aid)
            lines.append(f"⚙️ {name} ({aid})")
            lines.append("  " + " | ".join(
                f"{short[p]}: {'✅' if pmap[p] else '❌'}" for p in perms.PERMS))
        lines.append(_DIV)
        lines.append(tr("own_matrix_hint", "fa"))
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tr("btn_back", "fa"),
                                  callback_data="own:home")]])
        await _edit_or_answer(cb, "\n".join(lines), kb)
        await cb.answer()

    # ------------------------------------------------------------------
    # administrators list
    # ------------------------------------------------------------------
    @router.callback_query(F.data == "own:list")
    async def on_owner_list(cb: CallbackQuery):
        if not await _owner_ok(cb) or cb.message is None:
            return
        admins = await engine.admin_ids()
        rows = []
        for aid in admins:
            row = await _user_row(aid)
            name = (row["first_name"] if row else None) or str(aid)
            marks = ("👑" if await engine.is_owner(aid) else "⚙️")
            if row and row["is_vip"]:
                marks += "⭐"
            if row and row["is_blocked"]:
                marks += "🚫"
            rows.append([InlineKeyboardButton(
                text=f"{marks} {name} ({aid})",
                callback_data=f"ownadm:{aid}")])
        rows.append([InlineKeyboardButton(text=tr("own_btn_addadmin", "fa"),
                                          callback_data="own:addadmin")])
        rows.append([InlineKeyboardButton(text=tr("btn_back", "fa"),
                                          callback_data="own:home")])
        text = "\n".join([
            tr("own_admins_title", "fa", n=len(admins)),
            _DIV,
            tr("own_admins_hint", "fa"),
        ])
        await _edit_or_answer(cb, text, InlineKeyboardMarkup(inline_keyboard=rows))
        await cb.answer()

    async def _edit_or_answer(cb: CallbackQuery, text: str,
                              kb: InlineKeyboardMarkup) -> None:
        """Edit the panel message when it is a text message; otherwise send
        a new one (covers media-message edge cases without crashing)."""
        msg = cb.message
        try:
            if msg is not None and msg.text is not None:
                await msg.edit_text(text, reply_markup=kb)
            elif msg is not None:
                await msg.answer(text, reply_markup=kb)
        except TelegramAPIError:
            pass

    # ------------------------------------------------------------------
    # per-admin management screen
    # ------------------------------------------------------------------
    @router.callback_query(F.data.startswith("ownadm:"))
    async def on_owner_admin(cb: CallbackQuery):
        if not await _owner_ok(cb) or cb.message is None:
            return
        try:
            target = int(cb.data.split(":", 1)[1])
        except (ValueError, TypeError):
            await cb.answer()
            return
        await _render_admin(cb, target)

    async def _render_admin(cb: CallbackQuery, target: int) -> None:
        pmap = await perms.effective_perms(engine, target)
        row = await _user_row(target)
        name = (row["first_name"] if row else None) or str(target)
        uname = f"@{row['username']}" if row and row["username"] else "—"
        settings_row = await db.fetchrow(
            """
            SELECT thumbnail_path, caption, caption_mode, watermark_enabled
            FROM admin_settings WHERE tg_id = $1
            """,
            target,
        )
        conf = []
        if settings_row:
            conf.append(("🖼", "✅" if settings_row["thumbnail_path"] else "—"))
            conf.append(("💧", "✅" if settings_row["watermark_enabled"] else "—"))
            conf.append(("📝", "✅" if settings_row["caption"]
                         else "—"))
        conf_line = "  ".join(f"{i} {s}" for i, s in conf) or "—"
        target_is_owner = await engine.is_owner(target)

        lines = [
            f"{name} · {uname} · `{target}`",
            tr("own_admin_flags", "fa",
               vip="⭐" if row and row["is_vip"] else "—",
               ban="🚫" if row and row["is_blocked"] else "✅"),
            tr("own_admin_conf", "fa", conf=conf_line),
            _DIV,
        ]
        kb_rows: list[list[InlineKeyboardButton]] = []
        for i in range(0, len(perms.PERMS), 2):
            pair = perms.PERMS[i:i + 2]
            r = []
            for perm in pair:
                ok = pmap[perm]
                r.append(InlineKeyboardButton(
                    text=("✅ " if ok else "❌ ") + perms.PERM_LABELS_FA[perm],
                    callback_data=f"ownperm:{target}:{perm}:{'0' if ok else '1'}"))
            kb_rows.append(r)
        if not target_is_owner:
            kb_rows.append([
                InlineKeyboardButton(
                    text=tr("own_btn_vip_toggle", "fa",
                            state="لغو" if row and row["is_vip"] else "اعطا"),
                    callback_data=f"ownvip:{target}"),
                InlineKeyboardButton(
                    text=tr("own_btn_ban_toggle", "fa",
                            state="رفع" if row and row["is_blocked"] else "بن"),
                    callback_data=f"ownban:{target}"),
            ])
            kb_rows.append([InlineKeyboardButton(
                text=tr("own_btn_demote", "fa"),
                callback_data=f"owndemote:{target}")])
        kb_rows.append([InlineKeyboardButton(text=tr("btn_back", "fa"),
                                             callback_data="own:list")])
        if target_is_owner:
            lines.append("")
            lines.append(tr("owner_is_target", "fa"))
        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        await _edit_or_answer(cb, "\n".join(lines), kb)
        await cb.answer()

    # ------------------------------------------------------------------
    # permission grant/revoke (explicit target value — idempotent)
    # ------------------------------------------------------------------
    @router.callback_query(F.data.startswith("ownperm:"))
    async def on_owner_perm(cb: CallbackQuery):
        if not await _owner_ok(cb) or cb.message is None:
            return
        try:
            _, target_s, perm, want_s = cb.data.split(":")
            target, want = int(target_s), want_s == "1"
        except (ValueError, TypeError):
            await cb.answer()
            return
        if perm not in perms.PERMS:
            await cb.answer()
            return
        if await engine.is_owner(target):
            await cb.answer(tr("owner_is_target", "fa"), show_alert=True)
            return
        await db.execute(
            """
            INSERT INTO admin_permissions(tg_id, perm, granted, granted_by, updated_at)
            VALUES ($1, $2, $3, $4, now())
            ON CONFLICT (tg_id, perm) DO UPDATE
            SET granted = $3, granted_by = $4, updated_at = now()
            """,
            target, perm, want, cb.from_user.id,
        )
        perms.invalidate_cache(target)
        await audit_mod.log_action(
            db, f"owner:{cb.from_user.id}", "owner",
            "admin.perm_grant" if want else "admin.perm_revoke",
            target, perm, source="telegram")
        log.info("owner permission change", extra={
            "detail": f"target={target} perm={perm} granted={want}"})
        await cb.answer(tr("owner_perm_done", "fa",
                           perm=perms.PERM_LABELS_FA[perm],
                           state="✅" if want else "❌"))
        await _render_admin(cb, target)

    # ------------------------------------------------------------------
    # VIP / ban quick toggles (true toggles — throttled)
    # ------------------------------------------------------------------
    @router.callback_query(F.data.startswith("ownvip:"))
    async def on_owner_vip_toggle(cb: CallbackQuery):
        if _throttled(cb) or not await _owner_ok(cb) or cb.message is None:
            return
        target = int(cb.data.split(":", 1)[1])
        new = await db.fetchval(
            "UPDATE users SET is_vip = NOT is_vip WHERE tg_id = $1 RETURNING is_vip",
            target)
        if new is None:
            await cb.answer(tr("own_user_missing", "fa"), show_alert=True)
            return
        await audit_mod.log_action(db, f"owner:{cb.from_user.id}", "owner",
                                   "user.vip", target, f"new={bool(new)}",
                                   source="telegram")
        await cb.answer(tr("own_vip_done", "fa",
                           state="⭐" if new else "—"))
        await _render_admin(cb, target)

    @router.callback_query(F.data.startswith("ownban:"))
    async def on_owner_ban_toggle(cb: CallbackQuery):
        if _throttled(cb) or not await _owner_ok(cb) or cb.message is None:
            return
        target = int(cb.data.split(":", 1)[1])
        if await engine.is_owner(target):
            await cb.answer(tr("owner_is_target", "fa"), show_alert=True)
            return
        new = await db.fetchval(
            "UPDATE users SET is_blocked = NOT is_blocked WHERE tg_id = $1 "
            "RETURNING is_blocked", target)
        if new is None:
            await cb.answer(tr("own_user_missing", "fa"), show_alert=True)
            return
        await audit_mod.log_action(db, f"owner:{cb.from_user.id}", "owner",
                                   "user.ban", target, f"new={bool(new)}",
                                   source="telegram")
        await cb.answer(tr("own_ban_done", "fa",
                           state="🚫" if new else "✅"))
        await _render_admin(cb, target)

    # ------------------------------------------------------------------
    # demote (with confirmation screen)
    # ------------------------------------------------------------------
    @router.callback_query(F.data.startswith("owndemote:"))
    async def on_owner_demote_ask(cb: CallbackQuery):
        if not await _owner_ok(cb) or cb.message is None:
            return
        target = int(cb.data.split(":", 1)[1])
        name = await _display_name(target)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tr("own_btn_demote_yes", "fa"),
                                  callback_data=f"owndemoteok:{target}")],
            [InlineKeyboardButton(text=tr("btn_back", "fa"),
                                  callback_data=f"ownadm:{target}")],
        ])
        await _edit_or_answer(cb, tr("own_demote_confirm", "fa", name=name), kb)
        await cb.answer()

    @router.callback_query(F.data.startswith("owndemoteok:"))
    async def on_owner_demote(cb: CallbackQuery):
        if _throttled(cb) or not await _owner_ok(cb) or cb.message is None:
            return
        target = int(cb.data.split(":", 1)[1])
        ok, why = await engine.demote_admin(
            f"owner:{cb.from_user.id}", target)
        if not ok:
            await cb.answer(tr("own_demote_failed", "fa", why=why),
                            show_alert=True)
            return
        await cb.answer(tr("own_demote_done", "fa"))
        await on_owner_list(cb)

    # ------------------------------------------------------------------
    # add administrator / add VIP (pending text input)
    # ------------------------------------------------------------------
    @router.callback_query(F.data == "own:addadmin")
    async def on_owner_addadmin(cb: CallbackQuery):
        if not await _owner_ok(cb) or cb.message is None:
            return
        pending[cb.from_user.id] = ("add_admin", time.time())
        await cb.answer(tr("own_add_admin_prompt", "fa"), show_alert=True)

    @router.callback_query(F.data == "own:addvip")
    async def on_owner_addvip(cb: CallbackQuery):
        if not await _owner_ok(cb) or cb.message is None:
            return
        pending[cb.from_user.id] = ("add_vip", time.time())
        await cb.answer(tr("own_add_vip_prompt", "fa"), show_alert=True)

    def _has_owner_pending(kind: str):
        def _check(message: Message) -> bool:
            if message.from_user is None:
                return False
            entry = pending.get(message.from_user.id)
            return bool(entry) and entry[0] == kind and time.time() - entry[1] < 600
        return _check

    @router.message(F.text, _has_owner_pending("add_admin"))
    async def on_owner_add_admin_text(message: Message):
        if message.from_user is None:
            return
        pending.pop(message.from_user.id, None)
        user = await _find_user(message.text or "")
        if user is None:
            await message.answer(tr("own_user_not_found", "fa",
                                    ref=(message.text or "")[:32]))
            return
        ok, why = await engine.promote_admin(
            f"owner:{message.from_user.id}", user["tg_id"])
        if not ok:
            await message.answer(tr("own_promote_failed", "fa", why=why))
            return
        await audit_mod.log_action(db, f"owner:{message.from_user.id}", "owner",
                                   "admin.promote", user["tg_id"], None,
                                   source="telegram")
        await message.answer(tr("own_admin_added", "fa",
                                name=user["first_name"] or str(user["tg_id"])))

    @router.message(F.text, _has_owner_pending("add_vip"))
    async def on_owner_add_vip_text(message: Message):
        if message.from_user is None:
            return
        pending.pop(message.from_user.id, None)
        user = await _find_user(message.text or "")
        if user is None:
            await message.answer(tr("own_user_not_found", "fa",
                                    ref=(message.text or "")[:32]))
            return
        new = await db.fetchval(
            "UPDATE users SET is_vip = TRUE WHERE tg_id = $1 RETURNING is_vip",
            user["tg_id"])
        if new is None:
            await message.answer(tr("own_user_not_found", "fa",
                                    ref=(message.text or "")[:32]))
            return
        await audit_mod.log_action(db, f"owner:{message.from_user.id}", "owner",
                                   "user.vip", user["tg_id"], "new=True",
                                   source="telegram")
        await message.answer(tr("own_vip_added", "fa",
                                name=user["first_name"] or str(user["tg_id"])))

    # ------------------------------------------------------------------
    # VIP list
    # ------------------------------------------------------------------
    @router.callback_query(F.data == "own:vip")
    async def on_owner_vip_list(cb: CallbackQuery):
        if not await _owner_ok(cb) or cb.message is None:
            return
        vips = await db.fetch(
            """
            SELECT tg_id, first_name, username FROM users
            WHERE is_vip ORDER BY last_seen_at DESC LIMIT 30
            """
        )
        rows = [[InlineKeyboardButton(
            text=f"⭐ {(v['first_name'] or v['tg_id'])}",
            callback_data=f"ownadm:{v['tg_id']}")] for v in vips]
        rows.append([InlineKeyboardButton(text=tr("own_btn_addvip", "fa"),
                                          callback_data="own:addvip")])
        rows.append([InlineKeyboardButton(text=tr("btn_back", "fa"),
                                          callback_data="own:home")])
        text = "\n".join([
            tr("own_vip_title", "fa", n=len(vips)),
            _DIV,
            tr("own_vip_hint", "fa"),
        ])
        await _edit_or_answer(cb, text, InlineKeyboardMarkup(inline_keyboard=rows))
        await cb.answer()

    # ------------------------------------------------------------------
    # recent relevant audit events
    # ------------------------------------------------------------------
    @router.callback_query(F.data == "own:audit")
    async def on_owner_audit(cb: CallbackQuery):
        if not await _owner_ok(cb) or cb.message is None:
            return
        rows = await db.fetch(
            """
            SELECT ts, actor, action, target, details FROM audit_log
            WHERE action LIKE 'admin.perm_%'
               OR action IN ('admin.promote','admin.demote','user.vip','user.ban',
                             'admin.personal_thumb','admin.personal_thumb_del',
                             'admin.wm_toggle','admin.wm_reset','admin.cap_set',
                             'admin.cap_del','admin.wm_image','admin.wm_font')
            ORDER BY ts DESC LIMIT 12
            """
        )
        lines = [tr("own_audit_title", "fa"), _DIV]
        if not rows:
            lines.append(tr("own_audit_empty", "fa"))
        for r in rows:
            ts = r["ts"].strftime("%m-%d %H:%M") if r["ts"] else "?"
            lines.append(f"• {ts} | {r['action']} | {r['target']} | {r['actor']}")
        rows_kb = [[InlineKeyboardButton(text=tr("btn_back", "fa"),
                                         callback_data="own:home")]]
        await _edit_or_answer(cb, "\n".join(lines),
                              InlineKeyboardMarkup(inline_keyboard=rows_kb))
        await cb.answer()

    async def sweep_pending() -> None:
        now = time.time()
        for uid in [u for u, (_k, t) in pending.items() if now - t > 600]:
            pending.pop(uid, None)

    router.sweep_pending = sweep_pending  # type: ignore[attr-defined]
    return router
