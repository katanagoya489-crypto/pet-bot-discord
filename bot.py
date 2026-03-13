
from __future__ import annotations
import asyncio
import discord
from discord.ext import commands
import database
import game_logic
from game_data import CHARACTERS, DEX_TARGETS, MUSIC_GAMES
from config import DISCORD_BOT_TOKEN, ENTRY_CHANNEL_ID, ADMIN_USER_IDS

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

def is_owner(interaction: discord.Interaction, owner_id: int) -> bool:
    return interaction.user.id == owner_id

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
            if row["thread_id"]:
                return await interaction.response.send_message(f"すでに育成中だよ。スレッド <#{row['thread_id']}> を見てね。", ephemeral=True)

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message("テキストチャンネルで使ってね。", ephemeral=True)

        thread = await channel.create_thread(name=f"{user.display_name}っち", type=discord.ChannelType.public_thread, auto_archive_duration=60)
        row, created = game_logic.start_pet_if_needed(user.id, guild.id, thread.id)
        await thread.send(
            f"{user.mention} の育成スレッドができたよ！\n\n"
            f"**{CHARACTERS[row['character_id']]['name']}** が生まれた！",
            view=PetView(user.id)
        )
        await interaction.response.send_message(f"育成を開始したよ！ {thread.mention}", ephemeral=True)

    @discord.ui.button(label="図鑑", style=discord.ButtonStyle.blurple, custom_id="main:dex")
    async def dex(self, interaction: discord.Interaction, button: discord.ui.Button):
        text = game_logic.build_dex_text(interaction.user.id)
        await interaction.response.send_message(text, ephemeral=True, view=DexView(interaction.user.id, 0))

    @discord.ui.button(label="あそびかた", style=discord.ButtonStyle.gray, custom_id="main:help")
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "【あそびかた】\n"
            "・育成開始で専用スレッドができる\n"
            "・ボタンでお世話する\n"
            "・夜は呼び出しが止まりやすい\n"
            "・おるすばん開始/終了で留守中の結果をまとめて見られる\n"
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

    async def _refresh(self, interaction: discord.Interaction, prefix: str = ""):
        row = database.fetch_pet(self.owner_id)
        if row is None:
            return await interaction.followup.send("データが見つからないよ。", ephemeral=True)
        row, evo_msgs = game_logic.update_over_time(self.owner_id, row)
        text = game_logic.status_lines(row)
        if prefix:
            text = prefix + "\n\n" + text
        if evo_msgs:
            text += "\n\n" + "\n".join(evo_msgs)
        await interaction.message.edit(content=text, view=PetView(self.owner_id))

    @discord.ui.button(label="ごはん", style=discord.ButtonStyle.green, custom_id="pet:feed")
    async def feed(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction): return
        row = database.fetch_pet(self.owner_id)
        row, result, evo = game_logic.perform_action(self.owner_id, row, "feed")
        await interaction.response.defer()
        await self._refresh(interaction, result)

    @discord.ui.button(label="おやつ", style=discord.ButtonStyle.blurple, custom_id="pet:snack")
    async def snack(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction): return
        row = database.fetch_pet(self.owner_id)
        row, result, evo = game_logic.perform_action(self.owner_id, row, "snack")
        await interaction.response.defer()
        await self._refresh(interaction, result)

    @discord.ui.button(label="あそぶ", style=discord.ButtonStyle.blurple, row=1, custom_id="pet:play")
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction): return
        row = database.fetch_pet(self.owner_id)
        row, result, evo = game_logic.perform_action(self.owner_id, row, "play")
        await interaction.response.defer()
        await self._refresh(interaction, result)

    @discord.ui.button(label="ねる", style=discord.ButtonStyle.gray, row=1, custom_id="pet:sleep")
    async def sleep(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction): return
        row = database.fetch_pet(self.owner_id)
        row, result, evo = game_logic.perform_action(self.owner_id, row, "sleep")
        await interaction.response.defer()
        await self._refresh(interaction, result)

    @discord.ui.button(label="ようす", style=discord.ButtonStyle.gray, row=1, custom_id="pet:status")
    async def status(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction): return
        row = database.fetch_pet(self.owner_id)
        row, result, evo = game_logic.perform_action(self.owner_id, row, "status")
        await interaction.response.defer()
        await self._refresh(interaction, result)

    @discord.ui.button(label="しつけ", style=discord.ButtonStyle.red, row=2, custom_id="pet:discipline")
    async def discipline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction): return
        row = database.fetch_pet(self.owner_id)
        row, result, evo = game_logic.perform_action(self.owner_id, row, "discipline")
        await interaction.response.defer()
        await self._refresh(interaction, result)

    @discord.ui.button(label="おそうじ", style=discord.ButtonStyle.red, row=2, custom_id="pet:clean")
    async def clean(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction): return
        row = database.fetch_pet(self.owner_id)
        row, result, evo = game_logic.perform_action(self.owner_id, row, "clean")
        await interaction.response.defer()
        await self._refresh(interaction, result)

    @discord.ui.button(label="おくすり", style=discord.ButtonStyle.red, row=2, custom_id="pet:medicine")
    async def medicine(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction): return
        row = database.fetch_pet(self.owner_id)
        row, result, evo = game_logic.perform_action(self.owner_id, row, "medicine")
        await interaction.response.defer()
        await self._refresh(interaction, result)

    @discord.ui.button(label="ミニゲーム", style=discord.ButtonStyle.green, row=3, custom_id="pet:minigame")
    async def minigame(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction): return
        row = database.fetch_pet(self.owner_id)
        row, evo = game_logic.update_over_time(self.owner_id, row)
        await interaction.response.send_message("あそぶ音楽ゲームを選んでね。", ephemeral=True, view=MiniGameMenuView(self.owner_id))

    @discord.ui.button(label="更新", style=discord.ButtonStyle.gray, row=3, custom_id="pet:refresh")
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction): return
        await interaction.response.defer()
        await self._refresh(interaction, "🔄 ようすを更新したよ。")

    @discord.ui.button(label="おるすばん開始", style=discord.ButtonStyle.blurple, row=4, custom_id="pet:away_start")
    async def away_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction): return
        row = database.fetch_pet(self.owner_id)
        row, msg = game_logic.start_odekake(self.owner_id, row)
        await interaction.response.defer()
        await self._refresh(interaction, msg)

    @discord.ui.button(label="おるすばん終了", style=discord.ButtonStyle.blurple, row=4, custom_id="pet:away_stop")
    async def away_stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction): return
        row = database.fetch_pet(self.owner_id)
        row, msg, evo = game_logic.stop_odekake(self.owner_id, row)
        await interaction.response.defer()
        await self._refresh(interaction, msg)

