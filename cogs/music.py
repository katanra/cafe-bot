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

# ── yt-dlp options ─────────────────────────────────────────────────────────────
# Uses the iOS client — most reliable way to bypass YouTube bot detection in 2025
YDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'noplaylist': True,
    'source_address': '0.0.0.0',
    'extractor_retries': 3,
    'socket_timeout': 15,
    'extractor_args': {
        'youtube': {
            'player_client': ['ios', 'web_embedded'],
        }
    },
}

# ── FFmpeg options ─────────────────────────────────────────────────────────────
# If ffmpeg.exe is not on PATH, set FFMPEG_PATH in your .env:
#   FFMPEG_PATH=C:\ffmpeg\bin\ffmpeg.exe
FFMPEG_EXE = os.getenv('FFMPEG_PATH', 'ffmpeg')

FFMPEG_OPTS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
    'executable': FFMPEG_EXE,
}

SPOTIFY_TRACK_RE    = re.compile(r'open\.spotify\.com/track/([A-Za-z0-9]+)')
SPOTIFY_PLAYLIST_RE = re.compile(r'open\.spotify\.com/playlist/([A-Za-z0-9]+)')
SPOTIFY_ALBUM_RE    = re.compile(r'open\.spotify\.com/album/([A-Za-z0-9]+)')


