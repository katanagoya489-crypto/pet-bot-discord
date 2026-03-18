from __future__ import annotations

import os
import sqlite3
import time
from typing import Any, Dict, Iterable, Optional

DB_PATH = os.getenv("YUITCHI_DB_PATH", "yuitchi_overhaul_v1.sqlite3")

PET_COLUMNS = {
    "user_id": "TEXT PRIMARY KEY",
    "guild_id": "TEXT",
    "thread_id": "TEXT",
    "panel_message_id": "TEXT",
    "system_message_id": "TEXT",
    "alert_message_id": "TEXT",
    "character_id": "TEXT NOT NULL DEFAULT 'egg_yuiran'",
    "stage": "TEXT NOT NULL DEFAULT 'egg'",
    "birth_at": "INTEGER NOT NULL DEFAULT 0",
    "stage_started_at": "INTEGER NOT NULL DEFAULT 0",
    "last_updated_at": "INTEGER NOT NULL DEFAULT 0",
    "journeyed": "INTEGER NOT NULL DEFAULT 0",
    "journey_at": "INTEGER NOT NULL DEFAULT 0",
    "hunger": "INTEGER NOT NULL DEFAULT 4",
    "mood": "INTEGER NOT NULL DEFAULT 4",
    "sleepiness": "INTEGER NOT NULL DEFAULT 0",
    "affection": "INTEGER NOT NULL DEFAULT 0",
    "stress": "INTEGER NOT NULL DEFAULT 0",
    "discipline": "INTEGER NOT NULL DEFAULT 0",
    "poop": "INTEGER NOT NULL DEFAULT 0",
    "is_sick": "INTEGER NOT NULL DEFAULT 0",
    "call_flag": "INTEGER NOT NULL DEFAULT 0",
    "call_reason": "TEXT NOT NULL DEFAULT ''",
    "call_started_at": "INTEGER NOT NULL DEFAULT 0",
    "call_stage": "INTEGER NOT NULL DEFAULT 0",
    "is_whim_call": "INTEGER NOT NULL DEFAULT 0",
    "is_sleeping": "INTEGER NOT NULL DEFAULT 0",
    "lights_off": "INTEGER NOT NULL DEFAULT 0",
    "notification_mode": "TEXT NOT NULL DEFAULT 'normal'",
    "sound_enabled": "INTEGER NOT NULL DEFAULT 1",
    "weight": "INTEGER NOT NULL DEFAULT 10",
    "care_miss_count": "INTEGER NOT NULL DEFAULT 0",
    "last_call_notified_at": "INTEGER NOT NULL DEFAULT 0",
    "last_random_event_at": "INTEGER NOT NULL DEFAULT 0",
    "away_mode": "INTEGER NOT NULL DEFAULT 0",
    "away_started_at": "INTEGER NOT NULL DEFAULT 0",
    "total_feed_count": "INTEGER NOT NULL DEFAULT 0",
    "total_snack_count": "INTEGER NOT NULL DEFAULT 0",
    "total_play_count": "INTEGER NOT NULL DEFAULT 0",
    "total_sleep_count": "INTEGER NOT NULL DEFAULT 0",
    "total_status_count": "INTEGER NOT NULL DEFAULT 0",
    "total_clean_count": "INTEGER NOT NULL DEFAULT 0",
    "total_medicine_count": "INTEGER NOT NULL DEFAULT 0",
    "total_discipline_count": "INTEGER NOT NULL DEFAULT 0",
    "total_praise_count": "INTEGER NOT NULL DEFAULT 0",
    "total_minigame_count": "INTEGER NOT NULL DEFAULT 0",
    "total_minigame_win_count": "INTEGER NOT NULL DEFAULT 0",
    "night_activity_count": "INTEGER NOT NULL DEFAULT 0",
}

USER_SETTING_COLUMNS = {
    "user_id": "TEXT PRIMARY KEY",
    "clock_offset_minutes": "INTEGER NOT NULL DEFAULT 0",
    "sleep_start": "TEXT NOT NULL DEFAULT '22:00'",
    "sleep_end": "TEXT NOT NULL DEFAULT '07:00'",
}

COLLECTION_COLUMNS = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "user_id": "TEXT NOT NULL",
    "character_id": "TEXT NOT NULL",
    "obtained_at": "INTEGER NOT NULL",
}

META_COLUMNS = {
    "key": "TEXT PRIMARY KEY",
    "value": "TEXT NOT NULL",
}


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table(conn: sqlite3.Connection, table: str, columns: Dict[str, str]) -> None:
    col_sql = ", ".join(f"{name} {spec}" for name, spec in columns.items())
    conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({col_sql})")
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, spec in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {spec}")


def init_db() -> None:
    conn = get_conn()
    _ensure_table(conn, "pets", PET_COLUMNS)
    _ensure_table(conn, "user_settings", USER_SETTING_COLUMNS)
    _ensure_table(conn, "collection", COLLECTION_COLUMNS)
    _ensure_table(conn, "meta", META_COLUMNS)
    conn.commit()
    conn.close()


init_db()


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return dict(row)


def now_ts() -> int:
    return int(time.time())


