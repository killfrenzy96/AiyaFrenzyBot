import discord
import asyncio
import traceback
from discord.ext import commands

from core import queuehandler

class CancelCog(commands.Cog, name='Cancel Cog', description='Cancels all images in queue.'):
    def __init__(self, bot: discord.Bot):
        self.bot = bot

    @commands.slash_command(name = 'cancel', description = 'Cancels all images in queue.')
    async def cancel(self, ctx: discord.ApplicationContext):
        loop = asyncio.get_running_loop()

        try:
            user = queuehandler.get_user(ctx)
            total_cleared: int = 0
            for queue in queuehandler.GlobalQueue.queues:
                index = len(queue)
                while index > 0:
                    index -= 1
                    user_compare = queuehandler.get_user(queue[index].ctx)
                    if user.id == user_compare.id:
                        queue.pop()
                        total_cleared += 1

            embed=discord.Embed()
            embed.add_field(name='Items Cleared', value=f'``{total_cleared}`` dreams cleared from queue', inline=False)
            loop.create_task(ctx.respond(embed=embed, ephemeral=True))

        except Exception as e:
            content = f'Something went wrong.\n{e}'
            print(content + f'\n{traceback.print_exc()}')
            loop.create_task(ctx.respond(content=content, ephemeral=True, delete_after=30))

def setup(bot: discord.Bot):
    bot.add_cog(CancelCog(bot))
