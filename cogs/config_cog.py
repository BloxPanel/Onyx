import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup
import json
import os
from discord.ui import InputText, View, Select, Button

CONFIG_FILE = "server_config.json"

# --- JSON helpers ---
def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

def save_guild_config(bot, guild_id: int, guild_config: dict):
    """Save guild config to JSON and update name/icon automatically."""
    config = load_config()
    guild = bot.get_guild(guild_id)
    if guild:
        guild_config["name"] = guild.name
        guild_config["icon"] = guild.icon.url if guild.icon else None
    config[str(guild_id)] = guild_config
    save_config(config)

# --- Modal classes ---
class AddPermModal(discord.ui.Modal):
    def __init__(self, guild_id: int):
        super().__init__(title="Add Dangerous Permission")
        self.guild_id = guild_id
        self.perm_input = InputText(label="Permission Name", placeholder="e.g., manage_webhooks")
        self.add_item(self.perm_input)

    async def callback(self, interaction: discord.Interaction):
        perm_name = self.perm_input.value.strip().lower()
        config = load_config()
        guild_config = config.setdefault(str(self.guild_id), {})
        dangerous_perms = set(guild_config.get("dangerous_perms", [
            "administrator","ban_members","kick_members","manage_guild","manage_roles","manage_webhooks"
        ]))
        dangerous_perms.add(perm_name)
        guild_config["dangerous_perms"] = list(dangerous_perms)
        save_guild_config(interaction.client, self.guild_id, guild_config)
        await interaction.response.send_message(f"✅ Added `{perm_name}` to dangerous permissions.", ephemeral=True)

class RemovePermModal(discord.ui.Modal):
    def __init__(self, guild_id: int):
        super().__init__(title="Remove Dangerous Permission")
        self.guild_id = guild_id
        self.perm_input = InputText(label="Permission Name", placeholder="e.g., manage_webhooks")
        self.add_item(self.perm_input)

    async def callback(self, interaction: discord.Interaction):
        perm_name = self.perm_input.value.strip().lower()
        config = load_config()
        guild_config = config.setdefault(str(self.guild_id), {})
        dangerous_perms = set(guild_config.get("dangerous_perms", []))
        dangerous_perms.discard(perm_name)
        guild_config["dangerous_perms"] = list(dangerous_perms)
        save_guild_config(interaction.client, self.guild_id, guild_config)
        await interaction.response.send_message(f"✅ Removed `{perm_name}` from dangerous permissions.", ephemeral=True)

class SetBanThresholdModal(discord.ui.Modal):
    def __init__(self, guild_id: int):
        super().__init__(title="Set Ban Threshold")
        self.guild_id = guild_id
        self.threshold_input = InputText(label="Ban Threshold", placeholder="Number of warnings before ban (1-5)")
        self.add_item(self.threshold_input)

    async def callback(self, interaction: discord.Interaction):
        try:
            threshold = int(self.threshold_input.value.strip())
            if threshold < 1 or threshold > 5:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("⚠️ Invalid number. Must be an integer between 1 and 5.", ephemeral=True)
            return

        config = load_config()
        guild_config = config.setdefault(str(self.guild_id), {})
        guild_config["ban_threshold"] = threshold
        save_guild_config(interaction.client, self.guild_id, guild_config)
        await interaction.response.send_message(f"✅ Ban threshold set to {threshold} warnings.", ephemeral=True)

class SetAdminRoleModal(discord.ui.Modal):
    def __init__(self, guild_id: int):
        super().__init__(title="Set Admin Role")
        self.guild_id = guild_id
        self.role_input = InputText(label="Admin Role ID", placeholder="Paste the role ID here")
        self.add_item(self.role_input)

    async def callback(self, interaction: discord.Interaction):
        try:
            role_id = int(self.role_input.value.strip())
        except ValueError:
            await interaction.response.send_message("⚠️ Invalid role ID.", ephemeral=True)
            return

        config = load_config()
        guild_config = config.setdefault(str(self.guild_id), {})
        guild_config["admin_role_id"] = role_id
        save_guild_config(interaction.client, self.guild_id, guild_config)
        await interaction.response.send_message(f"✅ Admin role set to <@&{role_id}>", ephemeral=True)

class SetAlertChannelModal(discord.ui.Modal):
    def __init__(self, guild_id: int):
        super().__init__(title="Set Alert Channel")
        self.guild_id = guild_id
        self.channel_input = InputText(label="Channel ID", placeholder="Paste the channel ID here")
        self.add_item(self.channel_input)

    async def callback(self, interaction: discord.Interaction):
        try:
            channel_id = int(self.channel_input.value.strip())
        except ValueError:
            await interaction.response.send_message("⚠️ Invalid channel ID.", ephemeral=True)
            return

        config = load_config()
        guild_config = config.setdefault(str(self.guild_id), {})
        guild_config["alert_channel_id"] = channel_id
        save_guild_config(interaction.client, self.guild_id, guild_config)
        await interaction.response.send_message(f"✅ Alert channel set to <#{channel_id}>", ephemeral=True)

