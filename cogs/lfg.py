import discord
from discord import app_commands
from discord.ext import commands
import os

SEP = ("· " * 14).strip()

LFG_VC_CATEGORY_ID = 1515950863422586950

# ── Rank image map ─────────────────────────────────────────────────────────────
_IMG_DIR = os.path.join(os.path.dirname(__file__), "..")

RANK_IMAGES: dict[str, str] = {
    "Predator": os.path.join(_IMG_DIR, "Pred.png"),
    "Master":   os.path.join(_IMG_DIR, "Master.png"),
    "Diamond":  os.path.join(_IMG_DIR, "diamond.png"),
    "Platinum": os.path.join(_IMG_DIR, "Plat.png"),
    "Gold":     os.path.join(_IMG_DIR, "Gold.png"),
    "Silver":   os.path.join(_IMG_DIR, "Silver.png"),
    "Bronze":   os.path.join(_IMG_DIR, "Bronze.png"),
}

# ── Rank colors ───────────────────────────────────────────────────────────────
RANK_COLORS: dict[str, int] = {
    "Predator": 0xFFB3B3,   # pastel red
    "Master":   0xD4AAEE,   # pastel purple
    "Diamond":  0xADD8F7,   # pastel blue
    "Platinum": 0xAFEEEE,   # pastel teal
    "Gold":     0xFFE599,   # pastel gold
    "Silver":   0xDDDDDD,   # pastel silver
    "Bronze":   0xE8C49A,   # pastel bronze
    "Rookie":   0xD0D0D0,   # pastel grey
}

APEX_RANK_OPTIONS = [
    discord.SelectOption(label="Predator",  value="Predator",  description="Top 750 per platform"),
    discord.SelectOption(label="Master",    value="Master",    description="Masters tier"),
    discord.SelectOption(label="Diamond",   value="Diamond",   description="Diamond tier"),
    discord.SelectOption(label="Platinum",  value="Platinum",  description="Platinum tier"),
    discord.SelectOption(label="Gold",      value="Gold",      description="Gold tier"),
    discord.SelectOption(label="Silver",    value="Silver",    description="Silver tier"),
    discord.SelectOption(label="Bronze",    value="Bronze",    description="Bronze tier"),
    discord.SelectOption(label="Rookie",    value="Rookie",    description="Starting out"),
]


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_vc_category(guild: discord.Guild):
    cat = guild.get_channel(LFG_VC_CATEGORY_ID)
    if cat is None:
        try:
            cat = await guild.fetch_channel(LFG_VC_CATEGORY_ID)
        except Exception as e:
            print(f"[LFG] fetch_channel failed: {e}")
    return cat if isinstance(cat, discord.CategoryChannel) else None


async def _create_and_move(
    guild: discord.Guild,
    vc_name: str,
    user: discord.Member,
) -> discord.VoiceChannel | None:
    """Create the VC and immediately move the poster into it if they're in voice."""
    try:
        category = await _get_vc_category(guild)
        vc = await guild.create_voice_channel(
            name=f"[ {vc_name[:40]} ]",
            category=category,
            overwrites={
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    speak=True,
                    send_messages=True,
                    read_message_history=True,
                )
            },
            reason=f"LFG by {user}"
        )
    except Exception as e:
        print(f"[LFG] VC creation error: {e}")
        return None

    if isinstance(user, discord.Member) and user.voice and user.voice.channel:
        try:
            await user.move_to(vc)
        except Exception as e:
            print(f"[LFG] Auto-move failed: {e}")

    return vc


# ── Ranked Modal ───────────────────────────────────────────────────────────────
# Shown after rank is selected — always has a notes field, VC name only if create_vc=True

