import discord
import copy
import traceback
import time
import asyncio
from discord.ui import Button, Select, InputText, Modal, View

from core import settings
from core import utility
from core import stablecog

discord_bot: discord.Bot = None

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
            extra_settings_value += f'\nstrength: {self.input_object.strength}'
        else:
            init_url = ''

        extra_settings_value += f'\nsteps: {self.input_object.steps}'
        extra_settings_value += f'\nguidance_scale: {self.input_object.guidance_scale}'

        extra_settings_value += f'\n\ncheckpoint: {self.input_object.model_name}'
        extra_settings_value += f'\nwidth: {self.input_object.width}'
        extra_settings_value += f'\nheight: {self.input_object.height}'
        extra_settings_value += f'\nstyle: {self.input_object.style}'

        extra_settings_value += f'\n\nfacefix: {self.input_object.facefix}'
        extra_settings_value += f'\ntiling: {self.input_object.tiling}'
        extra_settings_value += f'\nhighres_fix: {self.input_object.highres_fix}'
        extra_settings_value += f'\nclip_skip: {self.input_object.clip_skip}'
        extra_settings_value += f'\nscript: {self.input_object.script}'

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
                if 'checkpoint' in commands:        draw_object.model_name      = command_draw_object.model_name
                if 'width' in commands:             draw_object.width           = command_draw_object.width
                if 'height' in commands:            draw_object.height          = command_draw_object.height
                if 'steps' in commands:             draw_object.steps           = command_draw_object.steps
                if 'guidance_scale' in commands:    draw_object.guidance_scale  = command_draw_object.guidance_scale
                if 'strength' in commands:          draw_object.strength        = command_draw_object.strength
                if 'style' in commands:             draw_object.style           = command_draw_object.style
                if 'facefix' in commands:           draw_object.facefix         = command_draw_object.facefix
                if 'tiling' in commands:            draw_object.tiling          = command_draw_object.tiling
                if 'highres_fix' in commands:       draw_object.highres_fix     = command_draw_object.highres_fix
                if 'clip_skip' in commands:         draw_object.clip_skip       = command_draw_object.clip_skip
                if 'batch' in commands:             draw_object.batch           = command_draw_object.batch
                if 'script' in commands:            draw_object.script          = command_draw_object.script
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
    def __init__(self, stable_cog, input_object: utility.DrawObject):
        super().__init__(timeout=None)
        self.stable_cog = stable_cog
        self.input_object: utility.DrawObject = input_object
        self.extended = False

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

            if self.extended:
                view = DrawView(self.stable_cog, input_object)
            else:
                view = DrawExtendedView(self.stable_cog, input_object)
            loop.create_task(interaction.response.edit_message(view=view))

        except Exception as e:
            print_exception(e, interaction, loop)


