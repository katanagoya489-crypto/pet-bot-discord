from __future__ import annotations
import asyncio
import time
import discord
from discord.ext import commands
import database
import game_logic
import image_service
from game_data import CHARACTERS, DEX_TARGETS, MUSIC_GAMES
from config import DISCORD_BOT_TOKEN, ADMIN_USER_IDS, ENTRY_CHANNEL_ID

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

WELCOME_MARKER = "○○っちへようこそ！"
TEMP_MESSAGE_SECONDS = 8

def is_owner(interaction: discord.Interaction, owner_id: int) -> bool:
    return interaction.user.id == owner_id

async def send_temp_interaction_message(interaction: discord.Interaction, content: str | None = None, *, embed=None, view=None, ephemeral=True, seconds: int = TEMP_MESSAGE_SECONDS):
    if not interaction.response.is_done():
        await interaction.response.send_message(content=content, embed=embed, view=view, ephemeral=ephemeral)
        await asyncio.sleep(seconds)
        try:
            await interaction.delete_original_response()
        except Exception:
            pass
    else:
        try:
            msg = await interaction.followup.send(content=content, embed=embed, view=view, ephemeral=ephemeral, wait=True)
            await asyncio.sleep(seconds)
            try:
                await msg.delete()
            except Exception:
                pass
        except Exception:
            pass

async def build_embed(row, transient: str | None = None):
    embed = discord.Embed(description=game_logic.status_lines(row))
    key = game_logic.image_key_for_pet(row, transient=transient)
    url = await image_service.get_image_url(bot, key)
    if url:
        embed.set_image(url=url)
    return embed

async def build_letter_embed(character_name: str):
    key = f"{character_name}_手紙"
    url = await image_service.get_image_url(bot, key)
    if not url:
        return None
    embed = discord.Embed(title=f"{character_name} から手紙が届いています…")
    embed.set_image(url=url)
    return embed

async def maybe_send_notification(thread, user_id: int, row, text: str):
    mode = row["notification_mode"]
    if mode == "mute":
        return
    if mode == "quiet" and not any(k in text for k in ["進化", "旅", "病気", "図鑑"]):
        return
    if mode == "normal" and any(k in text for k in ["お腹", "ごきげん", "うんち", "わがまま", "眠そう"]):
        return
    await thread.send(f"<@{user_id}>\n{text}")

async def maybe_send_call_notification(thread, user_id: int, row):
    text = game_logic.call_message_text(f"<@{user_id}>", row)
    if not text:
        return
    mode = row["notification_mode"]
    if mode == "mute" or mode == "quiet":
        return
    if mode == "normal" and row["call_reason"] in ("hunger", "mood", "poop", "sleepy", "whim"):
        return
    await thread.send(text)

async def upsert_system_log(thread: discord.Thread, user_id: int, text: str):
    row = database.fetch_pet(user_id)
    if not row:
        return
    system_message_id = row["system_message_id"]
    if system_message_id:
        try:
            msg = await thread.fetch_message(int(system_message_id))
            await msg.edit(content=text)
            return
        except Exception:
            pass
    msg = await thread.send(text)
    database.update_pet(user_id, system_message_id=str(msg.id))

async def cleanup_old_main_panels(channel: discord.TextChannel, keep_message_id: int | None = None):
    try:
        async for m in channel.history(limit=50):
            if m.author.id != bot.user.id:
                continue
            if not m.content or WELCOME_MARKER not in m.content:
                continue
            if keep_message_id and m.id == keep_message_id:
                continue
            try:
                await m.delete()
            except Exception:
                pass
    except Exception:
        pass

async def delete_recent_thread_created_log(parent_channel: discord.TextChannel):
    await asyncio.sleep(1.2)
    try:
        async for m in parent_channel.history(limit=10):
            if m.type == discord.MessageType.thread_created:
                try:
                    await m.delete()
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
    diff = now - last
    if diff >= 30 * 60:
        return True
    if diff >= 15 * 60:
        return True
    return False