class RankedModal(discord.ui.Modal, title="Ranked BR  —  Apex Legends"):
    def __init__(self, cog, rank: str, create_vc: bool):
        super().__init__()
        self.cog       = cog
        self.rank      = rank
        self.create_vc = create_vc

        # VC name only needed when creating a voice channel
        if create_vc:
            self.vc_field = discord.ui.TextInput(
                label="Voice Channel Name",
                placeholder="e.g. Ranked grind, Diamond push...",
                min_length=1,
                max_length=40
            )
            self.add_item(self.vc_field)

        self.notes_field = discord.ui.TextInput(
            label="Notes",
            style=discord.TextStyle.paragraph,
            placeholder="e.g. Diamond+ only, mic preferred, chill grind welcome...",
            required=False,
            max_length=300
        )
        self.add_item(self.notes_field)

    async def on_submit(self, interaction: discord.Interaction):
        notes = self.notes_field.value.strip()
        vc    = None

        if self.create_vc:
            name = self.vc_field.value.strip()
            vc   = await _create_and_move(interaction.guild, name, interaction.user)

        embed = _build_ranked_embed(interaction.user, self.rank, vc, notes)
        msg   = await _send_lfg(interaction, embed, rank=self.rank)
        self.cog._track(msg, interaction.user.id, vc)
        await interaction.response.send_message("LFG posted!", ephemeral=True)


# ── VC Name Modal (standard modes — BR Trios, Duos, etc.) ─────────────────────

class VCNameModal(discord.ui.Modal, title="Name Your Voice Channel"):
    vc_name = discord.ui.TextInput(
        label="Voice Channel Name",
        placeholder="e.g. Ranked grind, Chill BR, Apex squad...",
        min_length=1,
        max_length=40
    )

    def __init__(self, cog, game: str, mode: str | None, rank: str | None):
        super().__init__()
        self.cog  = cog
        self.game = game
        self.mode = mode
        self.rank = rank

    async def on_submit(self, interaction: discord.Interaction):
        name  = self.vc_name.value.strip()
        vc    = await _create_and_move(interaction.guild, name, interaction.user)
        embed = _build_embed(interaction.user, self.game, self.mode, self.rank, 0, vc)
        msg   = await _send_lfg(interaction, embed, rank=self.rank)
        self.cog._track(msg, interaction.user.id, vc)
        await interaction.response.send_message("LFG posted!", ephemeral=True)


# ── Modals ─────────────────────────────────────────────────────────────────────

class CustomLobbyModal(discord.ui.Modal, title="Custom Match  —  Apex Legends"):
    code = discord.ui.TextInput(
        label="Lobby Code",
        placeholder="Paste your lobby code here",
        min_length=1,
        max_length=30
    )
    vc_name = discord.ui.TextInput(
        label="Voice Channel Name",
        placeholder="e.g. Apex customs, Friday customs...",
        min_length=1,
        max_length=40,
        required=False
    )
    notes = discord.ui.TextInput(
        label="Notes",
        style=discord.TextStyle.paragraph,
        placeholder="Rules, settings, what you need...",
        required=False,
        max_length=200
    )

    def __init__(self, cog, create_vc: bool = True):
        super().__init__()
        self.cog       = cog
        self.create_vc = create_vc
        if not create_vc:
            self.vc_name.label       = "Voice Channel Name  (skipped)"
            self.vc_name.placeholder = "Not used since you chose no VC"

    async def on_submit(self, interaction: discord.Interaction):
        code  = self.code.value.strip()
        notes = self.notes.value.strip()
        guild = interaction.guild

        if self.create_vc:
            name = self.vc_name.value.strip() or "Apex Legends"
            vc   = await _create_and_move(guild, name, interaction.user)
        else:
            vc = None

        embed = discord.Embed(
            title="Custom Match  —  Apex Legends",
            color=0xCDB4DB
        )
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url
        )
        embed.add_field(name="Lobby Code", value=f"```\n{code}\n```", inline=False)
        if notes:
            embed.add_field(name="Notes", value=notes, inline=False)
        if vc:
            embed.add_field(name="Voice Channel", value=vc.mention, inline=False)
        embed.set_footer(text="Copy the code above  ·  React ✅ to join the host's VC")

        msg = await _send_lfg(interaction, embed)
        self.cog._track(msg, interaction.user.id, vc)
        await interaction.response.send_message("Custom lobby posted!", ephemeral=True)


