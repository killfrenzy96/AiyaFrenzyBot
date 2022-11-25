import asyncio
import discord
import traceback
import time
from threading import Thread

#the queue object for txt2image and img2img
class DrawObject:
    def __init__(self, cog, ctx, prompt, negative_prompt, data_model, steps, width, height, guidance_scale, sampler, seed,
                 strength, init_image, copy_command, batch_count, style, facefix, tiling, clip_skip, simple_prompt, script,
                 view = None, payload = None):
        self.cog = cog
        self.ctx: discord.ApplicationContext | discord.Interaction | discord.Message = ctx
        self.prompt: str = prompt
        self.negative_prompt: str = negative_prompt
        self.data_model: str = data_model
        self.steps: int = steps
        self.width: int = width
        self.height: int = height
        self.guidance_scale: float = guidance_scale
        self.sampler: str = sampler
        self.seed: int = seed
        self.strength: float = strength
        self.init_image: discord.Attachment = init_image
        self.copy_command: str = copy_command
        self.batch_count: int = batch_count
        self.style: str = style
        self.facefix: str = facefix
        self.tiling: bool = tiling
        self.clip_skip: int = clip_skip
        self.simple_prompt: str = simple_prompt
        self.script: str = script
        self.view: discord.ui.View = view
        self.payload = payload

#the queue object for extras - upscale
class UpscaleObject:
    def __init__(self, cog, ctx, resize, init_image, upscaler_1, upscaler_2, upscaler_2_strength, copy_command,
                 view = None, payload = None):
        self.cog = cog
        self.ctx: discord.ApplicationContext = ctx
        self.resize: float = resize
        self.init_image: discord.Attachment = init_image
        self.upscaler_1: str = upscaler_1
        self.upscaler_2: str = upscaler_2
        self.upscaler_2_strength: float = upscaler_2_strength
        self.copy_command: str = copy_command
        self.view: discord.ui.View = view
        self.payload = payload

#the queue object for identify (interrogate)
class IdentifyObject:
    def __init__(self, cog, ctx, init_image, copy_command,
                 view = None, payload = None):
        self.cog = cog
        self.ctx: discord.ApplicationContext = ctx
        self.init_image: discord.Attachment = init_image
        self.copy_command: str = copy_command
        self.view: discord.ui.View = view
        self.payload = payload

#any command that needs to wait on processing should use the dream thread
class GlobalQueue:
    dream_thread = Thread()
    queue_high: list[DrawObject | UpscaleObject | IdentifyObject] = []
    queue_medium: list[DrawObject | UpscaleObject | IdentifyObject] = []
    queue_low: list[DrawObject | UpscaleObject | IdentifyObject] = []
    queue_lowest: list[DrawObject | UpscaleObject | IdentifyObject] = []

    queues: list[list[DrawObject | UpscaleObject | IdentifyObject]] = [queue_high, queue_medium, queue_low, queue_lowest]
    queue_length = 0

# get estimate of the compute cost of a dream
def get_dream_cost(queue_object: DrawObject | UpscaleObject | IdentifyObject):
    if type(queue_object) is DrawObject:
        dream_compute_cost: float = float(queue_object.batch_count)
        dream_compute_cost *= max(1.0, queue_object.steps / 20)
        dream_compute_cost *= pow(max(1.0, (queue_object.width * queue_object.height) / (512 * 512)), 1.25)

        if queue_object.init_image: dream_compute_cost *= max(0.2, queue_object.strength)

        match queue_object.sampler:
            case 'Huen':
                dream_compute_cost *= 2.0
            case 'DPM2':
                dream_compute_cost *= 2.0
            case 'DPM2 a':
                dream_compute_cost *= 2.0
            case 'DPM++ 2S a':
                dream_compute_cost *= 2.0
            case 'DPM2 Karras':
                dream_compute_cost *= 2.0
            case 'DPM2 a Karras':
                dream_compute_cost *= 2.0
            case 'DPM++ 2S a Karras':
                dream_compute_cost *= 2.0

    elif type(queue_object) is UpscaleObject:
        dream_compute_cost = queue_object.resize

    else:
        dream_compute_cost = 1.0

    return dream_compute_cost

def get_user_queue_cost(user_id: int):
    queue_cost = 0.0
    queue = GlobalQueue.queue_high + GlobalQueue.queue_medium + GlobalQueue.queue_low + GlobalQueue.queue_lowest
    for queue_object in queue:
        if queue_object.ctx.author.id == user_id:
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
        GlobalQueue.dream_thread = Thread(target=process_queue)
        GlobalQueue.dream_thread.start()

    if print_info:
        return queue_length


def process_queue():
    queue_index = 0
    while queue_index < len(GlobalQueue.queues):
        queue = GlobalQueue.queues[queue_index]
        if queue:
            queue_object = queue.pop(0)
            try:
                # print(f'Dream started: {queue_object.seed} - {time.time()}')
                queue_object.cog.dream(queue_object)
            except Exception as e:
                print(f'Dream failure:\n{queue_object}\n{e}\n{traceback.print_exc()}')
            queue_index = 0
        else:
            queue_index += 1

class UploadObject:
    def __init__(self, ctx, content, embed = None, files = None, view = None, delete_after = None):
        self.ctx: discord.ApplicationContext = ctx
        self.content: str = content
        self.embed: discord.Embed = embed
        self.files: list[discord.File] = files
        self.view: discord.ui.View = view
        self.delete_after: float = delete_after

class GlobalUploadQueue:
    upload_thread = Thread()
    event_loop = asyncio.get_event_loop()
    queue: list[UploadObject] = []

# upload the image
def process_upload(queue_object: UploadObject):
    # append upload to queue
    GlobalUploadQueue.queue.append(queue_object)

    # start upload queue thread
    if GlobalUploadQueue.upload_thread.is_alive() == False:
        GlobalUploadQueue.upload_thread = Thread(target=process_upload_queue)
        GlobalUploadQueue.upload_thread.start()

def process_upload_queue():
    while GlobalUploadQueue.queue:
        queue_object = GlobalUploadQueue.queue.pop(0)
        try:
            GlobalUploadQueue.event_loop.create_task(
                queue_object.ctx.channel.send(
                    content=queue_object.content,
                    embed=queue_object.embed,
                    files=queue_object.files,
                    view=queue_object.view,
                    delete_after=queue_object.delete_after
                )
            )
        except Exception as e:
            print(f'Upload failure:\n{queue_object}\n{e}\n{traceback.print_exc()}')

def get_guild(ctx: discord.ApplicationContext | discord.Interaction | discord.Message):
    if type(ctx) is discord.ApplicationContext:
        return '% s' % ctx.guild_id
    elif type(ctx) is discord.Interaction:
        return '% s' % ctx.guild.id
    elif type(ctx) is discord.Message:
        return '% s' % ctx.guild.id
    else:
        return 'private'

def get_user(ctx: discord.ApplicationContext | discord.Interaction | discord.Message):
    if type(ctx) is discord.ApplicationContext:
        return ctx.author
    elif type(ctx) is discord.Interaction:
        return ctx.user
    elif type(ctx) is discord.Message:
        return ctx.author
    else:
        return None