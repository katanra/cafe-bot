import discord
from discord import app_commands
from discord.ext import commands

SEP   = ("· " * 14).strip()
RANKS = ["→  #1", "→  #2", "→  #3"]

class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Show the server leaderboard")
    @app_commands.describe(category="What to rank by")
    @app_commands.choices(category=[
        app_commands.Choice(name="Gold",       value="gold"),
        app_commands.Choice(name="XP",         value="xp"),
        app_commands.Choice(name="Voice Time", value="voice"),
    ])
    async def leaderboard(self, interaction: discord.Interaction, category: str = "gold"):
        await interaction.response.defer()

        if category == "voice":
            data  = self.bot.db.get_voice_leaderboard(10)
            title = "◉  Voice Time"
            color = 0xB0C0F5
            sub   = "*time spent in the café*"
            def fmt(i, row):
                secs = row['voice_time']
                h, m = secs // 3600, (secs % 3600) // 60
                name = self._get_name(interaction.guild, row['user_id'])
                rank = RANKS[i] if i < 3 else f"      #{i+1}"
                return f"{rank}  **{name}** — {h}h {m}m"
        elif category == "xp":
            data  = self.bot.db.get_leaderboard('xp', 10)
            title = "◉  XP Rankings"
            color = 0xB0C0F5
            sub   = "*earned through activity & daily rewards*"
            def fmt(i, row):
                name = self._get_name(interaction.guild, row['user_id'])
                rank = RANKS[i] if i < 3 else f"      #{i+1}"
                return f"{rank}  **{name}** — {row['xp']:,} xp"
        else:
            data  = self.bot.db.get_leaderboard('gold', 10)
            title = "◉  Gold Rankings"
            color = 0xB0C0F5
            sub   = "*earned through winning duels*"
            def fmt(i, row):
                name = self._get_name(interaction.guild, row['user_id'])
                rank = RANKS[i] if i < 3 else f"      #{i+1}"
                return f"{rank}  **{name}** — {row['gold']:,} coins"

        if not data:
            await interaction.followup.send("No data yet — get dueling and chatting.")
            return

        lines = [fmt(i, row) for i, row in enumerate(data)]
        embed = discord.Embed(
            title=title,
            description=f"{sub}\n{SEP}\n" + "\n".join(lines),
            color=color
        )
        embed.set_footer(text="Use /balance to check your own stats.")
        await interaction.followup.send(embed=embed)

    def _get_name(self, guild, user_id):
        m = guild.get_member(user_id)
        return m.display_name if m else f"User {user_id}"

async def setup(bot):
    await bot.add_cog(Leaderboard(bot))
