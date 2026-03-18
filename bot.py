from __future__ import annotations

import asyncio
import os
import time
from typing import Optional

import discord
from discord.ext import commands

import database
import game_logic
import image_service
from game_data import CHARACTERS, MUSIC_GAMES

try:
    from config import DISCORD_BOT_TOKEN, ENTRY_CHANNEL_ID  # type: ignore
except Exception:
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
    ENTRY_CHANNEL_ID = int(os.getenv("ENTRY_CHANNEL_ID", "0") or 0)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

BOT_VERSION = "fresh-overhaul-v1"
WELCOME_MARKER = "○○っちへようこそ！"
TEMP_SECONDS = 10


async def send_temp(interaction: discord.Interaction, content: str, *, view: Optional[discord.ui.View] = None, embed: Optional[discord.Embed] = None, ephemeral: bool = True, seconds: int = TEMP_SECONDS):
    kwargs = {"content": content, "embed": embed, "ephemeral": ephemeral}
    if view is not None:
        kwargs["view"] = view
    if not interaction.response.is_done():
        await interaction.response.send_message(**kwargs)
    else:
        await interaction.followup.send(**kwargs)
    if ephemeral:
        return
    await asyncio.sleep(seconds)


async def build_embed(user_id: int, row: dict, transient: Optional[str] = None) -> discord.Embed:
    embed = discord.Embed(description=game_logic.status_lines(row))
    keys = game_logic.image_keys_for_pet(row, transient=transient)
    url = await image_service.find_first_image_url(bot, keys)
    if url:
        embed.set_image(url=url)
    return embed


async def build_letter_embed(row: dict) -> Optional[discord.Embed]:
    keys = game_logic.letter_image_keys(row)
    if not keys:
        return None
    url = await image_service.find_first_image_url(bot, keys)
    if not url:
        return None
    embed = discord.Embed(title=f"{game_logic.pet_name(row)} から手紙が届いています…")
    embed.set_image(url=url)
    return embed


async def upsert_log(thread: discord.Thread, user_id: int, field_name: str, title: str, text: str) -> None:
    row = database.fetch_pet(user_id)
    if not row:
        return
    message_id = row.get(field_name, "")
    content = f"【{title}】\n{text}"
    if message_id:
        try:
            msg = await thread.fetch_message(int(message_id))
            await msg.edit(content=content)
            return
        except Exception:
            pass
    msg = await thread.send(content)
    database.update_pet(user_id, **{field_name: str(msg.id)})


async def refresh_pet_panel(user_id: int, *, prefix: str = "", transient: Optional[str] = None) -> None:
    row = game_logic.maybe_cleanup_broken_pet(user_id)
    if not row:
        return
    thread_id = row.get("thread_id")
    panel_id = row.get("panel_message_id")
    if not thread_id or not panel_id:
        return
    try:
        thread = bot.get_channel(int(thread_id)) or await bot.fetch_channel(int(thread_id))
    except Exception:
        return
    if not isinstance(thread, discord.Thread):
        return
    try:
        message = await thread.fetch_message(int(panel_id))
    except Exception:
        return

    before_call = bool(row.get("call_flag"))
    row, evo_msgs, warning, _ = game_logic.update_over_time(user_id, row)
    embed = await build_embed(user_id, row, transient=transient)
    await message.edit(content=(prefix or None), embed=embed, view=PetView(user_id))

    if warning:
        await upsert_log(thread, user_id, "system_message_id", "システムログ", warning)
    if evo_msgs:
        await upsert_log(thread, user_id, "system_message_id", "システムログ", "\n".join(evo_msgs))
        if row.get("journeyed"):
            letter = await build_letter_embed(row)
            if letter:
                await thread.send(embed=letter)
    if row.get("call_flag"):
        text = game_logic.call_message_text(f"<@{user_id}>", row)
        if text:
            await upsert_log(thread, user_id, "alert_message_id", "呼出しログ", text)
    elif before_call:
        await upsert_log(thread, user_id, "alert_message_id", "呼出しログ", "○ 注意アイコン消灯\nいまはだいじょうぶ。")


async def create_clean_thread(parent: discord.TextChannel, name: str) -> discord.Thread:
    return await parent.create_thread(name=name, type=discord.ChannelType.public_thread, auto_archive_duration=60)