class DrawExtendedView(DrawView):
    def __init__(self, stable_cog, input_object: utility.DrawObject, page: int = 1):
        super().__init__(stable_cog, input_object)
        self.extended = True
        self.page_items: list[Button | Select] = []
        self.page = page

        match page:
            case 1: self.setup_page_1()
            case 2: self.setup_page_2()

        page_button_1 = Button(
            label='Checkpoint / Resolution / Sampler',
            custom_id='button_extra_page_1',
            row=4,
            emoji='🧩'
        )
        if page == 1: page_button_1.disabled = True
        async def button_page_1(interaction: discord.Interaction): await self.button_page_callback(interaction, 1)
        page_button_1.callback = button_page_1
        self.add_item(page_button_1)

        page_button_2 = Button(
            label='Steps / Guidance Scale / Style',
            custom_id='button_extra_page_2',
            row=4,
            emoji='🧩'
        )
        if page == 2: page_button_2.disabled = True
        async def button_page_2(interaction: discord.Interaction): await self.button_page_callback(interaction, 2)
        page_button_2.callback = button_page_2
        self.add_item(page_button_2)

    def clear_page(self):
        for item in self.page_items:
            self.remove_item(item)
        self.page_items = []

    def setup_page_1(self):
        # setup select for checkpoint
        checkpoint_placeholder = 'Change Checkpoint'
        if self.input_object: checkpoint_placeholder += f' - Current: {self.input_object.model_name}'

        checkpoint_options: list[discord.SelectOption] = []
        for (display_name, full_name) in settings.global_var.model_names.items():
            checkpoint_options.append(discord.SelectOption(
                label=display_name,
                description=full_name
            ))

        self.select_checkpoint = Select(
            placeholder=checkpoint_placeholder,
            custom_id='button_select_checkpoint',
            row=1,
            min_values=1,
            max_values=1,
            options=checkpoint_options,
        )
        self.select_checkpoint.callback = self.select_checkpoint_callback
        self.page_items.append(self.select_checkpoint)
        self.add_item(self.select_checkpoint)

        # setup select for resolution
        resolution_placeholder = 'Change Resolution'
        if self.input_object: resolution_placeholder += f' - Current: {self.input_object.width} x {self.input_object.height}'

        self.select_resolution = Select(
            placeholder=resolution_placeholder,
            custom_id='button_select_resolution',
            row=2,
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label='Upscale 4x', description='Send image to upscaler at 4x resolution'),
                discord.SelectOption(label='512 x 512', description='Default resolution'),
                discord.SelectOption(label='768 x 512', description='Landscape'),
                discord.SelectOption(label='512 x 768', description='Portrait'),
                discord.SelectOption(label='768 x 768', description='High resolution'),
                discord.SelectOption(label='1024 x 576', description='16:9 Landscape'),
                discord.SelectOption(label='576 x 1024', description='16:9 Portrait'),
            ],
        )
        self.select_resolution.callback = self.select_resolution_callback
        self.page_items.append(self.select_resolution)
        self.add_item(self.select_resolution)

        # setup select for style
        sampler_placeholder = 'Change Sampler'
        if self.input_object: sampler_placeholder += f' - Current: {self.input_object.sampler}'

        sampler_options: list[discord.SelectOption] = []
        for sampler in settings.global_var.sampler_names:
            sampler_options.append(discord.SelectOption(
                label=sampler
            ))

        self.select_sampler = Select(
            placeholder=sampler_placeholder,
            custom_id='button_select_sampler',
            row=3,
            min_values=1,
            max_values=1,
            options=sampler_options,
        )
        self.select_sampler.callback = self.select_sampler_callback
        self.page_items.append(self.select_sampler)
        self.add_item(self.select_sampler)

    def setup_page_2(self):
        # setup select for steps
        steps_placeholder = 'Change Steps'
        if self.input_object: steps_placeholder += f' - Current: {self.input_object.steps}'

        steps_options: list[discord.SelectOption] = []
        if self.input_object:
            guild = utility.get_guild(self.input_object.ctx)
            steps = self.input_object.steps
            max_steps = settings.read(guild)['max_steps']
            if steps - 10 >= 1: steps_options.append(discord.SelectOption(label=f'Steps = {steps - 10}', description='Steps -10'))
            if steps - 5 >= 1: steps_options.append(discord.SelectOption(label=f'Steps = {steps - 5}', description='Steps -5'))
            if steps - 1 >= 1: steps_options.append(discord.SelectOption(label=f'Steps = {steps - 1}', description='Steps -1'))
            if steps + 1 <= max_steps: steps_options.append(discord.SelectOption(label=f'Steps = {steps + 1}', description='Steps +1'))
            if steps + 5 <= max_steps: steps_options.append(discord.SelectOption(label=f'Steps = {steps + 5}', description='Steps +5'))
            if steps + 10 <= max_steps: steps_options.append(discord.SelectOption(label=f'Steps = {steps + 10}', description='Steps +10'))

        self.select_steps = Select(
            placeholder=steps_placeholder,
            custom_id='button_select_steps',
            row=1,
            min_values=1,
            max_values=1,
            options=steps_options,
        )
        self.select_steps.callback = self.select_steps_callback
        self.page_items.append(self.select_steps)
        self.add_item(self.select_steps)

        # setup select for guidance scale
        guidance_scale_placeholder = 'Change Guidance Scale'
        if self.input_object: guidance_scale_placeholder += f' - Current: {self.input_object.guidance_scale}'

        guidance_scale_options: list[discord.SelectOption] = []
        if self.input_object:
            guidance_scale = self.input_object.guidance_scale
            if guidance_scale - 5.0 >= 1.0: guidance_scale_options.append(discord.SelectOption(label=f'Guidance Scale = {guidance_scale - 5.0}', description='Guidance Scale -5'))
            if guidance_scale - 2.0 >= 1.0: guidance_scale_options.append(discord.SelectOption(label=f'Guidance Scale = {guidance_scale - 2.0}', description='Guidance Scale -2'))
            if guidance_scale - 1.0 >= 1.0: guidance_scale_options.append(discord.SelectOption(label=f'Guidance Scale = {guidance_scale - 1.0}', description='Guidance Scale -1'))
            if guidance_scale - 0.1 >= 1.0: guidance_scale_options.append(discord.SelectOption(label=f'Guidance Scale = {guidance_scale - 0.1}', description='Guidance Scale -0.1'))
            if guidance_scale + 0.1 <= 30.0: guidance_scale_options.append(discord.SelectOption(label=f'Guidance Scale = {guidance_scale + 0.1}', description='Guidance Scale +0.1'))
            if guidance_scale + 1.0 <= 30.0: guidance_scale_options.append(discord.SelectOption(label=f'Guidance Scale = {guidance_scale + 1.0}', description='Guidance Scale +1'))
            if guidance_scale + 2.0 <= 30.0: guidance_scale_options.append(discord.SelectOption(label=f'Guidance Scale = {guidance_scale + 2.0}', description='Guidance Scale +2'))
            if guidance_scale + 5.0 <= 30.0: guidance_scale_options.append(discord.SelectOption(label=f'Guidance Scale = {guidance_scale + 5.0}', description='Guidance Scale +5'))

        self.select_guidance_scale = Select(
            placeholder=guidance_scale_placeholder,
            custom_id='button_select_guidance_scale',
            row=2,
            min_values=1,
            max_values=1,
            options=guidance_scale_options,
        )
        self.select_guidance_scale.callback = self.select_guidance_scale_callback
        self.page_items.append(self.select_guidance_scale)
        self.add_item(self.select_guidance_scale)

        # setup select for style
        style_placeholder = 'Change Style'
        if self.input_object: style_placeholder += f' - Current: {self.input_object.style}'

        style_options: list[discord.SelectOption] = []
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

            style_options.append(discord.SelectOption(
                label=key,
                description=description
            ))

        self.select_style = Select(
            placeholder=style_placeholder,
            custom_id='button_select_style',
            row=3,
            min_values=1,
            max_values=1,
            options=style_options,
        )
        self.select_style.callback = self.select_style_callback
        self.page_items.append(self.select_style)
        self.add_item(self.select_style)

    # switches page
    async def button_page_callback(self, interaction: discord.Interaction, page: int = 1):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return
            stable_cog: stablecog.StableCog = self.stable_cog

            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                input_object = await get_input_object(stable_cog, interaction)
                if input_object == None: return

            # setup new page
            view = DrawExtendedView(stable_cog, input_object, page)
            loop.create_task(interaction.response.edit_message(view=view))

        except Exception as e:
            print_exception(e, interaction, loop)

    async def select_checkpoint_callback(self, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return
            stable_cog: stablecog.StableCog = self.stable_cog

            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                input_object = await get_input_object(stable_cog, interaction)
                if input_object == None: return

            # verify checkpoint
            checkpoint = self.select_checkpoint.values[0]
            if checkpoint not in settings.global_var.model_names:
                view = DrawExtendedView(self.stable_cog, input_object, self.page)
                loop.create_task(interaction.response.edit_message(view=view))
                loop.create_task(interaction.followup.edit_message('Unknown checkpoint! I have updated the options for you to try again.', ephemeral=True, delete_after=30))
                return

            # start dream
            draw_object = copy.copy(input_object)
            draw_object.model_name = checkpoint
            draw_object.ctx = interaction
            draw_object.view = None
            draw_object.payload = None

            loop.create_task(stable_cog.dream_object(draw_object))

        except Exception as e:
            print_exception(e, interaction, loop)

    async def select_resolution_callback(self, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return
            stable_cog: stablecog.StableCog = self.stable_cog
            message = await get_message(interaction)

            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                input_object = await get_input_object(stable_cog, interaction, message=message)
                if input_object == None: return

            if self.select_resolution.values[0].startswith('Upscale'):
                # upscale image
                upscale_cog = discord_bot.get_cog('UpscaleCog')
                if upscale_cog == None: raise Exception()

                init_url = message.attachments[0].url
                if not init_url:
                    loop.create_task(interaction.response.send_message('The image seems to be missing. This interaction no longer works.', ephemeral=True, delete_after=30))
                    return

                loop.create_task(upscale_cog.dream_handler(interaction, init_url=init_url))
            else:
                # verify resolution
                resolution = self.select_resolution.values[0].split('x')
                width = None
                height = None

                try:
                    width = int(resolution[0].strip())
                    height = int(resolution[1].strip())
                except:
                    pass

                if width not in [x for x in range(192, 1025, 64)]: width = None
                if height not in [x for x in range(192, 1025, 64)]: height = None

                if width == None: width = input_object.width
                if height == None: height = input_object.height

                # start dream
                draw_object = copy.copy(input_object)
                draw_object.width = width
                draw_object.height = height
                draw_object.ctx = interaction
                draw_object.view = None
                draw_object.payload = None

                loop.create_task(stable_cog.dream_object(draw_object))

        except Exception as e:
            print_exception(e, interaction, loop)

    async def select_sampler_callback(self, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return
            stable_cog: stablecog.StableCog = self.stable_cog

            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                input_object = await get_input_object(stable_cog, interaction)
                if input_object == None: return

            # verify style
            sampler = self.select_sampler.values[0]
            if sampler not in settings.global_var.sampler_names:
                view = DrawExtendedView(self.stable_cog, input_object, self.page)
                loop.create_task(interaction.response.edit_message(view=view))
                loop.create_task(interaction.followup.edit_message('Unknown sampler! I have updated the options for you to try again.', ephemeral=True, delete_after=30))
                return

            # start dream
            draw_object = copy.copy(input_object)
            draw_object.sampler = sampler
            draw_object.ctx = interaction
            draw_object.view = None
            draw_object.payload = None

            loop.create_task(stable_cog.dream_object(draw_object))

        except Exception as e:
            print_exception(e, interaction, loop)

    async def select_steps_callback(self, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return
            stable_cog: stablecog.StableCog = self.stable_cog

            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                input_object = await get_input_object(stable_cog, interaction)
                if input_object == None: return

            # get steps
            steps = int(self.select_steps.values[0].split('=')[1].strip())

            # start dream
            draw_object = copy.copy(input_object)
            draw_object.steps = steps
            draw_object.ctx = interaction
            draw_object.view = None
            draw_object.payload = None

            loop.create_task(stable_cog.dream_object(draw_object))

        except Exception as e:
            print_exception(e, interaction, loop)

    async def select_guidance_scale_callback(self, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return
            stable_cog: stablecog.StableCog = self.stable_cog

            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                input_object = await get_input_object(stable_cog, interaction)
                if input_object == None: return

            # get guidance scale
            guidance_scale = round(float(self.select_guidance_scale.values[0].split('=')[1].strip()), 2)

            # start dream
            draw_object = copy.copy(input_object)
            draw_object.guidance_scale = guidance_scale
            draw_object.ctx = interaction
            draw_object.view = None
            draw_object.payload = None

            loop.create_task(stable_cog.dream_object(draw_object))

        except Exception as e:
            print_exception(e, interaction, loop)

    async def select_style_callback(self, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return
            stable_cog: stablecog.StableCog = self.stable_cog

            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                input_object = await get_input_object(stable_cog, interaction)
                if input_object == None: return

            # verify style
            style = self.select_style.values[0]
            if style not in settings.global_var.style_names:
                view = DrawExtendedView(self.stable_cog, input_object, self.page)
                loop.create_task(interaction.response.edit_message(view=view))
                loop.create_task(interaction.followup.edit_message('Unknown style! I have updated the options for you to try again.', ephemeral=True, delete_after=30))
                return

            # start dream
            draw_object = copy.copy(input_object)
            draw_object.style = style
            draw_object.ctx = interaction
            draw_object.view = None
            draw_object.payload = None

            loop.create_task(stable_cog.dream_object(draw_object))

        except Exception as e:
            print_exception(e, interaction, loop)

    # the button to delete generated images
    @discord.ui.button(
        custom_id='button_x',
        row=0,
        emoji='❌')
    async def delete(self, button: Button, interaction: discord.Interaction):
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

# the view used after the bot restarts
class OfflineView(DrawExtendedView):
    def __init__(self, stable_cog, input_object: utility.DrawObject):
        super().__init__(stable_cog, input_object)
        self.extended = False

    # the 🏳️ ends the game and reveals the answer
    @discord.ui.button(
        custom_id='button_giveup',
        row=4,
        emoji='🏳️')
    async def button_draw_giveup(self, button: Button, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        loop.create_task(interaction.response.send_message('I may have been restarted. This interaction no longer works.\nPlease start a new minigame using the /minigame command.', ephemeral=True, delete_after=30))
        return

    # guess prompt button
    @discord.ui.button(
        custom_id='button_guess-prompt',
        row=4,
        emoji='⌨️')
    async def guess_prompt(self, button: Button, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        loop.create_task(interaction.response.send_message('I may have been restarted. This interaction no longer works.\nPlease start a new minigame using the /minigame command.', ephemeral=True, delete_after=30))
        return

# creating the view that holds a button to delete output
class DeleteView(View):
    def __init__(self, user: discord.User):
        super().__init__(timeout=None)
        self.user = user

    @discord.ui.button(
        custom_id='button_x',
        row=0,
        emoji='❌')
    async def delete(self, button: Button, interaction: discord.Interaction):
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

# shared utility functions
user_last_delete: dict = {}

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
            if emoji:
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
    else:
        message = interaction.message
    return message

def print_exception(e: Exception, interaction: discord.Interaction, loop: asyncio.AbstractEventLoop):
    user = interaction.user
    content = f'<@{user.id}> Something went wrong.\n{e}'
    print(content + f'\n{traceback.print_exc()}')
    loop.create_task(interaction.response.send_message(content, ephemeral=True, delete_after=30))
