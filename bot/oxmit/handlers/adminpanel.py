"""Button-driven administrator panel: everything is tappable - no command
syntax to type. Tier limits and per-user caps are edited with stepper
buttons (saved live), users are browsed and managed from cards, broadcast
has a preview + confirm step, and admins can write free-form messages to
any user. Live monitor and diagnostics included."""

from __future__ import annotations

import asyncio
import copy
import time
from datetime import datetime, timezone
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
from .. import forcesub
from .. import media as media_mod
from ..log import get_logger
from ..media import human_size
from ..texts import tr
from .common import is_admin

log = get_logger("oxmit.adminpanel")

# key -> (label, unit, step, min, max)
_LIMIT_META = {
    "max_source_gb": ("📦 سقف حجم ورودی", "GB", 1, 1, 20),
    "max_duration_min": ("⏱ حداکثر مدت", "دقیقه", 30, 30, 1440),
    "daily_quota_gb": ("📅 سهمیهٔ روزانه", "GB", 1, 1, 200),
    "max_active": ("🔄 کار همزمان", "", 1, 1, 10),
    "max_per_hour": ("⚡ سقف ساعتی", "", 5, 5, 120),
}
_ULIM_META = {
    "max_source_gb": ("📦 سقف حجم", "GB", 1, 1, 200),
    "max_duration_min": ("⏱ حداکثر مدت", "دقیقه", 30, 30, 2880),
    "daily_quota_gb": ("📅 سهمیهٔ روزانه", "GB", 1, 1, 200),
}
_LIMIT_SET_SQL = {
    "max_source_gb": "UPDATE users SET max_source_gb = $2 WHERE tg_id = $1",
    "max_duration_min": "UPDATE users SET max_duration_min = $2 WHERE tg_id = $1",
    "daily_quota_gb": "UPDATE users SET daily_quota_gb = $2 WHERE tg_id = $1",
}


