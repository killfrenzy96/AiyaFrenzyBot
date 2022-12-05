import time
import requests
import threading
import discord

# WebUI access point
class WebUI:
    def __init__(self, url: str, username: str, password: str, api_user: str, api_pass: str, api_auth = False, gradio_auth = False):
        self.online = False
        self.url = url

        self.username = username
        self.password = password
        self.gradio_auth = gradio_auth

        self.api_user = api_user
        self.api_pass = api_pass
        self.api_auth = api_auth

        self.reconnect_thread: threading.Thread = threading.Thread()

    # check connection to WebUI and authentication
    def check_status(self):
        try:
            response = requests.get(self.url + '/sdapi/v1/cmd-flags')
            # lazy method to see if --api-auth commandline argument is set
            if response.status_code == 401:
                self.api_auth = True
                # lazy method to see if --api-auth credentials are set
                if (not self.api_pass) or (not self.api_user):
                    print(f'> Web UI API at {self.url} rejected me! If using --api-auth, '
                          'please check your .env file for APIUSER and APIPASS values.')
                    self.online = False
                    return False
            # lazy method to see if --api commandline argument is not set
            elif response.status_code == 404:
                print(f'> Web UI API at {self.url} is unreachable! Please check Web UI COMMANDLINE_ARGS for --api.')
                self.online = False
                return False
        except:
            print(f'> Connection failed to Web UI at {self.url}')
            self.online = False
            return False

        try:
            s = requests.Session()
            if self.api_auth:
                s.auth = (self.api_user, self.api_pass)

            response_data = s.get(self.url + '/sdapi/v1/cmd-flags').json()
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
            # else:
            #     s.post(self.url + '/login', timeout=60)
        except Exception as e:
            print(f'> Connection failed to Web UI at {self.url}')
            self.online = False
            return False

        self.online = True
        return True

    # return a request session
    def get_session(self):
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
            #     else:
            #         s.post(self.url + '/login', timeout=5)
            # else:
            #     s.get(self.url + '/sdapi/v1/cmd-flags', timeout=5)
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
            print(f'> Checking connection to WebUI at {self.url}')
            while self.check_status() == False:
                print(f'> - Error: Retrying in 15 seconds...')
                time.sleep(15)
            print(f'> Connected to {self.url}')

        if self.reconnect_thread.is_alive() == False:
            self.reconnect_thread = threading.Thread(target=run, daemon=True)
            self.reconnect_thread.start()

    # block code until connected to the WebUI
    def connect_blocking(self):
        if self.reconnect_thread.is_alive() == False:
            self.connect()
        self.reconnect_thread.join()

    # force a connection check
    def reconnect(self):
        if self.reconnect_thread.is_alive() == False:
            print(f'> Connection ended to Web UI at {self.url}')
            self.online = False
            self.connect()


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
