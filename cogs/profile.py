import discord
from discord import app_commands
from discord.ext import commands
import time

SEP = ("· " * 14).strip()

MILESTONES_H = [10, 50, 100, 250, 500]
TIER_NAMES = {
    0:   "Newcomer",
    10:  "Regular",
    50:  "Veteran",
    100: "Devoted",
    250: "Elder",
    500: "The Café",
}


class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _fmt_time(self, seconds: int) -> str:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        if h:
            return f"{h}h {m}m"
        if m:
            return f"{m}m"
        return f"{seconds}s"

    def _vc_tier_block(self, total_seconds: int) -> str:
        """Returns tier name + progress bar toward next milestone."""
        hours = total_seconds / 3600
        current_tier = 0
        next_ms = None
        for ms in MILESTONES_H:
            if hours >= ms:
                current_tier = ms
            else:
                next_ms = ms
                break
        tier_name = TIER_NAMES.get(current_tier, "Newcomer")
        if next_ms is None:
            return f"**{tier_name}**  ◉  *max*\n`{'█' * 15}`  {hours:.0f}h"
        progress = (hours - current_tier) / (next_ms - current_tier)
        filled   = min(15, int(progress * 15))
        bar      = "█" * filled + "░" * (15 - filled)
        next_name = TIER_NAMES.get(next_ms, f"{next_ms}h")
        return (
            f"**{tier_name}**\n→  Next  —  **{next_name}** ({next_ms}h)\n"
            f"`{bar}`  {hours:.1f} / {next_ms}h"
        )

    @app_commands.command(name="profile", description="View your café profile")
    @app_commands.describe(member="Member to view (defaults to you)")
    async def profile(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        user   = self.bot.db.get_user(target.id)

        # Live VC session time
        voice_cog = self.bot.get_cog('Voice')
        total_vc  = user.get('voice_time', 0)
        if voice_cog and target.id in voice_cog.voice_sessions:
            total_vc += int(time.time() - voice_cog.voice_sessions[target.id])

        xp         = user.get('xp', 0)
        gold       = user.get('gold', 0)
        duel_wins  = self.bot.db.get_user_wins(target.id)
        duel_rank  = self.bot.db.get_duel_rank(target.id)
        xp_rank    = self.bot.db.get_xp_rank(target.id)
        gold_rank  = self.bot.db.get_gold_rank(target.id)
        vc_block   = self._vc_tier_block(total_vc)

        embed = discord.Embed(
            title=f"◉  {target.display_name}",
            description=f"*Café profile*\n{SEP}",
            color=0xB0C0F5
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        embed.add_field(
            name="→  XP",
            value=f"**{xp:,}** points  —  Rank **#{xp_rank}**",
            inline=True
        )
        gold_value = f"**{gold:,}** coins"
        if gold_rank > 0:
            gold_value += f"  —  Rank **#{gold_rank}**"

        embed.add_field(
            name="→  Gold",
            value=gold_value,
            inline=True
        )
        if duel_rank == 1:
            rank_label = "◉  Champion"
        elif duel_rank == 2:
            rank_label = "Contender"
        elif duel_rank == 3:
            rank_label = "Challenger"
        elif duel_rank > 3:
            rank_label = f"#{duel_rank}"
        else:
            rank_label = None

        duel_value = f"**{duel_wins}** wins"
        if rank_label:
            duel_value += f"  —  **{rank_label}**"

        embed.add_field(name="→  Duel Wins", value=duel_value, inline=True)
        embed.add_field(name="→  VC Time",   value=vc_block,   inline=False)
        embed.set_footer(text="Gold is earned through duels  ·  XP through activity")
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Profile(bot))
