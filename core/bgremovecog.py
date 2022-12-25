import discord
import io
import random
import requests
import time
import traceback
import asyncio
import threading
from urllib.parse import quote
from PIL import Image
from discord import option
from discord.ext import commands
from typing import Optional

import time
import numpy as np
# from skimage import io
import time

import gc
import torch
import torch.nn.functional as F
from torchvision.transforms.functional import normalize

from core import utility
from core import queuehandler
from core import viewhandler
from core import settings

from core.DIS.isnet import ISNetDIS


class BgRemoveCog(commands.Cog, description='Crops image background.'):
    def __init__(self, bot):
        self.bot: discord.Bot = bot

    @commands.slash_command(name = 'bgremove', description = 'Removes image background')
    @option(
        'init_image',
        discord.Attachment,
        description='The image for cropping.',
        required=False,
    )
    @option(
        'init_url',
        str,
        description='The URL image for cropping.',
        required=False,
    )
    async def dream_handler(self, ctx: discord.ApplicationContext | discord.Interaction, *,
                            init_image: Optional[discord.Attachment] = None,
                            init_url: Optional[str] = None):
        loop = asyncio.get_event_loop()
        guild = utility.get_guild(ctx)
        user = utility.get_user(ctx)
        content = None
        ephemeral = False

        try:
            print(f'Background remove Request -- {user.name}#{user.discriminator} -- {guild}')

            # get input image
            # image: str = None
            image_validated = False
            if init_url or init_image:
                if not init_url and init_image:
                    init_url = init_image.url

                if init_url.startswith('https://cdn.discordapp.com/') == False and init_url.startswith('https://media.discordapp.net/') == False:
                    print(f'Background remove rejected: Image is not from the Discord CDN.')
                    content = 'Only URL images from the Discord CDN are allowed!'
                    ephemeral = True
                    raise Exception()

                try:
                    # reject URL downloads larger than 10MB
                    url_head = await loop.run_in_executor(None, requests.head, init_url)
                    url_size = int(url_head.headers.get('content-length', -1))
                except:
                    content = 'Image not found! Please check the image URL.'
                    ephemeral = True
                    raise Exception()

                # check image download size
                if url_size > 10 * 1024 * 1024:
                    print(f'Background remove rejected: Image download too large.')
                    content = 'Image download is too large! Please make the download size smaller.'
                    ephemeral = True
                    raise Exception()

                # download and encode the image
                try:
                    image_response = await loop.run_in_executor(None, requests.get, init_url)
                    image_data = image_response.content
                    # image_string = base64.b64encode(image_data).decode('utf-8')
                except:
                    print(f'Background remove rejected: Image download failed.')
                    content = 'Image download failed! Please check the image URL.'
                    ephemeral = True
                    raise Exception()

                # check if image can open
                try:
                    image_bytes = io.BytesIO(image_data)
                    image_pil = Image.open(image_bytes)
                    image_pil_width, image_pil_height = image_pil.size
                except Exception as e:
                    print(f'Background remove rejected: Image is corrupted.')
                    print(f'\n{traceback.print_exc()}')
                    content = 'Image is corrupted! Please check the image you uploaded.'
                    ephemeral = True
                    raise Exception()

                # limit image width/height
                if image_pil_width * image_pil_height > 4096 * 4096:
                    print(f'Background remove rejected: Image size is too large.')
                    content = 'Image size is too large! Please use a lower resolution image.'
                    ephemeral = True
                    raise Exception()

                # setup image variable
                # image = 'data:image/png;base64,' + image_string
                image_validated = True

            #fail if no image is provided
            if image_validated == False:
                content = 'I need an image to remove the background from!'
                ephemeral = True
                raise Exception()

            #creates the crop object out of local variables
            def get_crop_object():
                queue_object = utility.BgRemoveObject(self, ctx, init_url, viewhandler.DeleteView())

                # send message with queue object
                queue_object.message = queue_object.get_command()
                print(queue_object.message) # log the command

                #construct a payload
                payload = {
                    'width': image_pil_width,
                    'height': image_pil_height,
                    'image': image_pil,
                }

                queue_object.payload = payload
                return queue_object

            crop_object = get_crop_object()
            content = f'<@{user.id}> {settings.global_var.messages[random.randrange(0, len(settings.global_var.messages))]}'
            loop.run_in_executor(None, self.dream, crop_object, None, None)

            # dream_cost = queuehandler.dream_queue.get_dream_cost(crop_object)
            # queue_cost = queuehandler.dream_queue.get_user_queue_cost(user.id)

            # # check if the user has too much things in queue
            # if dream_cost + queue_cost > settings.read(guild)['max_compute_queue']:
            #     content = f'<@{user.id}> Please wait! You have too much queued up.'
            #     ephemeral = True
            #     raise Exception()

            # priority = int(settings.read(guild)['priority'])
            # if dream_cost + queue_cost > settings.read(guild)['max_compute']:
            #     priority += 2
            # elif queue_cost > 0.0:
            #     priority += 1

            # # start the cropping
            # queue_length = queuehandler.dream_queue.process_dream(crop_object, priority)
            # if queue_length == None:
            #     content = f'<@{user.id}> Sorry, I cannot handle this request right now.'
            #     ephemeral = True
            # else:
            #     content = f'<@{user.id}> {settings.global_var.messages[random.randrange(0, len(settings.global_var.messages))]} Queue: ``{queue_length}``'

        except Exception as e:
            if content == None:
                content = f'<@{user.id}> Something went wrong.\n{e}'
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
            else:
                loop.create_task(ctx.channel.send(content, delete_after=delete_after))

    # generate the image
    def dream(self, queue_object: utility.UpscaleObject, web_ui: utility.WebUI, queue_continue: threading.Event):
        user = utility.get_user(queue_object.ctx)

        # much of the code below is copied from https://github.com/xuebinqin/DIS/blob/main/IS-Net/Inference.py
        try:
            model_path = settings.dir_path + '/../models/DIS/isnet-general-use.pth'
            input_size = [queue_object.payload['width'], queue_object.payload['height']]
            image_pil: Image.Image = queue_object.payload['image']

            torch.set_num_threads(4)
            net = ISNetDIS()
            net.load_state_dict(torch.load(model_path,map_location="cpu"))

            # Load image from memory
            image = np.array(image_pil)
            image = image.astype(np.float32)

            if len(image.shape) < 3:
                image = image[:, :, np.newaxis]
            im_shp=image.shape[0:2]

            if torch.cuda.is_available():
                net.load_state_dict(torch.load(model_path))
                net=net.cuda()
            else:
                net.load_state_dict(torch.load(model_path,map_location="cpu"))
            net.eval()

            # Convert image to tensor
            im_tensor = torch.tensor(image, dtype=torch.float32).permute(2,0,1)
            im_tensor = F.interpolate(torch.unsqueeze(im_tensor,0), input_size, mode="bilinear").type(torch.uint8)
            image = torch.divide(im_tensor,255.0)
            image = normalize(image,[0.5,0.5,0.5],[1.0,1.0,1.0])

            if torch.cuda.is_available():
                image=image.cuda()
            result=net(image)

            # Upsample output to original image size
            result = torch.squeeze(F.interpolate(result[0][0], im_shp, mode='bilinear'), 0)
            ma = torch.max(result)
            mi = torch.min(result)
            result = (result-mi)/(ma-mi)

            # Squeeze the singleton dimensions from the output tensor
            result = result.squeeze()

            # Convert the output tensor to a NumPy array
            result_array = (result*255).cpu().data.numpy().astype(np.uint8)

            # Convert the NumPy array to a Pillow image
            result_image = Image.fromarray(result_array)

            del net
            del im_tensor
            del im_shp
            del ma
            del mi
            del result
            gc.collect()
            torch.cuda.empty_cache()

            def post_dream():
                try:
                    image_r, image_g, image_b = image_pil.split()
                    image = Image.merge('RGBA', (image_r, image_g, image_b, result_image))

                    #create safe/sanitized filename
                    epoch_time = int(time.time())

                    # save local copy of image
                    if settings.global_var.dir != '--no-output':
                        file_path = f'{settings.global_var.dir}/{epoch_time}.png'
                        try:
                            # with open(file_path, 'wb') as fh:
                            #     fh.write(base64.b64decode(image_data))
                            print(f'Saved image: {file_path}')
                        except Exception as e:
                            print(f'Unable to save image: {file_path}\n{traceback.print_exc()}')
                    else:
                        file_path = f'{epoch_time}.png'
                        print(f'Received image: {file_path}')

                    # post to discord
                    with io.BytesIO() as buffer:
                        # result_image = Image.open(io.BytesIO(base64.b64decode(image_data)))
                        image.save(buffer, 'PNG')
                        buffer.seek(0)

                        files = [discord.File(fp=buffer, filename=file_path)]
                        queuehandler.upload_queue.process_upload(utility.UploadObject(queue_object=queue_object,
                            content=f'<@{user.id}> ``{queue_object.message}``', files=files, view=queue_object.view
                        ))
                        queue_object.view = None

                except Exception as e:
                    content = f'<@{user.id}> ``{queue_object.message}``\nSomething went wrong.\n{e}'
                    print(content + f'\n{traceback.print_exc()}')
                    queuehandler.upload_queue.process_upload(utility.UploadObject(queue_object=queue_object, content=content, delete_after=30))

            threading.Thread(target=post_dream, daemon=True).start()

        except Exception as e:
            content = f'<@{user.id}> ``{queue_object.message}``\nSomething went wrong.\n{e}'
            print(content + f'\n{traceback.print_exc()}')
            queuehandler.upload_queue.process_upload(utility.UploadObject(queue_object=queue_object, content=content, delete_after=30))

def setup(bot: discord.Bot):
    bot.add_cog(BgRemoveCog(bot))