class MiniGameMenuView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    async def send_game(self, interaction: discord.Interaction, key: str):
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
    async def rhythm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.send_game(interaction, "rhythm")

    @discord.ui.button(label="音あて", style=discord.ButtonStyle.green)
    async def instrument(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.send_game(interaction, "instrument")

    @discord.ui.button(label="メロディ", style=discord.ButtonStyle.green)
    async def melody(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.send_game(interaction, "melody")

class MiniGameAnswerView(discord.ui.View):
    def __init__(self, owner_id: int, game_key: str):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.game_key = game_key
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
        row, msg, evo = game_logic.resolve_minigame(self.owner_id, row, self.game_key, self.idx)
        await interaction.response.send_message(msg + ("\n" + "\n".join(evo) if evo else ""), ephemeral=True)

class DexView(discord.ui.View):
    def __init__(self, owner_id: int, page: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.page = page
        per = 4
        self.chunk = DEX_TARGETS[page*per:(page+1)*per]
        options = [discord.SelectOption(label=CHARACTERS[c]["name"], value=c) for c in self.chunk]
        self.add_item(DexSelect(owner_id, options))
        if page > 0:
            self.add_item(DexNavButton(owner_id, page-1, "前へ"))
        if (page+1)*per < len(DEX_TARGETS):
            self.add_item(DexNavButton(owner_id, page+1, "次へ"))

class DexSelect(discord.ui.Select):
    def __init__(self, owner_id: int, options):
        super().__init__(placeholder="詳細を見るキャラを選んでね", options=options)
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("これはあなたの図鑑表示だよ。", ephemeral=True)
        cid = self.values[0]
        await interaction.response.send_message(game_logic.build_dex_detail(self.owner_id, cid), ephemeral=True)

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

@bot.command()
async def setup_panel(ctx):
    if ADMIN_USER_IDS and ctx.author.id not in ADMIN_USER_IDS:
        return await ctx.send("管理者だけが使えるよ。")
    view = MainPanelView()
    await ctx.send("**○○っちへようこそ！**\n育成開始を押して遊んでね。", view=view)

@bot.command()
async def status(ctx):
    row = database.fetch_pet(ctx.author.id)
    if not row:
        return await ctx.send("まだ育成していないよ。")
    row, evo = game_logic.update_over_time(ctx.author.id, row)
    await ctx.send(game_logic.status_lines(row))

@bot.command()
async def dex(ctx):
    await ctx.send(game_logic.build_dex_text(ctx.author.id), view=DexView(ctx.author.id, 0))

@bot.command()
async def set_sleep(ctx, start: str, end: str):
    if ADMIN_USER_IDS and ctx.author.id not in ADMIN_USER_IDS:
        # player can still set their own sleep
        pass
    database.set_sleep_setting(ctx.author.id, start, end)
    await ctx.send(f"スリープ時間を {start}〜{end} に設定したよ。")

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
