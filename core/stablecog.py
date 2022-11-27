import base64
import contextlib
import csv
import discord
import io
import random
import requests
import time
import traceback
import asyncio
from threading import Thread
from asyncio import AbstractEventLoop
from PIL import Image, PngImagePlugin
from discord import option
from discord.ext import commands
from typing import Optional

from core import queuehandler
from core import viewhandler
from core import settings


class StableCog(commands.Cog, name='Stable Diffusion', description='Create images from natural language.'):
    ctx_parse = discord.ApplicationContext
    def __init__(self, bot):
        self.wait_message: list[str] = []
        self.bot: discord.Bot = bot
        self.send_model = False

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(viewhandler.DrawView(self))

    #pulls from model_names list and makes some sort of dynamic list to bypass Discord 25 choices limit
    def model_autocomplete(self: discord.AutocompleteContext):
        return [
            model for model in settings.global_var.model_names
        ]
    #and for styles
    def style_autocomplete(self: discord.AutocompleteContext):
        return [
            style for style in settings.global_var.style_names
        ]

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
        description='The number of images to generate. This is "Batch count", not "Batch size".',
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
                            prompt: str, negative: str = 'unset',
                            checkpoint: Optional[str] = None,
                            steps: Optional[int] = -1,
                            width: Optional[int] = 512, height: Optional[int] = 512,
                            guidance_scale: Optional[float] = 7.0,
                            sampler: Optional[str] = 'unset',
                            seed: Optional[int] = -1,
                            strength: Optional[float] = 0.75,
                            init_image: Optional[discord.Attachment] = None,
                            init_url: Optional[str],
                            batch: Optional[int] = None,
                            style: Optional[str] = 'None',
                            facefix: Optional[str] = 'None',
                            tiling: Optional[bool] = False,
                            highres_fix: Optional[bool] = False,
                            clip_skip: Optional[int] = 0,
                            script: Optional[str] = None):
        try:
            negative_prompt: str = negative
            data_model: str = checkpoint
            count: int = batch
            copy_command: str = None

            # sanatize input strings
            def sanatize(input: str):
                if input:
                    input = input.replace('``', ' ')
                    input = input.replace('\n', ' ')
                    for param in self.dream_params:
                        input = input.replace(f' {param}:', f' {param} ')
                return input

            prompt = sanatize(prompt)
            negative_prompt = sanatize(negative_prompt)
            style = sanatize(style)
            init_url = sanatize(init_url)

            #get guild id and user
            guild = queuehandler.get_guild(ctx)
            user = queuehandler.get_user(ctx)

            #update defaults with any new defaults from settingscog
            if negative_prompt == 'unset':
                negative_prompt = settings.read(guild)['negative_prompt']
            if steps == -1:
                steps = settings.read(guild)['default_steps']
            if count is None:
                count = settings.read(guild)['default_count']
            if sampler == 'unset':
                sampler = settings.read(guild)['sampler']
            if clip_skip == 0:
                clip_skip = settings.read(guild)['clip_skip']

            #if a model is not selected, do nothing
            model_name = 'Default'
            settings.global_var.send_model = False
            if data_model is None:
                data_model = settings.read(guild)['data_model']
                if data_model != '':
                    settings.global_var.send_model = True
            else:
                settings.global_var.send_model = True

            simple_prompt = prompt
            #take selected data_model and get model_name, then update data_model with the full name
            with open('resources/models.csv', 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter='|')
                for row in reader:
                    if row['display_name'] == data_model or row['model_full_name'] == data_model:
                        model_name = row['display_name']
                        data_model = row['model_full_name']
                        #look at the model for activator token and prepend prompt with it
                        prompt = row['activator_token'] + " " + prompt
                        #if there's no activator token, remove the extra blank space
                        prompt = prompt.lstrip(' ')
                        break

            print(f'Dream Request -- {user.name}#{user.discriminator} -- {guild}')

            if seed == -1: seed = random.randint(0, 0xFFFFFFFF)

            #url *will* override init image for compatibility, can be changed here
            if init_url:
                if init_url.startswith('https://cdn.discordapp.com/') == False:
                    await ctx.send_response('Only URL images from the Discord CDN are allowed!')
                    return

                try:
                    # init_image = requests.get(init_url)
                    loop = asyncio.get_event_loop()
                    image_future = loop.run_in_executor(None, requests.get, init_url)
                    init_image = await image_future
                except(Exception,):
                    await ctx.send_response('URL image not found!\nI will do my best without it!')

            #increment number of times command is used
            with open('resources/stats.txt', 'r') as f:
                data = list(map(int, f.readlines()))
            data[0] = data[0] + 1
            with open('resources/stats.txt', 'w') as f:
                f.write('\n'.join(str(x) for x in data))

            #random messages for aiya to say
            with open('resources/messages.csv') as csv_file:
                message_data = list(csv.reader(csv_file, delimiter='|'))
                message_row_count = len(message_data) - 1
                for row in message_data:
                    self.wait_message.append( row[0] )

            #formatting aiya initial reply
            append_options = ''

            def get_draw_object_args():
                return (self, ctx, prompt, negative_prompt, model_name, data_model,
                        steps, width, height, guidance_scale, sampler, seed,
                        strength, init_image, copy_command, count, style,
                        facefix, tiling, highres_fix, clip_skip, simple_prompt,
                        script)

            # get estimate of the compute cost of this dream
            def get_dream_cost(_width: int, _height: int, _steps: int, _count: int = 1):
                args = get_draw_object_args()
                dream_cost_draw_object = queuehandler.DrawObject(*args)
                dream_cost_draw_object.width = _width
                dream_cost_draw_object.height = _height
                dream_cost_draw_object.steps = _steps
                dream_cost_draw_object.batch_count = _count
                return queuehandler.get_dream_cost(dream_cost_draw_object)
            dream_compute_cost = get_dream_cost(width, height, steps, 1)

            #get settings
            setting_max_compute = settings.read(guild)['max_compute']
            setting_max_compute_batch = settings.read(guild)['max_compute_batch']
            setting_max_steps = settings.read(guild)['max_steps']

            # apply script modifications
            increment_seed = 0
            increment_steps = 0
            increment_guidance_scale = 0
            increment_clip_skip = 0

            match script:
                case None:
                    increment_seed = 1

                case 'preset steps':
                    steps = 10
                    increment_steps = 5
                    count = 9

                    average_step_cost = get_dream_cost(width, height, steps + (increment_steps * count * 0.5), count)
                    if average_step_cost > setting_max_compute_batch:
                        increment_steps = 10
                        count = 5

                case 'preset guidance_scale':
                    guidance_scale = 5.0
                    increment_guidance_scale = 1.0
                    count = max(10, count)

                    if dream_compute_cost * count > setting_max_compute_batch:
                        count = int(count / 2)
                        increment_guidance_scale = 2.0

                case 'preset clip_skip':
                    clip_skip = 1
                    increment_clip_skip = 1
                    count = max(6, min(12, count))

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
                                    count = max(5, count)
                                case 'guidance_scale':
                                    increment_guidance_scale = script_value
                                    if increment_guidance_scale < 1.0:
                                        count = max(10, count)
                                    else:
                                        count = max(4, count)
                                case 'clip_skip':
                                    increment_clip_skip = int(script_value)
                                    count = max(4, count)
                                    clip_skip_max = clip_skip + (count * increment_clip_skip)
                                    if clip_skip_max > 12:
                                        count = clip_skip_max - 12
                    except:
                        append_options = append_options + '\nInvalid script. I will ignore the script parameter.'
                        increment_seed = 1
                        increment_steps = 0
                        increment_guidance_scale = 0
                        increment_clip_skip = 0

            #lower step value to the highest setting if user goes over max steps
            if dream_compute_cost > setting_max_compute:
                steps = min(int(float(steps) * (setting_max_compute / dream_compute_cost)), setting_max_steps)
                append_options = append_options + '\nDream compute cost is too high! Steps reduced to ``' + str(steps) + '``'
            if steps > setting_max_steps:
                steps = setting_max_steps
                append_options = append_options + '\nExceeded maximum of ``' + str(steps) + '`` steps! This is the best I can do...'
            # if model_name != 'Default':
            #     append_options = append_options + '\nModel: ``' + str(model_name) + '``'
            # if negative_prompt != '':
            #     append_options = append_options + '\nNegative Prompt: ``' + str(negative_prompt) + '``'
            # if width != 512:
            #     append_options = append_options + '\nWidth: ``' + str(width) + '``'
            # if height != 512:
            #     append_options = append_options + '\nHeight: ``' + str(height) + '``'
            # if guidance_scale != 7.0:
            #     append_options = append_options + '\nGuidance Scale: ``' + str(guidance_scale) + '``'
            # if sampler != 'Euler a':
            #     append_options = append_options + '\nSampler: ``' + str(sampler) + '``'
            # if init_image:
            #     append_options = append_options + '\nStrength: ``' + str(strength) + '``'
            #     append_options = append_options + '\nURL Init Image: ``' + str(init_image.url) + '``'
            if count != 1:
                if increment_steps:
                    dream_compute_batch_cost = get_dream_cost(width, height, steps + (increment_steps * count * 0.5), count)
                else:
                    dream_compute_batch_cost = get_dream_cost(width, height, steps, count)
                setting_max_count = settings.read(guild)['max_count']
                if dream_compute_batch_cost > setting_max_compute_batch:
                    count = min(int(float(count) * setting_max_compute_batch / dream_compute_batch_cost), setting_max_count)
                    append_options = append_options + '\nBatch compute cost is too high! Batch count reduced to ``' + str(count) + '``'
                if count > setting_max_count:
                    count = setting_max_count
                    append_options = append_options + '\nExceeded maximum of ``' + str(count) + '`` images! This is the best I can do...'
            #     append_options = append_options + '\nCount: ``' + str(count) + '``'
            # if style != 'None':
            #     append_options = append_options + '\nStyle: ``' + str(style) + '``'
            # if facefix != 'None':
            #     append_options = append_options + '\nFace restoration: ``' + str(facefix) + '``'
            # if tiling:
            #     append_options = append_options + '\nTiling: ``' + str(tiling) + '``'
            # if highres_fix:
            #     append_options = append_options + '\High-res fix: ``' + str(highres_fix) + '``'
            # if clip_skip != 1:
            #     append_options = append_options + f'\nCLIP skip: ``{clip_skip}``'

            #log the command
            copy_command = f'/dream prompt:{simple_prompt}'
            if negative_prompt != '':
                copy_command = copy_command + f' negative:{negative_prompt}'
            if data_model and model_name != 'Default':
                copy_command = copy_command + f' checkpoint:{model_name}'
            copy_command = copy_command + f' width:{width} height:{height} steps:{steps} guidance_scale:{guidance_scale} sampler:{sampler} seed:{seed}'
            if init_image:
                copy_command = copy_command + f' strength:{strength} init_url:{init_image.url}'
            if style != 'None':
                copy_command = copy_command + f' style:{style}'
            if facefix != 'None':
                copy_command = copy_command + f' facefix:{facefix}'
            if tiling:
                copy_command = copy_command + f' tiling:{tiling}'
            if highres_fix:
                copy_command = copy_command + f' highres_fix:{highres_fix}'
            if clip_skip != 1:
                copy_command = copy_command + f' clip_skip:{clip_skip}'
            if count > 1:
                copy_command = copy_command + f' batch:{count}'
            if script:
                copy_command = copy_command + f' script:{script}'
            print(copy_command)

            #setup the queue
            content = None
            ephemeral = False

            # calculate total cost of queued items
            dream_cost = get_dream_cost(width, height, steps, count)
            queue_cost = queuehandler.get_user_queue_cost(user.id)

            print(f'Estimated total compute cost: {dream_cost + queue_cost}')

            if dream_cost + queue_cost > settings.read(guild)['max_compute_queue']:
                print(f'Dream rejected: Too much in queue already')
                content = f'<@{user.id}> Please wait! You have too much queued up.'
                ephemeral = True
                append_options = ''
            else:
                image = None
                if init_image is not None:
                    try:
                        image = base64.b64encode(init_image.content).decode('utf-8')
                    except:
                        loop = asyncio.get_event_loop()
                        image_future = loop.run_in_executor(None, requests.get, init_image.url)
                        image_response = await image_future
                        image = base64.b64encode(image_response.content).decode('utf-8')
                        # image = base64.b64encode(requests.get(init_image.url, stream=True).content).decode('utf-8')

                def get_draw_object():
                    args = get_draw_object_args()
                    queue_object = queuehandler.DrawObject(*args)
                    queue_object.batch_count = 1

                    #set up tuple of parameters to pass into the Discord view
                    queue_object.view = viewhandler.DrawView(args)

                    # create persistent session since we'll need to do a few API calls
                    s = requests.Session()
                    if settings.global_var.api_auth:
                        s.auth = (settings.global_var.api_user, settings.global_var.api_pass)

                    # construct a payload
                    payload = {
                        "prompt": queue_object.prompt,
                        "negative_prompt": queue_object.negative_prompt,
                        "steps": queue_object.steps,
                        "width": queue_object.width,
                        "height": queue_object.height,
                        "cfg_scale": queue_object.guidance_scale,
                        "sampler_index": queue_object.sampler,
                        "seed": queue_object.seed,
                        "seed_resize_from_h": 0,
                        "seed_resize_from_w": 0,
                        "denoising_strength": None,
                        "tiling": queue_object.tiling,
                        "n_iter": queue_object.batch_count,
                        "styles": [
                            queue_object.style
                        ]
                    }

                    # update payload is init_img or init_url is used
                    if queue_object.init_image is not None:
                        img_payload = {
                            "init_images": [
                                'data:image/png;base64,' + image
                            ],
                            "denoising_strength": queue_object.strength
                        }
                        payload.update(img_payload)

                    # update payload if high-res fix is used
                    if queue_object.highres_fix:
                        highres_payload = {
                            "enable_hr": queue_object.highres_fix,
                            "denoising_strength": queue_object.strength
                        }
                        payload.update(highres_payload)

                    # add any options that would go into the override_settings
                    override_settings = {"CLIP_stop_at_last_layers": queue_object.clip_skip}
                    if queue_object.facefix != 'None':
                        override_settings["face_restoration_model"] = queue_object.facefix
                        # face restoration needs this extra parameter
                        facefix_payload = {
                            "restore_faces": True,
                        }
                        payload.update(facefix_payload)

                    # update payload with override_settings
                    override_payload = {
                        "override_settings": override_settings
                    }
                    payload.update(override_payload)

                    queue_object.payload = payload
                    return queue_object

                if count == 1:
                    if guild == 'private':
                        priority: str = 'lowest'
                    # if user does not have a dream in process, they get high priority
                    elif queue_cost == 0.0:
                        priority: str = 'high'
                    else:
                        priority: str = 'medium'

                    queue_length = queuehandler.process_dream(self, get_draw_object(), priority)
                else:
                    if guild == 'private':
                        priority: str = 'lowest'
                    # batched items go into the low priority queue
                    else:
                        priority: str = 'low'
                    queue_length = queuehandler.process_dream(self, get_draw_object(), priority)

                    batch_count = 1
                    while batch_count < count:
                        batch_count += 1
                        copy_command = f'#{batch_count}`` ``'

                        if increment_seed:
                            seed += increment_seed
                            copy_command = copy_command + f'seed:{seed}'

                        if increment_steps:
                            steps += increment_steps
                            copy_command = copy_command + f'steps:{steps}'

                        if increment_guidance_scale:
                            guidance_scale += increment_guidance_scale
                            guidance_scale = round(guidance_scale, 4)
                            copy_command = copy_command + f'guidance_scale:{guidance_scale}'

                        if increment_clip_skip:
                            clip_skip += increment_clip_skip
                            copy_command = copy_command + f'clip_skip:{clip_skip}'

                        queuehandler.process_dream(self, get_draw_object(), priority, False)

                content = f'<@{user.id}> {self.wait_message[random.randint(0, message_row_count)]} Queue: ``{queue_length}``'
                if count > 1: content = content + f' - Batch: ``{count}``'
                content = content + append_options
        except Exception as e:
            print('dream failed')
            print(f'{e}\n{traceback.print_exc()}')
            content = f'dream failed\n{e}\n{traceback.print_exc()}'
            ephemeral = True

        if content:
            if ephemeral:
                delete_after = 30
            else:
                delete_after = 120
            try:
                if type(ctx) is discord.ApplicationContext:
                    await ctx.send_response(content=content, ephemeral=ephemeral, delete_after=delete_after)
                elif type(ctx) is discord.Interaction:
                    await ctx.response.send_message(content=content, ephemeral=ephemeral, delete_after=delete_after)
                else:
                    await ctx.reply(content, delete_after=delete_after)
            except:
                await ctx.channel.send(content, delete_after=delete_after)

    #generate the image
    def dream(self, queue_object: queuehandler.DrawObject):
        user = queuehandler.get_user(queue_object.ctx)

        try:
            start_time = time.time()

            # create persistent session since we'll need to do a few API calls
            s = requests.Session()
            if settings.global_var.api_auth:
                s.auth = (settings.global_var.api_user, settings.global_var.api_pass)

            # construct a payload for data model
            model_payload = {
                "sd_model_checkpoint": queue_object.data_model
            }

            # send normal payload to webui
            if settings.global_var.gradio_auth:
                login_payload = {
                    'username': settings.global_var.username,
                    'password': settings.global_var.password
                }
                s.post(settings.global_var.url + '/login', data=login_payload)
            # else:
            #     s.post(settings.global_var.url + '/login')

            # only send model payload if one is defined
            if settings.global_var.send_model:
                s.post(url=f'{settings.global_var.url}/sdapi/v1/options', json=model_payload)

            if queue_object.init_image is not None:
                url = f'{settings.global_var.url}/sdapi/v1/img2img'
            else:
                url = f'{settings.global_var.url}/sdapi/v1/txt2img'
            response = s.post(url=url, json=queue_object.payload)
            queue_object.payload = None

            def post_dream():
                try:
                    response_data = response.json()
                    end_time = time.time()

                    #create safe/sanitized filename
                    keep_chars = (' ', '.', '_')
                    file_name = "".join(c for c in queue_object.prompt if c.isalnum() or c in keep_chars).rstrip()

                    # save local copy of image and prepare PIL images
                    pil_images = []
                    for i, image_base64 in enumerate(response_data['images']):
                        image = Image.open(io.BytesIO(base64.b64decode(image_base64.split(",",1)[0])))
                        pil_images.append(image)

                        # grab png info
                        png_payload = {
                            "image": "data:image/png;base64," + image_base64
                        }
                        png_response = s.post(url=f'{settings.global_var.url}/sdapi/v1/png-info', json=png_payload)

                        metadata = PngImagePlugin.PngInfo()
                        epoch_time = int(time.time())
                        metadata.add_text("parameters", png_response.json().get("info"))
                        file_path = f'{settings.global_var.dir}/{epoch_time}-{queue_object.seed}-{file_name[0:120]}-{i}.png'
                        image.save(file_path, pnginfo=metadata)
                        print(f'Saved image: {file_path}')

                    # post to discord
                    with contextlib.ExitStack() as stack:
                        buffer_handles = [stack.enter_context(io.BytesIO()) for _ in pil_images]

                        # embed = discord.Embed()
                        # embed.colour = settings.global_var.embed_color

                        # image_count = len(pil_images)
                        # noun_descriptor = "drawing" if image_count == 1 else f'{image_count} drawings'
                        # embed.add_field(name=f'My {noun_descriptor} of', value=f'``{queue_object.simple_prompt}``', inline=False)

                        # embed.add_field(name='took me', value='``{0:.3f}`` seconds'.format(end_time-start_time), inline=False)

                        # footer_args = dict(text=f'{user.name}#{user.discriminator}')
                        # if user.avatar is not None:
                        #     footer_args['icon_url'] = user.avatar.url
                        # embed.set_footer(**footer_args)

                        for (pil_image, buffer) in zip(pil_images, buffer_handles):
                            pil_image.save(buffer, 'PNG')
                            buffer.seek(0)

                        files = [discord.File(fp=buffer, filename=f'{queue_object.seed}-{i}.png') for (i, buffer) in enumerate(buffer_handles)]
                        # event_loop.create_task(queue_object.ctx.channel.send(content=f'<@{user.id}>', embed=embed, files=files))
                        queuehandler.process_upload(queuehandler.UploadObject(
                            ctx=queue_object.ctx, content=f'<@{user.id}> ``{queue_object.copy_command}``', files=files, view=queue_object.view
                        ))
                        queue_object.view = None
                except Exception as e:
                    print('txt2img failed (thread)')
                    print(response)
                    embed = discord.Embed(title='txt2img failed', description=f'{e}\n{traceback.print_exc()}', color=settings.global_var.embed_color)
                    queuehandler.process_upload(queuehandler.UploadObject(
                        ctx=queue_object.ctx, content=f'<@{user.id}> ``{queue_object.copy_command}``', embed=embed
                    ))
            Thread(target=post_dream, daemon=True).start()

        except Exception as e:
            print('txt2img failed (main)')
            embed = discord.Embed(title='txt2img failed', description=f'{e}\n{traceback.print_exc()}', color=settings.global_var.embed_color)
            queuehandler.process_upload(queuehandler.UploadObject(
                ctx=queue_object.ctx, content=f'<@{user.id}> ``{queue_object.copy_command}``', embed=embed
            ))

    async def dream_object(self, draw_object: queuehandler.DrawObject):
        if draw_object.init_image:
            init_url = draw_object.init_image.url
        else:
            init_url = None

        await self.dream_handler(ctx=draw_object.ctx,
            prompt=draw_object.prompt,
            negative=draw_object.negative_prompt,
            checkpoint=draw_object.model_name,
            width=draw_object.width,
            height=draw_object.height,
            guidance_scale=draw_object.guidance_scale,
            steps=draw_object.steps,
            sampler=draw_object.sampler,
            seed=draw_object.seed,
            init_image=draw_object.init_image,
            init_url=init_url,
            strength=draw_object.strength,
            batch=draw_object.batch_count,
            style=draw_object.style,
            facefix=draw_object.facefix,
            tiling=draw_object.tiling,
            highres_fix=draw_object.highres_fix,
            clip_skip=draw_object.clip_skip,
            script=draw_object.script
        )

    async def dream_command(self, ctx: discord.ApplicationContext | discord.Message | discord.Interaction, command: str, randomize_seed = True):
        queue_object = self.get_draw_object_from_command(command)

        queue_object.ctx = ctx
        if randomize_seed:
            queue_object.seed = -1

        await self.dream_object(queue_object)

    def get_draw_object_from_command(self, command: str):
        def find_between(s: str, first: str, last: str):
            try:
                start = s.index(first) + len(first)
                end = s.index(last, start)
                return s[start:end]
            except ValueError:
                return ''

        command = '\n\n ' + command + '\n\n'

        for param in self.dream_params:
            command = command.replace(f' {param}:', f'\n\n{param}\n')
        command = command.replace('``', '\n\n')

        def get_param(param):
            result = find_between(command, f'\n{param}\n', '\n\n')
            return result.strip()

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
            if sampler not in settings.global_var.sampler_names: sampler = 'unset'
        except:
            sampler = 'unset'

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

        class simple_init_image: url: str
        init_url = get_param('init_url')
        if init_url == '':
            init_image = None
            init_url = None
        else:
            init_image = simple_init_image()
            init_image.url = init_url

        style = get_param('style')
        if style not in settings.global_var.style_names: style = 'None'

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
            negative_prompt=negative,
            model_name=checkpoint,
            data_model=checkpoint,
            steps=steps,
            width=width,
            height=height,
            guidance_scale=guidance_scale,
            sampler=sampler,
            seed=seed,
            strength=strength,
            init_image=init_image,
            copy_command=None,
            batch_count=batch,
            style=style,
            facefix=facefix,
            tiling=tiling,
            highres_fix=highres_fix,
            clip_skip=clip_skip,
            simple_prompt=prompt,
            script=script
        )

def setup(bot: discord.Bot):
    bot.add_cog(StableCog(bot))