def build_router(engine, db, cfg, state) -> Router:
    router = Router(name="adminpanel")
    pending_mode: dict[int, tuple[str, float]] = {}   # admin id -> (mode, ts)
    pending_target: dict[int, int] = {}               # admin id -> target user id
    live_tasks: dict[int, asyncio.Task] = {}          # admin id -> monitor task
    bcast_text: dict[int, str] = {}                   # admin id -> preview text

    # ------------------------------------------------------------------
    # live monitor (unchanged behaviour)
    # ------------------------------------------------------------------
    def _fmt_elapsed(seconds: float) -> str:
        seconds = max(0, int(seconds))
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    async def _monitor_loop(chat_id: int, admin_id: int, message_id: int) -> None:
        """Live task view: edit one message every 5s while jobs are active."""
        idle = 0
        last_text: str | None = None
        try:
            for _ in range(60):  # safety cap: 60 * 5s = 5 minutes
                if live_tasks.get(admin_id) is None:
                    return
                rows = await db.fetch(
                    """
                    SELECT j.id, j.progress, j.profile, j.source_size,
                           j.enqueued_at, j.started_at,
                           u.first_name, u.is_vip
                    FROM jobs j JOIN users u ON u.tg_id = j.requester_tg_id
                    WHERE j.status IN ('queued','processing')
                    ORDER BY j.enqueued_at
                    LIMIT 10
                    """
                )
                if not rows:
                    idle += 1
                    if idle >= 3:
                        live_tasks.pop(admin_id, None)
                        try:
                            await engine.bot.edit_message_text(
                                chat_id=chat_id, message_id=message_id,
                                text="✅ " + tr("admin_monitor_idle", "fa"))
                        except Exception:  # noqa: BLE001
                            pass
                        return
                else:
                    idle = 0
                lines = ["📡 " + tr("admin_monitor_title", "fa")]
                now = datetime.now(timezone.utc)
                for r in rows:
                    started = r["started_at"] or r["enqueued_at"]
                    if started is not None and started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                    elapsed = _fmt_elapsed((now - started).total_seconds()) if started else "-"
                    filled = int((r["progress"] or 0) / 10)
                    bar = "█" * filled + "░" * (10 - filled)
                    badge = " ⭐" if r["is_vip"] else ""
                    name = (r["first_name"] or "?")[:14]
                    lines.append(
                        f"{badge} {name} | {r['profile']} | [{bar}] "
                        f"{r['progress'] or 0}٪ | ⏱ {elapsed}"
                    )
                text = "\n".join(lines)
                if text == last_text:
                    await asyncio.sleep(5)
                    continue
                last_text = text
                try:
                    await engine.bot.edit_message_text(
                        chat_id=chat_id, message_id=message_id,
                        text=text,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(
                                text="⏹ " + tr("admin_monitor_stop", "fa"),
                                callback_data="mon:stop"),
                        ]]),
                    )
                except Exception:  # noqa: BLE001
                    pass
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass
        finally:
            live_tasks.pop(admin_id, None)

    # ------------------------------------------------------------------
    # shared render helpers
    # ------------------------------------------------------------------
    def _cancel_kb() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=tr("btn_cancel", "fa"), callback_data="pcx"),
        ]])

    def _user_card(row) -> str:
        tier = "⭐ VIP" if row["is_vip"] else "🏠 عادی"
        return (
            f"👤 {row['first_name'] or ''} (@{row['username'] or '-'})\n"
            f"آیدی: {row['tg_id']} | طبقه: {tier}\n"
            f"بن: {'🚫 فعال' if row['is_blocked'] else '✅ ندارد'}\n"
            f"درخواست‌ها: {row['total_requests']}\n"
            f"سقف اختصاصی: حجم {row['max_source_gb'] or '-'}GB | "
            f"مدت {row['max_duration_min'] or '-'}min | "
            f"روزی {row['daily_quota_gb'] or '-'}GB\n"
            f"(«-» یعنی طبقهٔ او اعمال شود)"
        )

    def _user_card_kb(row) -> InlineKeyboardMarkup:
        uid = row["tg_id"]
        vip_t = "⭐ VIP: روشن ✅" if row["is_vip"] else "⭐ VIP: خاموش"
        ban_t = "🚫 بن: فعال — رفع کن" if row["is_blocked"] else "🚫 بن کن"
        adm_t = "👑 حذف ادمین" if row["is_admin"] else "👑 ادمین کن"
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=vip_t, callback_data=f"uvip:{uid}"),
             InlineKeyboardButton(text=ban_t, callback_data=f"uban:{uid}")],
            [InlineKeyboardButton(text=adm_t, callback_data=f"uadm:{uid}")],
            [InlineKeyboardButton(text="🎚 سقف اختصاصی", callback_data=f"ulm:{uid}:menu")],
            [InlineKeyboardButton(text="✉️ ارسال پیام به کاربر", callback_data=f"umsg:{uid}")],
            [InlineKeyboardButton(text=tr("btn_back", "fa"), callback_data="uws:0")],
        ])

    def _tier_picker_kb() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 عادی", callback_data="lmt:normal:menu"),
             InlineKeyboardButton(text="⭐ VIP", callback_data="lmt:vip:menu")],
            [InlineKeyboardButton(text=tr("btn_back", "fa"), callback_data="adm:menu")],
        ])

    def _tier_panel(tier: str, tiers: dict) -> tuple[str, InlineKeyboardMarkup]:
        tier_name = "VIP" if tier == "vip" else "عادی"
        vals = tiers.get(tier, {})
        rows = []
        for key, (label, unit, _step, _lo, _hi) in _LIMIT_META.items():
            v = int(vals.get(key) or 0)
            disp = f"{v} {unit}".strip()
            rows.append([
                InlineKeyboardButton(text="➖", callback_data=f"lmt:{tier}:{key}:m"),
                InlineKeyboardButton(text=f"{label}: {disp}", callback_data="noop"),
                InlineKeyboardButton(text="➕", callback_data=f"lmt:{tier}:{key}:p"),
            ])
        other = "normal" if tier == "vip" else "vip"
        rows.append([
            InlineKeyboardButton(text=tr("btn_default", "fa"), callback_data=f"lmd:{tier}"),
            InlineKeyboardButton(text=("⭐ VIP" if other == "vip" else "🏠 عادی"),
                                 callback_data=f"lmt:{other}:menu"),
        ])
        rows.append([InlineKeyboardButton(text=tr("btn_back", "fa"), callback_data="lmt:menu")])
        text = tr("tier_panel_title", "fa", tier=tier_name)
        return text, InlineKeyboardMarkup(inline_keyboard=rows)

    def _ulim_panel(uid: int, row) -> tuple[str, InlineKeyboardMarkup]:
        tier_vals = (cfg.tier_defaults()).get("vip" if row["is_vip"] else "normal", {})
        lines = [tr("ulim_title", "fa", uid=uid)]
        rows = []
        for key, (label, unit, _step, _lo, _hi) in _ULIM_META.items():
            v = row[key]
            if v:
                disp = f"{v} {unit}".strip()
            else:
                disp = f"پیش‌فرض ({tier_vals.get(key, '?')})"
            rows.append([
                InlineKeyboardButton(text="➖", callback_data=f"ulm:{uid}:{key}:m"),
                InlineKeyboardButton(text=f"{label}: {disp}", callback_data="noop"),
                InlineKeyboardButton(text="➕", callback_data=f"ulm:{uid}:{key}:p"),
            ])
        rows.append([InlineKeyboardButton(text="♻️ پاک‌کردن همه",
                                          callback_data=f"ulc:{uid}")])
        rows.append([InlineKeyboardButton(text=tr("btn_back", "fa"),
                                          callback_data=f"uvw:{uid}")])
        return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)

    # ------------------------------------------------------------------
    # panel entry
    # ------------------------------------------------------------------
    def panel_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 آمار", callback_data="adm:stats"),
             InlineKeyboardButton(text="🩺 سلامت", callback_data="adm:health")],
            [InlineKeyboardButton(text="⏸/▶️ پذیرش", callback_data="adm:pause"),
             InlineKeyboardButton(text="📋 صف", callback_data="adm:queue")],
            [InlineKeyboardButton(text="📡 مانیتور", callback_data="adm:monitor"),
             InlineKeyboardButton(text="❌ خطاها", callback_data="adm:errors")],
            [InlineKeyboardButton(text="🧹 پاک‌سازی", callback_data="adm:cleanup"),
             InlineKeyboardButton(text="🖼 تامبنیل", callback_data="adm:thumb")],
            [InlineKeyboardButton(text="👥 کاربران", callback_data="uws:0"),
             InlineKeyboardButton(text="🎚 محدودیت‌ها", callback_data="adm:limits")],
            [InlineKeyboardButton(text="📢 اطلاع‌رسانی", callback_data="adm:broadcast"),
             InlineKeyboardButton(text="🚫 بن", callback_data="adm:ban")],
            [InlineKeyboardButton(text="🔒 عضویت اجباری", callback_data="adm:fsub")],
        ])

    @router.message(F.text.startswith("/admin"))
    async def on_admin(message: Message):
        if not await is_admin(db, cfg, message.from_user.id):
            await message.answer(tr("admin_denied"))
            return
        pending_mode.pop(message.from_user.id, None)  # /admin cancels pending flows
        await message.answer(
            tr("admin_panel_title", "fa"),
            reply_markup=panel_keyboard(),
        )

    async def _guard(callback: CallbackQuery) -> bool:
        if not await is_admin(db, cfg, callback.from_user.id):
            await callback.answer(tr("admin_denied"), show_alert=True)
            return False
        return True

    @router.callback_query(F.data == "noop")
    async def on_noop(callback: CallbackQuery):
        await callback.answer()

    @router.callback_query(F.data == "pcx")
    async def on_pending_cancel(callback: CallbackQuery):
        if not await _guard(callback):
            return
        pending_mode.pop(callback.from_user.id, None)
        pending_target.pop(callback.from_user.id, None)
        await callback.answer(tr("pending_cancelled", "fa"), show_alert=True)

    @router.callback_query(F.data.startswith("adm:"))
    async def on_admin_action(callback: CallbackQuery):
        if not await _guard(callback):
            return
        await callback.answer()
        action = callback.data.split(":", 1)[1]

        if action == "menu":
            try:
                await callback.message.edit_text(
                    tr("admin_panel_title", "fa"), reply_markup=panel_keyboard())
            except Exception:  # noqa: BLE001
                pass

        elif action == "stats":
            counters = await db.get_counters()
            rows = await db.fetch("SELECT status, count(*) AS n FROM jobs GROUP BY status")
            by = {r["status"]: r["n"] for r in rows}
            queued = by.get("queued", 0)
            active = by.get("processing", 0)
            try:
                encre_queue = await engine.encre.queue_count()
            except Exception:  # noqa: BLE001
                encre_queue = "?"
            free = engine._disk_free()
            uptime = int(time.time() - state.started_at)
            await callback.message.answer(
                f"📊 آمار کلی:\n"
                f"درخواست: {counters.get('requests_total', 0)} | انکد: {counters.get('jobs_encoded', 0)} | "
                f"ناموفق: {counters.get('jobs_failed', 0)} | لغو: {counters.get('jobs_cancelled', 0)}\n"
                f"صف: {queued} | فعال: {active} | صف Encore: {encre_queue}\n"
                f"dedup: دقیق {counters.get('dedup_exact_reuse', 0)} | فازی {counters.get('dedup_fuzzy_reuse', 0)} | "
                f"پیوسته {counters.get('dedup_inflight_joined', 0)} | مشابه {counters.get('dedup_similarity_reuse', 0)} | "
                f"ارتقا HEVC {counters.get('level_escalations', 0)} | no-gain {counters.get('no_gain_events', 0)}\n"
                f"بایت: ورودی {human_size(counters.get('bytes_in', 0))} | خروجی {human_size(counters.get('bytes_out', 0))} | "
                f"صرفه {human_size(counters.get('bytes_saved', 0))}\n"
                f"تحویل: موفق {counters.get('deliveries_ok', 0)} | ناموفق {counters.get('deliveries_failed', 0)}\n"
                f"دیسک: {human_size(free)} | آپ‌تایم: {uptime // 3600}h{(uptime % 3600) // 60}m | "
                f"ورکر: {cfg.worker_replicas} | {'⏸ متوقف' if state.paused else '▶️ فعال'}"
            )

        elif action == "health":
            parts = []
            try:
                await db.fetchval("SELECT 1")
                parts.append("✅ PostgreSQL")
            except Exception as exc:  # noqa: BLE001
                parts.append(f"❌ PostgreSQL: {str(exc)[:60]}")
            try:
                health = await engine.encre.health()
                parts.append(f"{'✅' if health.get('status') == 'UP' else '❌'} Encore {health.get('status')}")
            except Exception as exc:  # noqa: BLE001
                parts.append(f"❌ Encore: {str(exc)[:60]}")
            try:
                me = await engine.bot.get_me()
                parts.append(f"✅ BotAPI @{me.username}")
            except Exception as exc:  # noqa: BLE001
                parts.append(f"❌ BotAPI: {str(exc)[:60]}")
            parts.append(f"💾 {human_size(engine._disk_free())}")
            parts.append(f"📺 آرشیو: {state.archive_channel_id or 'تنظیم نشده'}")
            parts.append(f"🖼 تامبنیل: {'✅' if state.global_thumb else '—'}")
            await callback.message.answer("\n".join(parts))

        elif action == "pause":
            state.paused = not state.paused
            await db.set_config("paused", state.paused)
            await callback.message.answer(
                tr("admin_paused" if state.paused else "admin_resumed", "fa")
            )

        elif action == "queue":
            queued = await db.fetchval("SELECT count(*) FROM jobs WHERE status='queued'")
            active = await db.fetchval("SELECT count(*) FROM jobs WHERE status='processing'")
            try:
                encre_queue = await engine.encre.queue_count()
            except Exception:  # noqa: BLE001
                encre_queue = "?"
            rows = await db.fetch(
                "SELECT left(id::text,8) jid, status, profile, progress, requester_tg_id "
                "FROM jobs WHERE status IN ('queued','processing') ORDER BY enqueued_at LIMIT 10"
            )
            lines = [tr("admin_queue_view", "fa", queued=queued, active=active, encre=encre_queue)]
            for r in rows:
                lines.append(f"{r['jid']} {r['status']} {r['profile']} {r['progress']}% u{r['requester_tg_id']}")
            await callback.message.answer("\n".join(lines))

        elif action == "errors":
            rows = await db.fetch(
                "SELECT left(id::text,8) jid, error_category cat, left(coalesce(error_message,''),90) msg "
                "FROM jobs WHERE status='failed' ORDER BY completed_at DESC LIMIT 5"
            )
            if not rows:
                await callback.message.answer("خطای اخیری نیست ✅")
                return
            body = "\n".join(f"{r['jid']} [{r['cat']}] {r['msg']}" for r in rows)
            await callback.message.answer(f"{tr('admin_recent_errors', 'fa')}\n{body}")

        elif action == "cleanup":
            await engine.cleanup_sweep()
            await callback.message.answer(
                f"🧹 پاک‌سازی شد؛ دیسک آزاد: {human_size(engine._disk_free())}"
            )

        elif action == "monitor":
            old = live_tasks.get(callback.from_user.id)
            if old and not old.done():
                old.cancel()
                live_tasks.pop(callback.from_user.id, None)
            sent = await callback.message.answer("📡 …")
            task = asyncio.create_task(_monitor_loop(
                callback.message.chat.id, callback.from_user.id, sent.message_id))
            live_tasks[callback.from_user.id] = task

        elif action == "limits":
            try:
                await callback.message.edit_text(
                    tr("admin_limits_pick", "fa"), reply_markup=_tier_picker_kb())
            except Exception:  # noqa: BLE001
                await callback.message.answer(
                    tr("admin_limits_pick", "fa"), reply_markup=_tier_picker_kb())

        elif action == "thumb":
            pending_mode[callback.from_user.id] = ("thumb", time.time())
            current = "تنظیم شده ✅" if state.global_thumb else "تنظیم نشده"
            await callback.message.answer(
                tr("admin_thumb_prompt", "fa") + f"\n\nوضعیت فعلی: {current}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text=tr("admin_thumb_delete_btn", "fa"),
                                         callback_data="thdel"),
                    InlineKeyboardButton(text=tr("btn_cancel", "fa"), callback_data="pcx"),
                ]]),
            )

        elif action == "ban":
            pending_mode[callback.from_user.id] = ("user", time.time())
            await callback.message.answer(
                tr("admin_user_prompt", "fa"), reply_markup=_cancel_kb())

        elif action == "broadcast":
            pending_mode[callback.from_user.id] = ("broadcast", time.time())
            await callback.message.answer(
                tr("admin_broadcast_prompt", "fa"), reply_markup=_cancel_kb())

        elif action == "fsub":
            conf = await forcesub.current(db)
            state_txt = (f"فعال روی {conf['channel_id']}" if conf["enabled"]
                         else "غیرفعال")
            pending_mode[callback.from_user.id] = ("fsub", time.time())
            await callback.message.answer(
                f"🔒 وضعیت: {state_txt}\n\n" + tr("admin_fsub_prompt", "fa"),
                reply_markup=_cancel_kb(),
            )

    # ------------------------------------------------------------------
    # tier limits - stepper panel (no typing)
    # ------------------------------------------------------------------
    @router.callback_query(F.data == "lmt:menu")
    async def on_limits_picker(callback: CallbackQuery):
        if not await _guard(callback):
            return
        await callback.answer()
        try:
            await callback.message.edit_text(
                tr("admin_limits_pick", "fa"), reply_markup=_tier_picker_kb())
        except Exception:  # noqa: BLE001
            pass

    @router.callback_query(F.data.startswith("lmt:"))
    async def on_limit_step(callback: CallbackQuery):
        if not await _guard(callback):
            return
        await callback.answer()
        parts = callback.data.split(":")  # lmt:<tier>:<key>:<p|m> | lmt:<tier>:menu
        if len(parts) < 3:
            return
        tier = parts[1]
        if tier not in ("normal", "vip"):
            return
        if parts[2] == "menu":
            tiers = await engine.tiers_config()
            text, kb = _tier_panel(tier, tiers)
            try:
                await callback.message.edit_text(text, reply_markup=kb)
            except Exception:  # noqa: BLE001
                pass
            return
        if len(parts) < 4 or parts[2] not in engine._LIMIT_KEYS:
            return
        key, direction = parts[2], parts[3]
        label, unit, step, lo, hi = _LIMIT_META[key]
        tiers = copy.deepcopy(await engine.tiers_config())
        cur = int(tiers[tier].get(key) or 0)
        new = max(lo, min(hi, cur + (step if direction == "p" else -step)))
        if new == cur:
            return
        tiers[tier][key] = new
        await db.set_config("limits", tiers)
        engine.invalidate_tiers()
        await audit_mod.log_action(db, "admin:" + str(callback.from_user.id), "admin",
                                   "user.limits", tier,
                                   f"{key}: {cur} → {new}", source="telegram")
        text, kb = _tier_panel(tier, tiers)
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except Exception:  # noqa: BLE001
            pass

    @router.callback_query(F.data.startswith("lmd:"))
    async def on_limit_default(callback: CallbackQuery):
        if not await _guard(callback):
            return
        await callback.answer(tr("pending_saved", "fa"))
        tier = callback.data.split(":", 1)[1]
        if tier not in ("normal", "vip"):
            return
        tiers = copy.deepcopy(await engine.tiers_config())
        tiers[tier] = dict(cfg.tier_defaults()[tier])
        await db.set_config("limits", tiers)
        engine.invalidate_tiers()
        text, kb = _tier_panel(tier, tiers)
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # users browser + user card
    # ------------------------------------------------------------------
    async def _users_page(page: int):
        total = await db.fetchval("SELECT count(*) FROM users")
        rows = await db.fetch(
            "SELECT tg_id, first_name, username, is_vip, is_blocked FROM users "
            "ORDER BY last_seen_at DESC LIMIT 20 OFFSET $1",
            page * 20,
        )
        pages = max(1, (total + 19) // 20)
        return rows, pages, total

    def _users_kb(rows, page: int, pages: int) -> InlineKeyboardMarkup:
        kb_rows = []
        for r in rows:
            name = (r["first_name"] or str(r["tg_id"]))[:20]
            mark = ("💎" if r["is_vip"] else "") + ("🚫" if r["is_blocked"] else "")
            kb_rows.append([InlineKeyboardButton(
                text=f"{mark}{name}", callback_data=f"uvw:{r['tg_id']}")])
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"uws:{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"uws:{page + 1}"))
        kb_rows.append(nav)
        kb_rows.append([InlineKeyboardButton(text=tr("btn_back", "fa"),
                                             callback_data="adm:menu")])
        return InlineKeyboardMarkup(inline_keyboard=kb_rows)

    @router.callback_query(F.data.startswith("uws:"))
    async def on_users_page(callback: CallbackQuery):
        if not await _guard(callback):
            return
        await callback.answer()
        try:
            page = max(0, int(callback.data.split(":")[1]))
        except (TypeError, ValueError):
            page = 0
        rows, pages, total = await _users_page(page)
        if not rows:
            try:
                await callback.message.edit_text(tr("admin_users_empty", "fa"))
            except Exception:  # noqa: BLE001
                pass
            return
        text = tr("admin_users_title", "fa") + f" ({total})"
        try:
            await callback.message.edit_text(
                text, reply_markup=_users_kb(rows, page, pages))
        except Exception:  # noqa: BLE001
            pass

    @router.callback_query(F.data.startswith("uvw:"))
    async def on_user_view(callback: CallbackQuery):
        if not await _guard(callback):
            return
        await callback.answer()
        try:
            uid = int(callback.data.split(":", 1)[1])
        except (TypeError, ValueError):
            return
        row = await db.fetchrow("SELECT * FROM users WHERE tg_id = $1", uid)
        if not row:
            await callback.answer(tr("admin_user_notfound", "fa"), show_alert=True)
            return
        try:
            await callback.message.edit_text(
                _user_card(row), reply_markup=_user_card_kb(row))
        except Exception:  # noqa: BLE001
            pass

    @router.callback_query(F.data.startswith("uvip:"))
    async def on_user_vip(callback: CallbackQuery):
        if not await _guard(callback):
            return
        await callback.answer()
        uid = int(callback.data.split(":", 1)[1])
        await db.execute("UPDATE users SET is_vip = NOT is_vip WHERE tg_id = $1", uid)
        row = await db.fetchrow("SELECT * FROM users WHERE tg_id = $1", uid)
        await audit_mod.log_action(db, "admin:" + str(callback.from_user.id), "admin",
                                   "user.vip", uid, f"new={bool(row['is_vip'])}",
                                   source="telegram")
        try:
            await callback.message.edit_text(
                _user_card(row), reply_markup=_user_card_kb(row))
        except Exception:  # noqa: BLE001
            pass

    @router.callback_query(F.data.startswith("uadm:"))
    async def on_user_admin(callback: CallbackQuery):
        if not await _guard(callback):
            return
        await callback.answer()
        uid = int(callback.data.split(":", 1)[1])
        row = await db.fetchrow("SELECT is_admin FROM users WHERE tg_id = $1", uid)
        if row is None:
            await callback.answer(tr("admin_user_notfound", "fa"), show_alert=True)
            return
        actor = "admin:" + str(callback.from_user.id)
        if row["is_admin"]:
            if not await engine.is_owner(callback.from_user.id):
                await callback.answer(
                    "فقط owner می‌تواند ادمین را حذف کند.", show_alert=True)
                return
            ok, why = await engine.demote_admin(actor, uid)
        else:
            ok, why = await engine.promote_admin(actor, uid)
        if not ok:
            msgs = {"is_owner": "owner قابل حذف نیست.",
                    "last_admin": "آخرین ادمین قابل حذف نیست.",
                    "user_not_found": "کاربر یافت نشد.",
                    "already_admin": "از قبل ادمین است.",
                    "not_admin": "این کاربر ادمین نیست."}
            await callback.answer(msgs.get(why, why), show_alert=True)
            return
        await callback.answer("✅ انجام شد — منوی دستورات ادمین‌ها به‌روزرسانی شد")
        fresh = await db.fetchrow("SELECT * FROM users WHERE tg_id = $1", uid)
        try:
            await callback.message.edit_text(_user_card(fresh),
                                             reply_markup=_user_card_kb(fresh))
        except Exception:  # noqa: BLE001
            pass

    @router.callback_query(F.data.startswith("uban:"))
    async def on_user_ban(callback: CallbackQuery):
        if not await _guard(callback):
            return
        await callback.answer()
        uid = int(callback.data.split(":", 1)[1])
        await db.execute("UPDATE users SET is_blocked = NOT is_blocked WHERE tg_id = $1", uid)
        row = await db.fetchrow("SELECT * FROM users WHERE tg_id = $1", uid)
        await audit_mod.log_action(db, "admin:" + str(callback.from_user.id), "admin",
                                   "user.ban", uid, f"new={bool(row['is_blocked'])}",
                                   source="telegram")
        try:
            await callback.message.edit_text(
                _user_card(row), reply_markup=_user_card_kb(row))
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # per-user limits - stepper panel (0 = tier default)
    # ------------------------------------------------------------------
    @router.callback_query(F.data.startswith("ulm:"))
    async def on_ulim(callback: CallbackQuery):
        if not await _guard(callback):
            return
        await callback.answer()
        parts = callback.data.split(":")  # ulm:<uid>:<key>:<d> | ulm:<uid>:menu
        try:
            uid = int(parts[1])
        except (TypeError, ValueError):
            return
        row = await db.fetchrow("SELECT * FROM users WHERE tg_id = $1", uid)
        if not row:
            await callback.answer(tr("admin_user_notfound", "fa"), show_alert=True)
            return
        if parts[2] == "menu":
            text, kb = _ulim_panel(uid, row)
            try:
                await callback.message.edit_text(text, reply_markup=kb)
            except Exception:  # noqa: BLE001
                pass
            return
        key, direction = parts[2], parts[3]
        if key not in _ULIM_META:
            return
        label, unit, step, lo, hi = _ULIM_META[key]
        tier_vals = cfg.tier_defaults().get("vip" if row["is_vip"] else "normal", {})
        cur = int(row[key]) if row[key] else int(tier_vals.get(key, lo))
        new = max(0, min(hi, cur + (step if direction == "p" else -step)))
        if direction == "m" and new <= 0:
            new = 0  # 0 = clear override, fall back to the tier default
        await db.execute(_LIMIT_SET_SQL[key], uid, new if new > 0 else None)
        row = await db.fetchrow("SELECT * FROM users WHERE tg_id = $1", uid)
        text, kb = _ulim_panel(uid, row)
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except Exception:  # noqa: BLE001
            pass

    @router.callback_query(F.data.startswith("ulc:"))
    async def on_ulim_clear(callback: CallbackQuery):
        if not await _guard(callback):
            return
        await callback.answer(tr("pending_saved", "fa"))
        uid = int(callback.data.split(":", 1)[1])
        await db.execute(
            "UPDATE users SET max_source_gb = NULL, max_duration_min = NULL, "
            "daily_quota_gb = NULL WHERE tg_id = $1", uid)
        row = await db.fetchrow("SELECT * FROM users WHERE tg_id = $1", uid)
        text, kb = _ulim_panel(uid, row)
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # free-form admin message to a user
    # ------------------------------------------------------------------
    @router.callback_query(F.data.startswith("umsg:"))
    async def on_user_msg(callback: CallbackQuery):
        if not await _guard(callback):
            return
        await callback.answer()
        uid = int(callback.data.split(":", 1)[1])
        pending_mode[callback.from_user.id] = ("umsg", time.time())
        pending_target[callback.from_user.id] = uid
        await callback.message.answer(
            tr("msg_prompt", "fa", uid=uid), reply_markup=_cancel_kb())

    # ------------------------------------------------------------------
    # broadcast - preview + confirm (no accidental sends)
    # ------------------------------------------------------------------
    @router.callback_query(F.data == "bgo")
    async def on_broadcast_go(callback: CallbackQuery):
        if not await _guard(callback):
            return
        await callback.answer()
        text = bcast_text.pop(callback.from_user.id, None)
        if text is None:
            return
        users = await db.fetch(
            "SELECT tg_id FROM users WHERE is_blocked = FALSE AND notify_done = TRUE"
        )
        ok = fail = 0
        for i, u in enumerate(users):
            try:
                await engine.bot.send_message(u["tg_id"], text)
                ok += 1
            except Exception:  # noqa: BLE001
                fail += 1
            if (i + 1) % 20 == 0:
                await asyncio.sleep(1)  # rate-limited batches
        await audit_mod.log_action(db, "admin:" + str(callback.from_user.id), "admin",
                                   "broadcast", f"recipients={len(users)}",
                                   f"ok={ok} fail={fail} text={text[:60]!r}",
                                   source="telegram")
        await callback.message.answer(
            tr("admin_broadcast_done", "fa", ok=ok, fail=fail))

    @router.callback_query(F.data == "bno")
    async def on_broadcast_no(callback: CallbackQuery):
        if not await _guard(callback):
            return
        bcast_text.pop(callback.from_user.id, None)
        await callback.answer(tr("pending_cancelled", "fa"), show_alert=True)

    # ------------------------------------------------------------------
    # thumbnail delete button
    # ------------------------------------------------------------------
    @router.callback_query(F.data == "thdel")
    async def on_thumb_delete(callback: CallbackQuery):
        if not await _guard(callback):
            return
        await callback.answer()
        state.global_thumb = None
        await db.set_config("global_thumb_path", None)
        pending_mode.pop(callback.from_user.id, None)
        try:
            await callback.message.edit_text(tr("admin_thumb_cleared", "fa"))
        except Exception:  # noqa: BLE001
            pass

    @router.callback_query(F.data == "mon:stop")
    async def on_monitor_stop(callback: CallbackQuery):
        if not await _guard(callback):
            return
        await callback.answer()
        task = live_tasks.pop(callback.from_user.id, None)
        if task:
            task.cancel()
        try:
            await callback.message.edit_text("⏹ " + tr("admin_monitor_stopped", "fa"))
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # pending text/photo handlers (scoped + cancellable)
    # ------------------------------------------------------------------
    def _has_pending(mode: str):
        async def _filter(message: Message) -> bool:
            pending = pending_mode.get(message.from_user.id)
            return bool(pending) and pending[0] == mode and time.time() - pending[1] < 600
        return _filter

    @router.message(F.text, _has_pending("user"))
    async def on_admin_user_text(message: Message):
        pending_mode.pop(message.from_user.id, None)
        try:
            uid = int((message.text or "").strip())
        except (TypeError, ValueError):
            await message.answer(tr("admin_user_prompt", "fa"))
            return
        row = await db.fetchrow("SELECT * FROM users WHERE tg_id = $1", uid)
        if not row:
            await message.answer(tr("admin_user_notfound", "fa"))
            return
        await message.answer(_user_card(row), reply_markup=_user_card_kb(row))

    @router.message(F.text, _has_pending("umsg"))
    async def on_admin_umsg_text(message: Message):
        pending_mode.pop(message.from_user.id, None)
        uid = pending_target.pop(message.from_user.id, None)
        if uid is None:
            return
        try:
            await engine.bot.send_message(uid, message.text or "")
            await message.answer(tr("msg_sent", "fa", uid=uid))
        except TelegramAPIError:
            await message.answer(tr("msg_fail", "fa", uid=uid))

    @router.message(F.text, _has_pending("broadcast"))
    async def on_admin_broadcast_text(message: Message):
        pending_mode.pop(message.from_user.id, None)
        text = (message.text or "").strip()
        if not text:
            await message.answer(tr("admin_broadcast_prompt", "fa"))
            return
        recipients = await db.fetchval(
            "SELECT count(*) FROM users WHERE is_blocked = FALSE AND notify_done = TRUE")
        bcast_text[message.from_user.id] = text
        preview = text[:3000] + ("…" if len(text) > 3000 else "")
        await message.answer(
            tr("bcast_preview", "fa", n=recipients) + f"\n\n{preview}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=tr("btn_send", "fa") + f" ({recipients})",
                                     callback_data="bgo"),
                InlineKeyboardButton(text=tr("btn_cancel", "fa"), callback_data="bno"),
            ]]),
        )

    @router.message(F.photo, _has_pending("thumb"))
    async def on_admin_thumb_photo(message: Message):
        pending_mode.pop(message.from_user.id, None)
        try:
            tg_file = await engine.bot.get_file(message.photo[-1].file_id)
            src = await engine.resolve_local_path(tg_file.file_path)
            if src is None:
                raise RuntimeError("photo file unreadable")
            Path(cfg.media_thumbs).mkdir(parents=True, exist_ok=True)
            dst = Path(cfg.media_thumbs) / "global.jpg"
            ok = await asyncio.to_thread(
                media_mod.download_thumbnail, str(src), str(dst)
            )
            if not ok:
                raise RuntimeError("thumbnail normalize failed")
        except Exception as exc:  # noqa: BLE001
            await message.answer(tr("settings_thumb_failed", "fa", error=str(exc)[:80]))
            return
        state.global_thumb = str(dst)
        await db.set_config("global_thumb_path", str(dst))
        await message.answer(tr("admin_thumb_saved", "fa"))

    @router.message(F.text, _has_pending("fsub"))
    async def on_admin_fsub_text(message: Message):
        pending_mode.pop(message.from_user.id, None)
        raw = (message.text or "").strip()
        if raw.lower() in ("off", "خاموش", "حذف"):
            await db.set_config("force_sub", {"enabled": False})
            forcesub.clear_cache()
            await message.answer(tr("admin_fsub_off", "fa"))
            return
        channel_token, _, link = raw.partition("|")
        channel_token, link = channel_token.strip(), (link.strip() or None)
        channel_id = None
        try:
            if channel_token.lstrip("-").isdigit():
                channel_id = int(channel_token)
                chat = await engine.bot.get_chat(channel_id)
            elif channel_token.startswith("@"):
                chat = await engine.bot.get_chat(channel_token)
                channel_id = chat.id
            elif channel_token.startswith("https://t.me/"):
                uname = channel_token.split("t.me/", 1)[1].split("/")[0]
                chat = await engine.bot.get_chat("@" + uname)
                channel_id = chat.id
                link = link or f"https://t.me/{uname}"
            else:
                await message.answer(tr("admin_fsub_prompt", "fa"))
                return
            if link is None and getattr(chat, "username", None):
                link = f"https://t.me/{chat.username}"
            if link is None and getattr(chat, "invite_link", None):
                link = chat.invite_link
            me = await engine.bot.get_me()
            member = await engine.bot.get_chat_member(channel_id, me.id)
            if member.status != "administrator":
                await message.answer(tr("admin_fsub_verify_failed", "fa",
                                        error="bot is not an admin of that channel"))
                return
        except Exception as exc:  # noqa: BLE001
            await message.answer(tr("admin_fsub_verify_failed", "fa",
                                    error=str(exc)[:120]))
            return
        await db.set_config("force_sub",
                            {"enabled": True, "channel_id": channel_id, "link": link})
        forcesub.clear_cache()
        note = "" if link else "\n⚠️ برای این کانال لینکی پیدا نشد؛ دکمهٔ «عضویت» ساخته نمی‌شود (فقط دکمهٔ بررسی)."
        await message.answer(tr("admin_fsub_saved", "fa",
                                channel=channel_id, link=link or "-") + note)

    async def sweep_pending() -> None:
        now = time.time()
        for uid in [u for u, (_, t) in pending_mode.items() if now - t > 600]:
            pending_mode.pop(uid, None)
            pending_target.pop(uid, None)
        for uid in [u for u, t in bcast_text.items() if now - t > 600]:
            bcast_text.pop(uid, None)

    router.sweep_pending = sweep_pending  # type: ignore[attr-defined]
    return router
