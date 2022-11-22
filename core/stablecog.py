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
        'script',
        str,
        description='Generates image batches using a script.',
        required=False,
        choices = ['preset_steps', 'preset_guidance_scales', 'finetune_steps', 'finetune_guidance_scale']
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
                            script: Optional[str] = None):

        negative_prompt: str = negative
        data_model: str = checkpoint
        count: int = batch
        # tiling: bool = False

        # sanatize input strings
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
            'tiling',
            'script'
        ]

        def sanatize(input: str):
            if input:
                input = input.replace('``', ' ')
                for param in params:
                    input = input.replace(f' {param}:', f' {param} ')
            return input

        prompt = sanatize(prompt)
        negative_prompt = sanatize(negative_prompt)
        style = sanatize(style)
        init_url = sanatize(init_url)

        #update defaults with any new defaults from settingscog
        if ctx is discord.ApplicationContext:
            guild = '% s' % ctx.guild_id
        elif ctx.guild:
            guild = '% s' % ctx.guild.id
        else:
            guild = '% s' % 'private'
        if negative_prompt == 'unset':
            negative_prompt = settings.read(guild)['negative_prompt']
        if steps == -1:
            steps = settings.read(guild)['default_steps']
        if count is None:
            count = settings.read(guild)['default_count']
        if sampler == 'unset':
            sampler = settings.read(guild)['sampler']

        #if a model is not selected, do nothing
        model_name = 'Default'
        if data_model is None:
            data_model = settings.read(guild)['data_model']
            if data_model != '':
                self.send_model = True
        else:
            self.send_model = True

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

        print(f'Dream Request -- {ctx.author.name}#{ctx.author.discriminator}')

        if seed == -1: seed = random.randint(0, 0xFFFFFFFF)

        #url *will* override init image for compatibility, can be changed here
        if init_url:
            if init_url.startswith('https://cdn.discordapp.com/') == False:
                await ctx.send_response('Only URL images from the Discord CDN are allowed!')
                return

            try:
                init_image = requests.get(init_url)
            except(Exception,):
                await ctx.send_response('URL image not found!\nI will do my best without it!')

        #increment number of times command is used
        with open('resources/stats.txt', 'r') as f:
            data = list(map(int, f.readlines()))
        data[0] = data[0] + 1
        with open('resources/stats.txt', 'w') as f:
            f.write('\n'.join(str(x) for x in data))

        #random messages for bot to say
        with open('resources/messages.csv') as csv_file:
            message_data = list(csv.reader(csv_file, delimiter='|'))
            message_row_count = len(message_data) - 1
            for row in message_data:
                self.wait_message.append( row[0] )

        #formatting bot initial reply
        append_options = ''

        # get estimate of the compute cost of this dream
        def get_dream_cost(width: int, height: int, steps: int, count: int = 1):
            return queuehandler.get_dream_cost(queuehandler.DrawObject(
                self, ctx, prompt, negative_prompt, data_model, steps, height, width, guidance_scale, sampler, seed, strength, init_image, None, None, count, style, facefix, tiling, simple_prompt, script, None
            ))
        dream_compute_cost = get_dream_cost(width, height, steps, 1)

        # apply script modifications
        increment_seed = 0
        increment_steps = 0
        increment_guidance_scale = 0

        match script:
            case 'preset_steps':
                steps = 20
                increment_steps = 5
                count = 7

                average_step_cost = get_dream_cost(width, height, steps + (increment_steps * count * 0.5), 1)
                if average_step_cost > settings.read(guild)['max_compute_batch']:
                    increment_steps = 10
                    count = 4

            case 'preset_guidance_scales':
                guidance_scale = 4.0
                increment_guidance_scale = 1.0
                count = max(10, count)

            case 'finetune_steps':
                increment_steps = 1
                count = 10

                max_step_cost = get_dream_cost(width, height, steps + (increment_steps * count), 1)
                if max_step_cost > settings.read(guild)['max_compute']:
                    count = min(int(float(count) * (settings.read(guild)['max_compute'] / max_step_cost)), 10)

            case 'finetune_guidance_scale':
                increment_guidance_scale = 0.1
                count = max(10, count)

            case other:
                increment_seed = 1

        #lower step value to the highest setting if user goes over max steps
        if dream_compute_cost > settings.read(guild)['max_compute']:
            steps = min(int(float(steps) * (settings.read(guild)['max_compute'] / dream_compute_cost)), settings.read(guild)['max_steps'])
            append_options = append_options + '\nDream compute cost is too high! Steps reduced to ``' + str(steps) + '``'
        if steps > settings.read(guild)['max_steps']:
            steps = settings.read(guild)['max_steps']
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
            dream_compute_batch_cost = get_dream_cost(width, height, steps, count)
            max_count = settings.read(guild)['max_count']
            if dream_compute_batch_cost > settings.read(guild)['max_compute_batch']:
                count = min(int(float(count) * settings.read(guild)['max_compute_batch'] / dream_compute_batch_cost), max_count)
                append_options = append_options + '\nBatch compute cost is too high! Batch count reduced to ``' + str(count) + '``'
            if count > max_count:
                count = max_count
                append_options = append_options + '\nExceeded maximum of ``' + str(count) + '`` images! This is the best I can do...'
        #     append_options = append_options + '\nCount: ``' + str(count) + '``'
        # if style != 'None':
        #     append_options = append_options + '\nStyle: ``' + str(style) + '``'
        # if facefix != 'None':
        #     append_options = append_options + '\nFace restoration: ``' + str(facefix) + '``'
        # if tiling:
        #     append_options = append_options + '\nTiling: ``' + str(tiling) + '``'

        #log the command
        copy_command = f'/dream prompt:{simple_prompt}'
        if negative_prompt != '':
            copy_command = copy_command + f' negative:{negative_prompt}'
        if data_model and model_name != 'Default':
            copy_command = copy_command + f' checkpoint:{model_name}'
        copy_command = copy_command + f' steps:{steps} width:{width} height:{height} guidance_scale:{guidance_scale} sampler:{sampler} seed:{seed}'
        if init_image:
            copy_command = copy_command + f' strength:{strength} init_url:{init_image.url}'
        if style != 'None':
            copy_command = copy_command + f' style:{style}'
        if facefix != 'None':
            copy_command = copy_command + f' facefix:{facefix}'
        if tiling:
            copy_command = copy_command + f' tiling:{tiling}'
        if count > 1:
            copy_command = copy_command + f' batch:{count}'
        if script:
            copy_command = copy_command + f' script:{script}'
        print(copy_command)

        #set up tuple of parameters to pass into the Discord view
        input_tuple = (ctx, prompt, negative_prompt, data_model, steps, width, height, guidance_scale, sampler, seed, strength, init_image, count, style, facefix, simple_prompt)
        view = viewhandler.DrawView(input_tuple)

        #setup the queue
        content = None
        ephemeral = False

        # calculate total cost of queued items
        dream_cost = get_dream_cost(width, height, steps, count)
        queue_cost = queuehandler.get_user_queue_cost(ctx.author.id)

        print(f'Estimated total compute cost: {dream_cost + queue_cost}')

        if dream_cost + queue_cost > settings.read(guild)['max_compute_queue']:
            print(f'Dream rejected: Too much in queue already')
            content = f'<@{ctx.author.id}> Please wait! You have too much queued up.'
            ephemeral = True
            append_options = ''
        else:
            init_image_encoded = None
            if init_image is not None:
                init_image_encoded = base64.b64encode(requests.get(init_image.url, stream=True).content).decode('utf-8')

            queue_length = len(queuehandler.GlobalQueue.queue_high)
            if queuehandler.GlobalQueue.dream_thread.is_alive(): queue_length += 1
            def get_draw_object():
                return queuehandler.DrawObject(self, ctx, prompt, negative_prompt, data_model, steps, width, height, guidance_scale, sampler, seed, strength, init_image, init_image_encoded, copy_command, 1, style, facefix, tiling, simple_prompt, script, view)

            if count == 1:
                # if user does not have a dream in process, they get high priority
                if queue_cost == 0.0:
                    priority: str = 'high'
                    print(f'Dream priority: High')
                else:
                    priority: str = 'medium'
                    print(f'Dream priority: Medium')
                    queue_length += len(queuehandler.GlobalQueue.queue)

                queuehandler.process_dream(self, get_draw_object(), priority)
            else:
                # batched items go into the low priority queue
                print(f'Dream priority: Low')
                queue_length += len(queuehandler.GlobalQueue.queue)
                queue_length += len(queuehandler.GlobalQueue.queue_low)
                queuehandler.process_dream(self, get_draw_object(), 'low')

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

                    queuehandler.GlobalQueue.queue_low.append(get_draw_object())

            content = f'<@{ctx.author.id}> {self.wait_message[random.randint(0, message_row_count)]} Queue: ``{queue_length}``'
            if count > 1: content = content + f' - Batch: ``{count}``'
            content = content + append_options

        if content:
            try:
                if type(ctx) is discord.ApplicationContext:
                    await ctx.send_response(content=content, ephemeral=ephemeral)
                elif type(ctx) is discord.Interaction:
                    ctx.response.send_message(content=content, ephemeral=ephemeral)
                else:
                    await ctx.reply(content)
            except:
                await ctx.channel.send(content)

    #generate the image
    def dream(self, event_loop: AbstractEventLoop, queue_object: queuehandler.DrawObject):
        try:
            start_time = time.time()

            # create persistent session since we'll need to do a few API calls
            s = requests.Session()
            if settings.global_var.api_auth:
                s.auth = (settings.global_var.api_user, settings.global_var.api_pass)

            # construct a payload for data model, then the normal payload
            model_payload = {
                "sd_model_checkpoint": queue_object.data_model
            }
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
            if queue_object.init_image is not None:
                if queue_object.init_image_encoded:
                    image = queue_object.init_image_encoded
                else:
                    image = base64.b64encode(requests.get(queue_object.init_image.url, stream=True).content).decode('utf-8')
                img_payload = {
                    "init_images": [
                        'data:image/png;base64,' + image
                    ],
                    "denoising_strength": queue_object.strength
                }
                payload.update(img_payload)
            # add any options that would go into the override_settings
            override_settings = {"CLIP_stop_at_last_layers": queue_object.clip_skip}
            if queue_object.facefix != 'None':
                override_settings["face_restoration_model"] = queue_object.facefix
                # face restoration needs this extra parameter
                facefix_payload = {
                    "restore_faces": True,
                }
                payload.update(facefix_payload)

            # send normal payload to webui
            if settings.global_var.gradio_auth:
                login_payload = {
                    'username': settings.global_var.username,
                    'password': settings.global_var.password
                }
                s.post(settings.global_var.url + '/login', data=login_payload)
            else:
                s.post(settings.global_var.url + '/login')

            # update payload with override_settings
            override_payload = {
                "override_settings": override_settings
            }
            payload.update(override_payload)

            # only send model payload if one is defined
            if settings.global_var.send_model:
                s.post(url=f'{settings.global_var.url}/sdapi/v1/options', json=model_payload)
            if queue_object.init_image is not None:
                response = s.post(url=f'{settings.global_var.url}/sdapi/v1/img2img', json=payload)
            else:
                response = s.post(url=f'{settings.global_var.url}/sdapi/v1/txt2img', json=payload)

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

                        # footer_args = dict(text=f'{queue_object.ctx.author.name}#{queue_object.ctx.author.discriminator}')
                        # if queue_object.ctx.author.avatar is not None:
                        #     footer_args['icon_url'] = queue_object.ctx.author.avatar.url
                        # embed.set_footer(**footer_args)

                        for (pil_image, buffer) in zip(pil_images, buffer_handles):
                            pil_image.save(buffer, 'PNG')
                            buffer.seek(0)

                        files = [discord.File(fp=buffer, filename=f'{queue_object.seed}-{i}.png') for (i, buffer) in enumerate(buffer_handles)]
                        # event_loop.create_task(queue_object.ctx.channel.send(content=f'<@{queue_object.ctx.author.id}>', embed=embed, files=files))
                        queuehandler.process_upload(queuehandler.UploadObject(
                            ctx=queue_object.ctx, content=f'<@{queue_object.ctx.author.id}> ``{queue_object.copy_command}``', files=files, view=queue_object.view
                        ))
                except Exception as e:
                    print('txt2img failed (thread)')
                    print(response)
                    embed = discord.Embed(title='txt2img failed', description=f'{e}\n{traceback.print_exc()}', color=settings.global_var.embed_color)
                    queuehandler.process_upload(queuehandler.UploadObject(
                        ctx=queue_object.ctx, content=f'<@{queue_object.ctx.author.id}> ``{queue_object.copy_command}``', embed=embed, files=files
                    ))
            Thread(target=post_dream, daemon=True).start()

        except Exception as e:
            print('txt2img failed (main)')
            embed = discord.Embed(title='txt2img failed', description=f'{e}\n{traceback.print_exc()}', color=settings.global_var.embed_color)
            queuehandler.process_upload(queuehandler.UploadObject(
                ctx=queue_object.ctx, content=f'<@{queue_object.ctx.author.id}> ``{queue_object.copy_command}``', embed=embed
            ))

        queuehandler.process_queue()

def setup(bot: discord.Bot):
    bot.add_cog(StableCog(bot))
