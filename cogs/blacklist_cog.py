import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup
import json

GLOBAL_BLACKLISTED_DOMAINS = ["grabify.link", "iplogger.org", "bmwforum.co", "yip.su", "pornhub.com"]
GLOBAL_BLACKLISTED_KEYWORDS = ["Free Nitro", "nitro giveaway", "free crypto", "btc giveaway"]

blacklist = SlashCommandGroup("blacklist", "Manage the server blacklist")
blacklisted_keyword = blacklist.create_subgroup("keyword", "Manage keyword blacklist")

def load_config():
    with open("server_config.json", "r") as f:
        return json.load(f)

def save_config(config):
    with open("server_config.json", "w") as f:
        json.dump(config, f, indent=4)

class BlacklistCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_application_command(blacklist)

    # Domain commands
    @blacklist.command(name="add", description="Add a domain to the blacklist")
    async def add_blacklist(self, ctx, domain: str):
        config = load_config()
        guild_id = str(ctx.guild.id)
        guild_config = config.get(guild_id, {})
        blacklisted = guild_config.setdefault("blacklisted_domains", [])

        app_info = await self.bot.application_info()
        admin_role_id = guild_config.get("admin_role_id")
        admin_role = ctx.guild.get_role(admin_role_id) if admin_role_id else None
        has_admin_role = admin_role in ctx.user.roles if admin_role else False
        is_owner = ctx.user.id == app_info.owner.id

        if not (has_admin_role or is_owner):
            return await ctx.respond("🚫 You do not have permission to use this command.", ephemeral=True)

        if domain in GLOBAL_BLACKLISTED_DOMAINS:
            return await ctx.respond(f"🚫 `{domain}` is globally blacklisted.", ephemeral=True)
        if domain in blacklisted:
            return await ctx.respond(f"🚫 `{domain}` is already blacklisted for this server.", ephemeral=True)

        blacklisted.append(domain)
        save_config(config)
        await ctx.respond(f"✅ `{domain}` added to blacklist.", ephemeral=True)

    @blacklist.command(name="remove", description="Remove a domain from the blacklist")
    async def remove_blacklist(self, ctx, domain: str):
        config = load_config()
        guild_id = str(ctx.guild.id)
        guild_config = config.get(guild_id, {})
        blacklisted = guild_config.setdefault("blacklisted_domains", [])

        app_info = await self.bot.application_info()
        admin_role_id = guild_config.get("admin_role_id")
        admin_role = ctx.guild.get_role(admin_role_id) if admin_role_id else None
        has_admin_role = admin_role in ctx.user.roles if admin_role else False
        is_owner = ctx.user.id == app_info.owner.id

        if not (has_admin_role or is_owner):
            return await ctx.respond("🚫 You do not have permission to use this command.", ephemeral=True)

        if domain in GLOBAL_BLACKLISTED_DOMAINS:
            return await ctx.respond(f"🚫 Cannot remove global blacklist domain `{domain}`.", ephemeral=True)
        if domain not in blacklisted:
            return await ctx.respond(f"🚫 `{domain}` is not blacklisted for this server.", ephemeral=True)

        blacklisted.remove(domain)
        save_config(config)
        await ctx.respond(f"✅ `{domain}` removed from blacklist.", ephemeral=True)

    # Keyword commands
    @blacklisted_keyword.command(name="add", description="Add a keyword to the blacklist")
    async def keyword_blacklist(self, ctx, keyword: str):
        config = load_config()
        guild_id = str(ctx.guild.id)
        guild_config = config.get(guild_id, {})
        blacklisted = guild_config.setdefault("blacklisted_keywords", [])

        app_info = await self.bot.application_info()
        admin_role_id = guild_config.get("admin_role_id")
        admin_role = ctx.guild.get_role(admin_role_id) if admin_role_id else None
        has_admin_role = admin_role in ctx.user.roles if admin_role else False
        is_owner = ctx.user.id == app_info.owner.id

        if not (has_admin_role or is_owner):
            return await ctx.respond("🚫 You do not have permission to use this command.", ephemeral=True)

        if keyword in GLOBAL_BLACKLISTED_KEYWORDS or keyword in blacklisted:
            return await ctx.respond(f"🚫 `{keyword}` is already blacklisted.", ephemeral=True)

        blacklisted.append(keyword)
        save_config(config)
        await ctx.respond(f"✅ `{keyword}` added to keyword blacklist.", ephemeral=True)

    @blacklisted_keyword.command(name="remove", description="Remove a keyword from the blacklist")
    async def remove_keyword_blacklist(self, ctx, keyword: str):
        config = load_config()
        guild_id = str(ctx.guild.id)
        guild_config = config.get(guild_id, {})
        blacklisted = guild_config.setdefault("blacklisted_keywords", [])

        app_info = await self.bot.application_info()
        admin_role_id = guild_config.get("admin_role_id")
        admin_role = ctx.guild.get_role(admin_role_id) if admin_role_id else None
        has_admin_role = admin_role in ctx.user.roles if admin_role else False
        is_owner = ctx.user.id == app_info.owner.id

        if not (has_admin_role or is_owner):
            return await ctx.respond("🚫 You do not have permission to use this command.", ephemeral=True)

        if keyword in GLOBAL_BLACKLISTED_KEYWORDS:
            return await ctx.respond(f"🚫 Cannot remove global blacklist keyword `{keyword}`.", ephemeral=True)
        if keyword not in blacklisted:
            return await ctx.respond(f"🚫 `{keyword}` is not blacklisted for this server.", ephemeral=True)

        blacklisted.remove(keyword)
        save_config(config)
        await ctx.respond(f"✅ `{keyword}` removed from keyword blacklist.", ephemeral=True)

def setup(bot):
    bot.add_cog(BlacklistCog(bot))
