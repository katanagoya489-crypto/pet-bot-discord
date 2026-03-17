from __future__ import annotations
import asyncio, time, sqlite3, discord
from discord.ext import commands
import database, game_logic, image_service
from game_data import CHARACTERS, DEX_TARGETS, MUSIC_GAMES
from config import DISCORD_BOT_TOKEN, ADMIN_USER_IDS, ENTRY_CHANNEL_ID

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)
WELCOME_MARKER = "○○っちへようこそ！"
BOT_VERSION = "latest-fixed-v1"
TEMP_MESSAGE_SECONDS = 8

def is_owner(interaction: discord.Interaction, owner_id: int) -> bool:
    return interaction.user.id == owner_id

async def send_temp_interaction_message(interaction, content=None, *, embed=None, view=None, ephemeral=True, seconds=TEMP_MESSAGE_SECONDS):
    send_kwargs={"content":content,"embed":embed,"ephemeral":ephemeral}
    if view is not None: send_kwargs["view"]=view
    if not interaction.response.is_done():
        await interaction.response.send_message(**send_kwargs)
        await asyncio.sleep(seconds)
        try: await interaction.delete_original_response()
        except Exception: pass
    else:
        try:
            msg = await interaction.followup.send(wait=True, **send_kwargs)
            await asyncio.sleep(seconds)
            try: await msg.delete()
            except Exception: pass
        except Exception: pass

async def image_url_for_row(row, transient=None):
    for key in game_logic.image_key_candidates(row, transient=transient):
        try:
            url = await image_service.get_image_url(bot, key)
            if url:
                return url, key
        except Exception:
            continue
    return None, None

async def build_embed(row, transient=None):
    embed = discord.Embed(description=game_logic.status_lines(row))
    url, _ = await image_url_for_row(row, transient=transient)
    if url:
        embed.set_image(url=url)
    return embed

async def build_letter_embed(character_name: str):
    key = f"{character_name}_手紙"
    url = await image_service.get_image_url(bot, key)
    if not url: return None
    embed = discord.Embed(title=f"{character_name} から手紙が届いています…")
    embed.set_image(url=url)
    return embed

async def upsert_system_log(thread: discord.Thread, user_id: int, text: str):
    row = database.fetch_pet(user_id)
    if not row: return
    message_id = row["system_message_id"]; body = f"【システムログ】\n{text}"
    if message_id:
        try:
            msg = await thread.fetch_message(int(message_id)); await msg.edit(content=body); return
        except Exception: pass
    msg = await thread.send(body); database.update_pet(user_id, system_message_id=str(msg.id))

async def upsert_alert_log(thread: discord.Thread, user_id: int, text: str):
    row = database.fetch_pet(user_id)
    if not row: return
    message_id = row["alert_message_id"]; body = f"【呼出しログ】\n{text}"
    if message_id:
        try:
            msg = await thread.fetch_message(int(message_id)); await msg.edit(content=body); return
        except Exception: pass
    msg = await thread.send(body); database.update_pet(user_id, alert_message_id=str(msg.id))

def compose_result_alert(title: str, main_text: str, row, user_id: int) -> str:
    lines=[title, main_text]
    current_call = game_logic.call_message_text(f"<@{user_id}>", row)
    if current_call:
        lines += ["", "――いまのおせわサイン――", current_call]
    elif row["praise_pending"]:
        lines += ["", "✨ ほめてサイン", "👉 おすすめ：ほめる"]
    else:
        lines += ["", "○ 注意アイコン消灯", "いまはだいじょうぶ。"]
    return "\n".join(lines)


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

async def cleanup_old_main_panels(channel: discord.TextChannel, keep_message_id=None):
    try:
        async for m in channel.history(limit=50):
            if m.author.id != bot.user.id or not m.content or WELCOME_MARKER not in m.content: continue
            if keep_message_id and m.id == keep_message_id: continue
            try: await m.delete()
            except Exception: pass
    except Exception: pass

