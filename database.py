from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any

DB_PATH = os.getenv('YUITCHI_DB_PATH', str(Path(__file__).with_name('yuitchi.db')))

PET_COLUMNS = {
    'user_id': 'INTEGER PRIMARY KEY',
    'guild_id': 'INTEGER DEFAULT 0',
    'channel_id': 'INTEGER DEFAULT 0',
    'thread_id': 'TEXT DEFAULT ""',
    'panel_message_id': 'TEXT DEFAULT ""',
    'alert_message_id': 'TEXT DEFAULT ""',
    'system_message_id': 'TEXT DEFAULT ""',
    'character_id': 'TEXT DEFAULT "egg_yuiran"',
    'stage': 'TEXT DEFAULT "egg"',
    'stage_entered_at': 'INTEGER DEFAULT 0',
    'last_access_at': 'INTEGER DEFAULT 0',
    'age_seconds': 'INTEGER DEFAULT 0',
    'hunger': 'INTEGER DEFAULT 4',
    'mood': 'INTEGER DEFAULT 4',
    'sleepiness': 'INTEGER DEFAULT 0',
    'stress': 'INTEGER DEFAULT 0',
    'affection': 'INTEGER DEFAULT 20',
    'weight': 'INTEGER DEFAULT 10',
    'discipline': 'INTEGER DEFAULT 0',
    'care_miss_count': 'INTEGER DEFAULT 0',
    'poop': 'INTEGER DEFAULT 0',
    'is_sick': 'INTEGER DEFAULT 0',
    'is_sleeping': 'INTEGER DEFAULT 0',
    'lights_off': 'INTEGER DEFAULT 0',
    'is_whim_call': 'INTEGER DEFAULT 0',
    'call_flag': 'INTEGER DEFAULT 0',
    'call_reason': 'TEXT DEFAULT ""',
    'call_started_at': 'INTEGER DEFAULT 0',
    'call_stage': 'INTEGER DEFAULT 0',
    'last_call_notified_at': 'INTEGER DEFAULT 0',
    'journeyed': 'INTEGER DEFAULT 0',
    'odekake_active': 'INTEGER DEFAULT 0',
    'odekake_started_at': 'INTEGER DEFAULT 0',
    'total_feed_count': 'INTEGER DEFAULT 0',
    'total_snack_count': 'INTEGER DEFAULT 0',
    'total_play_count': 'INTEGER DEFAULT 0',
    'total_status_count': 'INTEGER DEFAULT 0',
    'total_sleep_count': 'INTEGER DEFAULT 0',
    'total_clean_count': 'INTEGER DEFAULT 0',
    'total_discipline_count': 'INTEGER DEFAULT 0',
    'total_praise_count': 'INTEGER DEFAULT 0',
    'total_minigame_count': 'INTEGER DEFAULT 0',
    'total_minigame_win_count': 'INTEGER DEFAULT 0',
    'total_medicine_count': 'INTEGER DEFAULT 0',
    'night_visit_count': 'INTEGER DEFAULT 0',
    'sickness_count': 'INTEGER DEFAULT 0',
    'praise_pending': 'INTEGER DEFAULT 0',
    'praise_due_at': 'INTEGER DEFAULT 0',
    'good_behavior_pending': 'INTEGER DEFAULT 0',
    'good_behavior_due_at': 'INTEGER DEFAULT 0',
    'notification_mode': 'TEXT DEFAULT "normal"',
    'sound_enabled': 'INTEGER DEFAULT 1',
}

SETTING_COLUMNS = {
    'user_id': 'INTEGER PRIMARY KEY',
    'clock_offset_minutes': 'INTEGER DEFAULT 0',
    'sleep_start': 'TEXT DEFAULT "22:00"',
    'sleep_end': 'TEXT DEFAULT "07:00"',
}


