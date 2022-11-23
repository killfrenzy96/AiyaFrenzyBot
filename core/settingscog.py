import discord
from discord import option
from discord.ext import commands
from typing import Optional

from core import settings


class SettingsCog(commands.Cog):
    def __init__(self, bot:commands.Bot):
        self.bot = bot

    # pulls from model_names list and makes some sort of dynamic list to bypass Discord 25 choices limit
    def model_autocomplete(self: discord.AutocompleteContext):
        return [
            model for model in settings.global_var.model_names
        ]

    @commands.slash_command(name = 'settings', description = 'Review and change server defaults')
    @option(
        'current_settings',
        bool,
        description='Show the current defaults for the server.',
        required=False,
    )
    @option(
        'set_n_prompt',
        str,
        description='Set default negative prompt for the server',
        required=False,
    )
    @option(
        'set_model',
        str,
        description='Set default data model for image generation',
        required=False,
        autocomplete=discord.utils.basic_autocomplete(model_autocomplete),
    )
    @option(
        'set_steps',
        int,
        description='Set default amount of steps for the server',
        min_value=1,
        required=False,
    )
    @option(
        'set_max_steps',
        int,
        description='Set default maximum steps for the server',
        min_value=1,
        required=False,
    )
    @option(
        'set_count',
        int,
        description='Set default count for the server',
        min_value=1,
        required=False,
    )
    @option(
        'set_max_count',
        int,
        description='Set default maximum count for the server',
        min_value=1,
        required=False,
    )
    @option(
        'set_sampler',
        str,
        description='Set default sampler for the server',
        required=False,
        choices=settings.global_var.sampler_names,
    )
    async def settings_handler(self, ctx,
                               current_settings: Optional[bool] = False,
                               set_n_prompt: Optional[str] = 'unset',
                               set_model: Optional[str] = None,
                               set_steps: Optional[int] = 1,
                               set_max_steps: Optional[int] = 1,
                               set_count: Optional[int] = None,
                               set_max_count: Optional[int] = None,
                               set_sampler: Optional[str] = 'unset',
                               set_clip_skip: Optional[int] = 0):
        guild = '% s' % ctx.guild_id
        reviewer = settings.read(guild)
        reply = 'Summary:\n'
        if current_settings:
            cur_set = settings.read(guild)
            for key, value in cur_set.items():
                reply = reply + str(key) + ": " + str(value) + ", "

        #run through each command and update the defaults user selects
        if set_n_prompt != 'unset':
            settings.update(guild, 'negative_prompt', set_n_prompt)
            reply = reply + '\nNew default negative prompts is "' + str(set_n_prompt) + '".'

        if set_model is not None:
            settings.update(guild, 'data_model', set_model)
            reply = reply + '\nNew default data model is "' + str(set_model) + '".'

        if set_sampler != 'unset':
            settings.update(guild, 'sampler', set_sampler)
            reply = reply + '\nNew default sampler is "' + str(set_sampler) + '".'

        if set_max_steps != 1:
            settings.update(guild, 'max_steps', set_max_steps)
            reply = reply + '\nNew max steps value is ' + str(set_max_steps) + '.'
            #automatically lower default steps if max steps goes below it
            if set_max_steps < reviewer['default_steps']:
                settings.update(guild, 'default_steps', set_max_steps)
                reply = reply + '\nDefault steps value is too high! Lowering to ' + str(set_max_steps) + '.'

        if set_max_count is not None:
            settings.update(guild, 'max_count', set_max_count)
            reply = reply + '\nNew max count value is ' + str(set_max_count) + '.'
            #automatically lower default count if max count goes below it
            if set_max_count < reviewer['default_count']:
                settings.update(guild, 'default_count', set_max_count)
                reply = reply + '\nDefault count value is too high! Lowering to ' + str(set_max_count) + '.'

        if set_clip_skip != 0:
            settings.update(guild, 'clip_skip', set_clip_skip)
            reply = reply + f'\nNew CLIP skip is {set_clip_skip}.'

        #review settings again in case user is trying to set steps/counts and max steps/counts simultaneously
        reviewer = settings.read(guild)
        if set_steps > reviewer['max_steps']:
            reply = reply + '\nMax steps is ' + str(reviewer["max_steps"]) + '! You can\'t go beyond it!'
        elif set_steps != 1:
            settings.update(guild, 'default_steps', set_steps)
            reply = reply + '\nNew default steps value is ' + str(set_steps) + '.'

        if set_count is not None:
            if set_count > reviewer['max_count']:
                reply = reply + '\nMax count is ' + str(reviewer["max_count"]) + '! You can\'t go beyond it!'
            else:
                settings.update(guild, 'default_count', set_count)
                reply = reply + '\nNew default count is ' + str(set_count) + '.'

        await ctx.send_response(reply)

def setup(bot):
    # bot.add_cog(SettingsCog(bot))
    pass