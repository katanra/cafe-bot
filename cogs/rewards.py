import discord
from discord import app_commands
from discord.ext import commands
from discord.ext import tasks
import datetime

DAILY_XP   = 50
DAILY_GOLD = 10

# Automatic daily bonus for top 3 gold holders (runs at noon UTC)
DAILY_AUTO_BONUSES  = [100, 50, 25]    # Gold bonus for #1, #2, #3
# Weekly Monday bonus for top 5 XP earners
WEEKLY_AUTO_BONUSES = [500, 300, 200, 100, 50]

class Rewards(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_auto_bonus.start()
        self.weekly_auto_bonus.start()

    def cog_unload(self):
        self.daily_auto_bonus.cancel()
        self.weekly_auto_bonus.cancel()

    # ── Scheduled tasks ───────────────────────────────────────────────────────

    @tasks.loop(time=datetime.time(hour=12, minute=0, tzinfo=datetime.timezone.utc))
    async def daily_auto_bonus(self):
        """Every day at noon UTC: reward the top 3 gold holders."""
        top3 = self.bot.db.get_leaderboard('gold', 3)
        for i, row in enumerate(top3):
            if row['gold'] > 0:
                self.bot.db.add_gold(row['user_id'], DAILY_AUTO_BONUSES[i])

    @tasks.loop(time=datetime.time(hour=12, minute=0, tzinfo=datetime.timezone.utc))
    async def weekly_auto_bonus(self):
        """Every Monday at noon UTC: reward the top 5 XP earners."""
        if datetime.datetime.now(datetime.timezone.utc).weekday() != 0:
            return
        top5 = self.bot.db.get_leaderboard('xp', 5)
        for i, row in enumerate(top5):
            if row['xp'] > 0:
                self.bot.db.add_gold(row['user_id'], WEEKLY_AUTO_BONUSES[i])

    @daily_auto_bonus.before_loop
    async def before_daily(self):
        await self.bot.wait_until_ready()

    @weekly_auto_bonus.before_loop
    async def before_weekly(self):
        await self.bot.wait_until_ready()

    # ── /daily ────────────────────────────────────────────────────────────────

    @app_commands.command(name="daily", description="Claim your daily XP and Gold reward!")
    async def daily(self, interaction: discord.Interaction):
        result = self.bot.db.claim_daily(interaction.user.id)

        if result == 'already_claimed':
            # Work out how long until midnight UTC (next reset)
            now       = datetime.datetime.now(datetime.timezone.utc)
            midnight  = (now + datetime.timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            remaining = int((midnight - now).total_seconds())
            h, m      = remaining // 3600, (remaining % 3600) // 60
            await interaction.response.send_message(
                f"⏰ You already claimed today's reward!\nCome back in **{h}h {m}m**.",
                ephemeral=True
            )
            return

        self.bot.db.add_xp(interaction.user.id,   DAILY_XP)
        self.bot.db.add_gold(interaction.user.id, DAILY_GOLD)

        embed = discord.Embed(
            title="🎁 Daily Reward Claimed!",
            description=(
                f"+**{DAILY_XP}** ⭐ XP\n"
                f"+**{DAILY_GOLD}** 🪙 Gold\n\n"
                f"Come back tomorrow for more!"
            ),
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

        # Update roles after reward
        roles_cog = self.bot.get_cog('Roles')
        if roles_cog and interaction.guild:
            await roles_cog.update_roles(interaction.user, interaction.guild)

async def setup(bot):
    await bot.add_cog(Rewards(bot))
