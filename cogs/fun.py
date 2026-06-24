import discord
from discord import app_commands
from discord.ext import commands
import random

SEP = ("· " * 14).strip()

EIGHT_BALL_RESPONSES = [
    # Positive
    "→  It is certain.",
    "→  Without a doubt.",
    "→  Yes, definitely.",
    "→  You may rely on it.",
    "→  Most likely.",
    "→  Outlook good.",
    "→  Signs point to yes.",
    "→  As I see it, yes.",
    # Neutral
    "→  Reply hazy, try again.",
    "→  Ask again later.",
    "→  Better not tell you now.",
    "→  Cannot predict now.",
    "→  Concentrate and ask again.",
    # Negative
    "→  Don't count on it.",
    "→  My reply is no.",
    "→  My sources say no.",
    "→  Outlook not so good.",
    "→  Very doubtful.",
]


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="8ball", description="Ask the magic 8-ball a question")
    @app_commands.describe(question="What do you want to ask?")
    async def eight_ball(self, interaction: discord.Interaction, question: str):
        answer = random.choice(EIGHT_BALL_RESPONSES)
        embed = discord.Embed(
            title="◉  Magic 8-Ball",
            description=(
                f"*{question}*\n"
                f"{SEP}\n"
                f"{answer}"
            ),
            color=0xB0C0F5
        )
        embed.set_footer(text="The ball has spoken.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="coinflip", description="Flip a coin")
    async def coinflip(self, interaction: discord.Interaction):
        result = random.choice(["Heads", "Tails"])
        embed = discord.Embed(
            title="◉  Coin Flip",
            description=(
                f"{SEP}\n"
                f"→  **{result}!**"
            ),
            color=0xB0C0F5
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="roll", description="Roll a dice — e.g. d6, d20, d100")
    @app_commands.describe(sides="Number of sides on the dice (default: 6)")
    async def roll(self, interaction: discord.Interaction, sides: int = 6):
        if sides < 2:
            await interaction.response.send_message(
                "→ A dice needs at least 2 sides!", ephemeral=True
            )
            return
        if sides > 1000:
            await interaction.response.send_message(
                "→ Max 1000 sides.", ephemeral=True
            )
            return
        result = random.randint(1, sides)
        embed = discord.Embed(
            title=f"◉  d{sides} Roll",
            description=(
                f"{SEP}\n"
                f"→  You rolled a **{result}**  *(out of {sides})*"
            ),
            color=0xB0C0F5
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Fun(bot))
