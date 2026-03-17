from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import discord

try:
    from config import CHARACTER_CHANNEL_ID as CONFIG_CHARACTER_CHANNEL_ID
except Exception:
    CONFIG_CHARACTER_CHANNEL_ID = 0

CHARACTER_CHANNEL_ID = int(os.getenv('CHARACTER_CHANNEL_ID', str(CONFIG_CHARACTER_CHANNEL_ID or 0)) or 0)
_CACHE: dict[str, tuple[float, Optional[str]]] = {}
_CACHE_TTL = 300.0


def _norm(text: str) -> str:
    return (text or '').strip()


async def get_image_url(bot: discord.Client, key: str) -> Optional[str]:
    if not CHARACTER_CHANNEL_ID or not key:
        return None
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]

    channel = bot.get_channel(CHARACTER_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(CHARACTER_CHANNEL_ID)
        except Exception:
            _CACHE[key] = (now, None)
            return None
    if not isinstance(channel, discord.TextChannel):
        _CACHE[key] = (now, None)
        return None

    exact = _norm(key)
    lower = exact.lower()
    async for msg in channel.history(limit=4000):
        text = _norm(msg.content)
        first_line = _norm(text.splitlines()[0]) if text else ''
        attach_name = Path(msg.attachments[0].filename).stem if msg.attachments else ''
        candidates = {text, first_line, attach_name, text.lower(), first_line.lower(), attach_name.lower()}
        if msg.attachments and (exact in candidates or lower in candidates):
            url = msg.attachments[0].url
            _CACHE[key] = (now, url)
            return url
    _CACHE[key] = (now, None)
    return None
