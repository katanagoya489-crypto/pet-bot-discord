
from __future__ import annotations
import asyncio
from typing import Optional
import discord
from discord.ext import commands

import database
import game_logic
import image_service
from game_data import CHARACTERS, DEX_TARGETS, MUSIC_GAMES
from config import DISCORD_BOT_TOKEN, ADMIN_USER_IDS, ENTRY_CHANNEL_ID, AUTO_TICK_SECONDS, THREAD_AUTO_ARCHIVE_MINUTES

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

def is_owner(interaction: discord.Interaction, owner_id: int) -> bool:
    return interaction.user.id == owner_id

async def build_pet_embed(row, transient: str | None = None) -> discord.Embed:
    embed = discord.Embed(description=game_logic.status_lines(row))
    key = game_logic.image_key_for_pet(row, transient=transient)
    url = await image_service.get_image_url(bot, key)
    if url:
        embed.set_image(url=url)
    return embed

async def build_letter_embed(character_name: str) -> Optional[discord.Embed]:
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
    if mode == "quiet" and not any(k in text for k in ["進化", "旅", "病気", "孵化"]):
        return
    if mode == "normal" and any(k in text for k in ["おなか", "ねむ", "うんち"]):
        return
    await thread.send(text)

async def render_panel(user_id: int, prefix: str = "", transient: str | None = None):
    row = database.fetch_pet(user_id)
    if not row or not row["thread_id"] or not row["panel_message_id"]:
        return
    try:
        thread = bot.get_channel(int(row["thread_id"])) or await bot.fetch_channel(int(row["thread_id"]))
        msg = await thread.fetch_message(int(row["panel_message_id"]))
    except Exception:
        return
    row, evo_msgs = game_logic.update_over_time(user_id, row)
    embed = await build_pet_embed(row, transient=transient)
    content = prefix or None
    await msg.edit(content=content, embed=embed, view=PetView(user_id))
    for evo in evo_msgs:
        await maybe_send_notification(thread, row, evo)
    if row["journeyed"]:
        letter_embed = await build_letter_embed(CHARACTERS[row["character_id"]]["name"])
        if letter_embed:
            await thread.send(embed=letter_embed)

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
            await msg.edit(content="**○○っちへようこそ！**\n育成開始を押して遊んでね。", view=MainPanelView())
            return
        except Exception:
            pass
    msg = await channel.send("**○○っちへようこそ！**\n育成開始を押して遊んでね。", view=MainPanelView())
    database.set_meta("main_panel_message_id", str(msg.id))

