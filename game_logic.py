from __future__ import annotations
import random, time
from datetime import datetime
import database
from game_data import CHARACTERS, DEX_TARGETS, STAGE_SECONDS, JOURNEY_MIN_SECONDS, JOURNEY_MAX_SECONDS, EVOLUTION_WARNING_SECONDS, MINIGAME_COOLDOWN_SECONDS, RANDOM_EVENT_INTERVAL_SECONDS, RANDOM_EVENTS, MUSIC_GAMES, NOTIFICATION_REASON_TEXT
from config import SLEEP_START, SLEEP_END

def clamp(n:int, lo:int=0, hi:int=100): return max(lo, min(hi, int(n)))
def clamp_meter(n:int): return max(0, min(4, int(n)))
def parse_hhmm(s:str): h,m=s.split(":"); return int(h), int(m)

def is_in_sleep_window(now_ts:int, start_str:str|None=None, end_str:str|None=None):
    start_str = start_str or SLEEP_START
    end_str = end_str or SLEEP_END
    sh, sm = parse_hhmm(start_str); eh, em = parse_hhmm(end_str)
    dt = datetime.fromtimestamp(now_ts)
    current = dt.hour*60 + dt.minute
    start = sh*60+sm; end = eh*60+em
    if start <= end: return start <= current < end
    return current >= start or current < end

