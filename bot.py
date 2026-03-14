from __future__ import annotations
import asyncio
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


def is_owner(interaction: discord.Interaction, owner_id: int) -> bool:
    return interaction.user.id == owner_id


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


async def maybe_send_notification(thread: discord.abc.Messageable, row, text: str):
    mode = row["notification_mode"]
    if mode == "mute":
        return
    if mode == "quiet" and not any(k in text for k in ["進化", "孵化", "旅", "病気"]):
        return
    if mode == "normal" and any(k in text for k in ["おなか", "ねむ", "うんち"]):
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
    """
    入口パネルは常に1件だけにする。
    BOT自身の welcome パネルを見つけたら、keep_message_id 以外は削除。
    """
    try:
        async for m in channel.history(limit=50):
            if m.author.id != bot.user.id:
                continue
            if not m.content:
                continue
            if WELCOME_MARKER not in m.content:
                continue
            if keep_message_id and m.id == keep_message_id:
                continue
            try:
                await m.delete()
            except Exception:
                pass
    except Exception:
        pass


async def delete_recent_thread_created_log(parent_channel: discord.TextChannel, thread_id: int):
    """
    親チャンネルに残るスレッド開始ログを、見つかった場合だけ消す。
    Discord側の仕様で消せないこともあるので best effort。
    """
    await asyncio.sleep(1.2)
    try:
        async for m in parent_channel.history(limit=10):
            if m.type == discord.MessageType.thread_created:
                # thread_created の対象スレッドを直接取れない環境もあるため、近傍ログを削除対象にする
                try:
                    await m.delete()
                except Exception:
                    pass
    except Exception:
        pass


async def create_clean_thread(parent_channel: discord.TextChannel, thread_name: str) -> discord.Thread:
    thread = await parent_channel.create_thread(
        name=thread_name,
        type=discord.ChannelType.public_thread,
        auto_archive_duration=60
    )
    bot.loop.create_task(delete_recent_thread_created_log(parent_channel, thread.id))
    return thread


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

    row, evo_msgs = game_logic.update_over_time(user_id, row)
    embed = await build_embed(row, transient=transient)

    content = prefix if prefix else None

    if evo_msgs:
        merged = "\n".join(evo_msgs)
        await upsert_system_log(thread, user_id, merged)

        for m in evo_msgs:
            await maybe_send_notification(thread, row, m)

        if row["journeyed"]:
            owned = database.fetch_collection(user_id)
            if owned:
                latest_character_id = owned[-1]["character_id"]
                character_name = CHARACTERS[latest_character_id]["name"]
            else:
                character_name = CHARACTERS[row["character_id"]]["name"]

            letter_embed = await build_letter_embed(character_name)
            if letter_embed:
                await thread.send(embed=letter_embed)

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
            await msg.edit(
                content=f"**{WELCOME_MARKER}**\n育成開始を押して遊んでね。",
                view=MainPanelView()
            )
            await cleanup_old_main_panels(channel, keep_message_id=msg.id)
            return
        except Exception:
            pass

    msg = await channel.send(
        f"**{WELCOME_MARKER}**\n育成開始を押して遊んでね。",
        view=MainPanelView()
    )
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
            return await interaction.response.send_message("サーバー内で使ってね。", ephemeral=True)

        row = database.fetch_pet(user.id)
        if row and not row["journeyed"]:
            return await interaction.response.send_message(
                "すでに育成中のデータがあるよ。『育成の続きから』を押して再開してね。",
                ephemeral=True
            )

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message("テキストチャンネルで使ってね。", ephemeral=True)

        try:
            thread = await create_clean_thread(channel, f"{user.display_name}っち")
            row, _ = game_logic.start_pet_if_needed(user.id, guild.id, thread.id)
            embed = await build_embed(row)
            panel = await thread.send(
                f"{user.mention} の育成スレッドができたよ！\n通知は最初は『たまごっち』設定です。忙しい時は設定で変えてね。",
                embed=embed,
                view=PetView(user.id)
            )
            database.update_pet(
                user.id,
                panel_message_id=str(panel.id),
                thread_id=str(thread.id),
                system_message_id=None,
            )
            await interaction.response.send_message(f"育成を開始したよ！ {thread.mention}", ephemeral=True)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"育成開始に失敗したよ。管理者に伝えてね。\n`{type(e).__name__}`", ephemeral=True)

    @discord.ui.button(label="育成の続きから", style=discord.ButtonStyle.blurple, custom_id="main:continue")
    async def continue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message("サーバー内で使ってね。", ephemeral=True)

        row = database.fetch_pet(user.id)
        if not row or row["journeyed"]:
            return await interaction.response.send_message(
                "続きの育成データが見つからないよ。『育成開始』から始めてね。",
                ephemeral=True
            )

        thread = None
        if row["thread_id"]:
            try:
                thread = bot.get_channel(int(row["thread_id"]))
                if thread is None:
                    thread = await bot.fetch_channel(int(row["thread_id"]))
            except Exception:
                thread = None

        try:
            if thread is None:
                channel = interaction.channel
                if not isinstance(channel, discord.TextChannel):
                    return await interaction.response.send_message("テキストチャンネルで使ってね。", ephemeral=True)

                new_thread = await create_clean_thread(channel, f"{user.display_name}っち-つづき")
                database.update_pet(user.id, thread_id=str(new_thread.id), panel_message_id=None, system_message_id=None)
                row = database.fetch_pet(user.id)
                embed = await build_embed(row)
                panel = await new_thread.send(
                    f"{user.mention} の育成データを続きから復帰したよ！\n前のスレッドが見つからなかったため、新しいスレッドを作成しました。",
                    embed=embed,
                    view=PetView(user.id)
                )
                database.update_pet(user.id, panel_message_id=str(panel.id))
                return await interaction.response.send_message(
                    f"育成データを復帰したよ！ {new_thread.mention}",
                    ephemeral=True
                )

            panel_ok = False
            if row["panel_message_id"]:
                try:
                    await thread.fetch_message(int(row["panel_message_id"]))
                    panel_ok = True
                except Exception:
                    panel_ok = False

            if not panel_ok:
                embed = await build_embed(row)
                panel = await thread.send(
                    f"{user.mention} の育成パネルを再作成したよ！",
                    embed=embed,
                    view=PetView(user.id)
                )
                database.update_pet(user.id, panel_message_id=str(panel.id))

            await interaction.response.send_message(
                f"続きから再開できるよ！ {thread.mention}",
                ephemeral=True
            )
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"続きからの復帰に失敗したよ。管理者に伝えてね。\n`{type(e).__name__}`", ephemeral=True)

    @discord.ui.button(label="図鑑", style=discord.ButtonStyle.gray, custom_id="main:dex")
    async def dex(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            game_logic.build_dex_text(interaction.user.id),
            ephemeral=True,
            view=DexView(interaction.user.id, 0)
        )

    @discord.ui.button(label="あそびかた", style=discord.ButtonStyle.gray, custom_id="main:help")
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "【あそびかた】\n"
            "・育成開始で専用スレッドができる\n"
            "・スレッドが消えたら『育成の続きから』で復帰できる\n"
            "・ボタンでお世話する\n"
            "・卵のあいだは見守るだけ\n"
            "・通知はデフォルトで本家たまごっち風\n"
            "・忙しい時は設定→通知設定/スリープ設定がおすすめ\n"
            "・成熟後は旅立って図鑑に登録される",
            ephemeral=True
        )


