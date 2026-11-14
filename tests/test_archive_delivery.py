"""Tests for archive captions, flood safety, and delivery fallback chain."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramRetryAfter

from oxmit.archive import build_caption, deliver_result, flood_safe


def test_build_caption_formatting():
    probe = {
        "width": 1920,
        "height": 1080,
        "vcodec": "h264",
        "acodec": "aac",
        "duration_s": 3665,
    }
    cap = build_caption("my_video.mp4", "Balanced", probe, 100_000_000, 40_000_000, "abc12345")
    assert "my_video.mp4" in cap
    assert "1920×1080" in cap
    assert "H264/AAC" in cap
    assert "1:01:05" in cap
    assert "abc12345" in cap
    assert "-60%" in cap


@pytest.mark.asyncio
async def test_flood_safe_retries_once():
    calls = 0

    async def _action():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TelegramRetryAfter(method=MagicMock(), message="flood", retry_after=0.01)
        return "success"

    res = await flood_safe(_action)
    assert res == "success"
    assert calls == 2


@pytest.mark.asyncio
async def test_deliver_result_copies_without_forward_attribution():
    engine = MagicMock()
    msg = MagicMock()
    msg.message_id = 999
    engine.bot.copy_message = AsyncMock(return_value=msg)
    engine.bot.forward_message = AsyncMock()

    ok, method, mid = await deliver_result(
        engine,
        chat_id=123,
        archive_message_id=456,
        archive_channel_id=-100123,
    )
    assert ok is True
    assert method == "copy"
    assert mid == 999
    engine.bot.copy_message.assert_awaited_once()
    # The private storage channel must never show up as "forwarded from".
    engine.bot.forward_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliver_result_fallback_to_file_id_when_archive_message_gone():
    engine = MagicMock()
    engine.bot.copy_message = AsyncMock(
        side_effect=TelegramBadRequest(method=MagicMock(), message="message to copy not found")
    )
    msg = MagicMock()
    msg.message_id = 888
    engine.bot.send_video = AsyncMock(return_value=msg)

    ok, method, mid = await deliver_result(
        engine,
        chat_id=123,
        archive_message_id=456,
        archive_channel_id=-100123,
        file_id="tg-file-123",
    )
    assert ok is True
    assert method == "file_id"
    assert mid == 888
    engine.bot.send_video.assert_awaited_once()


@pytest.mark.asyncio
async def test_deliver_result_as_document():
    engine = MagicMock()
    msg = MagicMock()
    msg.message_id = 777
    engine.bot.send_document = AsyncMock(return_value=msg)

    ok, method, mid = await deliver_result(
        engine,
        chat_id=123,
        file_id="tg-file-doc",
        as_document=True,
    )
    assert ok is True
    assert method == "doc_file_id"
    assert mid == 777
    engine.bot.send_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_deliver_result_passes_duration_and_dimensions():
    engine = MagicMock()
    msg = MagicMock()
    msg.message_id = 888
    engine.bot.send_video = AsyncMock(return_value=msg)

    ok, method, mid = await deliver_result(
        engine,
        chat_id=123,
        file_id="tg-file-123",
        duration=45,
        width=854,
        height=480,
    )
    assert ok is True
    assert method == "file_id"
    assert mid == 888
    engine.bot.send_video.assert_awaited_once()
    kwargs = engine.bot.send_video.await_args.kwargs
    assert kwargs.get("duration") == 45
    assert kwargs.get("width") == 854
    assert kwargs.get("height") == 480


@pytest.mark.asyncio
async def test_deliver_result_probes_file_path_before_file_id(monkeypatch):
    engine = MagicMock()
    msg = MagicMock()
    msg.message_id = 889
    engine.bot.send_video = AsyncMock(return_value=msg)

    probe_mock = AsyncMock(return_value={"duration_s": 42.4, "width": 1280, "height": 720})
    from oxmit import media as media_mod
    monkeypatch.setattr(media_mod, "probe_video", probe_mock)

    ok, method, mid = await deliver_result(
        engine,
        chat_id=123,
        file_id="tg-file-123",
        file_path="/path/to/video.mp4",
    )
    assert ok is True
    assert method == "file_id"
    probe_mock.assert_awaited_once_with("/path/to/video.mp4")
    kwargs = engine.bot.send_video.await_args.kwargs
    assert kwargs.get("duration") == 42
    assert kwargs.get("width") == 1280
    assert kwargs.get("height") == 720


@pytest.mark.asyncio
async def test_deliver_result_sub_second_duration_rounds_to_one(monkeypatch):
    engine = MagicMock()
    msg = MagicMock()
    msg.message_id = 890
    engine.bot.send_video = AsyncMock(return_value=msg)

    probe_mock = AsyncMock(return_value={"duration_s": 0.4, "width": 640, "height": 480})
    from oxmit import media as media_mod
    monkeypatch.setattr(media_mod, "probe_video", probe_mock)

    ok, method, mid = await deliver_result(
        engine,
        chat_id=123,
        file_path="/path/to/subsecond.mp4",
    )
    assert ok is True
    assert method == "upload"
    kwargs = engine.bot.send_video.await_args.kwargs
    # Sub-second duration must round to 1s rather than 0s to avoid 00:00 display
    assert kwargs.get("duration") == 1
    assert kwargs.get("width") == 640
    assert kwargs.get("height") == 480


def test_build_caption_sub_second_rounds_to_one():
    probe = {
        "width": 1280,
        "height": 720,
        "vcodec": "h264",
        "acodec": "aac",
        "duration_s": 0.4,
    }
    cap = build_caption("short.mp4", "Balanced", probe, 10_000, 5_000, "abc12345")
    assert "0:01" in cap
    assert "0:00" not in cap


@pytest.mark.asyncio
async def test_deliver_result_zero_duration_normalized_to_none():
    engine = MagicMock()
    msg = MagicMock()
    msg.message_id = 891
    engine.bot.send_video = AsyncMock(return_value=msg)

    ok, method, mid = await deliver_result(
        engine,
        chat_id=123,
        file_id="fid-123",
        duration=0,
    )
    assert ok is True
    assert method == "file_id"
    kwargs = engine.bot.send_video.await_args.kwargs
    # duration=0 must be normalized to None so Telegram does not render 00:00
    assert kwargs.get("duration") is None



