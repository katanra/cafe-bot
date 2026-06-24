import discord
from discord import app_commands
from discord.ext import commands

SEP = ("· " * 14).strip()

LFG_VC_CATEGORY = "LFG"   # bot looks for this category first; falls back to no category

# ── Apex rank options ──────────────────────────────────────────────────────────

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
    "Predator": "🔴", "Master": "🟣", "Diamond": "💎", "Platinum": "🔵",
    "Gold": "🟡",     "Silver": "⬜",  "Bronze": "🟫",  "Rookie": "🆕",
}

# ── Apex mode options ──────────────────────────────────────────────────────────

APEX_MODE_OPTIONS = [
    discord.SelectOption(label="Battle Royale — Trios",  value="BR Trios",     description="Standard 3-person squads"),
    discord.SelectOption(label="Battle Royale — Duos",   value="BR Duos",      description="2-person squads"),
    discord.SelectOption(label="Battle Royale — Solos",  value="BR Solos",     description="Solo play"),
    discord.SelectOption(label="Ranked — Battle Royale", value="Ranked BR",    description="Competitive BR"),
    discord.SelectOption(label="Mixtape",                value="Mixtape",      description="Rotating casual modes"),
    discord.SelectOption(label="TDM",                    value="TDM",          description="Team Deathmatch"),
    discord.SelectOption(label="Gun Run",                value="Gun Run",      description="Weapon progression mode"),
    discord.SelectOption(label="Control",                value="Control",      description="Territory control"),
    discord.SelectOption(label="1v1 Duel",               value="1v1 Duel",     description="Firing Range custom duel"),
    discord.SelectOption(label="Custom Match",           value="Custom Match", description="Private lobby"),
]


# ── Select menus ──────────────────────────────────────────────────────────────

class ApexRankSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Set your Apex rank...",
            options=APEX_RANK_OPTIONS,
            min_values=1, max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        rank  = self.values[0]
        emoji = RANK_EMOJIS.get(rank, "")
        await interaction.response.send_message(
            f"→ {interaction.user.mention} is **{emoji} {rank}**"
        )


class ApexModeSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Select a game mode...",
            options=APEX_MODE_OPTIONS,
            min_values=1, max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        mode = self.values[0]
        await interaction.response.send_message(
            f"→ {interaction.user.mention} is looking for **{mode}**"
        )


class LFGView(discord.ui.View):
    def __init__(self, is_apex: bool = False):
        super().__init__(timeout=None)
        self.add_item(ApexRankSelect())
        if is_apex:
            self.add_item(ApexModeSelect())


# ── Cog ───────────────────────────────────────────────────────────────────────

class LFG(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lfg_posts: dict[int, int]        = {}  # {message_id: poster_id}
        self.origins:   dict[int, dict[int, int]] = {}  # {message_id: {user_id: channel_id}}
        self.lfg_vcs:   dict[int, int]        = {}  # {vc_id: message_id}

    # ── Core posting logic (used by /lfg command AND panel modal) ─────────────

    async def create_lfg_post(
        self,
        interaction: discord.Interaction,
        game: str,
        description: str,
        slots: int = 0
    ):
        guild    = interaction.guild
        is_apex  = "apex" in game.lower()

        # ── Create voice channel ───────────────────────────────────────────────
        vc = None
        try:
            # Find or skip the LFG category
            category = discord.utils.get(guild.categories, name=LFG_VC_CATEGORY)

            # Make it explicitly visible to everyone
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    speak=True
                )
            }
            vc = await guild.create_voice_channel(
                name=f"[ {game[:40]} ]",
                category=category,
                overwrites=overwrites,
                reason=f"LFG by {interaction.user}"
            )
        except discord.Forbidden:
            vc = None
        except Exception:
            vc = None

        # ── Build embed ────────────────────────────────────────────────────────
        slot_line = f"\n→  **Slots needed:** {slots}" if slots > 0 else ""
        vc_line   = f"\n→  🔊 Voice channel: {vc.mention}" if vc else ""
        mode_hint = "\n→  Use the **game mode** dropdown to show what you're queuing." if is_apex else ""

        embed = discord.Embed(
            title="◉  Looking For Group",
            description=(
                f"*{game}*\n"
                f"{SEP}\n"
                f"{description}"
                f"{slot_line}"
                f"{vc_line}\n"
                f"{SEP}\n"
                f"→  Posted by {interaction.user.mention}"
                f"{mode_hint}"
            ),
            color=0xB0C0F5
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        footer = "React ✅ to join host's VC  ·  Remove to go back  ·  Set your rank below"
        if is_apex:
            footer += "  ·  Pick a game mode"
        embed.set_footer(text=footer)

        view = LFGView(is_apex=is_apex)
        lfg_ping_role = discord.utils.get(guild.roles, name="LFG Ping")
        await interaction.response.send_message(
            content=lfg_ping_role.mention if lfg_ping_role else None,
            embed=embed,
            view=view
        )
        msg = await interaction.original_response()
        await msg.add_reaction("✅")

        # Track post and VC
        self.lfg_posts[msg.id] = interaction.user.id
        self.origins[msg.id]   = {}
        if vc:
            self.lfg_vcs[vc.id] = msg.id
            # Move poster in automatically if they're already in a VC
            member = interaction.user
            if isinstance(member, discord.Member) and member.voice and member.voice.channel:
                try:
                    await member.move_to(vc)
                except Exception:
                    pass

    # ── /lfg slash command ─────────────────────────────────────────────────────

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
        await self.create_lfg_post(interaction, game, description, slots)

    # ── Auto-delete VC when it empties ────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if before.channel and before.channel.id in self.lfg_vcs:
            if len(before.channel.members) == 0:
                vc_id = before.channel.id
                try:
                    await before.channel.delete(reason="LFG VC auto-deleted (empty)")
                except Exception:
                    pass
                self.lfg_vcs.pop(vc_id, None)

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
                    f"→ {reactor.mention} The host isn't in a voice channel right now.",
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
                        f"then react to be moved to {target_vc.mention}!",
                        delete_after=10
                    )
            return

        if reactor.voice.channel.id == target_vc.id:
            return

        self.origins[payload.message_id][reactor.id] = reactor.voice.channel.id

        try:
            await reactor.move_to(target_vc)
        except discord.Forbidden:
            self.origins[payload.message_id].pop(reactor.id, None)
            if text_channel:
                await text_channel.send(
                    f"→ {reactor.mention} I don't have permission to move you to {target_vc.mention}.",
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

        origin_ch_id = self.origins.get(payload.message_id, {}).pop(reactor.id, None)
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
