from __future__ import annotations
import os, sqlite3, time
from typing import Any
from config import DATABASE_PATH
from game_data import CHARACTERS

PET_DATA_SCHEMA_VERSION = "2026-03-19d"
ALLOWED_NOTIFICATION_MODES = {"tamagotchi", "normal", "quiet", "mute"}

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
    cur.execute("CREATE TABLE IF NOT EXISTS settings (user_id TEXT PRIMARY KEY, sleep_start TEXT NOT NULL DEFAULT '22:00', sleep_end TEXT NOT NULL DEFAULT '07:00', clock_offset_minutes INTEGER NOT NULL DEFAULT 0)")
    cur.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.commit()
    existing = _existing_columns(cur)
    for col_name, col_def in MIGRATION_COLUMNS:
        if col_name not in existing:
            cur.execute(f"ALTER TABLE pets ADD COLUMN {col_name} {col_def}")
            conn.commit()
    existing_settings = {row[1] for row in cur.execute("PRAGMA table_info(settings)").fetchall()}
    for col_name, col_def in SETTINGS_MIGRATION_COLUMNS:
        if col_name not in existing_settings:
            cur.execute(f"ALTER TABLE settings ADD COLUMN {col_name} {col_def}")
            conn.commit()
    conn.close()


VALID_STAGES = {"egg", "baby1", "baby2", "child", "adult"}
REQUIRED_PET_FIELDS = ("guild_id", "character_id", "stage", "birth_at", "stage_entered_at", "last_access_at")
STAGE_DEFAULT_CHARACTER = {
    "egg": "egg_yuiran",
    "baby1": "baby_colon",
    "baby2": "baby_cororon",
    "child": "child_musubi",
    "adult": "adult_kanato",
}


def _is_blank(value) -> bool:
    return value is None or value == ""


def _coerce_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def repair_pet_row(user_id: int, row):
    if not row:
        return None
    now = int(time.time())
    updates: dict[str, Any] = {}
    character_id = row.get("character_id")
    stage = row.get("stage")

    if stage not in VALID_STAGES:
        stage = "egg"
        updates["stage"] = stage

    if character_id not in CHARACTERS:
        character_id = STAGE_DEFAULT_CHARACTER.get(stage, "egg_yuiran")
        updates["character_id"] = character_id

    expected_stage = CHARACTERS[character_id]["stage"]
    if stage != expected_stage:
        stage = expected_stage
        updates["stage"] = stage

    if _is_blank(row.get("guild_id")):
        updates["guild_id"] = str(row.get("guild_id") or "0")

    for key in ("birth_at", "stage_entered_at", "last_access_at"):
        if _is_blank(row.get(key)):
            updates[key] = now

    int_defaults = {
        "hunger": 4,
        "mood": 4,
        "sleepiness": 0,
        "affection": 20,
        "stress": 0,
        "discipline": 0,
        "poop": 0,
        "is_sick": 0,
        "call_flag": 0,
        "call_started_at": 0,
        "call_stage": 0,
        "is_whim_call": 0,
        "is_sleeping": 0,
        "lights_off": 0,
        "sound_enabled": 1,
        "weight": 10,
        "praise_pending": 0,
        "praise_due_at": 0,
        "good_behavior_pending": 0,
        "good_behavior_due_at": 0,
        "last_whim_at": 0,
        "last_call_notified_at": 0,
        "evolution_warned": 0,
        "last_random_event_at": 0,
        "age_seconds": 0,
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
        "care_miss_count": 0,
        "sickness_count": 0,
        "night_visit_count": 0,
        "odekake_active": 0,
        "journeyed": 0,
        "last_minigame_at": 0,
    }
    for key, default in int_defaults.items():
        value = row.get(key)
        if value is None:
            updates[key] = default

    for key in ("thread_id", "panel_message_id", "system_message_id", "alert_message_id"):
        value = row.get(key)
        if value in (None, ""):
            continue
        value_str = str(value).strip()
        if not value_str.isdigit():
            updates[key] = None

    if stage in ("egg", "adult") and _coerce_int(row.get("poop"), 0) != 0:
        updates["poop"] = 0
    if row.get("call_reason") == "poop" and stage in ("egg", "adult"):
        updates["call_reason"] = None
        updates["call_flag"] = 0
    if _coerce_int(row.get("odekake_active"), 0) and not row.get("odekake_started_at"):
        updates["odekake_active"] = 0
        updates["odekake_started_at"] = None
    if row.get("notification_mode") not in ALLOWED_NOTIFICATION_MODES:
        updates["notification_mode"] = "tamagotchi"

    if updates:
        update_pet(user_id, **updates)
        row = fetch_pet(user_id)
    return row


def is_pet_row_valid(row) -> bool:
    if not row:
        return False
    try:
        if row.get("journeyed"):
            return True
        if row.get("stage") not in VALID_STAGES:
            return False
        if row.get("character_id") not in CHARACTERS:
            return False
        for key in REQUIRED_PET_FIELDS:
            value = row.get(key)
            if value is None or value == "":
                return False
        return True
    except Exception:
        return False


def fetch_pet_clean(user_id: int):
    row, _ = run_save_checker_for_user(user_id)
    return row

