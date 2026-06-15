import discord
from discord import app_commands
from discord.ext import commands

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="balance", description="Check your Gold and XP balance")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        user = self.bot.db.get_user(target.id)
        embed = discord.Embed(title=f"💰 {target.display_name}'s Wallet", color=discord.Color.gold())
        embed.add_field(name="🪙 Gold", value=f"**{user['gold']:,}**", inline=True)
        embed.add_field(name="⭐ XP",   value=f"**{user['xp']:,}**",   inline=True)
        embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="give", description="Give gold to a member (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def give(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
            return
        self.bot.db.add_gold(member.id, amount)
        await interaction.response.send_message(f"✅ Gave **{amount:,}** 🪙 to {member.mention}")

    @app_commands.command(name="take", description="Take gold from a member (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def take(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
            return
        self.bot.db.remove_gold(member.id, amount)
        await interaction.response.send_message(f"✅ Took **{amount:,}** 🪙 from {member.mention}")

    @app_commands.command(name="addxp", description="Add XP to a member (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def addxp(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
            return
        self.bot.db.add_xp(member.id, amount)
        await interaction.response.send_message(f"✅ Gave **{amount:,}** ⭐ XP to {member.mention}")

    @give.error
    @take.error
    @addxp.error
    async def admin_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You need Administrator permission!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Economy(bot))
