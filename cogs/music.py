import os
import re
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import random
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

SEP = ("· " * 14).strip()

YDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'noplaylist': True,
    'source_address': '0.0.0.0',
    'extractor_retries': 3,
    'socket_timeout': 10,
}

FFMPEG_OPTS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

SPOTIFY_TRACK_RE   = re.compile(r'open\.spotify\.com/track/([A-Za-z0-9]+)')
SPOTIFY_PLAYLIST_RE = re.compile(r'open\.spotify\.com/playlist/([A-Za-z0-9]+)')
SPOTIFY_ALBUM_RE   = re.compile(r'open\.spotify\.com/album/([A-Za-z0-9]+)')


def _make_spotify() -> spotipy.Spotify | None:
    cid     = os.getenv('SPOTIFY_CLIENT_ID')
    csecret = os.getenv('SPOTIFY_CLIENT_SECRET')
    if not cid or not csecret:
        return None
    return spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=cid, client_secret=csecret
    ))


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
        self.bot     = bot
        self._ydl    = yt_dlp.YoutubeDL(YDL_OPTS)
        self._sp     = _make_spotify()
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

    # ── Spotify helpers ────────────────────────────────────────────────────────

    def _spotify_track_query(self, track_id: str) -> str | None:
        """Return 'Artist - Title' search string for a Spotify track ID."""
        if not self._sp:
            return None
        try:
            t = self._sp.track(track_id)
            artist = t['artists'][0]['name']
            title  = t['name']
            return f"{artist} - {title}"
        except Exception:
            return None

    def _spotify_playlist_queries(self, playlist_id: str) -> list[str]:
        """Return list of 'Artist - Title' strings for every track in a Spotify playlist."""
        if not self._sp:
            return []
        queries = []
        try:
            results = self._sp.playlist_tracks(playlist_id, limit=50)
            while results:
                for item in results.get('items', []):
                    t = item.get('track')
                    if not t:
                        continue
                    artist = t['artists'][0]['name']
                    title  = t['name']
                    queries.append(f"{artist} - {title}")
                results = self._sp.next(results) if results.get('next') else None
        except Exception:
            pass
        return queries

    def _spotify_album_queries(self, album_id: str) -> list[str]:
        """Return list of 'Artist - Title' strings for every track in a Spotify album."""
        if not self._sp:
            return []
        queries = []
        try:
            results = self._sp.album_tracks(album_id, limit=50)
            while results:
                for t in results.get('items', []):
                    artist = t['artists'][0]['name']
                    title  = t['name']
                    queries.append(f"{artist} - {title}")
                results = self._sp.next(results) if results.get('next') else None
        except Exception:
            pass
        return queries

    def _resolve_spotify(self, query: str) -> list[str] | str | None:
        """
        If query is a Spotify URL, resolve it to one or more YouTube search strings.
        Returns:
          - list[str]  for playlists/albums (multiple tracks)
          - str        for a single track
          - None       if not a Spotify URL
        """
        m = SPOTIFY_TRACK_RE.search(query)
        if m:
            return self._spotify_track_query(m.group(1))

        m = SPOTIFY_PLAYLIST_RE.search(query)
        if m:
            return self._spotify_playlist_queries(m.group(1))

        m = SPOTIFY_ALBUM_RE.search(query)
        if m:
            return self._spotify_album_queries(m.group(1))

        return None

    # ── YouTube search ─────────────────────────────────────────────────────────

    async def _search(self, query: str) -> dict | None:
        """Search YouTube (or fetch a URL) and return a track info dict."""
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

    # ── Playback internals ─────────────────────────────────────────────────────

    def _after_play(self, guild: discord.Guild, err):
        asyncio.run_coroutine_threadsafe(self._advance(guild), self.bot.loop)

    async def _advance(self, guild: discord.Guild):
        state = self._state(guild.id)

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

    async def _connect(self, interaction: discord.Interaction) -> discord.VoiceClient | None:
        """Connect or move to the user's voice channel. Returns VoiceClient or None."""
        state = self._state(interaction.guild_id)
        vc_channel = interaction.user.voice.channel

        if state.voice and state.voice.is_connected():
            if state.voice.channel != vc_channel:
                await state.voice.move_to(vc_channel)
            return state.voice

        try:
            state.voice = await vc_channel.connect(timeout=10.0, reconnect=True, self_deaf=True)
            return state.voice
        except Exception:
            await interaction.followup.send(
                "❌ Couldn't connect to your voice channel. Try `/stop` to reset, then try again.",
                ephemeral=True
            )
            return None

    # ── /play ──────────────────────────────────────────────────────────────────

    @app_commands.command(name="play", description="Play a song — supports YouTube URLs, searches, and Spotify links")
    @app_commands.describe(query="Song name, YouTube URL, or Spotify track/playlist/album link")
    async def play(self, interaction: discord.Interaction, query: str):
        if not interaction.user.voice:
            await interaction.response.send_message(
                "❌ You need to be in a voice channel first!", ephemeral=True
            )
            return

        await interaction.response.defer()

        state = self._state(interaction.guild_id)
        state.channel = interaction.channel

        vc = await self._connect(interaction)
        if not vc:
            return

        # ── Spotify resolution ──
        spotify_result = self._resolve_spotify(query)

        if isinstance(spotify_result, list):
            # Playlist or album — queue all tracks
            if not spotify_result:
                await interaction.followup.send("❌ Couldn't find any tracks in that Spotify link.")
                return

            # Search YouTube for the first track to start playing immediately
            added = 0
            first_track = None
            for i, sq in enumerate(spotify_result):
                track = await self._search(sq)
                if not track:
                    continue
                state.queue.append(track)
                if i == 0:
                    first_track = track
                added += 1

            if not added:
                await interaction.followup.send("❌ Couldn't find any of those tracks on YouTube.")
                return

            embed = discord.Embed(
                title="◉  Spotify Playlist Queued",
                description=(
                    f"{SEP}\n"
                    f"→  Added **{added}** tracks to the queue.\n"
                    f"→  Starting with: **{first_track['title']}**"
                ),
                color=0x1DB954  # Spotify green
            )
            await interaction.followup.send(embed=embed)

            if not vc.is_playing() and not vc.is_paused():
                await self._advance(interaction.guild)
            return

        elif isinstance(spotify_result, str):
            # Single Spotify track — resolve to YouTube search
            query = spotify_result

        # ── YouTube search / URL ──
        track = await self._search(query)
        if not track:
            await interaction.followup.send("❌ Couldn't find that song. Try a different search or URL.")
            return

        state.queue.append(track)

        if vc.is_playing() or vc.is_paused():
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
        state.voice.stop()
        await interaction.response.send_message(
            embed=discord.Embed(description=f"→  Skipped **{title}**.", color=0xB0C0F5)
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
            embed=discord.Embed(description=f"→  Loop is now {status}.", color=0xB0C0F5)
        )

    # ── /shuffle ──────────────────────────────────────────────────────────────

    @app_commands.command(name="shuffle", description="Shuffle the music queue")
    async def shuffle(self, interaction: discord.Interaction):
        state = self._state(interaction.guild_id)
        if len(state.queue) < 2:
            await interaction.response.send_message(
                "❌ Need at least 2 songs in the queue to shuffle.", ephemeral=True
            )
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
