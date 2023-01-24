import csv
import discord
import json
import os
import traceback
import threading

from core import utility

self = discord.Bot()
dir_path = os.path.dirname(os.path.realpath(__file__))

path = 'resources/'.format(dir_path)

template = {
    'default_steps': 20,
    'default_guidance_scale': 7.0,
    'default_strength': 0.75,
    'sampler': 'DPM++ 2M Karras',
    'negative_prompt': '',
    'max_steps': 100,
    'default_count': 1,
    'max_count': 16,
    'clip_skip': 1,
    'data_model': 'Default',
    'priority': 3, # lower priority gets placed in front of the queue
    'max_compute': 6.0,
    'max_compute_batch': 16.0,
    'max_compute_queue': 16.0
}

# initialize global variables here
class GlobalVar:
    web_ui: list[utility.WebUI] = []
    dir = ''
    embed_color = discord.Colour.from_rgb(222, 89, 28)

    sampler_names: list[str] = []
    model_names = {}
    model_tokens = {}
    model_resolutions = {}
    style_names = {}
    presets = {}
    facefix_models: list[str] = []
    upscaler_names: list[str] = []
    identify_models: list[str] = []
    hypernet_names: list[str] = []
    embedding_names: list[str] = []
    messages: list[str] = []

    images_generated: int
    config_cache: dict = None
    dream_cache: dict = None
    guilds_cache: dict = None

    dream_write_thread = threading.Thread()
    guilds_write_thread = threading.Thread()
    stats_write_thread = threading.Thread()

    slow_samplers = [
        'Heun', 'DPM2', 'DPM2 a', 'DPM++ 2S a',
        'DPM2 Karras', 'DPM2 a Karras', 'DPM++ 2S a Karras',
        'DPM++ SDE', 'DPM++ SDE Karras']

global_var = GlobalVar()

# read/write guild settings
def build(guild_id: str):
    def run():
        settings = json.dumps(template)
        with open(path + guild_id + '.json', 'w') as configfile:
            configfile.write(settings)
    if global_var.guilds_write_thread.is_alive(): global_var.guilds_write_thread.join()
    global_var.guilds_write_thread = threading.Thread(target=run)
    global_var.guilds_write_thread.start()

def read(guild_id: str):
    if global_var.guilds_cache:
        try:
            return global_var.guilds_cache[guild_id]
        except:
            pass

    global_var.guilds_cache = {}
    with open(path + guild_id + '.json', 'r') as configfile:
        settings = dict(template)
        settings.update(json.load(configfile))
    global_var.guilds_cache.update({guild_id: settings})
    return settings

def update(guild_id: str, sett: str, value):
    def run():
        settings = read(guild_id)
        if sett: settings[sett] = value
        with open(path + guild_id + '.json', 'w') as configfile:
            json.dump(settings, configfile)
    if global_var.guilds_write_thread.is_alive(): global_var.guilds_write_thread.join()
    global_var.guilds_write_thread = threading.Thread(target=run)
    global_var.guilds_write_thread.start()

def get_env_var(var: str, default: str = None):
    try:
        ret = global_var.config_cache[var]
    except:
        ret = os.getenv(var)
    return ret if ret is not None else default

def get_config(file_path: str):
    try:
        config = {}
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith('#'):
                    continue
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip()
                if key and val: config[key] = val
        print(f'> Config loaded at {file_path}')
        return config
    except Exception as e:
        print(f'> Failed to load config at {file_path}\n{e}\n{traceback.print_exc()}')
        return None

