from __future__ import annotations
import random
import time
from datetime import datetime
from typing import Tuple, List
import database
from game_data import (
    CHARACTERS, DEX_TARGETS, STAGE_SECONDS, JOURNEY_MIN_SECONDS, JOURNEY_MAX_SECONDS,
    EVOLUTION_WARNING_SECONDS, MINIGAME_COOLDOWN_SECONDS, RANDOM_EVENT_INTERVAL_SECONDS,
    RANDOM_EVENTS, MUSIC_GAMES, NOTIFICATION_REASON_TEXT
)
from config import SLEEP_START, SLEEP_END

def clamp(n: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(n)))

def clamp_meter(n: int) -> int:
    return max(0, min(4, int(n)))

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

def is_egg(row) -> bool:
    return row["character_id"] == "egg_yuiran"

def pet_name(row) -> str:
    return CHARACTERS[row["character_id"]]["name"]

def bar(value: int, max_value: int = 4) -> str:
    return "█" * value + "░" * (max_value - value)

def stress_label(value: int) -> str:
    if value <= 20: return "低い"
    if value <= 50: return "ふつう"
    if value <= 75: return "高め"
    return "かなり高い"

def image_key_for_pet(row, transient: str | None = None) -> str:
    name = pet_name(row)
    if row["character_id"] == "egg_yuiran":
        return "卵割れる" if transient == "hatch" else "卵"
    if transient == "feed": return f"{name}_ごはん"
    if transient == "snack": return f"{name}_おやつ"
    if row["is_sick"]: return f"{name}_病気"
    if row["poop"] >= 1: return f"{name}_ウンチ"
    if row["sleepiness"] >= 80: return f"{name}_眠い"
    if row["mood"] <= 1: return f"{name}_怒り"
    if row["mood"] >= 4: return f"{name}_喜び"
    return f"{name}_通常"

def status_lines(row) -> str:
    health = "😷 病気" if row["is_sick"] else "🙂 元気"
    call = "🔔 呼び出し中" if row["call_flag"] else "静か"
    whim = "（わがままサイン）" if row["is_whim_call"] else ""
    egg_note = "\n\n🥚 まだ卵の状態。孵化するまでは見守ってね。" if is_egg(row) else ""
    return (
        f"**{pet_name(row)}**\n\n"
        f"おなか　 {bar(row['hunger'])} ({row['hunger']}/4)\n"
        f"ごきげん {bar(row['mood'])} ({row['mood']}/4)\n"
        f"ねむけ　 {clamp(row['sleepiness'])}%\n"
        f"あいじょう {clamp(row['affection'])}%\n"
        f"ストレス {stress_label(row['stress'])} ({clamp(row['stress'])}%)\n\n"
        f"しつけ {row['discipline']}\n"
        f"お世話ミス {row['care_miss_count']}\n"
        f"病気回数 {row['sickness_count']}\n"
        f"うんち {row['poop']}\n"
        f"たいちょう {health}\n"
        f"状態 {call}{whim}"
        f"{egg_note}"
    )

def get_decay_profile(row) -> dict:
    stage = row["stage"]
    if stage == "baby1":
        return {"hunger_minutes": 30, "mood_minutes": 35, "sleep_gain_minutes": 70, "poop_minutes": 50}
    if stage == "baby2":
        return {"hunger_minutes": 25, "mood_minutes": 30, "sleep_gain_minutes": 60, "poop_minutes": 45}
    if stage == "child":
        return {"hunger_minutes": 20, "mood_minutes": 25, "sleep_gain_minutes": 50, "poop_minutes": 40}
    if stage == "adult":
        return {"hunger_minutes": 28, "mood_minutes": 32, "sleep_gain_minutes": 65, "poop_minutes": 55}
    return {"hunger_minutes": 9999, "mood_minutes": 9999, "sleep_gain_minutes": 9999, "poop_minutes": 9999}

def whim_check(row, now: int):
    if is_egg(row):
        return 0, None, row["last_whim_at"]
    if row["call_flag"]:
        return row["is_whim_call"], row["call_reason"], row["last_whim_at"]
    if row["hunger"] >= 3 and row["mood"] >= 3 and now - row["last_whim_at"] >= 40 * 60:
        if random.randint(1, 100) <= 25:
            return 1, "whim", now
    return 0, None, row["last_whim_at"]

def determine_call_reason(row):
    if row["is_sick"]: return 1, "sick"
    if row["poop"] >= 1: return 1, "poop"
    if row["sleepiness"] >= 90: return 1, "sleepy"
    if row["hunger"] <= 0: return 1, "hunger"
    if row["mood"] <= 0: return 1, "mood"
    if row["is_whim_call"]: return 1, "whim"
    return 0, None

