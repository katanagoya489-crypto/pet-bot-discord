from __future__ import annotations

import asyncio
import importlib.util
import sqlite3
import sys
import time
from pathlib import Path

import discord
from discord.ext import commands

BASE_DIR = Path(__file__).resolve().parent


def _load_local_module(module_name: str):
    module_path = BASE_DIR / f"{module_name}.py"
    if module_path.exists():
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            return module
    return __import__(module_name)


database = _load_local_module("database")
game_logic = _load_local_module("game_logic")
from game_data import CHARACTERS, DEX_TARGETS, MUSIC_GAMES

try:
    image_service = _load_local_module("image_service")
except Exception:
    class _ImageServiceFallback:
        @staticmethod
        async def get_image_url(_bot, _key):
            return None
    image_service = _ImageServiceFallback()

try:
    from config import ADMIN_USER_IDS, DISCORD_BOT_TOKEN, ENTRY_CHANNEL_ID
except Exception:
    ADMIN_USER_IDS = []
    DISCORD_BOT_TOKEN = ""
    ENTRY_CHANNEL_ID = 0

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)
WELCOME_MARKER = "○○っちへようこそ！"
TEMP_MESSAGE_SECONDS = 8
_background_started = False
_registered_pet_message_ids: set[int] = set()


def is_owner(interaction: discord.Interaction, owner_id: int) -> bool:
    return interaction.user.id == owner_id


async def send_temp_interaction_message(interaction: discord.Interaction, content: str | None = None, *, embed: discord.Embed | None = None, view: discord.ui.View | None = None, ephemeral: bool = True, seconds: int = TEMP_MESSAGE_SECONDS):
    send_kwargs = {"content": content, "embed": embed, "ephemeral": ephemeral}
    if view is not None:
        send_kwargs["view"] = view
    if not interaction.response.is_done():
        await interaction.response.send_message(**send_kwargs)
        await asyncio.sleep(seconds)
        try:
            await interaction.delete_original_response()
        except Exception:
            pass
        return
    try:
        msg = await interaction.followup.send(wait=True, **send_kwargs)
        await asyncio.sleep(seconds)
        try:
            await msg.delete()
        except Exception:
            pass
    except Exception:
        pass


async def build_embed(row, transient: str | None = None) -> discord.Embed:
    embed = discord.Embed(description=game_logic.status_lines(row))
    key = game_logic.image_key_for_pet(row, transient=transient)
    try:
        url = await image_service.get_image_url(bot, key)
    except Exception:
        url = None
    if url:
        embed.set_image(url=url)
    return embed


async def build_letter_embed(character_name: str):
    key = f"{character_name}_手紙"
    try:
        url = await image_service.get_image_url(bot, key)
    except Exception:
        url = None
    if not url:
        return None
    embed = discord.Embed(title=f"{character_name} から手紙が届いています…")
    embed.set_image(url=url)
    return embed


async def upsert_system_log(thread: discord.Thread, user_id: int, text: str):
    row = database.fetch_pet(user_id)
    if not row:
        return
    message_id = row["system_message_id"]
    body = f"【システムログ】\n{text}"
    if message_id:
        try:
            message = await thread.fetch_message(int(message_id))
            await message.edit(content=body)
            return
        except Exception:
            pass
    message = await thread.send(body)
    database.update_pet(user_id, system_message_id=str(message.id))


async def upsert_alert_log(thread: discord.Thread, user_id: int, text: str):
    row = database.fetch_pet(user_id)
    if not row:
        return
    message_id = row["alert_message_id"]
    body = f"【呼出しログ】\n{text}"
    if message_id:
        try:
            message = await thread.fetch_message(int(message_id))
            await message.edit(content=body)
            return
        except Exception:
            pass
    message = await thread.send(body)
    database.update_pet(user_id, alert_message_id=str(message.id))


def current_special_sign_text(row, user_id: int) -> str | None:
    if row["praise_pending"]:
        return f"✨ ほめてサイン\n<@{user_id}>\n👉 おすすめ：ほめる"
    if row.get("good_behavior_pending", 0):
        return f"🙏 いいことサイン\n<@{user_id}>\n👉 おすすめ：ほめる"
    return None


