import discord
from discord.ext import commands

from core import queuehandler

class CancelCog(commands.Cog, name='Cancel Cog', description='Cancels all images in queue.'):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name = "cancel", description = "Cancels all images in queue.")
    async def cancel(self, ctx: discord.ApplicationContext):
        def clear_queue(queue: list[queuehandler.DrawObject]):
            queue_cleared: int = 0
            index = len(queue)
            while index > 0:
                index -= 1
                if queue[index].ctx.author.id == ctx.author.id:
                    queue.pop()
                    queue_cleared += 1
            return queue_cleared

        total_cleared: int = 0
        total_cleared += clear_queue(queuehandler.GlobalQueue.queue_high)
        total_cleared += clear_queue(queuehandler.GlobalQueue.queue)
        total_cleared += clear_queue(queuehandler.GlobalQueue.queue_low)

        embed=discord.Embed()
        embed.add_field(name="Items Cleared", value=f'``{total_cleared}`` dreams cleared from queue', inline=False)
        await ctx.respond(embed=embed, ephemeral=True)

def setup(bot: discord.Bot):
    bot.add_cog(CancelCog(bot))
