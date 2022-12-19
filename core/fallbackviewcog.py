import discord
import asyncio
from discord.ext import commands

from core import viewhandler

# workaround cog to allow aiya to respond to all views (after a restart) without the need of a view containing every control
class FallbackViewCog(commands.Cog, description='Create images from natural language.'):
    ctx_parse = discord.ApplicationContext
    def __init__(self, bot):
        self.bot: discord.Bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        viewhandler.discord_bot = self.bot
        self.bot.add_view(viewhandler.DrawView(None))
        self.stable_cog = self.bot.get_cog('StableCog')

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.is_command(): return # do not interact with commands
        await asyncio.sleep(0.01) # make sure this function is executed after the view command
        if interaction.response.is_done() or interaction.custom_id == None: return # existing view, end this interaction
        input_object = await viewhandler.get_input_object(self.stable_cog, interaction)

        # match up custom id
        match interaction.custom_id:
            # delete button
            case 'button_x': await viewhandler.user_delete(interaction)

            # extra buttons navigation
            case 'button_extra_page_1': await viewhandler.DrawExtendedView(input_object).button_page_callback(interaction, 1)
            case 'button_extra_page_2': await viewhandler.DrawExtendedView(input_object).button_page_callback(interaction, 2)
            case 'button_extra_page_3': await viewhandler.DrawExtendedView(input_object).button_page_callback(interaction, 3)

            # extra buttons items
            case 'button_select_checkpoint': await viewhandler.DrawExtendedView(input_object, 1).select_checkpoint_callback(interaction)
            case 'button_select_resolution': await viewhandler.DrawExtendedView(input_object, 1).select_resolution_callback(interaction)
            case 'button_select_sampler': await viewhandler.DrawExtendedView(input_object, 1).select_sampler_callback(interaction)
            case 'button_select_steps': await viewhandler.DrawExtendedView(input_object, 2).select_steps_callback(interaction)
            case 'button_select_guidance_scale': await viewhandler.DrawExtendedView(input_object, 2).select_guidance_scale_callback(interaction)
            case 'button_select_style': await viewhandler.DrawExtendedView(input_object, 2).select_style_callback(interaction)
            case 'button_select_batch': await viewhandler.DrawExtendedView(input_object, 3).select_batch_callback(interaction)
            case 'button_select_strength': await viewhandler.DrawExtendedView(input_object, 3).select_strength_callback(interaction)
            case 'button_extra_remove_init_image': await viewhandler.DrawExtendedView(input_object, 3).button_remove_init_image_callback(interaction)
            case 'button_extra_highres_fix': await viewhandler.DrawExtendedView(input_object, 3).button_highres_fix_callback(interaction)
            case 'button_extra_tiling': await viewhandler.DrawExtendedView(input_object, 3).button_tiling_callback(interaction)
            case 'button_extra_facefix_codeformer': await viewhandler.DrawExtendedView(input_object, 3).button_facefix_codeformer_callback(interaction)
            case 'button_extra_facefix_gfpgan': await viewhandler.DrawExtendedView(input_object, 3).button_facefix_gfpgan_callback(interaction)

            # minigame buttons
            case 'button_giveup': await self.respond_minigame(interaction)
            case 'button_guess-prompt': await self.respond_minigame(interaction)

    async def respond_minigame(self, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        loop.create_task(interaction.response.send_message('I may have been restarted. This interaction no longer works.\nPlease start a new minigame using the /minigame command.', ephemeral=True, delete_after=30))

    async def respond_generic(self, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        loop.create_task(interaction.response.send_message('I may have been restarted. This interaction no longer works.', ephemeral=True, delete_after=30))

def setup(bot: discord.Bot):
    bot.add_cog(FallbackViewCog(bot))