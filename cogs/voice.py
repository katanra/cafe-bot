import discord
from discord import app_commands
from discord.ext import commands
from discord.ext import tasks
import datetime
import time

XP_PER_MINUTE_IN_VC = 2

# Channel to post milestone announcements in
MILESTONE_CHANNEL = "general"

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

MILESTONE_MESSAGES = {
    10:  "→  {user} has spent **10 hours** in the café. *A regular.*",
    50:  "→  {user} has spent **50 hours** in the café. *Practically lives here.*",
    100: "→  {user} has spent **100 hours** in the café. *Are you okay?*",
    250: "→  {user} has spent **250 hours** in the café. *The barista knows your order.*",
    500: "→  {user} has spent **500 hours** in the café. *You ARE the café.*",
}

# Weekly top 3 VC XP rewards (resets Sunday midnight UTC)
WEEKLY_VC_REWARDS = [500, 300, 100]


class Voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_sessions: dict[int, float] = {}   # {user_id: join_timestamp}
        self.temp_vcs:       dict[int, int]   = {}   # {channel_id: owner_id}
        self.weekly_vc_reset.start()

    def cog_unload(self):
        self.weekly_vc_reset.cancel()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _fmt_time(self, seconds: int) -> str:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h:
            return f"{h}h {m}m"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"

    def _progress_bar(self, total_seconds: int) -> str:
        """Returns tier name + Unicode progress bar toward next milestone."""
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
            return (
                f"→  Tier  —  **{tier_name}**  ◉  *max*\n"
                f"`{'█' * 15}`  {hours:.0f}h reached"
            )
        progress = (hours - current_tier) / (next_ms - current_tier)
        filled   = min(15, int(progress * 15))
        bar      = "█" * filled + "░" * (15 - filled)
        next_name = TIER_NAMES.get(next_ms, f"{next_ms}h")
        return (
            f"→  Tier  —  **{tier_name}**\n"
            f"→  Next  —  **{next_name}** ({next_ms}h)\n"
            f"`{bar}`  {hours:.1f} / {next_ms}h"
        )

    async def _save_session(self, member: discord.Member):
        """Flush session to DB, award XP, check milestones. Returns duration in seconds."""
        user_id = member.id
        if user_id not in self.voice_sessions:
            return 0
        duration = int(time.time() - self.voice_sessions.pop(user_id))
        if duration <= 0:
            return 0

        old_total = self.bot.db.get_user(user_id).get('voice_time', 0)
        self.bot.db.add_voice_time(user_id, duration)
        new_total = old_total + duration

        xp = (duration // 60) * XP_PER_MINUTE_IN_VC
        if xp > 0:
            self.bot.db.add_xp(user_id, xp)

        crossed = self.bot.db.check_new_milestones(user_id, old_total, new_total)
        if crossed and member.guild:
            await self._announce_milestones(member, crossed)

        return duration

    async def _announce_milestones(self, member: discord.Member, milestones: list):
        channel = discord.utils.get(member.guild.text_channels, name=MILESTONE_CHANNEL)
        if not channel:
            for ch in member.guild.text_channels:
                if ch.permissions_for(member.guild.me).send_messages:
                    channel = ch
                    break
        if not channel:
            return
        for m in milestones:
            msg = MILESTONE_MESSAGES.get(m, f"◉ {member.mention} hit **{m} hours** in VC!")
            embed = discord.Embed(
                description=msg.format(user=member.mention),
                color=0xB0C0F5
            )
            await channel.send(embed=embed)

    async def _check_temp_vc(self, channel: discord.VoiceChannel):
        if channel and channel.id in self.temp_vcs and len(channel.members) == 0:
            del self.temp_vcs[channel.id]
            try:
                await channel.delete(reason="Temp VC auto-deleted (empty)")
            except Exception:
                pass

    # ── Weekly reset ──────────────────────────────────────────────────────────

    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=datetime.timezone.utc))
    async def weekly_vc_reset(self):
        """Every Sunday midnight UTC: reward top 3 then reset all VC times."""
        if datetime.datetime.now(datetime.timezone.utc).weekday() != 6:
            return

        top3 = self.bot.db.get_voice_leaderboard(3)
        for i, row in enumerate(top3[:3]):
            if row['voice_time'] > 0:
                self.bot.db.add_xp(row['user_id'], WEEKLY_VC_REWARDS[i])

        self.bot.db.reset_voice_time()

        for guild in self.bot.guilds:
            channel = discord.utils.get(guild.text_channels, name=MILESTONE_CHANNEL)
            if not channel:
                continue
            ranks = ["→  #1", "→  #2", "→  #3"]
            lines = []
            for i, row in enumerate(top3[:3]):
                if row['voice_time'] == 0:
                    continue
                m    = guild.get_member(row['user_id'])
                name = m.display_name if m else f"User {row['user_id']}"
                lines.append(f"{ranks[i]}  **{name}** — +{WEEKLY_VC_REWARDS[i]} XP")
            if lines:
                embed = discord.Embed(
                    title="◉  Weekly VC Reset",
                    description=(
                        f"*The leaderboard has been wiped. Top earners rewarded.*\n"
                        f"{SEP}\n"
                        + "\n".join(lines) +
                        f"\n{SEP}\n"
                        f"→  *See you in the café next week.*"
                    ),
                    color=0xB0C0F5
                )
                await channel.send(embed=embed)

    @weekly_vc_reset.before_loop
    async def before_reset(self):
        await self.bot.wait_until_ready()

    # ── Voice state listener ──────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after:  discord.VoiceState,
    ):
        if member.bot:
            return

        joined = after.channel is not None and before.channel is None
        left   = before.channel is not None and after.channel is None
        moved  = (before.channel is not None and after.channel is not None
                  and before.channel.id != after.channel.id)

        if joined:
            self.voice_sessions[member.id] = time.time()

        elif left:
            await self._save_session(member)
            await self._check_temp_vc(before.channel)

        elif moved:
            await self._save_session(member)
            self.voice_sessions[member.id] = time.time()
            await self._check_temp_vc(before.channel)

    # ── /vctop ────────────────────────────────────────────────────────────────

    @app_commands.command(name="vctop", description="Show the voice time leaderboard")
    async def vctop(self, interaction: discord.Interaction):
        await interaction.response.defer()
        data = self.bot.db.get_voice_leaderboard(10)

        if not data:
            await interaction.followup.send("Nobody has spent time in a VC yet!")
            return

        ranks = ["→  #1", "→  #2", "→  #3"]
        lines = []
        for i, row in enumerate(data):
            if row['voice_time'] == 0:
                continue
            member = interaction.guild.get_member(row['user_id'])
            name   = member.display_name if member else f"User {row['user_id']}"
            rank   = ranks[i] if i < 3 else f"      #{i+1}"
            total  = row['voice_time']
            if row['user_id'] in self.voice_sessions:
                total += int(time.time() - self.voice_sessions[row['user_id']])
            lines.append(f"{rank}  **{name}** — {self._fmt_time(total)}")

        if not lines:
            await interaction.followup.send("Nobody has spent time in a VC yet!")
            return

        embed = discord.Embed(
            title="◉  Voice Time",
            description=f"*Time spent in the café this week*\n{SEP}\n" + "\n".join(lines),
            color=0xB0C0F5
        )
        embed.set_footer(text="Resets every Sunday midnight UTC  ·  2 XP per minute in VC")
        await interaction.followup.send(embed=embed)

    # ── /voicetime ────────────────────────────────────────────────────────────

    @app_commands.command(name="voicetime", description="Check time spent in voice channels")
    async def voicetime(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        user   = self.bot.db.get_user(target.id)
        total  = user.get('voice_time', 0)

        if target.id in self.voice_sessions:
            total += int(time.time() - self.voice_sessions[target.id])

        progress = self._progress_bar(total)

        embed = discord.Embed(
            title=f"◉  {target.display_name}",
            description=(
                f"*Voice channel time*\n"
                f"{SEP}\n"
                f"→  **{self._fmt_time(total)}**  in the café\n"
                f"{SEP}\n"
                f"{progress}"
            ),
            color=0xB0C0F5
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    # ── /createvc ─────────────────────────────────────────────────────────────

    @app_commands.command(name="createvc", description="Create a temporary voice channel")
    @app_commands.describe(name="Name for your voice channel", limit="Max users (0 = unlimited)")
    async def createvc(self, interaction: discord.Interaction, name: str, limit: int = 0):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Must be used in a server.", ephemeral=True)
            return

        TEMP_VC_CATEGORY_ID = 1515950863422586950

        guild    = interaction.guild
        category = guild.get_channel(TEMP_VC_CATEGORY_ID)
        if category is None:
            try:
                category = await guild.fetch_channel(TEMP_VC_CATEGORY_ID)
            except Exception as e:
                print(f"[Voice] fetch_channel failed: {e}")
                category = None

        print(f"[Voice] createvc — category lookup: {category!r}")

        if category is None or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                f"→ Category ID `{TEMP_VC_CATEGORY_ID}` not found or is not a category. "
                f"Check that Developer Mode is on and you copied the ID from the **category**, not a channel.",
                ephemeral=True
            )
            return

        try:
            channel = await guild.create_voice_channel(
                name=f"[ {name} ]",
                category=category,
                user_limit=limit if limit > 0 else None,
                reason=f"Temp VC by {interaction.user}"
            )
            self.temp_vcs[channel.id] = interaction.user.id

            if interaction.user.voice:
                await interaction.user.move_to(channel)
                moved_msg = "You've been moved in automatically."
            else:
                moved_msg = f"Join here: {channel.mention}"

            embed = discord.Embed(
                title="◉  Temp VC Created",
                description=(
                    f"**{channel.name}** is live.\n"
                    f"Limit: {'Unlimited' if limit == 0 else limit}\n"
                    f"{moved_msg}\n\n"
                    f"Auto-deletes when everyone leaves."
                ),
                color=0xB0C0F5
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to create voice channels!", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Voice(bot))
