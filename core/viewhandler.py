import discord
import copy
import traceback
import time
import asyncio
from discord.ui import InputText, Modal, View

from core import queuehandler
from core import stablecog


#the modal that is used for the 🖋 button
class DrawModal(Modal):
    def __init__(self, input_object: queuehandler.DrawObject, message: discord.Message) -> None:
        super().__init__(title="Change Prompt!")
        self.input_object = input_object
        self.message = message

        self.add_item(
            InputText(
                label='Prompt',
                value=self.input_object.simple_prompt,
                style=discord.InputTextStyle.long
            )
        )

        self.add_item(
            InputText(
                label='Negative prompt (optional)',
                style=discord.InputTextStyle.long,
                value=self.input_object.negative_prompt,
                required=False
            )
        )

        self.add_item(
            InputText(
                label='Seed. Remove to randomize.',
                style=discord.InputTextStyle.short,
                value=self.input_object.seed,
                required=False
            )
        )

        extra_settings_value = f'batch: {self.input_object.batch_count}'
        extra_settings_value += f'\nsteps: {self.input_object.steps}'
        extra_settings_value += f'\nguidance_scale: {self.input_object.guidance_scale}'

        if self.input_object.init_url:
            init_url = self.input_object.init_url
            extra_settings_value += f'\nstrength: {self.input_object.strength}'
        else:
            init_url = ''

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

            stable_cog = stablecog.StableCog(self)
            draw_object = copy.copy(self.input_object)

            draw_object.simple_prompt = self.children[0].value
            draw_object.prompt = self.input_object.prompt.replace(self.input_object.simple_prompt, self.children[0].value)

            draw_object.negative_prompt = self.children[1].value

            try:
                draw_object.seed = int(self.children[2].value)
            except:
                draw_object.seed = -1

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
                if 'batch' in commands:             draw_object.batch_count     = command_draw_object.batch_count
                if 'script' in commands:            draw_object.script          = command_draw_object.script
            except:
                pass

            draw_object.ctx = interaction
            draw_object.view = None
            draw_object.payload = None

            loop.create_task(stable_cog.dream_object(draw_object))
        except Exception as e:
            print_exception('re-prompt failed', e, interaction, loop)

# create the view to confirm the deletion of an image
class DeleteModal(Modal):
    def __init__(self, message: discord.Message) -> None:
        super().__init__(title="Confirm Delete")
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
                loop.create_task(interaction.response.send_message("You can't delete other people's images!", ephemeral=True, delete_after=30))
                return

            loop.create_task(interaction.response.defer())
            loop.create_task(interaction.message.delete())
            update_user_delete(interaction.user.id)

        except Exception as e:
            print_exception('delete failed', e, interaction, loop)

