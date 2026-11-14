"""Archive channel uploads and result delivery (forward/copy/file_id chain)."""

from __future__ import annotations

import asyncio
import aiohttp
from collections.abc import Awaitable, Callable

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramRetryAfter, TelegramForbiddenError
from aiogram.types import FSInputFile

from . import media as media_mod
from .log import get_logger

log = get_logger("oxmit.archive")

NOT_FOUND_MARKERS = (
    "message to forward not found",
    "message to copy not found",
    "message not found",
    "chat not found",
)


async def flood_safe(coro_factory: Callable[[], Awaitable]):
    """Await a Telegram call; on flood-wait sleep and retry it exactly once.

    Without this, a single retry_after would abort the delivery method and
    fall through to the next one, wasting uploads on rate-limited chats.
    """
    try:
        return await coro_factory()
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after + 1)
        return await coro_factory()


def build_caption(
    filename: str,
    profile_title: str,
    probe: dict,
    source_size: int,
    output_size: int,
    job_short: str,
) -> str:
    ratio = (1 - output_size / source_size) * 100 if source_size else 0
    width = probe.get("width") or "?"
    height = probe.get("height") or "?"
    vcodec = (probe.get("vcodec") or "?").upper()
    acodec = (probe.get("acodec") or "?").upper()
    # Unknown duration must not render as 0:00 (F-DUR).
    duration = probe.get("duration_s")
    if duration:
        mins, secs = divmod(int(duration), 60)
        hours, mins = divmod(mins, 60)
        dur_text = f"{hours}:{mins:02d}:{secs:02d}" if hours else f"{mins}:{secs:02d}"
    else:
        dur_text = "نامشخص"
    return (
        f"🎬 {media_mod.sanitize_filename(filename, 40)}\n"
        f"⚙️ {profile_title} | {width}×{height} | {vcodec}/{acodec}\n"
        f"⏱ {dur_text} | 💾 {media_mod.human_size(source_size)} → "
        f"{media_mod.human_size(output_size)} (-{ratio:.0f}%)\n"
        f"🆔 {job_short}"
    )


def _is_not_found(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in NOT_FOUND_MARKERS)


async def deliver_result(
    engine,
    *,
    chat_id: int,
    archive_message_id: int = 0,
    archive_channel_id: int | None = None,
    file_id: str | None = None,
    file_path: str | None = None,
    caption: str | None = None,
    supports_streaming: bool = True,
    as_document: bool = False,
    thumbnail=None,
) -> tuple[bool, str, int | None]:
    """Deliver a result to a chat. Never raises on Telegram errors.

    Order: copy from archive (no forward attribution) -> send by file_id ->
    upload local file. as_document sends the file as an attachment instead
    of a streamable video when a direct file id/path is available. thumbnail
    (an FSInputFile) only applies to the fresh local-upload branch - Telegram
    keeps the stored thumbnail for file_id re-sends.
    Returns (ok, method, telegram_message_id).

    Uncertain outcomes (V3 §20): a timeout or connection error AFTER a
    request may have been transmitted is NOT a definitive failure. Such
    errors return ``(False, "sent_unknown", None)`` and callers must record
    an unknown delivery state instead of blindly retrying (duplicate risk).
    """
    bot = engine.bot
    if archive_message_id and archive_channel_id and not as_document:
        # copy_message, never forward_message: a copy carries no
        # "forwarded from <private channel>" header, so the storage channel
        # is never exposed to users, and the file itself is not re-uploaded.
        try:
            msg = await flood_safe(lambda: bot.copy_message(
                chat_id=chat_id,
                from_chat_id=archive_channel_id,
                message_id=archive_message_id,
                caption=caption,
            ))
            return True, "copy", msg.message_id
        except (asyncio.TimeoutError, ConnectionResetError, aiohttp.ClientError) as exc:
            log.warning("delivery outcome unknown (network) [copy]",
                        extra={"detail": str(exc)[:150]})
            return False, "sent_unknown", None
        except (TelegramBadRequest, TelegramForbiddenError, TelegramAPIError) as exc:
            if _is_not_found(exc):
                log.warning("archive message gone (copy)", extra={"detail": str(exc)[:150]})
            else:
                log.info("copy failed, trying file_id/local",
                         extra={"detail": str(exc)[:150]})
    if file_id:
        try:
            if as_document:
                msg = await flood_safe(lambda: bot.send_document(
                    chat_id=chat_id, document=file_id, caption=caption,
                ))
            else:
                msg = await flood_safe(lambda: bot.send_video(
                    chat_id=chat_id,
                    video=file_id,
                    caption=caption,
                    supports_streaming=supports_streaming,
                ))
            return True, "doc_file_id" if as_document else "file_id", msg.message_id
        except (asyncio.TimeoutError, ConnectionResetError, aiohttp.ClientError) as exc:
            log.warning("delivery outcome unknown (network) [file_id]",
                        extra={"detail": str(exc)[:150]})
            return False, "sent_unknown", None
        except (TelegramBadRequest, TelegramForbiddenError, TelegramAPIError) as exc:
            log.info("file_id send failed", extra={"detail": str(exc)[:150]})
    if file_path:
        try:
            if as_document:
                msg = await flood_safe(lambda: bot.send_document(
                    chat_id=chat_id, document=FSInputFile(file_path), caption=caption,
                ))
            else:
                msg = await flood_safe(lambda: bot.send_video(
                    chat_id=chat_id,
                    video=FSInputFile(file_path),
                    caption=caption,
                    supports_streaming=supports_streaming,
                    thumbnail=thumbnail,
                ))
            return True, "doc_upload" if as_document else "upload", msg.message_id
        except (asyncio.TimeoutError, ConnectionResetError, aiohttp.ClientError) as exc:
            log.warning("delivery outcome unknown (network) [upload]",
                        extra={"detail": str(exc)[:150]})
            return False, "sent_unknown", None
        except (TelegramBadRequest, TelegramForbiddenError, TelegramAPIError) as exc:
            log.info("local upload failed", extra={"detail": str(exc)[:150]})
    return False, "none", None
