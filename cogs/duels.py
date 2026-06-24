import discord
from discord import app_commands
from discord.ext import commands
import datetime
import time

DUEL_WIN_GOLD      = 50
SEP                = ("· " * 14).strip()
DUEL_MOD_ROLE      = "Duel Mod"
DUEL_LOG_CHANNEL   = "duel-log"
DUEL_COOLDOWN_SECS = 30 * 60
MAX_DAILY_WINS     = 10

DUEL_RANK_TITLES = {
    1: "Champion",
    2: "Contender",
    3: "Challenger",
}


def duel_rank_label(rank: int) -> str:
    """Returns a formatted rank label like '◉ Champion' or '#4'."""
    if rank == 0:
        return "Unranked"
    title = DUEL_RANK_TITLES.get(rank)
    return f"◉  {title}" if title else f"#{rank}"


DUEL_RULES = [
    ("→  Character",    "Both players must play as **Wraith**. No other legend allowed."),
    ("→  Abilities",    "No **Tactical** or **Ultimate** abilities during the duel. Passive is fine."),
    ("→  Weapons",      "Loadout agreed before the match — **no takebacks**.\nBanned: Care Package weapons (Kraber, Bocek, etc.) and weapons with upgrade abilities (e.g. Double Tap Alternator)."),
    ("→  Gear",         "Both players must have a **Purple (Level 3) Evo Shield** equipped."),
    ("→  Format",       "**First to 9 kills** wins. Match takes place in **The PIT** in the Firing Range."),
    ("→  Screen Share", "At least one player must share their screen in a **server Voice Channel**. If neither can share, the duel is **void**."),
    ("→  Disconnects",  "If a player disconnects and does not return within **10 minutes**, they **forfeit** the match."),
    ("→  Account",      "Account must be **Level 100+**. Smurf accounts are **banned** and result in disqualification."),
    ("→  Confirmation", "The winner is confirmed **only by a Duel Mod** watching the screen share. Players cannot self-report."),
]


