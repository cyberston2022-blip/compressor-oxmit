"""
Dedicated Just-In-Time (JIT) Download Pipeline for Oxmit.
Decouples metadata intake from disk byte acquisition.
"""
import os
import shutil
import asyncio
from pathlib import Path
from aiogram import Bot

class DownloadPipeline:
    def __init__(self, bot: Bot, botapi_dir: Path = Path("/var/lib/telegram-bot-api")):
        self.bot = bot
        self.botapi_dir = botapi_dir

    async def resolve_local_file(self, file_id: str, target_dir: Path) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        file_info = await self.bot.get_file(file_id)
        rel_path = file_info.file_path
        
        local_src = self.botapi_dir / rel_path if rel_path else None
        dest_path = target_dir / (os.path.basename(rel_path) if rel_path else f"{file_id}.mp4")

        if local_src and local_src.exists():
            try:
                os.link(local_src, dest_path)
            except OSError:
                shutil.copy2(local_src, dest_path)
            return dest_path

        dest_path = await self.bot.download_file(file_info.file_path, dest_path)
        return Path(dest_path)
