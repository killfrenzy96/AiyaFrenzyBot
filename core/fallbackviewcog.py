import discord
import asyncio
from discord.ext import commands

from core import viewhandler
from core import minigamecog
from core import tipscog

# workaround cog to allow aiya to respond to all views (after a restart) without the need of a view containing every control
class FallbackViewCog(commands.Cog, description='Create images from natural language.'):
    ctx_parse = discord.ApplicationContext
    def __init__(self, bot):
        self.bot: discord.Bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        viewhandler.discord_bot = self.bot
        self.bot.add_view(viewhandler.DrawView(None))
        self.bot.add_view(viewhandler.DrawExtendedView(None))
        self.bot.add_view(viewhandler.DeleteView())
        self.bot.add_view(minigamecog.MinigameView(None, None))
        self.bot.add_view(tipscog.TipsView())

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.is_command(): return # do not interact with commands

        # manage draw extended view buttons
        if interaction.custom_id.startswith('button_extra_'):
            message = await viewhandler.get_message(interaction)
            try:
                # reuse the existing view if possible
                view: viewhandler.DrawExtendedView = viewhandler.fallback_views[message.id]
                await view.button_extra_callback(interaction)
            except:
                # get input object
                stable_cog = self.bot.get_cog('StableCog')
                input_object = await viewhandler.get_input_object(stable_cog, interaction, ' ')
                if input_object == None: return

                # create a new view
                view = viewhandler.DrawExtendedView(input_object)
                viewhandler.fallback_views[message.id] = view
                await view.button_extra_callback(interaction)

def setup(bot: discord.Bot):
    bot.add_cog(FallbackViewCog(bot))