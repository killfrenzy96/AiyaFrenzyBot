import csv
import discord
import random
import copy
import traceback
import time
from discord.ui import InputText, Modal, View

from core import queuehandler
from core import settings
from core import stablecog

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

        if self.input_object.init_image:
            self.add_item(
                InputText(
                    label='Init URL. \'C\' uses current image.',
                    style=discord.InputTextStyle.short,
                    value=self.input_object.init_image.url,
                    required=False
                )
            )
            self.add_item(
                InputText(
                    label='Batch | Steps | Guidance Scale | Strength',
                    style=discord.InputTextStyle.short,
                    value=f'{self.input_object.batch_count}|{self.input_object.steps}|{self.input_object.guidance_scale}|{self.input_object.strength}',
                    required=False
                )
            )
        else:
            self.add_item(
                InputText(
                    label='Init URL. \'C\' uses current image.',
                    style=discord.InputTextStyle.short,
                    value='',
                    required=False
                )
            )
            self.add_item(
                InputText(
                    label='Batch | Steps | Guidance Scale',
                    style=discord.InputTextStyle.short,
                    value=f'{self.input_object.batch_count}|{self.input_object.steps}|{self.input_object.guidance_scale}',
                    required=False
                )
            )

    async def callback(self, interaction: discord.Interaction):
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
                url = self.message.attachments[0].url
            else:
                url = self.children[3].value

            if url:
                class simple_init_image: url: str
                draw_object.init_image = simple_init_image()
                draw_object.init_image.url = url
            else:
                draw_object.init_image = None
        except:
            pass

        try:
            split_str = self.children[4].value.split('|')
            draw_object.batch_count = max(1, int(split_str[0]))
            draw_object.steps = max(1, int(split_str[1]))
            draw_object.guidance_scale = max(1.0, float(split_str[2]))
            if draw_object.init_image: draw_object.strength = max(0.0, min(1.0, float(split_str[3])))
        except:
            pass

        draw_object.ctx = interaction
        draw_object.view = None
        draw_object.payload = None

        await stablecog.StableCog(self).dream_object(draw_object)

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
        try:
            if not self.message.content.startswith(f'<@{interaction.user.id}>'):
                await interaction.response.send_message("You can't delete other people's images!", ephemeral=True, delete_after=30)
                return

            await interaction.message.delete()
            await interaction.response.defer()
            update_user_delete(interaction.user.id)

        except Exception as e:
            print('delete failed')
            print(f'{e}\n{traceback.print_exc()}')
            # button.disabled = True
            # await interaction.response.edit_message(view=self)
            await interaction.response.defer()
            await interaction.followup.send(f'delete failed\n{e}\n{traceback.print_exc()}', ephemeral=True, delete_after=30)

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
    show_extra = False


    # the 🖋 button will allow a new prompt and keep same parameters for everything else
    @discord.ui.button(
        custom_id="button_re-prompt",
        emoji="🖋")
    async def button_draw(self, button: discord.Button, interaction: discord.Interaction):
        try:
            if interaction.message == None:
                message = await interaction.original_response()
            else:
                message = interaction.message

            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                # create input object from message command
                if '``/dream ' in message.content:
                    command = self.find_between(message.content, '``/dream ', '``')
                    input_object = stablecog.StableCog(self).get_draw_object_from_command(command)
                else:
                    await interaction.response.defer()
                    await interaction.followup.send('I may have been restarted. This button no longer works.\nPlease try using 🖋 on a message containing the full /dream command.', ephemeral=True, delete_after=30)
                    return

            await interaction.response.send_modal(DrawModal(input_object, message))

        except Exception as e:
            print('re-prompt failed')
            print(f'{e}\n{traceback.print_exc()}')
            # button.disabled = True
            # await interaction.response.edit_message(view=self)
            await interaction.response.defer()
            await interaction.followup.send(f're-prompt failed\n{e}\n{traceback.print_exc()}', ephemeral=True, delete_after=30)


    # the 🖼️ button will take the same parameters for the image, send the original image to init_image, change the seed, and add a task to the queue
    @discord.ui.button(
        custom_id="button_image-variation",
        emoji="🖼️")
    async def button_draw_variation(self, button: discord.Button, interaction: discord.Interaction):
        try:
            if interaction.message == None:
                message = await interaction.original_response()
            else:
                message = interaction.message

            # obtain URL for the original image
            url = message.attachments[0].url
            if not url:
                await interaction.response.defer()
                await interaction.followup.send('The image seems to be missing. This button no longer works.', ephemeral=True, delete_after=30)
                return

            class simple_init_image: url: str
            init_image = simple_init_image()
            init_image.url = url

            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                # create input object from message command
                if '``/dream ' in message.content:
                    command = self.find_between(message.content, '``/dream ', '``')
                    input_object = stablecog.StableCog(self).get_draw_object_from_command(command)
                else:
                    await interaction.response.defer()
                    await interaction.followup.send('I may have been restarted. This button no longer works.\nPlease try using 🖼️ on a message containing the full /dream command.', ephemeral=True, delete_after=30)
                    return

            # setup draw object to send to the stablecog
            draw_object = copy.copy(input_object)
            draw_object.seed = -1
            draw_object.ctx = interaction
            draw_object.view = None
            draw_object.payload = None
            draw_object.init_image = init_image

            # run stablecog dream using draw object
            await stablecog.StableCog(self).dream_object(draw_object)

        except Exception as e:
            print('Send to img2img failed')
            print(f'{e}\n{traceback.print_exc()}')
            # button.disabled = True
            # await interaction.response.edit_message(view=self)
            await interaction.response.defer()
            await interaction.followup.send(f're-roll failed\n{e}\n{traceback.print_exc()}', ephemeral=True, delete_after=30)


    # the 🔁 button will take the same parameters for the image, change the seed, and add a task to the queue
    @discord.ui.button(
        custom_id="button_re-roll",
        emoji="🔁")
    async def button_reroll(self, button: discord.Button, interaction: discord.Interaction):
        try:
            # get input object
            if self.input_object:
                input_object = self.input_object
            else:
                # create input object from message command
                if interaction.message == None:
                    message = await interaction.original_response()
                else:
                    message = interaction.message

                if '``/dream ' in message.content:
                    command = self.find_between(message.content, '``/dream ', '``')
                    input_object = stablecog.StableCog(self).get_draw_object_from_command(command)
                else:
                    await interaction.response.defer()
                    await interaction.followup.send('I may have been restarted. This button no longer works.\nPlease try using 🔁 on a message containing the full /dream command.', ephemeral=True, delete_after=30)
                    return

            # setup draw object to send to the stablecog
            draw_object = copy.copy(input_object)
            draw_object.seed = -1
            draw_object.ctx = interaction
            draw_object.view = None
            draw_object.payload = None

            # run stablecog dream using draw object
            await stablecog.StableCog(self).dream_object(draw_object)

        except Exception as e:
            print('reroll failed')
            print(f'{e}\n{traceback.print_exc()}')
            # button.disabled = True
            # await interaction.response.edit_message(view=self)
            await interaction.response.defer()
            await interaction.followup.send(f're-roll failed\n{e}\n{traceback.print_exc()}', ephemeral=True, delete_after=30)


    #the button to delete generated images
    @discord.ui.button(
        custom_id="button_x",
        emoji="❌")
    async def delete(self, button: discord.Button, interaction: discord.Interaction):
        try:
            if interaction.message == None:
                message = await interaction.original_response()
            else:
                message = interaction.message

            if not message.content.startswith(f'<@{interaction.user.id}>'):
                await interaction.response.send_message("You can't delete other people's images!", ephemeral=True, delete_after=30)
                return

            if confirm_user_delete(interaction.user.id):
                await interaction.response.send_modal(DeleteModal(message))
            else:
                await interaction.message.delete()
                update_user_delete(interaction.user.id)

        except Exception as e:
            print('delete failed')
            print(f'{e}\n{traceback.print_exc()}')
            # button.disabled = True
            # await interaction.response.edit_message(view=self)
            await interaction.response.defer()
            await interaction.followup.send(f'delete failed\n{e}\n{traceback.print_exc()}', ephemeral=True, delete_after=30)


    def find_between(self, s: str, first: str, last: str):
        try:
            start = s.index( first ) + len( first )
            end = s.index( last, start )
            return s[start:end]
        except ValueError:
            return ''


# creating the view that holds a button to delete output
class DeleteView(View):
    def __init__(self, user: discord.User):
        super().__init__(timeout=None)
        self.user = user

    @discord.ui.button(
        custom_id="button_x",
        emoji="❌")
    async def delete(self, button: discord.Button, interaction: discord.Interaction):
        try:
            if interaction.message == None:
                message = await interaction.original_response()
            else:
                message = interaction.message

            if not message.content.startswith(f'<@{interaction.user.id}>'):
                await interaction.response.send_message("You can't delete other people's images!", ephemeral=True, delete_after=30)
                return

            if confirm_user_delete(interaction.user.id):
                await interaction.response.send_modal(DeleteModal(message))
            else:
                await interaction.message.delete()
                update_user_delete(interaction.user.id)

        except Exception as e:
            print('delete failed')
            print(f'{e}\n{traceback.print_exc()}')
            # button.disabled = True
            # await interaction.response.edit_message(view=self)
            await interaction.response.defer()
            await interaction.followup.send(f'delete failed\n{e}\n{traceback.print_exc()}', ephemeral=True, delete_after=30)
