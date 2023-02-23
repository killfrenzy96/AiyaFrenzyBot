import base64
import discord
import io
import random
import requests
import time
import traceback
import asyncio
import threading
from discord import option
from discord.ext import commands
from os.path import splitext, basename
from PIL import Image
from typing import Optional
from urllib.parse import urlparse

from core import utility
from core import queuehandler
from core import viewhandler
from core import settings

from core.riffusion import audio


class UpscaleCog(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self.wait_message = []
        self.bot = bot
        self.file_name = ''

    scripts = [
        'spectrogram from image'
    ]

    @commands.slash_command(name = 'upscale', description = 'Upscale an image')
    @option(
        'init_image',
        discord.Attachment,
        description='The starter image to upscale',
        required=False,
    )
    @option(
        'init_url',
        str,
        description='The starter URL image to upscale. This overrides init_image!',
        required=False,
    )
    @option(
        'resize',
        float,
        description='The amount to upscale the image by (1.0 to 4.0).',
        min_value=1,
        max_value=4,
        required=True,
    )
    @option(
        'upscaler_1',
        str,
        description='The upscaler model to use.',
        required=False,
        autocomplete=settings.autocomplete_upscaler,
    )
    @option(
        'upscaler_2',
        str,
        description='The 2nd upscaler model to use.',
        required=False,
        autocomplete=settings.autocomplete_upscaler,
    )
    @option(
        'upscaler_2_strength',
        float,
        description='The visibility of the 2nd upscaler model. (0.0 to 1.0)',
        required=False,
    )
    @option(
        'gfpgan',
        float,
        description='The visibility of the GFPGAN face restoration model. (0.0 to 1.0)',
        required=False,
    )
    @option(
        'codeformer',
        float,
        description='The visibility of the codeformer face restoration model. (0.0 to 1.0)',
        required=False,
    )
    @option(
        'upscale_first',
        bool,
        description='Do the upscale before restoring faces. Default: False',
        required=False,
    )
    @option(
        'script',
        str,
        description='Run a script in this upscale.',
        required=False,
        choices=scripts
    )
    async def dream_handler(self, ctx: discord.ApplicationContext | discord.Interaction, *,
                            init_image: Optional[discord.Attachment] = None,
                            init_url: Optional[str],
                            resize: float = 4.0,
                            upscaler_1: str = None,
                            upscaler_2: Optional[str] = None,
                            upscaler_2_strength: Optional[float] = 0.5,
                            gfpgan: Optional[float] = 0.0,
                            codeformer: Optional[float] = 0.0,
                            upscale_first: Optional[bool] = False,
                            script: Optional[str] = None):
        loop = asyncio.get_event_loop()
        content = None
        ephemeral = False

        try:
            # get guild id and user
            guild = utility.get_guild(ctx)
            user = utility.get_user(ctx)

            print(f'Upscale Request -- {user.name}#{user.discriminator} -- {guild}')

            if upscaler_1 == None and upscaler_2 == None:
                if 'R-ESRGAN 4x+' in settings.global_var.upscaler_names:
                    upscaler_1 = 'R-ESRGAN 4x+'
                elif 'SwinIR_4x' in settings.global_var.upscaler_names:
                    upscaler_1 = 'SwinIR_4x'
                elif '4xESRGAN' in settings.global_var.upscaler_names:
                    upscaler_1 = '4xESRGAN'
                else:
                    print(f'Upscale rejected: No upscaler selected.')
                    content = 'You must select an upscaler!'
                    ephemeral = True
                    raise Exception()

            # get input image
            image: str = None
            image_validated = False
            if init_url or init_image:
                if not init_url and init_image:
                    init_url = init_image.url

                if init_url.startswith('https://cdn.discordapp.com/') == False and init_url.startswith('https://media.discordapp.net/') == False:
                    print(f'Upscale rejected: Image is not from the Discord CDN.')
                    content = 'Only URL images from the Discord CDN are allowed!'
                    ephemeral = True
                    raise Exception()

                try:
                    # reject URL downloads larger than 10MB
                    url_head = await loop.run_in_executor(None, requests.head, init_url)
                    url_size = int(url_head.headers.get('content-length', -1))
                except:
                    content = 'Image not found! Please check the image URL.'
                    ephemeral = True
                    raise Exception()

                # check image download size
                if url_size > 10 * 1024 * 1024:
                    print(f'Upscale rejected: Image download too large.')
                    content = 'Image download is too large! Please make the download size smaller.'
                    ephemeral = True
                    raise Exception()

                # download and encode the image
                try:
                    image_response = await loop.run_in_executor(None, requests.get, init_url)
                    image_data = image_response.content
                    image_string = base64.b64encode(image_data).decode('utf-8')
                except:
                    print(f'Upscale rejected: Image download failed.')
                    content = 'Image download failed! Please check the image URL.'
                    ephemeral = True
                    raise Exception()

                # check if image can open
                try:
                    image_bytes = io.BytesIO(image_data)
                    image_pil = Image.open(image_bytes)
                    image_pil_width, image_pil_height = image_pil.size
                except Exception as e:
                    print(f'Upscale rejected: Image is corrupted.')
                    print(f'\n{traceback.print_exc()}')
                    content = 'Image is corrupted! Please check the image you uploaded.'
                    ephemeral = True
                    raise Exception()

                # limit image width/height
                if image_pil_width * image_pil_height > 512 * 512 * settings.read(guild)['max_compute']:
                    print(f'Upscale rejected: Image size is too large.')
                    content = 'Image size is too large! Please use a lower resolution image.'
                    ephemeral = True
                    raise Exception()

                # setup image variable
                image = 'data:image/png;base64,' + image_string
                image_validated = True

            #fail if no image is provided
            if image_validated == False:
                content = 'I need an image to upscale!'
                ephemeral = True
                raise Exception()

            #pull the name from the image
            disassembled = urlparse(init_url)
            filename, file_ext = splitext(basename(disassembled.path))
            self.file_name = filename

            #formatting aiya initial reply
            append_options = ''
            if upscaler_2:
                append_options = append_options + '\nUpscaler 2: ``' + str(upscaler_2) + '``'
                append_options = append_options + ' - Strength: ``' + str(upscaler_2_strength) + '``'

            #creates the upscale object out of local variables
            def get_upscale_object():
                queue_object = utility.UpscaleObject(self, ctx, resize, init_url, upscaler_1, upscaler_2, upscaler_2_strength, gfpgan, codeformer, upscale_first, script, viewhandler.DeleteView())

                # send message with queue object
                queue_object.message = queue_object.get_command()
                print(queue_object.message) # log the command

                #construct a payload
                payload = {
                    'upscaling_resize': queue_object.resize,
                    'upscaler_1': queue_object.upscaler_1,
                    'image': image,
                    'gfpgan_visibility': queue_object.gfpgan,
                    'codeformer_visibility': queue_object.codeformer,
                    'upscale_first': queue_object.upscale_first
                }
                if queue_object.upscaler_2 is not None:
                    up2_payload = {
                        'upscaler_2': queue_object.upscaler_2,
                        'extras_upscaler_2_visibility': queue_object.upscaler_2_strength
                    }
                    payload.update(up2_payload)

                queue_object.payload = payload
                return queue_object

            upscale_object = get_upscale_object()
            dream_cost = queuehandler.dream_queue.get_dream_cost(upscale_object)
            queue_cost = queuehandler.dream_queue.get_user_queue_cost(user.id)

            # check if the user has too much things in queue
            if dream_cost + queue_cost > settings.read(guild)['max_compute_queue']:
                content = f'<@{user.id}> Please wait! You have too much queued up.'
                ephemeral = True
                raise Exception()

            priority = int(settings.read(guild)['priority'])
            if dream_cost + queue_cost > settings.read(guild)['max_compute']:
                priority += 2
            elif queue_cost > 0.0:
                priority += 1

            # start the upscaling
            queue_length = queuehandler.dream_queue.process_dream(upscale_object, priority)
            if queue_length == None:
                content = f'<@{user.id}> Sorry, I cannot handle this request right now.'
                ephemeral = True
            else:
                content = f'<@{user.id}> {settings.global_var.messages[random.randrange(0, len(settings.global_var.messages))]} Queue: ``{queue_length}``'

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
            elif type(ctx) is discord.Interaction:
                loop.create_task(ctx.response.send_message(content=content, ephemeral=ephemeral, delete_after=delete_after))
            else:
                loop.create_task(ctx.channel.send(content, delete_after=delete_after))

    # generate the image
    def dream(self, queue_object: utility.UpscaleObject, web_ui: utility.WebUI, queue_continue: threading.Event):
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

            response = s.post(url=f'{web_ui.url}/sdapi/v1/extra-single-image', json=queue_object.payload, timeout=120)
            queue_object.payload = None

            def post_dream():
                try:
                    response_data = response.json()
                    image_data = response_data['image']

                    #create safe/sanitized filename
                    epoch_time = int(time.time())

                    # save local copy of image
                    if settings.global_var.dir != '--no-output':
                        file_path = f'{settings.global_var.dir}/{epoch_time}-x{queue_object.resize}-{self.file_name[0:120]}.png'
                        try:
                            with open(file_path, 'wb') as fh:
                                fh.write(base64.b64decode(image_data))
                            print(f'Saved image: {file_path}')
                        except Exception as e:
                            print(f'Unable to save image: {file_path}\n{traceback.print_exc()}')
                    else:
                        file_path = f'{epoch_time}-x{queue_object.resize}-{self.file_name[0:120]}.png'
                        print(f'Received image: {file_path}')

                    # open image
                    image = Image.open(io.BytesIO(base64.b64decode(image_data)))

                    # prepare riffusion audio files
                    riffusion_audio: io.BytesIO = None
                    if queue_object.script == 'spectrogram from image':
                        try:
                            width, height = image.size
                            wav, duration = audio.wav_bytes_from_spectrogram_image(image, height, queue_object.resize)
                            riffusion_audio = audio.mp3_bytes_from_wav_bytes(wav)

                            # save audio
                            if settings.global_var.dir != '--no-output':
                                epoch_time = int(time.time())
                                file_path_audio = f'{settings.global_var.dir}/{epoch_time}-x{queue_object.resize}-{self.file_name[0:120]}.mp3'
                                try:
                                    riffusion_audio.seek(0)
                                    with open(file_path, 'wb') as f:
                                        f.write(riffusion_audio.read())
                                    print(f'Saved audio: {file_path_audio}')
                                except Exception as e:
                                    print(f'Unable to save audio: {file_path_audio}\n{traceback.print_exc()}')
                            else:
                                file_path_audio = f'{epoch_time}-x{queue_object.resize}-{self.file_name[0:120]}.mp3'
                                print(f'Generated audio: {file_path_audio}')
                        except:
                            file_path_audio = f'{epoch_time}-x{queue_object.resize}-{self.file_name[0:120]}.mp3'
                            print(f'Failed to create audio: {file_path_audio}')
                            traceback.print_exc()

                    # post to discord
                    with io.BytesIO() as buffer:
                        image = Image.open(io.BytesIO(base64.b64decode(image_data)))
                        image.save(buffer, 'PNG')
                        size = buffer.getbuffer().nbytes
                        if buffer.getbuffer().nbytes > 8 * 1000 * 1000:
                            print(f'Image too large: {size} bytes - Converting image to JPEG')
                            buffer.truncate(0)
                            buffer.seek(0)
                            quality = int(max(5, min(95, ((8 * 1000 * 1000) / size) * 350.0)))
                            image.save(buffer, format='JPEG', optimize=True, quality=quality)
                            file_path = file_path.rstrip('.png') + '.jpeg'
                            print(f'New image size: {buffer.getbuffer().nbytes} bytes - Quality: {quality}')
                        buffer.seek(0)

                        files = [discord.File(fp=buffer, filename=file_path)]
                        if riffusion_audio: files += [discord.File(fp=riffusion_audio, filename=file_path_audio)]
                        queuehandler.upload_queue.process_upload(utility.UploadObject(queue_object=queue_object,
                            content=f'<@{user.id}> ``{queue_object.message}``', files=files, view=queue_object.view
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
    bot.add_cog(UpscaleCog(bot))
