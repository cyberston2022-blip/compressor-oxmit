"""
Progress Manager with Telegram 429 Rate-Limit Prevention.
"""
import asyncio
import time
from typing import Dict, Tuple
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.exceptions import TelegramRetryAfter
from .progress_cards import ProgressState, render_glass_card

class ProgressManager:
    def __init__(self, bot: Bot, min_edit_interval: float = 2.5):
        self.bot = bot
        self.min_interval = min_edit_interval
        self._last_edit: Dict[Tuple[int, int], float] = {}
        self._lock = asyncio.Lock()

    async def update_progress(self, chat_id: int, message_id: int, state: ProgressState, reply_markup: InlineKeyboardMarkup = None, force: bool = False):
        key = (chat_id, message_id)
        now = time.time()
        
        if not force and key in self._last_edit:
            if now - self._last_edit[key] < self.min_interval:
                return

        text = render_glass_card(state)
        async with self._lock:
            try:
                await self.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
                self._last_edit[key] = time.time()
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
            except Exception:
                pass
