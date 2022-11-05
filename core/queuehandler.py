import asyncio
import discord
from threading import Thread


#the queue object for txt2image and img2img
class DrawObject:
    def __init__(self, ctx, prompt, negative_prompt, data_model, steps, height, width, guidance_scale, sampler, seed,
                 strength, init_image, copy_command, batch_count, facefix):
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
        self.copy_command: str = copy_command
        self.batch_count: int = batch_count
        self.facefix: bool = facefix

#any command that needs to wait on processing should use the dream thread
class GlobalQueue:
    dream_thread = Thread()
    event_loop = asyncio.get_event_loop()
    queue = []
async def process_dream(self, queue_object):
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
    queue = []
async def process_upload(self, queue_object):
    if GlobalUploadQueue.upload_thread.is_alive():
        GlobalUploadQueue.queue.append(queue_object)
    else:
        GlobalUploadQueue.upload_thread = Thread(target=self.upload,
                                args=(GlobalUploadQueue.event_loop, queue_object))
        GlobalUploadQueue.upload_thread.start()