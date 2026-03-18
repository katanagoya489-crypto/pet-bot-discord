from __future__ import annotations

import random
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, Iterable, Optional

import database
from game_data import (
    ADULT_EVOLUTION_RULES,
    CHARACTERS,
    DEX_TARGETS,
    EGG_IMAGE_KEYS,
    IMAGE_STATE_SUFFIXES,
    JOURNEY_MAX_SECONDS,
    JOURNEY_MIN_SECONDS,
    MINIGAME_COOLDOWN_SECONDS,
    MUSIC_GAMES,
    NOTIFICATION_REASON_TEXT,
    STAGE_SECONDS,
)

try:
    from config import SLEEP_START, SLEEP_END  # type: ignore
except Exception:
    SLEEP_START = "22:00"
    SLEEP_END = "07:00"

JST = ZoneInfo("Asia/Tokyo")


def clamp(n: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(n)))


def clamp_meter(n: int) -> int:
    return max(0, min(4, int(n)))


def bar(v: int, full: str = "♥", empty: str = "♡") -> str:
    v = clamp_meter(v)
    return full * v + empty * (4 - v)


def pet_name(row: Dict[str, Any]) -> str:
    return CHARACTERS.get(row.get("character_id", "egg_yuiran"), CHARACTERS["egg_yuiran"])["name"]


def current_stage_for_character(character_id: str) -> str:
    return CHARACTERS.get(character_id, CHARACTERS["egg_yuiran"])["stage"]


def is_egg(row: Dict[str, Any]) -> bool:
    return current_stage_for_character(row.get("character_id", "")) == "egg"


def is_adult(row: Dict[str, Any]) -> bool:
    return current_stage_for_character(row.get("character_id", "")) == "adult"


def poop_enabled(row: Dict[str, Any]) -> bool:
    stage = current_stage_for_character(row.get("character_id", ""))
    return stage in {"baby1", "baby2", "child"}


def normalize_hhmm(value: str) -> str:
    raw = (value or "").strip()
    hh, mm = raw.split(":")
    h = int(hh)
    m = int(mm)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("invalid time")
    return f"{h:02d}:{m:02d}"


def parse_hhmm(value: str) -> tuple[int, int]:
    normalized = normalize_hhmm(value)
    hh, mm = normalized.split(":")
    return int(hh), int(mm)


def now_jst() -> datetime:
    return datetime.now(JST)


def get_user_now(user_id: int) -> datetime:
    setting = database.fetch_user_settings(user_id)
    offset = int(setting.get("clock_offset_minutes", 0) or 0)
    return now_jst() + timedelta(minutes=offset)


def current_time_label(user_id: Optional[int] = None) -> str:
    dt = get_user_now(user_id) if user_id is not None else now_jst()
    return dt.strftime("%H:%M")


def is_in_sleep_window(user_id: int, dt: Optional[datetime] = None) -> bool:
    setting = database.fetch_user_settings(user_id)
    start = setting.get("sleep_start", SLEEP_START)
    end = setting.get("sleep_end", SLEEP_END)
    dt = dt or get_user_now(user_id)
    sh, sm = parse_hhmm(start)
    eh, em = parse_hhmm(end)
    current = dt.hour * 60 + dt.minute
    start_m = sh * 60 + sm
    end_m = eh * 60 + em
    if start_m <= end_m:
        return start_m <= current < end_m
    return current >= start_m or current < end_m


def adjust_display_clock(user_id: int, minutes: int) -> None:
    setting = database.fetch_user_settings(user_id)
    current = int(setting.get("clock_offset_minutes", 0) or 0)
    database.set_user_setting(user_id, clock_offset_minutes=current + minutes)


def reset_display_clock(user_id: int) -> None:
    database.set_user_setting(user_id, clock_offset_minutes=0)


