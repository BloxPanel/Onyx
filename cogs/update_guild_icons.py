# cogs/update_guild_icons.py
import discord
from discord.ext import commands
import json
import os

CONFIG_FILE = "server_config.json"

class UpdateGuildIcons(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def update_icons(self):
        """Update server_config.json with name, icon hash, and owner_id for each guild"""
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
        else:
            config = {}

        for guild in self.bot.guilds:
            gid = str(guild.id)
            if gid not in config:
                config[gid] = {}
            config[gid]["name"] = guild.name
            config[gid]["icon"] = guild.icon.key if guild.icon else None
            config[gid]["owner_id"] = guild.owner_id  # Save the server owner's ID

        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
        print("✅ Updated server_config.json with names, icon hashes, and owner IDs")

    @commands.Cog.listener()
    async def on_ready(self):
        await self.update_icons()

def setup(bot):
    bot.add_cog(UpdateGuildIcons(bot))
