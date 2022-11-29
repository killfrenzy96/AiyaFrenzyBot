import os
import base64
import contextlib
import discord
import io
import random
import requests
import time
import traceback
import asyncio
from difflib import SequenceMatcher
from threading import Thread
from PIL import Image, PngImagePlugin
from discord import option
from discord.ui import InputText, Modal, View
from discord.ext import commands
from typing import Optional

from core import queuehandler
from core import settings
from core import viewhandler


class Minigame:
    def __init__(self, host: discord.User, guild: discord.Guild):
        self.host = host
        self.guild = guild
        self.id = random.randint(0, 0xFFFFFFFF)
        self.running = False
        self.last_view: MinigameView = None

        self.minigame_id: int = None
        self.reveal_prompt: bool = False
        self.prompt: str = None
        self.hard_mode: bool = False
        self.game_iteration: int = 0
        self.batch: int = 1
        self.image_base64: list[str] = []
        self.channel: discord.TextChannel = None

        self.restarting = False
        self.guess_count = 0
        self.image_count = 0

    async def start(self, ctx: discord.ApplicationContext | discord.Interaction):
        if self.running == True:
            return
        self.running = True

        loop = asyncio.get_running_loop()
        self.channel = ctx.channel

        # minigames.append(self)
        loop.create_task(self.next_image_variation(ctx, self.prompt))

    async def stop(self):
        if self.running == False:
            return
        self.running = False

        # minigames.remove(self)

    async def answer(self, ctx: discord.ApplicationContext | discord.Interaction, guess: str):
        loop = asyncio.get_running_loop()
        user = queuehandler.get_user(ctx)

        if self.running == False:
            content = f'<@{user.id}> This game is over. '
            if user.id == self.host.id:
                content += 'Press 🖋️ or 🖼️ to continue the minigame.'
            else:
                content += f'Please start a new game or ask {self.host.name} to keep going.'
            ephemeral = True
        else:
            prompt = self.prompt.lower()
            guess = self.sanatize(guess).lower()

            self.guess_count += 1
            similarity = SequenceMatcher(None, prompt, guess).ratio()

            if prompt in guess or similarity > 0.9:
                content = f'<@{user.id}> has guessed the answer! The prompt was ``{self.prompt}``.\nIt took ``{self.guess_count}`` guesses and ``{self.image_count}`` images to get this answer.\nPress 🖋️ or 🖼️ to continue the minigame.'
                ephemeral = False
                await self.stop()
            elif similarity > 0.8:
                content = f'<@{user.id}> tried ``{guess}``. This is really close.'
                ephemeral = False
            elif similarity > 0.65:
                content = f'<@{user.id}> tried ``{guess}``. This is kind of close.'
                ephemeral = False
            else:
                content = f'<@{user.id}> tried ``{guess}``. This was not the correct answer.'
                ephemeral = False

        if ephemeral:
            delete_after = 30
        else:
            delete_after = None

        if type(ctx) is discord.ApplicationContext:
            loop.create_task(ctx.send_response(content=content, ephemeral=ephemeral, delete_after=delete_after))
        elif type(ctx) is discord.Interaction:
            loop.create_task(ctx.response.send_message(content=content, ephemeral=ephemeral, delete_after=delete_after))

    async def next_image_variation(self, ctx: discord.ApplicationContext | discord.Interaction, prompt: str = 'unset'):
        loop = asyncio.get_running_loop()

        print(f'Minigame Request -- {self.host.name}#{self.host.discriminator} -- {self.guild}')

        dream_cost = 2.0
        queue_cost = round(queuehandler.get_user_queue_cost(self.host.id), 2)

        if dream_cost + queue_cost > settings.read(self.guild)['max_compute']:
            print(f'Minigame rejected: Too much in queue already')
            content = f'<@{self.host.id}> Please wait! You have too much queued up.'
            ephemeral = True
        else:
            if self.running == False:
                self.running = True
                self.restarting = True
                self.guess_count = 0
                self.image_count = 0
                if prompt == None:
                    prompt = 'unset'

            if prompt == 'unset' or not self.prompt:
                prompt = self.sanatize(prompt)
                self.prompt = await loop.run_in_executor(None, self.get_random_prompt, self.hard_mode)
            elif prompt:
                self.prompt = self.sanatize(prompt)

            content = f'<@{self.host.id}> '
            if self.game_iteration == 0:
                content += 'Your minigame is starting... '
            content += settings.global_var.messages[random.randint(0, len(settings.global_var.messages) - 1)]
            ephemeral = False

            loop.create_task(self.get_image_variation(ctx, self.prompt))

        if ephemeral:
            delete_after = 30
        else:
            delete_after = None

        if type(ctx) is discord.ApplicationContext:
            loop.create_task(ctx.send_response(content=content, ephemeral=ephemeral, delete_after=delete_after))
        elif type(ctx) is discord.Interaction:
            loop.create_task(ctx.response.send_message(content=content, ephemeral=ephemeral, delete_after=delete_after))

    async def give_up(self, ctx: discord.ApplicationContext | discord.Interaction):
        loop = asyncio.get_running_loop()

        content = f'<@{self.host.id}> has given up. The answer was ``{self.prompt}``.\nThere were ``{self.guess_count}`` guesses and ``{self.image_count}`` images generated.\nPress 🖋️ or 🖼️ to continue the minigame.'

        if type(ctx) is discord.ApplicationContext:
            loop.create_task(ctx.send_response(content=content))
        elif type(ctx) is discord.Interaction:
            loop.create_task(ctx.response.send_message(content=content))

        await self.stop()

    async def get_image_variation(self, ctx: discord.ApplicationContext | discord.Interaction, prompt: str):
        loop = asyncio.get_running_loop()

        model_name: str = 'Default'
        data_model: str = ''
        for index, (display_name, full_name) in enumerate(settings.global_var.model_names.items()):
            if display_name == model_name or full_name == model_name:
                #take selected data_model and get model_name, then update data_model with the full name
                model_name = display_name
                data_model = full_name

                #look at the model for activator token and prepend prompt with it
                token = settings.global_var.model_tokens[display_name]
                prompt = token + ' ' + prompt
                #if there's no activator token, remove the extra blank space
                prompt = prompt.lstrip(' ')

        if self.image_base64:
            if self.hard_mode:
                guidance_scale = random.randrange(3.0, 8.0)
            else:
                guidance_scale = random.randrange(5.0, 9.0)
            init_url = 'dummy'
        else:
            # start with a nonsence image
            guidance_scale = 1.0
            init_url = None

        words = prompt.split(' ')

        copy_command = f'Minigame ID ``{self.id}``\n'

        random_message = await loop.run_in_executor(None, self.get_random_word, 'resources/minigame-messages.csv')
        if self.restarting:
            copy_command += f'> This is a new prompt. {random_message}'
            self.restarting = False
        else:
            copy_command += f'> Guess the prompt. {random_message}'

        if len(words) > 1:
            copy_command += f'\n> ``({len(words)} words'
        else:
            copy_command += '\n> ``(1 word'

        for index, word in enumerate(words):
            if index == 0:
                copy_command += f', {len(word)} letters'
            else:
                copy_command += f' + {len(word)} letters'

        copy_command += ')``'

        draw_object = queuehandler.DrawObject(
            cog=self,
            ctx=ctx,
            prompt=prompt,
            negative_prompt=None,
            model_name='Default',
            data_model=data_model,
            steps=settings.read(self.guild)['default_steps'],
            width=512,
            height=512,
            guidance_scale=guidance_scale,
            sampler=settings.read(self.guild)['sampler'],
            seed=random.randint(0, 0xFFFFFFFF),
            strength=0.55 + random.random() * 0.25,
            init_url=init_url,
            copy_command=copy_command,
            batch_count=self.batch,
            style=None,
            facefix=False,
            tiling=False,
            highres_fix=False,
            clip_skip=1,
            simple_prompt=prompt,
            script=None,
            view=None
        )

        draw_object.view = MinigameView(self, draw_object)
        self.last_view = draw_object.view

        # construct a payload
        payload = {
            "prompt": draw_object.prompt,
            "steps": draw_object.steps,
            "width": draw_object.width,
            "height": draw_object.height,
            "cfg_scale": draw_object.guidance_scale,
            "sampler_index": draw_object.sampler,
            "seed": draw_object.seed,
            "seed_resize_from_h": 0,
            "seed_resize_from_w": 0,
            "denoising_strength": draw_object.strength,
            "tiling": draw_object.tiling,
            "n_iter": draw_object.batch_count
        }

        if init_url:
            # update payload if image_base64 is available
            img_payload = {
                "init_images": [
                    'data:image/png;base64,' + self.image_base64[random.randint(0, len(self.image_base64) - 1)]
                ],
                "denoising_strength": draw_object.strength
            }
            payload.update(img_payload)

        draw_object.payload = payload
        queuehandler.process_dream(self, draw_object, 'medium')

        # while game_iteration == self.game_iteration:
        #     await asyncio.sleep(0.1)

    def get_random_prompt(self, hard_mode: bool):
        nouns_path = 'resources/minigame-nouns.csv'

        if hard_mode:
            # hard mode includes an adjective and a noun
            adjectives_path = 'resources/minigame-adjectives.csv'

            random_adjective = self.get_random_word(adjectives_path)
            random_noun = self.get_random_word(nouns_path)

            # take care of rare edge case
            while random_noun == random_adjective:
                random_noun = self.get_random_word(nouns_path)

            return f'{random_adjective} {random_noun}'
        else:
            # easy mode only includes a noun
            return self.get_random_word(nouns_path)

    def get_random_word(self, filepath: str):
        file_stats = os.stat(filepath)
        file = open(filepath)
        offset = random.randrange(file_stats.st_size)
        file.seek(offset)
        file.readline()
        random_line = file.readline()

        # extra to handle last/first line edge cases
        if len(random_line) == 0: # we have hit the end
            file.seek(0)
            random_line = file.readline() # so we'll grab the first line instead

        random_line.replace('\n', '')
        return random_line.strip()

    def dream(self, queue_object: queuehandler.DrawObject):
        user = queuehandler.get_user(queue_object.ctx)

        try:
            s = requests.Session()
            if settings.global_var.api_auth:
                s.auth = (settings.global_var.api_user, settings.global_var.api_pass)

            # send normal payload to webui
            if settings.global_var.gradio_auth:
                login_payload = {
                    'username': settings.global_var.username,
                    'password': settings.global_var.password
                }
                s.post(settings.global_var.url + '/login', data=login_payload)
            # else:
            #     s.post(settings.global_var.url + '/login')

            # construct a payload for data model
            data_model = settings.global_var.model_names['Default']
            if data_model:
                model_payload = {
                    "sd_model_checkpoint": settings.global_var.model_names['Default']
                }
                s.post(url=f'{settings.global_var.url}/sdapi/v1/options', json=model_payload)

            if queue_object.init_url:
                url = f'{settings.global_var.url}/sdapi/v1/img2img'
            else:
                url = f'{settings.global_var.url}/sdapi/v1/txt2img'

            response = s.post(url=url, json=queue_object.payload)
            response_data = response.json()

            self.game_iteration += 1

            #create safe/sanitized filename
            keep_chars = (' ', '.', '_')
            file_name = "".join(c for c in queue_object.prompt if c.isalnum() or c in keep_chars).rstrip()

            # save local copy of image and prepare PIL images
            pil_images: list[Image.Image] = []
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

                for (pil_image, buffer) in zip(pil_images, buffer_handles):
                    pil_image.save(buffer, 'PNG')
                    buffer.seek(0)

                files = [discord.File(fp=buffer, filename=f'{queue_object.seed}-{i}.png') for (i, buffer) in enumerate(buffer_handles)]
                # event_loop.create_task(queue_object.ctx.channel.send(content=f'<@{user.id}>', embed=embed, files=files))
                queuehandler.process_upload(queuehandler.UploadObject(
                    ctx=queue_object.ctx, content=f'<@{user.id}> {queue_object.copy_command}', files=files, view=queue_object.view
                ))
                queue_object.view = None
                self.image_count += queue_object.batch_count

            self.image_base64 = response_data['images']

        except Exception as e:
            print('minigame failed (dream)')
            embed = discord.Embed(title='minigame failed (dream)', description=f'{e}\n{traceback.print_exc()}', color=settings.global_var.embed_color)
            queuehandler.process_upload(queuehandler.UploadObject(
                ctx=queue_object.ctx, content=f'<@{user.id}> Minigame Failed', embed=embed
            ))

    # sanatize input strings
    def sanatize(self, input: str):
        if input:
            input = input.replace('``', ' ')
            input = input.replace('\n', ' ')
        return input

