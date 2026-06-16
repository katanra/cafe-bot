import discord
from discord import app_commands
from discord.ext import commands

SEP = ("· " * 14).strip()

# ── XP role tiers ─────────────────────────────────────────────────────────────
# (min XP, role name) — highest qualifying tier is assigned, others removed.
# Roles are auto-created in your server if they don't exist yet.
XP_ROLES = [
    (10000, "Legend"),
    (5000,  "Elder"),
    (2000,  "Veteran"),
    (500,   "Regular"),
    (0,     "Newcomer"),
]

# ── Duel top-3 roles ──────────────────────────────────────────────────────────
# Assigned to the current top 3 on the duel leaderboard after every confirmed win.
DUEL_TOP_ROLES = {
    1: "Duel Champion",
    2: "Duel Contender",
    3: "Duel Challenger",
}


class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get_or_create_role(self, guild: discord.Guild, name: str) -> discord.Role | None:
        """Return existing role by name, or create it if missing."""
        role = discord.utils.get(guild.roles, name=name)
        if not role:
            try:
                role = await guild.create_role(name=name, reason="Café Bot auto-role")
            except discord.Forbidden:
                return None
        return role

    # ── Called by bot.py, rewards.py, duels.py ───────────────────────────────

    async def update_roles(self, member: discord.Member, guild: discord.Guild):
        """Assign the correct XP tier role to a member, removing the rest."""
        if not guild.me.guild_permissions.manage_roles:
            return

        user = self.bot.db.get_user(member.id)
        xp   = user.get('xp', 0)

        # Find highest qualifying tier
        earned_name = None
        for min_xp, role_name in XP_ROLES:
            if xp >= min_xp:
                earned_name = role_name
                break

        for min_xp, role_name in XP_ROLES:
            role = await self._get_or_create_role(guild, role_name)
            if not role:
                continue
            has_role    = role in member.roles
            should_have = (role_name == earned_name)
            try:
                if should_have and not has_role:
                    await member.add_roles(role, reason="XP tier update")
                elif not should_have and has_role:
                    await member.remove_roles(role, reason="XP tier update")
            except discord.Forbidden:
                pass

    async def update_top3_roles(self, guild: discord.Guild):
        """Assign Duel Champion / Contender / Challenger to current top 3 duelists."""
        if not guild.me.guild_permissions.manage_roles:
            return

        # Strip all duel top roles from everyone first
        for role_name in DUEL_TOP_ROLES.values():
            role = discord.utils.get(guild.roles, name=role_name)
            if not role:
                continue
            for member in list(role.members):
                try:
                    await member.remove_roles(role, reason="Duel top-3 reset")
                except discord.Forbidden:
                    pass

        # Assign to new top 3
        top3 = self.bot.db.get_duel_leaderboard(3)
        for i, row in enumerate(top3[:3], 1):
            if row['wins'] == 0:
                continue
            role = await self._get_or_create_role(guild, DUEL_TOP_ROLES[i])
            if not role:
                continue
            member = guild.get_member(row['winner_id'])
            if member:
                try:
                    await member.add_roles(role, reason="Duel top-3 update")
                except discord.Forbidden:
                    pass

    # ── /roles ────────────────────────────────────────────────────────────────

    @app_commands.command(name="roles", description="Show XP role tiers and your current standing")
    async def roles(self, interaction: discord.Interaction):
        user = self.bot.db.get_user(interaction.user.id)
        xp   = user.get('xp', 0)

        earned_name = None
        for min_xp, role_name in XP_ROLES:
            if xp >= min_xp:
                earned_name = role_name
                break

        lines = []
        for min_xp, role_name in reversed(XP_ROLES):
            marker = "  ◉  *you are here*" if role_name == earned_name else ""
            lines.append(f"→  **{role_name}** — {min_xp:,} XP{marker}")

        # Next tier info
        next_tier = None
        for min_xp, role_name in reversed(XP_ROLES):
            if xp < min_xp:
                next_tier = (min_xp, role_name)

        footer = "Roles are assigned automatically as you earn XP."
        if next_tier:
            needed = next_tier[0] - xp
            footer += f"  ·  {needed:,} XP until {next_tier[1]}."

        embed = discord.Embed(
            title="◉  XP Roles",
            description=f"*Earn XP through chat, VC time, and daily rewards*\n{SEP}\n" + "\n".join(lines),
            color=0xB0C0F5
        )
        embed.add_field(name="→  Your XP",      value=f"**{xp:,}** points",         inline=True)
        embed.add_field(name="→  Current Role",  value=f"**{earned_name or 'None'}**", inline=True)
        embed.set_footer(text=footer)
        await interaction.response.send_message(embed=embed)

    # ── /updateroles ──────────────────────────────────────────────────────────

    @app_commands.command(name="updateroles", description="Force-refresh all member roles (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def updateroles(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count = 0
        for member in interaction.guild.members:
            if not member.bot:
                await self.update_roles(member, interaction.guild)
                count += 1
        await self.update_top3_roles(interaction.guild)
        embed = discord.Embed(
            description=f"→  Roles refreshed for **{count}** members.",
            color=0xB0C0F5
        )
        await interaction.followup.send(embed=embed)

    @updateroles.error
    async def updateroles_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("→ Administrator permission required.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Roles(bot))
