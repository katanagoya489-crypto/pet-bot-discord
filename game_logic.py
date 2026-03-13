
from __future__ import annotations
import time
import random
from datetime import datetime
from typing import Dict, Tuple, List
import database
from game_data import (
    CHARACTERS, CARE_LABELS, STAGE_SECONDS, JOURNEY_MIN_SECONDS, JOURNEY_MAX_SECONDS,
    MUSIC_GAMES, MINIGAME_COOLDOWN_SECONDS, DEX_TARGETS, POOP_LIMIT
)
from config import SLEEP_START, SLEEP_END

def clamp(n: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(n)))

def label_for(metric: str, value: int) -> str:
    for low, high, label in CARE_LABELS[metric]:
        if low <= value <= high:
            return label
    return CARE_LABELS[metric][-1][2]

def parse_hhmm(s: str) -> Tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)

def is_in_sleep_window(now_ts: int, start_str: str | None = None, end_str: str | None = None) -> bool:
    start_str = start_str or SLEEP_START
    end_str = end_str or SLEEP_END
    sh, sm = parse_hhmm(start_str)
    eh, em = parse_hhmm(end_str)
    dt = datetime.fromtimestamp(now_ts)
    current = dt.hour * 60 + dt.minute
    start = sh * 60 + sm
    end = eh * 60 + em
    if start <= end:
        return start <= current < end
    return current >= start or current < end

def base_pet_dict(row) -> Dict:
    return dict(row) if row else {}

def pet_name(row) -> str:
    return CHARACTERS[row["character_id"]]["name"]

def status_lines(row) -> str:
    mood_extra = "😷 体調が悪そう" if row["is_sick"] else "🙂 元気"
    call = "🔔 呼んでいるみたい…" if row["call_flag"] else "静かに過ごしているみたい"
    return (
        f"**{pet_name(row)}**\n\n"
        f"おなか：{label_for('hunger', row['hunger'])}\n"
        f"きげん：{label_for('mood', row['mood'])}\n"
        f"ねむけ：{label_for('sleepiness', row['sleepiness'])}\n"
        f"あいじょう：{label_for('affection', row['affection'])}\n"
        f"ストレス：{label_for('stress', row['stress'])}\n\n"
        f"しつけ：{row['discipline']}\n"
        f"うんち：{row['poop']}\n"
        f"たいちょう：{mood_extra}\n"
        f"状態：{call}"
    )

def choose_normal_adult(row) -> str:
    scores = {
        "adult_sarii": row["affection"] + row["discipline"] + row["total_status_count"],
        "adult_icecream": row["total_snack_count"] * 25 + row["mood"],
        "adult_kou": row["total_play_count"] * 18 + row["affection"],
        "adult_nazuna": row["total_sleep_count"] * 22 + (100 - row["stress"]),
        "adult_kanato": 100 - abs(row["hunger"]-50) - abs(row["mood"]-50) - abs(row["sleepiness"]-50) + row["affection"],
        "adult_saina": row["total_minigame_win_count"] * 35 + row["mood"],
        "adult_akira": row["total_feed_count"] * 18 + row["mood"],
        "adult_owl": row["night_visit_count"] * 30 + row["total_sleep_count"] * 10,
        "adult_ichiru": (100 - row["stress"]) + (100 - row["hunger"]) + row["affection"],
    }
    return max(scores, key=scores.get)

def finalize_adult(normal_target: str) -> str:
    # Gugu 1% for all adult routes
    if random.randint(1, 100) == 1:
        return "secret_gugu"
    # Baaya only from Sarii route, 1%
    if normal_target == "adult_sarii" and random.randint(1, 100) == 1:
        return "secret_baaya"
    return normal_target

