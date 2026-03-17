from __future__ import annotations
from pathlib import Path
from typing import Optional
import discord
from config import CHARACTER_CHANNEL_ID

def _norm(s: str) -> str:
    return (s or "").strip()

def _match_key(text: str, key: str) -> bool:
    return _norm(text) == _norm(key)

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

    target = _norm(key)
    async for msg in channel.history(limit=2000):
        text = _norm(msg.content)
        first_line = _norm(text.splitlines()[0]) if text else ""
        if not msg.attachments:
            continue
        if _match_key(text, target) or _match_key(first_line, target):
            return msg.attachments[0].url
        for att in msg.attachments:
            stem = Path(att.filename).stem
            if _match_key(stem, target):
                return att.url
    return None