async def refresh_panel_for_user(user_id: int, prefix: str = "", transient: str | None = None):
    row = database.fetch_pet(user_id)
    if not row or not row["panel_message_id"]:
        return

    thread = None
    if row["thread_id"]:
        thread = bot.get_channel(int(row["thread_id"]))
        if thread is None:
            try:
                thread = await bot.fetch_channel(int(row["thread_id"]))
            except Exception:
                return
    if thread is None:
        return

    try:
        msg = await thread.fetch_message(int(row["panel_message_id"]))
    except Exception:
        return

    prev_call = row["call_flag"]
    prev_reason = row["call_reason"]
    now = int(time.time())

    row, evo_msgs, warning, event = game_logic.update_over_time(user_id, row)
    embed = await build_embed(row, transient=transient)
    content = prefix if prefix else None

    if warning:
        await upsert_system_log(thread, user_id, warning)
        await maybe_send_notification(thread, user_id, row, warning)

    if event:
        await upsert_system_log(thread, user_id, event)

    if evo_msgs:
        await upsert_system_log(thread, user_id, "\n".join(evo_msgs))
        for m in evo_msgs:
            await maybe_send_notification(thread, user_id, row, m)

        if row["journeyed"]:
            owned = database.fetch_collection(user_id)
            character_name = CHARACTERS[owned[-1]["character_id"]]["name"] if owned else CHARACTERS[row["character_id"]]["name"]
            letter_embed = await build_letter_embed(character_name)
            if letter_embed:
                await thread.send(embed=letter_embed)
            await thread.edit(archived=True)
            await thread.parent.send(f"<@{user_id}>\n旅立ちおつかれさま！ 次は別の進化も狙ってみよう。")

    if row["call_flag"] and ((not prev_call) or (prev_reason != row["call_reason"]) or remind_due(row, now)):
        call_text = game_logic.call_message_text(f"<@{user_id}>", row) or "🔔 呼び出し中"
        await upsert_system_log(thread, user_id, call_text)
        await maybe_send_call_notification(thread, user_id, row)
        database.update_pet(user_id, last_call_notified_at=now)

    await msg.edit(content=content, embed=embed, view=PetView(user_id))

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
            msg = await channel.fetch_message(int(panel_id))
            await msg.edit(content=f"**{WELCOME_MARKER}**\n育成開始を押して遊んでね。", view=MainPanelView())
            await cleanup_old_main_panels(channel, keep_message_id=msg.id)
            return
        except Exception:
            pass

    msg = await channel.send(f"**{WELCOME_MARKER}**\n育成開始を押して遊んでね。", view=MainPanelView())
    database.set_meta("main_panel_message_id", str(msg.id))
    await cleanup_old_main_panels(channel, keep_message_id=msg.id)

async def auto_tick_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        conn = database.get_conn()
        rows = conn.execute("SELECT user_id FROM pets WHERE journeyed = 0").fetchall()
        conn.close()
        for r in rows:
            try:
                await refresh_panel_for_user(int(r["user_id"]))
            except Exception:
                pass
        await asyncio.sleep(60)

class MainPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="育成開始", style=discord.ButtonStyle.green, custom_id="main:start")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
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
            panel = await thread.send(f"{user.mention} の育成スレッドができたよ！\n通知は最初は『たまごっち』設定です。忙しい時は設定で変えてね。", embed=embed, view=PetView(user.id))
            database.update_pet(user.id, panel_message_id=str(panel.id), thread_id=str(thread.id), system_message_id=None)
            await send_temp_interaction_message(interaction, f"育成を開始したよ！ {thread.mention}")
        except Exception as e:
            await send_temp_interaction_message(interaction, f"育成開始に失敗したよ。管理者に伝えてね。\n`{type(e).__name__}`")

    @discord.ui.button(label="育成の続きから", style=discord.ButtonStyle.blurple, custom_id="main:continue")
    async def continue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        guild = interaction.guild
        if guild is None:
            return await send_temp_interaction_message(interaction, "サーバー内で使ってね。")
        row = database.fetch_pet(user.id)
        if not row or row["journeyed"]:
            return await send_temp_interaction_message(interaction, "続きの育成データが見つからないよ。『育成開始』から始めてね。")
        thread = None
        if row["thread_id"]:
            try:
                thread = bot.get_channel(int(row["thread_id"])) or await bot.fetch_channel(int(row["thread_id"]))
            except Exception:
                thread = None
        try:
            if thread is None:
                channel = interaction.channel
                if not isinstance(channel, discord.TextChannel):
                    return await send_temp_interaction_message(interaction, "テキストチャンネルで使ってね。")
                new_thread = await create_clean_thread(channel, f"{user.display_name}っち-つづき")
                database.update_pet(user.id, thread_id=str(new_thread.id), panel_message_id=None, system_message_id=None)
                row = database.fetch_pet(user.id)
                embed = await build_embed(row)
                panel = await new_thread.send(f"{user.mention} の育成データを続きから復帰したよ！\n前のスレッドが見つからなかったため、新しいスレッドを作成しました。", embed=embed, view=PetView(user.id))
                database.update_pet(user.id, panel_message_id=str(panel.id))
                return await send_temp_interaction_message(interaction, f"育成データを復帰したよ！ {new_thread.mention}")
            panel_ok = False
            if row["panel_message_id"]:
                try:
                    await thread.fetch_message(int(row["panel_message_id"]))
                    panel_ok = True
                except Exception:
                    panel_ok = False
            if not panel_ok:
                embed = await build_embed(row)
                panel = await thread.send(f"{user.mention} の育成パネルを再作成したよ！", embed=embed, view=PetView(user.id))
                database.update_pet(user.id, panel_message_id=str(panel.id))
            await send_temp_interaction_message(interaction, f"続きから再開できるよ！ {thread.mention}")
        except Exception as e:
            await send_temp_interaction_message(interaction, f"続きからの復帰に失敗したよ。管理者に伝えてね。\n`{type(e).__name__}`")

    @discord.ui.button(label="図鑑", style=discord.ButtonStyle.gray, custom_id="main:dex")
    async def dex(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_temp_interaction_message(interaction, game_logic.build_dex_text(interaction.user.id), view=DexView(interaction.user.id, 0), seconds=20)

    @discord.ui.button(label="あそびかた", style=discord.ButtonStyle.gray, custom_id="main:help")
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_temp_interaction_message(
            interaction,
            "【あそびかた】\n・育成開始で専用スレッドができる\n・スレッドが消えたら『育成の続きから』で復帰できる\n・呼び出しは @ユーザー名 で届く\n・お世話ミスやわがままサインがある\n・進化前予兆やランダムイベントがある\n・成熟後は旅立って図鑑に登録される",
            seconds=20
        )

class PetView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=None)
        self.owner_id = owner_id

    async def _owner_check(self, interaction: discord.Interaction):
        if not is_owner(interaction, self.owner_id):
            await send_temp_interaction_message(interaction, "この子のお世話は本人だけができるよ。")
            return False
        return True

    async def _do_action(self, interaction, action):
        row = database.fetch_pet(self.owner_id)
        row, result, msgs, transient = game_logic.perform_action(self.owner_id, row, action)
        await interaction.response.defer()
        await refresh_panel_for_user(self.owner_id, prefix=result, transient=transient)
        thread = interaction.channel
        if msgs and isinstance(thread, discord.Thread):
            await upsert_system_log(thread, self.owner_id, "\n".join(msgs))
        for m in msgs:
            if isinstance(thread, discord.Thread):
                await maybe_send_notification(thread, self.owner_id, row, m)
            if row["journeyed"]:
                letter_embed = await build_letter_embed(CHARACTERS[row["character_id"]]["name"])
                if letter_embed and isinstance(thread, discord.Thread):
                    await thread.send(embed=letter_embed)

    @discord.ui.button(label="ごはん", style=discord.ButtonStyle.green, custom_id="pet:feed")
    async def feed(self, interaction, button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "feed")

    @discord.ui.button(label="おやつ", style=discord.ButtonStyle.blurple, custom_id="pet:snack")
    async def snack(self, interaction, button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "snack")

    @discord.ui.button(label="あそぶ", style=discord.ButtonStyle.blurple, row=1, custom_id="pet:play")
    async def play(self, interaction, button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "play")

    @discord.ui.button(label="ねる", style=discord.ButtonStyle.gray, row=1, custom_id="pet:sleep")
    async def sleep(self, interaction, button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "sleep")

    @discord.ui.button(label="ようす", style=discord.ButtonStyle.gray, row=1, custom_id="pet:status")
    async def status(self, interaction, button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "status")

    @discord.ui.button(label="しつけ", style=discord.ButtonStyle.red, row=2, custom_id="pet:discipline")
    async def discipline(self, interaction, button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "discipline")

    @discord.ui.button(label="おそうじ", style=discord.ButtonStyle.red, row=2, custom_id="pet:clean")
    async def clean(self, interaction, button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "clean")

    @discord.ui.button(label="おくすり", style=discord.ButtonStyle.red, row=2, custom_id="pet:medicine")
    async def medicine(self, interaction, button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "medicine")

    @discord.ui.button(label="ミニゲーム", style=discord.ButtonStyle.green, row=3, custom_id="pet:minigame")
    async def minigame(self, interaction, button):
        if not await self._owner_check(interaction):
            return
        row = database.fetch_pet(self.owner_id)
        _, err = game_logic.start_minigame(self.owner_id, row, "rhythm")
        if err:
            return await send_temp_interaction_message(interaction, err)
        await send_temp_interaction_message(interaction, "あそぶ音楽ゲームを選んでね。", view=MiniGameMenuView(self.owner_id), seconds=15)

    @discord.ui.button(label="設定", style=discord.ButtonStyle.gray, row=3, custom_id="pet:settings")
    async def settings(self, interaction, button):
        if not await self._owner_check(interaction):
            return
        row = database.fetch_pet(self.owner_id)
        await send_temp_interaction_message(interaction, f"通知モード: {game_logic.notification_mode_label(row['notification_mode'])}", view=SettingsView(self.owner_id), seconds=20)

    @discord.ui.button(label="おるすばん開始", style=discord.ButtonStyle.blurple, row=4, custom_id="pet:away_start")
    async def away_start(self, interaction, button):
        if not await self._owner_check(interaction):
            return
        row = database.fetch_pet(self.owner_id)
        _, msg = game_logic.start_odekake(self.owner_id, row)
        await interaction.response.defer()
        await refresh_panel_for_user(self.owner_id, prefix=msg)

    @discord.ui.button(label="おるすばん終了", style=discord.ButtonStyle.blurple, row=4, custom_id="pet:away_stop")
    async def away_stop(self, interaction, button):
        if not await self._owner_check(interaction):
            return
        row = database.fetch_pet(self.owner_id)
        _, msg, evo = game_logic.stop_odekake(self.owner_id, row)
        await interaction.response.defer()
        await refresh_panel_for_user(self.owner_id, prefix=msg)
        thread = interaction.channel
        if evo and isinstance(thread, discord.Thread):
            await upsert_system_log(thread, self.owner_id, "\n".join(evo))
        for m in evo:
            if isinstance(thread, discord.Thread):
                await maybe_send_notification(thread, self.owner_id, row, m)