def _make_spotify() -> spotipy.Spotify | None:
    cid     = os.getenv('SPOTIFY_CLIENT_ID')
    csecret = os.getenv('SPOTIFY_CLIENT_SECRET')
    if not cid or not csecret:
        return None
    try:
        return spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id=cid, client_secret=csecret
        ))
    except Exception as e:
        print(f"[Music] Spotify init failed: {e}")
        return None


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
        print(f"[Music] Loaded. FFmpeg path: '{FFMPEG_EXE}' | Spotify: {'yes' if self._sp else 'no'}")

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
        if not self._sp:
            return None
        try:
            t      = self._sp.track(track_id)
            artist = t['artists'][0]['name']
            title  = t['name']
            return f"{artist} - {title}"
        except Exception as e:
            print(f"[Music] Spotify track lookup failed: {e}")
            return None

    def _spotify_playlist_queries(self, playlist_id: str) -> list[str]:
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
                    queries.append(f"{t['artists'][0]['name']} - {t['name']}")
                results = self._sp.next(results) if results.get('next') else None
        except Exception as e:
            print(f"[Music] Spotify playlist lookup failed: {e}")
        return queries

    def _spotify_album_queries(self, album_id: str) -> list[str]:
        if not self._sp:
            return []
        queries = []
        try:
            results = self._sp.album_tracks(album_id, limit=50)
            while results:
                for t in results.get('items', []):
                    queries.append(f"{t['artists'][0]['name']} - {t['name']}")
                results = self._sp.next(results) if results.get('next') else None
        except Exception as e:
            print(f"[Music] Spotify album lookup failed: {e}")
        return queries

    def _resolve_spotify(self, query: str):
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
        """Search YouTube (or fetch a URL). Returns track dict or None on failure."""
        loop = self.bot.loop

        def _extract():
            try:
                return self._ydl.extract_info(query, download=False)
            except yt_dlp.utils.DownloadError as e:
                print(f"[Music] yt-dlp DownloadError for '{query}': {e}")
                return None
            except Exception as e:
                print(f"[Music] yt-dlp unexpected error for '{query}': {e}")
                return None

        info = await loop.run_in_executor(None, _extract)
        if not info:
            return None

        entry = info['entries'][0] if 'entries' in info else info
        stream = entry.get('url', '')
        if not stream:
            print(f"[Music] No stream URL returned for '{query}'")
            return None

        return {
            'title':    entry.get('title', 'Unknown'),
            'url':      entry.get('webpage_url') or entry.get('url', ''),
            'stream':   stream,
            'duration': entry.get('duration', 0),
            'thumb':    entry.get('thumbnail', ''),
        }

    # ── Playback internals ─────────────────────────────────────────────────────

    def _after_play(self, guild: discord.Guild, err):
        if err:
            print(f"[Music] Playback error in '{guild.name}': {err}")
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

        print(f"[Music] Advancing to: {track['title']}")

        # Re-fetch fresh stream URL so queued songs don't expire
        fresh      = await self._search(track['url'])
        stream_url = fresh['stream'] if fresh else track['stream']

        if not stream_url:
            print(f"[Music] No stream URL for '{track['title']}', skipping.")
            if state.channel:
                await state.channel.send(
                    embed=discord.Embed(
                        description=f"→  Skipped **{track['title']}** — couldn't get a stream URL.",
                        color=0xB0C0F5
                    )
                )
            await self._advance(guild)
            return

        try:
            audio = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTS)
        except FileNotFoundError:
            msg = (
                f"→  FFmpeg not found at `{FFMPEG_EXE}`.\n"
                f"→  Install FFmpeg and add it to PATH, or set `FFMPEG_PATH` in your `.env`.\n"
                f"→  Download: https://ffmpeg.org/download.html"
            )
            print(f"[Music] FFmpeg not found at '{FFMPEG_EXE}'")
            if state.channel:
                await state.channel.send(
                    embed=discord.Embed(description=msg, color=0xE74C3C)
                )
            state.current = None
            return
        except Exception as e:
            print(f"[Music] FFmpegPCMAudio error: {e}")
            if state.channel:
                await state.channel.send(
                    embed=discord.Embed(
                        description=f"→  Audio error: `{e}`", color=0xE74C3C
                    )
                )
            await self._advance(guild)
            return

        try:
            source = discord.PCMVolumeTransformer(audio, volume=state.volume)
        except Exception as e:
            print(f"[Music] PCMVolumeTransformer failed (audioop missing?): {e} — playing at fixed volume")
            source = audio  # fallback: play without volume control

        try:
            state.voice.play(
                source,
                after=lambda e: self._after_play(guild, e)
            )
        except Exception as e:
            print(f"[Music] voice.play() error: {e}")
            if state.channel:
                await state.channel.send(
                    embed=discord.Embed(
                        description=f"→  Playback failed: `{e}`", color=0xE74C3C
                    )
                )
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
        state      = self._state(interaction.guild_id)
        vc_channel = interaction.user.voice.channel

        if state.voice and state.voice.is_connected():
            if state.voice.channel != vc_channel:
                await state.voice.move_to(vc_channel)
            return state.voice

        try:
            state.voice = await vc_channel.connect(timeout=10.0, reconnect=True, self_deaf=True)
            return state.voice
        except Exception as e:
            print(f"[Music] Voice connect error: {e}")
            await interaction.followup.send(
                "[x] Couldn't connect to your voice channel. Try `/stop` to reset, then try again.",
                ephemeral=True
            )
            return None

    # ── /play ──────────────────────────────────────────────────────────────────

    @app_commands.command(name="play", description="Play a song — supports YouTube, searches, and Spotify links")
    @app_commands.describe(query="Song name, YouTube URL, or Spotify track/playlist/album link")
    async def play(self, interaction: discord.Interaction, query: str):
        if not interaction.user.voice:
            await interaction.response.send_message(
                "[x] You need to be in a voice channel first!", ephemeral=True
            )
            return

        await interaction.response.defer()

        state         = self._state(interaction.guild_id)
        state.channel = interaction.channel

        vc = await self._connect(interaction)
        if not vc:
            return

        # ── Spotify resolution ──
        spotify_result = self._resolve_spotify(query)

        if isinstance(spotify_result, list):
            if not spotify_result:
                await interaction.followup.send("[x] Couldn't find any tracks in that Spotify link.")
                return

            added       = 0
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
                await interaction.followup.send("[x] Couldn't find any of those tracks on YouTube.")
                return

            embed = discord.Embed(
                title="◉  Spotify Playlist Queued",
                description=(
                    f"{SEP}\n"
                    f"→  Added **{added}** tracks to the queue.\n"
                    f"→  Starting with: **{first_track['title']}**"
                ),
                color=0x1DB954
            )
            await interaction.followup.send(embed=embed)

            if not vc.is_playing() and not vc.is_paused():
                await self._advance(interaction.guild)
            return

        elif isinstance(spotify_result, str):
            query = spotify_result

        # ── YouTube search / URL ──
        track = await self._search(query)
        if not track:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=(
                        f"→  Couldn't find that song.\n"
                        f"→  Check the console for details, or try a different search."
                    ),
                    color=0xE74C3C
                )
            )
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

    # ── /musictest ────────────────────────────────────────────────────────────

    @app_commands.command(name="musictest", description="Diagnose music issues (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def musictest(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        lines = []

        # FFmpeg check
        import shutil
        ffmpeg_found = shutil.which(FFMPEG_EXE) or (os.path.isfile(FFMPEG_EXE) if FFMPEG_EXE != 'ffmpeg' else False)
        lines.append(f"→  FFmpeg path: `{FFMPEG_EXE}`  —  {'found' if ffmpeg_found else '**NOT FOUND**'}")

        # yt-dlp search check
        lines.append("→  Testing yt-dlp search...")
        track = await self._search("ytsearch1:rick astley never gonna give you up")
        if track:
            lines.append(f"→  yt-dlp: OK  —  got `{track['title']}`")
            lines.append(f"→  Stream URL: `{track['stream'][:60]}...`")
        else:
            lines.append("→  yt-dlp: **FAILED** — check console for details")

        # Spotify check
        if self._sp:
            lines.append("→  Spotify: connected")
        else:
            sp_id = os.getenv('SPOTIFY_CLIENT_ID')
            lines.append(f"→  Spotify: {'credentials found but failed to init' if sp_id else 'no credentials in .env'}")

        # audioop check
        try:
            import audioop
            lines.append("→  audioop: OK")
        except ImportError:
            try:
                import audioop_lts  # noqa
                lines.append("→  audioop: OK (audioop-lts)")
            except ImportError:
                lines.append("→  audioop: **MISSING** — volume control disabled, install audioop-lts")

        embed = discord.Embed(
            title="◉  Music Diagnostics",
            description=f"{SEP}\n" + "\n".join(lines),
            color=0xB0C0F5
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /skip ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="skip", description="Skip the current song")
    async def skip(self, interaction: discord.Interaction):
        state = self._state(interaction.guild_id)
        if not state.voice or not state.voice.is_playing():
            await interaction.response.send_message("[x] Nothing is playing.", ephemeral=True)
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
            await interaction.response.send_message("[x] Nothing is playing.", ephemeral=True)

    @app_commands.command(name="resume", description="Resume the paused song")
    async def resume(self, interaction: discord.Interaction):
        state = self._state(interaction.guild_id)
        if state.voice and state.voice.is_paused():
            state.voice.resume()
            await interaction.response.send_message(
                embed=discord.Embed(description="→  Resumed.", color=0xB0C0F5)
            )
        else:
            await interaction.response.send_message("[x] Nothing is paused.", ephemeral=True)

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
            lines.append(f"→  **Now:** {state.current['title']}  `{self._fmt(state.current['duration'])}`")
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
            await interaction.response.send_message("[x] Volume must be between 1 and 100.", ephemeral=True)
            return
        state        = self._state(interaction.guild_id)
        state.volume = level / 100
        if state.voice and isinstance(state.voice.source, discord.PCMVolumeTransformer):
            state.voice.source.volume = state.volume
        bar_filled = int((level / 100) * 15)
        bar        = "█" * bar_filled + "░" * (15 - bar_filled)
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"→  Volume set to **{level}%**\n`{bar}`",
                color=0xB0C0F5
            )
        )

    # ── /loop ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="loop", description="Toggle loop mode for the current song")
    async def loop(self, interaction: discord.Interaction):
        state      = self._state(interaction.guild_id)
        state.loop = not state.loop
        status     = "**on** — current song will repeat" if state.loop else "**off**"
        await interaction.response.send_message(
            embed=discord.Embed(description=f"→  Loop is now {status}.", color=0xB0C0F5)
        )

    # ── /shuffle ──────────────────────────────────────────────────────────────

    @app_commands.command(name="shuffle", description="Shuffle the music queue")
    async def shuffle(self, interaction: discord.Interaction):
        state = self._state(interaction.guild_id)
        if len(state.queue) < 2:
            await interaction.response.send_message(
                "[x] Need at least 2 songs in the queue to shuffle.", ephemeral=True
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
            await interaction.response.send_message("[x] Nothing is playing right now.", ephemeral=True)
            return
        t     = state.current
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