async def delete_recent_thread_created_log(parent_channel: discord.TextChannel):
    await asyncio.sleep(1.2)
    try:
        async for m in parent_channel.history(limit=10):
            if m.type == discord.MessageType.thread_created:
                try: await m.delete()
                except Exception: pass
    except Exception: pass

async def create_clean_thread(parent_channel: discord.TextChannel, thread_name: str) -> discord.Thread:
    thread = await parent_channel.create_thread(name=thread_name, type=discord.ChannelType.public_thread, auto_archive_duration=60)
    bot.loop.create_task(delete_recent_thread_created_log(parent_channel))
    return thread

def remind_due(row, now:int):
    if not row["call_flag"]:
        return False
    last = row["last_call_notified_at"] or 0
    if last == 0:
        return True
    stage = row.get("call_stage", 1)
    interval = 18 * 60 if stage <= 1 else 12 * 60 if stage == 2 else 7 * 60
    return now - last >= interval

async def refresh_panel_for_user(user_id:int, prefix:str="", transient=None):
    row = database.fetch_pet(user_id)
    if not row or not row["panel_message_id"]: return
    thread = None
    if row["thread_id"]:
        thread = bot.get_channel(int(row["thread_id"]))
        if thread is None:
            try: thread = await bot.fetch_channel(int(row["thread_id"]))
            except Exception: return
    if thread is None: return
    try: msg = await thread.fetch_message(int(row["panel_message_id"]))
    except Exception: return
    prev_call=row["call_flag"]; prev_reason=row["call_reason"]; now=int(time.time())
    row, evo_msgs, warning, event = game_logic.update_over_time(user_id, row)
    embed = await build_embed(row, transient=transient); content = prefix if prefix else None
    if warning: await upsert_system_log(thread, user_id, warning)
    if event: await upsert_system_log(thread, user_id, event)
    if evo_msgs:
        await upsert_system_log(thread, user_id, "\n".join(evo_msgs))
        if row["journeyed"]:
            owned = database.fetch_collection(user_id)
            character_name = CHARACTERS[owned[-1]["character_id"]]["name"] if owned else CHARACTERS[row["character_id"]]["name"]
            letter_embed = await build_letter_embed(character_name)
            if letter_embed: await thread.send(embed=letter_embed)
    if row["call_flag"] and ((not prev_call) or (prev_reason != row["call_reason"]) or remind_due(row, now)):
        call_text = game_logic.call_message_text(f"<@{user_id}>", row) or "● 注意アイコン点灯中\n🔔 おせわサイン"
        await upsert_alert_log(thread, user_id, call_text)
        database.update_pet(user_id, last_call_notified_at=now)
    if row["praise_pending"] and not row["call_flag"]:
        await upsert_alert_log(thread, user_id, "✨ ほめてサイン\n<@{}>\n👉 おすすめ：ほめる".format(user_id))
    elif (not row["call_flag"]) and prev_call:
        await upsert_alert_log(thread, user_id, "○ 注意アイコン消灯\nいまはだいじょうぶ。\nまたようすをみてね。")
    await msg.edit(content=content, embed=embed, view=PetView(user_id))

async def ensure_main_panel():
    if not ENTRY_CHANNEL_ID: return
    await bot.wait_until_ready()
    channel = bot.get_channel(ENTRY_CHANNEL_ID)
    if channel is None:
        try: channel = await bot.fetch_channel(ENTRY_CHANNEL_ID)
        except Exception: return
    if not isinstance(channel, discord.TextChannel): return
    panel_id = database.get_meta("main_panel_message_id")
    if panel_id:
        try:
            msg = await channel.fetch_message(int(panel_id))
            await msg.edit(content=f"**{WELCOME_MARKER}**\n育成開始を押して遊んでね。", view=MainPanelView())
            await cleanup_old_main_panels(channel, keep_message_id=msg.id); return
        except Exception: pass
    msg = await channel.send(f"**{WELCOME_MARKER}**\n育成開始を押して遊んでね。", view=MainPanelView())
    database.set_meta("main_panel_message_id", str(msg.id)); await cleanup_old_main_panels(channel, keep_message_id=msg.id)

