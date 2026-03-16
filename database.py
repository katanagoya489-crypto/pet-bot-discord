from __future__ import annotations
import os, sqlite3, time
from typing import Any
from config import DATABASE_PATH

BASE_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS pets (
    user_id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    thread_id TEXT,
    panel_message_id TEXT,
    system_message_id TEXT,
    alert_message_id TEXT,
    character_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    hunger INTEGER NOT NULL DEFAULT 4,
    mood INTEGER NOT NULL DEFAULT 4,
    sleepiness INTEGER NOT NULL DEFAULT 0,
    affection INTEGER NOT NULL DEFAULT 20,
    stress INTEGER NOT NULL DEFAULT 0,
    discipline INTEGER NOT NULL DEFAULT 0,
    poop INTEGER NOT NULL DEFAULT 0,
    is_sick INTEGER NOT NULL DEFAULT 0,
    call_flag INTEGER NOT NULL DEFAULT 0,
    call_reason TEXT,
    call_started_at INTEGER NOT NULL DEFAULT 0,
    call_stage INTEGER NOT NULL DEFAULT 0,
    is_whim_call INTEGER NOT NULL DEFAULT 0,
    is_sleeping INTEGER NOT NULL DEFAULT 0,
    lights_off INTEGER NOT NULL DEFAULT 0,
    sound_enabled INTEGER NOT NULL DEFAULT 1,
    weight INTEGER NOT NULL DEFAULT 10,
    praise_pending INTEGER NOT NULL DEFAULT 0,
    praise_due_at INTEGER NOT NULL DEFAULT 0,
    good_behavior_pending INTEGER NOT NULL DEFAULT 0,
    good_behavior_due_at INTEGER NOT NULL DEFAULT 0,
    last_whim_at INTEGER NOT NULL DEFAULT 0,
    last_call_notified_at INTEGER NOT NULL DEFAULT 0,
    evolution_warned INTEGER NOT NULL DEFAULT 0,
    last_random_event_at INTEGER NOT NULL DEFAULT 0,
    age_seconds INTEGER NOT NULL DEFAULT 0,
    total_feed_count INTEGER NOT NULL DEFAULT 0,
    total_snack_count INTEGER NOT NULL DEFAULT 0,
    total_play_count INTEGER NOT NULL DEFAULT 0,
    total_sleep_count INTEGER NOT NULL DEFAULT 0,
    total_status_count INTEGER NOT NULL DEFAULT 0,
    total_clean_count INTEGER NOT NULL DEFAULT 0,
    total_medicine_count INTEGER NOT NULL DEFAULT 0,
    total_discipline_count INTEGER NOT NULL DEFAULT 0,
    total_praise_count INTEGER NOT NULL DEFAULT 0,
    total_minigame_count INTEGER NOT NULL DEFAULT 0,
    total_minigame_win_count INTEGER NOT NULL DEFAULT 0,
    care_miss_count INTEGER NOT NULL DEFAULT 0,
    sickness_count INTEGER NOT NULL DEFAULT 0,
    night_visit_count INTEGER NOT NULL DEFAULT 0,
    odekake_active INTEGER NOT NULL DEFAULT 0,
    odekake_started_at INTEGER,
    notification_mode TEXT NOT NULL DEFAULT 'tamagotchi',
    birth_at INTEGER NOT NULL,
    stage_entered_at INTEGER NOT NULL,
    last_access_at INTEGER NOT NULL,
    last_minigame_at INTEGER NOT NULL DEFAULT 0,
    journeyed INTEGER NOT NULL DEFAULT 0
)
"""
MIGRATION_COLUMNS = [
    ("panel_message_id", "TEXT"), ("system_message_id", "TEXT"), ("alert_message_id", "TEXT"),
    ("notification_mode", "TEXT NOT NULL DEFAULT 'tamagotchi'"), ("call_reason", "TEXT"),
    ("call_started_at", "INTEGER NOT NULL DEFAULT 0"), ("call_stage", "INTEGER NOT NULL DEFAULT 0"),
    ("is_whim_call", "INTEGER NOT NULL DEFAULT 0"), ("is_sleeping", "INTEGER NOT NULL DEFAULT 0"),
    ("lights_off", "INTEGER NOT NULL DEFAULT 0"), ("sound_enabled", "INTEGER NOT NULL DEFAULT 1"),
    ("weight", "INTEGER NOT NULL DEFAULT 10"), ("last_whim_at", "INTEGER NOT NULL DEFAULT 0"),
    ("last_call_notified_at", "INTEGER NOT NULL DEFAULT 0"), ("evolution_warned", "INTEGER NOT NULL DEFAULT 0"),
    ("last_random_event_at", "INTEGER NOT NULL DEFAULT 0"), ("sickness_count", "INTEGER NOT NULL DEFAULT 0"), ("total_praise_count", "INTEGER NOT NULL DEFAULT 0"),
]

def get_conn():
    folder = os.path.dirname(DATABASE_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _existing_columns(cur) -> set[str]:
    rows = cur.execute("PRAGMA table_info(pets)").fetchall()
    return {row[1] for row in rows}

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(BASE_CREATE_SQL)
    cur.execute("CREATE TABLE IF NOT EXISTS collection (user_id TEXT NOT NULL, character_id TEXT NOT NULL, obtained_at INTEGER NOT NULL, PRIMARY KEY (user_id, character_id))")
    cur.execute("CREATE TABLE IF NOT EXISTS evolution_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, from_character_id TEXT NOT NULL, to_character_id TEXT NOT NULL, evolved_at INTEGER NOT NULL)")
    cur.execute("CREATE TABLE IF NOT EXISTS settings (user_id TEXT PRIMARY KEY, sleep_start TEXT NOT NULL DEFAULT '22:00', sleep_end TEXT NOT NULL DEFAULT '07:00')")
    cur.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.commit()
    existing = _existing_columns(cur)
    for col_name, col_def in MIGRATION_COLUMNS:
        if col_name not in existing:
            cur.execute(f"ALTER TABLE pets ADD COLUMN {col_name} {col_def}")
            conn.commit()
    conn.close()

def fetch_pet(user_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM pets WHERE user_id = ?", (str(user_id),)).fetchone()
    conn.close()
    return row

def create_pet(user_id: int, guild_id: int, thread_id: int):
    now = int(time.time())
    conn = get_conn()
    conn.execute("""
    INSERT OR REPLACE INTO pets (
        user_id, guild_id, thread_id, panel_message_id, system_message_id, alert_message_id, character_id, stage,
        hunger, mood, sleepiness, affection, stress, discipline, poop, is_sick, call_flag, call_reason, call_started_at, call_stage,
        is_whim_call, is_sleeping, lights_off, sound_enabled, weight, praise_pending, praise_due_at, good_behavior_pending, good_behavior_due_at, last_whim_at, last_call_notified_at,
        evolution_warned, last_random_event_at, age_seconds, total_feed_count, total_snack_count, total_play_count,
        total_sleep_count, total_status_count, total_clean_count, total_medicine_count, total_discipline_count, total_praise_count,
        total_minigame_count, total_minigame_win_count, care_miss_count, sickness_count, night_visit_count,
        odekake_active, odekake_started_at, notification_mode, birth_at, stage_entered_at, last_access_at,
        last_minigame_at, journeyed
    ) VALUES (?, ?, ?, NULL, NULL, NULL, 'egg_yuiran', 'egg',
        4, 4, 0, 20, 0, 0, 0, 0, 0, NULL, 0, 0,
        0, 0, 0, 1, 10, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0,
        0, 0, 0, 0, 0,
        0, NULL, 'tamagotchi', ?, ?, ?, 0, 0
    )
    """, (str(user_id), str(guild_id), str(thread_id), now, now, now))
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
    conn.execute("INSERT OR IGNORE INTO collection (user_id, character_id, obtained_at) VALUES (?, ?, ?)", (str(user_id), character_id, int(time.time())))
    conn.commit()
    conn.close()

def fetch_collection(user_id: int):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM collection WHERE user_id = ? ORDER BY obtained_at ASC", (str(user_id),)).fetchall()
    conn.close()
    return rows

def add_evolution_log(user_id: int, from_character_id: str, to_character_id: str):
    conn = get_conn()
    conn.execute("INSERT INTO evolution_log (user_id, from_character_id, to_character_id, evolved_at) VALUES (?, ?, ?, ?)", (str(user_id), from_character_id, to_character_id, int(time.time())))
    conn.commit()
    conn.close()

def set_sleep_setting(user_id: int, start: str, end: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO settings (user_id, sleep_start, sleep_end) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET sleep_start=excluded.sleep_start, sleep_end=excluded.sleep_end",
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
    conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit()
    conn.close()


def delete_collection(user_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM collection WHERE user_id = ?", (str(user_id),))
    conn.commit()
    conn.close()

def delete_all_user_data(user_id: int):
    conn = get_conn()
    uid = str(user_id)
    conn.execute("DELETE FROM pets WHERE user_id = ?", (uid,))
    conn.execute("DELETE FROM collection WHERE user_id = ?", (uid,))
    conn.execute("DELETE FROM settings WHERE user_id = ?", (uid,))
    conn.execute("DELETE FROM evolution_log WHERE user_id = ?", (uid,))
    conn.commit()
    conn.close()
