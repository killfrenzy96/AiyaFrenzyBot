import asyncio
import discord
import os
import sys
import csv
import discord
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

self.load_extension('core.settingscog')
self.load_extension('core.stablecog')
self.load_extension('core.upscalecog')
self.load_extension('core.identifycog')
self.load_extension('core.tipscog')
self.load_extension('core.cancelcog')

#stats slash command
@self.slash_command(name='stats', description='How many images have I generated?')
async def stats(ctx: discord.ApplicationContext):
    with open('resources/stats.txt', 'r') as f:
        data = list(map(int, f.readlines()))
    embed = discord.Embed(title='Art generated', description=f'I have created {data[0]} pictures!', color=settings.global_var.embed_color)
    await ctx.respond(embed=embed)

@self.event
async def on_ready():
    self.logger.info(f'Logged in as {self.user.name} ({self.user.id})')
    await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name='drawing tutorials.'))
    #because guilds are only known when on_ready, run files check for guilds
    settings.guilds_check(self)

# @self.event
# async def on_message(message: discord.Message):
#     if message.author == self.user:
#         try:
#             if message.content.startswith('<@') and '> ``' in message.content:
#                 await message.add_reaction('❌')
#                 if '``/dream prompt:' in message.content:
#                     await message.add_reaction('🔁')
#         except(Exception,):
#             pass

#fallback feature to delete generations if aiya has been restarted
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
        stable_cog = self.get_cog('Stable Diffusion')
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

        # message = await self.get_channel(ctx.channel_id).fetch_message(ctx.message_id)

        if message.author.id == self.user.id and user.id != self.user.id:
            # try:
                # Check if the message from Shanghai was actually a generation
                # if message.embeds[0].fields[0].name == 'command':
                if '``/dream prompt:' in message.content:
                    def find_between(s, first, last):
                        try:
                            start = s.index( first ) + len( first )
                            end = s.index( last, start )
                            return s[start:end]
                        except ValueError:
                            return ''

                    command = find_between(message.content, '``/dream ', '``')

                    message.author = user
                    await stable_cog.dream_command(message, command)

@self.event
async def on_guild_join(guild: discord.Guild):
    print(f'Wow, I joined {guild.name}! Refreshing settings.')
    settings.guilds_check(self)

async def shutdown(bot: discord.Bot):
    await bot.close()

try:
    self.run(os.getenv('TOKEN'))
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