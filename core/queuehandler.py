import asyncio
import discord
import traceback
import time
import requests
import threading

from core import settings

#the queue object for txt2image and img2img
class DrawObject:
    def __init__(self, cog, ctx, prompt, negative, model_name, data_model, steps, width, height, guidance_scale, sampler, seed,
                 strength, init_url, batch, style, facefix, tiling, highres_fix, clip_skip, script,
                 view = None, message = None, cache = True, payload = None):
        self.cog = cog
        self.ctx: discord.ApplicationContext | discord.Interaction | discord.Message = ctx
        self.prompt: str = prompt
        self.negative: str = negative
        self.model_name: str = model_name
        self.data_model: str = data_model
        self.steps: int = steps
        self.width: int = width
        self.height: int = height
        self.guidance_scale: float = guidance_scale
        self.sampler: str = sampler
        self.seed: int = seed
        self.strength: float = strength
        self.init_url: str = init_url
        self.batch: int = batch
        self.style: str = style
        self.facefix: str = facefix
        self.tiling: bool = tiling
        self.highres_fix: bool = highres_fix
        self.clip_skip: int = clip_skip
        self.script: str = script
        self.view: discord.ui.View = view
        self.message: str = message
        self.cache: bool = cache
        self.payload = payload

    def get_command(self):
        command = f'/dream prompt:{self.prompt}'
        if self.negative != '':
            command += f' negative:{self.negative}'
        if self.data_model and self.model_name != 'Default':
            command += f' checkpoint:{self.model_name}'
        command += f' width:{self.width} height:{self.height} steps:{self.steps} guidance_scale:{self.guidance_scale} sampler:{self.sampler} seed:{self.seed}'
        if self.init_url:
            command += f' strength:{self.strength} init_url:{self.init_url}'
        if self.style != None:
            command += f' style:{self.style}'
        if self.facefix != None:
            command += f' facefix:{self.facefix}'
        if self.tiling:
            command += f' tiling:{self.tiling}'
        if self.highres_fix:
            command += f' highres_fix:{self.highres_fix}'
        if self.clip_skip != 1:
            command += f' clip_skip:{self.clip_skip}'
        if self.batch > 1:
            command += f' batch:{self.batch}'
        if self.script:
            command += f' script:{self.script}'
        return command

#the queue object for extras - upscale
class UpscaleObject:
    def __init__(self, cog, ctx, resize, init_url, upscaler_1, upscaler_2, upscaler_2_strength, command,
                 gfpgan, codeformer, upscale_first,
                 view = None, payload = None):
        self.cog = cog
        self.ctx: discord.ApplicationContext = ctx
        self.resize: float = resize
        self.init_url: str = init_url
        self.upscaler_1: str = upscaler_1
        self.upscaler_2: str = upscaler_2
        self.upscaler_2_strength: float = upscaler_2_strength
        self.command: str = command
        self.gfpgan: float = gfpgan
        self.codeformer: float = codeformer
        self.upscale_first: bool = upscale_first
        self.view: discord.ui.View = view
        self.payload = payload

#the queue object for identify (interrogate)
class IdentifyObject:
    def __init__(self, cog, ctx, init_url, model, command,
                 view = None, payload = None):
        self.cog = cog
        self.ctx: discord.ApplicationContext = ctx
        self.init_url: str = init_url
        self.model: str = model
        self.command: str = command
        self.view: discord.ui.View = view
        self.payload = payload

#any command that needs to wait on processing should use the dream thread
class GlobalQueue:
    dream_thread = threading.Thread()
    queue_high: list[DrawObject | UpscaleObject | IdentifyObject] = []
    queue_medium: list[DrawObject | UpscaleObject | IdentifyObject] = []
    queue_low: list[DrawObject | UpscaleObject | IdentifyObject] = []
    queue_lowest: list[DrawObject | UpscaleObject | IdentifyObject] = []

    queues: list[list[DrawObject | UpscaleObject | IdentifyObject]] = [queue_high, queue_medium, queue_low, queue_lowest]
    queue_length = 0

    slow_samplers = [
        'Heun', 'DPM2', 'DPM2 a', 'DPM++ 2S a',
        'DPM2 Karras', 'DPM2 a Karras', 'DPM++ 2S a Karras',
        'DPM++ SDE', 'DPM++ SDE Karras']

# get estimate of the compute cost of a dream
def get_dream_cost(queue_object: DrawObject | UpscaleObject | IdentifyObject):
    if type(queue_object) is DrawObject:
        dream_compute_cost_add = 0.0
        dream_compute_cost = float(queue_object.steps) / 20.0
        if queue_object.sampler in GlobalQueue.slow_samplers: dream_compute_cost *= 2.0
        if queue_object.highres_fix: dream_compute_cost_add = dream_compute_cost
        dream_compute_cost *= pow(max(1.0, float(queue_object.width * queue_object.height) / float(512 * 512)), 1.25)
        if queue_object.init_url: dream_compute_cost *= max(0.2, queue_object.strength)
        dream_compute_cost += dream_compute_cost_add
        dream_compute_cost = max(1.0, dream_compute_cost)
        dream_compute_cost *= float(queue_object.batch)

    elif type(queue_object) is UpscaleObject:
        dream_compute_cost = queue_object.resize

    elif type(queue_object) is IdentifyObject:
        dream_compute_cost = 1.0
        if queue_object.model == 'combined': dream_compute_cost *= len(settings.global_var.identify_models)

    return dream_compute_cost

