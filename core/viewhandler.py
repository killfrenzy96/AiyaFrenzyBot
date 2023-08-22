import discord
import copy
import traceback
import time
import asyncio
from discord.ui import Button, Select, InputText, Modal, View
from discord.ext import commands

from core import settings
from core import utility
from core import stablecog
from core import upscalecog

discord_bot: discord.Bot = None
fallback_views = {}

# the modal that is used for the 🖋 button
class DrawModal(Modal):
    def __init__(self, stable_cog, input_object: utility.DrawObject, message: discord.Message) -> None:
        super().__init__(title='Change Prompt!')
        self.stable_cog = stable_cog
        self.input_object = input_object
        self.message = message

        self.add_item(InputText(
            label='Prompt',
            value=self.input_object.prompt,
            style=discord.InputTextStyle.long
        ))

        self.add_item(InputText(
                label='Negative prompt (optional)',
                style=discord.InputTextStyle.long,
                value=self.input_object.negative,
                required=False
        ))

        self.add_item(InputText(
                label='Seed. Remove to randomize.',
                style=discord.InputTextStyle.short,
                value=self.input_object.seed,
                required=False
        ))

        extra_settings_value = f'batch: {self.input_object.batch}'

        if self.input_object.init_url:
            init_url = self.input_object.init_url
        else:
            init_url = ''

        if self.input_object.init_url or (self.input_object.highres_fix != None or self.input_object.highres_fix != 'None'):
            extra_settings_value += f'\nstrength: {self.input_object.strength}'

        if self.input_object.model_name == None or self.input_object.model_name == 'None':
            self.input_object.model_name = 'Default'

        extra_settings_value += f'\nsteps: {self.input_object.steps}'
        extra_settings_value += f'\nguidance_scale: {self.input_object.guidance_scale}'
        extra_settings_value += f'\nwidth: {self.input_object.width}'
        extra_settings_value += f'\nheight: {self.input_object.height}'

        extra_settings_value += f'\n\ncheckpoint: {self.input_object.model_name}'
        extra_settings_value += f'\nstyle: {self.input_object.style}'

        extra_settings_value += f'\n\nhighres_fix: {self.input_object.highres_fix}'
        if self.input_object.highres_fix_prompt == None: self.input_object.highres_fix_prompt = ''
        if self.input_object.highres_fix_negative == None: self.input_object.highres_fix_negative = ''
        extra_settings_value += f'\nhighres_fix_prompt: {self.input_object.highres_fix_prompt}'
        extra_settings_value += f'\nhighres_fix_negative: {self.input_object.highres_fix_negative}'

        extra_settings_value += f'\n\nfacefix: {self.input_object.facefix}'
        extra_settings_value += f'\ntiling: {self.input_object.tiling}'
        extra_settings_value += f'\nclip_skip: {self.input_object.clip_skip}'
        extra_settings_value += f'\nscript: {self.input_object.script}'

        extra_settings_value += f'\ncontrolnet_model: {self.input_object.controlnet_model}'
        extra_settings_value += f'\ncontrolnet_weight: {self.input_object.controlnet_weight}'
        extra_settings_value += f'\ncontrolnet_url: {self.input_object.controlnet_url}'

        self.add_item(
            InputText(
                label='Init URL. \'C\' uses current image.',
                style=discord.InputTextStyle.short,
                value=init_url,
                required=False
            )
        )
        self.add_item(
            InputText(
                label='Extra settings',
                style=discord.InputTextStyle.long,
                value=extra_settings_value,
                required=False
            )
        )

    async def callback(self, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return

            draw_object = copy.copy(self.input_object)

            draw_object.prompt = self.children[0].value

            draw_object.negative = self.children[1].value

            try:
                draw_object.seed = int(self.children[2].value)
            except:
                draw_object.seed = None

            try:
                if self.children[3].value.lower().startswith('c'):
                    init_url = self.message.attachments[0].url
                else:
                    init_url = self.children[3].value

                if init_url:
                    draw_object.init_url = init_url
                else:
                    draw_object.init_url = None
            except:
                pass

            try:
                # reconstruct command from modal
                command = self.children[4].value
                commands = command.split('\n')
                for index, text in enumerate(commands):
                    if text: commands[index] = text.split(':')[0]

                stable_cog: stablecog.StableCog = self.stable_cog
                command_draw_object = stable_cog.get_draw_object_from_command(command.replace('\n', ' '))
                draw_object.model_name      = command_draw_object.model_name
                draw_object.width           = command_draw_object.width
                draw_object.height          = command_draw_object.height
                draw_object.steps           = command_draw_object.steps
                draw_object.guidance_scale  = command_draw_object.guidance_scale
                draw_object.strength        = command_draw_object.strength
                draw_object.style           = command_draw_object.style
                draw_object.facefix         = command_draw_object.facefix
                draw_object.tiling          = command_draw_object.tiling
                draw_object.highres_fix     = command_draw_object.highres_fix
                draw_object.highres_fix_prompt = command_draw_object.highres_fix_prompt
                draw_object.highres_fix_negative = command_draw_object.highres_fix_negative
                draw_object.clip_skip       = command_draw_object.clip_skip
                draw_object.batch           = command_draw_object.batch
                draw_object.controlnet_model = command_draw_object.controlnet_model
                draw_object.controlnet_url  = command_draw_object.controlnet_url
                draw_object.controlnet_weight = command_draw_object.controlnet_weight
                draw_object.script          = command_draw_object.script
            except:
                pass

            draw_object.ctx = interaction
            draw_object.view = None
            draw_object.payload = None

            loop.create_task(stable_cog.dream_object(draw_object))
        except Exception as e:
            print_exception(e, interaction, loop)

# create the view to confirm the deletion of an image
class DeleteModal(Modal):
    def __init__(self, message: discord.Message) -> None:
        super().__init__(title='Confirm Delete')
        self.message = message

        self.add_item(
            InputText(
                label='Confirmation',
                style=discord.InputTextStyle.short,
                value='Press submit to delete this image.',
                required=False
            )
        )

    async def callback(self, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return

            if not self.message.content.startswith(f'<@{interaction.user.id}>'):
                loop.create_task(interaction.response.send_message('You can\'t delete other people\'s images!', ephemeral=True, delete_after=30))
                return

            loop.create_task(interaction.response.defer())
            loop.create_task(interaction.message.delete())
            update_user_delete(interaction.user.id)

        except Exception as e:
            print_exception(e, interaction, loop)

# creating the view that holds the buttons for /draw output
class DrawView(View):
    def __init__(self, input_object: utility.DrawObject):
        super().__init__(timeout=None)
        self.input_object: utility.DrawObject = input_object
        self.stable_cog = discord_bot.get_cog('StableCog')
        self.upscale_cog = discord_bot.get_cog('UpscaleCog')

    # the 🖋 button will allow a new prompt and keep same parameters for everything else
    @discord.ui.button(
        custom_id='button_re-prompt',
        row=0,
        emoji='🖋')
    async def button_draw(self, button: Button, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return
            message = await get_message(interaction)
            stable_cog: stablecog.StableCog = self.stable_cog

            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                input_object = await get_input_object(stable_cog, interaction, '🖋')
                if input_object == None: return

            loop.create_task(interaction.response.send_modal(DrawModal(stable_cog, input_object, message)))

        except Exception as e:
            print_exception(e, interaction, loop)

    # the 🖼️ button will take the same parameters for the image, send the original image to init_image, change the seed, and add a task to the queue
    @discord.ui.button(
        custom_id='button_image-variation',
        row=0,
        emoji='🖼️')
    async def button_draw_variation(self, button: Button, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return
            message = await get_message(interaction)
            stable_cog: stablecog.StableCog = self.stable_cog

            # obtain URL for the original image
            init_url = message.attachments[0].url
            if not init_url:
                loop.create_task(interaction.response.send_message('The image seems to be missing. This interaction no longer works.', ephemeral=True, delete_after=30))
                return

            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                input_object = await get_input_object(stable_cog, interaction, '🖼️')
                if input_object == None: return

            # setup draw object to send to the stablecog
            draw_object = copy.copy(input_object)
            draw_object.seed = None
            draw_object.ctx = interaction
            draw_object.view = None
            draw_object.payload = None
            draw_object.init_url = init_url
            if draw_object.script:
                if draw_object.script.startswith('inpaint'):
                    draw_object.script = None
                elif draw_object.script.startswith('outpaint'):
                    draw_object.script = None
                    draw_object.strength = None

            # remove controlnet variation
            draw_object.controlnet_model = None
            draw_object.controlnet_preprocessor = None
            draw_object.controlnet_data_model = None
            draw_object.controlnet_url = None

            # use inpaint or refiner model if it exists
            model_name_new = settings.get_inpaint_model(draw_object.model_name)
            if model_name_new:
                draw_object.model_name = model_name_new
                draw_object.data_model = settings.global_var.model_names[model_name_new]
                if ('_refiner' in model_name_new): draw_object.strength = 0.25

            # transfer highres prompt to main prompt
            draw_object.highres_fix = None
            if draw_object.highres_fix_prompt: draw_object.prompt = draw_object.highres_fix_prompt
            if draw_object.highres_fix_negative: draw_object.negative = draw_object.highres_fix_negative
            draw_object.highres_fix_prompt = None
            draw_object.highres_fix_negative = None

            # run stablecog dream using draw object
            loop.create_task(stable_cog.dream_object(draw_object))

        except Exception as e:
            print_exception(e, interaction, loop)

    # the 🔁 button will take the same parameters for the image, change the seed, and add a task to the queue
    @discord.ui.button(
        custom_id='button_re-roll',
        row=0,
        emoji='🔁')
    async def button_reroll(self, button: Button, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return
            stable_cog: stablecog.StableCog = self.stable_cog

            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                input_object = await get_input_object(stable_cog, interaction, '🔁')
                if input_object == None: return

            # setup draw object to send to the stablecog
            draw_object = copy.copy(input_object)
            draw_object.seed = None
            draw_object.ctx = interaction
            draw_object.view = None
            draw_object.payload = None
            if not draw_object.init_url: draw_object.strength = None

            # run stablecog dream using draw object
            loop.create_task(stable_cog.dream_object(draw_object))

        except Exception as e:
            print_exception(e, interaction, loop)

    # the button to delete generated images
    @discord.ui.button(
        custom_id='button_extra',
        row=0,
        emoji='🔧')
    async def button_extra(self, button: Button, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return
            stable_cog: stablecog.StableCog = self.stable_cog

            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                input_object = await get_input_object(stable_cog, interaction, '🔧')
                if input_object == None: return

            view = DrawExtendedView(input_object)
            loop.create_task(interaction.response.edit_message(view=view))

        except Exception as e:
            print_exception(e, interaction, loop)


class DrawExtendedView(View):
    def __init__(self, input_object: utility.DrawObject, page: int = 4):
        super().__init__(timeout=None)
        self.input_object: utility.DrawObject = input_object
        self.stable_cog = discord_bot.get_cog('StableCog')
        self.upscale_cog = discord_bot.get_cog('UpscaleCog')
        self.extra_items: list[discord.ui.Item] = []
        self.page_buttons: list[discord.ui.Button] = []

        labels = [
            'Checkpoint / Resolution / Sampler',
            'Guidance Scale / Style',
            'Batch / Steps / Strength' if input_object and input_object.init_url else 'Batch / Steps',
            'More'
        ]

        for index, label in enumerate(labels):
            button_page = index + 1
            button = Button(
                label=label,
                custom_id=f'button_extra_page_{button_page}',
                row=4,
                emoji='🧩',
                style=discord.ButtonStyle.success
            )
            self.page_buttons.append(button)
            self.add_item(button)

        self.page = 0
        self.setup_page(page)

    def add_extra_item(self, item: discord.ui.Item):
        self.extra_items.append(item)
        self.add_item(item)

    def clear_extra_items(self):
        for item in self.extra_items:
            self.remove_item(item)
        self.extra_items = []

    def setup_page(self, page: int):
        if self.page == page: return
        if self.input_object == None: return

        self.page = page
        self.clear_extra_items()

        for index, button in enumerate(self.page_buttons):
            button_page = index + 1
            button.disabled = (self.page == button_page)

        match self.page:
            case 1:
                # setup select for checkpoint
                placeholder = f'Change Checkpoint - Current: {self.input_object.model_name}'

                options: list[discord.SelectOption] = []
                for (display_name, full_name) in settings.global_var.model_names.items():
                    options.append(discord.SelectOption(
                        label=display_name,
                        description=full_name
                    ))
                    if len(options) >= 25: break

                self.add_extra_item(Select(
                    placeholder=placeholder,
                    custom_id='button_extra_checkpoint',
                    row=1,
                    min_values=1,
                    max_values=1,
                    options=options,
                ))

                # setup select for resolution
                placeholder = f'Change Resolution - Current: {self.input_object.width} x {self.input_object.height}'

                self.add_extra_item(Select(
                    placeholder=placeholder,
                    custom_id='button_extra_resolution',
                    row=2,
                    min_values=1,
                    max_values=1,
                    options=[
                        discord.SelectOption(label='Upscale img2img 1024 x 1024', description='Send image to img2img to upscale to 1024 x 1024'),
                        discord.SelectOption(label='Upscale 4x', description='Send image to upscaler at 4x resolution'),
                        discord.SelectOption(label='512 x 512', description='Default resolution'),
                        discord.SelectOption(label='768 x 768', description='High resolution'),
                        discord.SelectOption(label='768 x 512', description='Landscape'),
                        discord.SelectOption(label='512 x 768', description='Portrait'),
                        discord.SelectOption(label='1024 x 576', description='16:9 Landscape'),
                        discord.SelectOption(label='576 x 1024', description='16:9 Portrait'),
                        discord.SelectOption(label='1024 x 1024', description='Maximum Resolution'),
                    ],
                ))

                # setup select for sampler
                placeholder = f'Change Sampler - Current: {self.input_object.sampler}'

                options: list[discord.SelectOption] = []
                for sampler in settings.global_var.sampler_names:
                    options.append(discord.SelectOption(
                        label=sampler
                    ))
                    if len(options) >= 25: break

                self.add_extra_item(Select(
                    placeholder=placeholder,
                    custom_id='button_extra_sampler',
                    row=3,
                    min_values=1,
                    max_values=1,
                    options=options,
                ))

            case 2:
                # setup select for guidance scale
                placeholder = f'Change Guidance Scale - Current: {self.input_object.guidance_scale}'

                options: list[discord.SelectOption] = []
                if self.input_object:
                    guidance_scale = self.input_object.guidance_scale
                    if guidance_scale - 5.0 >= 1.0: options.append(discord.SelectOption(label=f'Guidance Scale = {guidance_scale - 5.0}', description='Guidance Scale -5'))
                    if guidance_scale - 2.0 >= 1.0: options.append(discord.SelectOption(label=f'Guidance Scale = {guidance_scale - 2.0}', description='Guidance Scale -2'))
                    if guidance_scale - 1.0 >= 1.0: options.append(discord.SelectOption(label=f'Guidance Scale = {guidance_scale - 1.0}', description='Guidance Scale -1'))
                    if guidance_scale - 0.1 >= 1.0: options.append(discord.SelectOption(label=f'Guidance Scale = {guidance_scale - 0.1}', description='Guidance Scale -0.1'))
                    if guidance_scale + 0.1 <= 30.0: options.append(discord.SelectOption(label=f'Guidance Scale = {guidance_scale + 0.1}', description='Guidance Scale +0.1'))
                    if guidance_scale + 1.0 <= 30.0: options.append(discord.SelectOption(label=f'Guidance Scale = {guidance_scale + 1.0}', description='Guidance Scale +1'))
                    if guidance_scale + 2.0 <= 30.0: options.append(discord.SelectOption(label=f'Guidance Scale = {guidance_scale + 2.0}', description='Guidance Scale +2'))
                    if guidance_scale + 5.0 <= 30.0: options.append(discord.SelectOption(label=f'Guidance Scale = {guidance_scale + 5.0}', description='Guidance Scale +5'))

                self.add_extra_item(Select(
                    placeholder=placeholder,
                    custom_id='button_extra_guidance_scale',
                    row=1,
                    min_values=1,
                    max_values=1,
                    options=options,
                ))

                # setup select for style
                placeholder = f'Change Style - Current: {self.input_object.style}'

                options: list[discord.SelectOption] = []
                for key, value in settings.global_var.style_names.items():
                    values: list[str] = value.split('\n')
                    style_prompt = values[0]
                    style_negative = values[1]

                    description = style_prompt
                    if style_negative:
                        if description:
                            description += f' negative: {style_negative}'
                        else:
                            description = f'negative: {style_negative}'

                    if len(description) >= 100:
                        description = description[0:100]

                    options.append(discord.SelectOption(
                        label=key,
                        description=description
                    ))

                    if len(options) >= 25: break

                self.add_extra_item(Select(
                    placeholder=placeholder,
                    custom_id='button_extra_style',
                    row=2,
                    min_values=1,
                    max_values=1,
                    options=options,
                ))

            case 3:
                # setup select for batch
                placeholder = f'Change Batch - Current: {self.input_object.batch}'

                options: list[discord.SelectOption] = []
                if self.input_object:
                    guild = utility.get_guild(self.input_object.ctx)
                    max_batch = settings.read(guild)['max_count']
                    if max_batch > 25: max_batch = 25
                    for count in range(1, max_batch + 1):
                        options.append(discord.SelectOption(label=f'Batch = {count}'))

                self.add_extra_item(Select(
                    placeholder=placeholder,
                    custom_id='button_extra_batch',
                    row=1,
                    min_values=1,
                    max_values=1,
                    options=options,
                ))

                # setup select for steps
                placeholder = f'Change Steps - Current: {self.input_object.steps}'

                options: list[discord.SelectOption] = []
                if self.input_object:
                    guild = utility.get_guild(self.input_object.ctx)
                    steps = self.input_object.steps
                    max_steps = settings.read(guild)['max_steps']
                    if steps - 20 >= 1: options.append(discord.SelectOption(label=f'Steps = {steps - 20}', description='Steps -20'))
                    if steps - 10 >= 1: options.append(discord.SelectOption(label=f'Steps = {steps - 10}', description='Steps -10'))
                    if steps - 5 >= 1: options.append(discord.SelectOption(label=f'Steps = {steps - 5}', description='Steps -5'))
                    if steps - 1 >= 1: options.append(discord.SelectOption(label=f'Steps = {steps - 1}', description='Steps -1'))
                    if steps + 1 <= max_steps: options.append(discord.SelectOption(label=f'Steps = {steps + 1}', description='Steps +1'))
                    if steps + 5 <= max_steps: options.append(discord.SelectOption(label=f'Steps = {steps + 5}', description='Steps +5'))
                    if steps + 10 <= max_steps: options.append(discord.SelectOption(label=f'Steps = {steps + 10}', description='Steps +10'))
                    if steps + 20 <= max_steps: options.append(discord.SelectOption(label=f'Steps = {steps + 20}', description='Steps +20'))

                self.add_extra_item(Select(
                    placeholder=placeholder,
                    custom_id='button_extra_steps',
                    row=2,
                    min_values=1,
                    max_values=1,
                    options=options,
                ))

                # setup select for strength
                if self.input_object.init_url:
                    placeholder = f'Change Denoising Strength - Current: {self.input_object.strength}'

                    options: list[discord.SelectOption] = []
                    if self.input_object:
                        options.append(discord.SelectOption(label=f'Strength = {1.0}', description='Extreme Changes'))
                        options.append(discord.SelectOption(label=f'Strength = {0.95}', description='Large Changes'))
                        options.append(discord.SelectOption(label=f'Strength = {0.9}', description='Large Changes'))
                        options.append(discord.SelectOption(label=f'Strength = {0.85}', description='Large Changes'))
                        options.append(discord.SelectOption(label=f'Strength = {0.8}', description='Moderate Changes'))
                        options.append(discord.SelectOption(label=f'Strength = {0.75}', description='Moderate Changes'))
                        options.append(discord.SelectOption(label=f'Strength = {0.7}', description='Moderate Changes'))
                        options.append(discord.SelectOption(label=f'Strength = {0.65}', description='Small Changes'))
                        options.append(discord.SelectOption(label=f'Strength = {0.6}', description='Small Changes'))
                        options.append(discord.SelectOption(label=f'Strength = {0.55}', description='Small Changes'))
                        options.append(discord.SelectOption(label=f'Strength = {0.5}', description='Minimal Changes'))
                        options.append(discord.SelectOption(label=f'Strength = {0.45}', description='Minimal Changes'))
                        options.append(discord.SelectOption(label=f'Strength = {0.4}', description='Finetuning'))
                        options.append(discord.SelectOption(label=f'Strength = {0.3}', description='Finetuning'))
                        options.append(discord.SelectOption(label=f'Strength = {0.2}', description='Finetuning'))

                    self.add_extra_item(Select(
                        placeholder=placeholder,
                        custom_id='button_extra_strength',
                        row=3,
                        min_values=1,
                        max_values=1,
                        options=options,
                    ))

            case 4:
                # setup buttons for other options
                if self.input_object.init_url:
                    self.add_extra_item(Button(
                        label='Remove Init Image',
                        custom_id='button_extra_remove_init_image',
                        row=1,
                        emoji='✂️'
                    ))

                if self.input_object.highres_fix != None and self.input_object.highres_fix != 'None':
                    label = 'Disable HighRes Fix'
                else:
                    label = 'Enable HighRes Fix'

                self.add_extra_item(Button(
                    label=label,
                    custom_id='button_extra_highres_fix',
                    row=1,
                    emoji='🔨'
                ))

                if self.input_object.tiling:
                    label = 'Disable Tiling'
                else:
                    label = 'Enable Tiling'

                self.add_extra_item(Button(
                    label=label,
                    custom_id='button_extra_tiling',
                    row=1,
                    emoji='🪟'
                ))

                if self.input_object.facefix == 'CodeFormer':
                    label = 'Disable FaceFix (CodeFormer)'
                else:
                    label = 'Enable FaceFix (CodeFormer)'

                self.add_extra_item(Button(
                    label=label,
                    custom_id='button_extra_facefix_codeformer',
                    row=1,
                    emoji='🤔'
                ))

                if self.input_object.facefix == 'GFPGAN':
                    label = 'Disable FaceFix (GFPGAN)'
                else:
                    label = 'Enable FaceFix (GFPGAN)'

                self.add_extra_item(Button(
                    label=label,
                    custom_id='button_extra_facefix_gfpgan',
                    row=1,
                    emoji='🤨'
                ))

                # add outpainting buttons
                outpaint_directions = [['⏹️', 'Center'], ['⬆️', 'Up'], ['⬇️', 'Down'], ['⬅️', 'Left'], ['➡️', 'Right']]
                for (index, direction) in enumerate(outpaint_directions):
                    emoji = direction[0]
                    label = direction[1]
                    self.add_extra_item(Button(
                        label=f'Outpaint {label}',
                        custom_id=f'button_extra_outpaint_{label.lower()}',
                        row=2,
                        emoji=emoji
                    ))

                # add clip skip button
                if self.input_object.clip_skip == None or self.input_object.clip_skip == 1:
                    label = 'Enable CLIP Skip'
                else:
                    label = 'Disable CLIP Skip'

                self.add_extra_item(Button(
                    label=label,
                    custom_id='button_extra_clip_skip',
                    row=3,
                    emoji='🩼'
                ))

                # add control net
                self.add_extra_item(Button(
                    label='Create Variations with Controlnet',
                    custom_id='button_extra_controlnet_variation',
                    row=3,
                    emoji='🧬'
                ))

                # add control net
                if self.input_object.controlnet_url:
                    self.add_extra_item(Button(
                        label='Remove Controlnet Image',
                        custom_id='button_extra_remove_controlnet_variation',
                        row=3,
                        emoji='✂️'
                    ))


    # the 🖋 button will allow a new prompt and keep same parameters for everything else
    @discord.ui.button(
        label='Change Prompt',
        custom_id='button_extra-re-prompt',
        row=0,
        emoji='🖋')
    async def button_draw(self, button: Button, interaction: discord.Interaction):
        await DrawView.button_draw(self, button, interaction)

    # the 🖼️ button will take the same parameters for the image, send the original image to init_image, change the seed, and add a task to the queue
    @discord.ui.button(
        label='Create Variations with Init Image',
        custom_id='button_extra-image-variation',
        row=0,
        emoji='🖼️')
    async def button_draw_variation(self, button: Button, interaction: discord.Interaction):
        await DrawView.button_draw_variation(self, button, interaction)

    # the 🔁 button will take the same parameters for the image, change the seed, and add a task to the queue
    @discord.ui.button(
        label='Random Seed',
        custom_id='button_extra-re-roll',
        row=0,
        emoji='🔁')
    async def button_reroll(self, button: Button, interaction: discord.Interaction):
        await DrawView.button_reroll(self, button, interaction)

    # the button to delete generated images
    @discord.ui.button(
        label='Tweaks',
        custom_id='button_extra-hide',
        row=0,
        emoji='🔧')
    async def button_extra(self, button: Button, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return
            stable_cog: stablecog.StableCog = self.stable_cog

            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                input_object = await get_input_object(stable_cog, interaction, '🔧')
                if input_object == None: return

            # switch back to regular view
            view = DrawView(input_object)
            loop.create_task(interaction.response.edit_message(view=view))

        except Exception as e:
            print_exception(e, interaction, loop)

    # the button to delete generated images
    @discord.ui.button(
        label='Delete',
        custom_id='button_extra-x',
        row=0,
        emoji='❌')
    async def button_delete(self, button: Button, interaction: discord.Interaction):
        await user_delete(interaction)

    async def button_extra_callback(self, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return
            message = await get_message(interaction)
            custom_id = interaction.custom_id
            stable_cog: stablecog.StableCog = self.stable_cog

            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                input_object = await get_input_object(stable_cog, interaction, ' ')
                if input_object == None: return

            if custom_id.startswith('button_extra_page_'):
                page = int(interaction.custom_id.replace('button_extra_page_', '', 1))
                self.setup_page(page)
                if self.input_object:
                    loop.create_task(interaction.response.edit_message(view=self))
                else:
                    view = DrawExtendedView(input_object, self.page)
                    loop.create_task(interaction.response.edit_message(view=view))
                return

            # make a copy for this dream
            draw_object = copy.copy(input_object)
            draw_object.ctx = interaction
            draw_object.view = None
            draw_object.payload = None

            try:
                value = str(interaction.data['values'][0]).strip()
            except:
                value = None

            page = self.page
            def refresh_view():
                if self.input_object:
                    self.setup_page(page)
                    loop.create_task(interaction.followup.edit_message(message_id=message.id, view=self))
                elif input_object:
                    view = DrawExtendedView(input_object, self.page)
                    loop.create_task(interaction.followup.edit_message(message_id=message.id, view=view))

            match custom_id:
                case 'button_extra_checkpoint':
                    page = 1
                    if value not in settings.global_var.model_names:
                        loop.create_task(interaction.response.send_message('Unknown checkpoint! I have updated the options for you to try again.', ephemeral=True, delete_after=30))
                        loop.create_task(interaction.followup.edit_message(message_id=message.id, view=self))
                        return
                    draw_object.model_name = value

                case 'button_extra_resolution':
                    page = 1
                    task = value.split(' ')
                    if task[0] == 'Upscale':
                        # upscale image
                        init_url = message.attachments[0].url
                        if not init_url:
                            loop.create_task(interaction.response.send_message('The image seems to be missing. This interaction no longer works.', ephemeral=True, delete_after=30))
                            refresh_view()
                            return

                        if task[1] == 'img2img':
                            # upscale image using latent diffusion
                            draw_object.width = 1024
                            draw_object.height = 1024
                            draw_object.init_url = init_url
                            draw_object.strength = 0.2
                            draw_object.batch = 1

                            # use inpaint or refiner model if it exists
                            model_name_new = settings.get_inpaint_model(draw_object.model_name)
                            if model_name_new:
                                draw_object.model_name = model_name_new
                                draw_object.data_model = settings.global_var.model_names[model_name_new]
                            else:
                                draw_object.model_name = None
                                draw_object.data_model = None

                            # transfer highres prompt to main prompt
                            draw_object.highres_fix = None
                            if draw_object.highres_fix_prompt: draw_object.prompt = draw_object.highres_fix_prompt
                            if draw_object.highres_fix_negative: draw_object.negative = draw_object.highres_fix_negative
                            draw_object.highres_fix_prompt = None
                            draw_object.highres_fix_negative = None

                        else:
                            script = None
                            if len(message.attachments) > 1:
                                audio_url = message.attachments[1].url
                                if audio_url.endswith('.mp3'):
                                    script = 'spectrogram from image'

                            # upscale image with upscale cog
                            upscale_cog: upscalecog.UpscaleCog = self.upscale_cog
                            loop.create_task(upscale_cog.dream_handler(interaction, init_url=init_url, script=script))
                            refresh_view()
                            return

                    else:
                        # change resolution
                        resolution = value.split('x')
                        width = None
                        height = None

                        try:
                            width = int(resolution[0].strip())
                            height = int(resolution[1].strip())
                        except:
                            pass

                        if width not in [x for x in range(192, 1025, 64)]: width = None
                        if height not in [x for x in range(192, 1025, 64)]: height = None

                        if width != None: draw_object.width = width
                        if height != None: draw_object.height = height

                case 'button_extra_sampler':
                    page = 1
                    if value not in settings.global_var.sampler_names:
                        loop.create_task(interaction.response.send_message('Unknown sampler! I have updated the options for you to try again.', ephemeral=True, delete_after=30))
                        refresh_view()
                        return
                    draw_object.sampler = value

                case 'button_extra_guidance_scale':
                    page = 2
                    draw_object.guidance_scale = round(float(value.split('=')[1].strip()), 2)

                case 'button_extra_style':
                    page = 2
                    if value != None and value != 'None' and value not in settings.global_var.style_names:
                        loop.create_task(interaction.response.send_message('Unknown style! I have updated the options for you to try again.', ephemeral=True, delete_after=30))
                        refresh_view()
                        return
                    draw_object.style = value

                case 'button_extra_batch':
                    page = 3
                    draw_object.batch = int(value.split('=')[1].strip())

                case 'button_extra_steps':
                    page = 3
                    draw_object.steps = int(value.split('=')[1].strip())

                case 'button_extra_strength':
                    page = 3
                    draw_object.strength = round(float(value.split('=')[1].strip()), 2)

                case 'button_extra_clip_skip':
                    page = 4
                    # draw_object.clip_skip = int(value.split('=')[1].strip())
                    if draw_object.clip_skip == None or draw_object.clip_skip == 1:
                        draw_object.clip_skip = 2
                    else:
                        draw_object.clip_skip = 1

                case 'button_extra_remove_init_image':
                    page = 4
                    draw_object.init_url = None

                    if draw_object.script:
                        if draw_object.script.startswith('inpaint') or draw_object.script.startswith('outpaint'):
                            draw_object.script = None

                    if (draw_object.model_name != None and (draw_object.model_name.endswith('_inpaint') or draw_object.model_name.endswith('_refiner'))):
                        model_name_new = settings.get_non_inpaint_model(draw_object.model_name)
                        if model_name_new:
                            draw_object.model_name = model_name_new
                            draw_object.data_model = settings.global_var.model_names[model_name_new]
                        else:
                            draw_object.model_name = None
                            draw_object.data_model = None

                case 'button_extra_highres_fix':
                    page = 4
                    if input_object.highres_fix != None and input_object.highres_fix != 'None':
                        draw_object.highres_fix = None
                    else:
                        if 'Latent' in settings.global_var.highres_upscaler_names:
                            draw_object.highres_fix = 'Latent'
                        else:
                            for hires_upscaler in settings.global_var.highres_upscaler_names:
                                if hires_upscaler != 'None':
                                    draw_object.highres_fix = hires_upscaler
                                    break

                case 'button_extra_tiling':
                    page = 4
                    draw_object.tiling = (input_object.tiling != True)

                case 'button_extra_facefix_codeformer':
                    page = 4
                    if input_object.facefix == 'CodeFormer':
                        facefix = None
                    else:
                        facefix = 'CodeFormer'
                        if facefix not in settings.global_var.facefix_models:
                            raise Exception() # this shouldn't happen unless the API has changed

                case 'button_extra_facefix_gfpgan':
                    page = 4
                    if input_object.facefix == 'GFPGAN':
                        facefix = None
                    else:
                        facefix = 'GFPGAN'
                        if facefix not in settings.global_var.facefix_models:
                            raise Exception() # this shouldn't happen unless the API has changed

                case 'button_extra_controlnet_variation':
                    page = 4

                    # obtain URL for the original image
                    controlnet_url = message.attachments[0].url
                    if not controlnet_url:
                        loop.create_task(interaction.response.send_message('The image seems to be missing. This interaction no longer works.', ephemeral=True, delete_after=30))
                        return

                    # get input object
                    if self.input_object:
                        input_object = self.input_object
                    else:
                        input_object = await get_input_object(stable_cog, interaction, '🧬')
                        if input_object == None: return

                    # setup draw object to send to the stablecog
                    draw_object = copy.copy(input_object)
                    draw_object.seed = None
                    draw_object.ctx = interaction
                    draw_object.view = None
                    draw_object.payload = None
                    # draw_object.init_url = None
                    draw_object.controlnet_url = controlnet_url
                    if draw_object.script:
                        if draw_object.script.startswith('inpaint'):
                            draw_object.script = None
                        elif draw_object.script.startswith('outpaint'):
                            draw_object.script = None
                            draw_object.strength = None

                    # remove init image variation
                    draw_object.init_url = None

                    # transfer highres prompt to main prompt
                    draw_object.highres_fix = None
                    if draw_object.highres_fix_prompt: draw_object.prompt = draw_object.highres_fix_prompt
                    if draw_object.highres_fix_negative: draw_object.negative = draw_object.highres_fix_negative
                    draw_object.highres_fix_prompt = None
                    draw_object.highres_fix_negative = None

                case 'button_extra_remove_controlnet_variation':
                    page = 4
                    draw_object.controlnet_model = None
                    draw_object.controlnet_preprocessor = None
                    draw_object.controlnet_data_model = None
                    draw_object.controlnet_url = None

                    if draw_object.script:
                        if draw_object.script.startswith('inpaint') or draw_object.script.startswith('outpaint'):
                            draw_object.script = None

                    if (draw_object.model_name != None and 'inpaint' in draw_object.model_name) or (draw_object.data_model and 'inpaint' in draw_object.data_model):
                        draw_object.model_name = None
                        draw_object.data_model = None

                case other:
                    # outpainting directions
                    if custom_id.startswith('button_extra_outpaint_'):
                        page = 4

                        init_url = message.attachments[0].url
                        if not init_url:
                            loop.create_task(interaction.response.send_message('The image seems to be missing. This interaction no longer works.', ephemeral=True, delete_after=30))
                            refresh_view()
                            return

                        if draw_object.model_name == 'Default':
                            for (display_name, full_name) in settings.global_var.model_names.items():
                                if 'inpaint' in display_name:
                                    draw_object.model_name = display_name
                                    draw_object.data_model = full_name
                                    break

                        custom_id_outpaint = custom_id.replace('button_extra_outpaint_', '', 1)
                        draw_object.script = f'outpaint {custom_id_outpaint}'
                        draw_object.init_url = init_url
                        draw_object.strength = 1.0
                        draw_object.seed = None

                        # transfer highres prompt to main prompt
                        draw_object.highres_fix = None
                        if draw_object.highres_fix_prompt: draw_object.prompt = draw_object.highres_fix_prompt
                        if draw_object.highres_fix_negative: draw_object.negative = draw_object.highres_fix_negative
                        draw_object.highres_fix_prompt = None
                        draw_object.highres_fix_negative = None

            # start dream
            loop.create_task(stable_cog.dream_object(draw_object))
            refresh_view()

        except Exception as e:
            print_exception(e, interaction, loop)

# creating the view that holds a button to delete output
class DeleteView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        custom_id='button_x',
        row=0,
        emoji='❌')
    async def button_delete(self, button: Button, interaction: discord.Interaction):
        await user_delete(interaction)

# shared utility functions
user_last_delete: dict = {}

async def user_delete(interaction: discord.Interaction):
    loop = asyncio.get_running_loop()
    try:
        if check_interaction_permission(interaction, loop) == False: return
        message = await get_message(interaction)

        if not message.content.startswith(f'<@{interaction.user.id}>'):
            loop.create_task(interaction.response.send_message('You can\'t delete other people\'s images!', ephemeral=True, delete_after=30))
            return

        if confirm_user_delete(interaction.user.id):
            loop.create_task(interaction.response.send_modal(DeleteModal(message)))
        else:
            loop.create_task(interaction.message.delete())
            update_user_delete(interaction.user.id)

    except Exception as e:
        print_exception(e, interaction, loop)

def confirm_user_delete(user_id: int):
    try:
        return (time.time() - float(user_last_delete[str(user_id)])) > 30.0
    except:
        return True

def update_user_delete(user_id: int):
    user_last_delete_update = {
        f'{user_id}': time.time()
    }
    user_last_delete.update(user_last_delete_update)

async def get_input_object(stable_cog, interaction: discord.Interaction, emoji: str = None, message: discord.Message = None):
    loop = asyncio.get_running_loop()

    # create input object from message command
    if message == None: message = await get_message(interaction)
    if '``/dream ' in message.content:
        # retrieve command from message
        command = utility.find_between(message.content, '``/dream ', '``')
        return stable_cog.get_draw_object_from_command(command)
    elif '``/minigame ' in message.content:
        loop.create_task(interaction.response.send_message('I may have been restarted. This interaction no longer works.\nPlease start a new minigame using the /minigame command.', ephemeral=True, delete_after=30))
        return None
    else:
        # retrieve command from cache
        command = settings.get_dream_command(message.id)
        if command:
            return stable_cog.get_draw_object_from_command(command)
        else:
            if emoji == ' ':
                loop.create_task(interaction.response.send_message(f'I may have been restarted. This interaction no longer works.\nPlease try again on a message containing the full /dream command.', ephemeral=True, delete_after=30))
            elif emoji:
                loop.create_task(interaction.response.send_message(f'I may have been restarted. This interaction no longer works.\nPlease try using {emoji} on a message containing the full /dream command.', ephemeral=True, delete_after=30))
            else:
                loop.create_task(interaction.response.send_message('I may have been restarted. This interaction no longer works.', ephemeral=True, delete_after=30))
            return None

def check_interaction_permission(interaction: discord.Interaction, loop: asyncio.AbstractEventLoop):
    try:
        if interaction.channel.permissions_for(interaction.user).use_application_commands:
            return True
        else:
            loop.create_task(interaction.response.send_message('You do not have permission to interact with this channel.', ephemeral=True, delete_after=30))
            return False
    except:
        return True

async def get_message(interaction: discord.Interaction):
    if interaction.message == None:
        message = await interaction.original_response()
        interaction.message = message
    else:
        message = interaction.message
    return message

def print_exception(e: Exception, interaction: discord.Interaction, loop: asyncio.AbstractEventLoop):
    user = interaction.user
    content = f'<@{user.id}> Something went wrong.\n{e}'
    print(content + f'\n{traceback.print_exc()}')
    loop.create_task(interaction.response.send_message(content, ephemeral=True, delete_after=30))
