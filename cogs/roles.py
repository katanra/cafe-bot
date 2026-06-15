import discord
from discord import app_commands
from discord.ext import commands

GOLD_ROLES = [("Warlord",10000),("Legend",5000),("Champion",1000),("Knight",500),("Squire",100),("Peasant",0)]
XP_ROLES   = [("Elder",5000),("Veteran",1000),("Regular",500),("Chatter",100),("Lurker",0)]
TOP_ROLES  = {1:"👑 Gold Champion", 2:"🥈 Silver Duelist", 3:"🥉 Bronze Fighter"}

class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_or_create_role(self, guild, name):
        role = discord.utils.get(guild.roles, name=name)
        if not role:
            try:
                role = await guild.create_role(name=name, reason="Cafe Bot auto-role")
            except discord.Forbidden:
                return None
        return role

    async def update_roles(self, member, guild):
        user = self.bot.db.get_user(member.id)
        gold, xp = user['gold'], user['xp']

        # Gold roles — remove all, then assign correct one
        for name, _ in GOLD_ROLES:
            r = discord.utils.get(guild.roles, name=name)
            if r and r in member.roles:
                try: await member.remove_roles(r)
                except: pass
        for name, threshold in GOLD_ROLES:
            if gold >= threshold:
                r = await self.get_or_create_role(guild, name)
                if r:
                    try: await member.add_roles(r)
                    except: pass
                break

        # XP roles — same pattern
        for name, _ in XP_ROLES:
            r = discord.utils.get(guild.roles, name=name)
            if r and r in member.roles:
                try: await member.remove_roles(r)
                except: pass
        for name, threshold in XP_ROLES:
            if xp >= threshold:
                r = await self.get_or_create_role(guild, name)
                if r:
                    try: await member.add_roles(r)
                    except: pass
                break

    async def update_top3_roles(self, guild):
        for name in TOP_ROLES.values():
            r = discord.utils.get(guild.roles, name=name)
            if r:
                for m in r.members:
                    try: await m.remove_roles(r)
                    except: pass
        top3 = self.bot.db.get_leaderboard('gold', 3)
        for i, row in enumerate(top3, 1):
            if row['gold'] == 0:
                continue
            m = guild.get_member(row['user_id'])
            if m:
                r = await self.get_or_create_role(guild, TOP_ROLES[i])
                if r:
                    try: await m.add_roles(r)
                    except: pass

    @app_commands.command(name="updateroles", description="Force-refresh all member roles (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def updateroles(self, interaction: discord.Interaction):
        await interaction.response.defer()
        count = 0
        for m in interaction.guild.members:
            if not m.bot:
                await self.update_roles(m, interaction.guild)
                count += 1
        await self.update_top3_roles(interaction.guild)
        await interaction.followup.send(f"✅ Updated roles for **{count}** members!")

    @updateroles.error
    async def updateroles_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You need Administrator permission!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Roles(bot))