class PetView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=None)
        self.owner_id = owner_id

    async def _owner_check(self, interaction: discord.Interaction) -> bool:
        if not is_owner(interaction, self.owner_id):
            await interaction.response.send_message("この子のお世話は本人だけができるよ。", ephemeral=True)
            return False
        return True

    async def _do_action(self, interaction, action):
        row = database.fetch_pet(self.owner_id)
        row, result, msgs, transient = game_logic.perform_action(self.owner_id, row, action)
        await interaction.response.defer()
        await refresh_panel_for_user(self.owner_id, prefix=result, transient=transient)

        thread = interaction.channel
        if msgs:
            await upsert_system_log(thread, self.owner_id, "\n".join(msgs))

        for m in msgs:
            await maybe_send_notification(thread, row, m)
            if row["journeyed"]:
                letter_embed = await build_letter_embed(CHARACTERS[row["character_id"]]["name"])
                if letter_embed:
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
            return await interaction.response.send_message(err, ephemeral=True)
        await interaction.response.send_message(
            "あそぶ音楽ゲームを選んでね。",
            ephemeral=True,
            view=MiniGameMenuView(self.owner_id)
        )

    @discord.ui.button(label="設定", style=discord.ButtonStyle.gray, row=3, custom_id="pet:settings")
    async def settings(self, interaction, button):
        if not await self._owner_check(interaction):
            return
        row = database.fetch_pet(self.owner_id)
        await interaction.response.send_message(
            f"通知モード: {game_logic.notification_mode_label(row['notification_mode'])}",
            ephemeral=True,
            view=SettingsView(self.owner_id)
        )

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
        if evo:
            await upsert_system_log(interaction.channel, self.owner_id, "\n".join(evo))
        for m in evo:
            await maybe_send_notification(interaction.channel, row, m)