def personality_bonus(character_id: str, action: str):
    # 進化後の個性補正
    if character_id == "adult_sarii" and action == "discipline":
        return {"discipline": 1}
    if character_id == "adult_icecream" and action == "snack":
        return {"mood": 1}
    if character_id == "adult_kou" and action == "play":
        return {"mood": 1, "affection": 2}
    if character_id == "adult_nazuna" and action == "sleep":
        return {"sleepiness": -10}
    if character_id == "adult_saina" and action == "minigame_win":
        return {"mood": 1, "affection": 2}
    if character_id == "adult_akira" and action == "feed":
        return {"mood": 1}
    if character_id == "adult_owl" and action == "night_visit":
        return {"affection": 1}
    if character_id == "adult_ichiru" and action == "clean":
        return {"stress": -5}
    return {}

def choose_normal_adult(row) -> str:
    scores = {
        "adult_sarii": row["affection"] + row["discipline"] * 20 + row["total_status_count"] * 5 - row["care_miss_count"] * 8,
        "adult_icecream": row["total_snack_count"] * 20 + row["mood"] * 10,
        "adult_kou": row["total_play_count"] * 18 + row["affection"],
        "adult_nazuna": row["total_sleep_count"] * 20 + (100 - row["stress"]),
        "adult_kanato": 100 - abs(row["hunger"] - 2) * 20 - abs(row["mood"] - 2) * 20 + row["affection"],
        "adult_saina": row["total_minigame_win_count"] * 35 + row["mood"] * 5,
        "adult_akira": row["total_feed_count"] * 18 + row["mood"] * 8,
        "adult_owl": row["night_visit_count"] * 30 + row["total_sleep_count"] * 8,
        "adult_ichiru": (100 - row["stress"]) + row["affection"] - row["care_miss_count"] * 5 - row["sickness_count"] * 3,
    }
    return max(scores, key=scores.get)

def finalize_adult(normal_target: str) -> str:
    if random.randint(1, 100) == 1:
        return "secret_gugu"
    if normal_target == "adult_sarii" and random.randint(1, 100) == 1:
        return "secret_baaya"
    return normal_target

def evolution_warning_due(row, now: int) -> bool:
    cid = row["character_id"]
    if cid not in STAGE_SECONDS:
        return False
    remain = STAGE_SECONDS[cid] - (now - row["stage_entered_at"])
    return (remain <= EVOLUTION_WARNING_SECONDS) and (not row["evolution_warned"])

def evolve_if_needed(user_id: int, row) -> List[str]:
    messages = []
    now = int(time.time())
    character_id = row["character_id"]
    if character_id in STAGE_SECONDS and now - row["stage_entered_at"] >= STAGE_SECONDS[character_id]:
        if character_id == "egg_yuiran":
            next_id, next_stage = "baby_colon", "baby1"
        elif character_id == "baby_colon":
            next_id, next_stage = "baby_cororon", "baby2"
        elif character_id == "baby_cororon":
            next_id, next_stage = "child_musubi", "child"
        else:
            next_id, next_stage = finalize_adult(choose_normal_adult(row)), "adult"
        database.update_pet(user_id, character_id=next_id, stage=next_stage, stage_entered_at=now, evolution_warned=0)
        database.add_evolution_log(user_id, character_id, next_id)
        messages.append(f"✨ **{CHARACTERS[character_id]['name']}** は **{CHARACTERS[next_id]['name']}** に進化した！")
    elif row["stage"] == "adult":
        elapsed = now - row["stage_entered_at"]
        if elapsed >= JOURNEY_MIN_SECONDS:
            chance = min(1.0, (elapsed - JOURNEY_MIN_SECONDS) / max(1, JOURNEY_MAX_SECONDS - JOURNEY_MIN_SECONDS))
            if random.random() < chance:
                database.save_collection(user_id, row["character_id"])
                database.update_pet(user_id, journeyed=1)
                messages.append(f"📖 図鑑登録！ **{CHARACTERS[row['character_id']]['name']}** を登録したよ！")
                messages.append(f"🌟 **{CHARACTERS[row['character_id']]['name']}** は旅に出ました。")
    return messages

def random_event_if_due(user_id: int, row):
    now = int(time.time())
    if is_egg(row):
        return None
    if now - row["last_random_event_at"] < RANDOM_EVENT_INTERVAL_SECONDS:
        return None
    if random.randint(1, 100) > 30:
        return None
    event = random.choice(RANDOM_EVENTS)
    database.update_pet(user_id, last_random_event_at=now)
    return event

