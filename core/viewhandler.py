import csv
import discord
import random
import copy
import traceback
from discord.ui import InputText, Modal, View

from core import queuehandler
from core import settings
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
        if self.input_object.init_image:
            self.add_item(
                InputText(
                    label='Seed. Remove to randomize. \'T\' for txt2img.',
                    style=discord.InputTextStyle.short,
                    value=self.input_object.seed,
                    required=False
                )
            )
        else:
            self.add_item(
                InputText(
                    label='Seed. Remove to randomize. \'I\' for img2img.',
                    style=discord.InputTextStyle.short,
                    value=self.input_object.seed,
                    required=False
                )
            )
        self.add_item(
            InputText(
                label='Batch count',
                style=discord.InputTextStyle.short,
                value=self.input_object.batch_count,
                required=False
            )
        )
        if self.input_object.init_image:
            self.add_item(
                InputText(
                    label='Steps | Guidance Scale | Strength',
                    style=discord.InputTextStyle.short,
                    value=f'{self.input_object.steps}|{self.input_object.guidance_scale}|{self.input_object.strength}',
                    required=False
                )
            )
        else:
            self.add_item(
                InputText(
                    label='Steps | Guidance Scale',
                    style=discord.InputTextStyle.short,
                    value=f'{self.input_object.steps}|{self.input_object.guidance_scale}',
                    required=False
                )
            )

    async def callback(self, interaction: discord.Interaction):
        draw_object = copy.copy(self.input_object)

        draw_object.simple_prompt = self.children[0].value
        draw_object.prompt = self.input_object.prompt.replace(self.input_object.simple_prompt, self.children[0].value)

        draw_object.negative_prompt = self.children[1].value

        try:
            seed = self.children[2].value.lower()
            if seed.startswith('i'):
                class simple_init_image:
                    url: str
                draw_object.init_image = simple_init_image()
                draw_object.init_image.url = self.message.attachments[0].url
                draw_object.seed = int(seed.replace('v', ''))
            elif seed.startswith('t'):
                draw_object.init_image = None
                draw_object.seed = int(seed.replace('t', ''))
            else:
                draw_object.seed = int(seed)
        except:
            draw_object.seed = -1

        try:
            draw_object.batch_count = int(self.children[3].value)
            draw_object.batch_count = max(1, draw_object.batch_count)
        except:
            pass

        try:
            split_str = self.children[4].value.split('|')
            draw_object.steps = max(1, int(split_str[0]))
            draw_object.guidance_scale = max(1.0, float(split_str[1]))
            if draw_object.init_image: draw_object.strength = max(0.0, min(1.0, float(split_str[2])))
        except:
            pass

        draw_object.ctx = interaction
        draw_object.payload = None
        draw_object.view = None

        await stablecog.StableCog(self).dream_object(draw_object)