class SettingsView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    @discord.ui.button(label="通知:たまごっち", style=discord.ButtonStyle.green)
    async def nt1(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("本人だけ変更できるよ。", ephemeral=True)
        database.update_pet(self.owner_id, notification_mode="tamagotchi")
        await interaction.response.send_message("通知モードを『たまごっち』にしたよ。", ephemeral=True)

    @discord.ui.button(label="通知:ふつう", style=discord.ButtonStyle.blurple)
    async def nt2(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("本人だけ変更できるよ。", ephemeral=True)
        database.update_pet(self.owner_id, notification_mode="normal")
        await interaction.response.send_message("通知モードを『ふつう』にしたよ。", ephemeral=True)

    @discord.ui.button(label="通知:静か", style=discord.ButtonStyle.gray, row=1)
    async def nt3(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("本人だけ変更できるよ。", ephemeral=True)
        database.update_pet(self.owner_id, notification_mode="quiet")
        await interaction.response.send_message("通知モードを『静か』にしたよ。", ephemeral=True)

    @discord.ui.button(label="通知:ミュート", style=discord.ButtonStyle.red, row=1)
    async def nt4(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("本人だけ変更できるよ。", ephemeral=True)
        database.update_pet(self.owner_id, notification_mode="mute")
        await interaction.response.send_message("通知モードを『ミュート』にしたよ。", ephemeral=True)

    @discord.ui.button(label="スリープ 00:00-07:00", style=discord.ButtonStyle.gray, row=2)
    async def sleep_default(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("本人だけ変更できるよ。", ephemeral=True)
        database.set_sleep_setting(self.owner_id, "00:00", "07:00")
        await interaction.response.send_message("スリープ時間を 00:00〜07:00 にしたよ。", ephemeral=True)

    @discord.ui.button(label="リセット", style=discord.ButtonStyle.red, row=2)
    async def reset(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("本人だけ変更できるよ。", ephemeral=True)
        await interaction.response.send_message("本当に最初からやり直す？", ephemeral=True, view=ResetConfirmView(self.owner_id))


class ResetConfirmView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id

    @discord.ui.button(label="はい", style=discord.ButtonStyle.red)
    async def yes(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("本人だけ実行できるよ。", ephemeral=True)
        thread = interaction.channel
        database.delete_pet(self.owner_id)
        await interaction.response.send_message("リセットしたよ。スレッドを閉じるね。", ephemeral=True)
        try:
            await thread.delete()
        except Exception:
            pass

    @discord.ui.button(label="いいえ", style=discord.ButtonStyle.gray)
    async def no(self, interaction, button):
        await interaction.response.send_message("キャンセルしたよ。", ephemeral=True)


class MiniGameMenuView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    async def send_game(self, interaction, key: str):
        row = database.fetch_pet(self.owner_id)
        game, err = game_logic.start_minigame(self.owner_id, row, key)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        await interaction.response.send_message(
            f"**{game['title']}**\n{game['question']}",
            ephemeral=True,
            view=MiniGameAnswerView(self.owner_id, key)
        )

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
            return await interaction.response.send_message("本人だけが遊べるよ。", ephemeral=True)

        row = database.fetch_pet(self.owner_id)
        _, msg, evo = game_logic.resolve_minigame(self.owner_id, row, self.game_key, self.idx)

        await interaction.response.edit_message(
            content="このミニゲームは終了したよ。",
            view=None
        )
        await interaction.followup.send(
            msg + (("\n" + "\n".join(evo)) if evo else ""),
            ephemeral=True
        )
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
            return await interaction.response.send_message("これはあなたの図鑑表示だよ。", ephemeral=True)
        await interaction.response.send_message(
            game_logic.build_dex_detail(self.owner_id, self.values[0]),
            ephemeral=True
        )


class DexNavButton(discord.ui.Button):
    def __init__(self, owner_id: int, page: int, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.gray)
        self.owner_id = owner_id
        self.page = page

    async def callback(self, interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("これはあなたの図鑑表示だよ。", ephemeral=True)
        await interaction.response.edit_message(
            content=game_logic.build_dex_text(self.owner_id),
            view=DexView(self.owner_id, self.page)
        )


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
        msg = await channel.send(
            f"**{WELCOME_MARKER}**\n育成開始を押して遊んでね。",
            view=MainPanelView()
        )
        database.set_meta("main_panel_message_id", str(msg.id))
        await cleanup_old_main_panels(channel, keep_message_id=msg.id)


@bot.command()
async def status(ctx):
    row = database.fetch_pet(ctx.author.id)
    if not row:
        return await ctx.send("まだ育成していないよ。")
    row, evo = game_logic.update_over_time(ctx.author.id, row)
    embed = await build_embed(row)
    await ctx.send(("\n".join(evo)) if evo else None, embed=embed)


@bot.command()
async def dex(ctx):
    await ctx.send(game_logic.build_dex_text(ctx.author.id), view=DexView(ctx.author.id, 0))


@bot.command()
async def set_sleep(ctx, start: str, end: str):
    database.set_sleep_setting(ctx.author.id, start, end)
    await ctx.send(f"スリープ時間を {start}〜{end} に設定したよ。")


if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