class OtherGameModal(discord.ui.Modal, title="Post LFG"):
    game = discord.ui.TextInput(
        label="Game",
        placeholder="e.g. Valorant, Fortnite",
        max_length=50
    )
    description = discord.ui.TextInput(
        label="What are you looking for?",
        style=discord.TextStyle.paragraph,
        placeholder="e.g. Need 2 more for ranked, chill vibes",
        max_length=300
    )
    slots = discord.ui.TextInput(
        label="Slots needed  (optional)",
        placeholder="e.g. 2",
        required=False,
        max_length=2
    )
    vc_name = discord.ui.TextInput(
        label="Voice Channel Name  (optional)",
        placeholder="Leave blank to use game name",
        required=False,
        max_length=40
    )

    def __init__(self, cog, create_vc: bool = True):
        super().__init__()
        self.cog       = cog
        self.create_vc = create_vc

    async def on_submit(self, interaction: discord.Interaction):
        game  = self.game.value.strip()
        desc  = self.description.value.strip()
        slots = 0
        try:
            slots = int(self.slots.value) if self.slots.value.strip() else 0
        except ValueError:
            pass

        if self.create_vc:
            name = self.vc_name.value.strip() or game
            vc   = await _create_and_move(interaction.guild, name, interaction.user)
        else:
            vc = None

        embed = _build_embed(interaction.user, game, None, None, slots, vc, desc)
        msg   = await _send_lfg(interaction, embed)
        self.cog._track(msg, interaction.user.id, vc)
        await interaction.response.send_message("LFG posted!", ephemeral=True)


# ── Rank select ────────────────────────────────────────────────────────────────

class ApexRankView(discord.ui.View):
    def __init__(self, cog, create_vc: bool = True):
        super().__init__(timeout=120)
        self.cog       = cog
        self.create_vc = create_vc
        sel            = discord.ui.Select(
            placeholder="Choose your rank...",
            options=APEX_RANK_OPTIONS
        )
        sel.callback = self._on_rank
        self.add_item(sel)

    async def _on_rank(self, interaction: discord.Interaction):
        rank = interaction.data["values"][0]
        # RankedModal handles both VC name (if needed) and notes
        await interaction.response.send_modal(
            RankedModal(self.cog, rank=rank, create_vc=self.create_vc)
        )


# ── Apex mode buttons ──────────────────────────────────────────────────────────

class ApexModeView(discord.ui.View):
    def __init__(self, cog, create_vc: bool = True):
        super().__init__(timeout=120)
        self.cog       = cog
        self.create_vc = create_vc

    async def _post(self, interaction: discord.Interaction, mode: str):
        if self.create_vc:
            await interaction.response.send_modal(
                VCNameModal(self.cog, "Apex Legends", mode, None)
            )
        else:
            await interaction.response.edit_message(content="LFG posted!", view=None, embeds=[])
            embed = _build_embed(interaction.user, "Apex Legends", mode, None, 0, None)
            msg   = await _send_lfg(interaction, embed)
            self.cog._track(msg, interaction.user.id, None)

    # Row 0  ——  Battle Royale
    @discord.ui.button(label="BR Trios",   style=discord.ButtonStyle.primary,   row=0)
    async def br_trios(self, i, b):  await self._post(i, "BR Trios")

    @discord.ui.button(label="BR Duos",    style=discord.ButtonStyle.primary,   row=0)
    async def br_duos(self, i, b):   await self._post(i, "BR Duos")

    @discord.ui.button(label="Ranked BR",  style=discord.ButtonStyle.danger,    row=0)
    async def ranked_br(self, i, b):
        await i.response.edit_message(
            content="Select your rank:",
            view=ApexRankView(self.cog, self.create_vc),
            embeds=[]
        )

    @discord.ui.button(label="Mixtape",    style=discord.ButtonStyle.secondary, row=0)
    async def mixtape(self, i, b):   await self._post(i, "Mixtape")

    # Row 1  ——  Arcade & Custom
    @discord.ui.button(label="TDM",          style=discord.ButtonStyle.secondary, row=1)
    async def tdm(self, i, b):       await self._post(i, "TDM")

    @discord.ui.button(label="Gun Run",       style=discord.ButtonStyle.secondary, row=1)
    async def gun_run(self, i, b):   await self._post(i, "Gun Run")

    @discord.ui.button(label="Control",       style=discord.ButtonStyle.secondary, row=1)
    async def control(self, i, b):   await self._post(i, "Control")

    @discord.ui.button(label="1v1 Duel",      style=discord.ButtonStyle.secondary, row=1)
    async def duel_1v1(self, i, b):  await self._post(i, "1v1 Duel")

    @discord.ui.button(label="Custom Match",  style=discord.ButtonStyle.success,   row=1)
    async def custom_match(self, i, b):
        await i.response.send_modal(CustomLobbyModal(self.cog, self.create_vc))


