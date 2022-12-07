import csv
import discord
import json
import os
import threading

from core import utility

self = discord.Bot()
dir_path = os.path.dirname(os.path.realpath(__file__))

path = 'resources/'.format(dir_path)

template = {
    'default_steps': 20,
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
    style_names = {}
    facefix_models: list[str] = []
    upscaler_names: list[str] = []
    identify_models: list[str] = []
    messages: list[str] = []

    config_cache: dict = None
    dream_cache: dict = None
    dream_cache_thread = threading.Thread()
    guilds_cache: dict = None
    guilds_cache_thread = threading.Thread()

    slow_samplers = [
        'Heun', 'DPM2', 'DPM2 a', 'DPM++ 2S a',
        'DPM2 Karras', 'DPM2 a Karras', 'DPM++ 2S a Karras',
        'DPM++ SDE', 'DPM++ SDE Karras']

global_var = GlobalVar()

def build(guild_id: str):
    def run():
        settings = json.dumps(template)
        with open(path + guild_id + '.json', 'w') as configfile:
            configfile.write(settings)
    if global_var.guilds_cache_thread.is_alive(): global_var.guilds_cache_thread.join()
    global_var.guilds_cache_thread = threading.Thread(target=run)
    global_var.guilds_cache_thread.start()

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
    if global_var.guilds_cache_thread.is_alive(): global_var.guilds_cache_thread.join()
    global_var.guilds_cache_thread = threading.Thread(target=run)
    global_var.guilds_cache_thread.start()

def get_env_var(var: str, default: str = None):
    try:
        ret = global_var.config_cache[var]
    except:
        ret = os.getenv(var)
    return ret if ret is not None else default

def get_config(file_path: str):
    try:
        config = {}
        with open(file_path) as f:
            for line in f:
                if line.startswith('#'):
                    continue
                key, val = line.split('=', 1)
                config[key.strip()] = val.strip()
        print(f'Loaded config at {file_path}')
        return config
    except:
        return None

def startup_check():
    # load config file if it exists
    config_path = get_env_var('CONFIG', 'resources/config.cfg')
    if config_path: global_var.config_cache = get_config(config_path)

    # cleanup current web ui array if reloading
    for web_ui in global_var.web_ui:
        web_ui.stop()

    # connect to WebUI URL access points
    global_var.web_ui = []
    index = 0
    while True:
        if index == 0:
            url = get_env_var('URL', 'http://127.0.0.1:7860').rstrip('/')
            suffix = ''
        else:
            url = get_env_var(f'URL{index}')
            if not url and index > 2: break
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

            global_var.web_ui.append(web_ui)
        index += 1

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

    header = ['display_name', 'model_full_name', 'activator_token']
    unset_model = ['Default', '', '']
    make_model_file = True
    replace_model_file = False

    # if models.csv exists and has data
    print('Loading checkpoint models...')
    if os.path.isfile('resources/models.csv'):
        with open('resources/models.csv', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter='|')
            for i, row in enumerate(reader):
                # if header is missing columns, reformat the file
                if i == 0:
                    if len(row)<3:
                        with open('resources/models.csv', 'r') as fp:
                            reader = csv.DictReader(fp, fieldnames=header, delimiter = '|')
                            with open('resources/models2.csv', 'w', newline='') as fh:
                                writer = csv.DictWriter(fh, fieldnames=reader.fieldnames, delimiter = '|')
                                writer.writeheader()
                                header = next(reader)
                                writer.writerows(reader)
                                replace_model_file = True
                        break # no need to run this multiple times
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
            global_var.model_names[row[0]] = row[1]
            global_var.model_tokens[row[0]] = row[2]

    print(f'- Checkpoint models count: {len(global_var.model_names)}')

    # get random messages list
    print('Loading messages...')
    with open('resources/messages.csv') as csv_file:
        message_data = list(csv.reader(csv_file, delimiter='|'))
        for row in message_data:
            global_var.messages.append(row[0])

    print(f'- Messages count: {len(global_var.messages)}')

    # if directory in DIR doesn't exist, create it
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
            with open(file_path, 'r') as f:
                reader = csv.reader(f, delimiter='`')
                for row in reader:
                    if len(row) == 2:
                        global_var.dream_cache.update({int(row[0]): row[1]})
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
dream_cache_write_thread = threading.Thread()
def append_dream_command(message_id: int, command: str):
    def run():
        if get_dream_command(message_id) == None:
            dream_cache_line = str(message_id) + '`' + command + '\n'

            # archive file if it's too big (over 1MB)
            try:
                file_stats = os.stat('resources/dream-cache.txt')
                if file_stats.st_size > 1024 * 1024:
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

    if global_var.dream_cache_thread.is_alive(): global_var.dream_cache_thread.join()
    global_var.dream_cache_thread = threading.Thread(target=run)
    global_var.dream_cache_thread.start()


# increment number of images generated
def increment_stats(count: int = 1):
    def run():
        with open('resources/stats.txt', 'r') as f:
            data = list(map(int, f.readlines()))
        data[0] = data[0] + count
        with open('resources/stats.txt', 'w') as f:
            f.write('\n'.join(str(x) for x in data))
    threading.Thread(target=run).start()