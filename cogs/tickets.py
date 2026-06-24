import discord
from discord import app_commands
from discord.ext import commands
import asyncio

SEP             = ("· " * 14).strip()
TICKET_CATEGORY = "Tickets"
STAFF_ROLE      = "Staff"   # change this if your staff role has a different name

TICKET_TYPES = {
    "complaint": {
        "label":  "Complaint",
        "emoji":  "📋",
        "color":  0xE57373,
        "prompt": (
            "Please describe your complaint below.\n"
            "→  What happened?\n"
            "→  Who was involved?\n"
            "→  Any screenshots or evidence?"
        ),
    },
    "question": {
        "label":  "General Question",
        "emoji":  "❓",
        "color":  0xB0C0F5,
        "prompt": "Go ahead and ask your question — staff will reply as soon as possible.",
    },
    "staff_app": {
        "label":  "Staff Application",
        "emoji":  "📝",
        "color":  0x81C784,
        "prompt": (
            "Please answer the following in your next message:\n"
            "→  **Age:**\n"
            "→  **Timezone:**\n"
            "→  **Why do you want to be staff?**\n"
            "→  **Any previous moderation experience?**\n"
            "→  **How active are you per week?**"
        ),
    },
}


# ── Close confirm ──────────────────────────────────────────────────────────────

class CloseConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)

    @discord.ui.button(label="Yes, close it", style=discord.ButtonStyle.danger)
    async def yes_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="→ Closing in 5 seconds…", view=self)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
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


# ── Close button (persistent — survives restarts) ──────────────────────────────

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔒 Close Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="tickets:close"
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        is_staff   = (
            (staff_role and staff_role in interaction.user.roles)
            or interaction.user.guild_permissions.manage_channels
        )
        # Ticket channels are named ticket-{user_id}
        is_owner = interaction.channel.name == f"ticket-{interaction.user.id}"

        if not (is_staff or is_owner):
            await interaction.response.send_message(
                "→ Only the ticket owner or staff can close this.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "→ Are you sure you want to close this ticket?",
            view=CloseConfirmView()
        )


# ── Ticket type dropdown (persistent) ─────────────────────────────────────────

class TicketTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=info["label"],
                emoji=info["emoji"],
                value=key,
                description={
                    "complaint":  "Report a player or issue",
                    "question":   "Ask the staff anything",
                    "staff_app":  "Apply to join the staff team",
                }[key]
            )
            for key, info in TICKET_TYPES.items()
        ]
        super().__init__(
            placeholder="Open a support ticket…",
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
        existing = discord.utils.get(guild.text_channels, name=f"ticket-{user.id}")
        if existing:
            await interaction.response.send_message(
                f"→ You already have an open ticket: {existing.mention}",
                ephemeral=True
            )
            return

        # Find or create the Tickets category
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
                    "→ I don't have permission to create channels. "
                    "Ask an admin to give me **Manage Channels** permission.",
                    ephemeral=True
                )
                return

        # Per-channel permissions: hidden from everyone, visible to ticket owner + staff
        staff_role = discord.utils.get(guild.roles, name=STAFF_ROLE)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me:           discord.PermissionOverwrite(
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
                name=f"ticket-{user.id}",
                category=category,
                overwrites=overwrites,
                topic=f"{info['label']} · {user.display_name} ({user.id})",
                reason=f"Ticket opened by {user}"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "→ Couldn't create ticket channel — check my **Manage Channels** permission.",
                ephemeral=True
            )
            return

        # Ticket opening embed
        staff_ping = staff_role.mention if staff_role else "staff"
        embed = discord.Embed(
            title=f"◉  {info['emoji']}  {info['label']}",
            description=(
                f"*ticket opened*\n"
                f"{SEP}\n"
                f"→  Hey {user.mention}, thanks for reaching out!\n"
                f"{SEP}\n"
                f"**→  What to do next:**\n"
                f"{info['prompt']}\n"
                f"{SEP}\n"
                f"→  {staff_ping} will be with you shortly.\n"
                f"→  Click **Close Ticket** below when your issue is resolved."
            ),
            color=info["color"]
        )
        embed.set_footer(text=f"Opened by {user.display_name}  ·  {user.id}")
        await channel.send(
            content=user.mention,
            embed=embed,
            view=CloseTicketView()
        )

        await interaction.response.send_message(
            f"→ Your ticket is open: {channel.mention}", ephemeral=True
        )


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketTypeSelect())


# ── Cog ───────────────────────────────────────────────────────────────────────

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Register persistent views so buttons work after bot restarts
        bot.add_view(TicketPanelView())
        bot.add_view(CloseTicketView())

    @app_commands.command(
        name="setuptickets",
        description="Post the support ticket panel in this channel (Admin only)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setuptickets(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="◉  Support",
            description=(
                f"*Need help? We're here.*\n"
                f"{SEP}\n"
                f"→  **📋 Complaint** — Report a player or issue\n"
                f"→  **❓ General Question** — Ask the staff anything\n"
                f"→  **📝 Staff Application** — Apply to join the team\n"
                f"{SEP}\n"
                f"*Select an option from the dropdown below to open a ticket.\n"
                f"Only you and staff can see your ticket.*"
            ),
            color=0xB0C0F5
        )
        embed.set_footer(text="One ticket at a time  ·  Close when your issue is resolved")
        await interaction.response.send_message(embed=embed, view=TicketPanelView())

    @setuptickets.error
    async def setuptickets_error(self, interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "→ Administrator permission required.", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Tickets(bot))