# ── Game select ────────────────────────────────────────────────────────────────

class GameSelectView(discord.ui.View):
    def __init__(self, cog, create_vc: bool = True):
        super().__init__(timeout=120)
        self.cog       = cog
        self.create_vc = create_vc

    @discord.ui.button(label="Apex Legends",   style=discord.ButtonStyle.primary,   row=0)
    async def apex(self, interaction: discord.Interaction, button):
        await interaction.response.edit_message(
            content="Select a game mode:",
            view=ApexModeView(self.cog, self.create_vc),
            embeds=[]
        )

    @discord.ui.button(label="Other game...",  style=discord.ButtonStyle.secondary, row=0)
    async def other(self, interaction: discord.Interaction, button):
        await interaction.response.send_modal(OtherGameModal(self.cog, self.create_vc))


# ── VC choice (entry point) ────────────────────────────────────────────────────

class VCChoiceView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="Yes, create one",   style=discord.ButtonStyle.success,   row=0)
    async def yes_vc(self, interaction: discord.Interaction, button):
        await interaction.response.edit_message(
            content="Select a game:",
            view=GameSelectView(self.cog, create_vc=True),
            embeds=[]
        )

    @discord.ui.button(label="No, just post it",  style=discord.ButtonStyle.secondary, row=0)
    async def no_vc(self, interaction: discord.Interaction, button):
        await interaction.response.edit_message(
            content="Select a game:",
            view=GameSelectView(self.cog, create_vc=False),
            embeds=[]
        )


# ── Embed builders ─────────────────────────────────────────────────────────────

def _build_ranked_embed(
    user: discord.Member,
    rank: str,
    vc: discord.VoiceChannel | None,
    notes: str | None,
) -> discord.Embed:
    """Minimal, clean embed specifically for Ranked BR posts."""
    embed = discord.Embed(
        title="Looking for Group  ·  Ranked BR",
        color=RANK_COLORS.get(rank, 0xBDD5EA)
    )

    # User shown as author at the top
    embed.set_author(
        name=user.display_name,
        icon_url=user.display_avatar.url
    )

    # Rank field — clean, no extra symbols
    embed.add_field(name="Rank", value=rank, inline=True)

    # Voice channel if one was created
    if vc:
        embed.add_field(name="Voice Channel", value=vc.mention, inline=True)

    # Notes on its own row so it has breathing room
    if notes:
        embed.add_field(name="Notes", value=notes, inline=False)

    embed.set_footer(text=f"Posted by {user.display_name}  ·  React ✅ to join")
    return embed


def _build_embed(
    user: discord.Member,
    game: str,
    mode: str | None,
    rank: str | None,
    slots: int,
    vc: discord.VoiceChannel | None,
    description: str | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"Looking for Group  ·  {game}",
        color=0xBDD5EA
    )

    embed.set_author(
        name=user.display_name,
        icon_url=user.display_avatar.url
    )

    if mode:
        embed.add_field(name="Mode", value=mode, inline=True)
    if rank:
        embed.add_field(name="Rank", value=rank, inline=True)
    if slots > 0:
        embed.add_field(name="Slots Needed", value=str(slots), inline=True)
    if vc:
        embed.add_field(name="Voice Channel", value=vc.mention, inline=False)
    if description:
        embed.add_field(name="Notes", value=description, inline=False)

    embed.set_footer(text=f"Posted by {user.display_name}  ·  React ✅ to join")
    return embed


