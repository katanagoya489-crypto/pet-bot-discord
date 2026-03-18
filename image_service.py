from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Iterable, Optional

import discord

try:
    from config import CHARACTER_CHANNEL_ID  # type: ignore
except Exception:
    CHARACTER_CHANNEL_ID = int(os.getenv("CHARACTER_CHANNEL_ID", "0") or 0)

_CACHE: dict[str, tuple[float, Optional[str]]] = {}
_CACHE_SECONDS = 120.0


def _normalize(s: str) -> str:
    return (s or "").strip().replace("\u3000", " ")


def _filename_stem(name: str) -> str:
    return Path(name).stem.strip()


async def _iter_channel_messages(bot: discord.Client):
    if not CHARACTER_CHANNEL_ID:
        return
    channel = bot.get_channel(CHARACTER_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(CHARACTER_CHANNEL_ID)
        except Exception:
            return
    if not isinstance(channel, discord.TextChannel):
        return
    async for msg in channel.history(limit=3000):
        yield msg


async def get_image_url(bot: discord.Client, key: str) -> Optional[str]:
    key = _normalize(key)
    if not key:
        return None
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _CACHE_SECONDS:
        return cached[1]

    result: Optional[str] = None
    async for msg in _iter_channel_messages(bot):
        content = _normalize(msg.content)
        first_line = _normalize(content.splitlines()[0]) if content else ""
        attachment_stem = _filename_stem(msg.attachments[0].filename) if msg.attachments else ""
        if msg.attachments and (content == key or first_line == key or attachment_stem == key):
            result = msg.attachments[0].url
            break
    _CACHE[key] = (now, result)
    return result


async def find_first_image_url(bot: discord.Client, keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        url = await get_image_url(bot, key)
        if url:
            return url
    return None
