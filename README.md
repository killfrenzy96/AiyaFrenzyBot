# AIYA Frenzy Bot

A Discord bot interface for Stable Diffusion. This is a fork of the AIYA Bot. you can find the original [here](https://github.com/Kilvoctu/aiyabot).

<img src=https://user-images.githubusercontent.com/32452698/206232000-34325431-82f2-4280-9f08-f6509068e1da.png width=50% height=50%>

# Modifications

This is modified from AIYABOT for my Discord server. The goal of these modifications is to focus on using the bot as a tool to make refined images rather than one off generations. I have also removed many sources of delay which allows this bot to generate images significantly faster, especially if multiple people are using this bot.

There is now support for multiple WebUI instances. You can try using this by adding URL, URL1, URL2, etc to your .env file. This also supports the use of USER1, PASS1, APIUSER1, APIPASS1, etc. AIYA Frenzy Bot will use all WebUI instances to speed up batched or queued image generation.

## Setup requirements

- Set up [AUTOMATIC1111's Stable Diffusion AI Web UI](https://github.com/AUTOMATIC1111/stable-diffusion-webui).
  - AIYA is currently tested on commit `685f9631b56ff8bd43bce24ff5ce0f9a0e9af490` of the Web UI.
- Run the Web UI as local host with api (`COMMANDLINE_ARGS= --listen --api`).
- Clone this repo.
- Create a text file in your cloned repo called ".env", formatted like so:
```dotenv
# .env
TOKEN = put your bot token here
```
- Run AIYA by running launch.bat (or launch.sh for Linux)

## Usage

To generate an image from text, use the /dream command and include your prompt as the query.

<img src=https://user-images.githubusercontent.com/32452698/208234253-1059bc64-ca61-4778-8166-8c59718fc07d.png>

### Currently supported options

- negative prompts
- swap model/checkpoint (_see [wiki](https://github.com/Kilvoctu/aiyabot/wiki/Model-swapping)_)
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

- /minigame command - play a little prompt guessing game with stable diffusion.
- /identify command - create a caption for your image.
- /stats command - shows how many /dream commands have been used.
- /tips command - basic tips for writing prompts.
- /upscale command - resize your image.
- buttons - certain outputs will contain buttons.
  - 🖋 - edit prompt, then generate a new image with same parameters.
  - 🖼️ - create variation by sending the image to img2img.
  - 🔁 - randomize seed, then generate a new image with same parameters.
  - 🔧 - shows extra options to allow quick changes to specific parameters.
  - ❌ - deletes the generated image.

## Notes

- Ensure AIYA has `bot` and `application.commands` scopes when inviting to your Discord server, and intents are enabled.
- [See wiki for optional .env variables you can set.](https://github.com/Kilvoctu/aiyabot/wiki/.env-Settings)
- [See wiki for notes on swapping models.](https://github.com/Kilvoctu/aiyabot/wiki/Model-swapping)

## Credits

AIYA only exists thanks to these awesome people:
- AUTOMATIC1111, and all the contributors to the Web UI repo.
  - https://github.com/AUTOMATIC1111/stable-diffusion-webui
- Kilvoctu, for creating the original AIYA Discord bot.
  - https://github.com/Kilvoctu/aiyabot
- harubaru, the foundation for the AIYA Discord bot.
  - https://github.com/harubaru/waifu-diffusion
  - https://github.com/harubaru/discord-stable-diffusion
- gingivere0, for PayloadFormatter class for the original API. Without that, I'd have given up from the start. Also has a great Discord bot as a no-slash-command alternative.
  - https://github.com/gingivere0/dalebot
- You, for using AIYA and contributing with PRs, bug reports, feedback, and more!