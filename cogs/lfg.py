import discord
from discord import app_commands
from discord.ext import commands

class LFG(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="lfg", description="Post a Looking For Group listing")
    @app_commands.describe(game="The game you're looking to play", description="What you're looking for", slots="How many extra players you need (optional)")
    async def lfg(self, interaction: discord.Interaction, game: str, description: str, slots: int = 0):
        embed = discord.Embed(
            title=f"🎮 LFG — {game}",
            description=description,
            color=discord.Color.blue()
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="📌 Posted by", value=interaction.user.mention, inline=True)
        if slots > 0:
            embed.add_field(name="👥 Slots needed", value=str(slots), inline=True)
        embed.set_footer(text="React ✅ to join!")
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        await msg.add_reaction("✅")

async def setup(bot):
    await bot.add_cog(LFG(bot))
