import discord
from discord import app_commands
from discord.ext import commands

SEP = ("· " * 14).strip()


async def toggle_role(interaction: discord.Interaction, role_name: str):
    """Add the role if the user doesn't have it; remove it if they do."""
    guild  = interaction.guild
    member = interaction.user

    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        try:
            role = await guild.create_role(
                name=role_name,
                mentionable=True,
                reason="Self-role auto-created by bot"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                f"→ I need the **Manage Roles** permission to create **{role_name}**.",
                ephemeral=True
            )
            return

    if role in member.roles:
        await member.remove_roles(role, reason="Self-role toggle")
        await interaction.response.send_message(
            f"→ Removed **{role_name}**.", ephemeral=True
        )
    else:
        await member.add_roles(role, reason="Self-role toggle")
        await interaction.response.send_message(
            f"→ Added **{role_name}**.", ephemeral=True
        )


class SelfRolesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # ── Row 0 — Game roles ─────────────────────────────────────────────────────

    @discord.ui.button(
        label="Apex Legends",
        style=discord.ButtonStyle.secondary,
        custom_id="roles:apex",
        row=0
    )
    async def apex(self, interaction: discord.Interaction, button: discord.ui.Button):
        await toggle_role(interaction, "Apex Legends")

    # ── Row 1 — Café roles ─────────────────────────────────────────────────────

    @discord.ui.button(
        label="Night Owl",
        style=discord.ButtonStyle.secondary,
        custom_id="roles:nightowl",
        row=1
    )
    async def night_owl(self, interaction: discord.Interaction, button: discord.ui.Button):
        await toggle_role(interaction, "Night Owl")

    @discord.ui.button(
        label="Weekend Warrior",
        style=discord.ButtonStyle.secondary,
        custom_id="roles:weekend",
        row=1
    )
    async def weekend_warrior(self, interaction: discord.Interaction, button: discord.ui.Button):
        await toggle_role(interaction, "Weekend Warrior")

    @discord.ui.button(
        label="LFG Ping",
        style=discord.ButtonStyle.secondary,
        custom_id="roles:lfgping",
        row=1
    )
    async def lfg_ping(self, interaction: discord.Interaction, button: discord.ui.Button):
        await toggle_role(interaction, "LFG Ping")

    @discord.ui.button(
        label="Event Alerts",
        style=discord.ButtonStyle.secondary,
        custom_id="roles:events",
        row=1
    )
    async def event_alerts(self, interaction: discord.Interaction, button: discord.ui.Button):
        await toggle_role(interaction, "Event Alerts")


class SelfRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.add_view(SelfRolesView())

    @app_commands.command(
        name="setuproles",
        description="Post the self-roles panel in this channel (Admin only)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setuproles(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="◉  Get Your Roles",
            description=(
                f"*click a button to add or remove a role*\n"
                f"{SEP}\n"
                f"→  **Apex Legends** — get pinged for Apex LFGs\n"
                f"{SEP}\n"
                f"→  **Night Owl** — you play late at night\n"
                f"→  **Weekend Warrior** — you mostly play on weekends\n"
                f"→  **LFG Ping** — get notified when someone posts an LFG\n"
                f"→  **Event Alerts** — get pinged for server events and giveaways\n"
                f"{SEP}\n"
                f"→  Click again to remove a role."
            ),
            color=0xB0C0F5
        )
        await interaction.response.send_message(embed=embed, view=SelfRolesView())

    @setuproles.error
    async def setuproles_error(self, interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "→ Administrator permission required.", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(SelfRoles(bot))
