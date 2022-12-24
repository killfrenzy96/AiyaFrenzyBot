# AIYA Frenzy Bot

A Discord bot interface for Stable Diffusion. This is a fork of the AIYA Bot. you can find the original [here](https://github.com/Kilvoctu/aiyabot).

<img src=https://user-images.githubusercontent.com/32452698/206232000-34325431-82f2-4280-9f08-f6509068e1da.png width=50% height=50%>

## Setup requirements

- Set up [AUTOMATIC1111's Stable Diffusion AI Web UI](https://github.com/AUTOMATIC1111/stable-diffusion-webui).
  - AIYA is currently tested on commit `685f9631b56ff8bd43bce24ff5ce0f9a0e9af490` of the Web UI.
- Run the Web UI as local host with api (`COMMANDLINE_ARGS= --listen --api`).
- Clone this repo.
- See [Setting up a Discord Bot](https://github.com/killfrenzy96/AiyaFrenzyBot/wiki/Setting-up-a-Discord-Bot) to obtain a Discord bot token.
- Create a text file in your cloned repo called ".env", formatted like so:
```dotenv
# .env
TOKEN = put your bot token here
```
- Run AIYA by running launch.bat (or launch.sh for Linux)

## Usage

To generate an image from text, use the /dream command and include your prompt as the query.

<img src=https://user-images.githubusercontent.com/32452698/208452767-a901aed2-76d8-41f3-8bdb-46ae14e835ab.png>

## Modifications from AIYABOT

This is modified from AIYABOT for my Discord server. The goal of these modifications is to make the bot more useful for refining images.

I have also removed many sources of delay and added support for multiple AUTOMATIC1111 Web UI instances, which allows this bot to generate images significantly faster, especially if multiple people are using this bot.

Interactions have been enhanced to make the bot easier to use for users who do not like to type in commands.

<img src=https://user-images.githubusercontent.com/32452698/208452780-6f068e4d-dcad-4b3a-9016-fd93edc86bf8.png>

### Currently supported options

- negative prompts
- swap model/checkpoint (_see [wiki](https://github.com/killfrenzy96/AiyaFrenzyBot/wiki/Model-Swapping)_)
- sampling steps
- width/height (up to 1024)
- CFG scale
- sampling method
- seed
- img2img
- denoising strength
- batch count
- Web UI styles
- face restoration
- tiling
- high-res fix
- CLIP skip

#### Bonus features

- /draw command - quickly generate quality prompts from a preset.
- /minigame command - play a little prompt guessing game with stable diffusion.
- /identify command - create a caption for your image.
- /stats command - shows how many /dream commands have been used.
- /tips command - basic tips for writing prompts.
- /upscale command - resize your image.
- buttons - certain outputs will contain buttons.
  - 🖋 - edit prompt, then generate a new image with same parameters.
  - 🖼️ - create variation by sending the image to img2img.
  - 🔁 - randomize seed, then generate a new image with same parameters.
  - 🔧 - tweaks, expands extra options to change various parameters.
  - ❌ - deletes the generated image.
- outpainting - use tweaks to quickly setup outpainting for your image.
- inpainting - use the alpha channel of an image as an inpainting mask.

## Notes

- Ensure AIYA has `bot` and `application.commands` scopes when inviting to your Discord server, and intents are enabled.
- [See wiki for optional config variables you can set.](https://github.com/killfrenzy96/AiyaFrenzyBot/wiki/Setup-and-Config)
- [See wiki for notes on swapping models.](https://github.com/killfrenzy96/AiyaFrenzyBot/wiki/Model-Swapping)

## Credits

AIYA only exists thanks to these awesome people:
- AUTOMATIC1111, and all the contributors to the Web UI repo.
  - https://github.com/AUTOMATIC1111/stable-diffusion-webui
- Kilvoctu, for creating the original AIYA Discord bot.
  - https://github.com/Kilvoctu/aiyabot
- harubaru, the foundation for the AIYA Discord bot.
  - https://github.com/harubaru/waifu-diffusion
  - https://github.com/harubaru/discord-stable-diffusion
- gingivere0, for PayloadFormatter class for the original API. Also has a great Discord bot as a no-slash-command alternative.
  - https://github.com/gingivere0/dalebot
- You, for using AIYA and contributing with PRs, bug reports, feedback, and more!