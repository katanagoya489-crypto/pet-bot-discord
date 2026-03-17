from __future__ import annotations
from pathlib import Path
from typing import Optional
import discord
from config import CHARACTER_CHANNEL_ID

def _normalize(text: str) -> str:
    return (text or "").strip()

def _stem(filename: str) -> str:
    return Path(filename).stem.strip()

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

    wanted = _normalize(key)
    async for msg in channel.history(limit=2000):
        if not msg.attachments:
            continue

        content = _normalize(msg.content)
        first_line = _normalize(content.splitlines()[0] if content else "")
        matched = content == wanted or first_line == wanted

        if not matched:
            for att in msg.attachments:
                if _stem(att.filename) == wanted:
                    matched = True
                    break

        if matched:
            for att in msg.attachments:
                ctype = (att.content_type or "").lower()
                if ctype.startswith("image/") or att.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    return att.url
            return msg.attachments[0].url
    return None