def render_settings_text(owner_id: int, row) -> str:
    setting = database.fetch_user_settings(owner_id) or {}
    sound = "ON" if row["sound_enabled"] else "OFF"
    sleep_start = setting.get("sleep_start", "22:00")
    sleep_end = setting.get("sleep_end", "07:00")
    offset = int(setting.get("clock_offset_minutes", 0) or 0)
    sign = "+" if offset >= 0 else "-"
    abs_minutes = abs(offset)
    offset_text = f"{sign}{abs_minutes // 60:02d}:{abs_minutes % 60:02d}"
    display_now = game_logic.current_time_label(user_id=owner_id)
    return (
        f"通知モード: {game_logic.notification_mode_label(row['notification_mode'])}\n"
        f"音: {sound}\n"
        f"表示時間: {display_now}\n"
        f"時計補正: {offset_text}\n"
        f"ねる時間: {sleep_start}〜{sleep_end}"
    )


def compose_result_alert(title: str, main_text: str, row, user_id: int) -> str:
    lines = [title, main_text]
    current_call = game_logic.call_message_text(f"<@{user_id}>", row)
    special_sign = current_special_sign_text(row, user_id)
    if current_call:
        lines += ["", "――いまのおせわサイン――", current_call]
    elif special_sign:
        lines += ["", special_sign]
    else:
        lines += ["", "○ 注意アイコン消灯", "いまはだいじょうぶ。"]
    return "\n".join(lines)


async def cleanup_old_main_panels(channel: discord.TextChannel, keep_message_id: int | None = None):
    try:
        async for message in channel.history(limit=50):
            if message.author.id != bot.user.id or not message.content or WELCOME_MARKER not in message.content:
                continue
            if keep_message_id and message.id == keep_message_id:
                continue
            try:
                await message.delete()
            except Exception:
                pass
    except Exception:
        pass


async def delete_recent_thread_created_log(parent_channel: discord.TextChannel):
    await asyncio.sleep(1.2)
    try:
        async for message in parent_channel.history(limit=10):
            if message.type == discord.MessageType.thread_created:
                try:
                    await message.delete()
                except Exception:
                    pass
    except Exception:
        pass


async def create_clean_thread(parent_channel: discord.TextChannel, thread_name: str) -> discord.Thread:
    thread = await parent_channel.create_thread(name=thread_name, type=discord.ChannelType.public_thread, auto_archive_duration=60)
    bot.loop.create_task(delete_recent_thread_created_log(parent_channel))
    return thread


def remind_due(row, now: int) -> bool:
    if not row["call_flag"]:
        return False
    last = row["last_call_notified_at"] or 0
    if last == 0:
        return True
    return now - last >= game_logic.remind_interval_seconds(row)


async def _resolve_thread(row):
    if not row or not row.get("thread_id"):
        return None
    thread = bot.get_channel(int(row["thread_id"]))
    if thread is not None:
        return thread
    try:
        return await bot.fetch_channel(int(row["thread_id"]))
    except Exception:
        return None


async def _recreate_panel_if_missing(user_id: int, row, thread: discord.Thread):
    embed = await build_embed(row)
    panel = await thread.send(f"<@{user_id}> の育成パネルを再作成したよ！", embed=embed, view=PetView(user_id))
    database.update_pet(user_id, panel_message_id=str(panel.id))
    register_pet_view(user_id, panel.id)
    return panel


