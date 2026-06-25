import discord
from discord import app_commands
from discord.ext import commands

# ── Type config ────────────────────────────────────────────────────────────────
# Each announcement type gets its own label, pastel color, and icon

TYPE_CONFIG: dict[str, dict] = {
    "general":   {"label": "Announcement",     "color": 0xBDD5EA, "icon": "📢"},
    "event":     {"label": "Event",            "color": 0xCDB4DB, "icon": "🎉"},
    "update":    {"label": "Update",           "color": 0xB5EAD7, "icon": "🔧"},
    "rules":     {"label": "Rules",            "color": 0xFFD6A5, "icon": "📋"},
    "emergency": {"label": "Emergency Notice", "color": 0xFFB7B2, "icon": "🚨"},
}


# ── Modal ──────────────────────────────────────────────────────────────────────

class AnnounceModal(discord.ui.Modal, title="Post Announcement"):
    headline = discord.ui.TextInput(
        label="Title",
        placeholder="e.g.  Server Update — New Channels Added",
        min_length=1,
        max_length=100
    )
    body = discord.ui.TextInput(
        label="Message",
        style=discord.TextStyle.paragraph,
        placeholder="Type your full announcement here. Discord markdown is supported.",
        min_length=1,
        max_length=2000
    )
    image_url = discord.ui.TextInput(
        label="Banner Image URL  (optional)",
        placeholder="https://i.imgur.com/example.png",
        required=False,
        max_length=500
    )

    def __init__(self, ann_type: str, ping: str):
        super().__init__()
        self.ann_type = ann_type
        self.ping     = ping

    async def on_submit(self, interaction: discord.Interaction):
        cfg = TYPE_CONFIG[self.ann_type]

        embed = discord.Embed(
            title=self.headline.value.strip(),
            description=self.body.value.strip(),
            color=cfg["color"],
            timestamp=discord.utils.utcnow()
        )

        # Author row: type icon + label + server icon
        embed.set_author(
            name=f"{cfg['icon']}  {cfg['label']}",
            icon_url=interaction.guild.icon.url if interaction.guild and interaction.guild.icon else None
        )

        # Footer: who posted it
        embed.set_footer(
            text=f"Posted by {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url
        )

        # Optional banner image at the bottom
        img = self.image_url.value.strip() if self.image_url.value else ""
        if img.startswith("http"):
            embed.set_image(url=img)

        # Ping content
        content: str | None = None
        if self.ping == "everyone":
            content = "@everyone"
        elif self.ping == "here":
            content = "@here"

        await interaction.channel.send(content=content, embed=embed)
        await interaction.response.send_message(
            f"→  {cfg['icon']} Announcement posted!",
            ephemeral=True
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print(f"[Announce] Modal error: {error}")
        try:
            await interaction.response.send_message(
                "→  Something went wrong posting that. Try again.",
                ephemeral=True
            )
        except Exception:
            pass


# ── Cog ───────────────────────────────────────────────────────────────────────

class Announce(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="announce",
        description="Post a formatted announcement embed  (Staff only)"
    )
    @app_commands.describe(
        type="The kind of announcement to post",
        ping="Optional ping to send with the announcement"
    )
    @app_commands.choices(
        type=[
            app_commands.Choice(name="📢  General",          value="general"),
            app_commands.Choice(name="🎉  Event",            value="event"),
            app_commands.Choice(name="🔧  Update",           value="update"),
            app_commands.Choice(name="📋  Rules",            value="rules"),
            app_commands.Choice(name="🚨  Emergency Notice", value="emergency"),
        ],
        ping=[
            app_commands.Choice(name="No ping",   value="none"),
            app_commands.Choice(name="@everyone", value="everyone"),
            app_commands.Choice(name="@here",     value="here"),
        ]
    )
    @app_commands.default_permissions(manage_messages=True)
    async def announce(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[str],
        ping: app_commands.Choice[str] = None,
    ):
        ping_val = ping.value if ping else "none"
        await interaction.response.send_modal(
            AnnounceModal(ann_type=type.value, ping=ping_val)
        )


async def setup(bot):
    await bot.add_cog(Announce(bot))
