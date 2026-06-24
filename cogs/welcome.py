import discord
from discord.ext import commands

SEP = ("· " * 14).strip()

# Channel to send welcome messages in
WELCOME_CHANNEL = "welcome"

# Fallback: if no #welcome channel, post in first available channel
FALLBACK_CHANNELS = ["general", "lobby", "chat"]


class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild

        # Find welcome channel
        channel = discord.utils.get(guild.text_channels, name=WELCOME_CHANNEL)
        if not channel:
            for name in FALLBACK_CHANNELS:
                channel = discord.utils.get(guild.text_channels, name=name)
                if channel:
                    break
        if not channel:
            # Last resort: first channel the bot can send in
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    channel = ch
                    break
        if not channel:
            return

        # Initialize user in DB
        self.bot.db.get_user(member.id)

        member_count = guild.member_count

        embed = discord.Embed(
            title=f"◉  Welcome to {guild.name}",
            description=(
                f"*a new face walks through the door*\n"
                f"{SEP}\n"
                f"→  Hey {member.mention}, welcome to the café.\n"
                f"→  You're member **#{member_count}**.\n"
                f"{SEP}\n"
                f"→  Use `/daily` to claim XP every day.\n"
                f"→  Use `/help` to see what the bot can do.\n"
                f"→  Win duels to climb the leaderboard and earn roles."
            ),
            color=0xB0C0F5
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Glad you're here.")
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Optional: log when someone leaves."""
        guild = member.guild
        channel = discord.utils.get(guild.text_channels, name=WELCOME_CHANNEL)
        if not channel:
            return
        embed = discord.Embed(
            description=f"→  **{member.display_name}** has left the café.",
            color=0x9B9BB4  # muted color for departures
        )
        await channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Welcome(bot))
