import time
import requests
import threading
import discord
import traceback

# WebUI access point
class WebUI:
    valid_flags = [
        '--no-dream',
        '--no-upscale',
        '--no-identify',
        '--wait-for',
        '--gradio-auth',
        '--api-auth'
    ]

    def __init__(self, url: str, username: str = None, password: str = None, api_user: str = None, api_pass: str = None):
        self.online = False
        self.stopped = False
        self.auth_rejected = 0
        self.online_last = None

        self.username = username
        self.password = password
        self.gradio_auth = False

        self.api_user = api_user
        self.api_pass = api_pass
        self.api_auth = False

        # flags, currently used to disable identify on certain webui endpoints
        # valid flags: --no-dream --no-upscale --no-identify --wait-for URLID

        # assign flags to key value pairs
        self.flags = {}
        if url:
            parts_list = url.split(' ')
            index = 0

            # before starting, get the URL first
            self.url = ''
            while index < len(parts_list):
                part = parts_list[index].strip()
                if part.startswith('--'):
                    break
                else:
                    if self.url: self.url += ' '
                    self.url += part
                    index += 1

            # now we can look at the flags
            while index < len(parts_list):
                part = parts_list[index].strip()

                # check if the key has a value
                index += 1
                if part.startswith('--') and index < len(parts_list):
                    part2 = parts_list[index].strip()

                    if part2.startswith('--'):
                        # two flags found, make it into its own key
                        self.flags[part] = True
                    else:
                        # flag value pair found, assign the value to the key
                        try:
                            self.flags[part] = part2
                        except:
                            pass
                        index += 1
                else:
                    # last item, assign the flag as a key
                    self.flags[part] = True
        else:
            self.url = url

        self.reconnect_thread: threading.Thread = threading.Thread()

        self.data_models: list[str] = []
        self.sampler_names: list[str] = []
        self.model_tokens = {}
        self.style_names = {}
        self.facefix_models: list[str] = []
        self.highres_upscaler_names: list[str] = []
        self.upscaler_names: list[str] = []
        self.identify_models: list[str] = []
        self.lora_names: list[str] = []
        self.hypernet_names: list[str] = []
        self.embedding_names: list[str] = []
        self.messages: list[str] = []

        if '--gradio-auth' in self.flags:
            try:
                username_password: list[str] = self.flags['--gradio-auth'].split(':', 1)
                self.username = username_password[0]
                self.password = username_password[1]
                self.gradio_auth = True
            except:
                print('> - Warning: Invalid args for --gradio-auth username:password')

        if '--api-auth' in self.flags:
            try:
                username_password: list[str] = self.flags['--api-auth'].split(':', 1)
                self.api_user = username_password[0]
                self.api_pass = username_password[1]
                self.api_auth = True
            except:
                print('> - Warning: Invalid args for --gradio-auth username:password')

    # check connection to WebUI and authentication
    def check_status(self):
        if self.stopped: return False
        try:
            response = requests.get(self.url + '/sdapi/v1/cmd-flags', timeout=30)
            # lazy method to see if --api-auth commandline argument is set
            self.api_auth = False
            if response.status_code == 401:
                self.api_auth = True
                # lazy method to see if --api-auth credentials are set
                if (not self.api_pass) or (not self.api_user):
                    print(f'> WebUI API at {self.url} rejected me! If using --api-auth, '
                          'please check your .env file for APIUSER and APIPASS values.')
                    self.auth_rejected += 1
                    self.online = False
                    return False
            # lazy method to see if --api commandline argument is not set
            elif response.status_code == 404:
                print(f'> WebUI API at {self.url} is unreachable! Please check WebUI COMMANDLINE_ARGS for --api.')
                self.auth_rejected += 1
                self.online = False
                return False
        except:
            if self.online == True:
                print(f'> Connection failed to WebUI at {self.url}')
            self.online = False
            return False

        # check gradio authentication
        if self.stopped: return False
        try:
            s = requests.Session()
            if self.api_auth:
                s.auth = (self.api_user, self.api_pass)

            response_data = s.get(self.url + '/sdapi/v1/cmd-flags', timeout=30).json()
            if response_data['gradio_auth']:
                self.gradio_auth = True
            else:
                self.gradio_auth = False

            if self.gradio_auth:
                login_payload = {
                    'username': self.username,
                    'password': self.password
                }
                s.post(self.url + '/login', data=login_payload, timeout=30)
            else:
                s.post(self.url + '/login', timeout=30)
        except Exception as e:
            print(f'> Gradio Authentication failed for WebUI at {self.url}')
            self.online = False
            return False

        # retrieve instance configuration
        if self.stopped: return False
        try:
            # get stable diffusion models
            # print('Retrieving stable diffusion models...')
            response_data = s.get(self.url + '/sdapi/v1/sd-models', timeout=30).json()
            self.data_models = []
            for sd_model in response_data:
                self.data_models.append(remove_hash(sd_model['title']))
            # print(f'- Stable diffusion models: {len(self.data_models)}')

            # get samplers
            # print('Retrieving samplers...')
            response_data = s.get(self.url + '/sdapi/v1/samplers', timeout=30).json()
            self.sampler_names = []
            for sampler in response_data:
                self.sampler_names.append(sampler['name'])

            # remove samplers that seem to have some issues under certain cases
            if 'DPM adaptive' in self.sampler_names: self.sampler_names.remove('DPM adaptive')
            if 'PLMS' in self.sampler_names: self.sampler_names.remove('PLMS')
            if 'UniPC' in self.sampler_names: self.sampler_names.remove('UniPC')
            # print(f'- Samplers count: {len(self.sampler_names)}')

            # get styles
            # print('Retrieving styles...')
            response_data = s.get(self.url + '/sdapi/v1/prompt-styles', timeout=30).json()
            self.style_names = {}
            for style in response_data:
                self.style_names[style['name']] = style['prompt'] + '\n' + style['negative_prompt']
            # print(f'- Styles count: {len(self.style_names)}')

            # get face fix models
            # print('Retrieving face fix models...')
            response_data = s.get(self.url + '/sdapi/v1/face-restorers', timeout=30).json()
            self.facefix_models = []
            for facefix_model in response_data:
                self.facefix_models.append(facefix_model['name'])
            # print(f'- Face fix models count: {len(self.facefix_models)}')

            # get settings from config workaround - if AUTOMATIC1111 provides a better way, this should be updated
            # print('Retrieving config models...')
            config = s.get(self.url + '/config', timeout=30).json()
            self.lora_names = []
            self.highres_upscaler_names = []
            try:
                for item in config['components']:
                    try:
                        if item['props']:
                            if item['props']['elem_id'] == 'setting_sd_lora':
                                self.lora_names = item['props']['choices']
                            if item['props']['elem_id'] == 'txt2img_hr_upscaler':
                                self.highres_upscaler_names = item['props']['choices']
                    except:
                        pass
            except:
                print('Warning: Could not read config. LORA or High-res upscalers will be missing.')
            if '' in self.lora_names: self.lora_names.remove('')
            if 'None' not in self.lora_names: self.lora_names.insert(0, 'None')
            if 'None' not in self.highres_upscaler_names: self.highres_upscaler_names.insert(0, 'None')

            # get upscaler models
            response_data = s.get(self.url + '/sdapi/v1/upscalers', timeout=30).json()
            self.upscaler_names = []
            for upscaler in response_data:
                self.upscaler_names.append(upscaler['name'])

            # remove upscalers that seem to have some issues
            if 'LSDR' in self.upscaler_names: self.upscaler_names.remove('LSDR')
            # print(f'- Upscalers count: {len(self.upscaler_names)}')

            # get hypernet models
            # print('Retrieving hyper network models...')
            response_data = s.get(self.url + '/sdapi/v1/hypernetworks', timeout=30).json()
            self.hypernet_names = []
            for hypernet_model in response_data:
                self.hypernet_names.append(hypernet_model['name'])
            # print(f'- Hyper network models count: {len(self.hypernet_names)}')

            # get embedding models
            # print('Retrieving embedding models...')
            response_data = s.get(self.url + '/sdapi/v1/embeddings', timeout=30).json()
            self.embedding_names = []
            for (item, embedding_list) in response_data.items():
                for (embedding_model, value) in embedding_list.items():
                    self.embedding_names.append(embedding_model)
            # print(f'- Embedding models count: {len(self.embedding_names)}')

            print(f'> Loaded data for WebUI at {self.url}')
            print(f'> - Models:{len(self.data_models)} Samplers:{len(self.sampler_names)} Styles:{len(self.style_names)} FaceFix:{len(self.facefix_models)} Upscalers:{len(self.upscaler_names)} HyperNets:{len(self.hypernet_names)} Embeddings:{len(self.embedding_names)}')
            if len(self.flags):
                print(f'> - Flags:{self.flags}')
                # check for any unknown flags
                for (flag, value) in self.flags.items():
                    if flag not in WebUI.valid_flags:
                        print(f'> - Warning - Unknown flag:{flag}')


        except Exception as e:
            print(f'> Retrieve data failed for WebUI at {self.url}')
            print(f'\n{traceback.print_exc()}')
            self.online = False
            return False

        if self.stopped: return False
        self.online_last = time.time()
        self.auth_rejected = 0
        self.online = True
        return True

    # return a request session
    def get_session(self):
        if self.stopped: return None
        try:
            s = requests.Session()
            if self.api_auth:
                s.auth = (self.api_user, self.api_pass)

                # send login payload to webui
                if self.gradio_auth:
                    login_payload = {
                        'username': self.username,
                        'password': self.password
                    }
                    s.post(self.url + '/login', data=login_payload, timeout=5)
                else:
                    s.post(self.url + '/login', timeout=5)

            # if it's been a while since the last check for being online, do one now
            elif time.time() > self.online_last + 5:
                s.get(self.url + '/sdapi/v1/cmd-flags', timeout=5)
            self.online_last = time.time()
            self.auth_rejected = 0
            self.online = True
            return s

        except Exception as e:
            if self.online == True:
                print(f'> Connection failed to WebUI at {self.url}')
            self.online = False
            self.connect() # attempt to reconnect
            return None

    # continually retry a connection to the webui
    def connect(self):
        def run():
            print(f'> Connecting to WebUI at {self.url}')
            while self.check_status() == False:
                if self.stopped: return None
                if self.auth_rejected >= 3:
                    print(f'> - Request rejected too many times! I will not try to reconnect to WebUI at {self.url}')
                    break
                time.sleep(30)
                if self.auth_rejected >= 3:
                    break
            print(f'> Connected to {self.url}')

        if self.stopped: return None
        if self.reconnect_thread.is_alive() == False:
            self.reconnect_thread = threading.Thread(target=run, daemon=True)
            self.reconnect_thread.start()

    # block code until connected to the WebUI
    def connect_blocking(self):
        if self.stopped: return None
        if self.reconnect_thread.is_alive() == False:
            self.connect()
        self.reconnect_thread.join()

    # force a connection check
    def reconnect(self):
        if self.stopped: return None
        if self.reconnect_thread.is_alive() == False:
            self.online = False
            self.connect()

    # stop all further connections on this WebUI
    def stop(self):
        self.online = False
        self.stopped = True


