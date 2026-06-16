import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import os

SEP = ("· " * 14).strip()

APEX_API_BASE = "https://api.mozambiquehe.re/bridge"

PLATFORM_CHOICES = [
    app_commands.Choice(name="PC (Origin / EA App)", value="PC"),
    app_commands.Choice(name="PlayStation",           value="PS4"),
    app_commands.Choice(name="Xbox",                  value="X1"),
]

# Rank division display names
RANK_NAMES = {
    "Bronze":   "🟤 Bronze",
    "Silver":   "⚪ Silver",
    "Gold":     "🟡 Gold",
    "Platinum": "🔵 Platinum",
    "Diamond":  "💎 Diamond",
    "Master":   "🟣 Master",
    "Apex Predator": "🔴 Apex Predator",
}


class ApexStats(commands.Cog):
    def __init__(self, bot):
        self.bot     = bot
        self.api_key = os.getenv("APEX_API_KEY", "")

    @app_commands.command(name="apexstats", description="Look up Apex Legends stats for any player")
    @app_commands.describe(
        username="EA / Origin username (exactly as it appears in-game)",
        platform="Platform the account is on (default: PC)"
    )
    @app_commands.choices(platform=PLATFORM_CHOICES)
    async def apexstats(
        self,
        interaction: discord.Interaction,
        username: str,
        platform: str = "PC"
    ):
        if not self.api_key:
            await interaction.response.send_message(
                "❌ No Apex API key set.\n"
                "Get a free key at **https://apexlegendsapi.com** then add it to your `.env` file as:\n"
                "`APEX_API_KEY=your_key_here`",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        params = {
            "player": username,
            "platform": platform,
            "auth": self.api_key,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(APEX_API_BASE, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 404:
                        await interaction.followup.send(
                            f"❌ Player **{username}** not found on {platform}. Check the spelling and platform.",
                            ephemeral=True
                        )
                        return
                    if resp.status == 403:
                        await interaction.followup.send(
                            "❌ Invalid API key. Check `APEX_API_KEY` in your `.env` file.",
                            ephemeral=True
                        )
                        return
                    if resp.status != 200:
                        await interaction.followup.send(
                            f"❌ Apex API returned an error ({resp.status}). Try again in a moment.",
                            ephemeral=True
                        )
                        return
                    data = await resp.json()
        except Exception as e:
            await interaction.followup.send(f"❌ Couldn't reach the Apex API: {e}", ephemeral=True)
            return

        # ── Parse response ────────────────────────────────────────────────────
        try:
            global_data  = data.get("global", {})
            real_name    = global_data.get("name", username)
            level        = global_data.get("level", "?")
            platform_out = global_data.get("platform", platform)

            # Ranked Battle Royale
            rank_br   = global_data.get("rank", {})
            rank_name = rank_br.get("rankName", "Unranked")
            rank_div  = rank_br.get("rankDiv", "")
            rank_score= rank_br.get("rankScore", 0)
            rank_label= RANK_NAMES.get(rank_name, rank_name)
            if rank_div and rank_name not in ("Apex Predator", "Master"):
                rank_label += f" {rank_div}"

            # Ranked Arenas (may not exist in newer seasons)
            rank_ar      = global_data.get("arena", {})
            arena_name   = rank_ar.get("rankName", "")
            arena_div    = rank_ar.get("rankDiv", "")
            arena_label  = RANK_NAMES.get(arena_name, arena_name) if arena_name else None
            if arena_div and arena_name not in ("Apex Predator", "Master"):
                arena_label = f"{arena_label} {arena_div}" if arena_label else None

            # Realtime / selected legend
            realtime   = data.get("realtime", {})
            online     = realtime.get("isOnline", 0)
            in_game    = realtime.get("isInGame", 0)
            legend     = realtime.get("selectedLegend", "Unknown")

            # Avatar
            avatar_url = global_data.get("avatar", "")

        except (KeyError, TypeError):
            await interaction.followup.send(
                "❌ Got an unexpected response from the API. The player may have a private profile.",
                ephemeral=True
            )
            return

        # ── Build embed ───────────────────────────────────────────────────────
        status_line = ""
        if online:
            status_line = "🟢  *Currently online*"
            if in_game:
                status_line = "🎮  *In a match right now*"

        embed = discord.Embed(
            title=f"◉  {real_name}",
            description=(
                f"*Apex Legends — {platform_out}*\n"
                f"{SEP}\n"
                f"{status_line}" if status_line else
                f"*Apex Legends — {platform_out}*\n"
                f"{SEP}"
            ),
            color=0xB0C0F5
        )

        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        embed.add_field(name="→  Level",        value=f"**{level}**",            inline=True)
        embed.add_field(name="→  Legend",        value=f"**{legend}**",           inline=True)
        embed.add_field(name="→  BR Rank",       value=f"**{rank_label}**\n{rank_score:,} RP", inline=True)

        if arena_label:
            embed.add_field(name="→  Arena Rank", value=f"**{arena_label}**", inline=True)

        embed.set_footer(text="Stats via apexlegendsapi.com  ·  Data may be a few minutes delayed")
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(ApexStats(bot))
