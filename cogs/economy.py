import discord
from discord import app_commands
from discord.ext import commands

SEP = "─" * 28

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="balance", description="Check your Gold and XP balance")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        user   = self.bot.db.get_user(target.id)
        embed  = discord.Embed(
            title=f"☕  {target.display_name}",
            description=f"*Café standing & earnings*\n{SEP}",
            color=0x3B1F0E
        )
        embed.add_field(name="◆  Gold",  value=f"**{user['gold']:,}** coins",  inline=True)
        embed.add_field(name="◆  XP",    value=f"**{user['xp']:,}** points",   inline=True)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text="Gold is earned through duels only.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="give", description="Give gold to a member (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def give(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("✦ Amount must be positive.", ephemeral=True)
            return
        self.bot.db.add_gold(member.id, amount)
        embed = discord.Embed(
            description=f"✦  **{amount:,}** gold awarded to {member.mention}.",
            color=0xBA7517
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="take", description="Take gold from a member (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def take(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("✦ Amount must be positive.", ephemeral=True)
            return
        self.bot.db.remove_gold(member.id, amount)
        embed = discord.Embed(
            description=f"◆  **{amount:,}** gold removed from {member.mention}.",
            color=0x3B1F0E
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="addxp", description="Add XP to a member (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def addxp(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("✦ Amount must be positive.", ephemeral=True)
            return
        self.bot.db.add_xp(member.id, amount)
        embed = discord.Embed(
            description=f"✦  **{amount:,}** XP awarded to {member.mention}.",
            color=0x3B6D11
        )
        await interaction.response.send_message(embed=embed)

    @give.error
    @take.error
    @addxp.error
    async def admin_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("◆ Administrator permission required.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Economy(bot))