class SettingsView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    @discord.ui.button(label="通知:たまごっち", style=discord.ButtonStyle.green)
    async def nt1(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await send_temp_interaction_message(interaction, "本人だけ変更できるよ。")
        database.update_pet(self.owner_id, notification_mode="tamagotchi")
        await send_temp_interaction_message(interaction, "通知モードを『たまごっち』にしたよ。")

    @discord.ui.button(label="通知:ふつう", style=discord.ButtonStyle.blurple)
    async def nt2(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await send_temp_interaction_message(interaction, "本人だけ変更できるよ。")
        database.update_pet(self.owner_id, notification_mode="normal")
        await send_temp_interaction_message(interaction, "通知モードを『ふつう』にしたよ。")

    @discord.ui.button(label="通知:静か", style=discord.ButtonStyle.gray, row=1)
    async def nt3(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await send_temp_interaction_message(interaction, "本人だけ変更できるよ。")
        database.update_pet(self.owner_id, notification_mode="quiet")
        await send_temp_interaction_message(interaction, "通知モードを『静か』にしたよ。")

    @discord.ui.button(label="通知:ミュート", style=discord.ButtonStyle.red, row=1)
    async def nt4(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await send_temp_interaction_message(interaction, "本人だけ変更できるよ。")
        database.update_pet(self.owner_id, notification_mode="mute")
        await send_temp_interaction_message(interaction, "通知モードを『ミュート』にしたよ。")

    @discord.ui.button(label="スリープ 00:00-07:00", style=discord.ButtonStyle.gray, row=2)
    async def sleep_default(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await send_temp_interaction_message(interaction, "本人だけ変更できるよ。")
        database.set_sleep_setting(self.owner_id, "00:00", "07:00")
        await send_temp_interaction_message(interaction, "スリープ時間を 00:00〜07:00 にしたよ。")

    @discord.ui.button(label="リセット", style=discord.ButtonStyle.red, row=2)
    async def reset(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await send_temp_interaction_message(interaction, "本人だけ変更できるよ。")
        await send_temp_interaction_message(interaction, "本当に最初からやり直す？", view=ResetConfirmView(self.owner_id), seconds=20)

class ResetConfirmView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id

    @discord.ui.button(label="はい", style=discord.ButtonStyle.red)
    async def yes(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await send_temp_interaction_message(interaction, "本人だけ実行できるよ。")
        thread = interaction.channel
        database.delete_pet(self.owner_id)
        await send_temp_interaction_message(interaction, "リセットしたよ。スレッドを閉じるね。")
        try:
            await thread.delete()
        except Exception:
            pass

    @discord.ui.button(label="いいえ", style=discord.ButtonStyle.gray)
    async def no(self, interaction, button):
        await send_temp_interaction_message(interaction, "キャンセルしたよ。")

class MiniGameMenuView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    async def send_game(self, interaction, key: str):
        row = database.fetch_pet(self.owner_id)
        game, err = game_logic.start_minigame(self.owner_id, row, key)
        if err:
            return await send_temp_interaction_message(interaction, err)
        await send_temp_interaction_message(interaction, f"**{game['title']}**\n{game['question']}", view=MiniGameAnswerView(self.owner_id, key), seconds=15)

    @discord.ui.button(label="リズム", style=discord.ButtonStyle.green)
    async def rhythm(self, interaction, button):
        await self.send_game(interaction, "rhythm")

    @discord.ui.button(label="音あて", style=discord.ButtonStyle.green)
    async def instrument(self, interaction, button):
        await self.send_game(interaction, "instrument")

    @discord.ui.button(label="メロディ", style=discord.ButtonStyle.green)
    async def melody(self, interaction, button):
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

    async def callback(self, interaction):
        if interaction.user.id != self.owner_id:
            return await send_temp_interaction_message(interaction, "本人だけが遊べるよ。")
        row = database.fetch_pet(self.owner_id)
        _, msg, evo = game_logic.resolve_minigame(self.owner_id, row, self.game_key, self.idx)
        result_text = msg + (("\n" + "\n".join(evo)) if evo else "")
        thread = interaction.channel
        if isinstance(thread, discord.Thread):
            await upsert_system_log(thread, self.owner_id, result_text)
        await interaction.response.edit_message(content="このミニゲームは終了したよ。", view=None)
        await asyncio.sleep(2)
        try:
            await interaction.delete_original_response()
        except Exception:
            pass
        await refresh_panel_for_user(self.owner_id)

class DexView(discord.ui.View):
    def __init__(self, owner_id: int, page: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.page = page
        owned_rows = database.fetch_collection(owner_id)
        owned_ids = [r["character_id"] for r in owned_rows]
        owned_target_ids = [cid for cid in DEX_TARGETS if cid in owned_ids]
        per = 4
        chunk = owned_target_ids[page * per:(page + 1) * per]
        if chunk:
            options = [discord.SelectOption(label=CHARACTERS[c]["name"], value=c) for c in chunk]
            self.add_item(DexSelect(owner_id, options))
        if page > 0:
            self.add_item(DexNavButton(owner_id, page - 1, "前へ"))
        if (page + 1) * per < len(owned_target_ids):
            self.add_item(DexNavButton(owner_id, page + 1, "次へ"))

class DexSelect(discord.ui.Select):
    def __init__(self, owner_id: int, options):
        super().__init__(placeholder="詳細を見るキャラを選んでね", options=options)
        self.owner_id = owner_id

    async def callback(self, interaction):
        if interaction.user.id != self.owner_id:
            return await send_temp_interaction_message(interaction, "これはあなたの図鑑表示だよ。")
        await send_temp_interaction_message(interaction, game_logic.build_dex_detail(self.owner_id, self.values[0]), seconds=20)

class DexNavButton(discord.ui.Button):
    def __init__(self, owner_id: int, page: int, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.gray)
        self.owner_id = owner_id
        self.page = page

    async def callback(self, interaction):
        if interaction.user.id != self.owner_id:
            return await send_temp_interaction_message(interaction, "これはあなたの図鑑表示だよ。")
        await interaction.response.edit_message(content=game_logic.build_dex_text(self.owner_id), view=DexView(self.owner_id, self.page))

@bot.event
async def on_ready():
    database.init_db()
    bot.add_view(MainPanelView())
    print(f"Logged in as {bot.user}")
    bot.loop.create_task(ensure_main_panel())
    bot.loop.create_task(auto_tick_loop())

@bot.command()
async def setup_panel(ctx):
    if ADMIN_USER_IDS and ctx.author.id not in ADMIN_USER_IDS:
        return await ctx.send("管理者だけが使えるよ。")
    channel = ctx.channel
    if isinstance(channel, discord.TextChannel):
        msg = await channel.send(f"**{WELCOME_MARKER}**\n育成開始を押して遊んでね。", view=MainPanelView())
        database.set_meta("main_panel_message_id", str(msg.id))
        await cleanup_old_main_panels(channel, keep_message_id=msg.id)

@bot.command()
async def status(ctx):
    row = database.fetch_pet(ctx.author.id)
    if not row:
        return await ctx.send("まだ育成していないよ。")
    row, evo, warning, event = game_logic.update_over_time(ctx.author.id, row)
    embed = await build_embed(row)
    texts = []
    if evo: texts.extend(evo)
    if warning: texts.append(warning)
    if event: texts.append(event)
    await ctx.send(("\n".join(texts)) if texts else None, embed=embed)

@bot.command()
async def dex(ctx):
    await ctx.send(game_logic.build_dex_text(ctx.author.id), view=DexView(ctx.author.id, 0))

@bot.command()
async def set_sleep(ctx, start: str, end: str):
    database.set_sleep_setting(ctx.author.id, start, end)
    await ctx.send(f"スリープ時間を {start}〜{end} に設定したよ。")

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
