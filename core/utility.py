import time
import requests
import threading
import discord

# WebUI access point
class WebUI:
    def __init__(self, url: str, username: str, password: str, api_user: str, api_pass: str, api_auth = False, gradio_auth = False):
        self.online = False
        self.stopped = False
        self.auth_rejected = False
        self.online_last = None
        self.url = url

        self.username = username
        self.password = password
        self.gradio_auth = gradio_auth

        self.api_user = api_user
        self.api_pass = api_pass
        self.api_auth = api_auth

        self.reconnect_thread: threading.Thread = threading.Thread()

        self.data_models: list[str] = []
        self.sampler_names: list[str] = []
        self.model_tokens = {}
        self.style_names = {}
        self.facefix_models: list[str] = []
        self.upscaler_names: list[str] = []
        self.identify_models: list[str] = []
        self.messages: list[str] = []

    # check connection to WebUI and authentication
    def check_status(self):
        if self.stopped: return False
        try:
            response = requests.get(self.url + '/sdapi/v1/cmd-flags')
            # lazy method to see if --api-auth commandline argument is set
            if response.status_code == 401:
                self.api_auth = True
                # lazy method to see if --api-auth credentials are set
                if (not self.api_pass) or (not self.api_user):
                    print(f'> Web UI API at {self.url} rejected me! If using --api-auth, '
                          'please check your .env file for APIUSER and APIPASS values.')
                    self.auth_rejected = True
                    self.online = False
                    return False
            # lazy method to see if --api commandline argument is not set
            elif response.status_code == 404:
                print(f'> Web UI API at {self.url} is unreachable! Please check Web UI COMMANDLINE_ARGS for --api.')
                self.auth_rejected = True
                self.online = False
                return False
        except:
            print(f'> Connection failed to Web UI at {self.url}')
            self.online = False
            return False

        # check gradio authentication
        if self.stopped: return False
        try:
            s = requests.Session()
            if self.api_auth:
                s.auth = (self.api_user, self.api_pass)

            response_data = s.get(self.url + '/sdapi/v1/cmd-flags', timeout=60).json()
            if response_data['gradio_auth']:
                self.gradio_auth = True
            else:
                self.gradio_auth = False

            if self.gradio_auth:
                login_payload = {
                    'username': self.username,
                    'password': self.password
                }
                s.post(self.url + '/login', data=login_payload, timeout=60)
            else:
                s.post(self.url + '/login', timeout=60)
        except Exception as e:
            print(f'> Gradio Authentication failed for Web UI at {self.url}')
            self.online = False
            return False

        # retrieve instance configuration
        if self.stopped: return False
        try:
            # get stable diffusion models
            # print('Retrieving stable diffusion models...')
            response_data = s.get(self.url + '/sdapi/v1/sd-models', timeout=60).json()
            self.data_models = []
            for sd_model in response_data:
                self.data_models.append(sd_model['title'])
            # print(f'- Stable diffusion models: {len(self.data_models)}')

            # get samplers
            # print('Retrieving samplers...')
            response_data = s.get(self.url + '/sdapi/v1/samplers', timeout=60).json()
            for sampler in response_data:
                self.sampler_names.append(sampler['name'])

            # remove samplers that seem to have some issues under certain cases
            if 'DPM adaptive' in self.sampler_names: self.sampler_names.remove('DPM adaptive')
            if 'PLMS' in self.sampler_names: self.sampler_names.remove('PLMS')
            # print(f'- Samplers count: {len(self.sampler_names)}')

            # get styles
            # print('Retrieving styles...')
            response_data = s.get(self.url + '/sdapi/v1/prompt-styles', timeout=60).json()
            for style in response_data:
                self.style_names[style['name']] = style['prompt'] + '\n' + style['negative_prompt']
            # print(f'- Styles count: {len(self.style_names)}')

            # get face fix models
            # print('Retrieving face fix models...')
            response_data = s.get(self.url + '/sdapi/v1/face-restorers', timeout=60).json()
            for facefix_model in response_data:
                self.facefix_models.append(facefix_model['name'])
            # print(f'- Face fix models count: {len(self.facefix_models)}')

            # get samplers workaround - if AUTOMATIC1111 provides a better way, this should be updated
            # print('Retrieving upscaler models...')
            config = s.get(self.url + '/config/', timeout=60).json()
            try:
                for item in config['components']:
                    try:
                        if item['props']:
                            if item['props']['label'] == 'Upscaler':
                                self.upscaler_names = item['props']['choices']
                    except:
                        pass
            except:
                print('Warning: Could not read config. Upscalers will be missing.')

            print(f'> Loaded data for Web UI at {self.url}')
            print(f'> - Models:{len(self.data_models)} Samplers:{len(self.sampler_names)} Styles:{len(self.style_names)} FaceFix:{len(self.facefix_models)} Upscalers:{len(self.upscaler_names)}')

        except Exception as e:
            print(f'> Retrieve data failed for Web UI at {self.url}')
            self.online = False
            return False

        if self.stopped: return False
        self.online_last = time.time()
        self.auth_rejected = False
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
            elif time.time() > self.online_last + 30:
                s.get(self.url + '/sdapi/v1/cmd-flags', timeout=5)
            self.online_last = time.time()
            self.auth_rejected = False
            self.online = True
            return s

        except Exception as e:
            print(f'> Connection failed to Web UI at {self.url}')
            self.online = False
            self.connect() # attempt to reconnect
            return None

    # continually retry a connection to the webui
    def connect(self):
        def run():
            print(f'> Connecting to WebUI at {self.url}')
            while self.check_status() == False:
                if self.stopped: return None
                if self.auth_rejected:
                    print(f'> - Request rejected! I will not try to reconnect to Web UI at {self.url}')
                    break
                else:
                    print(f'> - Retrying in 30 seconds...')
                time.sleep(30)
                if self.auth_rejected:
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

    # stop all further connections on this web ui
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
        self.highres_fix: bool = highres_fix
        self.clip_skip: int = clip_skip
        self.script: str = script

    def get_command(self):
        command = f'/dream prompt:{self.prompt}'
        if self.negative != '':
            command += f' negative:{self.negative}'
        if self.data_model and self.model_name != 'Default':
            command += f' checkpoint:{self.model_name}'
        command += f' width:{self.width} height:{self.height} steps:{self.steps} guidance_scale:{self.guidance_scale} sampler:{self.sampler} seed:{self.seed}'
        if self.init_url:
            command += f' strength:{self.strength} init_url:{self.init_url}'
        if self.style != None and self.style != 'None':
            command += f' style:{self.style}'
        if self.facefix != None and self.facefix != 'None':
            command += f' facefix:{self.facefix}'
        if self.tiling:
            command += f' tiling:{self.tiling}'
        if self.highres_fix:
            command += f' highres_fix:{self.highres_fix}'
        if self.clip_skip != 1:
            command += f' clip_skip:{self.clip_skip}'
        if self.batch > 1:
            command += f' batch:{self.batch}'
        if self.script:
            command += f' script:{self.script}'
        return command

# the queue object for extras - upscale
class UpscaleObject(DreamObject):
    def __init__(self, cog, ctx, resize, init_url, upscaler_1, upscaler_2, upscaler_2_strength, command,
                 gfpgan, codeformer, upscale_first,
                 view = None, message = None, write_to_cache = False, wait_for_dream: DreamObject = None, payload = None):
        super().__init__(cog, ctx, view, message, write_to_cache, wait_for_dream, payload)
        self.resize: float = resize
        self.init_url: str = init_url
        self.upscaler_1: str = upscaler_1
        self.upscaler_2: str = upscaler_2
        self.upscaler_2_strength: float = upscaler_2_strength
        self.command: str = command
        self.gfpgan: float = gfpgan
        self.codeformer: float = codeformer
        self.upscale_first: bool = upscale_first

# the queue object for identify (interrogate)
class IdentifyObject(DreamObject):
    def __init__(self, cog, ctx, init_url, model, command,
                 view = None, message = None, write_to_cache = False, wait_for_dream: DreamObject = None, payload = None):
        super().__init__(cog, ctx, view, message, write_to_cache, wait_for_dream, payload)
        self.init_url: str = init_url
        self.model: str = model
        self.command: str = command

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
