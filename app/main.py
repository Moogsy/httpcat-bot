"""
httpcat - Discord bot
Copyright (C) 2020 - Saphielle Akiyama

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import os
import io
import asyncio
import random

from typing import Union

import aiohttp
import discord
from discord.ext import commands

import config

# NOTE: This whole thing is made as a joke

VALID_RANGES = (
    (100, 101),
    (200, 207),
    (300, 307),
    (400, 451),
    (499, 511),
    (599, 599),
)

class Bot(commands.Bot):
    def __init__(self, **options):
        super().__init__(**options)
        self.cache = {}
        self.support_server_url = options.pop('support_server_url')
        self.source_url = options.pop('source_url')

        # _before_invoke is set to None somewhere in the superclass
        self._before_invoke = self.before_invoke

        CooldownMapping = commands.CooldownMapping
        BucketType = commands.BucketType
        self.cds = [
            CooldownMapping.from_cooldown(5, 10, BucketType.member),
            CooldownMapping.from_cooldown(500, 3600, BucketType.default),
        ]
        self.__token = options.pop('token')
        os.environ['JISHAKU_NO_UNDERSCORE'] = 'True'
        self.load_extension('jishaku')

    async def connect(self, *args, **kwargs):
        """Dodging depreciation warnings"""
        self._session = aiohttp.ClientSession()
        return await super().connect(*args, **kwargs)

    @property
    def session(self) -> aiohttp.ClientSession:
        """Let's avoid accidentally re-assigning it"""
        return self._session

    def run(self, *args, **kwargs):
        """Accessing the config twice would be meh"""
        return super().run(self.__token, *args, **kwargs)
    
    async def before_invoke(self, ctx: commands.Context):
        """Proper rate limiting to avoid abuse"""
        await ctx.trigger_typing()

        for cd in self.cds:
            bucket = cd.get_bucket(ctx.message)
            if retry_after := bucket.update_rate_limit():
                raise commands.CommandOnCooldown(cd, retry_after)
    
    async def on_command_error(self, ctx: commands.Context, error: Exception):
        """Basic error handling"""
        error = getattr(error, "original", error)

        if isinstance(error, commands.CommandNotFound):
            msg = ctx.message
            msg.content = f"http {msg.content}"
            return await bot.process_commands(msg)
        
        if isinstance(error, commands.CommandOnCooldown):
            if ctx.command.name == "http":
                return
            elif (ctx.command.name != "help"
                and error.retry_after < 3):
                await asyncio.sleep(error.retry_after)
                return await ctx.reinvoke()

        await ctx.send("{0.__class__.__name__}: {0}".format(error))
        return await super().on_command_error(ctx, error)
    
    async def close(self, *args, **kwargs):
        await self.session.close()
        return await super().close(*args, **kwargs)

class UsefulHelp(commands.HelpCommand):
    def __init__(self):
        command_attrs = {"cooldown": commands.Cooldown(1, 10, commands.BucketType.member)}
        super().__init__(command_attrs=command_attrs)

    def get_command_signature(self, command: commands.Command) -> str:
        if command.name == 'http':
            return f"{self.clean_prefix}{command.signature}"
        return "{0.clean_prefix}{1.qualified_name} {1.signature}".format(self, command)

    async def send_embed(self, embed: discord.Embed) -> discord.Message:
        destination = self.get_destination()

        bot = self.context.bot
        invite_url = discord.utils.oauth_url(bot.user.id)

        links = []
        links.append(f"[Invite]({invite_url})")
        links.append(f"[Support server]({bot.support_server_url})")
        links.append(f"[Source]({bot.source_url})")

        embed.add_field(name="Useful links", value=" | ".join(links))
        
        return await destination.send(embed=embed)

    async def send_all_help(self, *args, **kwargs):
        """Takes over all send_x_help that has multiple commands"""
        all_commands = [c for c in self.context.bot.commands if c.name in {"http", "random"}]
        embed = discord.Embed(title="Help")
        embed.color = discord.Color.from_hsv(random.random(), random.uniform(.75, .95), 1)

        for command in all_commands:
            name = self.get_command_signature(command)
            embed.add_field(name=name, value=command.help, inline=False)

        return await self.send_embed(embed)

    send_bot_help = send_cog_help = send_group_help = send_all_help

    async def send_command_help(self, command: commands.Command):
        """Just one command"""
        embed = discord.Embed()
        embed.title = self.get_command_signature(command)
        embed.add_field(name="description", value=command.help)

        if aliases := "\n-".join(command.aliases):
            embed.add_field(name="aliases", value='-' + aliases)

        return await self.send_embed(embed)

bot = Bot(**config.PARAMS, help_command=UsefulHelp())

@bot.command()
async def http(ctx: commands.Context, *, code: Union[int, str] = None):
    """Shows the corresponding http cat image given a status code"""
    if code is None:
        code = 400
    if isinstance(code, str):
        code = 422

    if not (img := bot.cache.get(code)):
        async with bot.session.get(f"https://http.cat/{code}.jpg") as resp:
            bytes_img = await resp.read()
            img = io.BytesIO(bytes_img)

        bot.cache[code] = img

    img.seek(0)
    file = discord.File(img, filename=f"{code}.jpg")
    await ctx.send(file=file)

@http.error
async def http_error(ctx: commands.Context, error: Exception):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.invoke(http, code=429)

@bot.command(name="random")
async def random_(ctx: commands.Context):
    """Shows a random http cat"""
    code = random.randint(*random.choice(VALID_RANGES))
    return await http(ctx, code=code)

bot.run()

