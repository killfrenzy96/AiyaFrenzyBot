import csv
import discord
import json
import os
import requests
import time
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
            "data_model": "Default",
            "max_compute": 6.0,
            "max_compute_batch": 16.0,
            "max_compute_queue": 16.0
        }

#initialize global variables here
class GlobalVar:
    url = ""
    dir = ""
    embed_color = discord.Colour.from_rgb(222, 89, 28)
    username: Optional[str] = None
    password: Optional[str] = None
    api_auth = False
    api_user: Optional[str] = None
    api_pass: Optional[str] = None
    sampler_names = []
    model_names = {}
    style_names = {}
    facefix_models = []
    model_fn_index = 0
    send_model = False


global_var = GlobalVar()

def build(guild_id):
    settings = json.dumps(template)
    with open(path + guild_id + '.json', 'w') as configfile:
        configfile.write(settings)

def read(guild_id):
    with open(path + guild_id + '.json', 'r') as configfile:
        settings = dict(template)
        settings.update(json.load(configfile))
    return settings

def update(guild_id:str, sett:str, value):
    with open(path + guild_id + '.json', 'r') as configfile:
        settings = json.load(configfile)
    settings[sett] = value
    with open(path + guild_id + '.json', 'w') as configfile:
        json.dump(settings, configfile)

def get_env_var_with_default(var: str, default: str) -> str:
    ret = os.getenv(var)
    return ret if ret is not None else default

def startup_check():
    #check .env for parameters. if they don't exist, ignore it and go with defaults.
    global_var.url = get_env_var_with_default('URL', 'http://127.0.0.1:7860').rstrip("/")
    print(f'Using URL: {global_var.url}')

    global_var.dir = get_env_var_with_default('DIR', 'outputs')
    print(f'Using outputs directory: {global_var.dir}')

    global_var.username = os.getenv("USER")
    global_var.password = os.getenv("PASS")
    global_var.api_user = os.getenv("APIUSER")
    global_var.api_pass = os.getenv("APIPASS")

    #check if Web UI is running
    connected = False
    while not connected:
        try:
            response = requests.get(global_var.url + '/sdapi/v1/cmd-flags')
            # lazy method to see if --api-auth commandline argument is set
            if response.status_code == 401:
                global_var.api_auth = True
                # lazy method to see if --api-auth credentials are set
                if not global_var.api_pass:
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
    #creating files if they don't exist
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
    #if models.csv exists and has data
    if os.path.isfile('resources/models.csv'):
        with open('resources/models.csv', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter="|")
            for i, row in enumerate(reader):
                #if header is missing columns, reformat the file
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
                #if first row has data, do nothing
                if i == 1:
                    make_model_file = False
        if replace_model_file:
            os.remove('resources/models.csv')
            os.rename('resources/models2.csv', 'resources/models.csv')
    #create/reformat model.csv if something is wrong
    if make_model_file:
        print(f'Uh oh, missing models.csv data. Creating a new one.')
        with open('resources/models.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter = "|")
            writer.writerow(header)
            writer.writerow(unset_model)

    #get display_name:model_full_name pairs from models.csv into global variable
    with open('resources/models.csv', encoding='utf-8') as csv_file:
        model_data = list(csv.reader(csv_file, delimiter='|'))
        for row in model_data[1:]:
            global_var.model_names[row[0]] = row[1]

    #if directory in DIR doesn't exist, create it
    dir_exists = os.path.exists(global_var.dir)
    if dir_exists is False:
        print(f'The folder for DIR doesn\'t exist! Creating folder at {global_var.dir}.')
        os.mkdir(global_var.dir)

    #pull list of samplers, styles and face restorers from api
    with requests.Session() as s:
        if global_var.api_auth:
            s.auth = (global_var.api_user, global_var.api_pass)

        if global_var.username is not None:
            login_payload = {
                'username': global_var.username,
                'password': global_var.password
            }
            s.post(global_var.url + '/login', data=login_payload)
            r = s.get(global_var.url + "/sdapi/v1/samplers")
            r2 = s.get(global_var.url + "/sdapi/v1/prompt-styles")
            r3 = s.get(global_var.url + "/sdapi/v1/face-restorers")
        else:
            s.post(global_var.url + '/login')
            r = s.get(global_var.url + "/sdapi/v1/samplers")
            r2 = s.get(global_var.url + "/sdapi/v1/prompt-styles")
            r3 = s.get(global_var.url + "/sdapi/v1/face-restorers")
        for s1 in r.json():
            global_var.sampler_names.append(s1['name'])
        for s2 in r2.json():
            global_var.style_names[s2['name']] = s2['prompt']
        for s3 in r3.json():
            global_var.facefix_models.append(s3['name'])

        if 'DPM adaptive' in global_var.sampler_names: global_var.sampler_names.remove('DPM adaptive')

def guilds_check(self):
    #guild settings files. has to be done after on_ready
    class simple_guild: id: int | str
    guild_private: simple_guild = simple_guild()
    guild_private.id = 'private'

    for guild in self.guilds + [guild_private]:
        try:
            read(str(guild.id))
            print(f'I\'m using local settings for {guild.id} a.k.a {guild}.')
            #if models.csv has the blank "Default" data, update guild settings
            with open('resources/models.csv', 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter='|')
                for row in reader:
                    if row['display_name'] == 'Default' and row['model_full_name'] == '':
                        update(str(guild.id), 'data_model', '')
                        print('I see models.csv is on defaults. Updating guild model settings to default.')
        except FileNotFoundError:
            build(str(guild.id))
            print(f'Creating new settings file for {guild.id} a.k.a {guild}.')

    if os.path.isfile('resources/None.json'):
        pass
    else:
        print(f'Setting up settings for DMs, called None.json')
        build("None")