def evolve_if_needed(user_id: int, row) -> List[str]:
    messages = []
    now = int(time.time())
    character_id = row["character_id"]
    if character_id in STAGE_SECONDS:
        if now - row["stage_entered_at"] >= STAGE_SECONDS[character_id]:
            if character_id == "egg_yuiran":
                next_id = "baby_colon"
                next_stage = "baby1"
            elif character_id == "baby_colon":
                next_id = "baby_cororon"
                next_stage = "baby2"
            elif character_id == "baby_cororon":
                next_id = "child_musubi"
                next_stage = "child"
            else:
                normal_target = choose_normal_adult(row)
                next_id = finalize_adult(normal_target)
                next_stage = "adult"
            database.update_pet(user_id, character_id=next_id, stage=next_stage, stage_entered_at=now)
            database.add_evolution_log(user_id, character_id, next_id)
            row = database.fetch_pet(user_id)
            messages.append(f"✨ **{CHARACTERS[character_id]['name']}** は **{CHARACTERS[next_id]['name']}** に進化した！")
    else:
        if row["stage"] == "adult":
            elapsed = now - row["stage_entered_at"]
            if elapsed >= JOURNEY_MIN_SECONDS:
                chance = min(1.0, (elapsed - JOURNEY_MIN_SECONDS) / max(1, JOURNEY_MAX_SECONDS - JOURNEY_MIN_SECONDS))
                if random.random() < chance:
                    database.save_collection(user_id, row["character_id"])
                    database.update_pet(user_id, journeyed=1)
                    messages.append(f"🌟 **{CHARACTERS[row['character_id']]['name']}** は旅に出ました。図鑑に登録されたよ！")
    return messages