# minigames: list[Minigame] = []

class MinigameCog(commands.Cog, name='Stable Diffusion Minigame', description='Guess the prompt from the picture minigame.'):
    ctx_parse = discord.ApplicationContext
    def __init__(self, bot):
        self.bot: discord.Bot = bot

    @option(
        'prompt',
        str,
        description='The starting prompt. If provdided, you will handle the prompts instead of me.',
        required=False,
    )
    @option(
        'hard_mode',
        str,
        description='Hard mode will generate two words per prompt instead of one.',
        required=False,
    )
    @option(
        'batch',
        int,
        description='The number of images to generate. This is "Batch count", not "Batch size".',
        required=False,
    )
    @commands.slash_command(name = 'minigame', description = 'Starts a minigame where you guess the prompt from a picture.')
    async def draw_handler(self, ctx: discord.ApplicationContext, *,
                           prompt: Optional[str] = None,
                           hard_mode: Optional[bool] = False,
                           batch: Optional[int] = 2):
        try:
            loop = asyncio.get_event_loop()
            host = queuehandler.get_user(ctx)
            guild = queuehandler.get_guild(ctx)

            # interaction = await ctx.send_response(content='Please wait. The minigame is starting...')
            # message = viewhandler.get_message(interaction)

            minigame = Minigame(host, guild)
            minigame.prompt = prompt
            minigame.hard_mode = hard_mode
            minigame.batch = max(1, min(3, batch))

            if prompt:
                minigame.reveal_prompt = True
            else:
                minigame.reveal_prompt = False

            loop.create_task(minigame.start(ctx))

        except Exception as e:
            viewhandler.print_exception('minigame failed', e, ctx.interaction, loop)

    # This is disabled. It would require extra intents that's not neccessary for the primary function of this bot.
    # @commands.Cog.listener()
    # async def on_message(self, message: discord.Message):
    #     loop = asyncio.get_event_loop()
    #     if message.author.id == self.bot.user.id:
    #         return

    #     print('Message content:')
    #     print(message.content)

    #     for minigame in minigames:
    #         if message.channel == minigame.channel:
    #             loop.create_task(minigame.answer(message))


