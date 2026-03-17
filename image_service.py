from __future__ import annotations
from pathlib import Path
from typing import Optional
import discord
from config import CHARACTER_CHANNEL_ID

def _norm(s: str) -> str:
    return (s or "").strip()

async def get_image_url(bot: discord.Client, key: str) -> Optional[str]:
    if not CHARACTER_CHANNEL_ID or not key:
        return None
    channel = bot.get_channel(CHARACTER_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(CHARACTER_CHANNEL_ID)
        except Exception:
            return None
    if not isinstance(channel, discord.TextChannel):
        return None

    async for msg in channel.history(limit=2000):
        text = _norm(msg.content)
        first_line = _norm(text.splitlines()[0]) if text else ""
        attach_name = ""
        if msg.attachments:
            attach_name = Path(msg.attachments[0].filename).stem
        if (text == key or first_line == key or attach_name == key) and msg.attachments:
            return msg.attachments[0].url
    return None
