import csv
import discord
import json
import os
import requests
import time
import traceback
import threading
from typing import Optional

self = discord.Bot()
dir_path = os.path.dirname(os.path.realpath(__file__))

path = 'resources/'.format(dir_path)

template = {
            "default_steps": 20,
            "sampler": "DPM++ 2M Karras",
            "negative_prompt": "",
            "max_steps": 100,
            "default_count": 1,
            "max_count": 16,
            "clip_skip": 1,
            "data_model": "Default",
            "max_compute": 6.0,
            "max_compute_batch": 16.0,
            "max_compute_queue": 16.0
        }

# initialize global variables here
class GlobalVar:
    url = ""
    dir = ""
    embed_color = discord.Colour.from_rgb(222, 89, 28)
    username: Optional[str] = None
    password: Optional[str] = None
    api_auth = False
    gradio_auth = False
    api_user: Optional[str] = None
    api_pass: Optional[str] = None

    sampler_names: list[str] = []
    model_names = {}
    model_tokens = {}
    style_names = {}
    facefix_models: list[str] = []
    upscaler_names: list[str] = []
    identify_models: list[str] = []
    messages: list[str] = []

    dream_cache: dict = None
    dream_cache_thread = threading.Thread()
    guilds_cache: dict = None
    guilds_cache_thread = threading.Thread()

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
        settings[sett] = value
        with open(path + guild_id + '.json', 'w') as configfile:
            json.dump(settings, configfile)
    if global_var.guilds_cache_thread.is_alive(): global_var.guilds_cache_thread.join()
    global_var.guilds_cache_thread = threading.Thread(target=run)
    global_var.guilds_cache_thread.start()

def get_env_var_with_default(var: str, default: str) -> str:
    ret = os.getenv(var)
    return ret if ret is not None else default

def startup_check():
    # check .env for parameters. if they don't exist, ignore it and go with defaults.
    global_var.url = get_env_var_with_default('URL', 'http://127.0.0.1:7860').rstrip("/")
    print(f'Using URL: {global_var.url}')

    global_var.dir = get_env_var_with_default('DIR', 'outputs')
    print(f'Using outputs directory: {global_var.dir}')

    global_var.username = os.getenv("USER")
    global_var.password = os.getenv("PASS")
    global_var.api_user = os.getenv("APIUSER")
    global_var.api_pass = os.getenv("APIPASS")

    # check if Web UI is running
    connected = False
    while not connected:
        try:
            response = requests.get(global_var.url + '/sdapi/v1/cmd-flags')
            # lazy method to see if --api-auth commandline argument is set
            if response.status_code == 401:
                global_var.api_auth = True
                # lazy method to see if --api-auth credentials are set
                if (not global_var.api_pass) or (not global_var.api_user):
                    print('API rejected me! If using --api-auth, '
                          'please check your .env file for APIUSER and APIPASS values.')
                    os.system("pause")
            # lazy method to see if --api commandline argument is not set
            if response.status_code == 404:
                print('API is unreachable! Please check Web UI COMMANDLINE_ARGS for --api.')
                os.system("pause")
            return requests.head(global_var.url)
        except(Exception,):
            print(f'Waiting for Web UI at {global_var.url}...')
            time.sleep(20)

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
            reader = csv.reader(f, delimiter="|")
            for i, row in enumerate(reader):
                # if header is missing columns, reformat the file
                if i == 0:
                    if len(row)<3:
                        with open('resources/models.csv', 'r') as fp:
                            reader = csv.DictReader(fp, fieldnames=header, delimiter = "|")
                            with open('resources/models2.csv', 'w', newline='') as fh:
                                writer = csv.DictWriter(fh, fieldnames=reader.fieldnames, delimiter = "|")
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
            writer = csv.writer(f, delimiter = "|")
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

    # create persistent session since we'll need to do a few API calls
    s = requests.Session()
    if global_var.api_auth:
        s.auth = (global_var.api_user, global_var.api_pass)

    # do a check to see if --gradio-auth is set
    print('Connecting to WebUI...')
    try:
        response_data = s.get(global_var.url + '/sdapi/v1/cmd-flags').json()
        if response_data['gradio_auth']:
            global_var.gradio_auth = True

        if global_var.gradio_auth:
            login_payload = {
                'username': global_var.username,
                'password': global_var.password
            }
            s.post(global_var.url + '/login', data=login_payload)
        else:
            s.post(global_var.url + '/login')
    except Exception as e:
        print("Can't connect to API for some reason!"
                "Please check your .env URL or credentials.")
        os.system("pause")

    # get samplers
    print('Retrieving samplers...')
    response_data = s.get(global_var.url + "/sdapi/v1/samplers").json()
    for sampler in response_data:
        try:
            global_var.sampler_names.append(sampler['name'])
        except(Exception,):
            # throw in last exception error for anything that wasn't caught earlier
            print("Can't connect to API for some reason!"
                  "Please check your .env URL or credentials.")
            os.system("pause")

    # remove samplers that seem to have some issues under certain cases
    if 'DPM adaptive' in global_var.sampler_names: global_var.sampler_names.remove('DPM adaptive')
    if 'PLMS' in global_var.sampler_names: global_var.sampler_names.remove('PLMS')

    print(f'- Samplers count: {len(global_var.sampler_names)}')

    # get styles
    print('Retrieving styles...')
    response_data = s.get(global_var.url + "/sdapi/v1/prompt-styles").json()
    for style in response_data:
        global_var.style_names[style['name']] = style['prompt']

    print(f'- Styles count: {len(global_var.model_names)}')

    # get face fix models
    print('Retrieving face fix models...')
    response_data = s.get(global_var.url + "/sdapi/v1/face-restorers").json()
    for facefix_model in response_data:
        global_var.facefix_models.append(facefix_model['name'])

    print(f'- Face fix models count: {len(global_var.facefix_models)}')

    # get samplers workaround - if AUTOMATIC1111 provides a better way, this should be updated
    print('Loading upscaler models...')
    config = s.get(global_var.url + "/config/").json()
    try:
        for item in config['components']:
            try:
                if item['props']:
                    if item['props']['label'] == 'Upscaler':
                        global_var.upscaler_names = item['props']['choices']
            except:
                pass
    except:
        print('Warning: Could not read config. Upscalers will be missing.')

    print(f'- Upscalers count: {len(global_var.upscaler_names)}')

    # get dream cache
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
        try:
            read(str(guild.id))
            print(f'I\'m using local settings for {guild.id} a.k.a {guild}.')
        except FileNotFoundError:
            build(str(guild.id))
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