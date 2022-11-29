import base64
import discord
import traceback
import requests
import asyncio
from threading import Thread
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
        try:
            loop = asyncio.get_event_loop()

            #get guild id and user
            guild = queuehandler.get_guild(ctx)
            user = queuehandler.get_user(ctx)

            print(f'Identify Request -- {user.name}#{user.discriminator} -- {guild}')

            # get input image
            image: str = None
            image_validated = False
            if init_url or init_image:
                if not init_url and init_image:
                    init_url = init_image.url

                if init_url.startswith('https://cdn.discordapp.com/') == False:
                    print(f'Dream rejected: Image is not from the Discord CDN.')
                    content = 'Only URL images from the Discord CDN are allowed!'
                    ephemeral = True
                    image_validated = False

                try:
                    # reject URL downloads larger than 10MB
                    url_head = await loop.run_in_executor(None, requests.head, init_url)
                    url_size = int(url_head.headers.get('content-length', -1))
                    if url_size > 10 * 1024 * 1024:
                        print(f'Dream rejected: Image too large.')
                        content = 'URL image is too large! Please make the download size smaller.'
                        ephemeral = True
                        image_validated = False
                    else:
                        # download and encode the image
                        image_data = await loop.run_in_executor(None, requests.get, init_url)
                        image = base64.b64encode(image_data.content).decode('utf-8')
                        image_validated = True
                except:
                    content = 'URL image not found! Please check the image URL.'
                    ephemeral = True
                    image_validated = False
            #fail if no image is provided
            if image_validated == False:
                content = 'I need an image to identify!'
                ephemeral = True

            #set up the queue if an image was found
            content = None
            ephemeral = False

            if image_validated:
                #log the command
                copy_command = f'/identify init_url:{init_image.url}'
                print(copy_command)

                image = None
                if init_image is not None:
                    try:
                        image = base64.b64encode(init_image.content).decode('utf-8')
                    except:
                        image_response = await loop.run_in_executor(None, requests.get, init_image.url)
                        image = base64.b64encode(image_response.content).decode('utf-8')
                        # image = base64.b64encode(requests.get(init_image.url, stream=True).content).decode('utf-8')

                #creates the upscale object out of local variables
                def get_identify_object():
                    queue_object = queuehandler.IdentifyObject(self, ctx, init_image, copy_command, viewhandler.DeleteView(user.id))

                    #construct a payload
                    payload = {
                        "image": 'data:image/png;base64,' + image
                    }

                    queue_object.payload = payload
                    return queue_object

                identify_object = get_identify_object()
                dream_cost = queuehandler.get_dream_cost(identify_object)
                queue_cost = queuehandler.get_user_queue_cost(user.id)

                if dream_cost + queue_cost > settings.read(guild)['max_compute_queue']:
                    content = f'<@{user.id}> Please wait! You have too much queued up.'
                    ephemeral = True
                else:
                    if guild == 'private':
                        priority: str = 'lowest'
                    elif queue_cost == 0.0:
                        priority: str = 'high'
                    else:
                        priority: str = 'medium'

                    # queuehandler.GlobalQueue.identify_q.append(identify_object)
                    queue_length = queuehandler.process_dream(self, identify_object, priority)
                    # await ctx.send_response(f'<@{user.id}>, I\'m identifying the image!\nQueue: ``{len(queuehandler.union(queuehandler.GlobalQueue.draw_q, queuehandler.GlobalQueue.upscale_q, queuehandler.GlobalQueue.identify_q))}``')
                    content = f'<@{user.id}> I\'m identifying the image! Queue: ``{queue_length}``'
        except Exception as e:
            print('identify failed')
            print(f'{e}\n{traceback.print_exc()}')
            content = f'identify failed\n{e}\n{traceback.print_exc()}'
            ephemeral = True

        if content:
            if ephemeral:
                delete_after = 30
            else:
                delete_after = 120

            if type(ctx) is discord.ApplicationContext:
                loop.create_task(ctx.send_response(content=content, ephemeral=ephemeral, delete_after=delete_after))
            else:
                loop.create_task(ctx.channel.send(content, delete_after=delete_after))

    def dream(self, queue_object: queuehandler.IdentifyObject):
        user = queuehandler.get_user(queue_object.ctx)

        try:
            #send normal payload to webui
            with requests.Session() as s:
                if settings.global_var.api_auth:
                    s.auth = (settings.global_var.api_user, settings.global_var.api_pass)

                if settings.global_var.gradio_auth:
                    login_payload = {
                        'username': settings.global_var.username,
                        'password': settings.global_var.password
                    }
                    s.post(settings.global_var.url + '/login', data=login_payload)
                # else:
                #     s.post(settings.global_var.url + '/login')

            response = s.post(url=f'{settings.global_var.url}/sdapi/v1/interrogate', json=queue_object.payload)
            queue_object.payload = None

            def post_dream():
                try:
                    response_data = response.json()

                    # post to discord
                    # embed = discord.Embed()
                    # embed.set_image(url=queue_object.init_image.url)
                    # embed.colour = settings.global_var.embed_color
                    # embed.add_field(name=f'I think this is', value=f'``{response_data.get("caption")}``', inline=False)
                    # event_loop.create_task(
                    #     queue_object.ctx.channel.send(content=f'<@{user.id}>', embed=embed))
                    queuehandler.process_upload(queuehandler.UploadObject(
                        ctx=queue_object.ctx, content=f'<@{user.id}> ``{queue_object.copy_command}``\nI think this is ``{response_data.get("caption")}``', view=queue_object.view
                    ))
                    queue_object.view = None
                except Exception as e:
                    print('identify failed (thread)')
                    print(response)
                    embed = discord.Embed(title='identify failed', description=f'{e}\n{traceback.print_exc()}', color=settings.global_var.embed_color)
                    queuehandler.process_upload(queuehandler.UploadObject(
                        ctx=queue_object.ctx, content=f'<@{user.id}> ``{queue_object.copy_command}``', embed=embed
                    ))
            Thread(target=post_dream, daemon=True).start()

        except Exception as e:
            print('identify failed (main)')
            embed = discord.Embed(title='identify failed', description=f'{e}\n{traceback.print_exc()}', color=settings.global_var.embed_color)
            queuehandler.process_upload(queuehandler.UploadObject(
                ctx=queue_object.ctx, content=f'<@{user.id}> ``{queue_object.copy_command}``', embed=embed
            ))

def setup(bot):
    bot.add_cog(IdentifyCog(bot))
