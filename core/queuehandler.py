import asyncio
import discord
import traceback
from threading import Thread

#the queue object for txt2image and img2img
class DrawObject:
    def __init__(self, cog, ctx, prompt, negative_prompt, data_model, steps, width, height, guidance_scale, sampler, seed,
                 strength, init_image, init_image_encoded, copy_command, batch_count, style, facefix, tiling, clip_skip, simple_prompt, script, view):
        self.cog = cog
        self.ctx: discord.ApplicationContext = ctx
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
        self.init_image_encoded: str = init_image_encoded
        self.copy_command: str = copy_command
        self.batch_count: int = batch_count
        self.style: str = style
        self.facefix: str = facefix
        self.tiling: bool = tiling
        self.clip_skip: int = clip_skip
        self.simple_prompt: str = simple_prompt
        self.script: str = script
        self.view = view

#the queue object for extras - upscale
class UpscaleObject:
    def __init__(self, cog, ctx, resize, init_image, init_image_encoded, upscaler_1, upscaler_2, upscaler_2_strength, copy_command, view):
        self.cog = cog
        self.ctx: discord.ApplicationContext = ctx
        self.resize: float = resize
        self.init_image: discord.Attachment = init_image
        self.init_image_encoded: str = init_image_encoded
        self.upscaler_1: str = upscaler_1
        self.upscaler_2: str = upscaler_2
        self.upscaler_2_strength: float = upscaler_2_strength
        self.copy_command: str = copy_command
        self.view = view

#the queue object for identify (interrogate)
class IdentifyObject:
    def __init__(self, cog, ctx, init_image, init_image_encoded, copy_command, view):
        self.cog = cog
        self.ctx: discord.ApplicationContext = ctx
        self.init_image: discord.Attachment = init_image
        self.init_image_encoded: str = init_image_encoded
        self.copy_command: str = copy_command
        self.view = view

#any command that needs to wait on processing should use the dream thread
class GlobalQueue:
    dream_thread = Thread()
    event_loop = asyncio.get_event_loop()
    queue_high: list[DrawObject | UpscaleObject | IdentifyObject] = []
    queue_medium: list[DrawObject | UpscaleObject | IdentifyObject] = []
    queue_low: list[DrawObject | UpscaleObject | IdentifyObject] = []
    queue_lowest: list[DrawObject | UpscaleObject | IdentifyObject] = []

    queues: list[list[DrawObject | UpscaleObject | IdentifyObject]] = [queue_high, queue_medium, queue_low, queue_lowest]

#this creates the master queue that oversees all queues
def union(list_1, list_2, list_3):
    master_queue = list_1 + list_2 + list_3
    return master_queue

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
                queue_object.cog.dream(GlobalQueue.event_loop, queue_object)
            except Exception as e:
                print(f'Dream failure:\n{queue_object}\n{e}\n{traceback.print_exc()}')
            queue_index = 0
        else:
            queue_index += 1

class UploadObject:
    def __init__(self, ctx, content, embed = None, files = None, view = None):
        self.ctx: discord.ApplicationContext = ctx
        self.content: str = content
        self.embed: discord.Embed = embed
        self.files: list[discord.File] = files
        self.view = view

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
                    view=queue_object.view
                )
            )
        except Exception as e:
            print(f'Upload failure:\n{queue_object}\n{e}\n{traceback.print_exc()}')