async def auto_tick_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        rows = database.fetch_all_active_pets()
        for row in rows:
            try:
                await render_panel(int(row["user_id"]))
            except Exception:
                pass
        await asyncio.sleep(AUTO_TICK_SECONDS)

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
        if row and not row["journeyed"] and row["thread_id"]:
            return await interaction.response.send_message(f"すでに育成中だよ。スレッド <#{row['thread_id']}> を見てね。", ephemeral=True)

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message("テキストチャンネルで使ってね。", ephemeral=True)

        thread = await channel.create_thread(
            name=f"{user.display_name}っち",
            type=discord.ChannelType.public_thread,
            auto_archive_duration=THREAD_AUTO_ARCHIVE_MINUTES if THREAD_AUTO_ARCHIVE_MINUTES in [60, 1440, 4320, 10080] else 60,
        )
        row, _ = game_logic.start_pet_if_needed(user.id, guild.id, thread.id)
        embed = await build_pet_embed(row)
        panel = await thread.send(
            f"{user.mention} の育成スレッドができたよ！\n"
            "【通知について】\n"
            "この育成ゲームは、たまごっち風に通知が多めです。\n"
            "忙しい時や寝る前は設定から通知モードやスリープを調整してね。",
            embed=embed,
            view=PetView(user.id),
        )
        database.update_pet(user.id, panel_message_id=str(panel.id))
        await interaction.response.send_message(f"育成を開始したよ！ {thread.mention}", ephemeral=True)

    @discord.ui.button(label="図鑑", style=discord.ButtonStyle.blurple, custom_id="main:dex")
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

    async def _do_action(self, interaction: discord.Interaction, action: str):
        row = database.fetch_pet(self.owner_id)
        if not row:
            return await interaction.response.send_message("育成データが見つからないよ。", ephemeral=True)
        row, result, evo_msgs, transient = game_logic.perform_action(self.owner_id, row, action)
        await interaction.response.defer()
        await render_panel(self.owner_id, prefix=result, transient=transient)
        for msg in evo_msgs:
            await maybe_send_notification(interaction.channel, row, msg)

    @discord.ui.button(label="ごはん", style=discord.ButtonStyle.green, custom_id="pet:feed")
    async def feed(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "feed")

    @discord.ui.button(label="おやつ", style=discord.ButtonStyle.blurple, custom_id="pet:snack")
    async def snack(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "snack")

    @discord.ui.button(label="あそぶ", style=discord.ButtonStyle.blurple, row=1, custom_id="pet:play")
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "play")

    @discord.ui.button(label="ねる", style=discord.ButtonStyle.gray, row=1, custom_id="pet:sleep")
    async def sleep(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "sleep")

    @discord.ui.button(label="ようす", style=discord.ButtonStyle.gray, row=1, custom_id="pet:status")
    async def status(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "status")

    @discord.ui.button(label="しつけ", style=discord.ButtonStyle.red, row=2, custom_id="pet:discipline")
    async def discipline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "discipline")

    @discord.ui.button(label="おそうじ", style=discord.ButtonStyle.red, row=2, custom_id="pet:clean")
    async def clean(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "clean")

    @discord.ui.button(label="おくすり", style=discord.ButtonStyle.red, row=2, custom_id="pet:medicine")
    async def medicine(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._owner_check(interaction):
            await self._do_action(interaction, "medicine")

    @discord.ui.button(label="ミニゲーム", style=discord.ButtonStyle.green, row=3, custom_id="pet:minigame")
    async def minigame(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction):
            return
        row = database.fetch_pet(self.owner_id)
        _, err = game_logic.start_minigame(self.owner_id, row, "rhythm")
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        await interaction.response.send_message("あそぶ音楽ゲームを選んでね。", ephemeral=True, view=MiniGameMenuView(self.owner_id))

    @discord.ui.button(label="設定", style=discord.ButtonStyle.gray, row=3, custom_id="pet:settings")
    async def settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction):
            return
        row = database.fetch_pet(self.owner_id)
        await interaction.response.send_message(
            f"通知モード: {game_logic.notification_mode_label(row['notification_mode'])}",
            ephemeral=True,
            view=SettingsView(self.owner_id)
        )

    @discord.ui.button(label="おるすばん開始", style=discord.ButtonStyle.blurple, row=4, custom_id="pet:away_start")
    async def away_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction):
            return
        row = database.fetch_pet(self.owner_id)
        _, msg = game_logic.start_odekake(self.owner_id, row)
        await interaction.response.defer()
        await render_panel(self.owner_id, prefix=msg)

    @discord.ui.button(label="おるすばん終了", style=discord.ButtonStyle.blurple, row=4, custom_id="pet:away_stop")
    async def away_stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction):
            return
        row = database.fetch_pet(self.owner_id)
        _, msg, evo = game_logic.stop_odekake(self.owner_id, row)
        await interaction.response.defer()
        await render_panel(self.owner_id, prefix=msg)
        for item in evo:
            await maybe_send_notification(interaction.channel, row, item)

