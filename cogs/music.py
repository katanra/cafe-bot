import os
import re
import shutil
import datetime
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import random
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

SEP = ("· " * 14).strip()

# ── yt-dlp format fallback chain ───────────────────────────────────────────────
# The bot tries each format in order. If one fails it logs the error and retries
# with the next. 'best' at the end is the catch-all.
YDL_FORMAT_CHAIN = [
    'bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best',
    'bestaudio/best',
    'best',
]

YDL_OPTS = {
    'format': YDL_FORMAT_CHAIN[0],
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'noplaylist': True,
    'source_address': '0.0.0.0',
    'extractor_retries': 3,
    'socket_timeout': 15,
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


# ── Error log ──────────────────────────────────────────────────────────────────

class MusicDiag:
    """Circular buffer of recent music errors + auto-fix attempts."""
    MAX = 25

    def __init__(self):
        self._log: list[dict] = []

    def record(self, context: str, error: str, fixed: bool = False):
        self._log.append({
            'time':    datetime.datetime.now().strftime('%H:%M:%S'),
            'context': context,
            'error':   str(error)[:220],
            'fixed':   fixed,
        })
        if len(self._log) > self.MAX:
            self._log.pop(0)

    def recent(self, n: int = 6) -> list[dict]:
        return self._log[-n:]

    def summary(self, n: int = 6) -> str:
        entries = self.recent(n)
        if not entries:
            return "→  No errors recorded."
        lines = []
        for e in reversed(entries):
            mark = "[+]" if e['fixed'] else "[x]"
            lines.append(f"`{e['time']}`  {mark}  **{e['context']}** — {e['error']}")
        return "\n".join(lines)


_DIAG = MusicDiag()


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
        self.queue:      list[dict]                      = []
        self.current:    dict | None                     = None
        self.voice:      discord.VoiceClient | None      = None
        self.channel:    discord.abc.Messageable | None  = None
        self.volume:     float                           = 0.5
        self.loop:       bool                            = False
        self.fail_count: int                             = 0   # consecutive advance failures


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot     = bot
        self._ydl    = yt_dlp.YoutubeDL(YDL_OPTS)
        self._sp     = _make_spotify()
        self._states: dict[int, GuildMusic] = {}
        self._diag   = _DIAG
        print(f"[Music] Loaded. FFmpeg path: '{FFMPEG_EXE}' | Spotify: {'yes' if self._sp else 'no'}")

    async def cog_load(self):
        """Run a silent startup self-check and log any problems."""
        self.bot.loop.create_task(self._startup_check())

    async def _startup_check(self):
        await self.bot.wait_until_ready()
        problems = []

        # FFmpeg
        found = shutil.which(FFMPEG_EXE) or (os.path.isfile(FFMPEG_EXE) if FFMPEG_EXE != 'ffmpeg' else False)
        if not found:
            problems.append(f"FFmpeg not found at '{FFMPEG_EXE}'")
            self._diag.record("startup", f"FFmpeg not found at '{FFMPEG_EXE}'")

        # Spotify
        if not self._sp:
            cid = os.getenv('SPOTIFY_CLIENT_ID')
            msg = "Spotify credentials missing" if not cid else "Spotify init failed"
            problems.append(msg)
            self._diag.record("startup", msg)

        # audioop
        try:
            import audioop  # noqa
        except ImportError:
            try:
                import audioop_lts  # noqa
            except ImportError:
                problems.append("audioop missing — install audioop-lts")
                self._diag.record("startup", "audioop missing")

        # yt-dlp quick test
        try:
            def _test():
                opts = {**YDL_OPTS, 'quiet': True}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.extract_info("ytsearch1:test audio", download=False)
            await self.bot.loop.run_in_executor(None, _test)
        except Exception as e:
            problems.append(f"yt-dlp self-test failed: {e}")
            self._diag.record("startup", f"yt-dlp: {e}")

        if problems:
            print(f"[Music] Startup issues detected: {'; '.join(problems)}")
        else:
            print("[Music] Startup self-check passed.")

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
        """Search YouTube (or fetch a URL) with automatic format fallback.

        Tries each format in YDL_FORMAT_CHAIN in order. If one fails with a
        format error it logs the failure and retries the next format so the bot
        self-heals when YouTube changes available formats.
        """
        loop = self.bot.loop

        for fmt in YDL_FORMAT_CHAIN:
            opts = {**YDL_OPTS, 'format': fmt}

            def _extract(o=opts):
                try:
                    with yt_dlp.YoutubeDL(o) as ydl:
                        return ydl.extract_info(query, download=False)
                except yt_dlp.utils.DownloadError as e:
                    return ('download_error', str(e))
                except Exception as e:
                    return ('other_error', str(e))

            result = await loop.run_in_executor(None, _extract)

            # If yt-dlp returned an error tuple, log and try next format
            if isinstance(result, tuple):
                kind, msg = result
                is_format_error = 'format' in msg.lower() or 'not available' in msg.lower()
                self._diag.record(f"yt-dlp/{fmt[:20]}", msg,
                                  fixed=is_format_error and fmt != YDL_FORMAT_CHAIN[-1])
                print(f"[Music] yt-dlp error (format={fmt!r}) for '{query}': {msg}")
                if is_format_error:
                    print(f"[Music] Format error — retrying with next format in chain")
                    continue
                return None  # non-format errors won't be fixed by a different format

            if not result:
                self._diag.record("yt-dlp/no-result", f"No result for '{query}'")
                return None

            entry = result['entries'][0] if 'entries' in result else result
            stream = entry.get('url', '')
            if not stream:
                self._diag.record("yt-dlp/no-stream", f"No stream URL for '{query}'")
                print(f"[Music] No stream URL returned for '{query}'")
                continue  # try next format

            return {
                'title':    entry.get('title', 'Unknown'),
                'url':      entry.get('webpage_url') or entry.get('url', ''),
                'stream':   stream,
                'duration': entry.get('duration', 0),
                'thumb':    entry.get('thumbnail', ''),
            }

        # All formats exhausted
        self._diag.record("yt-dlp/all-formats-failed", f"'{query}'")
        print(f"[Music] All formats exhausted for '{query}'")
        return None

    # ── Playback internals ─────────────────────────────────────────────────────

    def _after_play(self, guild: discord.Guild, err):
        if err:
            print(f"[Music] Playback error in '{guild.name}': {err}")
            self._diag.record(f"playback/{guild.name}", str(err))
            state = self._state(guild.id)
            if state.channel:
                asyncio.run_coroutine_threadsafe(
                    state.channel.send(
                        embed=discord.Embed(
                            description=f"→  Playback stopped with an error: `{str(err)[:120]}`",
                            color=0xE74C3C
                        )
                    ),
                    self.bot.loop
                )
        asyncio.run_coroutine_threadsafe(self._advance(guild), self.bot.loop)

    async def _advance(self, guild: discord.Guild):
        state = self._state(guild.id)

        if state.loop and state.current:
            state.queue.insert(0, state.current)

        if not state.queue:
            state.current = None
            state.fail_count = 0
            return

        # ── Hard stop if too many consecutive failures (prevents reconnect loops) ──
        if state.fail_count >= 3:
            state.current    = None
            state.fail_count = 0
            state.queue.clear()
            self._diag.record("advance/loop-break", "Stopped after 3 consecutive failures")
            if state.channel:
                await state.channel.send(
                    embed=discord.Embed(
                        description=(
                            "→  Music stopped after 3 failed attempts.\n"
                            "→  Run `/musicfix` to diagnose, then `/play` to try again."
                        ),
                        color=0xE74C3C
                    )
                )
            return

        # ── Voice check — stop cleanly instead of reconnect-looping ──
        if state.voice is None or not state.voice.is_connected():
            state.current    = None
            state.fail_count = 0
            self._diag.record("voice/disconnected", "Queue stopped — voice client lost")
            if state.channel:
                await state.channel.send(
                    embed=discord.Embed(
                        description="→  Disconnected from voice. Join a VC and use `/play` to resume.",
                        color=0xB0C0F5
                    )
                )
            return

        track = state.queue.pop(0)
        state.current = track

        print(f"[Music] Advancing to: {track['title']}")

        # Re-fetch a fresh stream URL — don't fall back to the stale original
        fresh = await self._search(track['url'])
        if not fresh:
            # Search completely failed — tell the user specifically what went wrong
            state.fail_count += 1
            self._diag.record("advance/search-failed", track['title'])
            print(f"[Music] Search failed for '{track['title']}' (fail #{state.fail_count})")
            if state.channel:
                await state.channel.send(
                    embed=discord.Embed(
                        description=(
                            f"→  Couldn't get audio for **{track['title']}**.\n"
                            f"→  YouTube may be blocking requests — check console or run `/musicfix`."
                        ),
                        color=0xE74C3C
                    )
                )
            await self._advance(guild)
            return

        stream_url = fresh['stream']
        if not stream_url:
            state.fail_count += 1
            self._diag.record("advance/no-stream", track['title'])
            if state.channel:
                await state.channel.send(
                    embed=discord.Embed(
                        description=f"→  No stream URL for **{track['title']}** — skipping.",
                        color=0xE74C3C
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
            self._diag.record("ffmpeg/not-found", f"Not found at '{FFMPEG_EXE}'")
            state.fail_count += 1
            if state.channel:
                await state.channel.send(embed=discord.Embed(description=msg, color=0xE74C3C))
            state.current = None
            state.queue.clear()   # no point queuing more if FFmpeg is missing
            return
        except Exception as e:
            print(f"[Music] FFmpegPCMAudio error: {e}")
            self._diag.record("ffmpeg/audio-error", str(e))
            state.fail_count += 1
            if state.channel:
                await state.channel.send(
                    embed=discord.Embed(description=f"→  Audio init error: `{e}`", color=0xE74C3C)
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
            self._diag.record("voice/play-error", str(e))
            state.fail_count += 1
            if state.channel:
                await state.channel.send(
                    embed=discord.Embed(description=f"→  Playback failed: `{e}`", color=0xE74C3C)
                )
            await self._advance(guild)
            return

        # ── Success — reset failure counter and announce ──
        state.fail_count = 0
        print(f"[Music] Playing: {track['title']}")

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

        # Clean up stale/disconnected voice client (handles 4006 session errors)
        if state.voice:
            if state.voice.is_connected() and state.voice.channel == vc_channel:
                return state.voice
            try:
                await state.voice.disconnect(force=True)
            except Exception:
                pass
            state.voice = None

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

    # ── /musicfix ─────────────────────────────────────────────────────────────

    @app_commands.command(
        name="musicfix",
        description="Auto-diagnose and fix music problems, and show recent error log (Admin only)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def musicfix(self, interaction: discord.Interaction):
        """Actively attempts to fix problems, not just report them."""
        await interaction.response.defer(ephemeral=True)
        fixes   = []   # things fixed
        issues  = []   # things broken with no auto-fix
        info    = []   # neutral status lines

        # ── 1. FFmpeg ──
        ffmpeg_found = shutil.which(FFMPEG_EXE) or (
            os.path.isfile(FFMPEG_EXE) if FFMPEG_EXE != 'ffmpeg' else False
        )
        if ffmpeg_found:
            info.append(f"→  FFmpeg: found at `{FFMPEG_EXE}`")
        else:
            issues.append(
                f"→  FFmpeg **not found** at `{FFMPEG_EXE}`\n"
                f"     Install it and add to PATH, or set `FFMPEG_PATH` in `.env`.\n"
                f"     Download: https://ffmpeg.org/download.html"
            )

        # ── 2. Spotify ──
        if self._sp:
            info.append("→  Spotify: connected")
        else:
            # Attempt a re-init with current env
            new_sp = _make_spotify()
            if new_sp:
                self._sp = new_sp
                fixes.append("→  Spotify: re-initialised successfully [+]")
                self._diag.record("spotify/reinit", "Re-init succeeded", fixed=True)
            else:
                sp_id = os.getenv('SPOTIFY_CLIENT_ID')
                issues.append(
                    f"→  Spotify: {'no credentials in .env' if not sp_id else 'credentials present but init failed'}"
                )

        # ── 3. audioop ──
        try:
            import audioop  # noqa
            info.append("→  audioop: OK")
        except ImportError:
            try:
                import audioop_lts  # noqa
                info.append("→  audioop: OK (audioop-lts)")
            except ImportError:
                issues.append("→  audioop: **missing** — run `pip install audioop-lts`")

        # ── 4. Stale voice clients ──
        stale_count = 0
        for gid, state in self._states.items():
            if state.voice and not state.voice.is_connected():
                try:
                    await state.voice.disconnect(force=True)
                except Exception:
                    pass
                state.voice   = None
                state.current = None
                stale_count  += 1
                self._diag.record("voice/stale-cleared", f"guild {gid}", fixed=True)
        if stale_count:
            fixes.append(f"→  Cleared {stale_count} stale voice connection(s) [+]")
        else:
            info.append("→  Voice clients: all clean")

        # ── 5. yt-dlp format probe ──
        info.append("→  Testing yt-dlp formats...")
        working_fmt = None
        for fmt in YDL_FORMAT_CHAIN:
            opts = {**YDL_OPTS, 'format': fmt, 'quiet': True}
            def _probe(o=opts):
                try:
                    with yt_dlp.YoutubeDL(o) as ydl:
                        r = ydl.extract_info("ytsearch1:audio test", download=False)
                        entry = r['entries'][0] if 'entries' in r else r
                        return entry.get('url', '')
                except Exception as e:
                    return None
            url = await self.bot.loop.run_in_executor(None, _probe)
            if url:
                working_fmt = fmt
                break

        if working_fmt:
            if working_fmt != YDL_FORMAT_CHAIN[0]:
                # Update the live ydl instance to use the best working format
                YDL_OPTS['format'] = working_fmt
                self._ydl = yt_dlp.YoutubeDL(YDL_OPTS)
                fixes.append(f"→  yt-dlp format updated to `{working_fmt}` [+]")
                self._diag.record("yt-dlp/format-updated", working_fmt, fixed=True)
            else:
                info.append(f"→  yt-dlp: OK (format `{working_fmt}`)")
        else:
            issues.append("→  yt-dlp: **all formats failed** — YouTube may be blocking requests")

        # ── Build embed ──
        sections = []
        if fixes:
            sections.append("**Fixed automatically:**\n" + "\n".join(fixes))
        if issues:
            sections.append("**Needs attention:**\n" + "\n".join(issues))
        if info:
            sections.append("**Status:**\n" + "\n".join(info))

        # Recent error log
        log_str = self._diag.summary(6)
        sections.append(f"**Recent error log:**\n{log_str}")

        embed = discord.Embed(
            title="◉  Music Auto-Fix",
            description=f"{SEP}\n" + f"\n{SEP}\n".join(sections),
            color=0x2ECC71 if not issues else 0xE67E22
        )
        embed.set_footer(text="Run /musictest for a simpler read-only check")
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