def _dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = _dict_factory
    return conn


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {r['name'] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')


def init_db() -> None:
    conn = get_conn()
    conn.execute(
        'CREATE TABLE IF NOT EXISTS pets ('
        + ', '.join(f'{k} {v}' for k, v in PET_COLUMNS.items())
        + ')'
    )
    conn.execute(
        'CREATE TABLE IF NOT EXISTS user_settings ('
        + ', '.join(f'{k} {v}' for k, v in SETTING_COLUMNS.items())
        + ')'
    )
    conn.execute(
        'CREATE TABLE IF NOT EXISTS collection ('
        'user_id INTEGER NOT NULL, '
        'character_id TEXT NOT NULL, '
        'first_obtained_at INTEGER NOT NULL, '
        'PRIMARY KEY(user_id, character_id))'
    )
    conn.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    _ensure_columns(conn, 'pets', PET_COLUMNS)
    _ensure_columns(conn, 'user_settings', SETTING_COLUMNS)
    conn.commit()
    conn.close()


def ensure_user_settings(user_id: int) -> None:
    conn = get_conn()
    conn.execute('INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()


def fetch_user_settings(user_id: int) -> dict[str, Any]:
    ensure_user_settings(user_id)
    conn = get_conn()
    row = conn.execute('SELECT * FROM user_settings WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return row or {'user_id': user_id, 'clock_offset_minutes': 0, 'sleep_start': '22:00', 'sleep_end': '07:00'}


def update_user_settings(user_id: int, **kwargs: Any) -> None:
    if not kwargs:
        return
    ensure_user_settings(user_id)
    conn = get_conn()
    parts = ', '.join(f'{k} = ?' for k in kwargs)
    values = list(kwargs.values()) + [user_id]
    conn.execute(f'UPDATE user_settings SET {parts} WHERE user_id = ?', values)
    conn.commit()
    conn.close()


def default_pet_values(user_id: int, guild_id: int = 0, channel_id: int = 0) -> dict[str, Any]:
    now = int(time.time())
    return {
        'user_id': user_id,
        'guild_id': guild_id,
        'channel_id': channel_id,
        'character_id': 'egg_yuiran',
        'stage': 'egg',
        'stage_entered_at': now,
        'last_access_at': now,
        'hunger': 4,
        'mood': 4,
        'sleepiness': 0,
        'stress': 0,
        'affection': 20,
        'weight': 10,
        'discipline': 0,
        'care_miss_count': 0,
        'poop': 0,
        'is_sick': 0,
        'is_sleeping': 0,
        'lights_off': 0,
        'is_whim_call': 0,
        'call_flag': 0,
        'call_reason': '',
        'call_started_at': 0,
        'call_stage': 0,
        'last_call_notified_at': 0,
        'journeyed': 0,
        'odekake_active': 0,
        'odekake_started_at': 0,
        'notification_mode': 'normal',
        'sound_enabled': 1,
    }


def create_pet(user_id: int, guild_id: int = 0, channel_id: int = 0, **overrides: Any) -> None:
    init_db()
    values = default_pet_values(user_id, guild_id, channel_id)
    values.update(overrides)
    conn = get_conn()
    keys = ', '.join(values.keys())
    placeholders = ', '.join('?' for _ in values)
    conn.execute(f'INSERT OR REPLACE INTO pets ({keys}) VALUES ({placeholders})', list(values.values()))
    conn.commit()
    conn.close()


def fetch_pet(user_id: int) -> dict[str, Any] | None:
    init_db()
    conn = get_conn()
    row = conn.execute('SELECT * FROM pets WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return row


def update_pet(user_id: int, **kwargs: Any) -> None:
    if not kwargs:
        return
    init_db()
    conn = get_conn()
    parts = ', '.join(f'{k} = ?' for k in kwargs)
    values = list(kwargs.values()) + [user_id]
    conn.execute(f'UPDATE pets SET {parts} WHERE user_id = ?', values)
    conn.commit()
    conn.close()


def delete_pet(user_id: int) -> None:
    conn = get_conn()
    conn.execute('DELETE FROM pets WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()


def reset_all_user_data(user_id: int) -> None:
    conn = get_conn()
    conn.execute('DELETE FROM pets WHERE user_id = ?', (user_id,))
    conn.execute('DELETE FROM collection WHERE user_id = ?', (user_id,))
    conn.execute('DELETE FROM user_settings WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()


def save_collection(user_id: int, character_id: str) -> None:
    conn = get_conn()
    conn.execute(
        'INSERT OR IGNORE INTO collection (user_id, character_id, first_obtained_at) VALUES (?, ?, ?)',
        (user_id, character_id, int(time.time())),
    )
    conn.commit()
    conn.close()


def fetch_collection(user_id: int) -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        'SELECT * FROM collection WHERE user_id = ? ORDER BY first_obtained_at ASC',
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


def get_meta(key: str) -> str | None:
    conn = get_conn()
    row = conn.execute('SELECT value FROM meta WHERE key = ?', (key,)).fetchone()
    conn.close()
    return row['value'] if row else None


def set_meta(key: str, value: str) -> None:
    conn = get_conn()
    conn.execute('INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()


def list_active_user_ids() -> list[int]:
    conn = get_conn()
    rows = conn.execute('SELECT user_id FROM pets WHERE journeyed = 0').fetchall()
    conn.close()
    return [int(r['user_id']) for r in rows]
