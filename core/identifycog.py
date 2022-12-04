import base64
import discord
import traceback
import requests
import asyncio
import time
import threading
from discord import option
from discord.ext import commands
from typing import Optional

from core import queuehandler
from core import viewhandler
from core import settings


class IdentifyCog(commands.Cog, description = 'Describe an image'):
    def __init__(self, bot: discord.Bot):
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
    @option(
        'model',
        str,
        description='Select the model for interrogation',
        required=False,
        choices=['combined'] + settings.global_var.identify_models,
    )
    async def dream_handler(self, ctx: discord.ApplicationContext, *,
                            init_image: Optional[discord.Attachment] = None,
                            init_url: Optional[str] = None,
                            model: Optional[str] = 'combined'):
        loop = asyncio.get_running_loop()
        content = None
        ephemeral = False

        try:
            # get guild id and user
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
                        image = 'data:image/png;base64,' + base64.b64encode(image_data.content).decode('utf-8')
                        image_validated = True
                except:
                    content = 'URL image not found! Please check the image URL.'
                    ephemeral = True
                    image_validated = False

            # fail if no image is provided
            if image_validated == False:
                content = 'I need an image to identify!'
                ephemeral = True
                raise Exception()

            # log the command
            command = f'/identify init_url:{init_url} model:{model}'
            print(command)

            # creates the upscale object out of local variables
            def get_identify_object():
                queue_object = queuehandler.IdentifyObject(self, ctx, init_url, model, command, viewhandler.DeleteView(user.id))

                # construct a payload
                payload = {
                    'image': image,
                    'model': model
                }

                if model:
                    model_payload = {
                        'model': model
                    }
                    payload.update(model_payload)

                queue_object.payload = payload
                return queue_object

            identify_object = get_identify_object()

            # calculate total cost of queued items and reject if there is too expensive
            dream_cost = queuehandler.get_dream_cost(identify_object)
            queue_cost = queuehandler.get_user_queue_cost(user.id)
            if dream_cost + queue_cost > settings.read(guild)['max_compute_queue']:
                content = f'<@{user.id}> Please wait! You have too much queued up.'
                ephemeral = True
                raise Exception()

            if guild == 'private':
                priority: str = 'lowest'
            elif queue_cost == 0.0:
                priority: str = 'high'
            else:
                priority: str = 'medium'

            # start the interrogation
            queue_length = queuehandler.process_dream(identify_object, priority)
            content = f'<@{user.id}> I\'m identifying the image! Queue: ``{queue_length}``'

        except Exception as e:
            if content == None:
                content = f'Something went wrong.\n{e}'
                print(content + f'\n{traceback.print_exc()}')
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

    def dream(self, queue_object: queuehandler.IdentifyObject, queue_continue: threading.Event):
        user = queuehandler.get_user(queue_object.ctx)

        try:
            # send login payload to webui
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

            # safe for global queue to continue
            def continue_queue():
                time.sleep(0.1)
                queue_continue.set()
            threading.Thread(target=continue_queue, daemon=True).start()

            if queue_object.model == 'combined':
                # combined model payload - iterate through all models and put them in the prompt
                payloads: list[dict] = []
                threads: list[threading.Thread] = []
                responses: list[requests.Response] = []
                for model in settings.global_var.identify_models:
                    new_payload = {}
                    new_payload.update(queue_object.payload)
                    model_payload = {
                        'model': model
                    }
                    new_payload.update(model_payload)
                    payloads.append(new_payload)
                    responses.append(None)

                def interrogate(thread_index, thread_payload):
                    responses[thread_index] = s.post(url=f'{settings.global_var.url}/sdapi/v1/interrogate', json=thread_payload)

                for index, payload in enumerate(payloads):
                    thread = threading.Thread(target=interrogate, args=[index, payload], daemon=True)
                    threads.append(thread)

                for thread in threads:
                    thread.start()

                for thread in threads:
                    thread.join()

                def post_dream():
                    try:
                        content: str = ''
                        for index, response in enumerate(responses):
                            response_data = response.json()
                            if index > 0: content += ', '
                            content += response_data.get('caption')

                        content = content.encode('utf-8').decode('unicode_escape')
                        content = content.replace('\\(', '')
                        content = content.replace('\\)', '')
                        content = content.replace('_', ' ')

                        content = f'<@{user.id}> ``{queue_object.command}``\nI think this is ``{content}``'

                        queuehandler.process_upload(queuehandler.UploadObject(queue_object=queue_object,
                            content=content, view=queue_object.view
                        ))
                        queue_object.view = None
                    except Exception as e:
                        content = f'Something went wrong.\n{e}'
                        print(content + f'\n{traceback.print_exc()}')
                        queuehandler.process_upload(queuehandler.UploadObject(queue_object=queue_object, content=content, delete_after=30))
                threading.Thread(target=post_dream, daemon=True).start()
            else:
                # regular payload - get identify for the model specified
                response = s.post(url=f'{settings.global_var.url}/sdapi/v1/interrogate', json=queue_object.payload)
                queue_object.payload = None

                def post_dream():
                    try:
                        response_data = response.json()
                        content = response_data.get('caption')
                        queuehandler.process_upload(queuehandler.UploadObject(queue_object=queue_object,
                            content=f'<@{user.id}> ``{queue_object.command}``\nI think this is ``{content}``', view=queue_object.view
                        ))
                        queue_object.view = None
                    except Exception as e:
                        content = f'Something went wrong.\n{e}'
                        print(content + f'\n{traceback.print_exc()}')
                        queuehandler.process_upload(queuehandler.UploadObject(queue_object=queue_object, content=content, delete_after=30))
                threading.Thread(target=post_dream, daemon=True).start()

        except Exception as e:
            content = f'Something went wrong.\n{e}'
            print(content + f'\n{traceback.print_exc()}')
            queuehandler.process_upload(queuehandler.UploadObject(queue_object=queue_object, content=content, delete_after=30))

def setup(bot: discord.Bot):
    bot.add_cog(IdentifyCog(bot))