def set_display_clock_to_hhmm(user_id: int, hhmm: str) -> None:
    target = normalize_hhmm(hhmm)
    th, tm = parse_hhmm(target)
    now_real = now_jst()
    target_minutes = th * 60 + tm
    real_minutes = now_real.hour * 60 + now_real.minute
    delta = target_minutes - real_minutes
    database.set_user_setting(user_id, clock_offset_minutes=delta)


def validate_pet_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    try:
        row = dict(row)
        if row.get("character_id") not in CHARACTERS:
            return None
        stage = current_stage_for_character(row.get("character_id", ""))
        row["stage"] = stage
        numeric_defaults = {
            "hunger": 4, "mood": 4, "sleepiness": 0, "affection": 0, "stress": 0, "discipline": 0,
            "poop": 0, "is_sick": 0, "call_flag": 0, "call_started_at": 0, "call_stage": 0,
            "is_whim_call": 0, "is_sleeping": 0, "lights_off": 0, "sound_enabled": 1, "weight": 10,
            "care_miss_count": 0, "last_call_notified_at": 0, "last_random_event_at": 0, "away_mode": 0,
            "away_started_at": 0, "total_feed_count": 0, "total_snack_count": 0, "total_play_count": 0,
            "total_sleep_count": 0, "total_status_count": 0, "total_clean_count": 0,
            "total_medicine_count": 0, "total_discipline_count": 0, "total_praise_count": 0,
            "total_minigame_count": 0, "total_minigame_win_count": 0, "night_activity_count": 0,
            "birth_at": int(time.time()), "stage_started_at": int(time.time()), "last_updated_at": int(time.time()),
            "journeyed": 0, "journey_at": 0,
        }
        for key, default in numeric_defaults.items():
            try:
                row[key] = int(row.get(key, default) or default)
            except Exception:
                row[key] = default
        row["call_reason"] = str(row.get("call_reason", "") or "")
        row["notification_mode"] = str(row.get("notification_mode", "normal") or "normal")
        if not poop_enabled(row):
            row["poop"] = 0
        row["hunger"] = clamp_meter(row["hunger"])
        row["mood"] = clamp_meter(row["mood"])
        row["sleepiness"] = clamp(row["sleepiness"])
        row["stress"] = clamp(row["stress"])
        row["affection"] = clamp(row["affection"])
        row["discipline"] = clamp(row["discipline"], 0, 99)
        row["weight"] = max(1, int(row["weight"]))
        return row
    except Exception:
        return None


def maybe_cleanup_broken_pet(user_id: int) -> Optional[Dict[str, Any]]:
    row = database.fetch_pet(user_id)
    valid = validate_pet_row(row)
    if row is not None and valid is None:
        database.delete_pet(user_id)
        return None
    if valid is not None:
        database.update_pet(user_id, **valid)
    return valid


def start_new_pet(user_id: int, guild_id: int, thread_id: int = 0) -> Dict[str, Any]:
    database.delete_pet(user_id)
    return database.create_new_pet(user_id, guild_id, thread_id)


def start_or_resume_ready(user_id: int) -> tuple[bool, Optional[Dict[str, Any]]]:
    row = maybe_cleanup_broken_pet(user_id)
    if row is None:
        return False, None
    if row.get("journeyed", 0):
        database.delete_pet(user_id)
        return False, None
    return True, row


def character_image_bases(row: Dict[str, Any]) -> list[str]:
    name = pet_name(row)
    if is_egg(row):
        return ["結卵", "卵", "たまご", "egg"]
    return [name]


def _add_suffix_variants(out: list[str], base: str, suffixes: Iterable[str]) -> None:
    for suffix in suffixes:
        key = f"{base}_{suffix}" if suffix else base
        if key not in out:
            out.append(key)