# base queue object from dreams
class DreamObject:
    def __init__(self, cog, ctx, view = None, message = None, write_to_cache = False, wait_for_dream = None, payload = None):
        self.cog = cog
        self.ctx: discord.ApplicationContext | discord.Interaction | discord.Message = ctx
        self.view: discord.ui.View = view
        self.message: str = message
        self.write_to_cache: bool = write_to_cache
        self.wait_for_dream = wait_for_dream
        self.payload = payload
        self.uploaded = False
        self.dream_attempts = 0

# the queue object for txt2image and img2img
class DrawObject(DreamObject):
    def __init__(self, cog, ctx, prompt, negative, model_name, data_model, steps, width, height, guidance_scale, sampler, seed,
                 strength, init_url, batch, style, facefix, tiling, highres_fix, clip_skip, script,
                 view = None, message = None, write_to_cache = True, wait_for_dream: DreamObject = None, payload = None):
        super().__init__(cog, ctx, view, message, write_to_cache, wait_for_dream, payload)
        self.prompt: str = prompt
        self.negative: str = negative
        self.model_name: str = model_name
        self.data_model: str = data_model
        self.steps: int = steps
        self.width: int = width
        self.height: int = height
        self.guidance_scale: float = guidance_scale
        self.sampler: str = sampler
        self.seed: int = seed
        self.strength: float = strength
        self.init_url: str = init_url
        self.batch: int = batch
        self.style: str = style
        self.facefix: str = facefix
        self.tiling: bool = tiling
        self.highres_fix: str = highres_fix
        self.clip_skip: int = clip_skip
        self.script: str = script

    def get_command(self):
        command = f'/dream prompt:{self.prompt}'
        if self.negative != '':
            command += f' negative:{self.negative}'
        if self.data_model and self.model_name != 'Default':
            command += f' checkpoint:{self.model_name}'
        command += f' width:{self.width} height:{self.height} steps:{self.steps} guidance_scale:{self.guidance_scale} sampler:{self.sampler} seed:{self.seed}'
        if self.init_url or (self.highres_fix != None and self.highres_fix != 'None'):
            command += f' strength:{self.strength}'
        if self.init_url:
            command += f' init_url:{self.init_url}'
        if self.style != None and self.style != 'None':
            command += f' style:{self.style}'
        if self.facefix != None and self.facefix != 'None':
            command += f' facefix:{self.facefix}'
        if self.tiling:
            command += f' tiling:{self.tiling}'
        if self.highres_fix != None and self.highres_fix != 'None':
            command += f' highres_fix:{self.highres_fix}'
        if self.clip_skip != 1:
            command += f' clip_skip:{self.clip_skip}'
        if self.batch > 1:
            command += f' batch:{self.batch}'
        if self.script != None and self.script != 'None':
            command += f' script:{self.script}'
        return command

