import discord
from discord import app_commands
from discord.ext import commands
import asyncio

SEP             = ("· " * 14).strip()
TICKET_CATEGORY = "Tickets"
STAFF_ROLE      = "Staff"   # change to match your staff role name

TICKET_TYPES = {
    "complaint": {
        "label":  "Complaint",
        "desc":   "Report a player, bug, or issue to staff",
        "prompt": (
            "Describe your complaint below.\n"
            "→  What happened?\n"
            "→  Who was involved?\n"
            "→  Any evidence or screenshots?"
        ),
    },
    "question": {
        "label":  "General Question",
        "desc":   "Ask about rules, features, or anything else",
        "prompt": "Ask your question below and staff will reply as soon as possible.",
    },
    "staff_app": {
        "label":  "Staff Application",
        "desc":   "Apply to join the moderation team",
        "prompt": (
            "Answer the following in your next message:\n"
            "→  Age:\n"
            "→  Timezone:\n"
            "→  Why do you want to be staff?\n"
            "→  Any moderation experience?\n"
            "→  How active are you per week?"
        ),
    },
}


class CloseConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)

    @discord.ui.button(label="Close it", style=discord.ButtonStyle.danger)
    async def yes_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="→ Closing in 5 seconds.", view=self)
        await asyncio.sleep(5)
        category = interaction.channel.category
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except Exception:
            return
        # If category is now empty, delete it
        if category and len(category.channels) == 0:
            try:
                await category.delete(reason="All tickets resolved — category auto-removed")
            except Exception:
                pass

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="→ Cancelled.", view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="tickets:close"
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        is_staff   = (
            (staff_role and staff_role in interaction.user.roles)
            or interaction.user.guild_permissions.manage_channels
        )
        is_owner   = interaction.channel.name == f"ticket-{interaction.user.name}"

        if not (is_staff or is_owner):
            await interaction.response.send_message(
                "→ Only the ticket owner or staff can close this.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "→ Close this ticket?", view=CloseConfirmView()
        )


class TicketTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=info["label"],
                value=key,
                description=info["desc"]
            )
            for key, info in TICKET_TYPES.items()
        ]
        super().__init__(
            placeholder="Choose a ticket type to get started...",
            options=options,
            min_values=1,
            max_values=1,
            custom_id="tickets:type_select"
        )

    async def callback(self, interaction: discord.Interaction):
        ticket_type = self.values[0]
        info        = TICKET_TYPES[ticket_type]
        guild       = interaction.guild
        user        = interaction.user

        # One ticket at a time
        existing = discord.utils.get(guild.text_channels, name=f"ticket-{user.name}")
        if existing:
            await interaction.response.send_message(
                f"→ You already have an open ticket: {existing.mention}",
                ephemeral=True
            )
            return

        # Find or create Tickets category
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY)
        if not category:
            try:
                staff_role = discord.utils.get(guild.roles, name=STAFF_ROLE)
                cat_overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True, manage_channels=True, manage_permissions=True
                    ),
                }
                if staff_role:
                    cat_overwrites[staff_role] = discord.PermissionOverwrite(
                        view_channel=True, send_messages=True, read_message_history=True
                    )
                category = await guild.create_category(
                    TICKET_CATEGORY,
                    overwrites=cat_overwrites,
                    reason="Ticket system auto-setup"
                )
            except discord.Forbidden:
                await interaction.response.send_message(
                    "→ I need the Manage Channels permission to create tickets. Ask an admin.",
                    ephemeral=True
                )
                return

        # Channel permissions — hidden from everyone except the user and staff
        staff_role = discord.utils.get(guild.roles, name=STAFF_ROLE)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                manage_channels=True, manage_messages=True
            ),
            user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                read_message_history=True, manage_messages=True
            )

        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{user.name}",
                category=category,
                overwrites=overwrites,
                topic=f"{info['label']} — {user.display_name}",
                reason=f"Ticket by {user}"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "→ Couldn't create the channel — check my Manage Channels permission.",
                ephemeral=True
            )
            return

        # Opening message in the ticket channel
        staff_ping = staff_role.mention if staff_role else "staff"
        embed = discord.Embed(
            title=f"◉  {info['label']}",
            description=(
                f"{SEP}\n"
                f"→  Hey {user.mention}, your ticket is open.\n"
                f"{SEP}\n"
                f"{info['prompt']}\n"
                f"{SEP}\n"
                f"→  {staff_ping} will respond shortly.\n"
                f"→  Press Close Ticket when you're done."
            ),
            color=0xB0C0F5
        )
        await channel.send(content=user.mention, embed=embed, view=CloseTicketView())

        await interaction.response.send_message(
            f"→ Ticket opened: {channel.mention}", ephemeral=True
        )


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketTypeSelect())


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.add_view(TicketPanelView())
        bot.add_view(CloseTicketView())

    @app_commands.command(
        name="setuptickets",
        description="Post the ticket panel in this channel (Admin only)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setuptickets(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="◉  Support",
            description=(
                f"{SEP}\n"
                f"→  Select an option from the dropdown below.\n"
                f"→  Your ticket is private — only you and staff can see it.\n"
                f"→  One ticket at a time.\n"
                f"{SEP}"
            ),
            color=0xB0C0F5
        )
        await interaction.response.send_message(embed=embed, view=TicketPanelView())

    @setuptickets.error
    async def setuptickets_error(self, interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "→ Administrator permission required.", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Tickets(bot))
