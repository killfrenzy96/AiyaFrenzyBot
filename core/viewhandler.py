import csv
import discord
import random
from discord.ui import InputText, Modal, View

from core import queuehandler
from core import settings
from core import stablecog

'''
The input_tuple index reference
input_tuple[0] = ctx
[1] = prompt
[2] = negative_prompt
[3] = data_model
[4] = steps
[5] = width
[6] = height
[7] = guidance_scale
[8] = sampler
[9] = seed
[10] = strength
[11] = init_image
[12] = count
[13] = style
[14] = facefix
[15] = simple_prompt
'''

#the modal that is used for the 🖋 button
class DrawModal(Modal):
    def __init__(self, input_tuple) -> None:
        super().__init__(title="Change Prompt!")
        self.input_tuple = input_tuple
        self.add_item(
            InputText(
                label='Input your new prompt',
                value=input_tuple[15],
                style=discord.InputTextStyle.long
            )
        )
        self.add_item(
            InputText(
                label='Input your new negative prompt (optional)',
                style=discord.InputTextStyle.long,
                value=input_tuple[2],
                required=False
            )
        )

    async def callback(self, interaction: discord.Interaction):
        new_prompt = list(self.input_tuple)
        new_prompt[1] = new_prompt[1].replace(new_prompt[15], self.children[0].value)
        new_prompt[15] = self.children[0].value
        new_prompt[2] = self.children[1].value
        prompt_tuple = tuple(new_prompt)

        draw_dream = stablecog.StableCog(self)
        prompt_output = f'\nNew prompt: ``{self.children[0].value}``'
        if new_prompt[2] != '':
            prompt_output = prompt_output + f'\nNew negative prompt: ``{self.children[1].value}``'
        #check queue again, but now we know user is not in queue
        if queuehandler.GlobalQueue.dream_thread.is_alive():
            queuehandler.GlobalQueue.draw_q.append(queuehandler.DrawObject(*prompt_tuple, DrawView(prompt_tuple)))
            await interaction.response.send_message(f'<@{interaction.user.id}>, redrawing the image!\nQueue: ``{len(queuehandler.union(queuehandler.GlobalQueue.draw_q, queuehandler.GlobalQueue.upscale_q, queuehandler.GlobalQueue.identify_q))}``{prompt_output}')
        else:
            await queuehandler.process_dream(draw_dream, queuehandler.DrawObject(*prompt_tuple, DrawView(prompt_tuple)))
            await interaction.response.send_message(f'<@{interaction.user.id}>, redrawing the image!\nQueue: ``{len(queuehandler.union(queuehandler.GlobalQueue.draw_q, queuehandler.GlobalQueue.upscale_q, queuehandler.GlobalQueue.identify_q))}``{prompt_output}')