async def auto_tick_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        conn=database.get_conn(); rows=conn.execute("SELECT user_id FROM pets WHERE journeyed = 0").fetchall(); conn.close()
        for r in rows:
            try: await refresh_panel_for_user(int(r["user_id"]))
            except Exception: pass
        await asyncio.sleep(60)

class MainPanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="育成開始", style=discord.ButtonStyle.green, custom_id="main:start")
    async def start(self, interaction, button):
        user=interaction.user; guild=interaction.guild
        if guild is None: return await send_temp_interaction_message(interaction, "サーバー内で使ってね。")
        row = database.fetch_pet(user.id)
        if row and game_logic.can_resume_pet(row) and not row.get("journeyed"):
            return await send_temp_interaction_message(interaction, "すでに育成中のデータがあるよ。『育成の続きから』を押して再開してね。")
        if row and not game_logic.can_resume_pet(row):
            database.delete_pet(user.id)
        channel=interaction.channel
        if not isinstance(channel, discord.TextChannel): return await send_temp_interaction_message(interaction, "テキストチャンネルで使ってね。")
        try:
            thread=await create_clean_thread(channel, f"{user.display_name}っち")
            row,_=game_logic.start_pet_if_needed(user.id, guild.id, thread.id)
            embed=await build_embed(row)
            panel=await thread.send(f"{user.mention} の育成スレッドができたよ！", embed=embed, view=PetView(user.id))
            database.update_pet(user.id, panel_message_id=str(panel.id), thread_id=str(thread.id), system_message_id=None, alert_message_id=None)
            await upsert_alert_log(thread, user.id, "○ 注意アイコン消灯\nいまはだいじょうぶ。\nまたようすをみてね。")
            await send_temp_interaction_message(interaction, f"育成を開始したよ！ {thread.mention}")
        except Exception as e:
            await send_temp_interaction_message(interaction, f"育成開始に失敗したよ。\n`{type(e).__name__}`")
    @discord.ui.button(label="育成の続きから", style=discord.ButtonStyle.blurple, custom_id="main:continue")
    async def continue_btn(self, interaction, button):
        user=interaction.user; guild=interaction.guild
        if guild is None: return await send_temp_interaction_message(interaction, "サーバー内で使ってね。")
        try: database.init_db(); row=database.fetch_pet(user.id)
        except sqlite3.OperationalError as e: return await send_temp_interaction_message(interaction, f"続きからの復帰に失敗したよ。\n`{type(e).__name__}`")
        if not row or row.get("journeyed"): return await send_temp_interaction_message(interaction, "続きの育成データが見つからないよ。『育成開始』から始めてね。")
        if not game_logic.can_resume_pet(row):
            database.delete_pet(user.id)
            return await send_temp_interaction_message(interaction, "前の育成データがこわれていたので整理したよ。『育成開始』からやり直してね。")
        thread=None
        if row.get("thread_id"):
            tid = game_logic.try_int(row.get("thread_id"))
            if tid is not None:
                try: thread = bot.get_channel(tid) or await bot.fetch_channel(tid)
                except Exception: thread=None
        try:
            if thread is None:
                channel=interaction.channel
                if not isinstance(channel, discord.TextChannel): return await send_temp_interaction_message(interaction, "テキストチャンネルで使ってね。")
                new_thread=await create_clean_thread(channel, f"{user.display_name}っち-つづき")
                database.update_pet(user.id, thread_id=str(new_thread.id), panel_message_id=None, system_message_id=None, alert_message_id=None)
                row=database.fetch_pet(user.id); embed=await build_embed(row)
                panel=await new_thread.send(f"{user.mention} の育成データを続きから復帰したよ！", embed=embed, view=PetView(user.id))
                database.update_pet(user.id, panel_message_id=str(panel.id))
                await upsert_alert_log(new_thread, user.id, "○ 注意アイコン消灯\nいまはだいじょうぶ。\nまたようすをみてね。")
                return await send_temp_interaction_message(interaction, f"育成データを復帰したよ！ {new_thread.mention}")
            panel_ok=False
            if row.get("panel_message_id"):
                pid = game_logic.try_int(row.get("panel_message_id"))
                if pid is not None:
                    try: await thread.fetch_message(pid); panel_ok=True
                    except Exception: panel_ok=False
            if not panel_ok:
                embed=await build_embed(row); panel=await thread.send(f"{user.mention} の育成パネルを再作成したよ！", embed=embed, view=PetView(user.id))
                database.update_pet(user.id, panel_message_id=str(panel.id))
            if not row["alert_message_id"]: await upsert_alert_log(thread, user.id, "○ 注意アイコン消灯\nいまはだいじょうぶ。\nまたようすをみてね。")
            await send_temp_interaction_message(interaction, f"続きから再開できるよ！ {thread.mention}")
        except Exception as e:
            await send_temp_interaction_message(interaction, f"続きからの復帰に失敗したよ。\n`{type(e).__name__}`")
    @discord.ui.button(label="図鑑", style=discord.ButtonStyle.gray, custom_id="main:dex")
    async def dex(self, interaction, button):
        await send_temp_interaction_message(interaction, game_logic.build_dex_text(interaction.user.id), view=DexView(interaction.user.id, 0), seconds=20)
    @discord.ui.button(label="あそびかた", style=discord.ButtonStyle.gray, custom_id="main:help")
    async def help_button(self, interaction, button):
        await send_temp_interaction_message(interaction, "【あそびかた】\n・呼出しログは注意アイコンのかわりだよ\n・ようすでチェックメーターが見られる\n・でんきで眠る準備ができる\n・わがままサインが出たらしつけのチャンス\n・キラキラした時は ほめる のチャンス", seconds=20)

