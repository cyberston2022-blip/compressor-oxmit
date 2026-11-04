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
from .handlers import admin, adminpanel, intake, menu, settings
from .internal_api import start_internal_api
from .log import get_logger, setup_logging
from .resources import WorkerCpuTuner

log = get_logger("oxmit.bot")

USER_COMMANDS = [
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

    api_runners = await start_internal_api(engine, db, cfg, state, redis_client, port=8080)

    intake_router = intake.build_router(engine, db, cfg, state)
    adminpanel_router = adminpanel.build_router(engine, db, cfg, state)
    dp = Dispatcher()
    dp.include_router(menu.build_router(engine, db, cfg, state))
    dp.include_router(settings.build_router(engine, db, cfg, state))
    dp.include_router(adminpanel_router)
    dp.include_router(admin.build_router(engine, db, cfg, state))
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
        asyncio.create_task(sweep_loop(engine, intake_router, adminpanel_router)),
        asyncio.create_task(engine.fingerprinter.run()),
    ]

    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "channel_post"],
        )
    finally:
        for t in background:
            t.cancel()
        await asyncio.gather(*background, return_exceptions=True)
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
