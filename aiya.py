import asyncio
import os
import sys
import csv
import discord
from dotenv import load_dotenv
from core.logging import get_logger
from core import settings


#start up initialization stuff
self = discord.Bot()
intents = discord.Intents.default()
intents.members = True
load_dotenv()
self.logger = get_logger(__name__)

#load extensions
# check files and global variables
settings.files_check()
settings.old_api_check()

self.load_extension('core.settingscog')
self.load_extension('core.stablecog')
self.load_extension('core.tipscog')
self.load_extension('core.cancelcog')

#stats slash command
@self.slash_command(name = 'stats', description = 'How many images has the bot generated?')
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

#feature to delete generations. give bot 'Add Reactions' permission (or not, to hide the ❌)
@self.event
async def on_message(message: discord.Message):
    if message.author == self.user:
        try:
            if message.content.startswith('<@') and '> ``' in message.content:
                await message.add_reaction('❌')
                if '``/dream prompt:' in message.content:
                    await message.add_reaction('🔁')
        except(Exception,):
            pass

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

                    # command = message.embeds[0].fields[0].value
                    command = '\n\n ' + find_between(message.content, '``/dream ', '``') + '\n\n'
                    # messageReference = await self.get_channel(ctx.channel_id).fetch_message(message.reference.message_id)

                    dream_ctx = message
                    dream_ctx.author = user

                    params = [
                        'prompt',
                        'negative',
                        'checkpoint',
                        'steps',
                        'height',
                        'width',
                        'guidance_scale',
                        'sampler',
                        'seed',
                        'strength',
                        'init_url',
                        'batch',
                        'style',
                        'facefix',
                        'script'
                    ]

                    for param in params:
                        command = command.replace(f' {param}:', f'\n\n{param}\n')
                    command = command.replace('``', '\n\n')

                    def get_param(param):
                        result = find_between(command, f'\n{param}\n', '\n\n')
                        return result

                    prompt = get_param('prompt')

                    negative = get_param('negative')

                    checkpoint = get_param('checkpoint')
                    if checkpoint == '': checkpoint = 'Default'

                    with open('resources/models.csv', encoding='utf-8') as csv_file:
                        model_data = list(csv.reader(csv_file, delimiter='|'))
                        for row in model_data[1:]:
                            if checkpoint == row[0]: checkpoint = row[1]

                    try:
                        height = int(get_param('height'))
                        if height not in [x for x in range(192, 832, 64)]: height = 512
                    except:
                        height = 512

                    try:
                        width = int(get_param('width'))
                        if width not in [x for x in range(192, 832, 64)]: width = 512
                    except:
                        width = 512

                    try:
                        guidance_scale = float(get_param('guidance_scale'))
                        guidance_scale = max(1.0, guidance_scale)
                    except:
                        guidance_scale = 7.0

                    try:
                        steps = int(get_param('steps'))
                        steps = max(1, steps)
                    except:
                        steps = -1

                    try:
                        sampler = get_param('sampler')
                        if sampler not in settings.global_var.sampler_names: sampler = 'Euler a'
                    except:
                        sampler = 'Euler a'

                    seed = -1

                    try:
                        strength = float(get_param('strength'))
                        strength = max(0.0, min(1.0, strength))
                    except:
                        strength = 0.75

                    try:
                        batch = int(get_param('batch'))
                        batch = max(1.0, batch)
                    except:
                        batch = 1

                    init_url = get_param('init_url')
                    if init_url == '': init_url = None

                    style = get_param('style')
                    if style == '': style = 'None'

                    try:
                        facefix = (get_param('facefix').lower() == 'true')
                    except:
                        facefix = False

                    script = get_param('script')
                    if script == '': script = None

                    await stable_cog.dream_handler(ctx=message,
                        prompt=prompt,
                        negative=negative,
                        checkpoint=checkpoint,
                        height=height,
                        width=width,
                        guidance_scale=guidance_scale,
                        steps=steps,
                        sampler=sampler,
                        seed=seed,
                        init_url=init_url,
                        strength=strength,
                        batch=batch,
                        style=style,
                        facefix=facefix,
                        script=script
                    )

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