class SetAllowedPingRoleModal(discord.ui.Modal):
    def __init__(self, guild_id: int):
        super().__init__(title="Set Allowed Ping Role")
        self.guild_id = guild_id
        self.role_input = InputText(label="Allowed Ping Role ID", placeholder="Paste the role ID here")
        self.add_item(self.role_input)

    async def callback(self, interaction: discord.Interaction):
        try:
            role_id = int(self.role_input.value.strip())
        except ValueError:
            await interaction.response.send_message("⚠️ Invalid role ID.", ephemeral=True)
            return

        config = load_config()
        guild_config = config.setdefault(str(self.guild_id), {})
        guild_config["allowed_ping_role_id"] = role_id
        save_guild_config(interaction.client, self.guild_id, guild_config)
        await interaction.response.send_message(f"✅ Allowed ping role set to <@&{role_id}>", ephemeral=True)

# --- Dropdown / View ---
class ConfigDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Set Admin Role", description="Configure the admin role."),
            discord.SelectOption(label="Set Alert Channel", description="Choose a channel for alerts."),
            discord.SelectOption(label="Set Allowed Ping Role", description="Who can use @everyone/@here."),
            discord.SelectOption(label="Manage Dangerous Permissions", description="View/add/remove dangerous perms."),
            discord.SelectOption(label="Set Ban Threshold", description="Set warnings before auto-ban")
        ]
        super().__init__(placeholder="Choose what to configure…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selection = self.values[0]
        guild_id = str(interaction.guild.id)
        config = load_config()
        guild_config = config.setdefault(guild_id, {})

        if selection == "Manage Dangerous Permissions":
            perms = set(guild_config.get("dangerous_perms", [
                "administrator","ban_members","kick_members","manage_guild","manage_roles","manage_webhooks"
            ]))
            embed = discord.Embed(
                title="🛡 Dangerous Permissions",
                description=f"Current dangerous permissions:\n`{', '.join(perms)}`",
                color=discord.Color.green()
            )
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Add Perm", style=discord.ButtonStyle.success, custom_id="add_perm"))
            view.add_item(discord.ui.Button(label="Remove Perm", style=discord.ButtonStyle.danger, custom_id="remove_perm"))

            async def button_callback(interaction2: discord.Interaction):
                cid = interaction2.data.get("custom_id")
                if cid == "add_perm":
                    await interaction2.response.send_modal(AddPermModal(interaction.guild.id))
                elif cid == "remove_perm":
                    await interaction2.response.send_modal(RemovePermModal(interaction.guild.id))

            for item in view.children:
                if isinstance(item, discord.ui.Button):
                    item.callback = button_callback

            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        elif selection == "Set Ban Threshold":
            await interaction.response.send_modal(SetBanThresholdModal(interaction.guild.id))
        elif selection == "Set Admin Role":
            await interaction.response.send_modal(SetAdminRoleModal(interaction.guild.id))
        elif selection == "Set Alert Channel":
            await interaction.response.send_modal(SetAlertChannelModal(interaction.guild.id))
        elif selection == "Set Allowed Ping Role":
            await interaction.response.send_modal(SetAllowedPingRoleModal(interaction.guild.id))
        else:
            await interaction.response.send_message(f"🛠️ Feature `{selection}` not implemented yet.", ephemeral=True)

class ConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(ConfigDropdown())

# --- Cog ---
class ConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name="config", description="Configure the bot")
    async def config(self, ctx: discord.ApplicationContext):
        # Check owner/admin
        guild_config = load_config().get(str(ctx.guild.id), {})
        admin_role_id = guild_config.get("admin_role_id")
        if ctx.author.id != ctx.guild.owner_id and (not admin_role_id or admin_role_id not in [r.id for r in ctx.author.roles]):
            await ctx.respond("❌ You must be the server owner or have the admin role to configure this bot.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Server Configuration",
            description="Click the button to open config menu.",
            color=discord.Color.blue()
        )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Open Config Menu", style=discord.ButtonStyle.primary, custom_id="open_config"))

        async def button_callback(interaction: discord.Interaction):
            await interaction.response.send_message("🛠️ Select what to configure:", view=ConfigView(), ephemeral=True)

        for item in view.children:
            if isinstance(item, discord.ui.Button):
                item.callback = button_callback

        await ctx.respond(embed=embed, view=view)

    @commands.slash_command(name="view_config", description="View the current server configuration")
    async def view_config(self, ctx: discord.ApplicationContext):
        config_data = load_config()
        guild_config = config_data.get(str(ctx.guild.id), {})

        admin_role = ctx.guild.get_role(guild_config.get("admin_role_id"))
        alert_channel = ctx.guild.get_channel(guild_config.get("alert_channel_id"))
        allowed_ping_role = ctx.guild.get_role(guild_config.get("allowed_ping_role_id"))
        dangerous_perms = guild_config.get("dangerous_perms", [
            "administrator","ban_members","kick_members","manage_guild","manage_roles","manage_webhooks"
        ])
        ban_threshold = guild_config.get("ban_threshold", 3)

        embed = discord.Embed(title="Server Configuration", color=discord.Color.blue())
        embed.add_field(name="Admin Role", value=admin_role.mention if admin_role else "Not set", inline=False)
        embed.add_field(name="Alert Channel", value=alert_channel.mention if alert_channel else "Not set", inline=False)
        embed.add_field(name="Allowed Ping Role", value=allowed_ping_role.mention if allowed_ping_role else "Not set", inline=False)
        embed.add_field(name="Dangerous Permissions", value=", ".join(dangerous_perms), inline=False)
        embed.add_field(name="Ban Threshold", value=str(ban_threshold), inline=False)
        await ctx.respond(embed=embed)

def setup(bot):
    bot.add_cog(ConfigCog(bot))