class PetView(discord.ui.View):
    def __init__(self, owner_id:int):
        super().__init__(timeout=None)
        self.owner_id=owner_id
        try:
            row = database.fetch_pet(owner_id)
            if row and hasattr(game_logic, "poop_enabled") and (not game_logic.poop_enabled(row)):
                for item in list(self.children):
                    if getattr(item, "custom_id", "") == "pet:clean":
                        self.remove_item(item)
        except Exception:
            pass
    async def _owner_check(self, interaction):
        if not is_owner(interaction, self.owner_id):
            await send_temp_interaction_message(interaction, "この子のお世話は本人だけができるよ。"); return False
        return True
    async def _do_action(self, interaction, action):
        row=database.fetch_pet(self.owner_id); row, result, msgs, transient = game_logic.perform_action(self.owner_id, row, action)
        await interaction.response.defer(); await refresh_panel_for_user(self.owner_id, prefix="" if action=="status" else result, transient=transient)
        thread=interaction.channel
        if isinstance(thread, discord.Thread):
            latest_row=database.fetch_pet(self.owner_id)
            if result:
                title="【チェック画面】" if action=="status" else "🫧 おせわけっか"
                await upsert_alert_log(thread, self.owner_id, compose_result_alert(title, result, latest_row, self.owner_id))
            if msgs: await upsert_system_log(thread, self.owner_id, "\n".join(msgs))
    @discord.ui.button(label="ごはん", style=discord.ButtonStyle.green, custom_id="pet:feed")
    async def feed(self, interaction, button):
        if await self._owner_check(interaction): await self._do_action(interaction, "feed")
    @discord.ui.button(label="おやつ", style=discord.ButtonStyle.blurple, custom_id="pet:snack")
    async def snack(self, interaction, button):
        if await self._owner_check(interaction): await self._do_action(interaction, "snack")
    @discord.ui.button(label="あそぶ", style=discord.ButtonStyle.blurple, row=1, custom_id="pet:play")
    async def play(self, interaction, button):
        if await self._owner_check(interaction): await self._do_action(interaction, "play")
    @discord.ui.button(label="でんき", style=discord.ButtonStyle.gray, row=1, custom_id="pet:sleep")
    async def sleep(self, interaction, button):
        if await self._owner_check(interaction): await self._do_action(interaction, "sleep")
    @discord.ui.button(label="ようす", style=discord.ButtonStyle.gray, row=1, custom_id="pet:status")
    async def status(self, interaction, button):
        if await self._owner_check(interaction): await self._do_action(interaction, "status")
    @discord.ui.button(label="しつけ", style=discord.ButtonStyle.red, row=2, custom_id="pet:discipline")
    async def discipline(self, interaction, button):
        if await self._owner_check(interaction): await self._do_action(interaction, "discipline")

    @discord.ui.button(label="ほめる", style=discord.ButtonStyle.green, row=2, custom_id="pet:praise")
    async def praise(self, interaction, button):
        if await self._owner_check(interaction): await self._do_action(interaction, "praise")
    @discord.ui.button(label="おそうじ", style=discord.ButtonStyle.red, row=2, custom_id="pet:clean")
    async def clean(self, interaction, button):
        if await self._owner_check(interaction): await self._do_action(interaction, "clean")
    @discord.ui.button(label="おくすり", style=discord.ButtonStyle.red, row=2, custom_id="pet:medicine")
    async def medicine(self, interaction, button):
        if await self._owner_check(interaction): await self._do_action(interaction, "medicine")
    @discord.ui.button(label="ミニゲーム", style=discord.ButtonStyle.green, row=3, custom_id="pet:minigame")
    async def minigame(self, interaction, button):
        if not await self._owner_check(interaction): return
        row=database.fetch_pet(self.owner_id); _, err = game_logic.start_minigame(self.owner_id, row, "rhythm")
        if err: return await send_temp_interaction_message(interaction, err)
        await send_temp_interaction_message(interaction, "あそぶ音楽ゲームを選んでね。", view=MiniGameMenuView(self.owner_id), seconds=15)

    @discord.ui.button(label="おるすばん開始", style=discord.ButtonStyle.blurple, row=4, custom_id="pet:odekake_start")
    async def odekake_start(self, interaction, button):
        if not await self._owner_check(interaction): return
        row=database.fetch_pet(self.owner_id)
        row, result = game_logic.start_odekake(self.owner_id, row)
        await interaction.response.defer()
        await refresh_panel_for_user(self.owner_id, prefix=result)
        if isinstance(interaction.channel, discord.Thread):
            latest_row=database.fetch_pet(self.owner_id)
            await upsert_alert_log(interaction.channel, self.owner_id, compose_result_alert("🏠 おるすばん", result, latest_row, self.owner_id))

    @discord.ui.button(label="おるすばん終了", style=discord.ButtonStyle.blurple, row=5, custom_id="pet:odekake_end")
    async def odekake_end(self, interaction, button):
        if not await self._owner_check(interaction): return
        row=database.fetch_pet(self.owner_id)
        row, result, extra = game_logic.stop_odekake(self.owner_id, row)
        await interaction.response.defer()
        await refresh_panel_for_user(self.owner_id, prefix=result)
        if isinstance(interaction.channel, discord.Thread):
            latest_row=database.fetch_pet(self.owner_id)
            body = compose_result_alert("🏠 おるすばん", result + ("\n" + "\n".join(extra) if extra else ""), latest_row, self.owner_id)
            await upsert_alert_log(interaction.channel, self.owner_id, body)

    @discord.ui.button(label="設定", style=discord.ButtonStyle.gray, row=5, custom_id="pet:settings")
    async def settings(self, interaction, button):
        if not await self._owner_check(interaction): return
        row=database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, render_settings_text(self.owner_id, row), view=SettingsView(self.owner_id), seconds=25)