def update_over_time(user_id: int, row):
    now = int(time.time())
    if row["journeyed"]:
        return row, []
    if row["odekake_active"]:
        # No normal tick while away; stop mode should handle it.
        return row, []

    setting = database.fetch_sleep_setting(user_id)
    sleep_start = setting["sleep_start"] if setting else SLEEP_START
    sleep_end = setting["sleep_end"] if setting else SLEEP_END

    diff = max(0, now - row["last_access_at"])
    if diff < 30:
        return row, []

    minutes = diff // 60
    sleeping = is_in_sleep_window(now, sleep_start, sleep_end)

    hunger = row["hunger"] + (minutes * (1 if sleeping else 2)) // 8
    sleepiness = row["sleepiness"] + (0 if sleeping else minutes // 10)
    mood = row["mood"] - minutes // (20 if sleeping else 15)
    stress = row["stress"] + minutes // (30 if sleeping else 20)
    affection = row["affection"] - minutes // 60

    poop_increase = min(POOP_LIMIT - row["poop"], minutes // 120)
    poop = min(POOP_LIMIT, row["poop"] + max(0, poop_increase))
    if poop > 0:
        stress += poop * 2

    is_sick = row["is_sick"]
    if not is_sick:
        if poop >= 2 or stress >= 85 or hunger >= 90:
            if random.randint(1, 100) <= 25:
                is_sick = 1

    hunger = clamp(hunger)
    sleepiness = clamp(sleepiness)
    mood = clamp(mood)
    stress = clamp(stress)
    affection = clamp(affection)

    call_flag = 1 if (hunger >= 75 or mood <= 25 or poop >= 1 or is_sick) and not sleeping else 0
    care_miss_add = 1 if call_flag else 0

    updates = {
        "hunger": hunger,
        "sleepiness": sleepiness,
        "mood": mood,
        "stress": stress,
        "affection": affection,
        "poop": poop,
        "is_sick": is_sick,
        "call_flag": call_flag,
        "age_seconds": row["age_seconds"] + diff,
        "last_access_at": now,
        "care_miss_count": row["care_miss_count"] + care_miss_add,
    }
    database.update_pet(user_id, **updates)
    row = database.fetch_pet(user_id)
    messages = evolve_if_needed(user_id, row)
    row = database.fetch_pet(user_id)
    return row, messages

def perform_action(user_id: int, row, action: str) -> Tuple[object, str, List[str]]:
    now = int(time.time())
    result = ""
    if action == "feed":
        database.update_pet(user_id,
            hunger=clamp(row["hunger"] - 35),
            mood=clamp(row["mood"] + 5),
            call_flag=0 if row["hunger"] <= 80 else row["call_flag"],
            total_feed_count=row["total_feed_count"] + 1,
            affection=clamp(row["affection"] + 2),
            last_access_at=now)
        result = "🍚 ごはんを食べて満足そう！"
    elif action == "snack":
        database.update_pet(user_id,
            hunger=clamp(row["hunger"] - 15),
            mood=clamp(row["mood"] + 10),
            stress=clamp(row["stress"] + 3),
            total_snack_count=row["total_snack_count"] + 1,
            affection=clamp(row["affection"] + 2),
            last_access_at=now)
        result = "🍰 おやつを食べてごきげん！"
    elif action == "play":
        database.update_pet(user_id,
            mood=clamp(row["mood"] + 15),
            stress=clamp(row["stress"] - 10),
            hunger=clamp(row["hunger"] + 8),
            total_play_count=row["total_play_count"] + 1,
            affection=clamp(row["affection"] + 4),
            last_access_at=now)
        result = "🎵 たのしく遊んだ！"
    elif action == "sleep":
        database.update_pet(user_id,
            sleepiness=clamp(row["sleepiness"] - 30),
            mood=clamp(row["mood"] + 5),
            total_sleep_count=row["total_sleep_count"] + 1,
            last_access_at=now)
        result = "😴 すこし休んで元気になった。"
    elif action == "status":
        database.update_pet(user_id,
            total_status_count=row["total_status_count"] + 1,
            affection=clamp(row["affection"] + 1),
            last_access_at=now)
        result = "👀 ようすを見た。"
    elif action == "discipline":
        if row["call_flag"] and not row["is_sick"] and row["hunger"] < 75 and row["poop"] == 0:
            database.update_pet(user_id,
                discipline=row["discipline"] + 1,
                mood=clamp(row["mood"] - 3),
                call_flag=0,
                total_discipline_count=row["total_discipline_count"] + 1,
                last_access_at=now)
            result = "📏 しつけが成功した。"
        else:
            result = "📏 今はしつけるタイミングじゃないみたい。"
    elif action == "clean":
        database.update_pet(user_id,
            poop=0,
            stress=clamp(row["stress"] - 8),
            total_clean_count=row["total_clean_count"] + 1,
            call_flag=0 if row["poop"] > 0 else row["call_flag"],
            last_access_at=now)
        result = "🧹 きれいにした！"
    elif action == "medicine":
        if row["is_sick"]:
            cured = 1 if random.randint(1, 100) <= 85 else 0
            database.update_pet(user_id,
                is_sick=0 if cured else 1,
                stress=clamp(row["stress"] - 5),
                total_medicine_count=row["total_medicine_count"] + 1,
                call_flag=0 if cured else row["call_flag"],
                last_access_at=now)
            result = "💊 おくすりが効いた！" if cured else "💊 まだ少しつらそう…。"
        else:
            result = "💊 今は元気そう。"
    else:
        result = "なにもしなかった。"
    row = database.fetch_pet(user_id)
    row, msgs = update_over_time(user_id, row)
    return row, result, msgs

def start_odekake(user_id: int, row):
    if row["odekake_active"]:
        return row, "🚶 もうおるすばん中だよ。"
    now = int(time.time())
    database.update_pet(user_id, odekake_active=1, odekake_started_at=now, call_flag=0, last_access_at=now)
    return database.fetch_pet(user_id), "🏠 おるすばんを始めたよ。帰ってきたら結果をまとめて見るよ。"

def stop_odekake(user_id: int, row):
    if not row["odekake_active"] or not row["odekake_started_at"]:
        return row, "🏠 いまはおるすばんしていないよ。", []

    now = int(time.time())
    elapsed = max(0, now - row["odekake_started_at"])
    blocks = max(1, elapsed // (30 * 60))
    success_base = 60 + (row["affection"] - 50) // 5 + row["discipline"] * 2 - (row["stress"] - 30) // 4 - max(0, row["hunger"] - 60) // 4 - (20 if row["is_sick"] else 0)
    success_rate = max(10, min(90, success_base))

    good_events = ["ちゃんと休めた", "ひとりで遊べた", "落ち着いて待てた", "うまくお留守番できた"]
    bad_events = ["さみしくなった", "おなかがすいた", "少し疲れた", "落ち着かなかった"]

    log_lines = []
    hunger = row["hunger"]
    mood = row["mood"]
    stress = row["stress"]
    sleepiness = row["sleepiness"]
    affection = row["affection"]

    for _ in range(blocks):
        if random.randint(1, 100) <= success_rate:
            event = random.choice(good_events)
            mood = clamp(mood + 4)
            stress = clamp(stress - 3)
            affection = clamp(affection + 1)
        else:
            event = random.choice(bad_events)
            hunger = clamp(hunger + 8)
            mood = clamp(mood - 5)
            stress = clamp(stress + 6)
            sleepiness = clamp(sleepiness + 4)
        log_lines.append(f"・{event}")

    database.update_pet(
        user_id,
        odekake_active=0,
        odekake_started_at=None,
        hunger=hunger,
        mood=mood,
        stress=stress,
        sleepiness=sleepiness,
        affection=affection,
        last_access_at=now
    )
    row = database.fetch_pet(user_id)
    row, evo_msgs = update_over_time(user_id, row)
    return row, f"🏠 おるすばん終了！ {blocks}回ぶんの出来事をまとめたよ。\n" + "\n".join(log_lines), evo_msgs

def start_pet_if_needed(user_id: int, guild_id: int, thread_id: int):
    row = database.fetch_pet(user_id)
    if row and not row["journeyed"]:
        return row, False
    database.create_pet(user_id, guild_id, thread_id)
    return database.fetch_pet(user_id), True

def build_dex_text(user_id: int) -> str:
    owned = {row["character_id"] for row in database.fetch_collection(user_id)}
    lines = [f"図鑑 {len(owned)} / {len(DEX_TARGETS)}\n"]
    for cid in DEX_TARGETS:
        if cid in owned:
            lines.append(f"・{CHARACTERS[cid]['name']}")
        else:
            lines.append("・????")
    return "\n".join(lines)

def build_dex_detail(user_id: int, cid: str) -> str:
    owned = {row["character_id"] for row in database.fetch_collection(user_id)}
    if cid not in owned:
        return "まだ登録されていないよ。"
    c = CHARACTERS[cid]
    x_line = c["x_url"] if c["x_url"] else "未設定"
    return f"**{c['name']}**\n\n{c['profile']}\n\nX: {x_line}"

def minigame_available(row) -> bool:
    return int(time.time()) - row["last_minigame_at"] >= MINIGAME_COOLDOWN_SECONDS

def start_minigame(user_id: int, row, game_key: str):
    if not minigame_available(row):
        remain = MINIGAME_COOLDOWN_SECONDS - (int(time.time()) - row["last_minigame_at"])
        return None, f"🎮 ミニゲームはあと {remain // 60}分後にできるよ。"
    game = MUSIC_GAMES[game_key]
    return game, None

def resolve_minigame(user_id: int, row, game_key: str, choice_index: int):
    game = MUSIC_GAMES[game_key]
    now = int(time.time())
    win = (choice_index == game["answer"])
    updates = {
        "total_minigame_count": row["total_minigame_count"] + 1,
        "last_minigame_at": now,
        "last_access_at": now,
    }
    if win:
        updates["total_minigame_win_count"] = row["total_minigame_win_count"] + 1
        updates["mood"] = clamp(row["mood"] + 12)
        updates["affection"] = clamp(row["affection"] + 6)
        updates["stress"] = clamp(row["stress"] - 5)
        msg = "🎶 正解！ うれしそう！"
    else:
        updates["mood"] = clamp(row["mood"] + 1)
        msg = "🎶 ざんねん！ でも楽しめたみたい。"
    database.update_pet(user_id, **updates)
    row = database.fetch_pet(user_id)
    row, evo_msgs = update_over_time(user_id, row)
    return row, msg, evo_msgs
