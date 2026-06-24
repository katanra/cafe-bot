import discord
from discord import app_commands
from discord.ext import commands

SEP = ("· " * 14).strip()

APEX_RANK_OPTIONS = [
    discord.SelectOption(label="Predator",  emoji="🔴", value="Predator",  description="Top 750 per platform"),
    discord.SelectOption(label="Master",    emoji="🟣", value="Master",    description="Masters tier"),
    discord.SelectOption(label="Diamond",   emoji="💎", value="Diamond",   description="Diamond tier"),
    discord.SelectOption(label="Platinum",  emoji="🔵", value="Platinum",  description="Platinum tier"),
    discord.SelectOption(label="Gold",      emoji="🟡", value="Gold",      description="Gold tier"),
    discord.SelectOption(label="Silver",    emoji="⬜", value="Silver",    description="Silver tier"),
    discord.SelectOption(label="Bronze",    emoji="🟫", value="Bronze",    description="Bronze tier"),
    discord.SelectOption(label="Rookie",    emoji="🆕", value="Rookie",    description="Starting out"),
]

RANK_EMOJIS = {
    "Predator": "🔴",
    "Master":   "🟣",
    "Diamond":  "💎",
    "Platinum": "🔵",
    "Gold":     "🟡",
    "Silver":   "⬜",
    "Bronze":   "🟫",
    "Rookie":   "🆕",
}


class ApexRankSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Set your Apex rank...",
            options=APEX_RANK_OPTIONS,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        rank  = self.values[0]
        emoji = RANK_EMOJIS.get(rank, "")
        await interaction.response.send_message(
            f"→ {interaction.user.mention} is **{emoji} {rank}**"
        )


class LFGView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ApexRankSelect())


class LFG(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # {message_id: poster_id}
        self.lfg_posts: dict[int, int] = {}
        # {message_id: {user_id: channel_id}} — original VC before being moved
        self.origins: dict[int, dict[int, int]] = {}

    @app_commands.command(name="lfg", description="Post a Looking For Group listing")
    @app_commands.describe(
        game="The game you're looking to play",
        description="What you're looking for",
        slots="How many extra players you need (optional)"
    )
    async def lfg(
        self,
        interaction: discord.Interaction,
        game: str,
        description: str,
        slots: int = 0
    ):
        slot_line = f"\n→  **Slots needed:** {slots}" if slots > 0 else ""
        embed = discord.Embed(
            title="◉  Looking For Group",
            description=(
                f"*{game}*\n"
                f"{SEP}\n"
                f"{description}"
                f"{slot_line}\n"
                f"{SEP}\n"
                f"→  Posted by {interaction.user.mention}"
            ),
            color=0xB0C0F5
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(
            text="React ✅ to join host's VC · Remove reaction to go back · Select your rank below"
        )
        view = LFGView()
        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()
        await msg.add_reaction("✅")
        self.lfg_posts[msg.id] = interaction.user.id
        self.origins[msg.id]   = {}

    # ── React ✅ → move to host VC ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) != "✅":
            return
        if payload.message_id not in self.lfg_posts:
            return
        if payload.user_id == self.bot.user.id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        reactor = guild.get_member(payload.user_id)
        if not reactor or reactor.bot:
            return

        poster_id    = self.lfg_posts[payload.message_id]
        text_channel = guild.get_channel(payload.channel_id)

        if reactor.id == poster_id:
            return

        poster = guild.get_member(poster_id)

        if not poster or not poster.voice or not poster.voice.channel:
            if text_channel:
                await text_channel.send(
                    f"→ {reactor.mention} The LFG host isn't in a voice channel right now.",
                    delete_after=8
                )
            return

        target_vc = poster.voice.channel

        if not reactor.voice or not reactor.voice.channel:
            try:
                await reactor.send(
                    f"→ Join any voice channel first, then react again "
                    f"to be moved to **{target_vc.name}**!"
                )
            except discord.Forbidden:
                if text_channel:
                    await text_channel.send(
                        f"→ {reactor.mention} Join a voice channel first, "
                        f"then react again to be moved to {target_vc.mention}!",
                        delete_after=10
                    )
            return

        if reactor.voice.channel.id == target_vc.id:
            return

        # Remember where they came from
        self.origins[payload.message_id][reactor.id] = reactor.voice.channel.id

        try:
            await reactor.move_to(target_vc)
        except discord.Forbidden:
            self.origins[payload.message_id].pop(reactor.id, None)
            if text_channel:
                await text_channel.send(
                    f"→ {reactor.mention} I don't have permission to move you "
                    f"to {target_vc.mention}.",
                    delete_after=8
                )
        except Exception:
            self.origins[payload.message_id].pop(reactor.id, None)

    # ── Un-react → move back to original VC ───────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) != "✅":
            return
        if payload.message_id not in self.lfg_posts:
            return
        if payload.user_id == self.bot.user.id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        reactor = guild.get_member(payload.user_id)
        if not reactor or reactor.bot:
            return

        msg_origins  = self.origins.get(payload.message_id, {})
        origin_ch_id = msg_origins.pop(reactor.id, None)
        if not origin_ch_id:
            return

        origin_channel = guild.get_channel(origin_ch_id)
        if not origin_channel:
            return

        if not reactor.voice or not reactor.voice.channel:
            return

        try:
            await reactor.move_to(origin_channel)
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(LFG(bot))