# the queue object for extras - upscale
class UpscaleObject(DreamObject):
    def __init__(self, cog, ctx, resize, init_url, upscaler_1, upscaler_2, upscaler_2_strength,
                 gfpgan, codeformer, upscale_first,
                 view = None, message = None, write_to_cache = False, wait_for_dream: DreamObject = None, payload = None):
        super().__init__(cog, ctx, view, message, write_to_cache, wait_for_dream, payload)
        self.resize: float = resize
        self.init_url: str = init_url
        self.upscaler_1: str = upscaler_1
        self.upscaler_2: str = upscaler_2
        self.upscaler_2_strength: float = upscaler_2_strength
        self.gfpgan: float = gfpgan
        self.codeformer: float = codeformer
        self.upscale_first: bool = upscale_first

    def get_command(self):
        command = f'/upscale init_url:{self.init_url} resize:{self.resize} upscaler_1:{self.upscaler_1}'
        if self.upscaler_2 != None:
            command += f' upscaler_2:{self.upscaler_2} upscaler_2_strength:{self.upscaler_2_strength}'
        if self.gfpgan:
            command += f' gfpgan:{self.gfpgan}'
        if self.codeformer:
            command += f' codeformer:{self.codeformer}'
        if self.upscale_first:
            command += f' upscale_first:{self.upscale_first}'
        return command

