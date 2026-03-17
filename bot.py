from __future__ import annotations

import asyncio
import os
import time
from typing import Optional

import discord
from discord.ext import commands, tasks

import database
import game_logic
import image_service
from game_data import CHARACTERS, DEX_TARGETS

try:
    from config import DISCORD_BOT_TOKEN as CONFIG_TOKEN, ADMIN_USER_IDS as CONFIG_ADMINS, ENTRY_CHANNEL_ID as CONFIG_ENTRY
except Exception:
    CONFIG_TOKEN = ''
    CONFIG_ADMINS = []
    CONFIG_ENTRY = 0

DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN', CONFIG_TOKEN or '')
ENTRY_CHANNEL_ID = int(os.getenv('ENTRY_CHANNEL_ID', str(CONFIG_ENTRY or 0)) or 0)
WELCOME_MARKER = '○○っちへようこそ！'
BOT_VERSION = 'fresh-rebuild-v1'
TEMP_MESSAGE_SECONDS = 8

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.messages = True
bot = commands.Bot(command_prefix='!', intents=intents)


def is_owner(interaction: discord.Interaction, owner_id: int) -> bool:
    return interaction.user.id == owner_id


async def send_temp_interaction_message(interaction: discord.Interaction, content: Optional[str] = None, *, embed=None, view=None, ephemeral=True, seconds=TEMP_MESSAGE_SECONDS):
    kwargs = {'content': content, 'embed': embed, 'ephemeral': ephemeral}
    if view is not None:
        kwargs['view'] = view
    if not interaction.response.is_done():
        await interaction.response.send_message(**kwargs)
        await asyncio.sleep(seconds)
        try:
            await interaction.delete_original_response()
        except Exception:
            pass
    else:
        try:
            msg = await interaction.followup.send(wait=True, **kwargs)
            await asyncio.sleep(seconds)
            try:
                await msg.delete()
            except Exception:
                pass
        except Exception:
            pass


async def image_url_for_row(row: dict, transient: str | None = None):
    for key in game_logic.image_key_candidates(row, transient=transient):
        try:
            url = await image_service.get_image_url(bot, key)
            if url:
                return url, key
        except Exception:
            continue
    return None, None


async def build_embed(row: dict, user_id: int, transient: str | None = None) -> discord.Embed:
    embed = discord.Embed(description=game_logic.status_lines(row, user_id))
    url, used = await image_url_for_row(row, transient=transient)
    if url:
        embed.set_image(url=url)
    embed.set_footer(text=f'{BOT_VERSION}' + (f' / 画像:{used}' if used else ''))
    return embed


async def build_letter_embed(character_name: str):
    key = f'{character_name}_手紙'
    url = await image_service.get_image_url(bot, key)
    if not url:
        return None
    embed = discord.Embed(title=f'{character_name} から手紙が届いています…')
    embed.set_image(url=url)
    return embed


async def upsert_log_message(thread: discord.Thread, user_id: int, key_name: str, title: str, body: str):
    row = database.fetch_pet(user_id)
    if not row:
        return
    message_id = row.get(key_name, '') or ''
    content = f'【{title}】\n{body}'
    if message_id:
        try:
            msg = await thread.fetch_message(int(message_id))
            await msg.edit(content=content)
            return
        except Exception:
            pass
    msg = await thread.send(content)
    database.update_pet(user_id, **{key_name: str(msg.id)})


async def upsert_system_log(thread: discord.Thread, user_id: int, text: str):
    await upsert_log_message(thread, user_id, 'system_message_id', 'システムログ', text)


async def upsert_alert_log(thread: discord.Thread, user_id: int, text: str):
    await upsert_log_message(thread, user_id, 'alert_message_id', '呼出しログ', text)


async def create_clean_thread(parent_channel: discord.TextChannel, thread_name: str) -> discord.Thread:
    thread = await parent_channel.create_thread(name=thread_name, type=discord.ChannelType.public_thread, auto_archive_duration=60)
    return thread


async def cleanup_old_main_panels(channel: discord.TextChannel, keep_message_id=None):
    try:
        async for m in channel.history(limit=50):
            if m.author.id != bot.user.id or not m.content or WELCOME_MARKER not in m.content:
                continue
            if keep_message_id and m.id == keep_message_id:
                continue
            try:
                await m.delete()
            except Exception:
                pass
    except Exception:
        pass


