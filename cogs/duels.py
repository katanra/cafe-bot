import discord
from discord import app_commands
from discord.ext import commands

DUEL_WIN_GOLD = 50


class ActiveDuelView(discord.ui.View):
    def __init__(self, challenger: discord.Member, opponent: discord.Member, db, duel_id: int):
        super().__init__(timeout=None)
        self.challenger = challenger
        self.opponent   = opponent
        self.db         = db
        self.duel_id    = duel_id

    @discord.ui.button(label="🏆 I Won!", style=discord.ButtonStyle.green)
    async def claim_win(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in (self.challenger.id, self.opponent.id):
            await interaction.response.send_message("❌ You're not in this duel!", ephemeral=True)
            return
        winner = interaction.user
        loser  = self.opponent if winner.id == self.challenger.id else self.challenger
        self.db.complete_duel(self.duel_id, winner.id)
        self.db.add_gold(winner.id, DUEL_WIN_GOLD)
        for item in self.children:
            item.disabled = True
        roles_cog = interaction.client.get_cog('Roles')
        if roles_cog:
            guild = interaction.guild
            await roles_cog.update_roles(winner, guild)
            await roles_cog.update_top3_roles(guild)
        embed = discord.Embed(
            title="🏆 Duel Complete!",
            description=f"**{winner.mention}** defeated **{loser.mention}**!\n\n🪙 +**{DUEL_WIN_GOLD}** Gold awarded!",
            color=discord.Color.gold()
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🚫 Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in (self.challenger.id, self.opponent.id):
            await interaction.response.send_message("❌ You're not in this duel!", ephemeral=True)
            return
        self.db.cancel_duel_by_id(self.duel_id)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="❌ Duel cancelled.", embed=None, view=self)


class DuelChallengeView(discord.ui.View):
    def __init__(self, challenger: discord.Member, opponent: discord.Member, db, duel_id: int):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent   = opponent
        self.db         = db
        self.duel_id    = duel_id

    @discord.ui.button(label="⚔️ Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("❌ This challenge isn't for you!", ephemeral=True)
            return
        self.db.accept_duel(self.duel_id)
        for item in self.children:
            item.disabled = True
        embed = discord.Embed(
            title="⚔️ Duel in Progress!",
            description=(
                f"{self.challenger.mention} **vs** {self.opponent.mention}\n\n"
                f"When the duel is over, the winner clicks **I Won!**\n"
                f"🏆 Prize: **{DUEL_WIN_GOLD}** 🪙 Gold"
            ),
            color=discord.Color.orange()
        )
        active_view = ActiveDuelView(self.challenger, self.opponent, self.db, self.duel_id)
        await interaction.response.edit_message(embed=embed, view=active_view)

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("❌ This challenge isn't for you!", ephemeral=True)
            return
        self.db.cancel_duel_by_id(self.duel_id)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"❌ {self.opponent.mention} declined the duel.", embed=None, view=self
        )

    async def on_timeout(self):
        self.db.cancel_duel_by_id(self.duel_id)
        for item in self.children:
            item.disabled = True


class Duels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="duel", description="Challenge someone to a duel for gold!")
    async def duel(self, interaction: discord.Interaction, opponent: discord.Member):
        if opponent.id == interaction.user.id:
            await interaction.response.send_message("❌ You can't duel yourself!", ephemeral=True)
            return
        if opponent.bot:
            await interaction.response.send_message("❌ You can't duel a bot!", ephemeral=True)
            return

        duel_id = self.bot.db.create_duel(interaction.user.id, opponent.id, interaction.channel_id)
        embed = discord.Embed(
            title="⚔️ Duel Challenge!",
            description=(
                f"{interaction.user.mention} has challenged {opponent.mention} to a duel!\n\n"
                f"🏆 Winner earns **{DUEL_WIN_GOLD}** 🪙 Gold\n\n"
                f"{opponent.mention}, do you accept?"
            ),
            color=discord.Color.red()
        )
        view = DuelChallengeView(interaction.user, opponent, self.bot.db, duel_id)
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Duels(bot))