class MinigameView(View):
    def __init__(self, minigame: Minigame, input_object: queuehandler.DrawObject):
        super().__init__(timeout=None)
        self.minigame = minigame
        self.input_object = input_object

    # the 🖼️ button will take the same parameters for the image, send the original image to init_image, change the seed, and add a task to the queue
    @discord.ui.button(
        label="More Images",
        custom_id="button_image-variation",
        emoji="🖼️")
    async def button_draw_variation(self, button: discord.Button, interaction: discord.Interaction):
        loop = asyncio.get_event_loop()
        try:
            if viewhandler.check_interaction_permission(interaction, loop) == False: return

            # obtain URL for the original image
            if not self.minigame:
                loop.create_task(interaction.response.send_message('I may have been restarted. This button no longer works.\nPlease try using 🖼️ on a message containing the full /dream command.', ephemeral=True, delete_after=30))
                return

            # only allow interaction for the host
            if self.minigame.host.id != interaction.user.id:
                loop.create_task(interaction.response.send_message(f'Only {self.minigame.host.name} may create new variations.', ephemeral=True, delete_after=30))
                return

            # only allow interaction with the latest post
            if self.minigame.last_view != self:
                loop.create_task(interaction.response.send_message('You may only interact with the latest image from the minigame.', ephemeral=True, delete_after=30))
                return

            # run stablecog dream using draw object
            loop.create_task(self.minigame.next_image_variation(interaction, None))

        except Exception as e:
            viewhandler.print_exception('send to img2img failed', e, interaction, loop)

    # the 🖋️ button will allow a new prompt and keep same parameters for everything else
    @discord.ui.button(
        custom_id="button_re-prompt",
        emoji="🖋️")
    async def button_draw(self, button: discord.Button, interaction: discord.Interaction):
        loop = asyncio.get_event_loop()
        try:
            if viewhandler.check_interaction_permission(interaction, loop) == False: return

            # get input object
            if not self.input_object:
                loop.create_task(interaction.response.send_message('I may have been restarted. This button no longer works.\nPlease try using 🖋 on a message containing the full /dream command.', ephemeral=True, delete_after=30))
                return

            # only allow interaction for the host
            if self.minigame.host.id != interaction.user.id:
                loop.create_task(interaction.response.send_message(f'Only {self.minigame.host.name} may configure the minigame.', ephemeral=True, delete_after=30))
                return

            # only allow interaction with the latest post
            if self.minigame.last_view != self:
                loop.create_task(interaction.response.send_message('You may only interact with the latest image from the minigame.', ephemeral=True, delete_after=30))
                return

            loop.create_task(interaction.response.send_modal(MinigameEditModal(self, self.minigame)))

        except Exception as e:
            viewhandler.print_exception('re-prompt failed', e, interaction, loop)

    # the 🏳️ ends the game and reveals the answer
    @discord.ui.button(
        custom_id="button_giveup",
        emoji="🏳️")
    async def button_draw_giveup(self, button: discord.Button, interaction: discord.Interaction):
        loop = asyncio.get_event_loop()
        try:
            if viewhandler.check_interaction_permission(interaction, loop) == False: return

            # obtain URL for the original image
            if not self.minigame:
                loop.create_task(interaction.response.send_message('I may have been restarted. This button no longer works.\nPlease try using 🖼️ on a message containing the full /dream command.', ephemeral=True, delete_after=30))
                return

            # only allow interaction for the host
            if self.minigame.host.id != interaction.user.id:
                loop.create_task(interaction.response.send_message(f'Only {self.minigame.host.name} may give up.', ephemeral=True, delete_after=30))
                return

            # only allow interaction with the latest post
            if self.minigame.last_view != self:
                loop.create_task(interaction.response.send_message('You may only interact with the latest image from the minigame.', ephemeral=True, delete_after=30))
                return

            # run stablecog dream using draw object
            loop.create_task(self.minigame.give_up(interaction))

        except Exception as e:
            viewhandler.print_exception('send to img2img failed', e, interaction, loop)

    #the button to delete generated images
    @discord.ui.button(
        custom_id="button_x",
        emoji="❌")
    async def delete(self, button: discord.Button, interaction: discord.Interaction):
        loop = asyncio.get_event_loop()
        try:
            if viewhandler.check_interaction_permission(interaction, loop) == False: return
            message = await viewhandler.get_message(interaction)

            if not message.content.startswith(f'<@{interaction.user.id}>'):
                loop.create_task(interaction.response.send_message("You can't delete other people's images!", ephemeral=True, delete_after=30))
                return

            if viewhandler.confirm_user_delete(interaction.user.id):
                loop.create_task(interaction.response.send_modal(viewhandler.DeleteModal(message)))
            else:
                loop.create_task(interaction.message.delete())
                viewhandler.update_user_delete(interaction.user.id)

        except Exception as e:
            viewhandler.print_exception('delete failed', e, interaction, loop)

    # guess prompt button
    @discord.ui.button(
        label="Guess Prompt",
        custom_id="button_guess-prompt",
        emoji="⌨️",
        row=2)
    async def guess_prompt(self, button: discord.Button, interaction: discord.Interaction):
        loop = asyncio.get_event_loop()
        try:
            if viewhandler.check_interaction_permission(interaction, loop) == False: return

            loop.create_task(interaction.response.send_modal(MinigameAnswerModal(self, self.minigame)))

        except Exception as e:
            viewhandler.print_exception('delete failed', e, interaction, loop)


