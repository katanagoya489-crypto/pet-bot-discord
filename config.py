
from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
ENTRY_CHANNEL_ID = int(os.getenv("ENTRY_CHANNEL_ID", "0"))
CHARACTER_CHANNEL_ID = int(os.getenv("CHARACTER_CHANNEL_ID", "0"))
DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/bot.db")

SLEEP_START = os.getenv("SLEEP_START", "00:00")
SLEEP_END = os.getenv("SLEEP_END", "07:00")
ADMIN_USER_IDS = {int(x) for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip().isdigit()}

AUTO_TICK_SECONDS = int(os.getenv("AUTO_TICK_SECONDS", "60"))
THREAD_AUTO_ARCHIVE_MINUTES = int(os.getenv("THREAD_AUTO_ARCHIVE_MINUTES", "60"))

DEFAULT_NOTIFICATION_MODE = os.getenv("DEFAULT_NOTIFICATION_MODE", "tamagotchi")
