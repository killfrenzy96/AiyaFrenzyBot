import asyncio
import discord
from threading import Thread

#the queue object for txt2image and img2img
class DrawObject:
    def __init__(self, ctx, prompt, negative_prompt, data_model, steps, height, width, guidance_scale, sampler, seed,
                 strength, init_image, init_image_encoded, copy_command, batch_count, style, facefix, tiling, simple_prompt):
        self.ctx: discord.ApplicationContext = ctx
        self.prompt: str = prompt
        self.negative_prompt: str = negative_prompt
        self.data_model: str = data_model
        self.steps: int = steps
        self.height: int = height
        self.width: int = width
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

#any command that needs to wait on processing should use the dream thread
class GlobalQueue:
    dream_thread = Thread()
    event_loop = asyncio.get_event_loop()
    queue_high: list[DrawObject] = []
    queue: list[DrawObject] = []
    queue_low: list[DrawObject] = []

async def process_dream(self, queue_object: DrawObject, priority: str = ''):
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


class UploadObject:
    def __init__(self, ctx, content, embed, files):
        self.ctx: discord.ApplicationContext = ctx
        self.content: str = content
        self.embed: discord.Embed = embed
        self.files: list[discord.File] = files

class GlobalUploadQueue:
    upload_thread = Thread()
    event_loop = asyncio.get_event_loop()
    queue: list[UploadObject] = []

async def process_upload(self, queue_object: UploadObject):
    if GlobalUploadQueue.upload_thread.is_alive():
        GlobalUploadQueue.queue.append(queue_object)
    else:
        GlobalUploadQueue.upload_thread = Thread(target=self.upload,
                                args=(GlobalUploadQueue.event_loop, queue_object))
        GlobalUploadQueue.upload_thread.start()