#creating the view that holds the buttons for /draw output
class DrawView(View):
    def __init__(self, input_tuple):
        super().__init__(timeout=None)
        self.input_tuple = input_tuple

    #the 🖋 button will allow a new prompt and keep same parameters for everything else
    # @discord.ui.button(
    #     custom_id="button_re-prompt",
    #     emoji="🖋")
    async def button_draw(self, button, interaction):
        try:
            #check if the /draw output is from the person who requested it
            if self.message.embeds[0].footer.text == f'{interaction.user.name}#{interaction.user.discriminator}':
                #if there's room in the queue, open up the modal
                if queuehandler.GlobalQueue.dream_thread.is_alive():
                    user_already_in_queue = False
                    for queue_object in queuehandler.union(queuehandler.GlobalQueue.draw_q,
                                                           queuehandler.GlobalQueue.upscale_q,
                                                           queuehandler.GlobalQueue.identify_q):
                        if queue_object.ctx.author.id == interaction.user.id:
                            user_already_in_queue = True
                            break
                    if user_already_in_queue:
                        await interaction.response.send_message(content=f"Please wait! You're queued up.", ephemeral=True)
                    else:
                        await interaction.response.send_modal(DrawModal(self.input_tuple))
                else:
                    await interaction.response.send_modal(DrawModal(self.input_tuple))
            else:
                await interaction.response.send_message("You can't use other people's 🖋!", ephemeral=True)
        except(Exception,):
            #if interaction fails, assume it's because aiya restarted (breaks buttons)
            button.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("I may have been restarted. This button no longer works.", ephemeral=True)

    #the 🎲 button will take the same parameters for the image, change the seed, and add a task to the queue
    # @discord.ui.button(
    #     custom_id="button_re-roll",
    #     emoji="🎲")
    async def button_roll(self, button, interaction):
        try:
            #check if the /draw output is from the person who requested it
            # if self.message.embeds[0].footer.text == f'{interaction.user.name}#{interaction.user.discriminator}':
            if self.message.content.startswith(f'<@{interaction.user.id}>'):
                #update the tuple with a new seed
                new_seed = list(self.input_tuple)
                new_seed[9] = random.randint(0, 0xFFFFFFFF)
                seed_tuple = tuple(new_seed)

                #set up the draw dream and do queue code again for lack of a more elegant solution
                draw_dream = stablecog.StableCog(self)

                draw_object = queuehandler.DrawObject(*seed_tuple, DrawView(seed_tuple))
                draw_dream.dream_handler(ctx=interaction,
                    prompt=draw_object.prompt,
                    negative=draw_object.negative_prompt,
                    checkpoint=draw_object.data_model,
                    width=draw_object.width,
                    height=draw_object.height,
                    guidance_scale=draw_object.guidance_scale,
                    steps=draw_object.steps,
                    sampler=draw_object.sampler,
                    seed=draw_object.seed,
                    init_url=draw_object.init_image.url if draw_object.init_image else '',
                    strength=draw_object.strength,
                    batch=draw_object.batch_count,
                    style=draw_object.style,
                    facefix=draw_object.facefix,
                    tiling=draw_object.tiling,
                    script=draw_object.script
                )
            else:
                await interaction.response.send_message("You can't use other people's 🎲!", ephemeral=True)
        except(Exception,):
            #if interaction fails, assume it's because aiya restarted (breaks buttons)
            button.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("I may have been restarted. This button no longer works.", ephemeral=True)

    # the 📋 button will let you review the parameters of the generation
    # @discord.ui.button(
    #     custom_id="button_review",
    #     emoji="📋")
    async def button_review(self, button, interaction):
        #simpler variable name
        rev = self.input_tuple
        try:
            #the tuple will show the model_full_name. Get the associated display_name and activator_token from it.
            with open('resources/models.csv', 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter='|')
                for row in reader:
                    if row['model_full_name'] == rev[3]:
                        model_name = row['display_name']
                        activator_token = row['activator_token']

            #generate the command for copy-pasting, and also add embed fields
            embed = discord.Embed(title="About the image!", description="")
            embed.colour = settings.global_var.embed_color
            embed.add_field(name=f'Prompt', value=f'``{rev[15]}``', inline=False)
            copy_command = f'/draw prompt:{rev[15]} data_model:{model_name} steps:{rev[4]} width:{rev[5]} height:{rev[6]} guidance_scale:{rev[7]} sampler:{rev[8]} seed:{rev[9]} count:{rev[12]} '
            if rev[2] != '':
                copy_command = copy_command + f' negative_prompt:{rev[2]}'
                embed.add_field(name=f'Negative prompt', value=f'``{rev[2]}``', inline=False)
            if activator_token:
                embed.add_field(name=f'Data model', value=f'Display name - ``{model_name}``\nFull name - ``{rev[3]}``\nActivator token - ``{activator_token}``', inline=False)
            else:
                embed.add_field(name=f'Data model', value=f'Display name - ``{model_name}``\nFull name - ``{rev[3]}``', inline=False)
            extra_params = f'Sampling steps: ``{rev[4]}``\nSize: ``{rev[5]}x{rev[6]}``\nClassifier-free guidance scale: ``{rev[7]}``\nSampling method: ``{rev[8]}``\nSeed: ``{rev[9]}``'
            if rev[11]:
                #not interested in adding embed fields for strength and init_image
                copy_command = copy_command + f' strength:{rev[10]} init_url:{rev[11]}'
            if rev[13] != 'None':
                copy_command = copy_command + f' style:{rev[13]}'
                extra_params = extra_params + f'\nStyle preset: ``{rev[13]}``'
            if rev[14] != 'None':
                copy_command = copy_command + f' facefix:{rev[14]}'
                extra_params = extra_params + f'\nFace restoration model: ``{rev[14]}``'
            embed.add_field(name=f'Other parameters', value=extra_params, inline=False)
            embed.add_field(name=f'Command for copying', value=f'``{copy_command}``', inline=False)

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except(Exception,):
            # if interaction fails, assume it's because aiya restarted (breaks buttons)
            button.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("I may have been restarted. This button no longer works.", ephemeral=True)

    #the button to delete generated images
    # @discord.ui.button(
    #     custom_id="button_x",
    #     emoji="❌")
    async def delete(self, button, interaction):
        try:
            # if self.message.embeds[0].footer.text == f'{interaction.user.name}#{interaction.user.discriminator}':
            if self.message.content.startswith(f'<@{interaction.user.id}>'):
                await interaction.message.delete()
            else:
                await interaction.response.send_message("You can't delete other people's images!", ephemeral=True)
        except(Exception,):
                button.disabled = True
                await interaction.response.edit_message(view=self)
                await interaction.followup.send("I may have been restarted. This button no longer works.", ephemeral=True)

#creating the view that holds a button to delete output
class DeleteView(View):
    def __init__(self, user):
        super().__init__(timeout=None)
        self.user = user

    # @discord.ui.button(
    #     custom_id="button_x",
    #     emoji="❌")
    async def delete(self, button, interaction):
        if interaction.user.id == self.user:
            button.disabled = True
            await interaction.message.delete()
        else:
            await interaction.response.send_message("You can't delete other people's images!", ephemeral=True)
