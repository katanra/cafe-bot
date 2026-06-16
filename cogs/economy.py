import discord
from discord import app_commands
from discord.ext import commands

SEP = ("· " * 14).strip()

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="balance", description="Check your Gold and XP balance")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        target    = member or interaction.user
        user      = self.bot.db.get_user(target.id)
        gold_rank = self.bot.db.get_gold_rank(target.id)
        xp_rank   = self.bot.db.get_xp_rank(target.id)

        gold_value = f"**{user['gold']:,}** coins"
        if gold_rank > 0:
            gold_value += f"  —  Rank **#{gold_rank}**"

        embed = discord.Embed(
            title=f"◉  {target.display_name}",
            description=f"*café standing & earnings*\n{SEP}",
            color=0xB0C0F5
        )
        embed.add_field(name="→  Gold",  value=gold_value,                                            inline=True)
        embed.add_field(name="→  XP",    value=f"**{user['xp']:,}** points  —  Rank **#{xp_rank}**", inline=True)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text="Gold is earned through duels only.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="give", description="Give gold to a member (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def give(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("→ Amount must be positive.", ephemeral=True)
            return
        self.bot.db.add_gold(member.id, amount)
        embed = discord.Embed(
            description=f"→  **{amount:,}** gold awarded to {member.mention}.",
            color=0xB0C0F5
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="take", description="Take gold from a member (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def take(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("→ Amount must be positive.", ephemeral=True)
            return
        self.bot.db.remove_gold(member.id, amount)
        embed = discord.Embed(
            description=f"→  **{amount:,}** gold removed from {member.mention}.",
            color=0xB0C0F5
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="addxp", description="Add XP to a member (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def addxp(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("→ Amount must be positive.", ephemeral=True)
            return
        self.bot.db.add_xp(member.id, amount)
        embed = discord.Embed(
            description=f"→  **{amount:,}** XP awarded to {member.mention}.",
            color=0xB0C0F5
        )
        await interaction.response.send_message(embed=embed)

    @give.error
    @take.error
    @addxp.error
    async def admin_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("→ Administrator permission required.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Economy(bot))
