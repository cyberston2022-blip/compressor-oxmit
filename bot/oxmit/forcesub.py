"""Forced channel membership gate (عضویت اجباری).

Config lives in app_config 'force_sub': {"enabled": bool, "channel_id": int,
"link": str | None}. Admins are always exempt. Membership results are cached
for 5 minutes (positive results only); API errors fail open so a
misconfiguration never bricks the bot - the admin panel verifies the channel
at set time instead.
"""
from __future__ import annotations

import time

from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .log import get_logger
from .texts import tr

log = get_logger("oxmit.forcesub")

_POSITIVE_TTL_S = 300
_cache: dict[int, tuple[bool, float]] = {}


def clear_cache() -> None:
    _cache.clear()


async def current(db) -> dict:
    conf = await db.get_config("force_sub")
    if isinstance(conf, dict):
        return {
            "enabled": bool(conf.get("enabled")),
            "channel_id": conf.get("channel_id"),
            "link": conf.get("link"),
        }
    return {"enabled": False, "channel_id": None, "link": None}


async def gate(engine, db, tg_id: int, is_admin_user: bool = False) -> dict | None:
    """None = allowed; dict = join prompt info (for the join markup)."""
    conf = await current(db)
    if not conf["enabled"] or not conf["channel_id"] or is_admin_user:
        return None
    cached = _cache.get(tg_id)
    now = time.time()
    if cached and cached[1] > now:
        return None if cached[0] else conf
    try:
        member = await engine.bot.get_chat_member(conf["channel_id"], tg_id)
        status = getattr(member, "status", "")
        ok = status in ("creator", "administrator", "member") or (
            status == "restricted"
            and getattr(member, "is_member", True) is not False
        )
    except TelegramAPIError as exc:
        log.warning("force-sub check failed, failing open",
                    extra={"detail": str(exc)[:120]})
        return None
    if ok:
        # Positive results only: a user who just joined must be re-checked
        # immediately, not rejected from a stale negative cache entry.
        if len(_cache) > 10000:
            _cache.clear()
        _cache[tg_id] = (True, now + _POSITIVE_TTL_S)
    return None if ok else conf


def join_markup(conf: dict, lang: str = "fa") -> InlineKeyboardMarkup:
    rows = []
    if conf.get("link"):
        rows.append([InlineKeyboardButton(text=tr("fsub_btn_join", lang),
                                          url=conf["link"])])
    rows.append([InlineKeyboardButton(text=tr("fsub_btn_check", lang),
                                      callback_data="fsub:check")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def promo_row(conf: dict, lang: str = "fa") -> list[InlineKeyboardButton] | None:
    """Non-blocking channel-promotion button row for the /start keyboard.

    Shown whenever a channel link is configured — even while enforcement
    (``enabled``) is off — so the channel stays visible without gating.
    """
    if conf.get("link"):
        return [InlineKeyboardButton(text=tr("fsub_btn_channel", lang),
                                     url=conf["link"])]
    return None