# the queue object for identify (interrogate)
class IdentifyObject(DreamObject):
    def __init__(self, cog, ctx, init_url, model,
                 view = None, message = None, write_to_cache = False, wait_for_dream: DreamObject = None, payload = None):
        super().__init__(cog, ctx, view, message, write_to_cache, wait_for_dream, payload)
        self.init_url: str = init_url
        self.model: str = model

    def get_command(self):
        command = f'/identify init_url:{self.init_url} model:{self.model}'
        return command

# the queue object for discord uploads
class UploadObject:
    def __init__(self, queue_object, content, embed = None, ephemeral = None, files = None, view = None, delete_after = None):
        self.queue_object: DreamObject = queue_object
        self.content: str = content
        self.embed: discord.Embed = embed
        self.ephemeral: bool = ephemeral
        self.files: list[discord.File] = files
        self.view: discord.ui.View = view
        self.delete_after: float = delete_after
        self.is_uploading = False
        self.upload_attempts = 0

def get_guild(ctx: discord.ApplicationContext | discord.Interaction | discord.Message):
    try:
        if type(ctx) is discord.ApplicationContext:
            if ctx.guild_id:
                return '% s' % ctx.guild_id
            else:
                return 'private'
        elif type(ctx) is discord.Interaction:
            return '% s' % ctx.guild.id
        elif type(ctx) is discord.Message:
            return '% s' % ctx.guild.id
        else:
            return 'private'
    except:
        return 'private'

def get_user(ctx: discord.ApplicationContext | discord.Interaction | discord.Message):
    try:
        if type(ctx) is discord.ApplicationContext:
            return ctx.author
        elif type(ctx) is discord.Interaction:
            return ctx.user
        elif type(ctx) is discord.Message:
            return ctx.author
        else:
            return ctx.author
    except:
        return None

def find_between(s: str, first: str, last: str):
    try:
        start = s.index(first) + len(first)
        end = s.index(last, start)
        return s[start:end]
    except ValueError:
        return ''

def remove_hash(s: str):
    try:
        if s.endswith(']'):
            if s[len(s)-9] == '[':
                s = s[:-9].strip()
            elif s[len(s)-12] == '[':
                s = s[:-12].strip()
    except:
        pass
    return s