async def ensure_main_panel(channel: discord.TextChannel | None = None):
    if channel is None:
        if not ENTRY_CHANNEL_ID:
            return
        channel = bot.get_channel(ENTRY_CHANNEL_ID)
        if channel is None:
            try:
                channel = await bot.fetch_channel(ENTRY_CHANNEL_ID)
            except Exception:
                return
    if not isinstance(channel, discord.TextChannel):
        return
    panel_id = database.get_meta('main_panel_message_id')
    if panel_id:
        try:
            msg = await channel.fetch_message(int(panel_id))
            await msg.edit(content=f'**{WELCOME_MARKER}**\n育成開始を押して遊んでね。', view=MainPanelView())
            await cleanup_old_main_panels(channel, keep_message_id=msg.id)
            return
        except Exception:
            pass
    msg = await channel.send(f'**{WELCOME_MARKER}**\n育成開始を押して遊んでね。', view=MainPanelView())
    database.set_meta('main_panel_message_id', str(msg.id))
    await cleanup_old_main_panels(channel, keep_message_id=msg.id)


async def restore_thread_and_panel(user_id: int, row: dict, fallback_channel: discord.abc.GuildChannel | None = None) -> tuple[Optional[discord.Thread], Optional[discord.Message]]:
    row = game_logic.repair_pet_row(user_id, row)
    if not row:
        return None, None
    thread = None
    if row.get('thread_id'):
        thread = bot.get_channel(int(row['thread_id']))
        if thread is None:
            try:
                thread = await bot.fetch_channel(int(row['thread_id']))
            except Exception:
                thread = None
    if thread is None:
        parent = None
        if fallback_channel is not None:
            parent = fallback_channel if isinstance(fallback_channel, discord.TextChannel) else getattr(fallback_channel, 'parent', None)
        if parent is None and row.get('channel_id'):
            parent = bot.get_channel(int(row['channel_id']))
            if parent is None:
                try:
                    parent = await bot.fetch_channel(int(row['channel_id']))
                except Exception:
                    parent = None
        if isinstance(parent, discord.Thread):
            parent = parent.parent
        if not isinstance(parent, discord.TextChannel):
            return None, None
        thread = await create_clean_thread(parent, f'{CHARACTERS[row["character_id"]]["name"]}のおへや')
        database.update_pet(user_id, thread_id=str(thread.id), channel_id=parent.id)
        row = database.fetch_pet(user_id)

    panel = None
    if row.get('panel_message_id'):
        try:
            panel = await thread.fetch_message(int(row['panel_message_id']))
        except Exception:
            panel = None
    if panel is None:
        panel = await thread.send(embed=await build_embed(row, user_id), view=PetView(user_id))
        database.update_pet(user_id, panel_message_id=str(panel.id))
    return thread, panel


async def refresh_panel_for_user(user_id: int, prefix: str = '', transient: str | None = None):
    row = database.fetch_pet(user_id)
    if not row:
        return
    thread, panel = await restore_thread_and_panel(user_id, row)
    if thread is None or panel is None:
        return
    prev_call = bool(row.get('call_flag'))
    prev_reason = row.get('call_reason', '')
    row, evo_msgs, warning, event = game_logic.update_over_time(user_id, row)
    embed = await build_embed(row, user_id, transient=transient)
    content = prefix if prefix else None
    await panel.edit(content=content, embed=embed, view=PetView(user_id))
    if warning:
        await upsert_system_log(thread, user_id, warning)
    if event:
        await upsert_system_log(thread, user_id, event)
    if evo_msgs:
        await upsert_system_log(thread, user_id, '\n'.join(evo_msgs))
        if game_logic.is_adult(row):
            letter_embed = await build_letter_embed(CHARACTERS[row['character_id']]['name'])
            if letter_embed:
                await thread.send(embed=letter_embed)
    if row.get('call_flag'):
        if (not prev_call) or (prev_reason != row.get('call_reason')):
            await upsert_alert_log(thread, user_id, game_logic.call_message_text(f'<@{user_id}>', row))
            database.update_pet(user_id, last_call_notified_at=int(time.time()))
    elif prev_call:
        await upsert_alert_log(thread, user_id, '○ 注意アイコン消灯\nいまはだいじょうぶ。\nまたようすをみてね。')


class MainPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='育成開始', style=discord.ButtonStyle.green, custom_id='main:start', row=0)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None:
            return await send_temp_interaction_message(interaction, 'サーバー内で使ってね。')
        row = database.fetch_pet(interaction.user.id)
        row = game_logic.repair_pet_row(interaction.user.id, row)
        if row and game_logic.can_resume_pet(row):
            return await send_temp_interaction_message(interaction, 'すでに育成中のデータがあるよ。『育成の続きから』を押してね。')
        if row and not game_logic.can_resume_pet(row):
            database.delete_pet(interaction.user.id)
        parent = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else getattr(interaction.channel, 'parent', None)
        if not isinstance(parent, discord.TextChannel):
            return await send_temp_interaction_message(interaction, 'ここでは始められないよ。')
        thread = await create_clean_thread(parent, f'{interaction.user.display_name}の結っち')
        database.create_pet(interaction.user.id, guild_id=interaction.guild.id, channel_id=parent.id, thread_id=str(thread.id))
        row = database.fetch_pet(interaction.user.id)
        panel = await thread.send(embed=await build_embed(row, interaction.user.id), view=PetView(interaction.user.id))
        database.update_pet(interaction.user.id, panel_message_id=str(panel.id))
        await upsert_system_log(thread, interaction.user.id, '🥚 育成がはじまったよ！\n生まれるまで見守ってね。')
        await interaction.response.send_message(f'✅ 育成スレッドを作ったよ！ {thread.mention}', ephemeral=True)

    @discord.ui.button(label='育成の続きから', style=discord.ButtonStyle.blurple, custom_id='main:continue', row=0)
    async def continue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        row = database.fetch_pet(interaction.user.id)
        row = game_logic.repair_pet_row(interaction.user.id, row)
        if not row:
            return await send_temp_interaction_message(interaction, '続きの育成データが見つからないよ。『育成開始』から始めてね。')
        if not game_logic.can_resume_pet(row):
            database.delete_pet(interaction.user.id)
            return await send_temp_interaction_message(interaction, '続きのデータが壊れていたので整理したよ。もう一度『育成開始』を押してね。')
        thread, panel = await restore_thread_and_panel(interaction.user.id, row, interaction.channel)
        if thread is None or panel is None:
            database.delete_pet(interaction.user.id)
            return await send_temp_interaction_message(interaction, '続きのデータを開けなかったので整理したよ。もう一度『育成開始』を押してね。')
        await refresh_panel_for_user(interaction.user.id)
        await interaction.response.send_message(f'✅ 続きの育成へどうぞ！ {thread.mention}', ephemeral=True)

    @discord.ui.button(label='図鑑', style=discord.ButtonStyle.gray, custom_id='main:dex', row=0)
    async def dex(self, interaction: discord.Interaction, button: discord.ui.Button):
        owned = {r['character_id'] for r in database.fetch_collection(interaction.user.id)}
        lines = []
        for cid in DEX_TARGETS:
            char = CHARACTERS[cid]
            mark = '✅' if cid in owned else '⬜'
            lines.append(f'{mark} {char["name"]} - {char["profile"]}')
        embed = discord.Embed(title='図鑑', description='\n'.join(lines) or 'まだ登録がないよ。')
        await send_temp_interaction_message(interaction, embed=embed, seconds=20)

    @discord.ui.button(label='あそびかた', style=discord.ButtonStyle.gray, custom_id='main:help', row=0)
    async def help_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        text = (
            '・育成開始で自分だけの結っちを育てられるよ\n'
            '・おなか、ごきげん、ねむけを見ながらお世話しよう\n'
            '・困っていると呼び出しが出るよ\n'
            '・ムスビーまではうんちあり、おとなになるとうんちは消えるよ\n'
            '・設定から時計合わせやデータ整理もできるよ'
        )
        await send_temp_interaction_message(interaction, content=text, seconds=20)