async def refresh_panel_for_user(user_id: int, prefix: str = "", transient: str | None = None):
    row = database.fetch_pet(user_id)
    if not row:
        return
    thread = await _resolve_thread(row)
    if thread is None:
        return
    panel_message = None
    if row.get("panel_message_id"):
        try:
            panel_message = await thread.fetch_message(int(row["panel_message_id"]))
        except Exception:
            panel_message = None
    if panel_message is None and not row.get("journeyed"):
        panel_message = await _recreate_panel_if_missing(user_id, row, thread)
        row = database.fetch_pet(user_id)

    prev_call = row["call_flag"]
    prev_reason = row["call_reason"]
    now = int(time.time())
    row, evo_messages, warning, event = game_logic.update_over_time(user_id, row)

    if row["journeyed"]:
        if panel_message:
            embed = await build_embed(row, transient=transient)
            try:
                await panel_message.edit(content="🌟 この子は旅立ちました。", embed=embed, view=None)
            except Exception:
                pass
        if evo_messages:
            await upsert_system_log(thread, user_id, "\n".join(evo_messages))
            owned = database.fetch_collection(user_id)
            character_name = CHARACTERS[owned[-1]["character_id"]]["name"] if owned else CHARACTERS[row["character_id"]]["name"]
            letter_embed = await build_letter_embed(character_name)
            if letter_embed:
                await thread.send(embed=letter_embed)
        return

    if panel_message is None:
        return

    embed = await build_embed(row, transient=transient)
    content = prefix if prefix else None
    if warning:
        await upsert_system_log(thread, user_id, warning)
    if event:
        await upsert_system_log(thread, user_id, event)
    if evo_messages:
        await upsert_system_log(thread, user_id, "\n".join(evo_messages))

    if row["call_flag"] and ((not prev_call) or (prev_reason != row["call_reason"]) or remind_due(row, now)):
        call_text = game_logic.call_message_text(f"<@{user_id}>", row) or "● 注意アイコン点灯中\n🔔 おせわサイン"
        await upsert_alert_log(thread, user_id, call_text)
        database.update_pet(user_id, last_call_notified_at=now)
    else:
        special_sign = current_special_sign_text(row, user_id)
        if special_sign and not row["call_flag"]:
            await upsert_alert_log(thread, user_id, special_sign)
        elif not row["call_flag"] and prev_call:
            await upsert_alert_log(thread, user_id, "○ 注意アイコン消灯\nいまはだいじょうぶ。\nまたようすをみてね。")

    await panel_message.edit(content=content, embed=embed, view=PetView(user_id))
    register_pet_view(user_id, panel_message.id)


