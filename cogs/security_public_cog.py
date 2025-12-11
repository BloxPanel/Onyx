import discord
from discord.ext import commands
from discord.commands import slash_command
import re
import tldextract
import base64
import time
import os
import aiohttp
import json
import random
from datetime import datetime

CONFIG_FILE = "server_config.json"

# --- JSON helpers ---
def load_json(file):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return {}

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

# --- Regex for masked [text](url) and raw URLs ---
URL_REGEX = re.compile(
    r'\[.*?\]\((https?://[^\s]+)\)|'  # masked link
    r'(https?://[^\s]+)'              # raw url
)

def encode_url_to_vt_id(url):
    return base64.urlsafe_b64encode(url.encode("utf-8")).decode().rstrip("=")

class PublicSecurity(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.GLOBAL_BLACKLISTED_DOMAINS = ["grabify.link", "iplogger.org", "bmwforum.co", "yip.su", "pornhub.com"]
        self.GLOBAL_BLACKLISTED_KEYWORDS = ["Free Nitro", "nitro giveaway", "free crypto", "btc giveaway", "free robux", "Robux giveaway"]
        self.GLOBAL_ALLOWED_DOMAINS = ["youtube.com", "x.com", "tiktok.com"]
        self.VT_API_KEY = os.getenv("VT_API_KEY")

        # ✅ Add these lines:
        self.link_cache = {}  # stores cached VirusTotal results
        self.CACHE_EXPIRY = 300  # cache duration in seconds (5 minutes)
        self.tips_index = 0  # tracks which tip to show next
        tips_file = "security_tips.json"
        with open(tips_file, "r", encoding="utf-8") as f:
            self.security_tips = json.load(f)

    def load_config(self):
        return load_json(CONFIG_FILE)

    def get_alert_channel(self, guild: discord.Guild):
        config = self.load_config()
        alert_id = config.get(str(guild.id), {}).get("alert_channel_id")
        return guild.get_channel(alert_id) if alert_id else None

    def get_admin_role(self, guild: discord.Guild):
        config = self.load_config()
        role_id = config.get(str(guild.id), {}).get("admin_role_id")
        return guild.get_role(role_id) if role_id else None

    async def get_vt_url_report(self, url: str):
        if not self.VT_API_KEY:
            return None
        now = time.time()
        cache_entry = self.link_cache.get(url)
        if cache_entry:
            ts, data = cache_entry
            if now - ts < self.CACHE_EXPIRY:
                return data
        vt_id = encode_url_to_vt_id(url)
        endpoint = f"https://www.virustotal.com/api/v3/urls/{vt_id}"
        headers = {"x-apikey": self.VT_API_KEY}
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(endpoint, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.link_cache[url] = (now, data)
                        return data
                    self.link_cache[url] = (now, None)
                    return None
        except Exception as e:
            print(f"VirusTotal request failed for {url}: {e}")
            return None

    @slash_command(name="checklink", description="Check if a link is malicious using VirusTotal.")
    async def checklink(self, ctx, url: str):
        await ctx.defer()

        # --- Basic URL validation ---
        if not re.match(r"https?://", url):
            await ctx.respond("⚠️ Please provide a valid URL (starting with http:// or https://).", ephemeral=True)
            return

        try:
            data = await self.get_vt_url_report(url)

            if not data:
                await ctx.respond("❌ Failed to fetch results from VirusTotal.", ephemeral=True)
                return

            # --- Parse VirusTotal response ---
            attributes = data.get("data", {}).get("attributes", {})
            analysis_results = attributes.get("last_analysis_results", {})

            malicious_vendors = []
            suspicious_vendors = []
            harmless_count = 0
            undetected_count = 0

            for vendor, info in analysis_results.items():
                category = info.get("category")
                if category == "malicious":
                    malicious_vendors.append(vendor)
                elif category == "suspicious":
                    suspicious_vendors.append(vendor)
                elif category == "harmless":
                    harmless_count += 1
                elif category == "undetected":
                    undetected_count += 1

            total_vendors = len(analysis_results)

            embed = discord.Embed(
                title="🧪 VirusTotal Scan Results",
                description=f"**URL:** {url}\n**Total vendors scanned:** {total_vendors}",
                color=discord.Color.red() if malicious_vendors or suspicious_vendors else discord.Color.green()
            )

            embed.add_field(name="🦠 Malicious", value=f"{len(malicious_vendors)} ({', '.join(malicious_vendors)})" if malicious_vendors else "0", inline=False)
            embed.add_field(name="⚠️ Suspicious", value=f"{len(suspicious_vendors)} ({', '.join(suspicious_vendors)})" if suspicious_vendors else "0", inline=False)
            embed.add_field(name="✅ Harmless", value=str(harmless_count), inline=True)
            embed.add_field(name="❔ Undetected", value=str(undetected_count), inline=True)
            embed.set_footer(text="Data provided by VirusTotal")

            vt_link = attributes.get("permalink") or f"https://www.virustotal.com/gui/url/{data['data']['id']}"
            embed.add_field(name="🔗 Full Report", value=f"[View on VirusTotal]({vt_link})", inline=False)

            await ctx.respond(embed=embed)

        except Exception as e:
            await ctx.respond(f"❌ An error occurred while checking the link: `{e}`", ephemeral=True)

    @slash_command(name="securitytips", description="Get a security tip (rotates sequentially).")
    async def securitytips(self, ctx):
        await ctx.defer()

        try:
            tip = self.security_tips[self.tips_index]

            # increment index and loop back if at the end
            self.tips_index = (self.tips_index + 1) % len(self.security_tips)

            embed = discord.Embed(
                title="🔒 Security Tip",
                description=tip,
                color=discord.Color.blue()
            )
            await ctx.respond(embed=embed)

        except Exception as e:
            await ctx.respond(f"❌ Failed to fetch security tip: `{e}`", ephemeral=True)

    @slash_command(name="report", description="Report a link to server moderators for review.")
    async def report(self, ctx, link: str):
        await ctx.defer(ephemeral=True)  # optional: make initial response ephemeral

        # Create the embed
        embed = discord.Embed(
            title="New Reported Link",
            description=(
                f"<@{ctx.author.id}> has reported the link `{link}` as suspicious.\n"
                "Use `/checklink` or VirusTotal to verify the link against multiple security vendors."
            ),
            color=discord.Color.blue()
        )

        # Get the alert channel
        alert_channel = self.get_alert_channel(ctx.guild)
        admin_role = self.get_admin_role(ctx.guild)
        if alert_channel:
            if admin_role:
                await alert_channel.send(content=admin_role.mention, embed=embed)
            else:
                await alert_channel.send(embed=embed)
            await ctx.respond("✅ Your report has been sent to the moderators.", ephemeral=True)
        else:
            await ctx.respond("❌ The Alert Channel is not set up for this server, meaning you cannot report a link at this time. DM a server moderator to have them set it up.", ephemeral=True)
    

    # Prefix Command

    @commands.command(name="ping", description="Get the bot's ping.")
    async def ping_prefix(self, ctx: commands.Context):
        await self.send_ping_embed(ctx, self.bot)

    # Slash Command

    @slash_command(name="ping", description="Get the bot's ping")
    async def ping(self, ctx: discord.ApplicationContext):
        await self.send_ping_embed(ctx, self.bot)

    # Shared Embed
    async def send_ping_embed(self, ctx, bot: commands.Bot):
        is_slash = hasattr(ctx, "interaction") and ctx.interaction is not None
        start = time.perf_counter()

        if is_slash:
            # Defer the slash command (optional ephemeral)
            await ctx.defer(ephemeral=True)

            # Wait a tiny bit to measure round-trip
            end = time.perf_counter()
            latency_ms = round((end - start) * 1000)

            embed = discord.Embed(
                title="🏓 Pong!",
                description=(
                    f"Message latency: `{latency_ms} ms`\n"
                ),
                color=discord.Color.green()
            )

            # Edit the deferred interaction response
            await ctx.interaction.edit_original_response(embed=embed)

        else:
            # Prefix command: normal send
            msg = await ctx.send("🏓 Pinging...")
            end = time.perf_counter()
            latency_ms = round((end - start) * 1000)

            embed = discord.Embed(
                title="🏓 Pong!",
                description=(
                    f"Message latency: `{latency_ms} ms`\n"
                ),
                color=discord.Color.green()
            )
            await msg.edit(content=None, embed=embed)

    # --- Prefix Command ---
    @commands.command(name="whois", aliases=["w"])
    async def whois_prefix(self, ctx, member: discord.Member = None):
        await self.send_whois_embed(ctx, member or ctx.author)

    # --- Slash Command ---
    @slash_command(name="whois", description="Shows info about a user.")
    async def whois_slash(self, ctx, member: discord.Member = None):
        await ctx.defer()
        await self.send_whois_embed(ctx, member or ctx.author)

    # --- Shared Embed Function ---
    async def send_whois_embed(self, ctx, member):
        embed = discord.Embed(
            title=f"{member}",
            color=member.color,
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(name="Nickname", value=member.nick or "None", inline=True)
        embed.add_field(name="Account Created", value=member.created_at.strftime("%b %d, %Y"), inline=True)
        embed.add_field(name="Joined Server", value=member.joined_at.strftime("%b %d, %Y") if member.joined_at else "N/A", inline=True)
        embed.add_field(name="Top Role", value=member.top_role.mention, inline=True)
        embed.add_field(name="Bot?", value="✅ Yes" if member.bot else "❌ No", inline=True)

        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(PublicSecurity(bot))
