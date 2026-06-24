import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import random

SEP = ("· " * 14).strip()

YDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'noplaylist': True,
    'source_address': '0.0.0.0',
}

FFMPEG_OPTS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}


class GuildMusic:
    def __init__(self):
        self.queue:   list[dict]                      = []
        self.current: dict | None                     = None
        self.voice:   discord.VoiceClient | None      = None
        self.channel: discord.abc.Messageable | None  = None
        self.volume:  float                           = 0.5
        self.loop:    bool                            = False


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot    = bot
        self._ydl   = yt_dlp.YoutubeDL(YDL_OPTS)
        self._states: dict[int, GuildMusic] = {}

    def _state(self, gid: int) -> GuildMusic:
        if gid not in self._states:
            self._states[gid] = GuildMusic()
        return self._states[gid]

    def _fmt(self, secs) -> str:
        if not secs:
            return "?"
        m, s = divmod(int(secs), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    async def _search(self, query: str) -> dict | None:
        """Search YouTube and return track info dict."""
        loop = self.bot.loop
        try:
            info = await loop.run_in_executor(
                None, lambda: self._ydl.extract_info(query, download=False)
            )
        except Exception:
            return None
        if not info:
            return None
        entry = info['entries'][0] if 'entries' in info else info
        return {
            'title':    entry.get('title', 'Unknown'),
            'url':      entry.get('webpage_url') or entry.get('url', ''),
            'stream':   entry.get('url', ''),
            'duration': entry.get('duration', 0),
            'thumb':    entry.get('thumbnail', ''),
        }

    def _after_play(self, guild: discord.Guild, err):
        """Called by discord.py after a song finishes. Schedules next track."""
        asyncio.run_coroutine_threadsafe(self._advance(guild), self.bot.loop)

    async def _advance(self, guild: discord.Guild):
        """Pop next track from queue and start playing it."""
        state = self._state(guild.id)

        # Loop: re-queue the finished song before advancing
        if state.loop and state.current:
            state.queue.insert(0, state.current)

        if not state.queue or not state.voice or not state.voice.is_connected():
            state.current = None
            return

        track = state.queue.pop(0)
        state.current = track

        # Re-fetch fresh stream URL so queued songs don't expire
        fresh = await self._search(track['url'])
        stream_url = fresh['stream'] if fresh else track['stream']

        try:
            audio = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTS)
            state.voice.play(
                discord.PCMVolumeTransformer(audio, volume=state.volume),
                after=lambda e: self._after_play(guild, e)
            )
        except Exception as e:
            if state.channel:
                await state.channel.send(f"❌ Couldn't play **{track['title']}**: {e}")
            await self._advance(guild)
            return

        if state.channel:
            embed = discord.Embed(
                title="◉  Now Playing",
                description=(
                    f"*The café has music*\n"
                    f"{SEP}\n"
                    f"→  **{track['title']}**\n"
                    f"→  Duration: {self._fmt(track['duration'])}\n"
                    f"→  {track['url']}"
                ),
                color=0xB0C0F5
            )
            if track.get('thumb'):
                embed.set_thumbnail(url=track['thumb'])
            await state.channel.send(embed=embed)

    # ── /play ──────────────────────────────────────────────────────────────────

    @app_commands.command(name="play", description="Play a song in your voice channel")
    @app_commands.describe(query="Song name or YouTube URL")
    async def play(self, interaction: discord.Interaction, query: str):
        if not interaction.user.voice:
            await interaction.response.send_message(
                "❌ You need to be in a voice channel first!", ephemeral=True
            )
            return

        await interaction.response.defer()

        state = self._state(interaction.guild_id)
        state.channel = interaction.channel

        # Connect or move to user's voice channel
        vc_channel = interaction.user.voice.channel
        if state.voice and state.voice.is_connected():
            if state.voice.channel != vc_channel:
                await state.voice.move_to(vc_channel)
        else:
            try:
                state.voice = await vc_channel.connect(timeout=10.0, reconnect=False, self_deaf=True)
            except Exception as e:
                await interaction.followup.send(
                    "❌ Couldn't connect to your voice channel. Try using `/stop` first to reset, then try again.",
                    ephemeral=True
                )
                return

        track = await self._search(query)
        if not track:
            await interaction.followup.send("❌ Couldn't find that song. Try a different search or URL.")
            return

        state.queue.append(track)

        if state.voice.is_playing() or state.voice.is_paused():
            # Already playing — add to queue
            embed = discord.Embed(
                title="◉  Added to Queue",
                description=(
                    f"{SEP}\n"
                    f"→  **{track['title']}**\n"
                    f"→  Duration: {self._fmt(track['duration'])}\n"
                    f"→  Position in queue: #{len(state.queue)}"
                ),
                color=0xB0C0F5
            )
            if track.get('thumb'):
                embed.set_thumbnail(url=track['thumb'])
            await interaction.followup.send(embed=embed)
        else:
            # Nothing playing — start immediately
            await interaction.followup.send(
                embed=discord.Embed(description="→  Loading...", color=0xB0C0F5)
            )
            await self._advance(interaction.guild)

    # ── /skip ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="skip", description="Skip the current song")
    async def skip(self, interaction: discord.Interaction):
        state = self._state(interaction.guild_id)
        if not state.voice or not state.voice.is_playing():
            await interaction.response.send_message("❌ Nothing is playing.", ephemeral=True)
            return
        title = state.current['title'] if state.current else "current song"
        state.voice.stop()  # triggers _after_play → _advance automatically
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"→  Skipped **{title}**.",
                color=0xB0C0F5
            )
        )

    # ── /pause & /resume ──────────────────────────────────────────────────────

    @app_commands.command(name="pause", description="Pause the current song")
    async def pause(self, interaction: discord.Interaction):
        state = self._state(interaction.guild_id)
        if state.voice and state.voice.is_playing():
            state.voice.pause()
            await interaction.response.send_message(
                embed=discord.Embed(description="→  Paused.", color=0xB0C0F5)
            )
        else:
            await interaction.response.send_message("❌ Nothing is playing.", ephemeral=True)

    @app_commands.command(name="resume", description="Resume the paused song")
    async def resume(self, interaction: discord.Interaction):
        state = self._state(interaction.guild_id)
        if state.voice and state.voice.is_paused():
            state.voice.resume()
            await interaction.response.send_message(
                embed=discord.Embed(description="→  Resumed.", color=0xB0C0F5)
            )
        else:
            await interaction.response.send_message("❌ Nothing is paused.", ephemeral=True)

    # ── /stop ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="stop", description="Stop music and disconnect the bot from VC")
    async def stop(self, interaction: discord.Interaction):
        state = self._state(interaction.guild_id)
        if state.voice:
            state.queue.clear()
            state.current = None
            await state.voice.disconnect()
            state.voice = None
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"→  Stopped and disconnected.\n{SEP}\n→  Queue cleared.",
                color=0xB0C0F5
            )
        )

    # ── /queue ────────────────────────────────────────────────────────────────

    @app_commands.command(name="queue", description="Show the music queue")
    async def queue_cmd(self, interaction: discord.Interaction):
        state = self._state(interaction.guild_id)
        if not state.current and not state.queue:
            await interaction.response.send_message(
                embed=discord.Embed(description="→  The queue is empty.", color=0xB0C0F5)
            )
            return

        lines = []
        if state.current:
            lines.append(
                f"→  **Now:** {state.current['title']}  `{self._fmt(state.current['duration'])}`"
            )
        if state.queue:
            lines.append(SEP)
            for i, t in enumerate(state.queue[:10], 1):
                lines.append(f"→  **#{i}**  {t['title']}  `{self._fmt(t['duration'])}`")
            if len(state.queue) > 10:
                lines.append(f"→  *...and {len(state.queue) - 10} more*")

        embed = discord.Embed(
            title="◉  Queue",
            description="\n".join(lines),
            color=0xB0C0F5
        )
        embed.set_footer(text=f"{len(state.queue)} song(s) waiting  ·  Use /skip to advance")
        await interaction.response.send_message(embed=embed)

    # ── /volume ───────────────────────────────────────────────────────────────

    @app_commands.command(name="volume", description="Set the music volume (1–100)")
    @app_commands.describe(level="Volume level from 1 to 100")
    async def volume(self, interaction: discord.Interaction, level: int):
        if not 1 <= level <= 100:
            await interaction.response.send_message("❌ Volume must be between 1 and 100.", ephemeral=True)
            return
        state = self._state(interaction.guild_id)
        state.volume = level / 100
        if state.voice and isinstance(state.voice.source, discord.PCMVolumeTransformer):
            state.voice.source.volume = state.volume
        bar_filled = int((level / 100) * 15)
        bar = "█" * bar_filled + "░" * (15 - bar_filled)
        await interaction.response.send_message(
            embed=discord.Embed(
                description=(
                    f"→  Volume set to **{level}%**\n"
                    f"`{bar}`"
                ),
                color=0xB0C0F5
            )
        )

    # ── /loop ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="loop", description="Toggle loop mode for the current song")
    async def loop(self, interaction: discord.Interaction):
        state = self._state(interaction.guild_id)
        state.loop = not state.loop
        status = "**on** — current song will repeat" if state.loop else "**off**"
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"→  Loop is now {status}.",
                color=0xB0C0F5
            )
        )

    # ── /shuffle ──────────────────────────────────────────────────────────────

    @app_commands.command(name="shuffle", description="Shuffle the music queue")
    async def shuffle(self, interaction: discord.Interaction):
        state = self._state(interaction.guild_id)
        if len(state.queue) < 2:
            await interaction.response.send_message("❌ Need at least 2 songs in the queue to shuffle.", ephemeral=True)
            return
        random.shuffle(state.queue)
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"→  Shuffled **{len(state.queue)}** songs in the queue.",
                color=0xB0C0F5
            )
        )

    # ── /nowplaying ───────────────────────────────────────────────────────────

    @app_commands.command(name="nowplaying", description="Show what's currently playing")
    async def nowplaying(self, interaction: discord.Interaction):
        state = self._state(interaction.guild_id)
        if not state.current:
            await interaction.response.send_message("❌ Nothing is playing right now.", ephemeral=True)
            return
        t = state.current
        embed = discord.Embed(
            title="◉  Now Playing",
            description=(
                f"*The café has music*\n"
                f"{SEP}\n"
                f"→  **{t['title']}**\n"
                f"→  Duration: {self._fmt(t['duration'])}\n"
                f"→  {t['url']}"
            ),
            color=0xB0C0F5
        )
        if t.get('thumb'):
            embed.set_thumbnail(url=t['thumb'])
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Music(bot))
