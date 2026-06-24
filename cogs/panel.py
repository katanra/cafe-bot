import discord
from discord import app_commands
from discord.ext import commands

SEP       = ("· " * 14).strip()
DAILY_XP  = 100
DAILY_GOLD = 50

STREAK_BONUSES = {3: 25, 7: 75, 14: 150, 30: 300}

def _streak_bonus(streak: int) -> int:
    bonus = 0
    for days, xp in STREAK_BONUSES.items():
        if streak >= days:
            bonus = xp
    return bonus

def _rank_label(rank: int) -> str:
    titles = {1: "◉  Champion", 2: "◉  Contender"}
    if rank == 0:
        return "Unranked"
    return titles.get(rank, f"#{rank}")


# ── Duel Modal ────────────────────────────────────────────────────────────────

class DuelModal(discord.ui.Modal, title="Challenge Someone to a Duel"):
    target = discord.ui.TextInput(
        label="Who do you want to challenge?",
        placeholder="Type their exact username or @mention",
        max_length=50
    )

    async def on_submit(self, interaction: discord.Interaction):
        name = self.target.value.strip().lstrip("@")
        member = (
            discord.utils.find(lambda m: m.name.lower() == name.lower(), interaction.guild.members)
            or discord.utils.find(lambda m: m.display_name.lower() == name.lower(), interaction.guild.members)
        )
        if not member:
            await interaction.response.send_message(
                f"→ Couldn't find **{name}** in this server. Try their exact username.",
                ephemeral=True
            )
            return
        if member.id == interaction.user.id:
            await interaction.response.send_message("→ You can't duel yourself!", ephemeral=True)
            return
        if member.bot:
            await interaction.response.send_message("→ You can't duel a bot!", ephemeral=True)
            return
        # Hand off to the Duels cog command
        duels_cog = interaction.client.get_cog('Duels')
        if duels_cog:
            await duels_cog.duel.callback(duels_cog, interaction, member)
        else:
            await interaction.response.send_message("Duel system unavailable.", ephemeral=True)


# ── Main Panel View ───────────────────────────────────────────────────────────

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # Row 0 ── economy & profile

    @discord.ui.button(label="Daily Reward", style=discord.ButtonStyle.primary,
                       custom_id="panel:daily", row=0)
    async def daily(self, interaction: discord.Interaction, button: discord.ui.Button):
        result, streak = interaction.client.db.claim_daily(interaction.user.id)
        if result == 'already_claimed':
            await interaction.response.send_message(
                "→ Already claimed today — come back tomorrow!", ephemeral=True
            )
            return
        bonus     = _streak_bonus(streak)
        total_xp  = DAILY_XP + bonus
        interaction.client.db.add_xp(interaction.user.id, total_xp)
        interaction.client.db.add_gold(interaction.user.id, DAILY_GOLD)

        streak_line = f"\n→  ~ **{streak}-day streak!**"
        if bonus:
            streak_line += f"  +**{bonus}** bonus XP"
        embed = discord.Embed(
            title="◉  Daily Reward",
            description=(
                f"*claimed!*\n{SEP}\n"
                f"→  +**{total_xp}** XP\n"
                f"→  +**{DAILY_GOLD}** Gold"
                f"{streak_line}"
            ),
            color=0xB0C0F5
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Profile", style=discord.ButtonStyle.secondary,
                       custom_id="panel:profile", row=0)
    async def profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        db     = interaction.client.db
        user   = db.get_user(interaction.user.id)
        streak = db.get_streak(interaction.user.id)
        rank   = db.get_duel_rank(interaction.user.id)

        streak_val = f"~ **{streak}** days" if streak > 0 else "*No active streak*"
        embed = discord.Embed(
            title=f"◉  {interaction.user.display_name}",
            description=f"*your stats*\n{SEP}",
            color=0xB0C0F5
        )
        embed.add_field(name="→  XP",        value=f"**{user['xp']:,}**",   inline=True)
        embed.add_field(name="→  Gold",       value=f"**{user['gold']:,}**", inline=True)
        embed.add_field(name="→  Streak",     value=streak_val,              inline=True)
        embed.add_field(name="→  Duel Rank",  value=_rank_label(rank),       inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Leaderboard", style=discord.ButtonStyle.secondary,
                       custom_id="panel:lb", row=0)
    async def leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        data  = interaction.client.db.get_leaderboard('gold', 5)
        lines = []
        for i, row in enumerate(data):
            m    = interaction.guild.get_member(row['user_id'])
            name = m.display_name if m else f"User {row['user_id']}"
            pre  = ["→  #1", "→  #2", "→  #3"][i] if i < 3 else f"      #{i+1}"
            lines.append(f"{pre}  **{name}** — {row['gold']:,} gold")
        embed = discord.Embed(
            title="◉  Gold Leaderboard",
            description=f"{SEP}\n" + ("\n".join(lines) if lines else "No data yet."),
            color=0xB0C0F5
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # Row 1 ── social & competitive

    @discord.ui.button(label="Post LFG", style=discord.ButtonStyle.success,
                       custom_id="panel:lfg", row=1)
    async def post_lfg(self, interaction: discord.Interaction, button: discord.ui.Button):
        lfg_cog = interaction.client.get_cog('LFG')
        if lfg_cog:
            await lfg_cog.start_lfg_flow(interaction)
        else:
            await interaction.response.send_message("LFG system unavailable.", ephemeral=True)

    @discord.ui.button(label="Challenge to Duel", style=discord.ButtonStyle.danger,
                       custom_id="panel:duel", row=1)
    async def start_duel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DuelModal())

    @discord.ui.button(label="Shop", style=discord.ButtonStyle.secondary,
                       custom_id="panel:shop", row=1)
    async def show_shop(self, interaction: discord.Interaction, button: discord.ui.Button):
        shop_cog = interaction.client.get_cog('Shop')
        if shop_cog:
            await shop_cog.shop.callback(shop_cog, interaction)
        else:
            await interaction.response.send_message("Shop unavailable.", ephemeral=True)


# ── Cog ───────────────────────────────────────────────────────────────────────

class Panel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Re-register persistent view so buttons work after restarts
        bot.add_view(PanelView())

    @app_commands.command(name="panel", description="Post the bot panel in this channel (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="◉  Café Bot",
            description=(
                f"*everything you need, one click away*\n"
                f"{SEP}\n"
                f"→  **Daily Reward** — Claim XP and gold every day\n"
                f"→  **Profile** — View your stats\n"
                f"→  **Leaderboard** — See who's on top\n"
                f"→  **Post LFG** — Find teammates and auto-create a VC\n"
                f"→  **Challenge to Duel** — Start a 1v1\n"
                f"→  **Shop** — Spend your gold"
            ),
            color=0xB0C0F5
        )
        embed.set_footer(text="All responses are private — only you can see them")
        await interaction.response.send_message(embed=embed, view=PanelView())

    @panel.error
    async def panel_error(self, interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("→ Administrator permission required.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Panel(bot))