def startup_check():
    # load config file as an alternative to using .env vars
    config_path = get_env_var('CONFIG', 'resources/config.cfg')
    if config_path:
        if os.path.isfile(config_path):
            # read the config file
            global_var.config_cache = get_config(config_path)
        else:
            # create config file if it doesn't exist
            print(f'Config missing, creating config at {config_path}')
            with open(config_path, 'w') as f:
                f.write(
                    '# This config overrides your .env settings, and can be reloaded using the \'reload\' command from the console.\n'
                    '# Remove the # sign at the start of the setting if you want to use it.\n'
                    '\n'
                    '# The token for your discord bot.\n'
                    '# TOKEN = YOUR_DISCORD_APP_TOKEN_HERE\n'
                    '\n'
                    '# Directory of output images. Default is /outputs.\n'
                    '# If you do not want to save images, you can set this as --no-output\n'
                    '# DIR = --no-output\n'
                    '\n'
                    '# Optional URL arguments\n'
                    '# --gradio-auth username:password - If gradio authentication is required. Provide a username and password.\n'
                    '#    Example: URL = https://abcdef.gradio.app --gradio-auth username:password\n'
                    '# --api-auth username:password - If regular authentication is required. Provide a username and password.\n'
                    '#    Example: URL = https://127.0.0.1:7860 --api-auth username:password\n'
                    '# --no-dream - Prevents Aiya from starting dreams on this URL\n'
                    '# --no-upscale - Prevents Aiya from using the upscaler on this URL\n'
                    '# --no-identify - Prevents Aiya from using interrogation on this URL\n'
                    '# --wait-for URL - Waits for URL to finish processing before starting new dreams on this URL\n'
                    '\n'
                    '# The URL of your main WebUI instance.\n'
                    '# URL = http://127.0.0.1:7860\n'
                    '\n'
                    '# Additional URL\'s for WebUI instances. These are used to speed up queued or batched processing.\n'
                    '# You can add more URL\'s if you need to. They must be in order of priority starting from URL1.\n'
                    '# A few examples have been provided.\n'
                    '# URL1 = 127.0.0.1:7861\n'
                    '# URL2 = 127.0.0.1:7862\n'
                    '# URL3 = 192.168.1.123:7860 --wait-for http://192.168.1.123:7861\n'
                    '# URL4 = 192.168.1.123:7861 --no-upscale --no-identify --wait-for http://192.168.1.123:7860\n'
                    '# URL5 = https://abcdef.gradio.app --gradio-auth username:password\n'
                    '# URL6 = http://example.com:7860 --api-auth username:password\n'
                )

    # connect to WebUI URL access points
    web_ui_list = []
    index = 0
    while True:
        if index == 0:
            url = get_env_var('URL', 'http://127.0.0.1:7860').rstrip('/')
            suffix = ''
        else:
            url = get_env_var(f'URL{index}')
            if not url and index < 9: break
            suffix = str(index)

        if url:
            username = get_env_var(f'USER{suffix}')
            password = get_env_var(f'PASS{suffix}')
            api_user = get_env_var(f'APIUSER{suffix}')
            api_pass = get_env_var(f'APIPASS{suffix}')

            web_ui = utility.WebUI(url, username, password, api_user, api_pass)

            # check if Web UI is running
            if index == 0:
                web_ui.connect_blocking()
            else:
                web_ui.connect()

            web_ui_list.append(web_ui)
        index += 1

    # cleanup current web ui array (only needed when reloading)
    for web_ui in global_var.web_ui:
        web_ui.stop()

    # apply new webui list
    global_var.web_ui = web_ui_list

    print(f'WebUI Endpoints: {len(global_var.web_ui)}')

    global_var.dir = get_env_var('DIR', 'outputs')
    print(f'Using outputs directory: {global_var.dir}')

