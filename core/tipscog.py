import discord
import asyncio
from discord.ext import commands
from discord.ui import View

from core import settings


class TipsView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        custom_id='button_tips',
        label='Quick tips')
    async def button_tips(self, button: discord.Button, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()

        embed_tips = discord.Embed(title='Quick Tips', description='')
        embed_tips.colour = settings.global_var.embed_color
        embed_tips.add_field(name='Steps',
                             value='This is how many cycles the AI takes to create an image. '
                                   'More steps generally leads to better results, but not always!',
                             inline=False)
        embed_tips.add_field(name='Guidance Scale',
                             value='This represents how much importance is given to your prompt. The AI will give more '
                                   'attention to your prompt with higher values and be more creative with lower values.',
                             inline=False)
        embed_tips.add_field(name='Seed',
                             value='This value is the key used to generate an image. '
                                   'A seed can be used to recreate the same image or variations on it.',
                             inline=False)
        embed_tips.add_field(name='Prompting',
                             value='Word order influences the image. Putting `cat, dog` will lean more towards cat.\nKeep '
                                   'in mind when doing very long prompts, the AI will be more likely to ignore words near '
                                   'the end of the prompt. Can\'t think of a prompt? Try putting ? as the prompt.',
                             inline=False)
        embed_tips.add_field(name='Emphasizing',
                             value='`(word)`-each `()` increases attention to `word` by 1.1x\n`[word]`-each `[]` decreases '
                                   'attention to `word` by 1.1x\n`(word:1.5)`-increases attention to `word` by 1.5x\n`('
                                   'word:0.25)`-decreases attention to `word` by 4x\n`\(word\)`-use literal () characters '
                                   'in prompt.',
                             inline=False)
        embed_tips.add_field(name='Transitioning',
                             value='`[word1:word2:steps]`\nWhen generating an image, the AI will start at `word1`, '
                                   'then after the specified number of `steps`, switches to `word2`. Word order matters.',
                             inline=False)
        embed_tips.add_field(name='Alternating',
                             value='`[word1|word2]`\nWhen generating an image, the AI will alternate between the words for '
                                   'each step. Word order still applies.',
                             inline=False)
        embed_tips.add_field(name='Buttons',
                             value='🖋 edit prompt, then generate a new image with same parameters.\n'
                                   '🖼️ create variation by sending the image to img2img.\n'
                                   '🔁 randomize seed, then generate a new image with same parameters.\n'
                                   '🔧 shows extra options to allow quick changes to specific parameters.\n'
                                   '❌ deletes the generated image.',
                             inline=False)

        loop.create_task(interaction.response.edit_message(embed=embed_tips))

    @discord.ui.button(
        custom_id='button_styles',
        label='Styles list')
    async def button_style(self, button: discord.Button, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()

        style_list = ''
        for key, value in settings.global_var.style_names.items():
            values: list[str] = value.split('\n')
            style_prompt = values[0]
            style_negative = values[1]
            if style_prompt == '': style_prompt = ' '
            if style_negative == '': style_negative = ' '
            style_list = style_list + f'\n{key} - prompt:``{style_prompt}`` negative:``{style_negative}``'
        embed_styles = discord.Embed(title='Styles list', description=style_list)
        embed_styles.colour = settings.global_var.embed_color

        loop.create_task(interaction.response.edit_message(embed=embed_styles))

    @discord.ui.button(
        custom_id='button_model',
        label='Models list')
    async def button_model(self, button: discord.Button, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()

        model_list = ''
        for key, value in settings.global_var.model_names.items():
            if value == '':
                value = ' '
            model_list = model_list + f'\n{key} - ``{value}``'
        embed_model = discord.Embed(title='Models list', description=model_list)
        embed_model.colour = settings.global_var.embed_color

        loop.create_task(interaction.response.edit_message(embed=embed_model))

    @discord.ui.button(
        custom_id='button_about',
        label='About me')
    async def button_about(self, button: discord.Button, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()

        url_frenzy = 'https://github.com/killfrenzy96/aiyabot'
        url_aiya = 'https://github.com/Kilvoctu/aiyabot'
        url2 = 'https://raw.githubusercontent.com/Kilvoctu/kilvoctu.github.io/master/pics/previewthumb.png'
        embed_about = discord.Embed(title='About me',
                                    description=f'Hi! I\'m an open-source Discord bot written in Python.\n'
                                                f'This is a fork of aiyabot.\n'
                                                f'[My home is here]({url_frenzy}) if you want to see :3\n'
                                                f'[The original aiyabot is here]({url_aiya}) if you\'d like to check it out!')
        embed_about.colour = settings.global_var.embed_color
        embed_about.set_thumbnail(url=url2)
        embed_about.set_footer(text='Have a lovely day!', icon_url=url2)

        loop.create_task(interaction.response.edit_message(embed=embed_about))

class TipsCog(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot

    @commands.slash_command(name='tips', description='Some quick tips for generating images!')
    async def tips(self, ctx: discord.ApplicationContext):
        loop = asyncio.get_running_loop()

        first_embed = discord.Embed(title='Select a button!')
        first_embed.colour = settings.global_var.embed_color

        loop.create_task(ctx.respond(embed=first_embed, view=TipsView(), ephemeral=True))


def setup(bot: discord.Bot):
    bot.add_cog(TipsCog(bot))