def run_save_checker_for_user(user_id: int):
    stats = {"checked": 0, "repaired": 0, "collection_fixed": 0, "reset_to_egg": 0}
    row = fetch_pet(user_id)
    if not row:
        return None, stats
    stats["checked"] = 1
    before = dict(row)
    row = repair_pet_row(user_id, row)
    if not row:
        fallback = {
            "guild_id": str(before.get("guild_id") or "0"),
            "thread_id": before.get("thread_id"),
            "panel_message_id": before.get("panel_message_id"),
            "system_message_id": before.get("system_message_id"),
            "alert_message_id": before.get("alert_message_id"),
            "character_id": "egg_yuiran",
            "stage": "egg",
            "birth_at": int(time.time()),
            "stage_entered_at": int(time.time()),
            "last_access_at": int(time.time()),
        }
        update_pet(user_id, **fallback)
        row = fetch_pet(user_id)
        stats["reset_to_egg"] += 1
    elif row != before:
        stats["repaired"] += 1

    if row and not is_pet_row_valid(row):
        now = int(time.time())
        update_pet(
            user_id,
            character_id="egg_yuiran",
            stage="egg",
            birth_at=_coerce_int(row.get("birth_at"), now) or now,
            stage_entered_at=now,
            last_access_at=now,
            journeyed=0,
            poop=0,
            call_flag=0,
            call_reason=None,
            call_started_at=0,
            call_stage=0,
            is_whim_call=0,
            is_sick=0,
            odekake_active=0,
            odekake_started_at=None,
        )
        row = fetch_pet(user_id)
        stats["reset_to_egg"] += 1

    if row and row.get("journeyed") and str(row.get("character_id", "")).startswith(("adult_", "secret_")):
        before_count = len(fetch_collection(user_id))
        save_collection(user_id, row["character_id"])
        after_count = len(fetch_collection(user_id))
        if after_count > before_count:
            stats["collection_fixed"] += 1
            row = fetch_pet(user_id) or row
    return row, stats

def fetch_pet(user_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM pets WHERE user_id = ?", (str(user_id),)).fetchone()
    conn.close()
    return dict(row) if row else None

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


def restart_pet_cycle(user_id: int, *, thread_id: int | None = None):
    row = fetch_pet(user_id)
    if not row:
        return None
    guild_id = row.get("guild_id") or "0"
    target_thread_id = thread_id if thread_id is not None else row.get("thread_id") or 0
    create_pet(int(user_id), int(guild_id), int(target_thread_id))
    return fetch_pet(user_id)

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
        "INSERT INTO settings (user_id, sleep_start, sleep_end, clock_offset_minutes) VALUES (?, ?, ?, COALESCE((SELECT clock_offset_minutes FROM settings WHERE user_id = ?), 0)) ON CONFLICT(user_id) DO UPDATE SET sleep_start=excluded.sleep_start, sleep_end=excluded.sleep_end",
        (str(user_id), start, end, str(user_id)),
    )
    conn.commit()
    conn.close()

def fetch_sleep_setting(user_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM settings WHERE user_id = ?", (str(user_id),)).fetchone()
    conn.close()
    return dict(row) if row else None

def fetch_user_settings(user_id: int):
    return fetch_sleep_setting(user_id)

def set_clock_offset_minutes(user_id: int, minutes: int):
    conn = get_conn()
    conn.execute("INSERT INTO settings (user_id, sleep_start, sleep_end, clock_offset_minutes) VALUES (?, '22:00', '07:00', ?) ON CONFLICT(user_id) DO UPDATE SET clock_offset_minutes=excluded.clock_offset_minutes", (str(user_id), int(minutes)))
    conn.commit()
    conn.close()

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


def list_pet_user_ids(*, active_only: bool = False):
    conn = get_conn()
    if active_only:
        rows = conn.execute("SELECT user_id FROM pets WHERE journeyed = 0 ORDER BY user_id ASC").fetchall()
    else:
        rows = conn.execute("SELECT user_id FROM pets ORDER BY user_id ASC").fetchall()
    conn.close()
    result = []
    for row in rows:
        try:
            result.append(int(row["user_id"]))
        except Exception:
            continue
    return result


def migrate_all_pets_to_latest(*, active_only: bool = False):
    stats = {"total": 0, "updated": 0, "deleted": 0, "kept": 0, "collection_fixed": 0, "reset_to_egg": 0}
    for user_id in list_pet_user_ids(active_only=active_only):
        row, row_stats = run_save_checker_for_user(user_id)
        if row_stats["checked"] == 0:
            continue
        stats["total"] += 1
        if row_stats["repaired"]:
            stats["updated"] += 1
        elif row_stats["reset_to_egg"]:
            stats["updated"] += 1
        else:
            stats["kept"] += 1
        stats["collection_fixed"] += row_stats["collection_fixed"]
        stats["reset_to_egg"] += row_stats["reset_to_egg"]
    return stats


def ensure_pet_schema_latest(*, force: bool = False):
    current = get_meta("pet_schema_version")
    if (not force) and current == PET_DATA_SCHEMA_VERSION:
        return {"skipped": 1, "version": PET_DATA_SCHEMA_VERSION, "total": 0, "updated": 0, "deleted": 0, "kept": 0, "collection_fixed": 0, "reset_to_egg": 0}
    stats = migrate_all_pets_to_latest(active_only=False)
    set_meta("pet_schema_version", PET_DATA_SCHEMA_VERSION)
    stats["version"] = PET_DATA_SCHEMA_VERSION
    stats["skipped"] = 0
    return stats


SETTINGS_MIGRATION_COLUMNS = [("clock_offset_minutes", "INTEGER NOT NULL DEFAULT 0")]