def image_keys_for_pet(row: Dict[str, Any], transient: Optional[str] = None) -> list[str]:
    row = validate_pet_row(row) or {"character_id": "egg_yuiran", "stage": "egg", "poop": 0, "is_sick": 0, "is_sleeping": 0, "sleepiness": 0, "mood": 4}
    if is_egg(row):
        return list(EGG_IMAGE_KEYS)

    state = "normal"
    if transient == "feed":
        state = "feed"
    elif transient == "snack":
        state = "snack"
    elif row.get("is_sick"):
        state = "sick"
    elif poop_enabled(row) and int(row.get("poop", 0) or 0) >= 1:
        state = "poop"
    elif row.get("is_sleeping") or int(row.get("sleepiness", 0) or 0) >= 80:
        state = "sleepy"
    elif int(row.get("mood", 0) or 0) <= 1:
        state = "angry"
    elif int(row.get("mood", 0) or 0) >= 4:
        state = "happy"

    out: list[str] = []
    bases = character_image_bases(row)
    for base in bases:
        _add_suffix_variants(out, base, IMAGE_STATE_SUFFIXES.get(state, [""]))
    for base in bases:
        _add_suffix_variants(out, base, IMAGE_STATE_SUFFIXES["normal"])
    return out


def letter_image_keys(row: Dict[str, Any]) -> list[str]:
    if is_egg(row):
        return []
    bases = character_image_bases(row)
    out: list[str] = []
    for base in bases:
        _add_suffix_variants(out, base, IMAGE_STATE_SUFFIXES["letter"])
    return out


def notification_mode_label(mode: str) -> str:
    labels = {
        "tamagotchi": "たまごっち",
        "normal": "ふつう",
        "quiet": "静か",
        "mute": "ミュート",
    }
    return labels.get(mode, "ふつう")


def call_stage_label(row: Dict[str, Any]) -> str:
    stage = int(row.get("call_stage", 0) or 0)
    if not row.get("call_flag"):
        return "なし"
    if stage <= 1:
        return "よびだし中"
    if stage == 2:
        return "かなりこまってる"
    return "すごくこまってる"


def call_message_text(user_mention: str, row: Dict[str, Any]) -> str:
    if not row.get("call_flag"):
        return ""
    reason = row.get("call_reason", "")
    text = NOTIFICATION_REASON_TEXT.get(reason, "🔔 おせわサイン")
    recommended = {
        "hunger": "ごはん",
        "mood": "あそぶ",
        "poop": "おそうじ",
        "sick": "おくすり",
        "sleepy": "でんき",
        "whim": "しつけ",
    }.get(reason, "ようす")
    lines = ["● 注意アイコン点灯中", "📟 ピーピー！", user_mention, text, f"👉 おすすめ：{recommended}", f"呼出し段階：{call_stage_label(row)}"]
    return "\n".join(lines)


def status_lines(row: Dict[str, Any]) -> str:
    lines = [
        f"**{pet_name(row)}**",
        "",
        f"おなか　 {bar(row['hunger'])}",
        f"ごきげん {bar(row['mood'])}",
        f"ねむけ　 {clamp(row['sleepiness'])}%",
        f"たいじゅう {row['weight']}g",
        f"しつけ　 {row['discipline']}",
        f"おせわミス {row['care_miss_count']}",
    ]
    if poop_enabled(row):
        lines.append(f"うんち　 {row['poop']}")
    lines.extend([
        f"たいちょう {'😷 病気' if row['is_sick'] else '🙂 元気'}",
        f"いま　 {'🏠 おるすばん' if row['away_mode'] else ('💤 ねている' if row['is_sleeping'] else '☀ おきている')}",
        f"注意 {'● 点灯中' if row['call_flag'] else '○ 消灯'}",
    ])
    if is_egg(row):
        lines.append("")
        lines.append("🥚 まだ卵の状態。孵化するまで見守ってね。")
    return "\n".join(lines)