class ClockSetModal(discord.ui.Modal, title="時計を合わせる"):
    target_time = discord.ui.TextInput(label="合わせたい時間", placeholder="例: 21:30", required=True, max_length=5)

    def __init__(self, owner_id: int):
        super().__init__()
        self.owner_id = owner_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await send_temp_interaction_message(interaction, "本人だけ変更できるよ。")
        try:
            game_logic.set_display_clock_to_hhmm(self.owner_id, str(self.target_time))
            row = database.fetch_pet(self.owner_id)
            await send_temp_interaction_message(interaction, f"時計を **{self.target_time}** に合わせたよ。\n\n{render_settings_text(self.owner_id, row)}", seconds=25)
        except Exception:
            await send_temp_interaction_message(interaction, "時間の書き方がちがうよ。\n`21:30` みたいに入れてね。")


class SleepWindowModal(discord.ui.Modal, title="ねる時間を設定"):
    sleep_start = discord.ui.TextInput(label="ねる時間", placeholder="例: 22:00", required=True, max_length=5)
    sleep_end = discord.ui.TextInput(label="おきる時間", placeholder="例: 07:00", required=True, max_length=5)

    def __init__(self, owner_id: int):
        super().__init__()
        self.owner_id = owner_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await send_temp_interaction_message(interaction, "本人だけ変更できるよ。")
        try:
            start = game_logic.normalize_hhmm(str(self.sleep_start))
            end = game_logic.normalize_hhmm(str(self.sleep_end))
            database.set_sleep_setting(self.owner_id, start, end)
            row = database.fetch_pet(self.owner_id)
            await send_temp_interaction_message(interaction, f"ねる時間を **{start}〜{end}** にしたよ。\n\n{render_settings_text(self.owner_id, row)}", seconds=25)
        except Exception:
            await send_temp_interaction_message(interaction, "時間の書き方がちがうよ。\n`22:00` と `07:00` みたいに入れてね。")