class SettingsSleepModal(discord.ui.Modal, title='ねる時間を設定'):
    sleep_start = discord.ui.TextInput(label='ねる時間', placeholder='22:00', default='22:00', max_length=5)
    sleep_end = discord.ui.TextInput(label='おきる時間', placeholder='07:00', default='07:00', max_length=5)

    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id
        start, end = game_logic.sleep_window(user_id)
        self.sleep_start.default = start
        self.sleep_end.default = end

    async def on_submit(self, interaction: discord.Interaction):
        database.update_user_settings(self.user_id, sleep_start=str(self.sleep_start), sleep_end=str(self.sleep_end))
        await refresh_panel_for_user(self.user_id)
        await send_temp_interaction_message(interaction, f'🌙 ねる時間を {self.sleep_start}〜{self.sleep_end} にしたよ。')


class SettingsClockModal(discord.ui.Modal, title='時計を合わせる'):
    target_time = discord.ui.TextInput(label='表示したい時刻', placeholder='21:30', max_length=5)

    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            hh, mm = str(self.target_time).split(':', 1)
            target_minutes = int(hh) * 60 + int(mm)
            jst_now = datetime_now_minutes()
            offset = target_minutes - jst_now
            while offset <= -720:
                offset += 1440
            while offset > 720:
                offset -= 1440
            database.update_user_settings(self.user_id, clock_offset_minutes=offset)
            await refresh_panel_for_user(self.user_id)
            await send_temp_interaction_message(interaction, f'🕒 時計を {self.target_time} に合わせたよ。')
        except Exception:
            await send_temp_interaction_message(interaction, '時刻は 21:30 みたいに入れてね。')


def datetime_now_minutes() -> int:
    now = time.localtime(time.time() + 9 * 3600)
    return now.tm_hour * 60 + now.tm_min


class DataResetView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id

    @discord.ui.button(label='今の育成だけ消す', style=discord.ButtonStyle.danger)
    async def delete_pet_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_owner(interaction, self.owner_id):
            return await send_temp_interaction_message(interaction, '持ち主だけが使えるよ。')
        database.delete_pet(self.owner_id)
        await send_temp_interaction_message(interaction, '🧹 今の育成データを消したよ。')

    @discord.ui.button(label='図鑑も全部消す', style=discord.ButtonStyle.danger)
    async def delete_all_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_owner(interaction, self.owner_id):
            return await send_temp_interaction_message(interaction, '持ち主だけが使えるよ。')
        database.reset_all_user_data(self.owner_id)
        await send_temp_interaction_message(interaction, '🧹 育成データと図鑑を全部消したよ。')