def build_check_text(user_id: int, row: Dict[str, Any]) -> str:
    setting = database.fetch_user_settings(user_id)
    offset = int(setting.get("clock_offset_minutes", 0) or 0)
    sign = "+" if offset >= 0 else "-"
    abs_minutes = abs(offset)
    offset_text = f"{sign}{abs_minutes // 60:02d}:{abs_minutes % 60:02d}"
    lines = [
        "【チェック】",
        "",
        f"名前：{pet_name(row)}",
        f"いまのじかん：{current_time_label(user_id)}",
        f"時計補正：{offset_text}",
        f"ねる時間：{setting.get('sleep_start', SLEEP_START)}〜{setting.get('sleep_end', SLEEP_END)}",
        "",
        f"おなか　 {bar(row['hunger'])}",
        f"ごきげん {bar(row['mood'])}",
        f"しつけ　 {row['discipline']}",
        f"おせわミス {row['care_miss_count']}",
        f"たいちょう：{'びょうき' if row['is_sick'] else 'げんき'}",
    ]
    if poop_enabled(row):
        lines.append(f"うんち：{row['poop']}")
    lines.extend([
        f"ねむけ：{clamp(row['sleepiness'])}%",
        f"でんき：{'OFF' if row['lights_off'] else 'ON'}",
        f"状態：{'おるすばん' if row['away_mode'] else ('ねている' if row['is_sleeping'] else 'おきている')}",
        f"音：{'ON' if row['sound_enabled'] else 'OFF'}",
        f"注意：{'点灯中' if row['call_flag'] else '消灯'}",
        f"呼出し段階：{call_stage_label(row)}",
    ])
    return "\n".join(lines)


def _decay_profile(row: Dict[str, Any]) -> Dict[str, int]:
    stage = row.get("stage", "egg")
    if stage == "baby1":
        return {"hunger": 22 * 60, "mood": 26 * 60, "sleep": 55 * 60, "poop": 42 * 60}
    if stage == "baby2":
        return {"hunger": 20 * 60, "mood": 24 * 60, "sleep": 50 * 60, "poop": 40 * 60}
    if stage == "child":
        return {"hunger": 18 * 60, "mood": 22 * 60, "sleep": 45 * 60, "poop": 36 * 60}
    if stage == "adult":
        return {"hunger": 26 * 60, "mood": 30 * 60, "sleep": 60 * 60, "poop": 999999}
    return {"hunger": 999999, "mood": 999999, "sleep": 999999, "poop": 999999}


def _set_call_from_state(row: Dict[str, Any], now: int) -> None:
    reason = ""
    if row["is_sick"]:
        reason = "sick"
    elif poop_enabled(row) and row["poop"] >= 1:
        reason = "poop"
    elif row["is_whim_call"]:
        reason = "whim"
    elif row["sleepiness"] >= 85 and not row["is_sleeping"]:
        reason = "sleepy"
    elif row["hunger"] <= 0:
        reason = "hunger"
    elif row["mood"] <= 0:
        reason = "mood"

    if reason:
        if row["call_reason"] != reason:
            row["call_started_at"] = now
            row["call_stage"] = 1
        else:
            elapsed = max(0, now - int(row.get("call_started_at", now) or now))
            row["call_stage"] = 1 if elapsed < 12 * 60 else 2 if elapsed < 24 * 60 else 3
        row["call_flag"] = 1
        row["call_reason"] = reason
    else:
        row["call_flag"] = 0
        row["call_reason"] = ""
        row["call_stage"] = 0
        row["call_started_at"] = 0


def _care_miss_if_overdue(row: Dict[str, Any], now: int) -> Optional[str]:
    if not row.get("call_flag"):
        return None
    started = int(row.get("call_started_at", now) or now)
    elapsed = now - started
    threshold = 20 * 60
    if elapsed < threshold:
        return None
    if row.get("_care_miss_awarded"):
        return None
    row["care_miss_count"] += 1
    row["_care_miss_awarded"] = 1
    return f"おせわミス +1（理由：{row.get('call_reason') or '放置'}）"


def _adult_journey(row: Dict[str, Any], now: int) -> Optional[str]:
    if not is_adult(row) or row.get("journeyed"):
        return None
    elapsed = now - int(row.get("stage_started_at", now) or now)
    if elapsed < JOURNEY_MIN_SECONDS:
        return None
    limit = int((JOURNEY_MIN_SECONDS + JOURNEY_MAX_SECONDS) / 2)
    if elapsed < limit:
        return None
    row["journeyed"] = 1
    row["journey_at"] = now
    return f"{pet_name(row)} は旅立っていったよ…"


