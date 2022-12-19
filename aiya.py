import asyncio
import discord
import os
import sys
from core import utility
from core import settings
from core.logging import get_logger
from dotenv import load_dotenv


#start up initialization stuff
self = discord.Bot()
intents = discord.Intents.default()
intents.members = True
load_dotenv()
self.logger = get_logger(__name__)

#load extensions
# check files and global variables
settings.startup_check()
settings.files_check()

self.load_extension('core.stablecog')
self.load_extension('core.upscalecog')
self.load_extension('core.identifycog')
self.load_extension('core.tipscog')
self.load_extension('core.cancelcog')
self.load_extension('core.minigamecog')
self.load_extension('core.fallbackviewcog')

#stats slash command
@self.slash_command(name='stats', description='How many images have I generated?')
async def stats(ctx: discord.ApplicationContext):
    embed = discord.Embed(title='Art generated', description=f'I have created {settings.global_var.images_generated} pictures!', color=settings.global_var.embed_color)
    await ctx.respond(content=f'<@{ctx.user.id}>', embed=embed)

@self.event
async def on_ready():
    self.logger.info(f'Logged in as {self.user.name} ({self.user.id})')
    await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name='drawing tutorials.'))
    #because guilds are only known when on_ready, run files check for guilds
    settings.guilds_check(self)

# fallback feature to let reactions still work
@self.event
async def on_raw_reaction_add(ctx: discord.RawReactionActionEvent):
    if ctx.user_id == self.user.id:
        return

    if ctx.emoji.name == '❌':
        channel = self.get_channel(ctx.channel_id)
        if channel == None:
            channel = await self.fetch_channel(ctx.channel_id)

        message: discord.Message = await channel.fetch_message(ctx.message_id)

        author = message.author
        if author == None:
            return

        user = ctx.member
        if user == None:
            user = await self.fetch_user(ctx.user_id)

        if channel.permissions_for(user).use_application_commands == False:
            return

        if author.id == self.user.id and message.content.startswith(f'<@{ctx.user_id}>'):
            await message.delete()

    if ctx.emoji.name == '🔁':
        stable_cog = self.get_cog('StableCog')
        if stable_cog == None:
            print('Error: StableCog not found.')
            return

        channel = self.get_channel(ctx.channel_id)
        if channel == None:
            channel = await self.fetch_channel(ctx.channel_id)

        message: discord.Message = await channel.fetch_message(ctx.message_id)

        user = ctx.member
        if user == None:
            user = await self.fetch_user(ctx.user_id)

        if channel.permissions_for(user).use_application_commands == False:
            return

        if message.author.id == self.user.id and user.id != self.user.id:
            # check if the message from Shanghai was actually a generation
            if '``/dream prompt:' in message.content:
                command = utility.find_between(message.content, '``/dream ', '``')

                message.author = user
                await stable_cog.dream_command(message, command)

@self.event
async def on_guild_join(guild: discord.Guild):
    print(f'Wow, I joined {guild.name}! Refreshing settings.')
    settings.guilds_check(self)

async def shutdown(bot: discord.Bot):
    await bot.close()

print('Starting Bot...')
from core import consoleinput
console_input = consoleinput.ConsoleInput(self)

try:
    console_input.run()
    self.run(settings.get_env_var('TOKEN'))
except KeyboardInterrupt:
    self.logger.info('Keyboard interrupt received. Exiting.')
    asyncio.run(shutdown(self))
except SystemExit:
    self.logger.info('System exit received. Exiting.')
    asyncio.run(shutdown(self))
except Exception as e:
    self.logger.error(e)
    asyncio.run(shutdown(self))
finally:
    sys.exit(0)