class SettingsView(discord.ui.View):
    def __init__(self, owner_id:int):
        super().__init__(timeout=180)
        self.owner_id=owner_id

    async def _owner_only(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await send_temp_interaction_message(interaction, "本人だけ変更できるよ。")
            return False
        return True

    @discord.ui.button(label="通知:たまごっち", style=discord.ButtonStyle.green)
    async def nt1(self, interaction, button):
        if not await self._owner_only(interaction): return
        database.update_pet(self.owner_id, notification_mode="tamagotchi")
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, "通知モードを『たまごっち』にしたよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="通知:ふつう", style=discord.ButtonStyle.blurple)
    async def nt2(self, interaction, button):
        if not await self._owner_only(interaction): return
        database.update_pet(self.owner_id, notification_mode="normal")
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, "通知モードを『ふつう』にしたよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="通知:静か", style=discord.ButtonStyle.gray, row=1)
    async def nt3(self, interaction, button):
        if not await self._owner_only(interaction): return
        database.update_pet(self.owner_id, notification_mode="quiet")
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, "通知モードを『静か』にしたよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="通知:ミュート", style=discord.ButtonStyle.red, row=1)
    async def nt4(self, interaction, button):
        if not await self._owner_only(interaction): return
        database.update_pet(self.owner_id, notification_mode="mute")
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, "通知モードを『ミュート』にしたよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="音:ON", style=discord.ButtonStyle.green, row=2)
    async def sound_on(self, interaction, button):
        if not await self._owner_only(interaction): return
        database.update_pet(self.owner_id, sound_enabled=1)
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, "音をONにしたよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="音:OFF", style=discord.ButtonStyle.gray, row=2)
    async def sound_off(self, interaction, button):
        if not await self._owner_only(interaction): return
        database.update_pet(self.owner_id, sound_enabled=0)
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, "音をOFFにしたよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="時計を合わせる", style=discord.ButtonStyle.blurple, row=3)
    async def clock_set(self, interaction, button):
        if not await self._owner_only(interaction): return
        await interaction.response.send_modal(ClockSetModal(self.owner_id))

    @discord.ui.button(label="時計+1時間", style=discord.ButtonStyle.green, row=3)
    async def clock_plus(self, interaction, button):
        if not await self._owner_only(interaction): return
        game_logic.adjust_display_clock(self.owner_id, 60)
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, "時計を +1時間 したよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="時計-1時間", style=discord.ButtonStyle.red, row=3)
    async def clock_minus(self, interaction, button):
        if not await self._owner_only(interaction): return
        game_logic.adjust_display_clock(self.owner_id, -60)
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, "時計を -1時間 したよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="時計をJSTに戻す", style=discord.ButtonStyle.gray, row=4)
    async def clock_reset(self, interaction, button):
        if not await self._owner_only(interaction): return
        game_logic.reset_display_clock(self.owner_id)
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, "時計を日本時間に戻したよ。\n\n" + render_settings_text(self.owner_id, row), seconds=25)

    @discord.ui.button(label="ねる時間を設定", style=discord.ButtonStyle.gray, row=4)
    async def set_sleep_window(self, interaction, button):
        if not await self._owner_only(interaction): return
        await interaction.response.send_modal(SleepWindowModal(self.owner_id))




    @discord.ui.button(label="データ整理", style=discord.ButtonStyle.red, row=5)
    async def data_cleanup(self, interaction, button):
        if not await self._owner_only(interaction): return
        await send_temp_interaction_message(interaction, "消したい内容を選んでね。", view=CleanupMenuView(self.owner_id), seconds=30)


