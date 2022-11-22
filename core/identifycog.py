import base64
import discord
import traceback
import requests
import asyncio
from threading import Thread
from asyncio import AbstractEventLoop
from discord import option
from discord.ext import commands
from typing import Optional

from core import queuehandler
from core import viewhandler
from core import settings


class IdentifyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name = 'identify', description = 'Describe an image')
    @option(
        'init_image',
        discord.Attachment,
        description='The image to identify',
        required=False,
    )
    @option(
        'init_url',
        str,
        description='The URL image to identify. This overrides init_image!',
        required=False,
    )
    async def dream_handler(self, ctx: discord.ApplicationContext, *,
                            init_image: Optional[discord.Attachment] = None,
                            init_url: Optional[str]):

        print(f'Identify Request -- {ctx.author.name}#{ctx.author.discriminator}')

        has_image = True
        #url *will* override init image for compatibility, can be changed here
        if init_url:
            try:
                init_image = requests.get(init_url)
            except(Exception,):
                await ctx.send_response('URL image not found!\nI have nothing to work with...', ephemeral=True)
                has_image = False

            if init_url.startswith('https://cdn.discordapp.com/') == False:
                await ctx.send_response('Only URL images from the Discord CDN are allowed!')
                has_image = False

        #fail if no image is provided
        if init_url is None:
            if init_image is None:
                await ctx.send_response('I need an image to identify!', ephemeral=True)
                has_image = False

        #get guild id
        if ctx is discord.ApplicationContext:
            guild = '% s' % ctx.guild_id
        elif ctx.guild:
            guild = '% s' % ctx.guild.id
        else:
            guild = '% s' % 'private'

        view = viewhandler.DeleteView(ctx.author.id)
        #set up the queue if an image was found
        content = None
        ephemeral = False

        if has_image:
            #log the command
            copy_command = f'/identify init_url:{init_image.url}'
            print(copy_command)

            init_image_encoded = None
            if init_image is not None:
                init_image_encoded = base64.b64encode(requests.get(init_image.url, stream=True).content).decode('utf-8')

            #creates the upscale object out of local variables
            def get_identify_object():
                return queuehandler.IdentifyObject(self, ctx, init_image, init_image_encoded, copy_command, view)

            identify_object = get_identify_object()
            dream_cost = queuehandler.get_dream_cost(identify_object)
            queue_cost = queuehandler.get_user_queue_cost(ctx.author.id)
            queue_length = len(queuehandler.GlobalQueue.queue_high)

            if dream_cost + queue_cost > settings.read(guild)['max_compute_queue']:
                content = f'<@{ctx.author.id}> Please wait! You have too much queued up.'
                ephemeral = True
            else:
                if queue_cost == 0.0:
                    priority: str = 'high'
                    print(f'Dream priority: High')
                else:
                    priority: str = 'medium'
                    print(f'Dream priority: Medium')
                    queue_length += len(queuehandler.GlobalQueue.queue)

                # queuehandler.GlobalQueue.identify_q.append(identify_object)
                queuehandler.process_dream(self, identify_object, priority)
                # await ctx.send_response(f'<@{ctx.author.id}>, I\'m identifying the image!\nQueue: ``{len(queuehandler.union(queuehandler.GlobalQueue.draw_q, queuehandler.GlobalQueue.upscale_q, queuehandler.GlobalQueue.identify_q))}``')
                content = f'<@{ctx.author.id}> I\'m identifying the image! Queue: ``{queue_length}``'

        if content:
            try:
                await ctx.send_response(content=content, ephemeral=ephemeral)
            except:
                try:
                    await ctx.reply(content)
                except:
                    await ctx.channel.send(content)

    def dream(self, event_loop: AbstractEventLoop, queue_object: queuehandler.IdentifyObject):
        try:
            #construct a payload
            if queue_object.init_image_encoded:
                image = queue_object.init_image_encoded
            else:
                image = base64.b64encode(requests.get(queue_object.init_image.url, stream=True).content).decode('utf-8')

            payload = {
                "image": 'data:image/png;base64,' + image
            }

            #send normal payload to webui
            with requests.Session() as s:
                if settings.global_var.username is not None:
                    login_payload = {
                    'username': settings.global_var.username,
                    'password': settings.global_var.password
                    }
                    s.post(settings.global_var.url + '/login', data=login_payload)
                else:
                    s.post(settings.global_var.url + '/login')

                response = s.post(url=f'{settings.global_var.url}/sdapi/v1/interrogate', json=payload)

            def post_dream():
                try:
                    response_data = response.json()

                    # post to discord
                    # embed = discord.Embed()
                    # embed.set_image(url=queue_object.init_image.url)
                    # embed.colour = settings.global_var.embed_color
                    # embed.add_field(name=f'I think this is', value=f'``{response_data.get("caption")}``', inline=False)
                    # event_loop.create_task(
                    #     queue_object.ctx.channel.send(content=f'<@{queue_object.ctx.author.id}>', embed=embed))
                    queuehandler.process_upload(queuehandler.UploadObject(
                        ctx=queue_object.ctx, content=f'<@{queue_object.ctx.author.id}> I think this is ``{response_data.get("caption")}``'
                    ))
                except Exception as e:
                    print('identify failed (thread)')
                    print(response)
                    embed = discord.Embed(title='identify failed', description=f'{e}\n{traceback.print_exc()}', color=settings.global_var.embed_color)
                    queuehandler.process_upload(queuehandler.UploadObject(
                        ctx=queue_object.ctx, content=f'<@{queue_object.ctx.author.id}> ``{queue_object.copy_command}``', embed=embed, view=queue_object.view
                    ))
            Thread(target=post_dream, daemon=True).start()

        except Exception as e:
            print('identify failed (main)')
            embed = discord.Embed(title='identify failed', description=f'{e}\n{traceback.print_exc()}', color=settings.global_var.embed_color)
            queuehandler.process_upload(queuehandler.UploadObject(
                ctx=queue_object.ctx, content=f'<@{queue_object.ctx.author.id}> ``{queue_object.copy_command}``', embed=embed
            ))
        #check each queue for any remaining tasks
        queuehandler.process_queue()

def setup(bot):
    bot.add_cog(IdentifyCog(bot))