async def _send_lfg(
    interaction: discord.Interaction,
    embed: discord.Embed,
    rank: str | None = None,
) -> discord.Message:
    lfg_ping = discord.utils.get(interaction.guild.roles, name="LFG Ping")

    # Attach rank badge as thumbnail (top-right corner of the embed)
    files: list[discord.File] = []
    if rank and rank in RANK_IMAGES:
        img_path = RANK_IMAGES[rank]
        if os.path.isfile(img_path):
            img_filename = os.path.basename(img_path)
            files.append(discord.File(img_path, filename=img_filename))
            embed.set_thumbnail(url=f"attachment://{img_filename}")

    kwargs: dict = {
        "content": lfg_ping.mention if lfg_ping else None,
        "embed":   embed,
    }
    if files:
        kwargs["files"] = files

    msg = await interaction.channel.send(**kwargs)
    await msg.add_reaction("✅")
    return msg


# ── Cog ───────────────────────────────────────────────────────────────────────

class LFG(commands.Cog):
    def __init__(self, bot):
        self.bot        = bot
        self.lfg_posts: dict[int, int]            = {}
        self.origins:   dict[int, dict[int, int]] = {}
        self.lfg_vcs:   dict[int, int]            = {}

    def _track(self, msg: discord.Message, poster_id: int, vc: discord.VoiceChannel | None):
        self.lfg_posts[msg.id] = poster_id
        self.origins[msg.id]   = {}
        if vc:
            self.lfg_vcs[vc.id] = msg.id

    async def start_lfg_flow(self, interaction: discord.Interaction):
        embed = discord.Embed(
            description=(
                f"Setting up your LFG post\n"
                f"{SEP}\n"
                f"Create a custom voice channel for your group?"
            ),
            color=0xD5C8F0
        )
        await interaction.response.send_message(
            embed=embed,
            view=VCChoiceView(self),
            ephemeral=True
        )

    @app_commands.command(name="lfg", description="Post a Looking For Group listing")
    async def lfg(self, interaction: discord.Interaction):
        await self.start_lfg_flow(interaction)

    # ── Auto-delete VC when empty ──────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel and before.channel.id in self.lfg_vcs:
            if len(before.channel.members) == 0:
                vc_id = before.channel.id
                try:
                    await before.channel.delete(reason="LFG VC empty — auto-removed")
                except Exception:
                    pass
                self.lfg_vcs.pop(vc_id, None)

    # ── React to join host VC ─────────────────────────────────────────────────

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

        poster_id = self.lfg_posts[payload.message_id]
        if reactor.id == poster_id:
            return

        poster       = guild.get_member(poster_id)
        text_channel = guild.get_channel(payload.channel_id)

        if not poster or not poster.voice or not poster.voice.channel:
            if text_channel:
                await text_channel.send(
                    f"{reactor.mention} The host isn't in a voice channel right now.",
                    delete_after=8
                )
            return

        target_vc = poster.voice.channel

        if not reactor.voice or not reactor.voice.channel:
            try:
                await reactor.send(
                    f"Join any voice channel first, then react to be moved to **{target_vc.name}**!"
                )
            except discord.Forbidden:
                if text_channel:
                    await text_channel.send(
                        f"{reactor.mention} Join a VC first, then react to be moved to {target_vc.mention}!",
                        delete_after=10
                    )
            return

        if reactor.voice.channel.id == target_vc.id:
            return

        self.origins[payload.message_id][reactor.id] = reactor.voice.channel.id
        try:
            await reactor.move_to(target_vc)
        except Exception:
            self.origins[payload.message_id].pop(reactor.id, None)

    # ── Un-react to go back ───────────────────────────────────────────────────

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

        origin_id = self.origins.get(payload.message_id, {}).pop(reactor.id, None)
        if not origin_id:
            return
        origin = guild.get_channel(origin_id)
        if not origin or not reactor.voice or not reactor.voice.channel:
            return
        try:
            await reactor.move_to(origin)
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(LFG(bot))