class SettingsView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    @discord.ui.button(label='時計+1時間', style=discord.ButtonStyle.gray, row=0)
    async def clock_plus(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_owner(interaction, self.owner_id):
            return await send_temp_interaction_message(interaction, '持ち主だけが使えるよ。')
        settings = database.fetch_user_settings(self.owner_id)
        database.update_user_settings(self.owner_id, clock_offset_minutes=game_logic.safe_int(settings.get('clock_offset_minutes', 0)) + 60)
        await refresh_panel_for_user(self.owner_id)
        await send_temp_interaction_message(interaction, '🕒 表示時刻を +1時間 したよ。')

    @discord.ui.button(label='時計-1時間', style=discord.ButtonStyle.gray, row=0)
    async def clock_minus(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_owner(interaction, self.owner_id):
            return await send_temp_interaction_message(interaction, '持ち主だけが使えるよ。')
        settings = database.fetch_user_settings(self.owner_id)
        database.update_user_settings(self.owner_id, clock_offset_minutes=game_logic.safe_int(settings.get('clock_offset_minutes', 0)) - 60)
        await refresh_panel_for_user(self.owner_id)
        await send_temp_interaction_message(interaction, '🕒 表示時刻を -1時間 したよ。')

    @discord.ui.button(label='時計を合わせる', style=discord.ButtonStyle.gray, row=0)
    async def clock_set(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_owner(interaction, self.owner_id):
            return await send_temp_interaction_message(interaction, '持ち主だけが使えるよ。')
        await interaction.response.send_modal(SettingsClockModal(self.owner_id))

    @discord.ui.button(label='JSTに戻す', style=discord.ButtonStyle.gray, row=1)
    async def clock_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_owner(interaction, self.owner_id):
            return await send_temp_interaction_message(interaction, '持ち主だけが使えるよ。')
        database.update_user_settings(self.owner_id, clock_offset_minutes=0)
        await refresh_panel_for_user(self.owner_id)
        await send_temp_interaction_message(interaction, '🇯🇵 日本時間表示に戻したよ。')

    @discord.ui.button(label='ねる時間', style=discord.ButtonStyle.gray, row=1)
    async def sleep_window_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_owner(interaction, self.owner_id):
            return await send_temp_interaction_message(interaction, '持ち主だけが使えるよ。')
        await interaction.response.send_modal(SettingsSleepModal(self.owner_id))

    @discord.ui.button(label='データ整理', style=discord.ButtonStyle.danger, row=1)
    async def reset_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_owner(interaction, self.owner_id):
            return await send_temp_interaction_message(interaction, '持ち主だけが使えるよ。')
        await send_temp_interaction_message(interaction, 'どちらを消す？', view=DataResetView(self.owner_id), seconds=40)


class PetView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        row = database.fetch_pet(owner_id)
        if row and not game_logic.poop_enabled(row):
            try:
                self.remove_item(self.clean_btn)
            except Exception:
                pass

    async def _run_action(self, interaction: discord.Interaction, action: str):
        if not is_owner(interaction, self.owner_id):
            return await send_temp_interaction_message(interaction, '持ち主だけが使えるよ。')
        row = database.fetch_pet(self.owner_id)
        row = game_logic.repair_pet_row(self.owner_id, row)
        if not row:
            return await send_temp_interaction_message(interaction, '育成データが見つからないよ。')
        row, result, extra_msgs, transient = game_logic.perform_action(self.owner_id, row, action)
        await refresh_panel_for_user(self.owner_id, prefix=None, transient=transient)
        lines = [result] + [m for m in extra_msgs if m]
        await send_temp_interaction_message(interaction, '\n'.join(lines), seconds=12)

    @discord.ui.button(label='ごはん', style=discord.ButtonStyle.green, custom_id='pet:feed', row=0)
    async def feed_btn(self, interaction, button):
        await self._run_action(interaction, 'feed')

    @discord.ui.button(label='おやつ', style=discord.ButtonStyle.blurple, custom_id='pet:snack', row=0)
    async def snack_btn(self, interaction, button):
        await self._run_action(interaction, 'snack')

    @discord.ui.button(label='あそぶ', style=discord.ButtonStyle.blurple, custom_id='pet:play', row=0)
    async def play_btn(self, interaction, button):
        await self._run_action(interaction, 'play')

    @discord.ui.button(label='でんき', style=discord.ButtonStyle.gray, custom_id='pet:sleep', row=0)
    async def sleep_btn(self, interaction, button):
        await self._run_action(interaction, 'sleep')

    @discord.ui.button(label='ようす', style=discord.ButtonStyle.gray, custom_id='pet:status', row=1)
    async def status_btn(self, interaction, button):
        await self._run_action(interaction, 'status')

    @discord.ui.button(label='しつけ', style=discord.ButtonStyle.gray, custom_id='pet:discipline', row=1)
    async def discipline_btn(self, interaction, button):
        await self._run_action(interaction, 'discipline')

    @discord.ui.button(label='ほめる', style=discord.ButtonStyle.gray, custom_id='pet:praise', row=1)
    async def praise_btn(self, interaction, button):
        await self._run_action(interaction, 'praise')

    @discord.ui.button(label='おそうじ', style=discord.ButtonStyle.gray, custom_id='pet:clean', row=1)
    async def clean_btn(self, interaction, button):
        await self._run_action(interaction, 'clean')

    @discord.ui.button(label='おくすり', style=discord.ButtonStyle.gray, custom_id='pet:medicine', row=2)
    async def medicine_btn(self, interaction, button):
        await self._run_action(interaction, 'medicine')

    @discord.ui.button(label='ミニゲーム', style=discord.ButtonStyle.gray, custom_id='pet:minigame', row=2)
    async def minigame_btn(self, interaction, button):
        await self._run_action(interaction, 'minigame')

    @discord.ui.button(label='おるすばん開始', style=discord.ButtonStyle.gray, custom_id='pet:odekake_start', row=2)
    async def odekake_start_btn(self, interaction, button):
        if not is_owner(interaction, self.owner_id):
            return await send_temp_interaction_message(interaction, '持ち主だけが使えるよ。')
        row = database.fetch_pet(self.owner_id)
        if not row:
            return await send_temp_interaction_message(interaction, '育成データが見つからないよ。')
        database.update_pet(self.owner_id, odekake_active=1, odekake_started_at=int(time.time()), last_access_at=int(time.time()))
        await refresh_panel_for_user(self.owner_id)
        await send_temp_interaction_message(interaction, '🏠 おるすばんを始めたよ。帰ってきたら終了を押してね。')

    @discord.ui.button(label='おるすばん終了', style=discord.ButtonStyle.gray, custom_id='pet:odekake_end', row=2)
    async def odekake_end_btn(self, interaction, button):
        if not is_owner(interaction, self.owner_id):
            return await send_temp_interaction_message(interaction, '持ち主だけが使えるよ。')
        row = database.fetch_pet(self.owner_id)
        if not row:
            return await send_temp_interaction_message(interaction, '育成データが見つからないよ。')
        database.update_pet(self.owner_id, odekake_active=0, last_access_at=int(time.time()))
        await refresh_panel_for_user(self.owner_id)
        await send_temp_interaction_message(interaction, '🏠 おるすばんを終わったよ。おかえり！')

    @discord.ui.button(label='設定', style=discord.ButtonStyle.danger, custom_id='pet:settings', row=2)
    async def settings_btn(self, interaction, button):
        if not is_owner(interaction, self.owner_id):
            return await send_temp_interaction_message(interaction, '持ち主だけが使えるよ。')
        row = database.fetch_pet(self.owner_id)
        if not row:
            return await send_temp_interaction_message(interaction, '育成データが見つからないよ。')
        settings = database.fetch_user_settings(self.owner_id)
        offset = game_logic.safe_int(settings.get('clock_offset_minutes', 0))
        sign = '+' if offset >= 0 else '-'
        offset_text = f'{sign}{abs(offset) // 60:02d}:{abs(offset) % 60:02d}'
        start, end = game_logic.sleep_window(self.owner_id)
        text = '\n'.join([
            f'表示時間: {game_logic.current_time_label(self.owner_id)}',
            f'時計補正: {offset_text}',
            f'ねる時間: {start}〜{end}',
            f'音: {game_logic.sound_label(row)}',
        ])
        await send_temp_interaction_message(interaction, text, view=SettingsView(self.owner_id), seconds=40)


@bot.command(name='setup_panel')
async def setup_panel(ctx: commands.Context):
    if not isinstance(ctx.channel, discord.TextChannel):
        return await ctx.reply('このチャンネルでは使えないよ。')
    await ensure_main_panel(ctx.channel)
    await ctx.reply('パネルを設置したよ。', delete_after=8)


@bot.command(name='image_keys')
async def image_keys(ctx: commands.Context):
    row = database.fetch_pet(ctx.author.id)
    row = game_logic.repair_pet_row(ctx.author.id, row)
    if not row:
        return await ctx.reply('育成データが見つからないよ。', delete_after=8)
    keys = game_logic.image_key_candidates(row)
    await ctx.reply('いま探しにいく画像名候補:\n' + '\n'.join(f'- {k}' for k in keys[:20]), delete_after=20)


@tasks.loop(seconds=60)
async def tick_loop():
    for user_id in database.list_active_user_ids():
        try:
            await refresh_panel_for_user(user_id)
        except Exception:
            continue


@bot.event
async def on_ready():
    database.init_db()
    bot.add_view(MainPanelView())
    for user_id in database.list_active_user_ids():
        bot.add_view(PetView(user_id))
    if not tick_loop.is_running():
        tick_loop.start()
    await ensure_main_panel()
    print(f'Logged in as {bot.user} / version={BOT_VERSION}')


if __name__ == '__main__':
    database.init_db()
    bot.run(DISCORD_BOT_TOKEN)