def update_over_time(user_id: int, row):
    now = int(time.time())
    if row["journeyed"] or row["odekake_active"]:
        return row, [], None, None

    setting = database.fetch_sleep_setting(user_id)
    sleep_start = setting["sleep_start"] if setting else SLEEP_START
    sleep_end = setting["sleep_end"] if setting else SLEEP_END

    diff = max(0, now - row["last_access_at"])
    if diff < 30:
        warning = "✨ 体が光り始めた… もうすぐ進化するかも！" if evolution_warning_due(row, now) else None
        if warning:
            database.update_pet(user_id, evolution_warned=1)
            row = database.fetch_pet(user_id)
        return row, [], warning, random_event_if_due(user_id, row)

    sleeping = is_in_sleep_window(now, sleep_start, sleep_end)
    profile = get_decay_profile(row)
    minutes = diff / 60

    hunger_loss = int(minutes / profile["hunger_minutes"]) if not sleeping else max(0, int(minutes / (profile["hunger_minutes"] * 2.2)))
    mood_loss = int(minutes / profile["mood_minutes"]) if not sleeping else max(0, int(minutes / (profile["mood_minutes"] * 2.0)))
    sleep_gain = int(minutes / profile["sleep_gain_minutes"]) if not sleeping else 0
    poop_gain = int(minutes / profile["poop_minutes"]) if not sleeping else max(0, int(minutes / (profile["poop_minutes"] * 2.0)))

    hunger = clamp_meter(row["hunger"] - hunger_loss)
    mood = clamp_meter(row["mood"] - mood_loss)
    sleepiness = clamp(row["sleepiness"] + sleep_gain)
    poop = min(3, row["poop"] + poop_gain)

    stress = row["stress"]
    if hunger <= 1: stress += 8
    if mood <= 1: stress += 8
    if poop >= 1: stress += 10
    if sleepiness >= 80: stress += 6
    stress = clamp(stress)

    affection = row["affection"]
    if hunger == 0 or mood == 0:
        affection = clamp(affection - 2)

    is_sick = row["is_sick"]
    sickness_count = row["sickness_count"]
    if not is_sick:
        sick_risk = 0
        if poop >= 2: sick_risk += 20
        if stress >= 70: sick_risk += 20
        if hunger == 0: sick_risk += 20
        if row["care_miss_count"] >= 3: sick_risk += 10
        if sick_risk > 0 and random.randint(1, 100) <= sick_risk:
            is_sick = 1
            sickness_count += 1

    is_whim_call, whim_reason, last_whim_at = whim_check(row, now)

    temp_row = dict(row)
    temp_row.update({
        "hunger": hunger,
        "mood": mood,
        "sleepiness": sleepiness,
        "poop": poop,
        "is_sick": is_sick,
        "is_whim_call": is_whim_call,
    })
    call_flag, call_reason = determine_call_reason(temp_row)

    care_miss_count = row["care_miss_count"]
    if row["call_flag"]:
        since_notice = now - row["last_call_notified_at"]
        if since_notice >= 15 * 60:
            care_miss_count += 1

    night_visit_count = row["night_visit_count"]
    if datetime.fromtimestamp(now).hour >= 22 or datetime.fromtimestamp(now).hour < 5:
        night_visit_count += 1

    evo_warned = row["evolution_warned"]
    warning = None
    if evolution_warning_due(row, now):
        warning = "✨ 体が光り始めた… もうすぐ進化するかも！"
        evo_warned = 1

    database.update_pet(
        user_id,
        hunger=hunger,
        mood=mood,
        sleepiness=sleepiness,
        affection=affection,
        stress=stress,
        poop=poop,
        is_sick=is_sick,
        sickness_count=sickness_count,
        call_flag=call_flag,
        call_reason=call_reason if call_reason else whim_reason,
        is_whim_call=is_whim_call,
        last_whim_at=last_whim_at,
        age_seconds=row["age_seconds"] + diff,
        last_access_at=now,
        care_miss_count=care_miss_count,
        night_visit_count=night_visit_count,
        evolution_warned=evo_warned,
    )
    row = database.fetch_pet(user_id)
    msgs = evolve_if_needed(user_id, row)
    return database.fetch_pet(user_id), msgs, warning, random_event_if_due(user_id, row)

