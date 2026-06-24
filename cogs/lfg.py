import discord
from discord import app_commands
from discord.ext import commands

SEP = ("· " * 14).strip()


class LFG(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # {message_id: poster_id} — tracks which messages are LFG posts
        self.lfg_posts: dict[int, int] = {}

    @app_commands.command(name="lfg", description="Post a Looking For Group listing")
    @app_commands.describe(
        game="The game you're looking to play",
        description="What you're looking for",
        slots="How many extra players you need (optional)"
    )
    async def lfg(
        self,
        interaction: discord.Interaction,
        game: str,
        description: str,
        slots: int = 0
    ):
        slot_line = f"\n→  **Slots needed:** {slots}" if slots > 0 else ""
        embed = discord.Embed(
            title="◉  Looking For Group",
            description=(
                f"*{game}*\n"
                f"{SEP}\n"
                f"{description}"
                f"{slot_line}\n"
                f"{SEP}\n"
                f"→  Posted by {interaction.user.mention}"
            ),
            color=0xB0C0F5
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="React ✅ to be moved into the host's voice channel.")
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        await msg.add_reaction("✅")
        # Remember this message so the reaction listener can handle it
        self.lfg_posts[msg.id] = interaction.user.id

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Only care about ✅ on tracked LFG posts
        if str(payload.emoji) != "✅":
            return
        if payload.message_id not in self.lfg_posts:
            return
        if payload.user_id == self.bot.user.id:
            return  # ignore the bot's own reaction

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        reactor = guild.get_member(payload.user_id)
        if not reactor or reactor.bot:
            return

        poster_id    = self.lfg_posts[payload.message_id]
        text_channel = guild.get_channel(payload.channel_id)

        # Don't try to move the poster when they react to their own post
        if reactor.id == poster_id:
            return

        poster = guild.get_member(poster_id)

        # Poster isn't in a VC right now
        if not poster or not poster.voice or not poster.voice.channel:
            if text_channel:
                await text_channel.send(
                    f"→ {reactor.mention} The LFG host isn't in a voice channel right now.",
                    delete_after=8
                )
            return

        target_vc = poster.voice.channel

        # Reactor needs to be in a VC first — Discord doesn't allow force-joining
        if not reactor.voice or not reactor.voice.channel:
            try:
                await reactor.send(
                    f"→ Join any voice channel first, then react again "
                    f"to be moved to **{target_vc.name}**!"
                )
            except discord.Forbidden:
                if text_channel:
                    await text_channel.send(
                        f"→ {reactor.mention} Join a voice channel first, "
                        f"then react again to be moved to {target_vc.mention}!",
                        delete_after=10
                    )
            return

        # Already in the right channel — nothing to do
        if reactor.voice.channel.id == target_vc.id:
            return

        # Move them to the host's channel
        try:
            await reactor.move_to(target_vc)
        except discord.Forbidden:
            if text_channel:
                await text_channel.send(
                    f"→ {reactor.mention} I don't have permission to move you "
                    f"to {target_vc.mention}.",
                    delete_after=8
                )
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(LFG(bot))
