import discord
from discord.ext import commands
import re
import json
import os

class NSFWLinkFilter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Load the config once on startup
        self.config_path = "server_config.json"
        self.config = self.load_config()
        print(self.config)

        # NSFW-like keywords
        self.keywords = [
            "porn", "sex", "fuck", "nude", "boob", "dick", "pussy", "jerk", "xxx", "hentai", "onlyfans", "nsfw", "cum", "cumshot", "cumshots", "anal"
        ]

        # Regex to detect URLs
        self.link_pattern = re.compile(r"(https?://[^\s]+)", re.IGNORECASE)

    # --- Utility functions ---
    def load_config(self):
        if not os.path.exists(self.config_path):
            print(f"[!] Config file not found: {self.config_path}")
            return {}

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"[+] Loaded config with {len(data)} guilds.")
                return data
        except json.JSONDecodeError as e:
            print(f"[!] Failed to parse config.json: {e}")
            return {}

    def get_alert_channel(self, guild_id: int):
        guild_id = str(guild_id)
        data = self.config.get(guild_id)
        if data and "alert_channel_id" in data:
            return data["alert_channel_id"]
        return None

    # --- Main event ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        content = message.content.lower()
        urls = self.link_pattern.findall(content)
        if not urls:
            return

        # Check each URL
        for url in urls:
            # Whitelisted safe sites
            if any(site in url for site in [
                "discord", "youtube", "tenor", "imgur", "reddit", "x.com", "gyazo"
            ]):
                continue

            dash_count = url.count("-")
            found_keywords = [kw for kw in self.keywords if kw in url]
            multiple_keywords = len(found_keywords) >= 2

            # Heuristic: suspicious if 2+ dashes AND 2+ keywords
            if dash_count >= 2 and multiple_keywords:
                try:
                    await message.delete()
                except discord.Forbidden:
                    pass
                except discord.NotFound:
                    return

                # Log it using server-specific channel
                await self.log_detection(message, url, found_keywords)
                return  # stop after first detected URL

    async def log_detection(self, message, url, keywords):
        alert_channel_id = self.get_alert_channel(message.guild.id)
        if not alert_channel_id:
            return  # no alert channel set for this guild

        log_channel = message.guild.get_channel(alert_channel_id)
        if not log_channel:
            return  # channel missing/deleted

        embed = discord.Embed(
            title="🚫 Suspicious Link Removed",
            description=(
                f"**User:** {message.author.mention}\n"
                f"**Channel:** {message.channel.mention}\n"
                f"**Link:** `{url}`\n"
                f"**Keywords:** {', '.join(keywords)}"
            ),
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=message.author.display_avatar.url)
        await log_channel.send(embed=embed)

def setup(bot):
    bot.add_cog(NSFWLinkFilter(bot))