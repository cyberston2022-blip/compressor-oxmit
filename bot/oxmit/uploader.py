"""
Optimized Telegram Delivery Pipeline for Transcoded Videos.
"""
import os
from pathlib import Path
from aiogram import Bot
from aiogram.types import FSInputFile, Message
from aiogram.exceptions import TelegramRetryAfter
import asyncio

class UploadPipeline:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def deliver_video(self, chat_id: int, file_path: Path, metadata: dict, caption: str = "") -> Message:
        if not file_path.exists():
            raise FileNotFoundError(f"Output video not found: {file_path}")

        video_input = FSInputFile(str(file_path))
        thumb_input = FSInputFile(metadata["thumbnail"]) if metadata.get("thumbnail") and os.path.exists(metadata["thumbnail"]) else None

        for attempt in range(5):
            try:
                return await self.bot.send_video(
                    chat_id=chat_id,
                    video=video_input,
                    thumbnail=thumb_input,
                    caption=caption,
                    duration=int(metadata.get("duration", 0)),
                    width=int(metadata.get("width", 0)),
                    height=int(metadata.get("height", 0)),
                    supports_streaming=True
                )
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
            except Exception as e:
                if attempt == 4:
                    raise e
                await asyncio.sleep(2)