def _score_adult(row: Dict[str, Any], adult_id: str) -> float:
    rule = ADULT_EVOLUTION_RULES[adult_id]
    score = 0.0
    score += rule.get("discipline", 0) * row["total_discipline_count"]
    score += rule.get("status", 0) * row["total_status_count"]
    score += rule.get("praise", 0) * row["total_praise_count"]
    score += rule.get("snack", 0) * row["total_snack_count"]
    score += rule.get("mood", 0) * row["mood"]
    score += rule.get("feed", 0) * row["total_feed_count"]
    score += rule.get("play", 0) * row["total_play_count"]
    score += rule.get("minigame", 0) * (row["total_minigame_count"] + row["total_minigame_win_count"])
    score += rule.get("affection", 0) * row["affection"]
    score += rule.get("sleep", 0) * row["total_sleep_count"]
    score += rule.get("clean", 0) * row["total_clean_count"]
    score += rule.get("night", 0) * row["night_activity_count"]
    if rule.get("balance"):
        score += rule["balance"] * max(0, 10 - abs(row["total_feed_count"] - row["total_play_count"]))
    if rule.get("weight_light"):
        score += rule["weight_light"] * max(0, 20 - row["weight"])
    if rule.get("weight_mid"):
        score += rule["weight_mid"] * max(0, 15 - abs(row["weight"] - 15))
    if rule.get("stress_low"):
        score += rule["stress_low"] * max(0, 30 - row["stress"])
    score -= row["care_miss_count"] * 2.0
    return score


def choose_adult(row: Dict[str, Any]) -> str:
    candidates = [cid for cid in DEX_TARGETS if not CHARACTERS[cid]["secret"]]
    ranked = sorted(candidates, key=lambda cid: _score_adult(row, cid), reverse=True)
    chosen = ranked[0] if ranked else "adult_kanato"
    if chosen == "adult_sarii" and random.random() < 0.01:
        return "secret_baaya"
    if random.random() < 0.01:
        return "secret_gugu"
    return chosen


def _evolve_if_needed(user_id: int, row: Dict[str, Any], now: int) -> list[str]:
    messages: list[str] = []
    stage = row.get("stage", "egg")
    elapsed = now - int(row.get("stage_started_at", now) or now)
    if stage in STAGE_SECONDS and elapsed >= STAGE_SECONDS[stage]:
        if stage == "egg":
            row["character_id"] = "baby_colon"
            row["stage"] = "baby1"
        elif stage == "baby1":
            row["character_id"] = "baby_cororon"
            row["stage"] = "baby2"
        elif stage == "baby2":
            row["character_id"] = "child_musubi"
            row["stage"] = "child"
        elif stage == "child":
            row["character_id"] = choose_adult(row)
            row["stage"] = "adult"
            row["poop"] = 0
            database.add_collection_entry(user_id, row["character_id"])
        row["stage_started_at"] = now
        row["call_flag"] = 0
        row["call_reason"] = ""
        row["call_stage"] = 0
        row["call_started_at"] = 0
        row["is_whim_call"] = 0
        messages.append(f"🎉 {pet_name(row)} に進化したよ！")
    journey = _adult_journey(row, now)
    if journey:
        messages.append(journey)
    return messages


