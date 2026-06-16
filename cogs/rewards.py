import discord
from discord import app_commands
from discord.ext import commands
from discord.ext import tasks
import datetime

DAILY_XP = 50
SEP = ("· " * 14).strip()

class Rewards(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_xp_bonus.start()

    def cog_unload(self):
        self.daily_xp_bonus.cancel()

    # ── Scheduled tasks ───────────────────────────────────────────────────────

    @tasks.loop(time=datetime.time(hour=12, minute=0, tzinfo=datetime.timezone.utc))
    async def daily_xp_bonus(self):
        """Every Monday at noon UTC: top 5 XP earners get bonus XP."""
        if datetime.datetime.now(datetime.timezone.utc).weekday() != 0:
            return
        weekly_xp_bonuses = [500, 300, 200, 100, 50]
        top5 = self.bot.db.get_leaderboard('xp', 5)
        for i, row in enumerate(top5):
            if row['xp'] > 0:
                self.bot.db.add_xp(row['user_id'], weekly_xp_bonuses[i])

    @daily_xp_bonus.before_loop
    async def before_daily(self):
        await self.bot.wait_until_ready()

    # ── /daily ────────────────────────────────────────────────────────────────

    @app_commands.command(name="daily", description="Claim your daily XP reward!")
    async def daily(self, interaction: discord.Interaction):
        result = self.bot.db.claim_daily(interaction.user.id)

        if result == 'already_claimed':
            now      = datetime.datetime.now(datetime.timezone.utc)
            midnight = (now + datetime.timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            remaining = int((midnight - now).total_seconds())
            h, m = remaining // 3600, (remaining % 3600) // 60
            await interaction.response.send_message(
                f"→ You already claimed today's reward. Come back in **{h}h {m}m**.",
                ephemeral=True
            )
            return

        self.bot.db.add_xp(interaction.user.id, DAILY_XP)

        embed = discord.Embed(
            title="◉  Daily Reward",
            description=(
                f"*your café allowance for today*\n"
                f"{SEP}\n"
                f"→  **+{DAILY_XP} XP** awarded\n\n"
                f"→  Want gold? Win a duel.\n"
                f"→  Come back tomorrow for more XP."
            ),
            color=0xB0C0F5
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

        roles_cog = self.bot.get_cog('Roles')
        if roles_cog and interaction.guild:
            await roles_cog.update_roles(interaction.user, interaction.guild)

async def setup(bot):
    await bot.add_cog(Rewards(bot))
