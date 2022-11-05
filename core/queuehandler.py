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
    queue: list[DrawObject] = []

    def get_queue_position(user_id: int):
        queue_user_id: list[int] = []
        queue_user_count: list[int] = []

        # count all users in queue
        for queue_object in GlobalQueue.queue:
            try:
                user_index = queue_user_id.index(queue_object.ctx.author.id)
                queue_user_count[user_index] += 1
            except:
                queue_user_id.append(queue_object.ctx.author.id)
                queue_user_count.append(1)

        try:
            user_count = queue_user_id.index(user_id)
        except:
            return len(GlobalQueue.queue)

        for index, queue_object in enumerate(GlobalQueue.queue):
            count = queue_user_count[queue_user_id.index(queue_object.ctx.author.id)]
            if user_count < count:
                return index + 1

        return len(GlobalQueue.queue)

async def process_dream(self, queue_object: DrawObject):
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