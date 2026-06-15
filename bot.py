import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from database import Database

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
            await bot.load_extension(f'cogs.{filename[:-3]}')

@bot.event
async def setup_hook():
    await load_extensions()
    await bot.tree.sync()
    print('✅ Slash commands synced!')

token = os.getenv('DISCORD_TOKEN')
if not token:
    print("ERROR: No token found! Open .env and paste your bot token.")
else:
    bot.run(token)
