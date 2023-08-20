import discord
import traceback
import asyncio
from discord import option
from discord.ext import commands
from typing import Optional

from core import utility
from core import settings
from core import stablecog


class DrawCog(commands.Cog, description='An simplified way to create images from natural language.'):
    def __init__(self, bot):
        self.bot: discord.Bot = bot

    # pulls from model_names list and makes some sort of dynamic list to bypass Discord 25 choices limit
    def presets_autocomplete(self: discord.AutocompleteContext):
        return [
            preset for preset in settings.global_var.presets
        ]

    # use autocomplete if there are too many models, otherwise use choices
    if len(settings.global_var.presets) > 25:
        preset_autocomplete_fn = settings.custom_autocomplete(presets_autocomplete)
        preset_choices = []
    else:
        preset_autocomplete_fn = None
        preset_choices = settings.global_var.presets

    @commands.slash_command(name = 'draw', description = 'Create an image (simple)')
    @option(
        'preset',
        str,
        description='The kind of drawing you would like to make.',
        required=True,
        autocomplete=preset_autocomplete_fn,
        choices=preset_choices,
    )
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
        description='The number of images to generate. This is \'Batch count\', not \'Batch size\'.',
        min_value=1,
        required=False,
    )
    async def dream_handler(self, ctx: discord.ApplicationContext, *,
                            preset: str,
                            prompt: str, negative: str = None,
                            init_image: Optional[discord.Attachment] = None,
                            init_url: Optional[str] = None,
                            batch: Optional[int] = None):
        loop = asyncio.get_event_loop()
        guild = utility.get_guild(ctx)
        user = utility.get_user(ctx)
        content = None
        ephemeral = False

        try:
            print(f'Draw Request -- {user.name}#{user.discriminator} -- {guild}')
            stable_cog: stablecog.StableCog = self.bot.get_cog('StableCog')

            # generate draw object from preset command
            command_string = settings.global_var.presets[preset]
            draw_object = stable_cog.get_draw_object_from_command(command_string)

            # apply modifications to preset command
            if draw_object.prompt:
                draw_object.prompt = f'{draw_object.prompt}, {prompt}'
            else:
                draw_object.prompt = prompt

            if draw_object.negative:
                if negative:
                    draw_object.negative = f'{draw_object.negative}, {negative}'
            else:
                if negative: draw_object.negative = negative

            if init_url: draw_object.init_url = init_url
            if batch: draw_object.batch = batch

            # switch to inpaint or refiner model if init_url or init_image is used
            if init_image or init_url:
                new_model_name = settings.get_inpaint_model(draw_object.model_name)
                if new_model_name:
                    draw_object.model_name = new_model_name
                    if '_refiner' in new_model_name: draw_object.strength = 0.25

            # update hires fix prompt if needed
            if draw_object.highres_fix_prompt != None and draw_object.highres_fix_prompt != '':
                draw_object.highres_fix_prompt = f'{draw_object.highres_fix_prompt}, {prompt}'

            if negative and (draw_object.highres_fix_negative != None and draw_object.highres_fix_negative != ''):
                draw_object.highres_fix_negative = f'{draw_object.highres_fix_negative}, {negative}'

            # execute dream command
            await stable_cog.dream_handler(ctx=ctx,
                prompt=draw_object.prompt,
                negative=draw_object.negative,
                checkpoint=draw_object.model_name,
                width=draw_object.width,
                height=draw_object.height,
                guidance_scale=draw_object.guidance_scale,
                steps=draw_object.steps,
                sampler=draw_object.sampler,
                seed=draw_object.seed,
                init_image=init_image,
                init_url=draw_object.init_url,
                strength=draw_object.strength,
                batch=draw_object.batch,
                style=draw_object.style,
                facefix=draw_object.facefix,
                tiling=draw_object.tiling,
                highres_fix=draw_object.highres_fix,
                highres_fix_prompt=draw_object.highres_fix_prompt,
                highres_fix_negative=draw_object.highres_fix_negative,
                clip_skip=draw_object.clip_skip,
                script=draw_object.script
            )

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
            else:
                loop.create_task(ctx.channel.send(content, delete_after=delete_after))

def setup(bot: discord.Bot):
    if len(settings.global_var.presets) > 0:
        bot.add_cog(DrawCog(bot))