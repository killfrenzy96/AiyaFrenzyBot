import asyncio
import discord
from threading import Thread

#the queue object for txt2image and img2img
class DrawObject:
    def __init__(self, cog, ctx, prompt, negative_prompt, data_model, steps, width, height, guidance_scale, sampler, seed,
                 strength, init_image, init_image_encoded, copy_command, batch_count, style, facefix, tiling, simple_prompt, script, view):
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
        self.simple_prompt: str = simple_prompt
        self.script: str = script
        self.view = view

#the queue object for extras - upscale
class UpscaleObject:
    def __init__(self, cog, ctx, resize, init_image, upscaler_1, upscaler_2, upscaler_2_strength, copy_command, view):
        self.cog = cog
        self.ctx = ctx
        self.resize = resize
        self.init_image = init_image
        self.upscaler_1 = upscaler_1
        self.upscaler_2 = upscaler_2
        self.upscaler_2_strength = upscaler_2_strength
        self.copy_command: str = copy_command
        self.view = view

#the queue object for identify (interrogate)
class IdentifyObject:
    def __init__(self, cog, ctx, init_image, copy_command, view):
        self.cog = cog
        self.ctx = ctx
        self.init_image = init_image
        self.copy_command: str = copy_command
        self.view = view

#any command that needs to wait on processing should use the dream thread
class GlobalQueue:
    dream_thread = Thread()
    event_loop = asyncio.get_event_loop()
    queue_high: list[DrawObject | UpscaleObject | IdentifyObject] = []
    queue: list[DrawObject | UpscaleObject | IdentifyObject] = []
    queue_low: list[DrawObject | UpscaleObject | IdentifyObject] = []

#this creates the master queue that oversees all queues
def union(list_1, list_2, list_3):
    master_queue = list_1 + list_2 + list_3
    return master_queue

# get estimate of the compute cost of a dream
def get_dream_cost(queue_object: DrawObject | UpscaleObject | IdentifyObject):
    if queue_object is DrawObject:
        steps = queue_object.steps
        if queue_object.sampler == 'DPM adaptive': steps = 120

        dream_compute_cost: float = float(queue_object.batch_count)
        dream_compute_cost *= max(1.0, steps / 20)
        dream_compute_cost *= pow(max(1.0, (queue_object.width * queue_object.height) / (512 * 512)), 1.25)

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
    else:
        dream_compute_cost = 1.0
    return dream_compute_cost

def get_user_queue_cost(user_id: int):
    queue_cost = 0.0
    queue = GlobalQueue.queue_high + GlobalQueue.queue + GlobalQueue.queue_low
    for queue_object in queue:
        if queue_object.ctx.author.id == user_id:
            queue_cost += get_dream_cost(queue_object.width, queue_object.height, queue_object.steps, queue_object.batch_count)
    return queue_cost

def process_dream(self, queue_object: DrawObject | UpscaleObject | IdentifyObject, priority: str = ''):
    if GlobalQueue.dream_thread.is_alive():
        if priority == 'high':
            GlobalQueue.queue_high.append(queue_object)
        if priority == 'low':
            GlobalQueue.queue_low.append(queue_object)
        else:
            GlobalQueue.queue.append(queue_object)
    else:
        GlobalQueue.dream_thread = Thread(target=self.dream,
                                args=(GlobalQueue.event_loop, queue_object))
        GlobalQueue.dream_thread.start()

def process_queue():
    def start(target_queue: list[DrawObject | UpscaleObject | IdentifyObject]):
        queue_object = target_queue.pop(0)
        queue_object.cog.dream(GlobalQueue.event_loop, queue_object)

    if GlobalQueue.queue_high: start(GlobalQueue.queue_high)
    elif GlobalQueue.queue: start(GlobalQueue.queue)
    elif GlobalQueue.queue_low: start(GlobalQueue.queue_low)


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
def upload(upload_event_loop: asyncio.AbstractEventLoop, upload_queue_object: UploadObject):
    upload_event_loop.create_task(
        upload_queue_object.ctx.channel.send(
            content=upload_queue_object.content,
            embed=upload_queue_object.embed,
            files=upload_queue_object.files,
            view=upload_queue_object.view
        )
    )

    if GlobalUploadQueue.queue:
        upload(GlobalUploadQueue.event_loop, GlobalUploadQueue.queue.pop(0))

def process_upload(queue_object: UploadObject):
    if GlobalUploadQueue.upload_thread.is_alive():
        GlobalUploadQueue.queue.append(queue_object)
    else:
        GlobalUploadQueue.upload_thread = Thread(target=upload,
                                args=(GlobalUploadQueue.event_loop, queue_object))
        GlobalUploadQueue.upload_thread.start()
