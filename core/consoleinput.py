import asyncio
import discord
import traceback
from core import settings
from threading import Thread

class ConsoleInput:
    def __init__(self, bot: discord.Bot):
        self.bot = bot
        self.input_thread: Thread = None
        self.running = False
        self.help_output = ('Valid commands:\n'
                           '  reload - reloads all settings.\n'
                           '  guild list - lists all guilds that Aiya is in.\n'
                           '  guild leave (id) - leaves a guild.\n'
                           '  exit - shuts down bot and exits the program.')

    def run(self):
        if self.input_thread == None:
            self.running = True
            self.input_thread = Thread(target=self.get_input, daemon=True)
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
                        print(f'Reloading settings...')
                        print(f'> Reloading files')
                        settings.files_check()
                        print(f'> Clearing guilds cache')
                        settings.global_var.guilds_cache = {}
                        print(f'> Reloading guilds')
                        settings.guilds_check(self.bot)
                        print(f'Reload complete.')

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

                    case 'exit':
                        print(f'Shutting down...')
                        self.shutdown()
                        asyncio.run(self.bot.close())

                    case other:
                        print(self.help_output)

            except Exception as e:
                print(f'Command failed: {e}\n{traceback.print_exc()}')
