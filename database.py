
from __future__ import annotations
import os
import sqlite3
import time
from typing import Any
from config import DATABASE_PATH, DEFAULT_NOTIFICATION_MODE

def get_conn():
    folder = os.path.dirname(DATABASE_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pets (
        user_id TEXT PRIMARY KEY,
        guild_id TEXT NOT NULL,
        thread_id TEXT,
        panel_message_id TEXT,
        character_id TEXT NOT NULL,
        stage TEXT NOT NULL,
        hunger INTEGER NOT NULL DEFAULT 20,
        mood INTEGER NOT NULL DEFAULT 70,
        sleepiness INTEGER NOT NULL DEFAULT 10,
        affection INTEGER NOT NULL DEFAULT 20,
        stress INTEGER NOT NULL DEFAULT 10,
        discipline INTEGER NOT NULL DEFAULT 0,
        poop INTEGER NOT NULL DEFAULT 0,
        is_sick INTEGER NOT NULL DEFAULT 0,
        call_flag INTEGER NOT NULL DEFAULT 0,
        age_seconds INTEGER NOT NULL DEFAULT 0,
        total_feed_count INTEGER NOT NULL DEFAULT 0,
        total_snack_count INTEGER NOT NULL DEFAULT 0,
        total_play_count INTEGER NOT NULL DEFAULT 0,
        total_sleep_count INTEGER NOT NULL DEFAULT 0,
        total_status_count INTEGER NOT NULL DEFAULT 0,
        total_clean_count INTEGER NOT NULL DEFAULT 0,
        total_medicine_count INTEGER NOT NULL DEFAULT 0,
        total_discipline_count INTEGER NOT NULL DEFAULT 0,
        total_minigame_count INTEGER NOT NULL DEFAULT 0,
        total_minigame_win_count INTEGER NOT NULL DEFAULT 0,
        care_miss_count INTEGER NOT NULL DEFAULT 0,
        night_visit_count INTEGER NOT NULL DEFAULT 0,
        odekake_active INTEGER NOT NULL DEFAULT 0,
        odekake_started_at INTEGER,
        notification_mode TEXT NOT NULL DEFAULT 'tamagotchi',
        birth_at INTEGER NOT NULL,
        stage_entered_at INTEGER NOT NULL,
        last_access_at INTEGER NOT NULL,
        last_minigame_at INTEGER NOT NULL DEFAULT 0,
        last_notified_hunger INTEGER NOT NULL DEFAULT 0,
        last_notified_sleepiness INTEGER NOT NULL DEFAULT 0,
        last_notified_poop INTEGER NOT NULL DEFAULT 0,
        last_notified_sick INTEGER NOT NULL DEFAULT 0,
        journeyed INTEGER NOT NULL DEFAULT 0
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS collection (
        user_id TEXT NOT NULL,
        character_id TEXT NOT NULL,
        obtained_at INTEGER NOT NULL,
        PRIMARY KEY (user_id, character_id)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS evolution_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        from_character_id TEXT NOT NULL,
        to_character_id TEXT NOT NULL,
        evolved_at INTEGER NOT NULL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        user_id TEXT PRIMARY KEY,
        sleep_start TEXT NOT NULL DEFAULT '00:00',
        sleep_end TEXT NOT NULL DEFAULT '07:00'
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

def fetch_pet(user_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM pets WHERE user_id = ?", (str(user_id),)).fetchone()
    conn.close()
    return row

def fetch_all_active_pets():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM pets WHERE journeyed = 0").fetchall()
    conn.close()
    return rows

def create_pet(user_id: int, guild_id: int, thread_id: int):
    now = int(time.time())
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO pets (
            user_id, guild_id, thread_id, character_id, stage, hunger, mood, sleepiness, affection,
            stress, discipline, poop, is_sick, call_flag, age_seconds, birth_at, stage_entered_at,
            last_access_at, notification_mode
        ) VALUES (?, ?, ?, 'egg_yuiran', 'egg', 20, 70, 10, 20, 10, 0, 0, 0, 0, 0, ?, ?, ?, ?)
    """, (str(user_id), str(guild_id), str(thread_id), now, now, now, DEFAULT_NOTIFICATION_MODE))
    conn.commit()
    conn.close()

def update_pet(user_id: int, **fields: Any):
    if not fields:
        return
    conn = get_conn()
    cols = ", ".join(f"{k} = ?" for k in fields.keys())
    values = list(fields.values()) + [str(user_id)]
    conn.execute(f"UPDATE pets SET {cols} WHERE user_id = ?", values)
    conn.commit()
    conn.close()

def delete_pet(user_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM pets WHERE user_id = ?", (str(user_id),))
    conn.commit()
    conn.close()

def save_collection(user_id: int, character_id: str):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO collection (user_id, character_id, obtained_at) VALUES (?, ?, ?)",
        (str(user_id), character_id, int(time.time())),
    )
    conn.commit()
    conn.close()

def fetch_collection(user_id: int):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM collection WHERE user_id = ? ORDER BY obtained_at ASC", (str(user_id),)).fetchall()
    conn.close()
    return rows

def add_evolution_log(user_id: int, from_character_id: str, to_character_id: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO evolution_log (user_id, from_character_id, to_character_id, evolved_at) VALUES (?, ?, ?, ?)",
        (str(user_id), from_character_id, to_character_id, int(time.time())),
    )
    conn.commit()
    conn.close()

def set_sleep_setting(user_id: int, start: str, end: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO settings (user_id, sleep_start, sleep_end) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET sleep_start=excluded.sleep_start, sleep_end=excluded.sleep_end",
        (str(user_id), start, end),
    )
    conn.commit()
    conn.close()

def fetch_sleep_setting(user_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM settings WHERE user_id = ?", (str(user_id),)).fetchone()
    conn.close()
    return row

def get_meta(key: str):
    conn = get_conn()
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None

def set_meta(key: str, value: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()
