import discord
from discord import app_commands
from discord.ext import commands

SEP = ("· " * 14).strip()

# Only the top 2 duel ranks get roles
DUEL_TOP_ROLES = {
    1: "Duel Champion",
    2: "Duel Contender",
}


class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _get_or_create_role(self, guild: discord.Guild, name: str) -> discord.Role | None:
        role = discord.utils.get(guild.roles, name=name)
        if not role:
            try:
                role = await guild.create_role(name=name, reason="Café Bot duel role")
            except discord.Forbidden:
                return None
        return role

    async def update_roles(self, member: discord.Member, guild: discord.Guild):
        """No-op — XP roles have been removed."""
        pass

    async def update_top_duel_roles(self, guild: discord.Guild):
        """Assign Duel Champion / Duel Contender to the current top 2 duelists."""
        if not guild.me.guild_permissions.manage_roles:
            return

        # Strip all duel roles from everyone first
        for role_name in DUEL_TOP_ROLES.values():
            role = discord.utils.get(guild.roles, name=role_name)
            if not role:
                continue
            for member in list(role.members):
                try:
                    await member.remove_roles(role, reason="Duel top-2 reset")
                except discord.Forbidden:
                    pass

        # Assign to new top 2
        top2 = self.bot.db.get_duel_leaderboard(2)
        for i, row in enumerate(top2, 1):
            if row['wins'] == 0:
                continue
            role_name = DUEL_TOP_ROLES.get(i)
            if not role_name:
                continue
            role = await self._get_or_create_role(guild, role_name)
            if not role:
                continue
            member = guild.get_member(row['winner_id'])
            if member:
                try:
                    await member.add_roles(role, reason=f"Duel rank #{i}")
                except discord.Forbidden:
                    pass

    # Keep backward-compat name used in duels.py
    async def update_top3_roles(self, guild: discord.Guild):
        await self.update_top_duel_roles(guild)

    @app_commands.command(name="updateroles", description="Refresh duel rank roles (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def updateroles(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.update_top_duel_roles(interaction.guild)
        embed = discord.Embed(
            description="→  Duel rank roles refreshed.",
            color=0xB0C0F5
        )
        await interaction.followup.send(embed=embed)

    @updateroles.error
    async def updateroles_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("→ Administrator permission required.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Roles(bot))
