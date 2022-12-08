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

from core import utility
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
            guild = utility.get_guild(ctx)
            user = utility.get_user(ctx)

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

            # creates the upscale object out of local variables
            def get_identify_object():
                queue_object = utility.IdentifyObject(self, ctx, init_url, model, viewhandler.DeleteView(user.id))

                # send message with queue object
                queue_object.message = queue_object.get_command()
                print(queue_object.message) # log the command

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
            dream_cost = queuehandler.dream_queue.get_dream_cost(identify_object)
            queue_cost = queuehandler.dream_queue.get_user_queue_cost(user.id)
            if dream_cost + queue_cost > settings.read(guild)['max_compute_queue']:
                content = f'<@{user.id}> Please wait! You have too much queued up.'
                ephemeral = True
                raise Exception()

            priority = int(settings.read(guild)['priority'])
            if queue_cost > 0.0: priority += 1
            if dream_cost + queue_cost > settings.read(guild)['max_compute']:
                priority += 2
            elif queue_cost > 0.0:
                priority += 1

            # start the interrogation
            queue_length = queuehandler.dream_queue.process_dream(identify_object, priority)
            if queue_length == None:
                content = f'<@{user.id}> Sorry, I cannot handle this request right now.'
                ephemeral = True
            else:
                content = f'<@{user.id}> I\'m identifying the image! Queue: ``{queue_length}``'

        except Exception as e:
            if content == None:
                content = f'<@{user.id}> Something went wrong.\n{e}'
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

    def dream(self, queue_object: utility.IdentifyObject, web_ui: utility.WebUI, queue_continue: threading.Event):
        user = utility.get_user(queue_object.ctx)

        try:
            # get webui session
            s = web_ui.get_session()
            if s == None:
                # no session, return the object to the queue handler to try again
                queuehandler.dream_queue.process_dream(queue_object, 0, False)
                return

            # safe for global queue to continue
            def continue_queue():
                time.sleep(0.1)
                queue_continue.set()
            threading.Thread(target=continue_queue, daemon=True).start()

            if queue_object.model == 'combined':
                # combined model payload - iterate through all models and put them in the prompt
                payloads: list[dict] = []
                threads: list[threading.Thread] = []
                responses: list[requests.Response | Exception] = []
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
                    try:
                        responses[thread_index] = s.post(url=f'{web_ui.url}/sdapi/v1/interrogate', json=thread_payload, timeout=60)
                    except Exception as e:
                        responses[thread_index] = e

                for index, payload in enumerate(payloads):
                    thread = threading.Thread(target=interrogate, args=[index, payload], daemon=True)
                    threads.append(thread)

                for thread in threads:
                    thread.start()

                for thread in threads:
                    thread.join()

                for response in responses:
                    if type(response) is not requests.Response:
                        raise response

                def post_dream():
                    try:
                        content: str = ''
                        for index, response in enumerate(responses):
                            response_data = response.json()
                            caption = response_data.get('caption')
                            if caption:
                                if content: content += ', '
                                content += caption

                        content = content.encode('utf-8').decode('unicode_escape')
                        content = content.replace('\\(', '')
                        content = content.replace('\\)', '')
                        content = content.replace('_', ' ')

                        content = f'<@{user.id}> ``{queue_object.message}``\nI think this is ``{content}``'

                        queuehandler.upload_queue.process_upload(utility.UploadObject(queue_object=queue_object,
                            content=content, view=queue_object.view
                        ))
                        queue_object.view = None

                    except Exception as e:
                        content = f'<@{user.id}> ``{queue_object.message}``\nSomething went wrong.\n{e}'
                        print(content + f'\n{traceback.print_exc()}')
                        queuehandler.upload_queue.process_upload(utility.UploadObject(queue_object=queue_object, content=content, delete_after=30))

                threading.Thread(target=post_dream, daemon=True).start()
            else:
                # regular payload - get identify for the model specified
                response = s.post(url=f'{web_ui.url}/sdapi/v1/interrogate', json=queue_object.payload, timeout=60)
                queue_object.payload = None

                def post_dream():
                    try:
                        response_data = response.json()
                        content = response_data.get('caption')
                        queuehandler.upload_queue.process_upload(utility.UploadObject(queue_object=queue_object,
                            content=f'<@{user.id}> ``{queue_object.message}``\nI think this is ``{content}``', view=queue_object.view
                        ))
                        queue_object.view = None
                    except Exception as e:
                        content = f'<@{user.id}> ``{queue_object.message}``\nSomething went wrong.\n{e}'
                        print(content + f'\n{traceback.print_exc()}')
                        queuehandler.upload_queue.process_upload(utility.UploadObject(queue_object=queue_object, content=content, delete_after=30))
                threading.Thread(target=post_dream, daemon=True).start()

        except requests.exceptions.RequestException as e:
            # connection error, return items to queue
            time.sleep(5.0)
            web_ui.reconnect()
            queuehandler.dream_queue.process_dream(queue_object, 0, False)
            return

        except Exception as e:
            content = f'<@{user.id}> ``{queue_object.message}``\nSomething went wrong.\n{e}'
            print(content + f'\n{traceback.print_exc()}')
            queuehandler.upload_queue.process_upload(utility.UploadObject(queue_object=queue_object, content=content, delete_after=30))

def setup(bot: discord.Bot):
    bot.add_cog(IdentifyCog(bot))