async def ensure_main_panel():
    if not ENTRY_CHANNEL_ID:
        return
    await bot.wait_until_ready()
    channel = bot.get_channel(ENTRY_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(ENTRY_CHANNEL_ID)
        except Exception:
            return
    if not isinstance(channel, discord.TextChannel):
        return
    panel_id = database.get_meta("main_panel_message_id")
    if panel_id:
        try:
            message = await channel.fetch_message(int(panel_id))
            await message.edit(content=f"**{WELCOME_MARKER}**\n育成開始を押して遊んでね。", view=MainPanelView())
            await cleanup_old_main_panels(channel, keep_message_id=message.id)
            return
        except Exception:
            pass
    message = await channel.send(f"**{WELCOME_MARKER}**\n育成開始を押して遊んでね。", view=MainPanelView())
    database.set_meta("main_panel_message_id", str(message.id))
    await cleanup_old_main_panels(channel, keep_message_id=message.id)


async def auto_tick_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        for user_id in database.fetch_active_pet_ids():
            try:
                await refresh_panel_for_user(user_id)
            except Exception:
                pass
        await asyncio.sleep(60)


def register_pet_view(owner_id: int, message_id: int | str | None):
    if not message_id:
        return
    try:
        message_id_int = int(message_id)
    except Exception:
        return
    if message_id_int in _registered_pet_message_ids:
        return
    bot.add_view(PetView(owner_id), message_id=message_id_int)
    _registered_pet_message_ids.add(message_id_int)


async def register_persistent_views():
    bot.add_view(MainPanelView())
    for row in database.fetch_active_pets():
        if row.get("panel_message_id"):
            register_pet_view(int(row["user_id"]), int(row["panel_message_id"]))


class MainPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="育成開始", style=discord.ButtonStyle.green, custom_id="main:start")
    async def start(self, interaction: discord.Interaction, _button: discord.ui.Button):
        user = interaction.user
        guild = interaction.guild
        if guild is None:
            return await send_temp_interaction_message(interaction, "サーバー内で使ってね。")
        row = database.fetch_pet(user.id)
        if row and not row["journeyed"]:
            return await send_temp_interaction_message(interaction, "すでに育成中のデータがあるよ。『育成の続きから』を押して再開してね。")
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await send_temp_interaction_message(interaction, "テキストチャンネルで使ってね。")
        try:
            thread = await create_clean_thread(channel, f"{user.display_name}っち")
            row, _ = game_logic.start_pet_if_needed(user.id, guild.id, thread.id)
            embed = await build_embed(row)
            panel = await thread.send(f"{user.mention} の育成スレッドができたよ！", embed=embed, view=PetView(user.id))
            database.update_pet(user.id, panel_message_id=str(panel.id), thread_id=str(thread.id), system_message_id=None, alert_message_id=None)
            register_pet_view(user.id, panel.id)
            await upsert_alert_log(thread, user.id, "○ 注意アイコン消灯\nいまはだいじょうぶ。\nまたようすをみてね。")
            await send_temp_interaction_message(interaction, f"育成を開始したよ！ {thread.mention}")
        except Exception as exc:
            await send_temp_interaction_message(interaction, f"育成開始に失敗したよ。\n`{type(exc).__name__}`")

    @discord.ui.button(label="育成の続きから", style=discord.ButtonStyle.blurple, custom_id="main:continue")
    async def continue_btn(self, interaction: discord.Interaction, _button: discord.ui.Button):
        user = interaction.user
        guild = interaction.guild
        if guild is None:
            return await send_temp_interaction_message(interaction, "サーバー内で使ってね。")
        try:
            database.init_db()
            row = database.fetch_pet(user.id)
        except sqlite3.OperationalError as exc:
            return await send_temp_interaction_message(interaction, f"続きからの復帰に失敗したよ。\n`{type(exc).__name__}`")
        if not row or row["journeyed"]:
            return await send_temp_interaction_message(interaction, "続きの育成データが見つからないよ。『育成開始』から始めてね。")
        thread = await _resolve_thread(row)
        try:
            if thread is None:
                channel = interaction.channel
                if not isinstance(channel, discord.TextChannel):
                    return await send_temp_interaction_message(interaction, "テキストチャンネルで使ってね。")
                new_thread = await create_clean_thread(channel, f"{user.display_name}っち-つづき")
                database.update_pet(user.id, thread_id=str(new_thread.id), panel_message_id=None, system_message_id=None, alert_message_id=None)
                row = database.fetch_pet(user.id)
                embed = await build_embed(row)
                panel = await new_thread.send(f"{user.mention} の育成データを続きから復帰したよ！", embed=embed, view=PetView(user.id))
                database.update_pet(user.id, panel_message_id=str(panel.id))
                register_pet_view(user.id, panel.id)
                await upsert_alert_log(new_thread, user.id, "○ 注意アイコン消灯\nいまはだいじょうぶ。\nまたようすをみてね。")
                return await send_temp_interaction_message(interaction, f"育成データを復帰したよ！ {new_thread.mention}")
            panel_ok = False
            if row.get("panel_message_id"):
                try:
                    await thread.fetch_message(int(row["panel_message_id"]))
                    panel_ok = True
                except Exception:
                    panel_ok = False
            if not panel_ok:
                embed = await build_embed(row)
                panel = await thread.send(f"{user.mention} の育成パネルを再作成したよ！", embed=embed, view=PetView(user.id))
                database.update_pet(user.id, panel_message_id=str(panel.id))
                register_pet_view(user.id, panel.id)
            if not row.get("alert_message_id"):
                await upsert_alert_log(thread, user.id, "○ 注意アイコン消灯\nいまはだいじょうぶ。\nまたようすをみてね。")
            await send_temp_interaction_message(interaction, f"続きから再開できるよ！ {thread.mention}")
        except Exception as exc:
            await send_temp_interaction_message(interaction, f"続きからの復帰に失敗したよ。\n`{type(exc).__name__}`")

    @discord.ui.button(label="図鑑", style=discord.ButtonStyle.gray, custom_id="main:dex")
    async def dex(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await send_temp_interaction_message(interaction, game_logic.build_dex_text(interaction.user.id), view=DexView(interaction.user.id, 0), seconds=20)

    @discord.ui.button(label="あそびかた", style=discord.ButtonStyle.gray, custom_id="main:help")
    async def help_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await send_temp_interaction_message(interaction, "【あそびかた】\n・呼出しログは注意アイコンのかわりだよ\n・ようすでチェックメーターが見られる\n・でんきで眠る準備ができる\n・わがままサインが出たらしつけのチャンス\n・キラキラした時は ほめる のチャンス\n・おるすばん中は基本操作が止まるよ", seconds=20)


class PetView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=None)
        self.owner_id = owner_id

    async def _owner_check(self, interaction: discord.Interaction) -> bool:
        if not is_owner(interaction, self.owner_id):
            await send_temp_interaction_message(interaction, "この子のお世話は本人だけができるよ。")
            return False
        return True

    async def _do_action(self, interaction: discord.Interaction, action: str):
        row = database.fetch_pet(self.owner_id)
        row, result, messages, transient = game_logic.perform_action(self.owner_id, row, action)
        await interaction.response.defer()
        await refresh_panel_for_user(self.owner_id, prefix="" if action == "status" else result, transient=transient)
        thread = interaction.channel
        if isinstance(thread, discord.Thread):
            latest_row = database.fetch_pet(self.owner_id)
            if result:
                title = "【チェック画面】" if action == "status" else "🫧 おせわけっか"
                await upsert_alert_log(thread, self.owner_id, compose_result_alert(title, result, latest_row, self.owner_id))
            if messages:
                await upsert_system_log(thread, self.owner_id, "\n".join(messages))

    @discord.ui.button(label="ごはん", style=discord.ButtonStyle.green, custom_id="pet:feed")
    async def feed(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "feed")

    @discord.ui.button(label="おやつ", style=discord.ButtonStyle.blurple, custom_id="pet:snack")
    async def snack(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "snack")

    @discord.ui.button(label="あそぶ", style=discord.ButtonStyle.blurple, row=1, custom_id="pet:play")
    async def play(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "play")

    @discord.ui.button(label="でんき", style=discord.ButtonStyle.gray, row=1, custom_id="pet:sleep")
    async def sleep(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "sleep")

    @discord.ui.button(label="ようす", style=discord.ButtonStyle.gray, row=1, custom_id="pet:status")
    async def status(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "status")

    @discord.ui.button(label="しつけ", style=discord.ButtonStyle.red, row=2, custom_id="pet:discipline")
    async def discipline(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "discipline")

    @discord.ui.button(label="ほめる", style=discord.ButtonStyle.green, row=2, custom_id="pet:praise")
    async def praise(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "praise")

    @discord.ui.button(label="おそうじ", style=discord.ButtonStyle.red, row=2, custom_id="pet:clean")
    async def clean(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "clean")

    @discord.ui.button(label="おくすり", style=discord.ButtonStyle.red, row=2, custom_id="pet:medicine")
    async def medicine(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "medicine")

    @discord.ui.button(label="ミニゲーム", style=discord.ButtonStyle.green, row=3, custom_id="pet:minigame")
    async def minigame(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not await self._owner_check(interaction):
            return
        row = database.fetch_pet(self.owner_id)
        _, err = game_logic.start_minigame(self.owner_id, row, "rhythm")
        if err:
            return await send_temp_interaction_message(interaction, err)
        await send_temp_interaction_message(interaction, "あそぶ音楽ゲームを選んでね。", view=MiniGameMenuView(self.owner_id), seconds=15)

    @discord.ui.button(label="おるすばん開始", style=discord.ButtonStyle.blurple, row=3, custom_id="pet:odekake_start")
    async def odekake_start(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not await self._owner_check(interaction):
            return
        row = database.fetch_pet(self.owner_id)
        row, message = game_logic.start_odekake(self.owner_id, row)
        await interaction.response.defer()
        await refresh_panel_for_user(self.owner_id, prefix=message)
        if isinstance(interaction.channel, discord.Thread):
            await upsert_alert_log(interaction.channel, self.owner_id, compose_result_alert("🏠 おるすばん", message, database.fetch_pet(self.owner_id), self.owner_id))

    @discord.ui.button(label="おるすばん終了", style=discord.ButtonStyle.blurple, row=4, custom_id="pet:odekake_end")
    async def odekake_end(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not await self._owner_check(interaction):
            return
        row = database.fetch_pet(self.owner_id)
        row, message, extra = game_logic.stop_odekake(self.owner_id, row)
        await interaction.response.defer()
        await refresh_panel_for_user(self.owner_id, prefix=message)
        if isinstance(interaction.channel, discord.Thread):
            await upsert_alert_log(interaction.channel, self.owner_id, compose_result_alert("🏠 おるすばん", message, database.fetch_pet(self.owner_id), self.owner_id))
            if extra:
                await upsert_system_log(interaction.channel, self.owner_id, "\n".join(extra))

    @discord.ui.button(label="設定", style=discord.ButtonStyle.gray, row=4, custom_id="pet:settings")
    async def settings(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not await self._owner_check(interaction):
            return
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, render_settings_text(self.owner_id, row), view=SettingsView(self.owner_id), seconds=30)



class ClockSetModal(discord.ui.Modal, title="時計を合わせる"):
    clock_text = discord.ui.TextInput(label="表示したい時刻", placeholder="21:30", required=True, max_length=5)

    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await send_temp_interaction_message(interaction, "本人だけ変更できるよ。")
        try:
            new_time = game_logic.set_display_clock_to_hhmm(self.owner_id, str(self.clock_text))
            row = database.fetch_pet(self.owner_id)
            await send_temp_interaction_message(interaction, f"表示時間を **{new_time}** に合わせたよ。\n\n{render_settings_text(self.owner_id, row)}", seconds=25)
        except Exception:
            await send_temp_interaction_message(interaction, "時刻は `HH:MM` 形式で入れてね。例: `21:30`")


class SleepWindowModal(discord.ui.Modal, title="ねる時間を設定"):
    start_text = discord.ui.TextInput(label="ねはじめ", placeholder="22:00", required=True, max_length=5)
    end_text = discord.ui.TextInput(label="おきる時間", placeholder="07:00", required=True, max_length=5)

    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await send_temp_interaction_message(interaction, "本人だけ変更できるよ。")
        try:
            start, end = game_logic.set_sleep_window(self.owner_id, str(self.start_text), str(self.end_text))
            row = database.fetch_pet(self.owner_id)
            await send_temp_interaction_message(interaction, f"ねる時間を **{start}〜{end}** にしたよ。\n\n{render_settings_text(self.owner_id, row)}", seconds=25)
        except Exception:
            await send_temp_interaction_message(interaction, "時間は `HH:MM` 形式で入れてね。例: `22:00` と `07:00`")


class SettingsView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    async def _owner_only(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await send_temp_interaction_message(interaction, "本人だけ変更できるよ。")
            return False
        return True

    @discord.ui.button(label="通知:たまごっち", style=discord.ButtonStyle.green)
    async def nt1(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        database.update_pet(self.owner_id, notification_mode="tamagotchi")
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, "通知モードを『たまごっち』にしたよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="通知:ふつう", style=discord.ButtonStyle.blurple)
    async def nt2(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        database.update_pet(self.owner_id, notification_mode="normal")
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, "通知モードを『ふつう』にしたよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="通知:静か", style=discord.ButtonStyle.gray, row=1)
    async def nt3(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        database.update_pet(self.owner_id, notification_mode="quiet")
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, "通知モードを『静か』にしたよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="通知:ミュート", style=discord.ButtonStyle.red, row=1)
    async def nt4(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        database.update_pet(self.owner_id, notification_mode="mute")
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, "通知モードを『ミュート』にしたよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="音:ON", style=discord.ButtonStyle.green, row=2)
    async def sound_on(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        database.update_pet(self.owner_id, sound_enabled=1)
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, "音をONにしたよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="音:OFF", style=discord.ButtonStyle.gray, row=2)
    async def sound_off(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        database.update_pet(self.owner_id, sound_enabled=0)
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, "音をOFFにしたよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="時計を合わせる", style=discord.ButtonStyle.blurple, row=3)
    async def set_clock(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        await interaction.response.send_modal(ClockSetModal(self.owner_id))

    @discord.ui.button(label="時計+1時間", style=discord.ButtonStyle.green, row=3)
    async def clock_plus(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        offset = game_logic.adjust_display_clock(self.owner_id, 60)
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, f"時計を +1時間 したよ。\n時計補正: {offset}\n\n{render_settings_text(self.owner_id, row)}", seconds=25)

    @discord.ui.button(label="時計-1時間", style=discord.ButtonStyle.red, row=3)
    async def clock_minus(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        offset = game_logic.adjust_display_clock(self.owner_id, -60)
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, f"時計を -1時間 したよ。\n時計補正: {offset}\n\n{render_settings_text(self.owner_id, row)}", seconds=25)

    @discord.ui.button(label="時計をJSTに戻す", style=discord.ButtonStyle.gray, row=4)
    async def clock_reset(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        game_logic.reset_display_clock(self.owner_id)
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, "時計を日本時間に戻したよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="ねる時間を設定", style=discord.ButtonStyle.gray, row=4)
    async def set_sleep_window(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        await interaction.response.send_modal(SleepWindowModal(self.owner_id))


class MiniGameMenuView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    async def send_game(self, interaction: discord.Interaction, key: str):
        row = database.fetch_pet(self.owner_id)
        game, err = game_logic.start_minigame(self.owner_id, row, key)
        if err:
            return await send_temp_interaction_message(interaction, err)
        await send_temp_interaction_message(interaction, f"**{game['title']}**\n{game['question']}", view=MiniGameAnswerView(self.owner_id, key), seconds=15)

    @discord.ui.button(label="リズム", style=discord.ButtonStyle.green)
    async def rhythm(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self.send_game(interaction, "rhythm")

    @discord.ui.button(label="音あて", style=discord.ButtonStyle.green)
    async def instrument(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self.send_game(interaction, "instrument")

    @discord.ui.button(label="メロディ", style=discord.ButtonStyle.green)
    async def melody(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self.send_game(interaction, "melody")


class MiniGameAnswerView(discord.ui.View):
    def __init__(self, owner_id: int, game_key: str):
        super().__init__(timeout=180)
        game = MUSIC_GAMES[game_key]
        for idx, choice in enumerate(game["choices"]):
            self.add_item(MiniGameChoiceButton(owner_id, game_key, idx, choice))


class MiniGameChoiceButton(discord.ui.Button):
    def __init__(self, owner_id: int, game_key: str, idx: int, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.blurple)
        self.owner_id = owner_id
        self.game_key = game_key
        self.idx = idx

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await send_temp_interaction_message(interaction, "本人だけが遊べるよ。")
        row = database.fetch_pet(self.owner_id)
        _, msg, evo = game_logic.resolve_minigame(self.owner_id, row, self.game_key, self.idx)
        await interaction.response.edit_message(content="このミニゲームは終了したよ。", view=None)
        await asyncio.sleep(2)
        try:
            await interaction.delete_original_response()
        except Exception:
            pass
        await refresh_panel_for_user(self.owner_id)
        if isinstance(interaction.channel, discord.Thread):
            latest_row = database.fetch_pet(self.owner_id)
            body = compose_result_alert("🎮 ミニゲームけっか", msg + ("\n" + "\n".join(evo) if evo else ""), latest_row, self.owner_id)
            await upsert_alert_log(interaction.channel, self.owner_id, body)


class DexView(discord.ui.View):
    def __init__(self, owner_id: int, page: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.page = page
        owned_rows = database.fetch_collection(owner_id)
        owned_ids = [row["character_id"] for row in owned_rows]
        owned_target_ids = [cid for cid in DEX_TARGETS if cid in owned_ids]
        per_page = 4
        chunk = owned_target_ids[page * per_page:(page + 1) * per_page]
        if chunk:
            options = [discord.SelectOption(label=CHARACTERS[cid]["name"], value=cid) for cid in chunk]
            self.add_item(DexSelect(owner_id, options))
        if page > 0:
            self.add_item(DexNavButton(owner_id, page - 1, "前へ"))
        if (page + 1) * per_page < len(owned_target_ids):
            self.add_item(DexNavButton(owner_id, page + 1, "次へ"))


class DexSelect(discord.ui.Select):
    def __init__(self, owner_id: int, options):
        super().__init__(placeholder="詳細を見るキャラを選んでね", options=options)
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await send_temp_interaction_message(interaction, "これはあなたの図鑑表示だよ。")
        await send_temp_interaction_message(interaction, game_logic.build_dex_detail(self.owner_id, self.values[0]), seconds=20)


class DexNavButton(discord.ui.Button):
    def __init__(self, owner_id: int, page: int, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.gray)
        self.owner_id = owner_id
        self.page = page

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await send_temp_interaction_message(interaction, "これはあなたの図鑑表示だよ。")
        await interaction.response.edit_message(content=game_logic.build_dex_text(self.owner_id), view=DexView(self.owner_id, self.page))


@bot.event
async def on_ready():
    global _background_started
    database.init_db()
    await register_persistent_views()
    print(f"Logged in as {bot.user}")
    if not _background_started:
        bot.loop.create_task(ensure_main_panel())
        bot.loop.create_task(auto_tick_loop())
        _background_started = True


@bot.command()
async def setup_panel(ctx: commands.Context):
    if ADMIN_USER_IDS and ctx.author.id not in ADMIN_USER_IDS:
        return await ctx.send("管理者だけが使えるよ。")
    channel = ctx.channel
    if isinstance(channel, discord.TextChannel):
        message = await channel.send(f"**{WELCOME_MARKER}**\n育成開始を押して遊んでね。", view=MainPanelView())
        database.set_meta("main_panel_message_id", str(message.id))
        await cleanup_old_main_panels(channel, keep_message_id=message.id)


if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN が設定されていません。config.py を確認してください。")
    bot.run(DISCORD_BOT_TOKEN)
