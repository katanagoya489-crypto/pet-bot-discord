from __future__ import annotations

import random
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import database
from game_data import (
    CHARACTERS,
    CALL_REASON_TEXT,
    DEX_TARGETS,
    EGG_IMAGE_KEYS,
    EVOLUTION_WARNING_SECONDS,
    IMAGE_STATE_ALIASES,
    MUSIC_GAMES,
    RANDOM_EVENT_INTERVAL_SECONDS,
    RANDOM_EVENTS,
    STAGE_SECONDS,
)

JST = ZoneInfo('Asia/Tokyo')


def clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(value)))


def clamp_meter(value: int) -> int:
    return max(0, min(4, int(value)))


def safe_int(value, default=0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def character_stage(character_id: str) -> str:
    return CHARACTERS.get(character_id, {}).get('stage', 'egg')


def is_egg(row: dict) -> bool:
    return character_stage(row.get('character_id', '')) == 'egg'


def is_adult(row: dict) -> bool:
    return character_stage(row.get('character_id', '')) == 'adult'


def poop_enabled(row: dict) -> bool:
    stage = character_stage(row.get('character_id', ''))
    return stage in {'baby1', 'baby2', 'child'}


def can_resume_pet(row: dict | None) -> bool:
    if not row:
        return False
    cid = row.get('character_id')
    if cid not in CHARACTERS:
        return False
    if row.get('journeyed'):
        return False
    return True


def repair_pet_row(user_id: int, row: dict | None) -> dict | None:
    if not row:
        return None
    cid = row.get('character_id')
    if cid not in CHARACTERS:
        database.delete_pet(user_id)
        return None
    true_stage = character_stage(cid)
    updates = {}
    if row.get('stage') != true_stage:
        updates['stage'] = true_stage
    if not poop_enabled(row) and safe_int(row.get('poop', 0)) != 0:
        updates['poop'] = 0
        if row.get('call_reason') == 'poop':
            updates['call_flag'] = 0
            updates['call_reason'] = ''
            updates['call_started_at'] = 0
            updates['call_stage'] = 0
    if updates:
        database.update_pet(user_id, **updates)
        row = database.fetch_pet(user_id)
    return row


def user_now(user_id: int) -> datetime:
    settings = database.fetch_user_settings(user_id)
    offset = safe_int(settings.get('clock_offset_minutes', 0))
    return datetime.now(JST) + timedelta(minutes=offset)


def current_time_label(user_id: int) -> str:
    return user_now(user_id).strftime('%Y/%m/%d %H:%M')


def sleep_window(user_id: int) -> tuple[str, str]:
    settings = database.fetch_user_settings(user_id)
    return settings.get('sleep_start', '22:00'), settings.get('sleep_end', '07:00')


def _parse_hhmm(text: str, fallback: str) -> tuple[int, int]:
    try:
        hh, mm = (text or fallback).split(':', 1)
        hh_i, mm_i = int(hh), int(mm)
        if 0 <= hh_i <= 23 and 0 <= mm_i <= 59:
            return hh_i, mm_i
    except Exception:
        pass
    hh, mm = fallback.split(':', 1)
    return int(hh), int(mm)


def in_sleep_hours(user_id: int, when: datetime | None = None) -> bool:
    when = when or user_now(user_id)
    start_text, end_text = sleep_window(user_id)
    sh, sm = _parse_hhmm(start_text, '22:00')
    eh, em = _parse_hhmm(end_text, '07:00')
    start = when.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = when.replace(hour=eh, minute=em, second=0, microsecond=0)
    if start <= end:
        return start <= when < end
    return when >= start or when < end


def notification_mode_label(mode: str) -> str:
    return {
        'normal': 'ふつう',
        'tamagotchi': 'たまごっち',
        'quiet': '静か',
        'mute': 'ミュート',
    }.get(mode or 'normal', 'ふつう')


def sound_label(row: dict) -> str:
    return 'ON' if safe_int(row.get('sound_enabled', 1)) else 'OFF'


def call_stage_label(row: dict) -> str:
    stage = safe_int(row.get('call_stage', 0))
    return {0: 'なし', 1: '呼出し中', 2: '困ってる', 3: 'かなり困ってる'}.get(stage, '呼出し中')


def call_message_text(user_mention: str, row: dict) -> str:
    reason = row.get('call_reason') or ''
    if not reason:
        return ''
    parts = ['●● 注意アイコン点灯中', '📟 ピーピー！', user_mention, '', CALL_REASON_TEXT.get(reason, 'おせわサインだよ！')]
    recommend = {
        'hunger': 'おすすめ：ごはん',
        'mood': 'おすすめ：あそぶ',
        'poop': 'おすすめ：おそうじ',
        'sick': 'おすすめ：おくすり',
        'sleepy': 'おすすめ：でんき',
        'whim': 'おすすめ：しつけ',
    }.get(reason)
    if recommend:
        parts.extend(['', recommend])
    return '\n'.join(parts)


def determine_call_reason(row: dict) -> tuple[int, str]:
    if safe_int(row.get('is_sick', 0)):
        return 1, 'sick'
    if poop_enabled(row) and safe_int(row.get('poop', 0)) >= 1:
        return 1, 'poop'
    if clamp_meter(row.get('hunger', 0)) == 0:
        return 1, 'hunger'
    if clamp_meter(row.get('mood', 0)) == 0:
        return 1, 'mood'
    if safe_int(row.get('sleepiness', 0)) >= 65 and not safe_int(row.get('is_sleeping', 0)) and in_sleep_hours(safe_int(row.get('user_id', 0))):
        return 1, 'sleepy'
    if safe_int(row.get('is_whim_call', 0)):
        return 1, 'whim'
    return 0, ''


def _current_state_name(row: dict, transient: str | None = None) -> str:
    if transient == 'feed':
        return 'ごはん'
    if transient == 'snack':
        return 'おやつ'
    if transient == 'sleep':
        return '眠い'
    if transient == 'medicine' or safe_int(row.get('is_sick', 0)):
        return '病気'
    if transient == 'clean' and poop_enabled(row):
        return 'ウンチ'
    if transient == 'play':
        return '喜び'
    if safe_int(row.get('stress', 0)) >= 65 or clamp_meter(row.get('mood', 4)) <= 1:
        return '怒り'
    if poop_enabled(row) and safe_int(row.get('poop', 0)) >= 1:
        return 'ウンチ'
    if safe_int(row.get('sleepiness', 0)) >= 65:
        return '眠い'
    return '通常'


def image_key_candidates(row: dict, transient: str | None = None) -> list[str]:
    cid = row.get('character_id', 'egg_yuiran')
    char = CHARACTERS.get(cid, CHARACTERS['egg_yuiran'])
    base = char.get('image_base') or char['name']
    state = _current_state_name(row, transient=transient)
    keys: list[str] = []
    if is_egg(row):
        keys.extend(EGG_IMAGE_KEYS)
        for alias in IMAGE_STATE_ALIASES['通常']:
            keys.append(f'{base}_{alias}')
        keys.append(base)
    else:
        for alias in IMAGE_STATE_ALIASES.get(state, [state]):
            keys.append(f'{base}_{alias}')
        for alias in IMAGE_STATE_ALIASES['通常']:
            keys.append(f'{base}_{alias}')
        keys.append(base)
    # Deduplicate while preserving order.
    seen = set()
    out = []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def build_check_text(row: dict, user_id: int) -> str:
    start, end = sleep_window(user_id)
    lines = [
        f'いまのじかん：{current_time_label(user_id)}',
        f'おなか：{clamp_meter(row.get("hunger", 0))}/4',
        f'ごきげん：{clamp_meter(row.get("mood", 0))}/4',
        f'ねむけ：{clamp(row.get("sleepiness", 0))}%',
        f'ストレス：{clamp(row.get("stress", 0))}%',
        f'あいじょう：{clamp(row.get("affection", 0))}',
        f'たいじゅう：{safe_int(row.get("weight", 0))}',
        f'しつけ：{safe_int(row.get("discipline", 0))}',
        f'おせわミス：{safe_int(row.get("care_miss_count", 0))}',
        f'たいちょう：{"びょうき" if safe_int(row.get("is_sick", 0)) else "げんき"}',
    ]
    if poop_enabled(row):
        lines.append(f'うんち：{safe_int(row.get("poop", 0))}')
    lines.extend([
        f'でんき：{"OFF" if safe_int(row.get("lights_off", 0)) else "ON"}',
        f'ねる時間：{start}〜{end}',
        f'呼出し段階：{call_stage_label(row)}',
    ])
    return '\n'.join(lines)


def status_lines(row: dict, user_id: int) -> str:
    char = CHARACTERS.get(row.get('character_id', 'egg_yuiran'), CHARACTERS['egg_yuiran'])
    lines = [
        f'**{char["name"]}**',
        f'おなか：{clamp_meter(row.get("hunger", 0))}/4',
        f'ごきげん：{clamp_meter(row.get("mood", 0))}/4',
        f'ねむけ：{clamp(row.get("sleepiness", 0))}%',
        f'たいじゅう：{safe_int(row.get("weight", 0))}',
        f'しつけ：{safe_int(row.get("discipline", 0))}',
        f'おせわミス：{safe_int(row.get("care_miss_count", 0))}',
    ]
    if poop_enabled(row):
        lines.append(f'うんち：{safe_int(row.get("poop", 0))}')
    lines.append(f'いまのじかん：{current_time_label(user_id)}')
    return '\n'.join(lines)


def get_decay_profile(row: dict) -> dict[str, float]:
    stage = character_stage(row.get('character_id', ''))
    if stage == 'baby1':
        return {'hunger': 22, 'mood': 26, 'sleep': 55, 'poop': 42}
    if stage == 'baby2':
        return {'hunger': 20, 'mood': 24, 'sleep': 50, 'poop': 40}
    if stage == 'child':
        return {'hunger': 18, 'mood': 22, 'sleep': 45, 'poop': 36}
    if stage == 'adult':
        return {'hunger': 26, 'mood': 30, 'sleep': 60, 'poop': 999999}
    return {'hunger': 99999, 'mood': 99999, 'sleep': 99999, 'poop': 99999}


def _maybe_start_whim(row: dict, now: int) -> tuple[int, int]:
    if is_egg(row) or safe_int(row.get('is_sleeping', 0)):
        return 0, now
    last = safe_int(row.get('good_behavior_due_at', 0))
    if last and now - last < RANDOM_EVENT_INTERVAL_SECONDS:
        return safe_int(row.get('is_whim_call', 0)), last
    if random.randint(1, 100) <= 8:
        return 1, now
    return 0, last or now


def choose_normal_adult(row: dict) -> str:
    snack_bias = safe_int(row.get('total_snack_count', 0)) - safe_int(row.get('total_feed_count', 0))
    play_bias = safe_int(row.get('total_play_count', 0)) + safe_int(row.get('total_minigame_win_count', 0)) * 2
    stable_bias = 100 - safe_int(row.get('care_miss_count', 0)) * 12 - safe_int(row.get('sickness_count', 0)) * 10 - max(0, safe_int(row.get('stress', 0)) - 40)
    scores = {
        'adult_sarii': stable_bias + safe_int(row.get('discipline', 0)) * 28 + safe_int(row.get('total_status_count', 0)) * 4 + safe_int(row.get('affection', 0)) - safe_int(row.get('weight', 0)),
        'adult_icecream': safe_int(row.get('weight', 0)) * 8 + max(0, snack_bias) * 14 + clamp_meter(row.get('mood', 0)) * 16 + safe_int(row.get('total_snack_count', 0)) * 10,
        'adult_kou': play_bias * 14 + safe_int(row.get('affection', 0)) * 2 + clamp_meter(row.get('mood', 0)) * 8,
        'adult_nazuna': safe_int(row.get('total_sleep_count', 0)) * 16 + stable_bias + max(0, 16 - safe_int(row.get('weight', 0))) * 2,
        'adult_kanato': stable_bias + safe_int(row.get('affection', 0)) + safe_int(row.get('discipline', 0)) * 6,
        'adult_saina': safe_int(row.get('total_minigame_win_count', 0)) * 26 + safe_int(row.get('total_minigame_count', 0)) * 10 + clamp_meter(row.get('mood', 0)) * 10,
        'adult_akira': safe_int(row.get('total_feed_count', 0)) * 14 + max(0, safe_int(row.get('total_feed_count', 0)) - safe_int(row.get('total_snack_count', 0))) * 8,
        'adult_owl': safe_int(row.get('night_visit_count', 0)) * 18 + safe_int(row.get('total_sleep_count', 0)) * 6 + safe_int(row.get('stress', 0)) // 4,
        'adult_ichiru': stable_bias + safe_int(row.get('total_clean_count', 0)) * 12 + max(0, 20 - safe_int(row.get('stress', 0))) * 4 + safe_int(row.get('affection', 0)),
    }
    return max(scores, key=scores.get)


def finalize_adult(normal_target: str) -> str:
    if random.randint(1, 100) == 1:
        return 'secret_gugu'
    if normal_target == 'adult_sarii' and random.randint(1, 100) == 1:
        return 'secret_baaya'
    return normal_target


def update_sleep_state(user_id: int, row: dict, now: int) -> tuple[int, int, str | None]:
    sleeping = safe_int(row.get('is_sleeping', 0))
    lights_off = safe_int(row.get('lights_off', 0))
    local_now = user_now(user_id)
    should_sleep = in_sleep_hours(user_id, local_now)
    message = None
    if sleeping and not should_sleep:
        sleeping = 0
        lights_off = 0
        message = '☀️ おはよう！ 目をさましたよ。'
    elif not sleeping and should_sleep and safe_int(row.get('sleepiness', 0)) >= 65 and lights_off:
        sleeping = 1
    return sleeping, lights_off, message


def update_over_time(user_id: int, row: dict) -> tuple[dict, list[str], str | None, str | None]:
    row = repair_pet_row(user_id, row) or row
    if not row:
        return {}, [], None, None
    now = int(time.time())
    if safe_int(row.get('journeyed', 0)):
        return row, [], None, None
    if safe_int(row.get('odekake_active', 0)):
        database.update_pet(user_id, last_access_at=now)
        return database.fetch_pet(user_id), [], None, None

    is_sleeping, lights_off, wake_message = update_sleep_state(user_id, row, now)
    last_access = safe_int(row.get('last_access_at', now)) or now
    diff = max(0, now - last_access)
    if diff < 30:
        database.update_pet(user_id, is_sleeping=is_sleeping, lights_off=lights_off)
        new_row = database.fetch_pet(user_id)
        return new_row, [], wake_message, None

    profile = get_decay_profile(row)
    minutes = diff / 60.0
    hunger_loss = int(minutes / profile['hunger']) if not is_sleeping else max(0, int(minutes / (profile['hunger'] * 3.0)))
    mood_loss = int(minutes / profile['mood']) if not is_sleeping else 0
    sleep_gain = 0 if is_sleeping else int(minutes / profile['sleep'])
    poop_gain = 0
    if poop_enabled(row):
        poop_gain = int(minutes / profile['poop']) if not is_sleeping else max(0, int(minutes / (profile['poop'] * 2.5)))

    hunger = clamp_meter(row.get('hunger', 0) - hunger_loss)
    mood = clamp_meter(row.get('mood', 0) - mood_loss)
    sleepiness = clamp(row.get('sleepiness', 0) + sleep_gain if not is_sleeping else max(0, row.get('sleepiness', 0) - int(minutes * 1.5)))
    poop = 0 if not poop_enabled(row) else min(3, safe_int(row.get('poop', 0)) + poop_gain)
    stress = safe_int(row.get('stress', 0))
    if hunger <= 1:
        stress += 8
    if mood <= 1:
        stress += 8
    if poop_enabled(row) and poop >= 1:
        stress += 10
    if sleepiness >= 80 and not is_sleeping:
        stress += 6
    if is_sleeping and not lights_off:
        stress += 10
    stress = clamp(stress)
    affection = clamp(safe_int(row.get('affection', 0)) - (2 if hunger == 0 or mood == 0 else 0))

    is_sick = safe_int(row.get('is_sick', 0))
    sickness_count = safe_int(row.get('sickness_count', 0))
    if not is_sick:
        sick_risk = 0
        if poop_enabled(row) and poop >= 2:
            sick_risk += 20
        if stress >= 70:
            sick_risk += 20
        if hunger == 0:
            sick_risk += 20
        if safe_int(row.get('care_miss_count', 0)) >= 3:
            sick_risk += 10
        if sick_risk > 0 and random.randint(1, 100) <= sick_risk:
            is_sick = 1
            sickness_count += 1

    whim_call, whim_at = _maybe_start_whim(row, now)
    temp = dict(row)
    temp.update({'hunger': hunger, 'mood': mood, 'sleepiness': sleepiness, 'poop': poop, 'is_sick': is_sick, 'is_whim_call': whim_call, 'is_sleeping': is_sleeping})
    call_flag, call_reason = determine_call_reason(temp)
    call_started_at = safe_int(row.get('call_started_at', 0))
    call_stage = safe_int(row.get('call_stage', 0))
    if call_flag:
        if not safe_int(row.get('call_flag', 0)):
            call_started_at = now
            call_stage = 1
        else:
            elapsed = max(0, now - (call_started_at or now))
            call_stage = 3 if elapsed >= 30 * 60 else 2 if elapsed >= 15 * 60 else max(1, call_stage)
    else:
        call_started_at = 0
        call_stage = 0

    care_miss = safe_int(row.get('care_miss_count', 0))
    if safe_int(row.get('call_flag', 0)) and safe_int(row.get('last_call_notified_at', 0)) and now - safe_int(row.get('last_call_notified_at', 0)) >= 20 * 60:
        care_miss += 1

    local_now = user_now(user_id)
    night_visit_count = safe_int(row.get('night_visit_count', 0))
    if local_now.hour >= 22 or local_now.hour < 5:
        night_visit_count += 1

    warning = None
    if row.get('character_id') in STAGE_SECONDS:
        remain = STAGE_SECONDS[row['character_id']] - (now - safe_int(row.get('stage_entered_at', now)))
        if remain <= EVOLUTION_WARNING_SECONDS and remain > 0:
            warning = '✨ 体が光り始めた… もうすぐ進化するかも！'

    database.update_pet(
        user_id,
        hunger=hunger,
        mood=mood,
        sleepiness=sleepiness,
        stress=stress,
        affection=affection,
        poop=poop,
        is_sick=is_sick,
        sickness_count=sickness_count,
        is_whim_call=whim_call,
        good_behavior_due_at=whim_at,
        call_flag=call_flag,
        call_reason=call_reason,
        call_started_at=call_started_at,
        call_stage=call_stage,
        is_sleeping=is_sleeping,
        lights_off=lights_off,
        age_seconds=safe_int(row.get('age_seconds', 0)) + diff,
        last_access_at=now,
        care_miss_count=care_miss,
        night_visit_count=night_visit_count,
        weight=max(1, safe_int(row.get('weight', 10)) - (1 if diff >= 90 * 60 and not is_sleeping and random.randint(1, 100) <= 15 else 0)),
    )
    row = database.fetch_pet(user_id)

    msgs: list[str] = []
    cid = row.get('character_id')
    if cid in STAGE_SECONDS and now - safe_int(row.get('stage_entered_at', now)) >= STAGE_SECONDS[cid]:
        if cid == 'egg_yuiran':
            next_id = 'baby_colon'
        elif cid == 'baby_colon':
            next_id = 'baby_cororon'
        elif cid == 'baby_cororon':
            next_id = 'child_musubi'
        else:
            next_id = finalize_adult(choose_normal_adult(row))
            database.save_collection(user_id, next_id)
        database.update_pet(
            user_id,
            character_id=next_id,
            stage=character_stage(next_id),
            stage_entered_at=now,
            poop=0 if not poop_enabled({'character_id': next_id}) else safe_int(row.get('poop', 0)),
            call_flag=0 if next_id == 'egg_yuiran' or character_stage(next_id) == 'adult' else safe_int(row.get('call_flag', 0)),
            call_reason='' if next_id == 'egg_yuiran' or character_stage(next_id) == 'adult' else row.get('call_reason', ''),
            call_started_at=0 if character_stage(next_id) in {'egg', 'adult'} else safe_int(row.get('call_started_at', 0)),
            call_stage=0 if character_stage(next_id) in {'egg', 'adult'} else safe_int(row.get('call_stage', 0)),
        )
        prev_name = CHARACTERS[cid]['name']
        next_name = CHARACTERS[next_id]['name']
        msgs.append(f'✨ **{prev_name}** は **{next_name}** に進化した！')
        row = database.fetch_pet(user_id)

    event = None
    if random.randint(1, 100) <= 12 and now - safe_int(row.get('last_call_notified_at', 0)) >= RANDOM_EVENT_INTERVAL_SECONDS:
        event = random.choice(RANDOM_EVENTS)
    return row, msgs, warning or wake_message, event


def perform_action(user_id: int, row: dict, action: str) -> tuple[dict, str, list[str], str | None]:
    row = repair_pet_row(user_id, row) or row
    if not row:
        return {}, '育成データが見つからないよ。', [], None
    now = int(time.time())
    transient = None
    if is_egg(row) and action not in {'status'}:
        row, msgs, warning, event = update_over_time(user_id, row)
        extras = [x for x in [warning, event] if x]
        return row, '🥚 まだ卵の状態だよ。生まれるまでお世話はできないよ。', msgs + extras, transient
    if safe_int(row.get('is_sleeping', 0)) and action not in {'status', 'sleep'}:
        row, msgs, warning, event = update_over_time(user_id, row)
        extras = [x for x in [warning, event] if x]
        return row, '💤 ねているよ。あさまでそっとしておこう。', msgs + extras, transient

    result = ''
    if action == 'feed':
        database.update_pet(
            user_id,
            hunger=clamp_meter(row.get('hunger', 0) + 2),
            mood=clamp_meter(row.get('mood', 0) + 0),
            total_feed_count=safe_int(row.get('total_feed_count', 0)) + 1,
            affection=clamp(row.get('affection', 0) + 2),
            weight=min(30, safe_int(row.get('weight', 10)) + 1),
            call_flag=0 if row.get('call_reason') == 'hunger' else safe_int(row.get('call_flag', 0)),
            call_reason='' if row.get('call_reason') == 'hunger' else row.get('call_reason', ''),
            last_access_at=now,
        )
        result = '🍚 ごはんをたべた！'
        transient = 'feed'
    elif action == 'snack':
        database.update_pet(
            user_id,
            mood=clamp_meter(row.get('mood', 0) + 1),
            stress=clamp(row.get('stress', 0) + 4),
            total_snack_count=safe_int(row.get('total_snack_count', 0)) + 1,
            affection=clamp(row.get('affection', 0) + 1),
            weight=min(30, safe_int(row.get('weight', 10)) + 1),
            last_access_at=now,
        )
        result = '🍰 おやつをたべてうれしそう！'
        transient = 'snack'
    elif action == 'play':
        database.update_pet(
            user_id,
            mood=clamp_meter(row.get('mood', 0) + 2),
            stress=clamp(row.get('stress', 0) - 15),
            total_play_count=safe_int(row.get('total_play_count', 0)) + 1,
            affection=clamp(row.get('affection', 0) + 3),
            call_flag=0 if row.get('call_reason') == 'mood' else safe_int(row.get('call_flag', 0)),
            call_reason='' if row.get('call_reason') == 'mood' else row.get('call_reason', ''),
            last_access_at=now,
        )
        result = '🎵 たのしくあそんだ！'
        transient = 'play'
    elif action == 'sleep':
        if safe_int(row.get('sleepiness', 0)) < 65:
            result = '💡 まだ ねないみたい。'
        else:
            database.update_pet(
                user_id,
                is_sleeping=1,
                lights_off=1,
                sleepiness=clamp(row.get('sleepiness', 0) - 20),
                total_sleep_count=safe_int(row.get('total_sleep_count', 0)) + 1,
                call_flag=0 if row.get('call_reason') == 'sleepy' else safe_int(row.get('call_flag', 0)),
                call_reason='' if row.get('call_reason') == 'sleepy' else row.get('call_reason', ''),
                last_access_at=now,
            )
            result = '💡 でんきをけしたよ。ぐっすりねている…'
            transient = 'sleep'
    elif action == 'status':
        database.update_pet(
            user_id,
            total_status_count=safe_int(row.get('total_status_count', 0)) + 1,
            affection=clamp(row.get('affection', 0) + 1),
            last_access_at=now,
        )
        row = database.fetch_pet(user_id)
        return row, build_check_text(row, user_id), [], None
    elif action == 'discipline':
        if safe_int(row.get('is_whim_call', 0)):
            database.update_pet(
                user_id,
                discipline=safe_int(row.get('discipline', 0)) + 1,
                mood=clamp_meter(row.get('mood', 0) - 1 if row.get('mood', 0) > 0 else 0),
                is_whim_call=0,
                call_flag=0,
                call_reason='',
                total_discipline_count=safe_int(row.get('total_discipline_count', 0)) + 1,
                last_access_at=now,
            )
            result = '📏 しかった！ わがままサインがきえた。'
        else:
            database.update_pet(user_id, affection=clamp(row.get('affection', 0) - 1), stress=clamp(row.get('stress', 0) + 2), last_access_at=now)
            result = '📏 いまは しつけるタイミングじゃないみたい。'
    elif action == 'praise':
        database.update_pet(
            user_id,
            affection=clamp(row.get('affection', 0) + 4),
            mood=clamp_meter(row.get('mood', 0) + 1),
            stress=clamp(row.get('stress', 0) - 6),
            total_praise_count=safe_int(row.get('total_praise_count', 0)) + 1,
            last_access_at=now,
        )
        result = '✨ ほめた！ うれしそう！'
    elif action == 'clean':
        if not poop_enabled(row):
            result = '🧹 いまは おそうじの必要はないよ。'
        elif safe_int(row.get('poop', 0)) <= 0:
            result = '🧹 まだ うんちはないみたい。'
        else:
            database.update_pet(
                user_id,
                poop=max(0, safe_int(row.get('poop', 0)) - 1),
                stress=clamp(row.get('stress', 0) - 8),
                total_clean_count=safe_int(row.get('total_clean_count', 0)) + 1,
                call_flag=0 if row.get('call_reason') == 'poop' and safe_int(row.get('poop', 0)) <= 1 else safe_int(row.get('call_flag', 0)),
                call_reason='' if row.get('call_reason') == 'poop' and safe_int(row.get('poop', 0)) <= 1 else row.get('call_reason', ''),
                last_access_at=now,
            )
            result = '🧹 うんちをきれいにした！'
            transient = 'clean'
    elif action == 'medicine':
        if safe_int(row.get('is_sick', 0)):
            database.update_pet(
                user_id,
                is_sick=0,
                stress=clamp(row.get('stress', 0) - 8),
                total_medicine_count=safe_int(row.get('total_medicine_count', 0)) + 1,
                call_flag=0 if row.get('call_reason') == 'sick' else safe_int(row.get('call_flag', 0)),
                call_reason='' if row.get('call_reason') == 'sick' else row.get('call_reason', ''),
                last_access_at=now,
            )
            result = '💊 おくすりで元気になった！'
            transient = 'medicine'
        else:
            result = '💊 いまは元気そうだよ。'
    elif action == 'minigame':
        won = random.randint(1, 100) <= 65
        database.update_pet(
            user_id,
            mood=clamp_meter(row.get('mood', 0) + (2 if won else 1)),
            stress=clamp(row.get('stress', 0) - (12 if won else 6)),
            weight=max(1, safe_int(row.get('weight', 10)) - 1),
            total_minigame_count=safe_int(row.get('total_minigame_count', 0)) + 1,
            total_minigame_win_count=safe_int(row.get('total_minigame_win_count', 0)) + (1 if won else 0),
            last_access_at=now,
        )
        result = '🎮 ミニゲームに勝った！' if won else '🎮 ミニゲームで遊んだ！'
        transient = 'play'
    else:
        result = 'まだその操作はできないよ。'

    row = database.fetch_pet(user_id)
    row, msgs, warning, event = update_over_time(user_id, row)
    extras = [x for x in [warning, event] if x]
    return row, result, msgs + extras, transient