def is_egg(row): return row["character_id"] == "egg_yuiran"
def poop_enabled(row): return row.get("stage") != "adult"
def pet_name(row): return CHARACTERS[row["character_id"]]["name"]
def bar(v:int, m:int=4, full="♥", empty="♡"): return full*v + empty*(m-v)
def age_days(row): return max(0, (int(time.time())-row["birth_at"])//(24*60*60))
def current_time_label(): return datetime.now().strftime("%H:%M")

def safe_get(row, key, default=None):
    if row is None:
        return default
    try:
        return row.get(key, default)
    except AttributeError:
        try:
            return row[key]
        except Exception:
            return default

def call_stage_label(row):
    stage = safe_get(row, "call_stage", 0)
    if not row["call_flag"]:
        return "なし"
    if stage <= 1:
        return "よびだし中"
    if stage == 2:
        return "かなりこまってる"
    return "すごくこまってる"
def sound_label(row): return "ON" if row["sound_enabled"] else "OFF"

def maybe_start_praise_event(user_id, row, now):
    if is_egg(row) or row["is_sleeping"] or row["call_flag"] or row["praise_pending"] or safe_get(row, "good_behavior_pending", 0):
        return
    if row["mood"] >= 3 and row["stress"] <= 30 and random.randint(1, 100) <= 10:
        database.update_pet(user_id, praise_pending=1, praise_due_at=now)

def maybe_start_good_behavior_event(user_id, row, now):
    if is_egg(row) or row["is_sleeping"] or row["call_flag"] or row["praise_pending"] or safe_get(row, "good_behavior_pending", 0):
        return
    poop_ok = (row["poop"] == 0) if poop_enabled(row) else True
    good_state = poop_ok and row["is_sick"] == 0 and row["stress"] <= 25 and row["mood"] >= 2
    if good_state and random.randint(1, 100) <= 6:
        database.update_pet(user_id, good_behavior_pending=1, good_behavior_due_at=now)

def image_key_for_pet(row, transient=None):
    name = pet_name(row)
    if row["character_id"] == "egg_yuiran": return "卵割れる" if transient == "hatch" else "卵"
    if transient == "feed": return f"{name}_ごはん"
    if transient == "snack": return f"{name}_おやつ"
    if row["is_sick"]: return f"{name}_病気"
    if poop_enabled(row) and row["poop"] >= 1: return f"{name}_ウンチ"
    if row["is_sleeping"] or row["sleepiness"] >= 80: return f"{name}_眠い"
    if row["mood"] <= 1: return f"{name}_怒り"
    if row["mood"] >= 4: return f"{name}_喜び"
    return f"{name}_通常"

def status_lines(row):
    health = "😷 病気" if row["is_sick"] else "🙂 元気"
    call = "● 注意アイコン点灯中" if row["call_flag"] else "○ 注意アイコン消灯"
    sleeping = "💤 ねている" if row["is_sleeping"] else "☀ おきている"
    whim = "（わがままサイン）" if row["is_whim_call"] else ""
    praise = "✨ ほめてサイン" if row["praise_pending"] else ""
    good = "🙏 いいことサイン" if safe_get(row, "good_behavior_pending", 0) else ""
    egg_note = "\n\n🥚 まだ卵の状態。孵化するまでは見守ってね。" if is_egg(row) else ""
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
    lines += [
        f"たいちょう {health}",
        f"いま　 {sleeping}",
        f"状態 {call}{whim}",
    ]
    if praise:
        lines.append(praise)
    if good:
        lines.append(good)
    if egg_note:
        lines.append(egg_note.strip("\n"))
    return "\n".join(lines)


def build_check_text(row):
    health = "びょうき" if row["is_sick"] else "げんき"
    sleeping = "ねている" if row["is_sleeping"] else "おきている"
    lines = [
        "【チェック】",
        "",
        f"名前：{pet_name(row)}",
        f"年齢：{age_days(row)}さい",
        f"体重：{row['weight']}g",
        f"いまのじかん：{current_time_label()}",
        "",
        f"おなか　 {bar(row['hunger'])}",
        f"ごきげん {bar(row['mood'])}",
        f"しつけ　 {row['discipline']}",
        f"おせわミス {row['care_miss_count']}",
        "",
        f"たいちょう：{health}",
    ]
    if poop_enabled(row):
        lines.append(f"うんち：{row['poop']}")
    lines += [
        f"ねむけ：{clamp(row['sleepiness'])}%",
        f"でんき：{'OFF' if row['lights_off'] else 'ON'}",
        f"状態：{sleeping}",
        f"音：{sound_label(row)}",
        f"注意：{'点灯中' if row['call_flag'] else '消灯'}",
        f"呼出し段階：{call_stage_label(row)}",
    ]
    return "\n".join(lines)


def get_decay_profile(row):
    stage = row["stage"]
    if stage == "baby1": return {"hunger_minutes": 22, "mood_minutes": 26, "sleep_gain_minutes": 55, "poop_minutes": 42}
    if stage == "baby2": return {"hunger_minutes": 20, "mood_minutes": 24, "sleep_gain_minutes": 50, "poop_minutes": 40}
    if stage == "child": return {"hunger_minutes": 18, "mood_minutes": 22, "sleep_gain_minutes": 45, "poop_minutes": 36}
    if stage == "adult": return {"hunger_minutes": 26, "mood_minutes": 30, "sleep_gain_minutes": 60, "poop_minutes": 52}
    return {"hunger_minutes": 9999, "mood_minutes": 9999, "sleep_gain_minutes": 9999, "poop_minutes": 9999}

def personality_bonus(character_id, action):
    mapping = {
        ("adult_sarii","discipline"): {"discipline":1},
        ("adult_icecream","snack"): {"mood":1},
        ("adult_kou","play"): {"mood":1,"affection":2},
        ("adult_nazuna","light_off"): {"sleepiness":-10},
        ("adult_saina","minigame_win"): {"mood":1,"affection":2},
        ("adult_akira","feed"): {"mood":1},
        ("adult_owl","night_visit"): {"affection":1},
        ("adult_ichiru","clean"): {"stress":-5},
    }
    return mapping.get((character_id, action), {})


def choose_normal_adult(row):
    snack_bias = row["total_snack_count"] - row["total_feed_count"]
    play_bias = row["total_play_count"] + row["total_minigame_win_count"] * 2
    stable_bias = 100 - row["care_miss_count"] * 12 - row["sickness_count"] * 10 - max(0, row["stress"] - 40)
    balance = 100 - abs(row["weight"] - 12) * 5 - abs(row["hunger"] - 2) * 15 - abs(row["mood"] - 2) * 15
    scores = {
        "adult_sarii": stable_bias + row["discipline"] * 28 + row["total_status_count"] * 4 + row["affection"] + safe_get(row, "total_praise_count", 0) * 10 - row["weight"],
        "adult_icecream": row["weight"] * 8 + max(0, snack_bias) * 14 + row["mood"] * 16 + row["total_snack_count"] * 10,
        "adult_kou": play_bias * 14 + row["affection"] * 2 + row["mood"] * 8 - max(0, row["weight"] - 16) * 4,
        "adult_nazuna": row["total_sleep_count"] * 16 + stable_bias + max(0, 16 - row["weight"]) * 2,
        "adult_kanato": balance + row["affection"] + row["discipline"] * 6,
        "adult_saina": row["total_minigame_win_count"] * 26 + row["total_minigame_count"] * 10 + row["mood"] * 10,
        "adult_akira": row["total_feed_count"] * 14 + max(0, row["total_feed_count"] - row["total_snack_count"]) * 8 + max(0, 15 - row["weight"]) * 5,
        "adult_owl": row["night_visit_count"] * 18 + row["total_sleep_count"] * 6 + row["stress"] // 4,
        "adult_ichiru": stable_bias + row["total_clean_count"] * 12 + max(0, 20 - row["stress"]) * 4 + row["affection"] + safe_get(row, "total_praise_count", 0) * 6,
    }
    return max(scores, key=scores.get)

def finalize_adult(normal_target):
    if random.randint(1,100) == 1: return "secret_gugu"
    if normal_target == "adult_sarii" and random.randint(1,100) == 1: return "secret_baaya"
    return normal_target

def evolution_warning_due(row, now):
    cid = row["character_id"]
    if cid not in STAGE_SECONDS: return False
    remain = STAGE_SECONDS[cid] - (now - row["stage_entered_at"])
    return remain <= EVOLUTION_WARNING_SECONDS and (not row["evolution_warned"])

def evolve_if_needed(user_id, row):
    messages=[]; now=int(time.time()); cid=row["character_id"]
    if cid in STAGE_SECONDS and now - row["stage_entered_at"] >= STAGE_SECONDS[cid]:
        if cid == "egg_yuiran": next_id, next_stage = "baby_colon", "baby1"
        elif cid == "baby_colon": next_id, next_stage = "baby_cororon", "baby2"
        elif cid == "baby_cororon": next_id, next_stage = "child_musubi", "child"
        else: next_id, next_stage = finalize_adult(choose_normal_adult(row)), "adult"
        extra_updates = {"character_id": next_id, "stage": next_stage, "stage_entered_at": now, "evolution_warned": 0}
        if next_stage == "adult":
            extra_updates["poop"] = 0
            if safe_get(row, "call_reason") == "poop":
                extra_updates["call_flag"] = 0
                extra_updates["call_reason"] = None
        database.update_pet(user_id, **extra_updates)
        database.add_evolution_log(user_id, cid, next_id)
        messages.append(f"✨ **{CHARACTERS[cid]['name']}** は **{CHARACTERS[next_id]['name']}** に進化した！")
    elif row["stage"] == "adult":
        elapsed = now - row["stage_entered_at"]
        if elapsed >= JOURNEY_MIN_SECONDS:
            chance = min(1.0, (elapsed - JOURNEY_MIN_SECONDS) / max(1, JOURNEY_MAX_SECONDS - JOURNEY_MIN_SECONDS))
            if random.random() < chance:
                database.save_collection(user_id, row["character_id"]); database.update_pet(user_id, journeyed=1)
                messages.append(f"📖 図鑑登録！ **{CHARACTERS[row['character_id']]['name']}** を登録したよ！")
                messages.append(f"🌟 **{CHARACTERS[row['character_id']]['name']}** は旅に出ました。")
    return messages

def random_event_if_due(user_id, row):
    now = int(time.time())
    if is_egg(row) or row["is_sleeping"]: return None
    if now - row["last_random_event_at"] < RANDOM_EVENT_INTERVAL_SECONDS: return None
    if random.randint(1,100) > 30: return None
    event = random.choice(RANDOM_EVENTS)
    database.update_pet(user_id, last_random_event_at=now)
    return event

def whim_check(row, now):
    if is_egg(row) or row["is_sleeping"]: return 0, None, row["last_whim_at"]
    if row["call_flag"]: return row["is_whim_call"], row["call_reason"], row["last_whim_at"]
    poop_ok = (row["poop"] == 0) if poop_enabled(row) else True
    essentials_ok = row["hunger"] >= 3 and row["mood"] >= 3 and poop_ok and row["is_sick"] == 0 and row["sleepiness"] < 80
    if essentials_ok and now - row["last_whim_at"] >= 40*60 and random.randint(1,100) <= 25:
        return 1, "whim", now
    return 0, None, row["last_whim_at"]

def determine_call_reason(row):
    if row["is_sick"]: return 1, "sick"
    if poop_enabled(row) and row["poop"] >= 1: return 1, "poop"
    if row["sleepiness"] >= 90 and not row["is_sleeping"]: return 1, "sleepy"
    if row["hunger"] <= 0: return 1, "hunger"
    if row["mood"] <= 0: return 1, "mood"
    if row["is_whim_call"]: return 1, "whim"
    return 0, None

def update_sleep_state(user_id, row, now):
    setting = database.fetch_sleep_setting(user_id)
    sleep_start = setting["sleep_start"] if setting else SLEEP_START
    sleep_end = setting["sleep_end"] if setting else SLEEP_END
    night_window = is_in_sleep_window(now, sleep_start, sleep_end)
    is_sleeping = row["is_sleeping"]; lights_off=row["lights_off"]; wake_message=None
    if is_sleeping and not night_window:
        is_sleeping=0; lights_off=0; wake_message="☀ おきたよ！"
    return is_sleeping, lights_off, wake_message

def update_over_time(user_id, row):
    now=int(time.time())
    if row["journeyed"] or row["odekake_active"]: return row, [], None, None
    if not poop_enabled(row) and (row["poop"] != 0 or safe_get(row, "call_reason") == "poop"):
        database.update_pet(
            user_id,
            poop=0,
            call_flag=0 if safe_get(row, "call_reason") == "poop" else row["call_flag"],
            call_reason=None if safe_get(row, "call_reason") == "poop" else row["call_reason"],
        )
        row = database.fetch_pet(user_id)
    is_sleeping, lights_off, wake_message = update_sleep_state(user_id, row, now)
    diff=max(0, now-row["last_access_at"])
    if diff < 30:
        warning = "✨ 体が光り始めた… もうすぐ進化するかも！" if evolution_warning_due(row, now) else None
        if warning: database.update_pet(user_id, evolution_warned=1)
        if wake_message: database.update_pet(user_id, is_sleeping=is_sleeping, lights_off=lights_off)
        row = database.fetch_pet(user_id)
        return row, [], wake_message or warning, random_event_if_due(user_id, row)
    profile=get_decay_profile(row); minutes=diff/60
    hunger_loss = int(minutes/profile["hunger_minutes"]) if not is_sleeping else max(0, int(minutes/(profile["hunger_minutes"]*3.0)))
    mood_loss = int(minutes/profile["mood_minutes"]) if not is_sleeping else 0
    sleep_gain = 0 if is_sleeping else int(minutes/profile["sleep_gain_minutes"])
    poop_gain = (int(minutes/profile["poop_minutes"]) if not is_sleeping else max(0,int(minutes/(profile["poop_minutes"]*2.5)))) if poop_enabled(row) else 0
    hunger=clamp_meter(row["hunger"]-hunger_loss); mood=clamp_meter(row["mood"]-mood_loss)
    sleepiness = clamp(row["sleepiness"] + sleep_gain if not is_sleeping else max(0, row["sleepiness"] - int(minutes*1.5)))
    poop=min(3, row["poop"]+poop_gain) if poop_enabled(row) else 0
    stress=row["stress"]
    if hunger <= 1: stress += 8
    if mood <= 1: stress += 8
    if poop_enabled(row) and poop >= 1: stress += 10
    if sleepiness >= 80 and not is_sleeping: stress += 6
    if is_sleeping and not lights_off: stress += 10
    stress=clamp(stress)
    affection=row["affection"]
    if hunger == 0 or mood == 0: affection=clamp(affection-2)
    is_sick=row["is_sick"]; sickness_count=row["sickness_count"]
    if not is_sick:
        sick_risk = 0
        if poop_enabled(row) and poop >= 2: sick_risk += 20
        if stress >= 70: sick_risk += 20
        if hunger == 0: sick_risk += 20
        if row["care_miss_count"] >= 3: sick_risk += 10
        if sick_risk > 0 and random.randint(1,100) <= sick_risk:
            is_sick=1; sickness_count += 1
    is_whim_call, whim_reason, last_whim_at = whim_check(row, now)
    temp = dict(row); temp.update({"hunger":hunger,"mood":mood,"sleepiness":sleepiness,"poop":poop,"is_sick":is_sick,"is_whim_call":is_whim_call,"is_sleeping":is_sleeping})
    call_flag, call_reason = determine_call_reason(temp)
    call_started_at = safe_get(row, "call_started_at", 0)
    call_stage = safe_get(row, "call_stage", 0)
    if call_flag:
        if not row["call_flag"]:
            call_started_at = now
            call_stage = 1
        else:
            elapsed_call = max(0, now - (call_started_at or now))
            if elapsed_call >= 30 * 60:
                call_stage = 3
            elif elapsed_call >= 15 * 60:
                call_stage = 2
            else:
                call_stage = max(1, call_stage)
    else:
        call_started_at = 0
        call_stage = 0
    care_miss_count = row["care_miss_count"]
    if row["call_flag"] and now - row["last_call_notified_at"] >= 20*60: care_miss_count += 1
    night_visit_count = row["night_visit_count"]
    if datetime.fromtimestamp(now).hour >= 22 or datetime.fromtimestamp(now).hour < 5:
        night_visit_count += 1
        bonus=personality_bonus(row["character_id"], "night_visit"); affection=clamp(affection+bonus.get("affection",0))
    evo_warned = row["evolution_warned"]; warning=None
    if evolution_warning_due(row, now): warning="✨ 体が光り始めた… もうすぐ進化するかも！"; evo_warned=1
    weight=row["weight"]
    if diff >= 90*60 and not is_sleeping and random.randint(1,100) <= 15: weight=max(1, weight-1)

    praise_pending = row["praise_pending"]
    praise_due_at = row["praise_due_at"]
    good_behavior_pending = safe_get(row, "good_behavior_pending", 0)
    good_behavior_due_at = safe_get(row, "good_behavior_due_at", 0)
    if praise_pending and now - praise_due_at >= 15 * 60:
        praise_pending = 0
        praise_due_at = 0
        care_miss_count += 1
    if good_behavior_pending and now - good_behavior_due_at >= 15 * 60:
        good_behavior_pending = 0
        good_behavior_due_at = 0
    database.update_pet(user_id, hunger=hunger, mood=mood, sleepiness=sleepiness, affection=affection, stress=stress, poop=poop,
        is_sick=is_sick, sickness_count=sickness_count, call_flag=call_flag, call_reason=call_reason if call_reason else whim_reason,
        call_started_at=call_started_at, call_stage=call_stage,
        is_whim_call=is_whim_call, is_sleeping=is_sleeping, lights_off=lights_off, weight=weight,
        praise_pending=praise_pending, praise_due_at=praise_due_at, good_behavior_pending=good_behavior_pending, good_behavior_due_at=good_behavior_due_at, last_whim_at=last_whim_at,
        age_seconds=row["age_seconds"]+diff, last_access_at=now, care_miss_count=care_miss_count, night_visit_count=night_visit_count, evolution_warned=evo_warned)
    row = database.fetch_pet(user_id)
    maybe_start_praise_event(user_id, row, now)
    row = database.fetch_pet(user_id)
    maybe_start_good_behavior_event(user_id, row, now)
    row = database.fetch_pet(user_id)
    msgs=evolve_if_needed(user_id, row)
    event=random_event_if_due(user_id,row)
    return database.fetch_pet(user_id), msgs, wake_message or warning, event

def perform_action(user_id, row, action):
    now=int(time.time()); transient=None
    if is_egg(row) and action != "status":
        row, msgs, warning, event = update_over_time(user_id,row); extra=[]; 
        if warning: extra.append(warning)
        if event: extra.append(event)
        return row, "🥚 まだ卵の状態だよ。生まれるまでお世話はできないよ。", msgs+extra, transient
    if row["is_sleeping"] and action not in ("status","sleep"):
        row, msgs, warning, event = update_over_time(user_id,row); extra=[]
        if warning: extra.append(warning)
        if event: extra.append(event)
        return row, "💤 ねているよ。あさまでそっとしておこう。", msgs+extra, transient
    result=""
    if action=="feed":
        bonus=personality_bonus(row["character_id"],"feed")
        database.update_pet(user_id, hunger=clamp_meter(row["hunger"]+2), mood=clamp_meter(row["mood"]+bonus.get("mood",0)),
            total_feed_count=row["total_feed_count"]+1, affection=clamp(row["affection"]+2), weight=min(30, row["weight"]+1),
            call_flag=0 if row["call_reason"]=="hunger" else row["call_flag"], call_reason=None if row["call_reason"]=="hunger" else row["call_reason"], last_access_at=now)
        result="🍚 ごはんをたべた！"; transient="feed"
    elif action=="snack":
        bonus=personality_bonus(row["character_id"],"snack")
        database.update_pet(user_id, mood=clamp_meter(row["mood"]+1+bonus.get("mood",0)), stress=clamp(row["stress"]+4),
            total_snack_count=row["total_snack_count"]+1, affection=clamp(row["affection"]+1), weight=min(30, row["weight"]+1), last_access_at=now)
        result="🍰 おやつをたべてうれしそう！"; transient="snack"
    elif action=="play":
        bonus=personality_bonus(row["character_id"],"play")
        database.update_pet(user_id, mood=clamp_meter(row["mood"]+2+bonus.get("mood",0)), stress=clamp(row["stress"]-15),
            total_play_count=row["total_play_count"]+1, affection=clamp(row["affection"]+3+bonus.get("affection",0)),
            call_flag=0 if row["call_reason"]=="mood" else row["call_flag"], call_reason=None if row["call_reason"]=="mood" else row["call_reason"], last_access_at=now)
        result="🎵 たのしくあそんだ！"
    elif action=="sleep":
        if row["sleepiness"] < 65: result="💡 まだ ねないみたい。"
        else:
            bonus=personality_bonus(row["character_id"],"light_off")
            database.update_pet(user_id, is_sleeping=1, lights_off=1, sleepiness=clamp(row["sleepiness"]-20+bonus.get("sleepiness",0)),
                total_sleep_count=row["total_sleep_count"]+1, call_flag=0 if row["call_reason"]=="sleepy" else row["call_flag"],
                call_reason=None if row["call_reason"]=="sleepy" else row["call_reason"], last_access_at=now)
            result="💡 でんきをけしたよ。ぐっすりねている…"
    elif action=="status":
        database.update_pet(user_id, total_status_count=row["total_status_count"]+1, affection=clamp(row["affection"]+1), last_access_at=now)
        result = build_check_text(database.fetch_pet(user_id))
    elif action=="discipline":
        if row["is_whim_call"]:
            bonus=personality_bonus(row["character_id"],"discipline")
            database.update_pet(user_id, discipline=row["discipline"]+1+bonus.get("discipline",0), mood=clamp_meter(row["mood"]-1 if row["mood"]>0 else 0),
                is_whim_call=0, call_flag=0, call_reason=None, total_discipline_count=row["total_discipline_count"]+1, last_access_at=now)
            result="📏 しかった！ わがままサインがきえた。"
        else:
            database.update_pet(user_id, affection=clamp(row["affection"] - 1), stress=clamp(row["stress"] + 2), last_access_at=now)
            result="📏 いまは しつけるタイミングじゃないみたい。しつけミス…"
    elif action=="praise":
        if row["praise_pending"] or safe_get(row, "good_behavior_pending", 0):
            database.update_pet(
                user_id,
                praise_pending=0,
                praise_due_at=0,
                good_behavior_pending=0,
                good_behavior_due_at=0,
                affection=clamp(row["affection"] + 6),
                mood=clamp_meter(row["mood"] + 1),
                stress=clamp(row["stress"] - 6),
                total_praise_count=safe_get(row, "total_praise_count", 0) + 1,
                last_access_at=now,
            )
            result="✨ ほめた！ うれしそう！"
        else:
            database.update_pet(
                user_id,
                affection=clamp(row["affection"] - 1),
                stress=clamp(row["stress"] + 2),
                last_access_at=now,
            )
            result="✨ いまは ほめるタイミングじゃないみたい。"
    elif action=="clean":
        if not poop_enabled(row):
            result="🧹 いまはおそうじはいらないよ。"
        else:
            bonus=personality_bonus(row["character_id"],"clean")
            database.update_pet(user_id, poop=0, stress=clamp(row["stress"]-12+bonus.get("stress",0)), total_clean_count=row["total_clean_count"]+1,
                call_flag=0 if row["call_reason"]=="poop" else row["call_flag"], call_reason=None if row["call_reason"]=="poop" else row["call_reason"], last_access_at=now)
            result="🧹 うんちをきれいにした！"
    elif action=="medicine":
        if row["is_sick"]:
            cured=1 if random.randint(1,100)<=85 else 0
            database.update_pet(user_id, is_sick=0 if cured else 1, stress=clamp(row["stress"]-8), total_medicine_count=row["total_medicine_count"]+1,
                call_flag=0 if cured and row["call_reason"]=="sick" else row["call_flag"], call_reason=None if cured and row["call_reason"]=="sick" else row["call_reason"], last_access_at=now)
            result="💊 おくすりがきいた！" if cured else "💊 まだちょっとつらそう…。"
        else:
            result="💊 いまは げんきそう。"
    row = database.fetch_pet(user_id); row, msgs, warning, event = update_over_time(user_id,row)
    if warning: msgs.append(warning)
    if event: msgs.append(event)
    return row, result, msgs, transient

def start_odekake(user_id, row):
    if is_egg(row): return row, "🥚 卵のあいだはおるすばんできないよ。"
    if row["odekake_active"]: return row, "🏠 もうおるすばん中だよ。"
    now=int(time.time())
    database.update_pet(user_id, odekake_active=1, odekake_started_at=now, call_flag=0, call_reason=None, is_whim_call=0, last_access_at=now)
    return database.fetch_pet(user_id), "🏠 おるすばんをはじめたよ。"

def stop_odekake(user_id, row):
    if not row["odekake_active"] or not row["odekake_started_at"]: return row, "🏠 いまはおるすばんしていないよ。", []
    now=int(time.time()); elapsed=max(0, now-row["odekake_started_at"]); blocks=max(1, elapsed//(30*60))
    success_rate=max(10, min(90, 60 + (row["affection"]-50)//5 + row["discipline"]*2 - (row["stress"]-30)//4))
    good=["ちゃんとまてた","ひとりであそべた","おだやかにすごせた","じょうずにおるすばんできた"]
    bad=["さみしくなった","おなかがすいた","すこしつかれた","おちつかなかった"]
    lines=[]; hunger=row["hunger"]; mood=row["mood"]; stress=row["stress"]; sleepiness=row["sleepiness"]; affection=row["affection"]
    for _ in range(blocks):
        if random.randint(1,100) <= success_rate:
            e=random.choice(good); mood=clamp_meter(mood+1); stress=clamp(stress-5); affection=clamp(affection+1)
        else:
            e=random.choice(bad); hunger=clamp_meter(hunger-1); mood=clamp_meter(mood-1); stress=clamp(stress+8); sleepiness=clamp(sleepiness+8)
        lines.append(f"・{e}")
    database.update_pet(user_id, odekake_active=0, odekake_started_at=None, hunger=hunger, mood=mood, stress=stress, sleepiness=sleepiness, affection=affection, last_access_at=now)
    row=database.fetch_pet(user_id); row, evo_msgs, warning, event = update_over_time(user_id,row); extra=evo_msgs[:]
    if warning: extra.append(warning)
    if event: extra.append(event)
    return row, "🏠 おるすばんしゅうりょう！\n" + "\n".join(lines), extra

def start_pet_if_needed(user_id, guild_id, thread_id):
    row=database.fetch_pet(user_id)
    if row and not row["journeyed"]: return row, False
    database.create_pet(user_id, guild_id, thread_id)
    return database.fetch_pet(user_id), True

def build_dex_text(user_id):
    owned={row["character_id"] for row in database.fetch_collection(user_id)}
    lines=[f"図鑑 {len(owned)} / {len(DEX_TARGETS)}\n"]
    for cid in DEX_TARGETS: lines.append(f"・{CHARACTERS[cid]['name']}" if cid in owned else "・????")
    return "\n".join(lines)

def build_dex_detail(user_id, cid):
    owned={row["character_id"] for row in database.fetch_collection(user_id)}
    if cid not in owned: return "まだ登録されていないよ。"
    c=CHARACTERS[cid]
    return f"**{c['name']}**\n\n{c['profile']}"

def minigame_available(row): return int(time.time()) - row["last_minigame_at"] >= MINIGAME_COOLDOWN_SECONDS

def start_minigame(user_id, row, game_key):
    if is_egg(row): return None, "🥚 まだ卵だから、ミニゲームは生まれてからだよ。"
    if row["is_sleeping"]: return None, "💤 ねているから、あそべないよ。"
    if not minigame_available(row):
        remain = MINIGAME_COOLDOWN_SECONDS - (int(time.time()) - row["last_minigame_at"])
        return None, f"🎮 ミニゲームはあと {remain // 60}分後にできるよ。"
    return MUSIC_GAMES[game_key], None

def resolve_minigame(user_id, row, game_key, choice_index):
    game=MUSIC_GAMES[game_key]; now=int(time.time()); win=(choice_index==game["answer"]); bonus=personality_bonus(row["character_id"], "minigame_win") if win else {}
    updates={"total_minigame_count":row["total_minigame_count"]+1,"last_minigame_at":now,"last_access_at":now,"weight":max(1,row["weight"]-1)}
    if win:
        updates["total_minigame_win_count"]=row["total_minigame_win_count"]+1
        updates["mood"]=clamp_meter(row["mood"]+1+bonus.get("mood",0)); updates["affection"]=clamp(row["affection"]+6+bonus.get("affection",0)); updates["stress"]=clamp(row["stress"]-8)
        msg="🎮 せいかい！ ごきげんアップ！"
    else:
        updates["mood"]=clamp_meter(row["mood"]); msg="🎮 ざんねん！ でもたのしかったみたい。"
    database.update_pet(user_id, **updates)
    row=database.fetch_pet(user_id); row, evo_msgs, warning, event = update_over_time(user_id,row); extra=evo_msgs[:]
    if warning: extra.append(warning)
    if event: extra.append(event)
    return row, msg, extra

def notification_mode_label(mode:str): return {"tamagotchi":"たまごっち","normal":"ふつう","quiet":"静か","mute":"ミュート"}.get(mode, mode)

def call_reason_title(reason:str):
    return {"hunger":"🍚 おなかぺこぺこ","mood":"😣 ごきげんダウン","poop":"💩 うんちあり","sick":"🤒 びょうきサイン","sleepy":"🌙 ねむねむサイン","whim":"📢 わがままサイン"}.get(reason,"🔔 おせわサイン")

def recommended_action_label(reason:str):
    return {"hunger":"ごはん","mood":"あそぶ","poop":"おそうじ","sick":"おくすり","sleepy":"でんき","whim":"しつけ"}.get(reason,"ようす")

def call_message_text(user_mention:str, row):
    reason=row["call_reason"]
    if not reason:
        return None
    body=NOTIFICATION_REASON_TEXT.get(reason)
    if not body:
        return None
    title=call_reason_title(reason)
    recommend=recommended_action_label(reason)
    beep="📟 ピーピー！ " if row["sound_enabled"] else ""
    stage=row.get("call_stage", 1)
    if stage <= 1:
        head = "● 注意アイコン点灯中"
        lead = "おせわサイン"
    elif stage == 2:
        head = "●● 注意アイコン点灯中"
        lead = "まだおせわできてないよ！"
    else:
        head = "●●● 注意アイコン点灯中"
        lead = "かなりこまってるよ！"
    return f"{head}\n{beep}{lead}\n{user_mention}\n{title}\n{body}\n👉 おすすめ：{recommend}"