class MinigameEditModal(Modal):
    def __init__(self, view: MinigameView, minigame: Minigame) -> None:
        super().__init__(title="Change Prompt!")
        self.view = view
        self.minigame = minigame

        if minigame.reveal_prompt:
            prompt = minigame.prompt
        else:
            prompt = ''

        if minigame.hard_mode:
            hard_mode = 'H'
        else:
            hard_mode = 'E'

        self.add_item(
            InputText(
                label='Prompt. Leave empty for a random prompt.',
                value=prompt,
                style=discord.InputTextStyle.short,
                required=False
            )
        )

        self.add_item(
            InputText(
                label='Hard Mode. \'H\' for hard. \'E\' for easy.',
                value=hard_mode,
                style=discord.InputTextStyle.short,
                required=False
            )
        )

        self.add_item(
            InputText(
                label='Batch',
                value=minigame.batch,
                style=discord.InputTextStyle.short,
                required=False
            )
        )

    async def callback(self, interaction: discord.Interaction):
        loop = asyncio.get_event_loop()
        try:
            if viewhandler.check_interaction_permission(interaction, loop) == False: return

            # obtain URL for the original image
            if not self.minigame:
                loop.create_task(interaction.response.send_message('I may have been restarted. This button no longer works.\nPlease try using 🖼️ on a message containing the full /dream command.', ephemeral=True, delete_after=30))
                return

            prompt = self.children[0].value
            if prompt:
                self.minigame.reveal_prompt = True
            else:
                self.minigame.reveal_prompt = False
                prompt = None

            hard_mode = self.children[1].value
            if hard_mode.lower() == 'h':
                self.minigame.hard_mode = True
            elif hard_mode.lower() == 'e':
                self.minigame.hard_mode = False

            try:
                batch = int(self.children[2].value)
                batch = max(1, min(3, batch))
                self.minigame.batch = batch
            except:
                pass

            # run stablecog dream using draw object
            await self.minigame.stop()
            loop.create_task(self.minigame.next_image_variation(interaction, prompt))

        except Exception as e:
            viewhandler.print_exception('send to img2img failed', e, interaction, loop)


class MinigameAnswerModal(Modal):
    def __init__(self, view: MinigameView, minigame: Minigame) -> None:
        super().__init__(title="Change Prompt!")
        self.view = view
        self.minigame = minigame

        self.add_item(
            InputText(
                label='What\'s your guess?',
                value='',
                style=discord.InputTextStyle.short,
                required=False
            )
        )

    async def callback(self, interaction: discord.Interaction):
        loop = asyncio.get_event_loop()
        try:
            if viewhandler.check_interaction_permission(interaction, loop) == False: return

            # obtain URL for the original image
            if not self.minigame:
                loop.create_task(interaction.response.send_message('I may have been restarted. This button no longer works.\nPlease try using 🖼️ on a message containing the full /dream command.', ephemeral=True, delete_after=30))
                return

            guess = self.children[0].value

            # run stablecog dream using draw object
            loop.create_task(self.minigame.answer(interaction, guess))

        except Exception as e:
            viewhandler.print_exception('send to img2img failed', e, interaction, loop)


def setup(bot: discord.Bot):
    bot.add_cog(MinigameCog(bot))