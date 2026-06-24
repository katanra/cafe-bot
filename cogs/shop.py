import discord
from discord import app_commands
from discord.ext import commands

SEP = ("· " * 14).strip()

# ── Shop items ────────────────────────────────────────────────────────────────
# Each item: (display_name, cost, description, item_id)
SHOP_ITEMS = [
    {
        "id":    "xp_boost",
        "name":  "XP Boost",
        "cost":  250,
        "desc":  "Instantly gain **300 XP**.",
        "emoji": "⚡",
    },
    {
        "id":    "big_xp_boost",
        "name":  "Big XP Boost",
        "cost":  600,
        "desc":  "Instantly gain **800 XP**.",
        "emoji": "🚀",
    },
    {
        "id":    "duel_reset",
        "name":  "Duel Reset",
        "cost":  300,
        "desc":  "Skip your 30-minute duel cooldown once.",
        "emoji": "⏱️",
    },
    {
        "id":    "lucky_daily",
        "name":  "Lucky Daily",
        "cost":  400,
        "desc":  "Your next `/daily` gives **double XP**.",
        "emoji": "🍀",
    },
]

ITEM_MAP = {item["id"]: item for item in SHOP_ITEMS}

# Track per-user active buffs in memory (resets on bot restart — intentional, keeps it simple)
# {user_id: set of active buff item_ids}
_active_buffs: dict[int, set] = {}


def has_buff(user_id: int, item_id: str) -> bool:
    return item_id in _active_buffs.get(user_id, set())


def add_buff(user_id: int, item_id: str):
    _active_buffs.setdefault(user_id, set()).add(item_id)


def consume_buff(user_id: int, item_id: str):
    if user_id in _active_buffs:
        _active_buffs[user_id].discard(item_id)


class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="shop", description="Browse the gold shop")
    async def shop(self, interaction: discord.Interaction):
        user = self.bot.db.get_user(interaction.user.id)
        gold = user.get('gold', 0)

        lines = []
        for item in SHOP_ITEMS:
            affordable = "✓" if gold >= item["cost"] else "✗"
            lines.append(
                f"{item['emoji']}  **{item['name']}** — {item['cost']:,} gold  `{affordable}`\n"
                f"      {item['desc']}"
            )

        embed = discord.Embed(
            title="◉  Gold Shop",
            description=(
                f"*spend your winnings*\n"
                f"{SEP}\n"
                + f"\n{SEP}\n".join(lines) +
                f"\n{SEP}\n"
                f"→  Your balance: **{gold:,}** gold"
            ),
            color=0xB0C0F5
        )
        embed.set_footer(text="Use /buy <item> to purchase  ·  Gold is earned from duel wins")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="buy", description="Buy an item from the shop")
    @app_commands.describe(item="Which item to buy")
    @app_commands.choices(item=[
        app_commands.Choice(name=f"{i['emoji']} {i['name']} — {i['cost']} gold", value=i["id"])
        for i in SHOP_ITEMS
    ])
    async def buy(self, interaction: discord.Interaction, item: str):
        shop_item = ITEM_MAP.get(item)
        if not shop_item:
            await interaction.response.send_message("❌ Unknown item.", ephemeral=True)
            return

        # Check and deduct gold
        success = self.bot.db.spend_gold(interaction.user.id, shop_item["cost"])
        if not success:
            user = self.bot.db.get_user(interaction.user.id)
            short = shop_item["cost"] - user["gold"]
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=(
                        f"→  Not enough gold.\n"
                        f"→  You need **{short:,}** more — win a duel!"
                    ),
                    color=0xB0C0F5
                ),
                ephemeral=True
            )
            return

        # Apply item effect
        result_line = ""

        if item == "xp_boost":
            self.bot.db.add_xp(interaction.user.id, 300)
            result_line = "→  **+300 XP** added to your account."

        elif item == "big_xp_boost":
            self.bot.db.add_xp(interaction.user.id, 800)
            result_line = "→  **+800 XP** added to your account."

        elif item == "duel_reset":
            # Signal the duels cog to clear this user's cooldown
            duels_cog = self.bot.get_cog('Duels')
            if duels_cog and interaction.user.id in duels_cog._last_duel:
                duels_cog._last_duel[interaction.user.id] = 0
            result_line = "→  Duel cooldown cleared. Challenge someone now!"

        elif item == "lucky_daily":
            add_buff(interaction.user.id, "lucky_daily")
            result_line = "→  Your next `/daily` will give double XP!"

        # Update XP roles if needed
        if item in ("xp_boost", "big_xp_boost"):
            roles_cog = self.bot.get_cog('Roles')
            if roles_cog and interaction.guild:
                await roles_cog.update_roles(interaction.user, interaction.guild)

        embed = discord.Embed(
            title=f"◉  {shop_item['emoji']} Purchased",
            description=(
                f"*{shop_item['name']}*\n"
                f"{SEP}\n"
                f"{result_line}\n"
                f"→  **-{shop_item['cost']:,}** gold spent."
            ),
            color=0xB0C0F5
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Shop(bot))