class ActiveDuelView(discord.ui.View):
    """Duel Mods (or server admins if no Duel Mod role exists) confirm the winner."""

    def __init__(self, challenger: discord.Member, opponent: discord.Member, db, duel_id: int):
        super().__init__(timeout=None)
        self.challenger = challenger
        self.opponent   = opponent
        self.db         = db
        self.duel_id    = duel_id

        self.children[0].label = f"◉ {challenger.display_name} Wins"
        self.children[1].label = f"◉ {opponent.display_name} Wins"

    def _is_duel_mod(self, interaction: discord.Interaction) -> bool:
        role = discord.utils.get(interaction.guild.roles, name=DUEL_MOD_ROLE)
        if role:
            return role in interaction.user.roles
        # No Duel Mod role set up — fall back to Manage Server permission
        if isinstance(interaction.user, discord.Member):
            return interaction.user.guild_permissions.manage_guild
        return False

    async def _resolve(self, interaction: discord.Interaction, winner: discord.Member, loser: discord.Member):
        today_wins = interaction.client.db.get_daily_wins(winner.id)
        gold_msg = ""
        if today_wins < MAX_DAILY_WINS:
            self.db.add_gold(winner.id, DUEL_WIN_GOLD)
            gold_msg = f"\n→  +**{DUEL_WIN_GOLD}** Gold awarded!"
        else:
            gold_msg = f"\n→  Daily win cap ({MAX_DAILY_WINS}) reached — no gold this time."

        self.db.complete_duel(self.duel_id, winner.id)

        for item in self.children:
            item.disabled = True

        roles_cog = interaction.client.get_cog('Roles')
        if roles_cog:
            await roles_cog.update_roles(winner, interaction.guild)
            await roles_cog.update_top3_roles(interaction.guild)

        embed = discord.Embed(
            title="◉  Duel Complete",
            description=(
                f"*the dust has settled*\n"
                f"{SEP}\n"
                f"→  **{winner.mention}** defeated **{loser.mention}**"
                f"{gold_msg}\n"
                f"{SEP}\n"
                f"→  *Confirmed by {interaction.user.mention}*"
            ),
            color=0xB0C0F5
        )
        await interaction.response.edit_message(embed=embed, view=self)

        log_channel = discord.utils.get(interaction.guild.text_channels, name=DUEL_LOG_CHANNEL)
        if log_channel:
            log_embed = discord.Embed(
                title="◉  Duel Result",
                description=(
                    f"*match record*\n"
                    f"{SEP}\n"
                    f"→  **Winner:** {winner.mention}\n"
                    f"→  **Loser:** {loser.mention}\n"
                    f"→  **Gold awarded:** {'Yes' if today_wins < MAX_DAILY_WINS else 'No — daily cap reached'}\n"
                    f"→  **Confirmed by:** {interaction.user.mention}"
                ),
                color=0xB0C0F5,
                timestamp=datetime.datetime.utcnow()
            )
            await log_channel.send(embed=log_embed)

    @discord.ui.button(label="◉ Challenger Wins", style=discord.ButtonStyle.primary, row=0)
    async def challenger_wins(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._is_duel_mod(interaction):
            await interaction.response.send_message(
                f"→ Only **{DUEL_MOD_ROLE}**s (or server admins) can confirm the winner!", ephemeral=True
            )
            return
        await self._resolve(interaction, self.challenger, self.opponent)

    @discord.ui.button(label="◉ Opponent Wins", style=discord.ButtonStyle.primary, row=0)
    async def opponent_wins(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._is_duel_mod(interaction):
            await interaction.response.send_message(
                f"→ Only **{DUEL_MOD_ROLE}**s (or server admins) can confirm the winner!", ephemeral=True
            )
            return
        await self._resolve(interaction, self.opponent, self.challenger)

    @discord.ui.button(label="No Contest", style=discord.ButtonStyle.secondary, row=1)
    async def no_contest(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._is_duel_mod(interaction):
            await interaction.response.send_message(
                f"→ Only **{DUEL_MOD_ROLE}**s (or server admins) can cancel a duel!", ephemeral=True
            )
            return
        self.db.cancel_duel_by_id(self.duel_id)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"→ Duel ruled **No Contest** by {interaction.user.mention}.",
            embed=None, view=self
        )


class DuelChallengeView(discord.ui.View):
    def __init__(self, challenger: discord.Member, opponent: discord.Member, db, duel_id: int):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent   = opponent
        self.db         = db
        self.duel_id    = duel_id
        self.message: discord.Message | None = None  # set after send

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.primary)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("→ This challenge isn't for you!", ephemeral=True)
            return
        self.db.accept_duel(self.duel_id)
        self.stop()
        for item in self.children:
            item.disabled = True

        embed = discord.Embed(
            title="◉  Duel in Progress",
            description=(
                f"*may the best player win*\n"
                f"{SEP}\n"
                f"→  {self.challenger.mention}  **vs**  {self.opponent.mention}\n"
                f"→  Prize: **{DUEL_WIN_GOLD} gold** to the winner\n"
                f"{SEP}\n"
                f"**→  Rules reminder**\n"
                f"→  Wraith only — no Tactical or Ultimate\n"
                f"→  Purple Evo Shield required\n"
                f"→  No Care Package or upgrade-ability weapons\n"
                f"→  First to 9 kills in The PIT\n"
                f"→  One player must share screen in VC\n"
                f"{SEP}\n"
                f"*A* ***{DUEL_MOD_ROLE}*** *(or admin) must confirm the winner below.*"
            ),
            color=0xB0C0F5
        )
        active_view = ActiveDuelView(self.challenger, self.opponent, self.db, self.duel_id)
        await interaction.response.edit_message(embed=embed, view=active_view)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("→ This challenge isn't for you!", ephemeral=True)
            return
        self.db.cancel_duel_by_id(self.duel_id)
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"→ {self.opponent.mention} declined the duel.", embed=None, view=self
        )

    async def on_timeout(self):
        self.db.cancel_duel_by_id(self.duel_id)
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(
                    content=f"→ Duel challenge expired — {self.opponent.mention} didn't respond in time.",
                    embed=None, view=self
                )
            except Exception:
                pass


