import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv
from database import Database

# Fix for voice on Windows with Python 3.12+
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)
bot.db = Database()

@bot.event
async def on_ready():
    print(f'✅ {bot.user} is online and ready!')
    print(f'Connected to {len(bot.guilds)} server(s)')
    # Clear any stale voice sessions from previous run
    for guild in bot.guilds:
        if guild.me and guild.me.voice:
            try:
                await guild.me.edit(voice_channel=None)
            except Exception:
                pass

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    # Award 5 XP per message (not for commands)
    if not message.content.startswith('!') and message.guild:
        bot.db.add_xp(message.author.id, 5)
        roles_cog = bot.get_cog('Roles')
        if roles_cog:
            await roles_cog.update_roles(message.author, message.guild)
    await bot.process_commands(message)

async def load_extensions():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
            except Exception as e:
                print(f'⚠️  Failed to load {filename}: {e}')

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    msg = "❌ Something went wrong. Try again in a moment."
    if isinstance(error, discord.app_commands.MissingPermissions):
        msg = "❌ You don't have permission to use that command."
    elif isinstance(error, discord.app_commands.CommandOnCooldown):
        msg = f"❌ Slow down! Try again in **{error.retry_after:.0f}s**."
    elif isinstance(error, discord.app_commands.BotMissingPermissions):
        msg = "❌ I'm missing permissions to do that. Check my role settings."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass

GUILD_ID = discord.Object(id=1392757032939163648)

@bot.event
async def setup_hook():
    await load_extensions()
    bot.tree.copy_global_to(guild=GUILD_ID)
    await bot.tree.sync(guild=GUILD_ID)
    print('✅ Slash commands synced!')

token = os.getenv('DISCORD_TOKEN')
if not token:
    print("ERROR: No token found! Open .env and paste your bot token.")
else:
    bot.run(token)
