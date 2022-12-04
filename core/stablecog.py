import base64
import contextlib
import discord
import io
import random
import requests
import time
import traceback
import asyncio
import threading
from urllib.parse import quote
from PIL import Image, PngImagePlugin
from discord import option
from discord.ext import commands
from typing import Optional

from core import queuehandler
from core import viewhandler
from core import settings


class StableCog(commands.Cog, description='Create images from natural language.'):
    ctx_parse = discord.ApplicationContext
    def __init__(self, bot):
        self.wait_message: list[str] = []
        self.bot: discord.Bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(viewhandler.DrawExtendedView(self, None))

    # pulls from model_names list and makes some sort of dynamic list to bypass Discord 25 choices limit
    # def model_autocomplete(self: discord.AutocompleteContext):
    #     return [
    #         model for model in settings.global_var.model_names
    #     ]
    # and for styles
    # def style_autocomplete(self: discord.AutocompleteContext):
    #     return [
    #         style for style in settings.global_var.style_names
    #     ]

    # a list of parameters, used to sanatize text
    dream_params = [
        'prompt',
        'negative',
        'checkpoint',
        'steps',
        'width',
        'height',
        'guidance_scale',
        'sampler',
        'seed',
        'strength',
        'init_url',
        'batch',
        'style',
        'facefix',
        'tiling',
        'highres_fix',
        'clip_skip',
        'script'
    ]

    scripts = [
        'preset steps',
        'preset guidance_scale',
        'preset clip_skip',
        'increment steps +5',
        'increment steps +1',
        'increment guidance_scale +2',
        'increment guidance_scale +1',
        'increment guidance_scale +0.1',
        'increment clip_skip +1'
    ]

    @commands.slash_command(name = 'dream', description = 'Create an image')
    @option(
        'prompt',
        str,
        description='A prompt to condition the model with.',
        required=True,
    )
    @option(
        'negative',
        str,
        description='Negative prompts to exclude from output.',
        required=False,
    )
    @option(
        'checkpoint',
        str,
        description='Select the data model for image generation',
        required=False,
        # autocomplete=discord.utils.basic_autocomplete(model_autocomplete),
        choices=settings.global_var.model_names,
    )
    @option(
        'steps',
        int,
        description='The amount of steps to sample the model.',
        min_value=1,
        required=False,
    )
    @option(
        'width',
        int,
        description='Width of the generated image. Default: 512',
        required=False,
        choices = [x for x in range(192, 1281, 64)]
    )
    @option(
        'height',
        int,
        description='Height of the generated image. Default: 512',
        required=False,
        choices = [x for x in range(192, 1281, 64)]
    )
    @option(
        'guidance_scale',
        float,
        description='Classifier-Free Guidance scale. Default: 7.0',
        required=False,
    )
    @option(
        'sampler',
        str,
        description='The sampler to use for generation. Default: DPM++ 2M Karras',
        required=False,
        choices=settings.global_var.sampler_names,
    )
    @option(
        'seed',
        int,
        description='The seed to use for reproducibility',
        required=False,
    )
    @option(
        'strength',
        float,
        description='The amount in which init_image will be altered (0.0 to 1.0).'
    )
    @option(
        'init_image',
        discord.Attachment,
        description='The starter image for generation. Remember to set strength value!',
        required=False,
    )
    @option(
        'init_url',
        str,
        description='The starter URL image for generation. This overrides init_image!',
        required=False,
    )
    @option(
        'batch',
        int,
        description='The number of images to generate. This is \'Batch count\', not \'Batch size\'.',
        required=False,
    )
    @option(
        'style',
        str,
        description='Apply a predefined style to the generation.',
        required=False,
        # autocomplete=discord.utils.basic_autocomplete(style_autocomplete),
        choices=settings.global_var.style_names,
    )
    @option(
        'facefix',
        str,
        description='Tries to improve faces in pictures.',
        required=False,
        choices=settings.global_var.facefix_models,
    )
    @option(
        'tiling',
        bool,
        description='Produces an image that can be tiled.',
        required=False,
    )
    @option(
        'highres_fix',
        bool,
        description='Tries to fix issues from generating high-res images. Takes longer!',
        required=False,
    )
    @option(
        'clip_skip',
        int,
        description='Number of last layers of CLIP model to skip',
        required=False,
        choices=[x for x in range(1, 13, 1)]
    )
    @option(
        'script',
        str,
        description='Generates image batches using a script.',
        required=False,
        choices=scripts
    )
    async def dream_handler(self, ctx: discord.ApplicationContext | discord.Message | discord.Interaction, *,
                            prompt: str, negative: str = None,
                            checkpoint: Optional[str] = None,
                            steps: Optional[int] = -1,
                            width: Optional[int] = 512, height: Optional[int] = 512,
                            guidance_scale: Optional[float] = 7.0,
                            sampler: Optional[str] = None,
                            seed: Optional[int] = -1,
                            strength: Optional[float] = 0.75,
                            init_image: Optional[discord.Attachment] = None,
                            init_url: Optional[str] = None,
                            batch: Optional[int] = None,
                            style: Optional[str] = None,
                            facefix: Optional[str] = None,
                            tiling: Optional[bool] = False,
                            highres_fix: Optional[bool] = False,
                            clip_skip: Optional[int] = 0,
                            script: Optional[str] = None):
        loop = asyncio.get_event_loop()
        content = None
        ephemeral = False

        try:
            command: str = None

            # get guild id and user
            guild = queuehandler.get_guild(ctx)
            user = queuehandler.get_user(ctx)

            print(f'Dream Request -- {user.name}#{user.discriminator} -- {guild}')

            # sanatize input strings
            def sanatize(input: str):
                if input:
                    input = input.replace('`', ' ')
                    input = input.replace('\n', ' ')
                    for param in self.dream_params:
                        input = input.replace(f' {param}:', f' {param} ')
                    input = input.strip()
                return input

            prompt = sanatize(prompt)
            negative = sanatize(negative)
            style = sanatize(style)
            init_url = sanatize(init_url)

            # query random result from lexica
            if prompt.startswith('?'):
                try:
                    prompt = prompt.removeprefix('?')
                    if prompt == '':
                        prompt = random.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')
                    else:
                        prompt = quote(prompt.strip())
                    response = await loop.run_in_executor(None, requests.get, f'https://lexica.art/api/v1/search?q={prompt}')
                    images = response.json()['images']
                    random_image = images[random.randrange(0, len(images))]
                    prompt = sanatize(random_image['prompt'])
                except:
                    print(f'Dream rejected: Random prompt query failed.')
                    content = f'<@{user.id}> Random prompt query failed.'
                    ephemeral = True
                    raise Exception()

            # update defaults with any new defaults from settingscog
            if not checkpoint:
                checkpoint = settings.read(guild)['data_model']
            if negative == None:
                negative = settings.read(guild)['negative_prompt']
            if steps == -1:
                steps = settings.read(guild)['default_steps']
            if batch is None:
                batch = settings.read(guild)['default_count']
            if sampler == None:
                sampler = settings.read(guild)['sampler']
            if clip_skip == 0:
                clip_skip = settings.read(guild)['clip_skip']

            # get data model and token from checkpoint
            data_model: str = ''
            token: str = ''
            for (display_name, full_name) in settings.global_var.model_names.items():
                if display_name == checkpoint or full_name == checkpoint:
                    checkpoint = display_name
                    data_model = full_name
                    token = settings.global_var.model_tokens[display_name]

            if seed == -1: seed = random.randint(0, 0xFFFFFFFF)

            # get arguments that can be passed into the draw object
            def get_draw_object_args():
                return (self, ctx, prompt, negative, checkpoint, data_model,
                        steps, width, height, guidance_scale, sampler, seed,
                        strength, init_url, batch, style,
                        facefix, tiling, highres_fix, clip_skip, script)

            # get estimate of the compute cost of this dream
            def get_dream_cost(_width: int, _height: int, _steps: int, _count: int = 1):
                args = get_draw_object_args()
                dream_cost_draw_object = queuehandler.DrawObject(*args)
                dream_cost_draw_object.width = _width
                dream_cost_draw_object.height = _height
                dream_cost_draw_object.steps = _steps
                dream_cost_draw_object.batch = _count
                return queuehandler.get_dream_cost(dream_cost_draw_object)
            dream_compute_cost = get_dream_cost(width, height, steps, 1)

            # get settings
            setting_max_compute = settings.read(guild)['max_compute']
            setting_max_compute_batch = settings.read(guild)['max_compute_batch']
            setting_max_steps = settings.read(guild)['max_steps']

            # apply script modifications
            increment_seed = 0
            increment_steps = 0
            increment_guidance_scale = 0
            increment_clip_skip = 0
            append_options = ''

            match script:
                case None:
                    increment_seed = 1

                case 'preset steps':
                    steps = 10
                    increment_steps = 5
                    batch = 9

                    average_step_cost = get_dream_cost(width, height, steps + (increment_steps * batch * 0.5), batch)
                    if average_step_cost > setting_max_compute_batch:
                        increment_steps = 10
                        batch = 5

                case 'preset guidance_scale':
                    guidance_scale = 5.0
                    increment_guidance_scale = 1.0
                    batch = max(10, batch)

                    if dream_compute_cost * batch > setting_max_compute_batch:
                        batch = int(batch / 2)
                        increment_guidance_scale = 2.0

                case 'preset clip_skip':
                    clip_skip = 1
                    increment_clip_skip = 1
                    batch = max(6, min(12, batch))

                case other:
                    try:
                        script_parts = script.split(' ')
                        script_setting = script_parts[0]
                        script_param = script_parts[1]
                        script_value = float(script_parts[2])

                        if script_setting == 'increment':
                            match script_param:
                                case 'steps':
                                    increment_steps = int(script_value)
                                    batch = max(5, batch)
                                case 'guidance_scale':
                                    increment_guidance_scale = script_value
                                    if increment_guidance_scale < 1.0:
                                        batch = max(10, batch)
                                    else:
                                        batch = max(4, batch)
                                case 'clip_skip':
                                    increment_clip_skip = int(script_value)
                                    batch = max(4, batch)
                                    clip_skip_max = clip_skip + (batch * increment_clip_skip)
                                    if clip_skip_max > 12:
                                        batch = clip_skip_max - 12
                    except:
                        append_options = append_options + '\nInvalid script. I will ignore the script parameter.'
                        increment_seed = 1
                        increment_steps = 0
                        increment_guidance_scale = 0
                        increment_clip_skip = 0

            # lower step value to the highest setting if user goes over max steps
            if dream_compute_cost > setting_max_compute:
                steps = min(int(float(steps) * (setting_max_compute / dream_compute_cost)), setting_max_steps)
                append_options = append_options + '\nDream compute cost is too high! Steps reduced to ``' + str(steps) + '``'
            if steps > setting_max_steps:
                steps = setting_max_steps
                append_options = append_options + '\nExceeded maximum of ``' + str(steps) + '`` steps! This is the best I can do...'

            # reduce batch count if batch compute cost is too high
            if batch != 1:
                if increment_steps:
                    dream_compute_batch_cost = get_dream_cost(width, height, steps + (increment_steps * batch * 0.5), batch)
                else:
                    dream_compute_batch_cost = get_dream_cost(width, height, steps, batch)
                setting_max_count = settings.read(guild)['max_count']
                if dream_compute_batch_cost > setting_max_compute_batch:
                    batch = min(int(float(batch) * setting_max_compute_batch / dream_compute_batch_cost), setting_max_count)
                    append_options = append_options + '\nBatch compute cost is too high! Batch count reduced to ``' + str(batch) + '``'
                if batch > setting_max_count:
                    batch = setting_max_count
                    append_options = append_options + '\nExceeded maximum of ``' + str(batch) + '`` images! This is the best I can do...'

            # calculate total cost of queued items and reject if there is too expensive
            dream_cost = round(get_dream_cost(width, height, steps, batch), 2)
            queue_cost = round(queuehandler.get_user_queue_cost(user.id), 2)
            print(f'Estimated total compute cost -- Dream: {dream_cost} Queue: {queue_cost} Total: {dream_cost + queue_cost}')

            if dream_cost + queue_cost > settings.read(guild)['max_compute_queue']:
                print(f'Dream rejected: Too much in queue already')
                content = f'<@{user.id}> Please wait! You have too much queued up.'
                ephemeral = True
                raise Exception()

            # get input image
            image: str = None
            image_validated = True
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
                except Exception as e:
                    content = 'URL image not found! Please check the image URL.'
                    ephemeral = True
                    image_validated = False

            if image_validated == False:
                raise Exception()

            # increment number of images generated
            settings.increment_stats(batch)

            # create draw object
            def get_draw_object(message: str = None):
                args = get_draw_object_args()
                queue_object = queuehandler.DrawObject(*args)

                # create view to handle buttons
                queue_object.view = viewhandler.DrawView(self, queue_object)

                # send message with queue object
                if message == None:
                    queue_object.message = queue_object.get_command()
                    print(queue_object.message) # log the command
                else:
                    queue_object.message = message

                # create persistent session since we'll need to do a few API calls
                s = requests.Session()
                if settings.global_var.api_auth:
                    s.auth = (settings.global_var.api_user, settings.global_var.api_pass)

                # construct a payload
                payload_prompt = queue_object.prompt
                if token: payload_prompt = f'{token} {payload_prompt}'

                payload = {
                    'prompt': payload_prompt,
                    'negative_prompt': queue_object.negative,
                    'steps': queue_object.steps,
                    'width': queue_object.width,
                    'height': queue_object.height,
                    'cfg_scale': queue_object.guidance_scale,
                    'sampler_index': queue_object.sampler,
                    'seed': queue_object.seed,
                    'seed_resize_from_h': 0,
                    'seed_resize_from_w': 0,
                    'denoising_strength': None,
                    'tiling': queue_object.tiling,
                    'n_iter': 1
                }

                # update payload if init_img or init_url is used
                if queue_object.init_url:
                    payload.update({
                        'init_images': [image],
                        'denoising_strength': queue_object.strength
                    })

                # update payload if high-res fix is used
                if queue_object.highres_fix:
                    payload.update({
                        'enable_hr': queue_object.highres_fix,
                        'denoising_strength': queue_object.strength
                    })

                # update payload if style is used
                if queue_object.highres_fix:
                    payload.update({
                        'styles': [queue_object.style]
                    })

                # add any options that would go into the override_settings
                override_settings = {}

                # update payload if clip skip is used
                if queue_object.clip_skip != 1:
                    override_settings['CLIP_stop_at_last_layers'] = queue_object.clip_skip

                # update payload if facefix is used
                if queue_object.facefix != None:
                    payload.update({
                        'restore_faces': True,
                    })
                    override_settings['face_restoration_model'] = queue_object.facefix

                # update payload with override_settings
                if len(override_settings) > 1:
                    override_payload = {
                        'override_settings': override_settings
                    }
                    payload.update(override_payload)

                # attach payload to queue object
                queue_object.payload = payload
                return queue_object

            # start the dream
            if batch == 1:
                if guild == 'private':
                    priority: str = 'lowest'
                elif queue_cost == 0.0: # if user does not have a dream in process, they get high priority
                    priority: str = 'high'
                elif dream_cost + queue_cost > setting_max_compute: # if user user has a lot in queue, they get low priority
                    priority: str = 'low'
                else:
                    priority: str = 'medium'

                queue_length = queuehandler.process_dream(get_draw_object(), priority)
            else:
                if guild == 'private':
                    priority: str = 'lowest'
                # batched items go into the low priority queue
                else:
                    priority: str = 'low'

                queue_length = queuehandler.process_dream(get_draw_object(), priority)

                batch_count = 1
                while batch_count < batch:
                    batch_count += 1
                    message = f'#{batch_count}`` ``'

                    if increment_seed:
                        seed += increment_seed
                        message += f'seed:{seed}'

                    if increment_steps:
                        steps += increment_steps
                        message += f'steps:{steps}'

                    if increment_guidance_scale:
                        guidance_scale += increment_guidance_scale
                        guidance_scale = round(guidance_scale, 4)
                        message += f'guidance_scale:{guidance_scale}'

                    if increment_clip_skip:
                        clip_skip += increment_clip_skip
                        message += f'clip_skip:{clip_skip}'

                    queuehandler.process_dream(get_draw_object(message), priority, False)

            content = f'<@{user.id}> {settings.global_var.messages[random.randrange(0, len(settings.global_var.messages))]} Queue: ``{queue_length}``'
            if batch > 1: content = content + f' - Batch: ``{batch}``'
            content = content + append_options

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
            elif type(ctx) is discord.Interaction:
                loop.create_task(ctx.response.send_message(content=content, ephemeral=ephemeral, delete_after=delete_after))
            elif type(ctx) is discord.Message:
                loop.create_task(ctx.reply(content, delete_after=delete_after))
            else:
                loop.create_task(ctx.channel.send(content, delete_after=delete_after))

    # generate the image
    def dream(self, queue_object: queuehandler.DrawObject, queue_continue: threading.Event):
        user = queuehandler.get_user(queue_object.ctx)

        try:
            # create persistent session since we'll need to do a few API calls
            s = requests.Session()
            if settings.global_var.api_auth:
                s.auth = (settings.global_var.api_user, settings.global_var.api_pass)

            # send login payload to webui
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

            # only send model payload if one is defined
            if queue_object.data_model:
                model_payload = {
                    'sd_model_checkpoint': queue_object.data_model
                }
                s.post(url=f'{settings.global_var.url}/sdapi/v1/options', json=model_payload)

            if queue_object.init_url:
                url = f'{settings.global_var.url}/sdapi/v1/img2img'
            else:
                url = f'{settings.global_var.url}/sdapi/v1/txt2img'
            response = s.post(url=url, json=queue_object.payload)
            queue_object.payload = None

            def post_dream():
                try:
                    response_data = response.json()
                    # create safe/sanitized filename
                    keep_chars = (' ', '.', '_')
                    file_name = ''.join(c for c in queue_object.prompt if c.isalnum() or c in keep_chars).rstrip()

                    # save local copy of image and prepare PIL images
                    pil_images = []
                    for i, image_base64 in enumerate(response_data['images']):
                        image = Image.open(io.BytesIO(base64.b64decode(image_base64.split(',',1)[0])))
                        pil_images.append(image)

                        # grab png info
                        png_payload = {
                            'image': 'data:image/png;base64,' + image_base64
                        }
                        png_response = s.post(url=f'{settings.global_var.url}/sdapi/v1/png-info', json=png_payload)

                        metadata = PngImagePlugin.PngInfo()
                        epoch_time = int(time.time())
                        metadata.add_text('parameters', png_response.json().get('info'))
                        file_path = f'{settings.global_var.dir}/{epoch_time}-{queue_object.seed}-{file_name[0:120]}-{i}.png'
                        image.save(file_path, pnginfo=metadata)
                        print(f'Saved image: {file_path}')

                    # post to discord
                    with contextlib.ExitStack() as stack:
                        buffer_handles = [stack.enter_context(io.BytesIO()) for _ in pil_images]

                        for (pil_image, buffer) in zip(pil_images, buffer_handles):
                            pil_image.save(buffer, 'PNG')
                            buffer.seek(0)

                        files = [discord.File(fp=buffer, filename=f'{queue_object.seed}-{i}.png') for (i, buffer) in enumerate(buffer_handles)]
                        queuehandler.process_upload(queuehandler.UploadObject(queue_object=queue_object,
                           content=f'<@{user.id}> ``{queue_object.message}``', files=files, view=queue_object.view
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

    async def dream_object(self, draw_object: queuehandler.DrawObject):
        loop = asyncio.get_running_loop()
        loop.create_task(self.dream_handler(ctx=draw_object.ctx,
            prompt=draw_object.prompt,
            negative=draw_object.negative,
            checkpoint=draw_object.model_name,
            width=draw_object.width,
            height=draw_object.height,
            guidance_scale=draw_object.guidance_scale,
            steps=draw_object.steps,
            sampler=draw_object.sampler,
            seed=draw_object.seed,
            init_image=None,
            init_url=draw_object.init_url,
            strength=draw_object.strength,
            batch=draw_object.batch,
            style=draw_object.style,
            facefix=draw_object.facefix,
            tiling=draw_object.tiling,
            highres_fix=draw_object.highres_fix,
            clip_skip=draw_object.clip_skip,
            script=draw_object.script
        ))

    # process dream from a command string
    async def dream_command(self, ctx: discord.ApplicationContext | discord.Message | discord.Interaction, command: str, randomize_seed = True):
        queue_object = self.get_draw_object_from_command(command)

        queue_object.ctx = ctx
        if randomize_seed:
            queue_object.seed = -1

        loop = asyncio.get_event_loop()
        loop.create_task(self.dream_object(queue_object))

    # get draw object from a command string
    def get_draw_object_from_command(self, command: str):
        def find_between(s: str, first: str, last: str):
            try:
                start = s.index(first) + len(first)
                end = s.index(last, start)
                return s[start:end]
            except ValueError:
                return ''

        # format command for easier processing
        command = '\n\n ' + command + '\n\n'
        for param in self.dream_params:
            command = command.replace(f' {param}:', f'\n\n{param}\n')
        command = command.replace('``', '\n\n')

        def get_param(param):
            result = find_between(command, f'\n{param}\n', '\n\n')
            return result.strip()

        # get all parameters and validate inputs
        prompt = get_param('prompt')

        negative = get_param('negative')

        checkpoint = get_param('checkpoint')
        if checkpoint not in settings.global_var.model_names: checkpoint = 'Default'

        try:
            width = int(get_param('width'))
            if width not in [x for x in range(192, 1281, 64)]:
                width = int(width / 64) * 64
                if width not in [x for x in range(192, 1281, 64)]: width = 512
        except:
            width = 512

        try:
            height = int(get_param('height'))
            if height not in [x for x in range(192, 1281, 64)]:
                height = int(height / 64) * 64
                if height not in [x for x in range(192, 1281, 64)]: height = 512
        except:
            height = 512

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
            if sampler not in settings.global_var.sampler_names: sampler = None
        except:
            sampler = None

        try:
            seed = int(get_param('seed'))
        except:
            seed = -1

        try:
            strength = float(get_param('strength'))
            strength = max(0.0, min(1.0, strength))
        except:
            strength = 0.75

        try:
            batch = int(get_param('batch'))
            batch = max(1, batch)
        except:
            batch = 1

        init_url = get_param('init_url')
        if init_url == '':
            init_url = None

        style = get_param('style')
        if style not in settings.global_var.style_names: style = None

        try:
            tiling = get_param('tiling')
            if tiling.lower() == 'true':
                tiling = True
            else:
                tiling = False
        except:
            tiling = False

        try:
            highres_fix = get_param('tiling')
            if highres_fix.lower() == 'true':
                highres_fix = True
            else:
                highres_fix = False
        except:
            highres_fix = False

        try:
            facefix = get_param('facefix')
            if facefix not in settings.global_var.facefix_models: facefix = 'None'
        except:
            facefix = 'None'

        try:
            clip_skip = int(get_param('clip_skip'))
            clip_skip = max(0, min(12, clip_skip))
        except:
            clip_skip = 0

        script = get_param('script')
        if script not in self.scripts: script = None

        return queuehandler.DrawObject(
            cog=None,
            ctx=None,
            prompt=prompt,
            negative=negative,
            model_name=checkpoint,
            data_model=checkpoint,
            steps=steps,
            width=width,
            height=height,
            guidance_scale=guidance_scale,
            sampler=sampler,
            seed=seed,
            strength=strength,
            init_url=init_url,
            batch=batch,
            style=style,
            facefix=facefix,
            tiling=tiling,
            highres_fix=highres_fix,
            clip_skip=clip_skip,
            script=script
        )

def setup(bot: discord.Bot):
    bot.add_cog(StableCog(bot))