class Duels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_duel:     dict[int, float] = {}
        self._last_opponent: dict[int, int]   = {}

    @app_commands.command(name="duel", description="Challenge someone to a duel for gold!")
    @app_commands.describe(opponent="The server member you want to challenge")
    async def duel(self, interaction: discord.Interaction, opponent: discord.Member):
        if not interaction.guild:
            await interaction.response.send_message("→ This command only works in a server.", ephemeral=True)
            return

        challenger = interaction.user

        if opponent.id == challenger.id:
            await interaction.response.send_message("→ You can't duel yourself!", ephemeral=True)
            return
        if opponent.bot:
            await interaction.response.send_message("→ You can't duel a bot!", ephemeral=True)
            return

        last = self._last_duel.get(challenger.id, 0)
        elapsed = time.time() - last
        if elapsed < DUEL_COOLDOWN_SECS:
            remaining = int(DUEL_COOLDOWN_SECS - elapsed)
            m, s = remaining // 60, remaining % 60
            await interaction.response.send_message(
                f"→ Wait **{m}m {s}s** before starting another duel.",
                ephemeral=True
            )
            return

        if self._last_opponent.get(challenger.id) == opponent.id:
            await interaction.response.send_message(
                f"→ You can't challenge **{opponent.display_name}** again back-to-back. Challenge someone else first!",
                ephemeral=True
            )
            return

        self._last_duel[challenger.id]     = time.time()
        self._last_opponent[challenger.id] = opponent.id

        duel_id = self.bot.db.create_duel(challenger.id, opponent.id, interaction.channel_id)

        mod_role = discord.utils.get(interaction.guild.roles, name=DUEL_MOD_ROLE)
        mod_ping = mod_role.mention if mod_role else ""

        c_rank  = self.bot.db.get_duel_rank(challenger.id)
        o_rank  = self.bot.db.get_duel_rank(opponent.id)
        c_label = f"  `{duel_rank_label(c_rank)}`" if c_rank > 0 else ""
        o_label = f"  `{duel_rank_label(o_rank)}`" if o_rank > 0 else ""

        embed = discord.Embed(
            title="◉  Duel Challenge",
            description=(
                f"*a challenge has been issued*\n"
                f"{SEP}\n"
                f"→  {challenger.mention}{c_label} has challenged {opponent.mention}{o_label}\n"
                f"→  Winner earns **{DUEL_WIN_GOLD} gold**\n"
                f"→  A **{DUEL_MOD_ROLE}** (or admin) will confirm the winner\n"
                f"{SEP}\n"
                f"*{opponent.mention}, do you accept?*"
            ),
            color=0xB0C0F5
        )
        view    = DuelChallengeView(challenger, opponent, self.bot.db, duel_id)
        content = f"{mod_ping} Duel requested — please be ready to spectate!" if mod_ping else None
        await interaction.response.send_message(content=content, embed=embed, view=view)
        # Store message ref so on_timeout can edit it
        view.message = await interaction.original_response()

    @duel.error
    async def duel_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        import traceback
        original = getattr(error, 'original', error)
        tb = ''.join(traceback.format_exception(type(original), original, original.__traceback__))
        print(f"[Duel Error]\n{tb}")
        msg = f"❌ **Duel error** (copy this and send it):\n```\n{type(original).__name__}: {original}\n```"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass

    @app_commands.command(name="duelrules", description="Show the official 1v1 duel rules")
    async def duelrules(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="◉  Official Duel Rules",
            description=f"*Apex Legends 1v1 — Firing Range*\n{SEP}",
            color=0xB0C0F5
        )
        for name, value in DUEL_RULES:
            embed.add_field(name=name, value=f"→  {value}", inline=False)
        embed.set_footer(text="Breaking any rule results in disqualification. Duel Mods have final say.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="duelboard", description="Show the duel wins leaderboard")
    async def duelboard(self, interaction: discord.Interaction):
        await interaction.response.defer()
        data = self.bot.db.get_duel_leaderboard(10)

        if not data:
            await interaction.followup.send("No duels have been completed yet!")
            return

        lines = []
        for i, row in enumerate(data):
            member = interaction.guild.get_member(row['winner_id'])
            name   = member.display_name if member else f"User {row['winner_id']}"
            rank   = i + 1
            title  = DUEL_RANK_TITLES.get(rank)
            prefix = f"**{title}**  {name}" if title else f"#{rank}  {name}"
            lines.append(f"→  {prefix} — **{row['wins']}** wins")

        embed = discord.Embed(
            title="◉  Duel Leaderboard",
            description=f"*top duelists*\n{SEP}\n" + "\n".join(lines),
            color=0xB0C0F5
        )
        embed.set_footer(text="Gold earned from duels  ·  Top 3 earn server roles")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="duelvoid", description="Void an active duel by ID (Duel Mod only)")
    @app_commands.describe(duel_id="The duel ID to void")
    async def duelvoid(self, interaction: discord.Interaction, duel_id: int):
        mod_role = discord.utils.get(interaction.guild.roles, name=DUEL_MOD_ROLE)
        # Allow Duel Mod role OR Manage Server permission
        has_access = (mod_role and mod_role in interaction.user.roles) or \
                     interaction.user.guild_permissions.manage_guild
        if not has_access:
            await interaction.response.send_message(
                f"→ Only **{DUEL_MOD_ROLE}**s or server admins can void duels.", ephemeral=True
            )
            return
        self.bot.db.cancel_duel_by_id(duel_id)
        await interaction.response.send_message(
            f"→ Duel **#{duel_id}** has been voided.", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Duels(bot))
