"""Application entry point: wiring, background loops, long polling."""

from __future__ import annotations

import asyncio
import sys

import redis.asyncio as aioredis
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.types import BotCommand

from .config import load_settings
from .db import Database
from .encore_client import EncoreClient
from .engine import JobEngine
from .gate import ChannelGateMiddleware, GateService, build_gate_router
from .handlers import admin, adminpanel, intake, menu, settings
from .handlers import merge_flow, moderation, nav, owner, personal, support
from .internal_api import start_internal_api
from .log import get_logger, setup_logging
from .resources import WorkerCpuTuner

log = get_logger("oxmit.bot")

USER_COMMANDS = [  # informational; refresh_admin_commands sets the real menus
    ("start", "شروع / Start"),
    ("settings", "⚙️ تنظیمات / Settings"),
]


def _build_session(cfg):
    server = TelegramAPIServer.from_base(cfg.local_bot_api_base)
    try:
        session = AiohttpSession(api=server, timeout=1800)
    except TypeError:
        session = AiohttpSession()
        try:
            session.api = server
        except Exception:  # noqa: BLE001
            log.exception("could not attach local bot api server to session")
        try:
            session.timeout = 1800
        except Exception:  # noqa: BLE001
            pass
    return session


async def poller_loop(engine: JobEngine, cpu_tuner: WorkerCpuTuner, cfg) -> None:
    while True:
        try:
            await engine.poll_once()
            # Only jobs actually running on a worker consume CPU; the rest sit
            # in Encore's queue. Jobs are marked 'processing' at submission, so
            # count only ones with live progress inside the activity window
            # (F17): progress_changed_at is refreshed on real progress only.
            window = int(getattr(cfg, "tuner_active_window_s", 180))
            processing = int(await engine.db.fetchval(
                "SELECT count(*) FROM jobs WHERE status = 'processing' "
                "AND progress < 100 "
                "AND progress_changed_at > now() - ($1 * interval '1 second')",
                window) or 0)
            await cpu_tuner.tune(min(processing, cfg.worker_replicas))
        except Exception:  # noqa: BLE001
            log.exception("poll_once failed")
        await asyncio.sleep(5)


async def sweep_loop(engine: JobEngine, *routers) -> None:
    while True:
        try:
            await engine.cleanup_sweep()
            for router in routers:
                sweep = getattr(router, "sweep_pending", None)
                if sweep:
                    await sweep()
        except Exception:  # noqa: BLE001
            log.exception("sweep failed")
        await asyncio.sleep(600)