def update_over_time(user_id: int, row: Dict[str, Any]) -> tuple[Dict[str, Any], list[str], Optional[str], Optional[str]]:
    row = validate_pet_row(row) or database.create_new_pet(user_id, 0, 0)
    now = int(time.time())
    last = int(row.get("last_updated_at", now) or now)
    elapsed = max(0, now - last)
    if elapsed == 0:
        warning = None
        event = None
        row.pop("_care_miss_awarded", None)
        _set_call_from_state(row, now)
        database.update_pet(user_id, **row)
        return row, [], warning, event

    profile = _decay_profile(row)
    hunger_down = elapsed // profile["hunger"]
    mood_down = elapsed // profile["mood"]
    sleep_up = elapsed // profile["sleep"]
    poop_up = elapsed // profile["poop"] if poop_enabled(row) else 0

    if row["away_mode"]:
        hunger_down //= 2
        mood_down //= 2
        sleep_up = max(1, sleep_up // 2) if sleep_up else 0

    row["hunger"] = clamp_meter(row["hunger"] - int(hunger_down))
    row["mood"] = clamp_meter(row["mood"] - int(mood_down))
    row["sleepiness"] = clamp(row["sleepiness"] + int(sleep_up) * 6)
    if poop_enabled(row):
        row["poop"] = min(3, int(row["poop"]) + int(poop_up))
    else:
        row["poop"] = 0

    if is_in_sleep_window(user_id) and row["lights_off"]:
        row["is_sleeping"] = 1
        row["sleepiness"] = max(0, row["sleepiness"] - 12)
    elif row["is_sleeping"] and not row["lights_off"]:
        row["is_sleeping"] = 0

    if row["hunger"] <= 0 or row["mood"] <= 0:
        row["stress"] = clamp(row["stress"] + 4)
    if row["poop"] >= 2 and poop_enabled(row):
        row["stress"] = clamp(row["stress"] + 2)
    if row["stress"] >= 85 and random.random() < 0.08:
        row["is_sick"] = 1

    if get_user_now(user_id).hour >= 21 or get_user_now(user_id).hour <= 5:
        row["night_activity_count"] += 1 if elapsed >= 60 * 60 else 0

    if random.random() < 0.05 and not row["call_flag"] and not is_egg(row) and not row["is_sleeping"]:
        row["is_whim_call"] = 1

    _set_call_from_state(row, now)
    care_miss_text = _care_miss_if_overdue(row, now)
    evo_msgs = _evolve_if_needed(user_id, row, now)

    row["last_updated_at"] = now
    if not row["call_flag"]:
        row.pop("_care_miss_awarded", None)
    database.update_pet(user_id, **{k: v for k, v in row.items() if not k.startswith("_")})
    return row, evo_msgs, care_miss_text, None


def _clear_call(row: Dict[str, Any]) -> None:
    row["call_flag"] = 0
    row["call_reason"] = ""
    row["call_started_at"] = 0
    row["call_stage"] = 0
    row["is_whim_call"] = 0
    row.pop("_care_miss_awarded", None)


def do_action(user_id: int, row: Dict[str, Any], action: str) -> tuple[Dict[str, Any], str, Optional[str]]:
    row = validate_pet_row(row) or database.create_new_pet(user_id, 0, 0)
    transient: Optional[str] = None
    msg = ""

    if action == "feed":
        row["hunger"] = clamp_meter(row["hunger"] + 1)
        row["weight"] += 1
        row["total_feed_count"] += 1
        transient = "feed"
        msg = "🍚 ごはんをあげたよ。"
        if row["call_reason"] == "hunger":
            _clear_call(row)
    elif action == "snack":
        row["mood"] = clamp_meter(row["mood"] + 1)
        row["weight"] += 1
        row["total_snack_count"] += 1
        transient = "snack"
        msg = "🍬 おやつをあげたよ。"
    elif action == "play":
        row["mood"] = clamp_meter(row["mood"] + 1)
        row["stress"] = clamp(row["stress"] - 8)
        row["weight"] = max(1, row["weight"] - 1)
        row["total_play_count"] += 1
        msg = "⚽ たくさんあそんだよ。"
        if row["call_reason"] == "mood":
            _clear_call(row)
    elif action == "light":
        row["lights_off"] = 0 if row["lights_off"] else 1
        if row["lights_off"] and is_in_sleep_window(user_id):
            row["is_sleeping"] = 1
            row["total_sleep_count"] += 1
            msg = "💡 でんきをけしたよ。おやすみ。"
        else:
            row["is_sleeping"] = 0
            msg = "💡 でんきをつけたよ。"
        if row["call_reason"] == "sleepy" and row["lights_off"]:
            _clear_call(row)
    elif action == "status":
        row["total_status_count"] += 1
        msg = "👀 ようすをみたよ。"
    elif action == "discipline":
        row["discipline"] = clamp(row["discipline"] + 1, 0, 99)
        row["stress"] = clamp(row["stress"] - 4)
        row["total_discipline_count"] += 1
        msg = "📣 しつけをしたよ。"
        if row["call_reason"] == "whim":
            _clear_call(row)
    elif action == "praise":
        row["affection"] = clamp(row["affection"] + 8)
        row["stress"] = clamp(row["stress"] - 6)
        row["total_praise_count"] += 1
        msg = "✨ たくさんほめたよ。"
    elif action == "clean":
        row["poop"] = 0
        row["total_clean_count"] += 1
        msg = "🧹 きれいにしたよ。"
        if row["call_reason"] == "poop":
            _clear_call(row)
    elif action == "medicine":
        row["is_sick"] = 0
        row["stress"] = clamp(row["stress"] - 10)
        row["total_medicine_count"] += 1
        msg = "💊 おくすりをあげたよ。"
        if row["call_reason"] == "sick":
            _clear_call(row)
    elif action == "away_start":
        row["away_mode"] = 1
        row["away_started_at"] = int(time.time())
        msg = "🏠 おるすばんを始めたよ。"
    elif action == "away_end":
        row["away_mode"] = 0
        row["away_started_at"] = 0
        msg = "🏠 おるすばんを終えたよ。"
    else:
        msg = "更新したよ。"

    row["last_updated_at"] = int(time.time())
    _set_call_from_state(row, row["last_updated_at"])
    database.update_pet(user_id, **{k: v for k, v in row.items() if not k.startswith("_")})
    return row, msg, transient


def start_minigame(user_id: int, row: Dict[str, Any], game_key: str) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    if game_key not in MUSIC_GAMES:
        return None, "そのミニゲームはないよ。"
    return MUSIC_GAMES[game_key], None


def submit_minigame_answer(user_id: int, row: Dict[str, Any], game_key: str, index: int) -> tuple[Dict[str, Any], str]:
    game = MUSIC_GAMES[game_key]
    row = validate_pet_row(row) or database.create_new_pet(user_id, 0, 0)
    row["total_minigame_count"] += 1
    if index == game["answer"]:
        row["mood"] = clamp_meter(row["mood"] + 1)
        row["stress"] = clamp(row["stress"] - 8)
        row["weight"] = max(1, row["weight"] - 1)
        row["total_minigame_win_count"] += 1
        msg = f"🎉 正解！ {game['title']} でうれしそう。"
    else:
        row["stress"] = clamp(row["stress"] + 3)
        msg = f"🙂 ざんねん。また {game['title']} であそぼう。"
    row["last_updated_at"] = int(time.time())
    database.update_pet(user_id, **{k: v for k, v in row.items() if not k.startswith("_")})
    return row, msg


def how_to_text() -> str:
    return (
        "【あそびかた】\n\n"
        "1. 育成開始を押して、自分の育成スレッドを作る\n"
        "2. ごはん・あそぶ・ようす などでおせわする\n"
        "3. 困っているサインが出たら、合うボタンで助ける\n"
        "4. 時間がたつと成長して、大人になる\n"
        "5. 図鑑にいろんな子を集めよう\n\n"
        "※ 卵と大人は うんち / おそうじ が出ません。"
    )


def dex_text(user_id: int) -> str:
    owned = {row["character_id"] for row in database.fetch_collection(user_id)}
    lines = ["【図鑑】", ""]
    for cid in DEX_TARGETS:
        char = CHARACTERS[cid]
        mark = "✅" if cid in owned else "⬜"
        lines.append(f"{mark} {char['name']} - {char['profile']}")
    return "\n".join(lines)