class CleanupMenuView(discord.ui.View):
    def __init__(self, owner_id:int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    async def _owner_only(self, interaction):
        if interaction.user.id != self.owner_id:
            await send_temp_interaction_message(interaction, "本人だけ変更できるよ。")
            return False
        return True

    @discord.ui.button(label="今の育成だけ消す", style=discord.ButtonStyle.red)
    async def delete_pet_only(self, interaction, button):
        if not await self._owner_only(interaction): return
        database.delete_pet(self.owner_id)
        await send_temp_interaction_message(interaction, "今の育成データだけ消したよ。\n『育成開始』から新しく始められるよ。", seconds=20)

    @discord.ui.button(label="図鑑も全部消す", style=discord.ButtonStyle.red)
    async def delete_all(self, interaction, button):
        if not await self._owner_only(interaction): return
        database.delete_all_user_data(self.owner_id)
        await send_temp_interaction_message(interaction, "育成データと図鑑を全部消したよ。\n最初からやり直せるよ。", seconds=20)


class MiniGameMenuView(discord.ui.View):
    def __init__(self, owner_id:int): super().__init__(timeout=180); self.owner_id=owner_id
    async def send_game(self, interaction, key:str):
        row=database.fetch_pet(self.owner_id); game, err = game_logic.start_minigame(self.owner_id, row, key)
        if err: return await send_temp_interaction_message(interaction, err)
        await send_temp_interaction_message(interaction, f"**{game['title']}**\n{game['question']}", view=MiniGameAnswerView(self.owner_id, key), seconds=15)
    @discord.ui.button(label="リズム", style=discord.ButtonStyle.green)
    async def rhythm(self, interaction, button): await self.send_game(interaction, "rhythm")
    @discord.ui.button(label="音あて", style=discord.ButtonStyle.green)
    async def instrument(self, interaction, button): await self.send_game(interaction, "instrument")
    @discord.ui.button(label="メロディ", style=discord.ButtonStyle.green)
    async def melody(self, interaction, button): await self.send_game(interaction, "melody")

class MiniGameAnswerView(discord.ui.View):
    def __init__(self, owner_id:int, game_key:str):
        super().__init__(timeout=180); game=MUSIC_GAMES[game_key]
        for idx, choice in enumerate(game["choices"]): self.add_item(MiniGameChoiceButton(owner_id, game_key, idx, choice))

class MiniGameChoiceButton(discord.ui.Button):
    def __init__(self, owner_id:int, game_key:str, idx:int, label:str):
        super().__init__(label=label, style=discord.ButtonStyle.blurple); self.owner_id=owner_id; self.game_key=game_key; self.idx=idx
    async def callback(self, interaction):
        if interaction.user.id != self.owner_id: return await send_temp_interaction_message(interaction, "本人だけが遊べるよ。")
        row=database.fetch_pet(self.owner_id); _, msg, evo = game_logic.resolve_minigame(self.owner_id, row, self.game_key, self.idx)
        await interaction.response.edit_message(content="このミニゲームは終了したよ。", view=None)
        await asyncio.sleep(2)
        try: await interaction.delete_original_response()
        except Exception: pass
        await refresh_panel_for_user(self.owner_id)
        thread=interaction.channel
        if isinstance(thread, discord.Thread):
            latest_row=database.fetch_pet(self.owner_id)
            body=compose_result_alert("🎮 ミニゲームけっか", msg + ("\n" + "\n".join(evo) if evo else ""), latest_row, self.owner_id)
            await upsert_alert_log(thread, self.owner_id, body)

class DexView(discord.ui.View):
    def __init__(self, owner_id:int, page:int):
        super().__init__(timeout=180); self.owner_id=owner_id; self.page=page
        owned_rows=database.fetch_collection(owner_id); owned_ids=[r["character_id"] for r in owned_rows]
        owned_target_ids=[cid for cid in DEX_TARGETS if cid in owned_ids]; per=4; chunk=owned_target_ids[page*per:(page+1)*per]
        if chunk:
            options=[discord.SelectOption(label=CHARACTERS[c]["name"], value=c) for c in chunk]; self.add_item(DexSelect(owner_id, options))
        if page > 0: self.add_item(DexNavButton(owner_id, page-1, "前へ"))
        if (page+1)*per < len(owned_target_ids): self.add_item(DexNavButton(owner_id, page+1, "次へ"))

class DexSelect(discord.ui.Select):
    def __init__(self, owner_id:int, options): super().__init__(placeholder="詳細を見るキャラを選んでね", options=options); self.owner_id=owner_id
    async def callback(self, interaction):
        if interaction.user.id != self.owner_id: return await send_temp_interaction_message(interaction, "これはあなたの図鑑表示だよ。")
        await send_temp_interaction_message(interaction, game_logic.build_dex_detail(self.owner_id, self.values[0]), seconds=20)

class DexNavButton(discord.ui.Button):
    def __init__(self, owner_id:int, page:int, label:str): super().__init__(label=label, style=discord.ButtonStyle.gray); self.owner_id=owner_id; self.page=page
    async def callback(self, interaction):
        if interaction.user.id != self.owner_id: return await send_temp_interaction_message(interaction, "これはあなたの図鑑表示だよ。")
        await interaction.response.edit_message(content=game_logic.build_dex_text(self.owner_id), view=DexView(self.owner_id, self.page))



@bot.command(name="image_keys")
async def image_keys(ctx):
    row = database.fetch_pet(ctx.author.id)
    if not row:
        return await ctx.reply("育成データがないよ。")
    keys = game_logic.image_keys_for_debug(row)
    await ctx.reply("いま探しにいく画像名:\n" + "\n".join(f"- {k}" for k in keys))

@bot.event
async def on_ready():
    database.init_db(); bot.add_view(MainPanelView()); print(f"Logged in as {bot.user} / version={BOT_VERSION}")
    bot.loop.create_task(ensure_main_panel()); bot.loop.create_task(auto_tick_loop())

@bot.command()
async def setup_panel(ctx):
    if ADMIN_USER_IDS and ctx.author.id not in ADMIN_USER_IDS: return await ctx.send("管理者だけが使えるよ。")
    channel=ctx.channel
    if isinstance(channel, discord.TextChannel):
        msg=await channel.send(f"**{WELCOME_MARKER}**\n育成開始を押して遊んでね。", view=MainPanelView())
        database.set_meta("main_panel_message_id", str(msg.id)); await cleanup_old_main_panels(channel, keep_message_id=msg.id)

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