async def ensure_main_panel() -> None:
    if not ENTRY_CHANNEL_ID:
        return
    await bot.wait_until_ready()
    try:
        channel = bot.get_channel(ENTRY_CHANNEL_ID) or await bot.fetch_channel(ENTRY_CHANNEL_ID)
    except Exception:
        return
    if not isinstance(channel, discord.TextChannel):
        return
    message_id = database.get_meta("main_panel_message_id")
    content = f"**{WELCOME_MARKER}**\n育成開始を押して遊んでね。"
    if message_id:
        try:
            msg = await channel.fetch_message(int(message_id))
            await msg.edit(content=content, view=MainPanelView())
            return
        except Exception:
            pass
    msg = await channel.send(content, view=MainPanelView())
    database.set_meta("main_panel_message_id", str(msg.id))


async def auto_tick_loop() -> None:
    await bot.wait_until_ready()
    while not bot.is_closed():
        for user_id in database.list_active_pet_user_ids():
            try:
                await refresh_pet_panel(user_id)
            except Exception:
                continue
        await asyncio.sleep(60)


class MainPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="育成開始", style=discord.ButtonStyle.green, custom_id="main:start")
    async def start_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
            return await send_temp(interaction, "サーバーのテキストチャンネルで使ってね。")
        has_pet, row = game_logic.start_or_resume_ready(interaction.user.id)
        if has_pet and row and not row.get("journeyed"):
            return await send_temp(interaction, "すでに育成中のデータがあるよ。『育成の続きから』を押してね。")
        thread = await create_clean_thread(interaction.channel, f"{interaction.user.display_name}っち")
        row = game_logic.start_new_pet(interaction.user.id, interaction.guild.id, thread.id)
        embed = await build_embed(interaction.user.id, row)
        panel = await thread.send(f"{interaction.user.mention} の育成スレッドができたよ！", embed=embed, view=PetView(interaction.user.id))
        database.update_pet(interaction.user.id, thread_id=str(thread.id), panel_message_id=str(panel.id))
        await upsert_log(thread, interaction.user.id, "system_message_id", "システムログ", "育成を開始したよ。")
        await send_temp(interaction, f"育成スレッドを作ったよ！\n{thread.mention} を見てね。")

    @discord.ui.button(label="育成の続きから", style=discord.ButtonStyle.blurple, custom_id="main:continue")
    async def continue_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
            return await send_temp(interaction, "サーバーのテキストチャンネルで使ってね。")
        has_pet, row = game_logic.start_or_resume_ready(interaction.user.id)
        if not has_pet or not row:
            return await send_temp(interaction, "続きの育成データが見つからないよ。『育成開始』から始めてね。")

        thread = None
        if row.get("thread_id"):
            try:
                thread = bot.get_channel(int(row["thread_id"])) or await bot.fetch_channel(int(row["thread_id"]))
            except Exception:
                thread = None
        if not isinstance(thread, discord.Thread):
            thread = await create_clean_thread(interaction.channel, f"{interaction.user.display_name}っち")
            database.update_pet(interaction.user.id, thread_id=str(thread.id), panel_message_id="", system_message_id="", alert_message_id="")

        row = database.fetch_pet(interaction.user.id) or row
        embed = await build_embed(interaction.user.id, row)
        panel_id = row.get("panel_message_id")
        if panel_id:
            try:
                msg = await thread.fetch_message(int(panel_id))
                await msg.edit(content=f"{interaction.user.mention} の育成を再開したよ！", embed=embed, view=PetView(interaction.user.id))
            except Exception:
                panel = await thread.send(f"{interaction.user.mention} の育成を再開したよ！", embed=embed, view=PetView(interaction.user.id))
                database.update_pet(interaction.user.id, panel_message_id=str(panel.id))
        else:
            panel = await thread.send(f"{interaction.user.mention} の育成を再開したよ！", embed=embed, view=PetView(interaction.user.id))
            database.update_pet(interaction.user.id, panel_message_id=str(panel.id))
        await send_temp(interaction, f"続きの育成を開いたよ！\n{thread.mention} を見てね。")

    @discord.ui.button(label="図鑑", style=discord.ButtonStyle.gray, custom_id="main:dex")
    async def dex_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await send_temp(interaction, game_logic.dex_text(interaction.user.id), seconds=20)

    @discord.ui.button(label="あそびかた", style=discord.ButtonStyle.gray, custom_id="main:howto")
    async def howto_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await send_temp(interaction, game_logic.how_to_text(), seconds=20)