def files_check():
    # create stats file if it doesn't exist
    if os.path.isfile('resources/stats.txt'):
        pass
    else:
        print(f'Uh oh, stats.txt missing. Creating a new one.')
        with open('resources/stats.txt', 'w') as f:
            f.write('0')

    # read stats
    with open('resources/stats.txt', 'r') as f:
        data = list(map(int, f.readlines()))
    global_var.images_generated = data[0]

    # get models
    print('Loading checkpoint models...')
    header = ['display_name', 'model_full_name', 'activator_token', 'native_resolution']
    unset_model = ['Default', '', '', '']
    make_model_file = True
    replace_model_file = False

    # if models.csv exists and has data
    if os.path.isfile('resources/models.csv'):
        with open('resources/models.csv', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter='|')
            for i, row in enumerate(reader):
                # if header is missing columns, reformat the file
                if i == 0:
                    if len(row)<5:
                        with open('resources/models.csv', 'r') as fp:
                            reader = csv.DictReader(fp, fieldnames=header, delimiter = '|')
                            with open('resources/models2.csv', 'w', newline='') as fh:
                                writer = csv.DictWriter(fh, fieldnames=reader.fieldnames, extrasaction='ignore', delimiter = '|')
                                writer.writeheader()
                                header = next(reader)
                                writer.writerows(reader)
                                replace_model_file = True
                # if first row has data, do nothing
                if i == 1:
                    make_model_file = False
        if replace_model_file:
            os.remove('resources/models.csv')
            os.rename('resources/models2.csv', 'resources/models.csv')

    # create/reformat model.csv if something is wrong
    if make_model_file:
        print(f'Uh oh, missing models.csv data. Creating a new one.')
        with open('resources/models.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter = '|')
            writer.writerow(header)
            writer.writerow(unset_model)

    # get display_name:model_full_name pairs from models.csv into global variable
    with open('resources/models.csv', encoding='utf-8') as csv_file:
        model_data = list(csv.reader(csv_file, delimiter='|'))
        for row in model_data[1:]:
            model_name = row[0]
            data_model = utility.remove_hash(row[1])

            global_var.model_names[model_name] = data_model

            try:
                global_var.model_tokens[model_name] = row[2]
            except:
                global_var.model_tokens[model_name] = ''

            try:
                resolution = int(int(row[3]) / 64) * 64
                global_var.model_resolutions[model_name] = resolution
            except:
                global_var.model_resolutions[model_name] = 512

    print(f'- Checkpoint models count: {len(global_var.model_names)}')
    print(global_var.model_names)

    print('Loading presets...')
    global_var.presets = {}
    try:
        with open('resources/presets.cfg', 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith('#'):
                    continue
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip()
                if key and val: global_var.presets[key] = val
    except FileNotFoundError:
        with open('resources/presets.cfg', 'w') as f:
            f.write('# preset name = full /dream command string here. Make sure to remove the # at the start.')

    print(f'- Presets count: {len(global_var.presets)}')

    # get random messages list
    print('Loading messages...')
    with open('resources/messages.csv') as csv_file:
        message_data = list(csv.reader(csv_file, delimiter='|'))
        for row in message_data:
            global_var.messages.append(row[0])

    print(f'- Messages count: {len(global_var.messages)}')

    # if directory in DIR doesn't exist, create it
    if global_var.dir != '--no-output':
        dir_exists = os.path.exists(global_var.dir)
        if dir_exists is False:
            print(f'The folder for DIR doesn\'t exist! Creating folder at {global_var.dir}.')
            os.mkdir(global_var.dir)

    # use main webui instance data for global config
    web_ui = global_var.web_ui[0]
    global_var.sampler_names = web_ui.sampler_names
    global_var.style_names = web_ui.style_names
    global_var.facefix_models = web_ui.facefix_models
    global_var.upscaler_names = web_ui.upscaler_names
    global_var.hypernet_names = web_ui.hypernet_names
    global_var.embedding_names = web_ui.embedding_names

    if len(global_var.model_names) > 25: print('- Warning: More than 25 checkpoints, falling back to autocomplete instead of choices.')
    if len(global_var.style_names) > 25: print('- Warning: More than 25 styles, falling back to autocomplete instead of choices.')
    if len(global_var.upscaler_names) > 25: print('- Warning: More than 25 upscalers, falling back to autocomplete instead of choices.')
    # if len(global_var.hypernet_names) > 25: print('- Warning: More than 25 hyper networks, falling back to autocomplete instead of choices.')

    # load dream cache
    get_dream_command(-1)

    # get interrogate models - no API endpoint for this, so it's hard coded
    global_var.identify_models = ['clip', 'deepdanbooru']


def guilds_check(self: discord.Bot):
    # add dummy guild for private channels
    class simple_guild:
        id: int | str
        def __str__(self):
            return self.id
    guild_private: simple_guild = simple_guild()
    guild_private.id = 'private'

    # guild settings files. has to be done after on_ready
    guilds = self.guilds + [guild_private]
    for guild in guilds:
        guild_string = str(guild.id)
        try:
            read(guild_string)
            update(guild_string, None, None) # update file template
            print(f'I\'m using local settings for {guild.id} a.k.a {guild}.')
        except FileNotFoundError:
            build(guild_string)
            print(f'Creating new settings file for {guild.id} a.k.a {guild}.')


# get dream command from cache
def get_dream_command(message_id: int):
    if global_var.dream_cache:
        try:
            return global_var.dream_cache[message_id]
        except:
            return None

    # retrieve cache from file
    print('Retrieving dream message cache...')
    global_var.dream_cache = {}

    def read_cache(file_path: str):
        try:
            with open(file_path) as f:
                for line in f:
                    if line.startswith('#'):
                        continue
                    key, val = line.split('=', 1)
                    global_var.dream_cache.update({int(key.strip()): val.strip()})
            print(f'- Loaded dream cache: {file_path}')
        except FileNotFoundError:
            pass

    read_cache('resources/dream-cache.txt')
    read_cache('resources/dream-cache-old.txt')
    print(f'- Dream message cache entries: {len(global_var.dream_cache)}')

    try:
        return global_var.dream_cache[message_id]
    except Exception as e:
        return None


# append command to dream command cache
def append_dream_command(message_id: int, command: str):
    # cache into disk
    def run():
        if get_dream_command(message_id) == None:
            dream_cache_line = str(message_id) + '=' + command.replace('\n', ' ').strip() + '\n'

            # cache into memory
            global_var.dream_cache[message_id] = dream_cache_line

            # archive file if it's too big (over 5MB)
            try:
                file_stats = os.stat('resources/dream-cache.txt')
                if file_stats.st_size > 5 * 1024 * 1024:
                    # remove old archived file
                    try:
                        os.remove('resources/dream-cache-old.txt')
                    except:
                        pass

                    # archive current file
                    try:
                        os.rename('resources/dream-cache.txt', 'resources/dream-cache-old.txt')
                    except:
                        pass
            except:
                pass

            try:
                with open('resources/dream-cache.txt', 'a') as f:
                    f.write(dream_cache_line)
            except FileNotFoundError:
                with open('resources/dream-cache.txt', 'w') as f:
                    f.write(dream_cache_line)

    if global_var.dream_write_thread.is_alive(): global_var.dream_write_thread.join()
    global_var.dream_write_thread = threading.Thread(target=run)
    global_var.dream_write_thread.start()


# increment number of images generated
def increment_stats(count: int = 1):
    def run():
        global_var.images_generated += count
        with open('resources/stats.txt', 'w') as f:
            f.write(str(global_var.images_generated))

    if global_var.stats_write_thread.is_alive(): global_var.stats_write_thread.join()
    global_var.stats_write_thread = threading.Thread(target=run)
    global_var.stats_write_thread.start()