def get_user_queue_cost(user_id: int):
    queue_cost = 0.0
    queue = GlobalQueue.queue_high + GlobalQueue.queue_medium + GlobalQueue.queue_low + GlobalQueue.queue_lowest
    for queue_object in queue:
        user = get_user(queue_object.ctx)
        if user and user.id == user_id:
            queue_cost += get_dream_cost(queue_object)
    return queue_cost

def process_dream(self, queue_object: DrawObject | UpscaleObject | IdentifyObject, priority: str | int = 1, print_info = True):
    if type(priority) is str:
        match priority:
            case 'high': priority = 0
            case 'medium': priority = 1
            case 'low': priority = 2
            case 'lowest': priority = 3

    if print_info:
        # get queue length
        queue_index = 0
        queue_length = 0
        while queue_index <= priority:
            queue_length += len(GlobalQueue.queues[queue_index])
            queue_index += 1
        if GlobalQueue.dream_thread.is_alive(): queue_length += 1

        match priority:
            case 0: priority_string = 'High'
            case 1: priority_string = 'Medium'
            case 2: priority_string = 'Low'
            case 3: priority_string = 'Lowest'
        print(f'Dream Priority: {priority_string} - Queue: {queue_length}')

    # append dream to queue
    if type(priority) is int:
        GlobalQueue.queues[priority].append(queue_object)

    # start dream queue thread
    if GlobalQueue.dream_thread.is_alive() == False:
        GlobalQueue.dream_thread = threading.Thread(target=process_queue, daemon=True)
        GlobalQueue.dream_thread.start()

    if print_info:
        return queue_length

def get_progress():
    try:
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

        url = f'{settings.global_var.url}/sdapi/v1/progress'
        response = s.get(url=url)
        return response.json()
    except:
        return None

def process_queue():
    queue_index = 0
    active_thread = threading.Thread()
    buffer_thread = threading.Thread()

    while queue_index < len(GlobalQueue.queues):
        queue = GlobalQueue.queues[queue_index]
        if queue:
            queue_object = queue.pop(0)
            try:
                # start next dream
                # queue_object.cog.dream(queue_object)

                # queue up dream while the current one is running
                if active_thread.is_alive() and buffer_thread.is_alive():
                    active_thread.join()
                    active_thread = buffer_thread
                    buffer_thread = threading.Thread()
                if active_thread.is_alive():
                    buffer_thread = active_thread

                active_thread_event = threading.Event()
                active_thread = threading.Thread(target=queue_object.cog.dream, args=[queue_object, active_thread_event], daemon=True)
                active_thread.start()

                # wait for thread to complete, or event (indicating it is safe to continue)
                def wait_for_join():
                    active_thread.join()
                    active_thread_event.set()
                wait_thread_join = threading.Thread(target=wait_for_join, daemon=True)
                wait_thread_join.start()
                active_thread_event.wait()

            except Exception as e:
                print(f'Dream failure:\n{queue_object}\n{e}\n{traceback.print_exc()}')
            queue_index = 0
        else:
            queue_index += 1

class UploadObject:
    def __init__(self, queue_object, content, embed = None, files = None, view = None, delete_after = None):
        self.queue_object: DrawObject | UpscaleObject | IdentifyObject = queue_object
        self.content: str = content
        self.embed: discord.Embed = embed
        self.files: list[discord.File] = files
        self.view: discord.ui.View = view
        self.delete_after: float = delete_after

class GlobalUploadQueue:
    upload_thread = threading.Thread()
    event_loop = asyncio.get_event_loop()
    queue: list[UploadObject] = []

# upload the image
def process_upload(queue_object: UploadObject):
    # append upload to queue
    GlobalUploadQueue.queue.append(queue_object)

    # start upload queue thread
    if GlobalUploadQueue.upload_thread.is_alive() == False:
        GlobalUploadQueue.upload_thread = threading.Thread(target=process_upload_queue, daemon=True)
        GlobalUploadQueue.upload_thread.start()

def process_upload_queue():
    async def run():
        while GlobalUploadQueue.queue:
            upload_object = GlobalUploadQueue.queue.pop(0)
            try:
                # send message
                message = await upload_object.queue_object.ctx.channel.send(
                    content=upload_object.content,
                    embed=upload_object.embed,
                    files=upload_object.files,
                    view=upload_object.view,
                    delete_after=upload_object.delete_after
                )

                # cache command
                if type(upload_object.queue_object) is DrawObject and upload_object.queue_object.cache:
                    settings.append_dream_command(message.id, upload_object.queue_object.get_command())

            except Exception as e:
                print(f'Upload failure:\n{upload_object}\n{e}\n{traceback.print_exc()}')
    GlobalUploadQueue.event_loop.create_task(run())

def get_guild(ctx: discord.ApplicationContext | discord.Interaction | discord.Message):
    try:
        if type(ctx) is discord.ApplicationContext:
            if ctx.guild_id:
                return '% s' % ctx.guild_id
            else:
                return 'private'
        elif type(ctx) is discord.Interaction:
            return '% s' % ctx.guild.id
        elif type(ctx) is discord.Message:
            return '% s' % ctx.guild.id
        else:
            return 'private'
    except:
        return 'private'

def get_user(ctx: discord.ApplicationContext | discord.Interaction | discord.Message):
    try:
        if type(ctx) is discord.ApplicationContext:
            return ctx.author
        elif type(ctx) is discord.Interaction:
            return ctx.user
        elif type(ctx) is discord.Message:
            return ctx.author
        else:
            return ctx.author
    except:
        return None