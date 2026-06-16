import discord
from discord import app_commands
from discord.ext import commands

SEP = ("· " * 14).strip()

class LFG(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="lfg", description="Post a Looking For Group listing")
    @app_commands.describe(
        game="The game you're looking to play",
        description="What you're looking for",
        slots="How many extra players you need (optional)"
    )
    async def lfg(self, interaction: discord.Interaction, game: str, description: str, slots: int = 0):
        slot_line = f"\n→  **Slots needed:** {slots}" if slots > 0 else ""
        embed = discord.Embed(
            title=f"◉  Looking For Group",
            description=(
                f"*{game}*\n"
                f"{SEP}\n"
                f"{description}"
                f"{slot_line}\n"
                f"{SEP}\n"
                f"→  Posted by {interaction.user.mention}"
            ),
            color=0xB0C0F5
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="React below to join.")
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        await msg.add_reaction("✅")

async def setup(bot):
    await bot.add_cog(LFG(bot))