#creating the view that holds the buttons for /draw output
class DrawView(View):
    def __init__(self, input_tuple: tuple):
        super().__init__(timeout=None)
        if type(input_tuple) is stablecog.StableCog:
            self.input_object = None
        else:
            self.input_object = queuehandler.DrawObject(*input_tuple)

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

            if self.input_object:
                await interaction.response.send_modal(DrawModal(self.input_object, message))
            else:
                if '``/dream ' in message.content:
                    command = self.find_between(message.content, '``/dream ', '``')
                    input_object = stablecog.StableCog(self).get_draw_object_from_command(command)
                    await interaction.response.send_modal(DrawModal(input_object, message))

                else:
                    # button.disabled = True
                    await interaction.response.edit_message(view=self)
                    await interaction.followup.send('I may have been restarted. This button no longer works.\nPlease try using 🖋 on a message containing the full /dream command.', ephemeral=True, delete_after=30)
        except Exception as e:
            print('re-prompt failed')
            print(f'{e}\n{traceback.print_exc()}')
            # button.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f're-prompt failed\n{e}\n{traceback.print_exc()}', ephemeral=True, delete_after=30)

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

            if self.input_object:
                await interaction.response.send_modal(DrawModal(self.input_object, message))
            else:
                if '``/dream ' in message.content:
                    command = self.find_between(message.content, '``/dream ', '``')
                    input_object = stablecog.StableCog(self).get_draw_object_from_command(command)
                    await interaction.response.send_modal(DrawModal(input_object, message))

                else:
                    # button.disabled = True
                    await interaction.response.edit_message(view=self)
                    await interaction.followup.send('I may have been restarted. This button no longer works.\nPlease try using 🖋 on a message containing the full /dream command.', ephemeral=True, delete_after=30)
        except Exception as e:
            print('re-prompt failed')
            print(f'{e}\n{traceback.print_exc()}')
            # button.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f're-prompt failed\n{e}\n{traceback.print_exc()}', ephemeral=True, delete_after=30)

    # the 🔁 button will take the same parameters for the image, change the seed, and add a task to the queue
    @discord.ui.button(
        custom_id="button_re-roll",
        emoji="🔁")
    async def button_roll(self, button: discord.Button, interaction: discord.Interaction):
        try:
            #update the tuple with a new seed
            if self.input_object:
                draw_object = copy.copy(self.input_object)
                draw_object.seed = -1
                draw_object.ctx = interaction
                draw_object.payload = None
                draw_object.view = None

                #set up the draw dream and do queue code again for lack of a more elegant solution
                await stablecog.StableCog(self).dream_object(draw_object)

            else:
                if interaction.message == None:
                    message = await interaction.original_response()
                else:
                    message = interaction.message

                if '``/dream ' in message.content:
                    command = self.find_between(message.content, '``/dream ', '``')
                    await stablecog.StableCog(self).dream_command(interaction, command)

                else:
                    # button.disabled = True
                    await interaction.response.edit_message(view=self)
                    await interaction.followup.send('I may have been restarted. This button no longer works.\nPlease try using 🔁 on a message containing the full /dream command.', ephemeral=True, delete_after=30)

        except Exception as e:
            print('reroll failed')
            print(f'{e}\n{traceback.print_exc()}')
            # button.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f're-roll failed\n{e}\n{traceback.print_exc()}', ephemeral=True, delete_after=30)

    # the 📋 button will let you review the parameters of the generation
    # @discord.ui.button(
    #     custom_id="button_review",
    #     emoji="📋")
    # async def button_review(self, button: discord.Button, interaction: discord.Interaction):
    #     #simpler variable name
    #     rev = self.input_tuple
    #     try:
    #         #the tuple will show the model_full_name. Get the associated display_name and activator_token from it.
    #         with open('resources/models.csv', 'r', encoding='utf-8') as f:
    #             reader = csv.DictReader(f, delimiter='|')
    #             for row in reader:
    #                 if row['model_full_name'] == rev[3]:
    #                     model_name = row['display_name']
    #                     activator_token = row['activator_token']

    #         #generate the command for copy-pasting, and also add embed fields
    #         embed = discord.Embed(title="About the image!", description="")
    #         embed.colour = settings.global_var.embed_color
    #         embed.add_field(name=f'Prompt', value=f'``{rev[16]}``', inline=False)
    #         copy_command = f'/draw prompt:{rev[16]} data_model:{model_name} steps:{rev[4]} width:{rev[5]} height:{rev[6]} guidance_scale:{rev[7]} sampler:{rev[8]} seed:{rev[9]} count:{rev[12]} '
    #         if rev[2] != '':
    #             copy_command = copy_command + f' negative_prompt:{rev[2]}'
    #             embed.add_field(name=f'Negative prompt', value=f'``{rev[2]}``', inline=False)
    #         if activator_token:
    #             embed.add_field(name=f'Data model', value=f'Display name - ``{model_name}``\nFull name - ``{rev[3]}``\nActivator token - ``{activator_token}``', inline=False)
    #         else:
    #             embed.add_field(name=f'Data model', value=f'Display name - ``{model_name}``\nFull name - ``{rev[3]}``', inline=False)
    #         extra_params = f'Sampling steps: ``{rev[4]}``\nSize: ``{rev[5]}x{rev[6]}``\nClassifier-free guidance scale: ``{rev[7]}``\nSampling method: ``{rev[8]}``\nSeed: ``{rev[9]}``'
    #         if rev[11]:
    #             #not interested in adding embed fields for strength and init_image
    #             copy_command = copy_command + f' strength:{rev[10]} init_url:{rev[11]}'
    #         if rev[12] != 1:
    #             copy_command = copy_command + f' count:{rev[13]}'
    #         if rev[13] != 'None':
    #             copy_command = copy_command + f' style:{rev[13]}'
    #             extra_params = extra_params + f'\nStyle preset: ``{rev[13]}``'
    #         if rev[14] != 'None':
    #             copy_command = copy_command + f' facefix:{rev[14]}'
    #             extra_params = extra_params + f'\nFace restoration model: ``{rev[14]}``'
    #         if rev[15]:
    #             copy_command = copy_command + f' enable_hr:{rev[15]}'
    #             extra_params = extra_params + f'\nHigh-res fix: ``{rev[15]}``'
    #         if rev[16] != 1:
    #             copy_command = copy_command + f' clip_skip:{rev[16]}'
    #             extra_params = extra_params + f'\nCLIP skip: ``{rev[16]}``'
    #         embed.add_field(name=f'Other parameters', value=extra_params, inline=False)
    #         embed.add_field(name=f'Command for copying', value=f'``{copy_command}``', inline=False)

    #         await interaction.response.send_message(embed=embed, ephemeral=True)
    #     except(Exception,):
    #         # if interaction fails, assume it's because aiya restarted (breaks buttons)
    #         button.disabled = True
    #         await interaction.response.edit_message(view=self)
    #         await interaction.followup.send("I may have been restarted. This button no longer works.", ephemeral=True)

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

            if message.content.startswith(f'<@{interaction.user.id}>'):
                await interaction.message.delete()
            else:
                await interaction.response.send_message("You can't delete other people's images!", ephemeral=True, delete_after=30)
        except Exception as e:
            print('remove failed')
            print(f'{e}\n{traceback.print_exc()}')
            # button.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f'remove failed\n{e}\n{traceback.print_exc()}', ephemeral=True, delete_after=30)

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

            if message.content.startswith(f'<@{interaction.user.id}>'):
                await interaction.message.delete()
            else:
                await interaction.response.send_message("You can't delete other people's images!", ephemeral=True, delete_after=30)
        except Exception as e:
            print('remove failed')
            print(f'{e}\n{traceback.print_exc()}')
            # button.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f'remove failed\n{e}\n{traceback.print_exc()}', ephemeral=True, delete_after=30)
