
from __future__ import annotations
from typing import Optional
import discord
from config import CHARACTER_CHANNEL_ID

async def get_image_url(bot: discord.Client, key: str) -> Optional[str]:
    if not CHARACTER_CHANNEL_ID:
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
        if (msg.content or "").strip() == key and msg.attachments:
            return msg.attachments[0].url
    return None