def perform_action(user_id: int, row, action: str):
    now = int(time.time())
    transient = None

    if is_egg(row) and action != "status":
        row, msgs, warning, event = update_over_time(user_id, row)
        extra = []
        if warning: extra.append(warning)
        if event: extra.append(event)
        return row, "🥚 まだ卵の状態だよ。生まれるまでお世話はできないよ。", msgs + extra, transient

    result = ""
    if action == "feed":
        bonus = personality_bonus(row["character_id"], "feed")
        database.update_pet(
            user_id,
            hunger=clamp_meter(row["hunger"] + 2),
            mood=clamp_meter(row["mood"] + bonus.get("mood", 0)),
            total_feed_count=row["total_feed_count"] + 1,
            affection=clamp(row["affection"] + 2),
            call_flag=0 if row["call_reason"] == "hunger" else row["call_flag"],
            call_reason=None if row["call_reason"] == "hunger" else row["call_reason"],
            last_access_at=now,
        )
        result = "🍚 ごはんを食べて満足そう！"
        transient = "feed"

    elif action == "snack":
        bonus = personality_bonus(row["character_id"], "snack")
        database.update_pet(
            user_id,
            mood=clamp_meter(row["mood"] + 1 + bonus.get("mood", 0)),
            stress=clamp(row["stress"] + 4),
            total_snack_count=row["total_snack_count"] + 1,
            affection=clamp(row["affection"] + 1),
            last_access_at=now,
        )
        result = "🍰 おやつを食べてうれしそう！"
        transient = "snack"

    elif action == "play":
        bonus = personality_bonus(row["character_id"], "play")
        database.update_pet(
            user_id,
            mood=clamp_meter(row["mood"] + 2 + bonus.get("mood", 0)),
            stress=clamp(row["stress"] - 15),
            total_play_count=row["total_play_count"] + 1,
            affection=clamp(row["affection"] + 3 + bonus.get("affection", 0)),
            call_flag=0 if row["call_reason"] == "mood" else row["call_flag"],
            call_reason=None if row["call_reason"] == "mood" else row["call_reason"],
            last_access_at=now,
        )
        result = "🎵 たのしく遊んだ！"

    elif action == "sleep":
        bonus = personality_bonus(row["character_id"], "sleep")
        database.update_pet(
            user_id,
            sleepiness=clamp(row["sleepiness"] - 45 + bonus.get("sleepiness", 0)),
            mood=clamp_meter(row["mood"] + 1),
            total_sleep_count=row["total_sleep_count"] + 1,
            call_flag=0 if row["call_reason"] == "sleepy" else row["call_flag"],
            call_reason=None if row["call_reason"] == "sleepy" else row["call_reason"],
            last_access_at=now,
        )
        result = "😴 すこし休んで元気になった。"

    elif action == "status":
        database.update_pet(
            user_id,
            total_status_count=row["total_status_count"] + 1,
            affection=clamp(row["affection"] + 1),
            last_access_at=now,
        )
        result = "👀 ようすを見た。"

    elif action == "discipline":
        if row["is_whim_call"]:
            bonus = personality_bonus(row["character_id"], "discipline")
            database.update_pet(
                user_id,
                discipline=row["discipline"] + 1 + bonus.get("discipline", 0),
                mood=clamp_meter(row["mood"] - 1 if row["mood"] > 0 else 0),
                is_whim_call=0,
                call_flag=0,
                call_reason=None,
                total_discipline_count=row["total_discipline_count"] + 1,
                last_access_at=now,
            )
            result = "📏 わがままサインをしつけた！"
        else:
            result = "📏 今はしつけるタイミングじゃないみたい。"

    elif action == "clean":
        bonus = personality_bonus(row["character_id"], "clean")
        database.update_pet(
            user_id,
            poop=0,
            stress=clamp(row["stress"] - 12 + bonus.get("stress", 0)),
            total_clean_count=row["total_clean_count"] + 1,
            call_flag=0 if row["call_reason"] == "poop" else row["call_flag"],
            call_reason=None if row["call_reason"] == "poop" else row["call_reason"],
            last_access_at=now,
        )
        result = "🧹 きれいにした！"

    elif action == "medicine":
        if row["is_sick"]:
            cured = 1 if random.randint(1, 100) <= 85 else 0
            database.update_pet(
                user_id,
                is_sick=0 if cured else 1,
                stress=clamp(row["stress"] - 8),
                total_medicine_count=row["total_medicine_count"] + 1,
                call_flag=0 if cured and row["call_reason"] == "sick" else row["call_flag"],
                call_reason=None if cured and row["call_reason"] == "sick" else row["call_reason"],
                last_access_at=now,
            )
            result = "💊 おくすりが効いた！" if cured else "💊 まだ少しつらそう…。"
        else:
            result = "💊 今は元気そう。"

    row = database.fetch_pet(user_id)
    row, msgs, warning, event = update_over_time(user_id, row)
    if warning:
        msgs.append(warning)
    if event:
        msgs.append(event)
    return row, result, msgs, transient