async def main() -> None:
    setup_logging()
    cfg = load_settings()
    missing = [
        name
        for name, value in (
            ("BOT_TOKEN", cfg.bot_token),
            ("TELEGRAM_API_ID", cfg.api_id and "set"),
            ("TELEGRAM_API_HASH", cfg.api_hash),
            ("PG_DSN", cfg.pg_dsn),
            ("ENCRE_PASSWORD", cfg.encre_password),
            ("INTERNAL_SECRET", cfg.internal_secret),
        )
        if not value
    ]
    if missing:
        log.error("missing configuration", extra={"detail": ",".join(missing)})
        sys.exit(1)

    db = Database(cfg.pg_dsn)
    await db.connect()
    drift = await db.reconcile_counters()
    if drift:
        log.warning("lifecycle counters reconciled from row state",
                    extra={"detail": str(drift)})
    redis_client = aioredis.from_url(cfg.redis_url, decode_responses=True)
    encre = EncoreClient(cfg.encre_base, cfg.encre_user, cfg.encre_password)
    session = _build_session(cfg)
    bot = Bot(token=cfg.bot_token, session=session)
    engine = JobEngine(db, cfg, bot, encre)

    # runtime state from config + DB
    state = engine.state
    if cfg.archive_channel_id:
        state.archive_channel_id = cfg.archive_channel_id
    else:
        state.archive_channel_id = await db.get_config("archive_channel_id")
    state.paused = bool(await db.get_config("paused"))
    state.global_thumb = await db.get_config("global_thumb_path")
    db_mode = await db.get_config("access_mode")
    if db_mode in ("public", "private"):
        state.access_mode = db_mode
    else:
        state.access_mode = "private" if cfg.owner_only else "public"
    # channel-membership gate (force-join): DB-authoritative target + id
    state.gate_channel = str(await db.get_config("gate_channel") or "")
    state.gate_channel_id = str(await db.get_config("gate_channel_id") or "")
    gate = GateService(db, state)

    try:
        me = await bot.get_me()
    except Exception as exc:  # noqa: BLE001
        log.error("cannot reach local bot api server", extra={"detail": str(exc)[:200]})
        raise
    state.bot_username = me.username or ""
    log.info(
        "bot online via local bot api server",
        extra={"detail": f"@{state.bot_username} archive={state.archive_channel_id}"},
    )
    # Best-effort gate resolution at boot: numeric/@username targets resolve
    # immediately; invite links resolve later from channel events or an
    # owner forward (never blocks startup).
    try:
        if gate.active:
            cid = await gate.resolve(bot)
            log.info("gate resolve", extra={"detail": f"resolved={bool(cid)}"})
    except Exception:  # noqa: BLE001
        log.exception("gate resolve failed at startup")

    api_runners = await start_internal_api(engine, db, cfg, state, redis_client, port=8080)

    intake_router = intake.build_router(engine, db, cfg, state)
    merge_router = merge_flow.build_router(engine, db, cfg, state)
    adminpanel_router = adminpanel.build_router(engine, db, cfg, state)
    personal_router = personal.build_router(engine, db, cfg, state)
    nav_router = nav.build_router(engine, db, cfg, state)
    # The branding hub opens the personal editors via pr:* callbacks, so the
    # nav router gets a bridge to the personal router's preview renderer.
    nav_router.bind_personal_router(personal_router)  # type: ignore[attr-defined]
    support_router = support.build_router(engine, db, cfg, state)
    dp = Dispatcher()
    owner_mw = OwnerOnlyMiddleware(cfg, state)
    dp.message.outer_middleware(owner_mw)
    dp.callback_query.outer_middleware(owner_mw)
    # Gate AFTER OwnerOnly: in private mode non-owners never reach it; in
    # public mode it is the only barrier between channel members and bots.
    gate_mw = ChannelGateMiddleware(cfg, state, gate)
    dp.message.outer_middleware(gate_mw)
    dp.callback_query.outer_middleware(gate_mw)

    # Gate router FIRST: its capture handlers (channel_post/chat_member/
    # owner forward) and gate:recheck callback must win over intake's
    # channel_post archive-discovery handler.
    dp.include_router(build_gate_router(engine, db, cfg, state, gate))
    dp.include_router(menu.build_router(engine, db, cfg, state))
    # Support BEFORE every other message consumer: an explicitly opened
    # contact session / an owner reply must not be swallowed by intake or
    # pending-input handlers; its filters only match those explicit states.
    dp.include_router(support_router)
    dp.include_router(moderation.build_router(engine, db, cfg, state))
    dp.include_router(settings.build_router(engine, db, cfg, state))
    dp.include_router(nav_router)
    dp.include_router(owner.build_router(engine, db, cfg, state))
    dp.include_router(personal_router)
    dp.include_router(adminpanel_router)
    dp.include_router(admin.build_router(engine, db, cfg, state))
    # merge router BEFORE intake: its DB-filtered video handler must see
    # uploads from an active merge session first; everything else falls
    # through to the standard intake flow.
    dp.include_router(merge_router)
    dp.include_router(intake_router)

    await engine.recover_on_startup()
    try:
        await engine.refresh_admin_commands()
        log.info("bot commands registered (default + admin scopes)")
    except Exception:  # noqa: BLE001
        log.exception("set_my_commands failed")
    # Strong references: unreferenced tasks are garbage-collection candidates.
    cpu_tuner = WorkerCpuTuner(cfg)
    background = [
        asyncio.create_task(poller_loop(engine, cpu_tuner, cfg)),
        asyncio.create_task(sweep_loop(engine, intake_router, adminpanel_router,
                                       merge_router, nav_router, support_router)),
        asyncio.create_task(engine.fingerprinter.run()),
    ]

    try:
        await dp.start_polling(
            bot,
            # chat_member: gate resolution capture for private channels
            # (join/leave events of the gate channel); no second poller.
            allowed_updates=["message", "callback_query", "channel_post",
                             "chat_member"],
        )
    finally:
        for t in background:
            t.cancel()
        await asyncio.gather(*background, return_exceptions=True)
        # Engine-spawned tasks (run_job from callbacks/panel, etc.) must be
        # stopped BEFORE the pool/session they use are closed below - or they
        # die with "Task was destroyed but it is pending" and leave jobs
        # stuck in 'processing' until the next boot's recovery.
        for t in list(engine._bg_tasks):
            t.cancel()
        if engine._bg_tasks:
            await asyncio.gather(*engine._bg_tasks, return_exceptions=True)
        if 'api_runners' in locals() and api_runners:
            for r in api_runners:
                try:
                    await r.cleanup()
                except Exception:
                    pass
        if bot and bot.session:
            try:
                await bot.session.close()
            except Exception:
                pass
        await encre.aclose()
        await redis_client.aclose()
        await db.close()


from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, CallbackQuery, Message

class OwnerOnlyMiddleware(BaseMiddleware):
    def __init__(self, cfg, state) -> None:
        self.cfg = cfg
        self.state = state

    async def __call__(self, handler, event: TelegramObject, data: dict):
        is_private = getattr(self.state, "access_mode", "") == "private" or getattr(self.state, "owner_only", False) or getattr(self.cfg, "owner_only", False)
        if not is_private:
            return await handler(event, data)
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)
        owner_id = self.cfg.owner_telegram_id
        is_owner_or_admin = (owner_id and user.id == owner_id) or (user.id in getattr(self.cfg, "admin_ids", []))
        if not is_owner_or_admin:
            if isinstance(event, Message):
                await event.answer("🔒 ربات در حال حاضر در حالت خصوصی قرار دارد و تنها برای مدیران مجاز و مالک ربات (@Oxmit) در دسترس است.")
            elif isinstance(event, CallbackQuery):
                await event.answer("🔒 ربات در حال حاضر در حالت خصوصی قرار دارد.", show_alert=True)
            return
        return await handler(event, data)