class PetView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        row = database.fetch_pet(owner_id)
        if row and not game_logic.poop_enabled(row):
            # remove clean button by not adding one later
            pass

    async def _owner_only(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await send_temp(interaction, "本人だけ操作できるよ。")
            return False
        return True

    async def _do(self, interaction: discord.Interaction, action: str):
        if not await self._owner_only(interaction):
            return
        row = game_logic.maybe_cleanup_broken_pet(self.owner_id)
        if not row:
            return await send_temp(interaction, "育成データが見つからないよ。『育成開始』から始めてね。")
        row, msg, transient = game_logic.do_action(self.owner_id, row, action)
        await refresh_pet_panel(self.owner_id, prefix=msg, transient=transient)
        await interaction.response.defer()

    @discord.ui.button(label="ごはん", style=discord.ButtonStyle.green, row=0, custom_id="pet:feed")
    async def feed(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._do(interaction, "feed")

    @discord.ui.button(label="おやつ", style=discord.ButtonStyle.green, row=0, custom_id="pet:snack")
    async def snack(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._do(interaction, "snack")

    @discord.ui.button(label="あそぶ", style=discord.ButtonStyle.blurple, row=0, custom_id="pet:play")
    async def play(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._do(interaction, "play")

    @discord.ui.button(label="でんき", style=discord.ButtonStyle.gray, row=0, custom_id="pet:light")
    async def light(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._do(interaction, "light")

    @discord.ui.button(label="ようす", style=discord.ButtonStyle.gray, row=1, custom_id="pet:status")
    async def status(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        row = game_logic.maybe_cleanup_broken_pet(self.owner_id)
        if not row:
            return await send_temp(interaction, "育成データが見つからないよ。")
        await send_temp(interaction, game_logic.build_check_text(self.owner_id, row), seconds=25)
        row, msg, _ = game_logic.do_action(self.owner_id, row, "status")
        await refresh_pet_panel(self.owner_id, prefix=msg)

    @discord.ui.button(label="しつけ", style=discord.ButtonStyle.blurple, row=1, custom_id="pet:discipline")
    async def discipline(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._do(interaction, "discipline")

    @discord.ui.button(label="ほめる", style=discord.ButtonStyle.blurple, row=1, custom_id="pet:praise")
    async def praise(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._do(interaction, "praise")

    @discord.ui.button(label="おそうじ", style=discord.ButtonStyle.gray, row=2, custom_id="pet:clean")
    async def clean(self, interaction: discord.Interaction, _: discord.ui.Button):
        row = database.fetch_pet(self.owner_id)
        if row and not game_logic.poop_enabled(row):
            return await send_temp(interaction, "この段階では おそうじ は必要ないよ。")
        await self._do(interaction, "clean")

    @discord.ui.button(label="おくすり", style=discord.ButtonStyle.gray, row=2, custom_id="pet:medicine")
    async def medicine(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._do(interaction, "medicine")

    @discord.ui.button(label="ミニゲーム", style=discord.ButtonStyle.green, row=2, custom_id="pet:minigame")
    async def minigame(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        await send_temp(interaction, "あそびを選んでね。", view=MiniGameMenuView(self.owner_id), seconds=20)

    @discord.ui.button(label="設定", style=discord.ButtonStyle.gray, row=3, custom_id="pet:settings")
    async def settings(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        row = database.fetch_pet(self.owner_id)
        if not row:
            return await send_temp(interaction, "育成データが見つからないよ。")
        await send_temp(interaction, render_settings_text(self.owner_id, row), view=SettingsView(self.owner_id), seconds=30)

    @discord.ui.button(label="おるすばん開始", style=discord.ButtonStyle.red, row=4, custom_id="pet:away_start")
    async def away_start(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._do(interaction, "away_start")

    @discord.ui.button(label="おるすばん終了", style=discord.ButtonStyle.green, row=4, custom_id="pet:away_end")
    async def away_end(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._do(interaction, "away_end")


class ClockSetModal(discord.ui.Modal, title="時計を合わせる"):
    target_time = discord.ui.TextInput(label="合わせたい時間", placeholder="例: 21:30", required=True, max_length=5)

    def __init__(self, owner_id: int):
        super().__init__()
        self.owner_id = owner_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await send_temp(interaction, "本人だけ変更できるよ。")
        try:
            game_logic.set_display_clock_to_hhmm(self.owner_id, str(self.target_time))
            row = database.fetch_pet(self.owner_id) or database.create_new_pet(self.owner_id, interaction.guild.id if interaction.guild else 0, 0)
            await send_temp(interaction, f"時計を **{self.target_time}** に合わせたよ。\n\n{render_settings_text(self.owner_id, row)}", seconds=25)
        except Exception:
            await send_temp(interaction, "時間の書き方がちがうよ。`21:30` みたいに入れてね。")


class SleepWindowModal(discord.ui.Modal, title="ねる時間を設定"):
    sleep_start = discord.ui.TextInput(label="ねる時間", placeholder="例: 22:00", required=True, max_length=5)
    sleep_end = discord.ui.TextInput(label="おきる時間", placeholder="例: 07:00", required=True, max_length=5)

    def __init__(self, owner_id: int):
        super().__init__()
        self.owner_id = owner_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await send_temp(interaction, "本人だけ変更できるよ。")
        try:
            start = game_logic.normalize_hhmm(str(self.sleep_start))
            end = game_logic.normalize_hhmm(str(self.sleep_end))
            database.set_sleep_setting(self.owner_id, start, end)
            row = database.fetch_pet(self.owner_id) or database.create_new_pet(self.owner_id, interaction.guild.id if interaction.guild else 0, 0)
            await send_temp(interaction, f"ねる時間を **{start}〜{end}** にしたよ。\n\n{render_settings_text(self.owner_id, row)}", seconds=25)
        except Exception:
            await send_temp(interaction, "時間の書き方がちがうよ。`22:00` と `07:00` みたいに入れてね。")


class SettingsView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    async def _owner_only(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await send_temp(interaction, "本人だけ変更できるよ。")
            return False
        return True

    @discord.ui.button(label="通知:たまごっち", style=discord.ButtonStyle.green, row=0)
    async def nt_tama(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        database.update_pet(self.owner_id, notification_mode="tamagotchi")
        row = database.fetch_pet(self.owner_id)
        await send_temp(interaction, "通知モードを『たまごっち』にしたよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="通知:ふつう", style=discord.ButtonStyle.blurple, row=0)
    async def nt_normal(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        database.update_pet(self.owner_id, notification_mode="normal")
        row = database.fetch_pet(self.owner_id)
        await send_temp(interaction, "通知モードを『ふつう』にしたよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="通知:静か", style=discord.ButtonStyle.gray, row=1)
    async def nt_quiet(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        database.update_pet(self.owner_id, notification_mode="quiet")
        row = database.fetch_pet(self.owner_id)
        await send_temp(interaction, "通知モードを『静か』にしたよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="通知:ミュート", style=discord.ButtonStyle.red, row=1)
    async def nt_mute(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        database.update_pet(self.owner_id, notification_mode="mute")
        row = database.fetch_pet(self.owner_id)
        await send_temp(interaction, "通知モードを『ミュート』にしたよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="音:ON", style=discord.ButtonStyle.green, row=2)
    async def sound_on(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        database.update_pet(self.owner_id, sound_enabled=1)
        row = database.fetch_pet(self.owner_id)
        await send_temp(interaction, "音をONにしたよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="音:OFF", style=discord.ButtonStyle.gray, row=2)
    async def sound_off(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        database.update_pet(self.owner_id, sound_enabled=0)
        row = database.fetch_pet(self.owner_id)
        await send_temp(interaction, "音をOFFにしたよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="時計を合わせる", style=discord.ButtonStyle.blurple, row=3)
    async def set_clock(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        await interaction.response.send_modal(ClockSetModal(self.owner_id))

    @discord.ui.button(label="時計+1時間", style=discord.ButtonStyle.green, row=3)
    async def plus_clock(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        game_logic.adjust_display_clock(self.owner_id, 60)
        row = database.fetch_pet(self.owner_id)
        await send_temp(interaction, "時計を +1時間 したよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="時計-1時間", style=discord.ButtonStyle.red, row=3)
    async def minus_clock(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        game_logic.adjust_display_clock(self.owner_id, -60)
        row = database.fetch_pet(self.owner_id)
        await send_temp(interaction, "時計を -1時間 したよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="時計をJSTに戻す", style=discord.ButtonStyle.gray, row=4)
    async def reset_clock(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        game_logic.reset_display_clock(self.owner_id)
        row = database.fetch_pet(self.owner_id)
        await send_temp(interaction, "時計を日本時間に戻したよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="ねる時間を設定", style=discord.ButtonStyle.gray, row=4)
    async def sleep_window(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        await interaction.response.send_modal(SleepWindowModal(self.owner_id))

    @discord.ui.button(label="データ整理", style=discord.ButtonStyle.red, row=5)
    async def cleanup(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        await send_temp(interaction, "消したい内容を選んでね。", view=CleanupMenuView(self.owner_id), seconds=30)


class CleanupMenuView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    async def _owner_only(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await send_temp(interaction, "本人だけ変更できるよ。")
            return False
        return True

    @discord.ui.button(label="今の育成だけ消す", style=discord.ButtonStyle.red)
    async def delete_pet_only(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        database.delete_pet(self.owner_id)
        await send_temp(interaction, "今の育成データだけ消したよ。『育成開始』から始められるよ。", seconds=20)

    @discord.ui.button(label="図鑑も全部消す", style=discord.ButtonStyle.red)
    async def delete_all(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        database.delete_all_user_data(self.owner_id)
        await send_temp(interaction, "育成データと図鑑を全部消したよ。最初からやり直せるよ。", seconds=20)


class MiniGameMenuView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    async def send_game(self, interaction: discord.Interaction, game_key: str):
        row = database.fetch_pet(self.owner_id)
        if not row:
            return await send_temp(interaction, "育成データが見つからないよ。")
        game, err = game_logic.start_minigame(self.owner_id, row, game_key)
        if err:
            return await send_temp(interaction, err)
        await send_temp(interaction, f"**{game['title']}**\n{game['question']}", view=MiniGameAnswerView(self.owner_id, game_key), seconds=20)

    @discord.ui.button(label="リズム", style=discord.ButtonStyle.green)
    async def rhythm(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.send_game(interaction, "rhythm")

    @discord.ui.button(label="音あて", style=discord.ButtonStyle.green)
    async def instrument(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.send_game(interaction, "instrument")

    @discord.ui.button(label="メロディ", style=discord.ButtonStyle.green)
    async def melody(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.send_game(interaction, "melody")


class MiniGameAnswerView(discord.ui.View):
    def __init__(self, owner_id: int, game_key: str):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.game_key = game_key
        game = MUSIC_GAMES[game_key]
        for index, choice in enumerate(game["choices"]):
            self.add_item(MiniGameChoiceButton(owner_id, game_key, index, choice))


class MiniGameChoiceButton(discord.ui.Button):
    def __init__(self, owner_id: int, game_key: str, answer_index: int, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.blurple)
        self.owner_id = owner_id
        self.game_key = game_key
        self.answer_index = answer_index

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await send_temp(interaction, "本人だけ操作できるよ。")
        row = database.fetch_pet(self.owner_id)
        if not row:
            return await send_temp(interaction, "育成データが見つからないよ。")
        row, msg = game_logic.submit_minigame_answer(self.owner_id, row, self.game_key, self.answer_index)
        await refresh_pet_panel(self.owner_id, prefix=msg)
        await interaction.response.defer()


def render_settings_text(owner_id: int, row: dict) -> str:
    setting = database.fetch_user_settings(owner_id)
    sound = "ON" if row.get("sound_enabled") else "OFF"
    offset = int(setting.get("clock_offset_minutes", 0) or 0)
    sign = "+" if offset >= 0 else "-"
    abs_minutes = abs(offset)
    offset_text = f"{sign}{abs_minutes // 60:02d}:{abs_minutes % 60:02d}"
    return (
        f"通知モード: {game_logic.notification_mode_label(row.get('notification_mode', 'normal'))}\n"
        f"音: {sound}\n"
        f"表示時間: {game_logic.current_time_label(owner_id)}\n"
        f"時計補正: {offset_text}\n"
        f"ねる時間: {setting.get('sleep_start', '22:00')}〜{setting.get('sleep_end', '07:00')}"
    )


@bot.command(name="setup_panel")
async def setup_panel(ctx: commands.Context):
    content = f"**{WELCOME_MARKER}**\n育成開始を押して遊んでね。"
    msg = await ctx.send(content, view=MainPanelView())
    database.set_meta("main_panel_message_id", str(msg.id))


@bot.command(name="image_keys")
async def image_keys_command(ctx: commands.Context):
    row = database.fetch_pet(ctx.author.id)
    if not row:
        return await ctx.reply("育成データがないよ。『育成開始』から始めてね。")
    keys = game_logic.image_keys_for_pet(row)
    await ctx.reply("\n".join(["今さがしにいく画像名:"] + [f"- {k}" for k in keys]))


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} / version={BOT_VERSION}")
    bot.loop.create_task(ensure_main_panel())
    bot.loop.create_task(auto_tick_loop())


if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN が設定されていません")
    bot.run(DISCORD_BOT_TOKEN)