class SettingsView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    async def _guard(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("本人だけ変更できるよ。", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="通知:たまごっち", style=discord.ButtonStyle.green)
    async def nt1(self, interaction, button):
        if not await self._guard(interaction): return
        database.update_pet(self.owner_id, notification_mode="tamagotchi")
        await interaction.response.send_message("通知モードを『たまごっち』にしたよ。", ephemeral=True)

    @discord.ui.button(label="通知:ふつう", style=discord.ButtonStyle.blurple)
    async def nt2(self, interaction, button):
        if not await self._guard(interaction): return
        database.update_pet(self.owner_id, notification_mode="normal")
        await interaction.response.send_message("通知モードを『ふつう』にしたよ。", ephemeral=True)

    @discord.ui.button(label="通知:静か", style=discord.ButtonStyle.gray, row=1)
    async def nt3(self, interaction, button):
        if not await self._guard(interaction): return
        database.update_pet(self.owner_id, notification_mode="quiet")
        await interaction.response.send_message("通知モードを『静か』にしたよ。", ephemeral=True)

    @discord.ui.button(label="通知:ミュート", style=discord.ButtonStyle.red, row=1)
    async def nt4(self, interaction, button):
        if not await self._guard(interaction): return
        database.update_pet(self.owner_id, notification_mode="mute")
        await interaction.response.send_message("通知モードを『ミュート』にしたよ。", ephemeral=True)

    @discord.ui.button(label="スリープ 00:00-07:00", style=discord.ButtonStyle.gray, row=2)
    async def sleep_default(self, interaction, button):
        if not await self._guard(interaction): return
        database.set_sleep_setting(self.owner_id, "00:00", "07:00")
        await interaction.response.send_message("スリープ時間を 00:00〜07:00 にしたよ。", ephemeral=True)

    @discord.ui.button(label="リセット", style=discord.ButtonStyle.red, row=2)
    async def reset(self, interaction, button):
        if not await self._guard(interaction): return
        await interaction.response.send_message("本当に最初からやり直す？", ephemeral=True, view=ResetConfirmView(self.owner_id))

class ResetConfirmView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id

    @discord.ui.button(label="はい", style=discord.ButtonStyle.red)
    async def yes(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("本人だけ実行できるよ。", ephemeral=True)
        row = database.fetch_pet(self.owner_id)
        database.delete_pet(self.owner_id)
        await interaction.response.send_message("リセットしたよ。スレッドを閉じるね。", ephemeral=True)
        if row and row["thread_id"]:
            try:
                thread = bot.get_channel(int(row["thread_id"])) or await bot.fetch_channel(int(row["thread_id"]))
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

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("本人だけが遊べるよ。", ephemeral=True)
        row = database.fetch_pet(self.owner_id)
        _, msg, evo = game_logic.resolve_minigame(self.owner_id, row, self.game_key, self.idx)
        await interaction.response.send_message(msg + (("\n" + "\n".join(evo)) if evo else ""), ephemeral=True)
        await render_panel(self.owner_id)

class DexView(discord.ui.View):
    def __init__(self, owner_id: int, page: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.page = page
        per = 4
        chunk = DEX_TARGETS[page * per:(page + 1) * per]
        options = [discord.SelectOption(label=CHARACTERS[c]["name"], value=c) for c in chunk]
        self.add_item(DexSelect(owner_id, options))
        if page > 0:
            self.add_item(DexNavButton(owner_id, page - 1, "前へ"))
        if (page + 1) * per < len(DEX_TARGETS):
            self.add_item(DexNavButton(owner_id, page + 1, "次へ"))

class DexSelect(discord.ui.Select):
    def __init__(self, owner_id: int, options):
        super().__init__(placeholder="詳細を見るキャラを選んでね", options=options)
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("これはあなたの図鑑表示だよ。", ephemeral=True)
        await interaction.response.send_message(game_logic.build_dex_detail(self.owner_id, self.values[0]), ephemeral=True)

class DexNavButton(discord.ui.Button):
    def __init__(self, owner_id: int, page: int, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.gray)
        self.owner_id = owner_id
        self.page = page

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("これはあなたの図鑑表示だよ。", ephemeral=True)
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
    msg = await ctx.send("**○○っちへようこそ！**\n育成開始を押して遊んでね。", view=MainPanelView())
    database.set_meta("main_panel_message_id", str(msg.id))

@bot.command()
async def status(ctx):
    row = database.fetch_pet(ctx.author.id)
    if not row:
        return await ctx.send("まだ育成していないよ。")
    row, evo = game_logic.update_over_time(ctx.author.id, row)
    embed = await build_pet_embed(row)
    await ctx.send(content="\n".join(evo) if evo else None, embed=embed)

@bot.command()
async def dex(ctx):
    await ctx.send(game_logic.build_dex_text(ctx.author.id), view=DexView(ctx.author.id, 0))

@bot.command()
async def set_sleep(ctx, start: str, end: str):
    database.set_sleep_setting(ctx.author.id, start, end)
    await ctx.send(f"スリープ時間を {start}〜{end} に設定したよ。")

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