#creating the view that holds the buttons for /draw output
class DrawView(View):
    def __init__(self, input_tuple: tuple | queuehandler.DrawObject):
        super().__init__(timeout=None)
        if type(input_tuple) is stablecog.StableCog:
            self.input_object = None
        elif type(input_tuple) == queuehandler.DrawObject:
            self.input_object: queuehandler.DrawObject = input_tuple
        else:
            self.input_object = queuehandler.DrawObject(*input_tuple)

    # the 🖋 button will allow a new prompt and keep same parameters for everything else
    @discord.ui.button(
        custom_id="button_re-prompt",
        emoji="🖋")
    async def button_draw(self, button: discord.Button, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        print('edit pressed')
        try:
            if check_interaction_permission(interaction, loop) == False: return
            message = await get_message(interaction)

            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                # create input object from message command
                if '``/dream ' in message.content:
                    command = self.find_between(message.content, '``/dream ', '``')
                    input_object = stablecog.StableCog(self).get_draw_object_from_command(command)
                else:
                    loop.create_task(interaction.response.send_message('I may have been restarted. This button no longer works.\nPlease try using 🖋 on a message containing the full /dream command.', ephemeral=True, delete_after=30))
                    return

            loop.create_task(interaction.response.send_modal(DrawModal(input_object, message)))

        except Exception as e:
            print_exception('re-prompt failed', e, interaction, loop)

    # the 🖼️ button will take the same parameters for the image, send the original image to init_image, change the seed, and add a task to the queue
    @discord.ui.button(
        custom_id="button_image-variation",
        emoji="🖼️")
    async def button_draw_variation(self, button: discord.Button, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return
            message = await get_message(interaction)

            # obtain URL for the original image
            init_url = message.attachments[0].url
            if not init_url:
                loop.create_task(interaction.response.send_message('The image seems to be missing. This button no longer works.', ephemeral=True, delete_after=30))
                return

            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                # create input object from message command
                if '``/dream ' in message.content:
                    command = self.find_between(message.content, '``/dream ', '``')
                    input_object = stablecog.StableCog(self).get_draw_object_from_command(command)
                else:
                    loop.create_task(interaction.response.send_message('I may have been restarted. This button no longer works.\nPlease try using 🖼️ on a message containing the full /dream command.', ephemeral=True, delete_after=30))
                    return

            # setup draw object to send to the stablecog
            draw_object = copy.copy(input_object)
            draw_object.seed = -1
            draw_object.ctx = interaction
            draw_object.view = None
            draw_object.payload = None
            draw_object.init_url = init_url

            # run stablecog dream using draw object
            loop.create_task(stablecog.StableCog(self).dream_object(draw_object))

        except Exception as e:
            print_exception('send to img2img failed', e, interaction, loop)


    # the 🔁 button will take the same parameters for the image, change the seed, and add a task to the queue
    @discord.ui.button(
        custom_id="button_re-roll",
        emoji="🔁")
    async def button_reroll(self, button: discord.Button, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return

            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                # create input object from message command
                message = await get_message(interaction)
                if '``/dream ' in message.content:
                    command = self.find_between(message.content, '``/dream ', '``')
                    input_object = stablecog.StableCog(self).get_draw_object_from_command(command)
                else:
                    loop.create_task(interaction.response.send_message('I may have been restarted. This button no longer works.\nPlease try using 🔁 on a message containing the full /dream command.', ephemeral=True, delete_after=30))
                    return

            # setup draw object to send to the stablecog
            draw_object = copy.copy(input_object)
            draw_object.seed = -1
            draw_object.ctx = interaction
            draw_object.view = None
            draw_object.payload = None

            # run stablecog dream using draw object
            loop.create_task(stablecog.StableCog(self).dream_object(draw_object))

        except Exception as e:
            print_exception('reroll failed', e, interaction, loop)


    #the button to delete generated images
    @discord.ui.button(
        custom_id="button_x",
        emoji="❌")
    async def delete(self, button: discord.Button, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return
            message = await get_message(interaction)

            if not message.content.startswith(f'<@{interaction.user.id}>'):
                loop.create_task(interaction.response.send_message("You can't delete other people's images!", ephemeral=True, delete_after=30))
                return

            if confirm_user_delete(interaction.user.id):
                loop.create_task(interaction.response.send_modal(DeleteModal(message)))
            else:
                loop.create_task(interaction.message.delete())
                update_user_delete(interaction.user.id)

        except Exception as e:
            print_exception('delete failed', e, interaction, loop)

    def find_between(self, s: str, first: str, last: str):
        try:
            start = s.index( first ) + len( first )
            end = s.index( last, start )
            return s[start:end]
        except ValueError:
            return ''


class DrawExtendedView(DrawView):
    def __init__(self, input_tuple: tuple | queuehandler.DrawObject):
        super().__init__(input_tuple)

    # the 🏳️ ends the game and reveals the answer
    @discord.ui.button(
        custom_id="button_giveup",
        emoji="🏳️")
    async def button_draw_giveup(self, button: discord.Button, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        loop.create_task(interaction.response.send_message('I may have been restarted. This button no longer works.', ephemeral=True, delete_after=30))
        return

    # guess prompt button
    @discord.ui.button(
        custom_id="button_guess-prompt",
        emoji="⌨️",
        row=2)
    async def guess_prompt(self, button: discord.Button, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        loop.create_task(interaction.response.send_message('I may have been restarted. This button no longer works.', ephemeral=True, delete_after=30))
        return

# creating the view that holds a button to delete output
class DeleteView(View):
    def __init__(self, user: discord.User):
        super().__init__(timeout=None)
        self.user = user

    @discord.ui.button(
        custom_id="button_x",
        emoji="❌")
    async def delete(self, button: discord.Button, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        try:
            if check_interaction_permission(interaction, loop) == False: return
            message = await get_message(interaction)

            if not message.content.startswith(f'<@{interaction.user.id}>'):
                loop.create_task(interaction.response.send_message("You can't delete other people's images!", ephemeral=True, delete_after=30))
                return

            if confirm_user_delete(interaction.user.id):
                loop.create_task(interaction.response.send_modal(DeleteModal(message)))
            else:
                loop.create_task(interaction.message.delete())
                update_user_delete(interaction.user.id)

        except Exception as e:
            print_exception('delete failed', e, interaction, loop)

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

def print_exception(message: str, e: Exception, interaction: discord.Interaction, loop: asyncio.AbstractEventLoop):
    print(f'Exception: {message}')
    print(f'{e}\n{traceback.print_exc()}')
    # button.disabled = True
    # await interaction.response.edit_message(view=self)
    loop.create_task(interaction.response.send_message(f'{message}\n{e}\n{traceback.print_exc()}', ephemeral=True, delete_after=30))