import discord
from discord import app_commands
from discord.ext import commands

SEP = ("· " * 14).strip()


COMMANDS = {
    "💰  Economy": [
        ("/balance",     "Check your Gold and XP"),
        ("/daily",       "Claim your daily XP reward (resets midnight UTC)"),
        ("/leaderboard", "Server rankings — XP, Gold, or Voice Time"),
        ("/shop",        "Browse the gold shop"),
        ("/buy",         "Spend gold on shop items"),
    ],
    "⚔️  Duels": [
        ("/duel",        "Challenge someone to a 1v1 for gold"),
        ("/duelboard",   "Top duelists leaderboard"),
        ("/duelrules",   "Full ruleset for café duels"),
        ("/duelvoid",    "Void a duel by ID  *(Duel Mod only)*"),
    ],
    "🎖️  Roles": [
        ("/roles",       "Show XP tier roles and your current rank"),
        ("/updateroles", "Force-refresh all member roles  *(Admin)*"),
    ],
    "🎙️  Voice": [
        ("/voicetime",   "Check your voice channel time"),
        ("/vctop",       "Voice time leaderboard"),
        ("/createvc",    "Create a temporary voice channel"),
    ],
    "🎵  Music": [
        ("/play",        "Play a song by name or YouTube URL"),
        ("/queue",       "View the current queue"),
        ("/nowplaying",  "Show the current track"),
        ("/skip",        "Skip the current song"),
        ("/pause",       "Pause playback"),
        ("/resume",      "Resume playback"),
        ("/stop",        "Stop music and disconnect"),
        ("/volume",      "Set volume 1–100"),
        ("/loop",        "Toggle loop mode"),
        ("/shuffle",     "Shuffle the queue"),
    ],
    "🎮  Fun": [
        ("/8ball",       "Ask the magic 8-ball a question"),
        ("/coinflip",    "Flip a coin"),
        ("/roll",        "Roll a dice (default: d6)"),
    ],
    "🔍  Profile": [
        ("/profile",     "View your full café profile"),
        ("/apexstats",   "Look up Apex Legends stats for any player"),
        ("/lfg",         "Post a Looking For Group listing"),
    ],
}


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show all Café Bot commands")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="◉  Café Bot — Commands",
            description=f"*everything the bot can do*\n{SEP}",
            color=0xB0C0F5
        )

        for category, cmds in COMMANDS.items():
            lines = "\n".join(f"→  `{name}` — {desc}" for name, desc in cmds)
            embed.add_field(name=category, value=lines, inline=False)

        embed.set_footer(text="Admin-only commands require the Administrator permission.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Help(bot))