def start_odekake(user_id: int, row):
    if is_egg(row):
        return row, "🥚 卵のあいだはおるすばんできないよ。"
    if row["odekake_active"]:
        return row, "🚶 もうおるすばん中だよ。"
    now = int(time.time())
    database.update_pet(user_id, odekake_active=1, odekake_started_at=now, call_flag=0, call_reason=None, is_whim_call=0, last_access_at=now)
    return database.fetch_pet(user_id), "🏠 おるすばんを始めたよ。帰ってきたら結果をまとめて見るよ。"

def stop_odekake(user_id: int, row):
    if not row["odekake_active"] or not row["odekake_started_at"]:
        return row, "🏠 いまはおるすばんしていないよ。", []

    now = int(time.time())
    elapsed = max(0, now - row["odekake_started_at"])
    blocks = max(1, elapsed // (30 * 60))
    success_rate = max(10, min(90, 60 + (row["affection"] - 50) // 5 + row["discipline"] * 2 - (row["stress"] - 30) // 4))

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
            mood = clamp_meter(mood + 1)
            stress = clamp(stress - 5)
            affection = clamp(affection + 1)
        else:
            event = random.choice(bad_events)
            hunger = clamp_meter(hunger - 1)
            mood = clamp_meter(mood - 1)
            stress = clamp(stress + 8)
            sleepiness = clamp(sleepiness + 8)
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
        last_access_at=now,
    )
    row = database.fetch_pet(user_id)
    row, evo_msgs, warning, event = update_over_time(user_id, row)
    extra = evo_msgs[:]
    if warning: extra.append(warning)
    if event: extra.append(event)
    return row, "🏠 おるすばん終了！\n" + "\n".join(log_lines), extra

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
        lines.append(f"・{CHARACTERS[cid]['name']}" if cid in owned else "・????")
    return "\n".join(lines)

def build_dex_detail(user_id: int, cid: str) -> str:
    owned = {row["character_id"] for row in database.fetch_collection(user_id)}
    if cid not in owned:
        return "まだ登録されていないよ。"
    c = CHARACTERS[cid]
    return f"**{c['name']}**\n\n{c['profile']}"

def minigame_available(row) -> bool:
    return int(time.time()) - row["last_minigame_at"] >= MINIGAME_COOLDOWN_SECONDS

def start_minigame(user_id: int, row, game_key: str):
    if is_egg(row):
        return None, "🥚 まだ卵だから、ミニゲームは生まれてからだよ。"
    if not minigame_available(row):
        remain = MINIGAME_COOLDOWN_SECONDS - (int(time.time()) - row["last_minigame_at"])
        return None, f"🎮 ミニゲームはあと {remain // 60}分後にできるよ。"
    return MUSIC_GAMES[game_key], None

def resolve_minigame(user_id: int, row, game_key: str, choice_index: int):
    game = MUSIC_GAMES[game_key]
    now = int(time.time())
    win = (choice_index == game["answer"])
    bonus = personality_bonus(row["character_id"], "minigame_win") if win else {}

    updates = {
        "total_minigame_count": row["total_minigame_count"] + 1,
        "last_minigame_at": now,
        "last_access_at": now,
    }
    if win:
        updates["total_minigame_win_count"] = row["total_minigame_win_count"] + 1
        updates["mood"] = clamp_meter(row["mood"] + 1 + bonus.get("mood", 0))
        updates["affection"] = clamp(row["affection"] + 6 + bonus.get("affection", 0))
        updates["stress"] = clamp(row["stress"] - 8)
        msg = "🎶 正解！ うれしそう！"
    else:
        updates["mood"] = clamp_meter(row["mood"])
        msg = "🎶 ざんねん！ でも楽しめたみたい。"

    database.update_pet(user_id, **updates)
    row = database.fetch_pet(user_id)
    row, evo_msgs, warning, event = update_over_time(user_id, row)
    extra = evo_msgs[:]
    if warning: extra.append(warning)
    if event: extra.append(event)
    return row, msg, extra

def notification_mode_label(mode: str) -> str:
    return {"tamagotchi": "たまごっち", "normal": "ふつう", "quiet": "静か", "mute": "ミュート"}.get(mode, mode)

def call_message_text(user_mention: str, row) -> str | None:
    reason = row["call_reason"]
    if not reason:
        return None
    body = NOTIFICATION_REASON_TEXT.get(reason)
    if not body:
        return None
    return f"{user_mention}\n{body}"
