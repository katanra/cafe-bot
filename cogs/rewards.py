import discord
from discord import app_commands
from discord.ext import commands
from discord.ext import tasks
import datetime

DAILY_XP = 50
SEP = ("· " * 14).strip()

# Streak milestones: {days: bonus_xp}
STREAK_BONUSES = {
    3:  25,
    7:  75,
    14: 150,
    30: 300,
}

def _streak_bonus(streak: int) -> int:
    """Return bonus XP for hitting a streak milestone, or 0."""
    return STREAK_BONUSES.get(streak, 0)

def _streak_bar(streak: int) -> str:
    """Visual progress bar toward next streak milestone."""
    milestones = sorted(STREAK_BONUSES.keys())
    next_ms = next((m for m in milestones if m > streak), None)
    if next_ms is None:
        return f"🔥 **{streak}-day streak** — *max milestone reached!*"
    prev_ms = max((m for m in milestones if m <= streak), default=0)
    progress = (streak - prev_ms) / (next_ms - prev_ms)
    filled   = min(10, int(progress * 10))
    bar      = "█" * filled + "░" * (10 - filled)
    return f"🔥 **{streak}-day streak**\n`{bar}`  {streak} / {next_ms} days"


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
        result, streak = self.bot.db.claim_daily(interaction.user.id)

        if result == 'already_claimed':
            now      = datetime.datetime.now(datetime.timezone.utc)
            midnight = (now + datetime.timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            remaining = int((midnight - now).total_seconds())
            h, m = remaining // 3600, (remaining % 3600) // 60
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=(
                        f"→  Already claimed today.\n"
                        f"→  Come back in **{h}h {m}m**.\n"
                        f"{SEP}\n"
                        f"{_streak_bar(streak)}"
                    ),
                    color=0xB0C0F5
                ),
                ephemeral=True
            )
            return

        # Check for Lucky Daily buff from shop
        try:
            from cogs.shop import has_buff, consume_buff
            lucky = has_buff(interaction.user.id, "lucky_daily")
        except Exception:
            lucky = False

        if lucky:
            consume_buff(interaction.user.id, "lucky_daily")

        # Award base XP + streak bonus (doubled if lucky)
        base      = DAILY_XP * (2 if lucky else 1)
        bonus     = _streak_bonus(streak) * (2 if lucky else 1)
        total_xp  = base + bonus
        self.bot.db.add_xp(interaction.user.id, total_xp)

        xp_line = f"→  **+{base} XP** awarded" + (" *(2x Lucky Daily!)*" if lucky else "")
        if bonus:
            xp_line += f"\n→  🎉 **+{bonus} XP** streak bonus!" + (" *(doubled!)*" if lucky else "")

        embed = discord.Embed(
            title="◉  Daily Reward",
            description=(
                f"*your café allowance for today*\n"
                f"{SEP}\n"
                f"{xp_line}\n"
                f"{SEP}\n"
                f"{_streak_bar(streak)}\n"
                f"{SEP}\n"
                f"→  Want gold? Win a duel."
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
