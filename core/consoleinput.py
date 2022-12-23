import asyncio
import discord
import traceback
import threading

from core import settings
from core import queuehandler

class ConsoleInput:
    def __init__(self, bot: discord.Bot):
        self.bot = bot
        self.input_thread: threading.Thread = None
        self.running = False
        self.help_output = ('Valid commands:\n'
                           '  reload - reloads all settings.\n'
                           '  guild list - lists all guilds that Aiya is in.\n'
                           '  guild leave (id) - leaves a guild.\n'
                           '  status - show web ui online and queue status.')

    def run(self):
        if self.input_thread == None:
            self.running = True
            self.input_thread = threading.Thread(target=self.get_input, daemon=True)
            self.input_thread.start()

    def shutdown(self):
        self.running = False

    def get_input(self):
        while self.running:
            console_input = input()
            try:
                input_parts = console_input.split(' ')
                match input_parts[0]:
                    case 'reload':
                        print('Reloading settings...')

                        # print('> Reloading config')
                        settings.startup_check()

                        # print('> Clearing guilds cache')
                        settings.global_var.guilds_cache = None

                        # print('> Clearing dream cache')
                        settings.global_var.dream_cache = None

                        # print('> Reloading files')
                        settings.files_check()

                        # print('> Reloading guilds')
                        settings.guilds_check(self.bot)

                        # print('> Resetup dream queue')
                        queuehandler.dream_queue.setup()

                        # print('> Reloading extensions')
                        self.bot.reload_extension('core.stablecog')
                        self.bot.reload_extension('core.drawcog')
                        self.bot.reload_extension('core.upscalecog')
                        self.bot.reload_extension('core.minigamecog')

                        print('Reload complete.')

                    case 'guild':
                        if len(input_parts) < 2:
                            print(self.help_output)
                            return

                        match input_parts[1]:
                            case 'list':
                                print(f'Guild ID - Guild Name')
                                for guild in self.bot.guilds:
                                    print(f'{guild.id} - {guild.name}')

                            case 'leave':
                                if len(input_parts) < 3:
                                    print(self.help_output)
                                    return

                                try:
                                    guild_id = int(input_parts[2])
                                except:
                                    print(f'Guild ID needs to be a valid integer.')
                                    return

                                guild = self.bot.get_guild(guild_id)
                                if not guild:
                                    print(f'Guild ID \'{guild_id}\' not found!')
                                    return

                                try:
                                    guild.leave()
                                    print(f'Left Guild ID \'{guild_id}\'')
                                except:
                                    print(f'Failed to leave Guild ID \'{guild_id}\'')
                            case other:
                                print(self.help_output)

                    case 'status':
                        for dream_instance in queuehandler.dream_queue.dream_instances:
                            web_ui = dream_instance.web_ui

                            message = web_ui.url
                            if web_ui.online:
                                message += ' - ONLINE'
                            else:
                                message += f' - OFFLINE'
                                if web_ui.reconnect_thread.is_alive():
                                    message += f',RECONNECTING'
                                else:
                                    message += f',DISABLED'
                            message += f' - Queue:{dream_instance.get_queue_length()}'
                            print(message)

                        print(f'Total Queue:{queuehandler.dream_queue.get_queue_length()}')

                    case other:
                        print(self.help_output)

            except Exception as e:
                print(f'Command failed: {e}\n{traceback.print_exc()}')