def fetch_pet(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM pets WHERE user_id = ?", (str(user_id),)).fetchone()
    conn.close()
    return row_to_dict(row)


def upsert_pet(data: Dict[str, Any]) -> None:
    conn = get_conn()
    keys = list(data.keys())
    placeholders = ", ".join("?" for _ in keys)
    updates = ", ".join(f"{k}=excluded.{k}" for k in keys if k != "user_id")
    conn.execute(
        f"INSERT INTO pets ({', '.join(keys)}) VALUES ({placeholders}) "
        f"ON CONFLICT(user_id) DO UPDATE SET {updates}",
        tuple(data[k] for k in keys),
    )
    conn.commit()
    conn.close()


def update_pet(user_id: int, **fields: Any) -> None:
    if not fields:
        return
    conn = get_conn()
    assigns = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [str(user_id)]
    conn.execute(f"UPDATE pets SET {assigns} WHERE user_id = ?", values)
    conn.commit()
    conn.close()


def create_new_pet(user_id: int, guild_id: int, thread_id: int = 0) -> Dict[str, Any]:
    now = now_ts()
    data: Dict[str, Any] = {
        "user_id": str(user_id),
        "guild_id": str(guild_id),
        "thread_id": str(thread_id) if thread_id else "",
        "panel_message_id": "",
        "system_message_id": "",
        "alert_message_id": "",
        "character_id": "egg_yuiran",
        "stage": "egg",
        "birth_at": now,
        "stage_started_at": now,
        "last_updated_at": now,
        "journeyed": 0,
        "journey_at": 0,
        "hunger": 4,
        "mood": 4,
        "sleepiness": 0,
        "affection": 0,
        "stress": 0,
        "discipline": 0,
        "poop": 0,
        "is_sick": 0,
        "call_flag": 0,
        "call_reason": "",
        "call_started_at": 0,
        "call_stage": 0,
        "is_whim_call": 0,
        "is_sleeping": 0,
        "lights_off": 0,
        "notification_mode": "normal",
        "sound_enabled": 1,
        "weight": 10,
        "care_miss_count": 0,
        "last_call_notified_at": 0,
        "last_random_event_at": 0,
        "away_mode": 0,
        "away_started_at": 0,
        "total_feed_count": 0,
        "total_snack_count": 0,
        "total_play_count": 0,
        "total_sleep_count": 0,
        "total_status_count": 0,
        "total_clean_count": 0,
        "total_medicine_count": 0,
        "total_discipline_count": 0,
        "total_praise_count": 0,
        "total_minigame_count": 0,
        "total_minigame_win_count": 0,
        "night_activity_count": 0,
    }
    upsert_pet(data)
    return fetch_pet(user_id) or data


def delete_pet(user_id: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM pets WHERE user_id = ?", (str(user_id),))
    conn.commit()
    conn.close()


def delete_all_user_data(user_id: int) -> None:
    conn = get_conn()
    uid = str(user_id)
    conn.execute("DELETE FROM pets WHERE user_id = ?", (uid,))
    conn.execute("DELETE FROM collection WHERE user_id = ?", (uid,))
    conn.execute("DELETE FROM user_settings WHERE user_id = ?", (uid,))
    conn.commit()
    conn.close()


def fetch_user_settings(user_id: int) -> Dict[str, Any]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM user_settings WHERE user_id = ?", (str(user_id),)).fetchone()
    if row is None:
        conn.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (str(user_id),))
        conn.commit()
        row = conn.execute("SELECT * FROM user_settings WHERE user_id = ?", (str(user_id),)).fetchone()
    conn.close()
    return row_to_dict(row) or {"user_id": str(user_id), "clock_offset_minutes": 0, "sleep_start": "22:00", "sleep_end": "07:00"}


def set_user_setting(user_id: int, **fields: Any) -> None:
    fetch_user_settings(user_id)
    if not fields:
        return
    conn = get_conn()
    assigns = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [str(user_id)]
    conn.execute(f"UPDATE user_settings SET {assigns} WHERE user_id = ?", values)
    conn.commit()
    conn.close()


def set_sleep_setting(user_id: int, sleep_start: str, sleep_end: str) -> None:
    set_user_setting(user_id, sleep_start=sleep_start, sleep_end=sleep_end)


def add_collection_entry(user_id: int, character_id: str) -> None:
    conn = get_conn()
    uid = str(user_id)
    exists = conn.execute(
        "SELECT 1 FROM collection WHERE user_id = ? AND character_id = ? LIMIT 1",
        (uid, character_id),
    ).fetchone()
    if not exists:
        conn.execute(
            "INSERT INTO collection (user_id, character_id, obtained_at) VALUES (?, ?, ?)",
            (uid, character_id, now_ts()),
        )
        conn.commit()
    conn.close()


def fetch_collection(user_id: int) -> list[Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM collection WHERE user_id = ? ORDER BY obtained_at ASC, id ASC",
        (str(user_id),),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_active_pet_user_ids() -> list[int]:
    conn = get_conn()
    rows = conn.execute("SELECT user_id FROM pets WHERE journeyed = 0").fetchall()
    conn.close()
    out: list[int] = []
    for row in rows:
        try:
            out.append(int(row["user_id"]))
        except Exception:
            continue
    return out


def set_meta(key: str, value: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_meta(key: str) -> Optional[str]:
    conn = get_conn()
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None
