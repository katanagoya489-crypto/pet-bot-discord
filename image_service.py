from __future__ import annotations
from pathlib import Path
from typing import Optional
import discord

FIXED_CHARACTER_CHANNEL_ID = 1481886210199781498
IMAGE_CACHE: dict[str, str] = {}
CACHE_READY = False

def normalize_key(key: str | None) -> str:
    return (key or "").strip().replace("　", " ")

def _add_key(key: str | None, url: str):
    key = normalize_key(key)
    if key:
        IMAGE_CACHE.setdefault(key, url)

async def warm_image_cache(bot: discord.Client, channel_id: int | None = None) -> int:
    global CACHE_READY
    IMAGE_CACHE.clear()
    cid = int(channel_id or FIXED_CHARACTER_CHANNEL_ID)
    channel = bot.get_channel(cid)
    if channel is None:
        try:
            channel = await bot.fetch_channel(cid)
        except Exception:
            print(f"画像読み込み失敗: channel={cid}")
            CACHE_READY = False
            return 0
    if not isinstance(channel, discord.TextChannel):
        print(f"画像読み込み失敗: channel={cid} is not text")
        CACHE_READY = False
        return 0
    async for msg in channel.history(limit=4000):
        if not msg.attachments:
            continue
        content = (msg.content or "").strip()
        url = msg.attachments[0].url
        if content:
            _add_key(content, url)
            _add_key(content.splitlines()[0].strip(), url)
        for att in msg.attachments:
            _add_key(Path(att.filename).stem, att.url)
    CACHE_READY = True
    print(f"画像読み込み完了: {len(IMAGE_CACHE)}件 / channel={cid}")
    return len(IMAGE_CACHE)

async def get_image_url(bot: discord.Client, key: str) -> Optional[str]:
    global CACHE_READY
    if not key:
        return None
    if not CACHE_READY:
        await warm_image_cache(bot)
    return IMAGE_CACHE.get(normalize_key(key))
