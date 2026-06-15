import discord
from discord import app_commands
from discord.ext import commands
import time

XP_PER_MINUTE_IN_VC = 2   # XP earned per minute in a voice channel

class Voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # {user_id: join_timestamp}
        self.voice_sessions: dict[int, float] = {}
        # {channel_id: owner_id}
        self.temp_vcs: dict[int, int] = {}

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _save_session(self, user_id: int):
        """Flush an active voice session to the database and return seconds."""
        if user_id not in self.voice_sessions:
            return 0
        duration = int(time.time() - self.voice_sessions.pop(user_id))
        if duration > 0:
            self.bot.db.add_voice_time(user_id, duration)
            xp = duration // 60 * XP_PER_MINUTE_IN_VC
            if xp > 0:
                self.bot.db.add_xp(user_id, xp)
        return duration

    async def _check_temp_vc(self, channel: discord.VoiceChannel):
        """Delete a temp VC if it belongs to us and is now empty."""
        if channel and channel.id in self.temp_vcs and len(channel.members) == 0:
            del self.temp_vcs[channel.id]
            try:
                await channel.delete(reason="Temp VC auto-deleted (empty)")
            except Exception:
                pass

    # ── Voice state listener ──────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot:
            return

        joined  = after.channel is not None and before.channel is None
        left    = before.channel is not None and after.channel is None
        moved   = (before.channel is not None and after.channel is not None
                   and before.channel.id != after.channel.id)

        if joined:
            self.voice_sessions[member.id] = time.time()

        elif left:
            self._save_session(member.id)
            await self._check_temp_vc(before.channel)

        elif moved:
            self._save_session(member.id)
            self.voice_sessions[member.id] = time.time()
            await self._check_temp_vc(before.channel)

    # ── /createvc ─────────────────────────────────────────────────────────────

    @app_commands.command(name="createvc", description="Create a private temporary voice channel")
    @app_commands.describe(
        name="Name for your voice channel",
        limit="Max users (0 = unlimited)"
    )
    async def createvc(self, interaction: discord.Interaction, name: str, limit: int = 0):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Must be used in a server.", ephemeral=True)
            return

        guild    = interaction.guild
        category = None

        # Prefer the category the user is currently in, otherwise first VC category
        if interaction.user.voice and interaction.user.voice.channel:
            category = interaction.user.voice.channel.category
        else:
            for cat in guild.categories:
                if any(isinstance(c, discord.VoiceChannel) for c in cat.channels):
                    category = cat
                    break

        try:
            channel = await guild.create_voice_channel(
                name=f"🔒 {name}",
                category=category,
                user_limit=limit if limit > 0 else None,
                reason=f"Temp VC by {interaction.user}"
            )
            self.temp_vcs[channel.id] = interaction.user.id

            # Move creator in if they're already in a VC
            if interaction.user.voice:
                await interaction.user.move_to(channel)
                moved_msg = "You've been moved in automatically!"
            else:
                moved_msg = f"Join it here: {channel.mention}"

            embed = discord.Embed(
                title="🎙️ Temp VC Created!",
                description=(
                    f"**{channel.name}** is live!\n"
                    f"👥 Limit: {'Unlimited' if limit == 0 else limit}\n"
                    f"{moved_msg}\n\n"
                    f"🗑️ It will auto-delete when everyone leaves."
                ),
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to create voice channels!", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    # ── /voicetime ────────────────────────────────────────────────────────────

    @app_commands.command(name="voicetime", description="Check time spent in voice channels")
    async def voicetime(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        user   = self.bot.db.get_user(target.id)
        total  = user.get('voice_time', 0)

        # Add live session time if they're in a VC right now
        if target.id in self.voice_sessions:
            total += int(time.time() - self.voice_sessions[target.id])

        hours = total // 3600
        mins  = (total % 3600) // 60

        embed = discord.Embed(
            title=f"🎙️ {target.display_name}'s Voice Time",
            description=f"**{hours}h {mins}m** spent in voice channels",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Voice(bot))
