import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import json
import sys
import subprocess
import traceback
import asyncio
import datetime
import importlib.util
import time

JOIN_RESTART_FLAG = "join_restart_flag.json"
last_join_restart = 0
JOIN_RESTART_COOLDOWN = 60  # seconds
HIDDEN_COMMANDS = {"captcha_test"}

class CustomHelpCommand(commands.HelpCommand):
    def get_command_signature(self, command):
        try:
            # Prefix commands have .signature
            sig = getattr(command, "signature", None)
            if sig is not None:
                return f"!{command.qualified_name} {sig}"

            # Slash commands (pycord) have .options instead
            if hasattr(command, "options"):
                options = " ".join([f"<{opt.name}>" for opt in getattr(command, "options", [])])
                return f"/{command.qualified_name} {options}"

            # Fallback for any other command types
            return f"{command.qualified_name}"

        except AttributeError:
            # Pycord SlashCommand can raise even inside hasattr()
            return f"/{getattr(command, 'qualified_name', 'unknown')}"

    async def send_bot_help(self, mapping):
        embed = discord.Embed(title="Bot Help", color=discord.Color.blurple())

        for cog, commands in mapping.items():
            if not commands:
                continue

            # Skip hidden or empty cogs
            visible_cmds = [
                self.get_command_signature(cmd)
                for cmd in commands
                if not getattr(cmd, "hidden", False)
                and getattr(cmd, "qualified_name", None) not in {"captcha_test"}  # 👈 filter manually
            ]
            if not visible_cmds:
                continue

            cog_name = cog.qualified_name if cog else "No Category"
            embed.add_field(name=cog_name, value="\n".join(visible_cmds), inline=False)

        await self.context.send(embed=embed)

    async def send_cog_help(self, cog):
        embed = discord.Embed(
            title=f"{cog.qualified_name} Help", color=discord.Color.blurple()
        )
        cmds = [
            self.get_command_signature(cmd)
            for cmd in cog.get_commands()
            if not getattr(cmd, "hidden", False)
        ]
        embed.add_field(name="Commands", value="\n".join(cmds) or "No commands", inline=False)
        await self.context.send(embed=embed)

    async def send_command_help(self, command):
        embed = discord.Embed(
            title=f"{command.qualified_name} Help", color=discord.Color.blurple()
        )
        embed.add_field(
            name="Usage",
            value=self.get_command_signature(command),
            inline=False,
        )
        await self.context.send(embed=embed)


# Load the server config once when the bot starts
with open("server_config.json", "r") as f:
    server_config = json.load(f)

# Load bot mode config
if os.path.exists("bot_mode.json"):
    with open("bot_mode.json", "r") as f:
        bot_mode = json.load(f)
else:
    bot_mode = {"mode": "production"}
    with open("bot_mode.json", "w") as f:
        json.dump(bot_mode, f, indent=4)

MODE = bot_mode.get("mode", "production")  # "production" or "maintenance"

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN_ID")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=CustomHelpCommand())

bot_owner_id = [1227388850574200974]

# --- Helper to load all cogs synchronously ---
def load_all_cogs():
    cogs = [
        "cogs.security_cog",
        "cogs.blacklist_cog",
        "cogs.config_cog",
        "cogs.eval_cog",
        "cogs.attachmentscanner_cog",
        "cogs.update_guild_icons",
        "cogs.captcha_cog",
        "cogs.security_public_cog",
        "cogs.nsfw_check"
    ]
    for cog in cogs:
        try:
            bot.load_extension(cog)
            print(f"✅ Loaded {cog}")
        except Exception as e:
            print(f"❌ Failed to load {cog}: {e}")

# --- Global check ---
@bot.check
async def maintenance_check(ctx):
    if MODE == "maintenance" and ctx.author.id not in bot_owner_id:
        await ctx.send("🚧 The bot is under maintenance. Please try again later.", delete_after=5)
        return False  # Block command from running
    return True

# --- Error handler ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        # Silently swallow CheckFailures so they don't print in console
        return
    # Raise other errors normally so you still see actual bugs
    raise error

@bot.event
async def on_guild_join(guild):
    global last_join_restart
    now = time.time()

    # --- Prevent rapid join restarts ---
    if now - last_join_restart < JOIN_RESTART_COOLDOWN:
        print(f"⚠️ Joined {guild.name}, restart skipped (cooldown active).")
        return
    last_join_restart = now

    # --- Check removed servers ---
    REMOVED_FILE = "removed_servers.json"
    try:
        with open(REMOVED_FILE, "r") as f:
            removed = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        removed = []

    if str(guild.id) in removed:
        print(f"⚠️ Attempted rejoin by removed server: {guild.name} ({guild.id})")
        try:
            await guild.leave()
        except Exception as e:
            print(f"❌ Failed to leave {guild.id}: {e}")
        return

    # --- Normal join handling ---
    print(f"🆕 Joined new server: {guild.name} ({guild.id})")

    # Create a join-specific restart flag
    with open(JOIN_RESTART_FLAG, "w") as f:
        json.dump({"reason": "joined_new_server", "guild_id": guild.id}, f)

    print("♻️ Join restart flag created — bot will restart shortly.")

# --- Commands ---
@bot.command(name="addcog", description="Add a new cog.", hidden=True)
async def addcog(ctx, cog_name: str, *, code: str):
    app_info = await bot.application_info()
    if ctx.author.id != app_info.owner.id:
        return await ctx.send("🚫 Only the bot owner can use this command.")

    code = code.strip("` ").strip("python")
    cog_file = f"cogs/{cog_name}.py"

    if os.path.exists(cog_file):
        return await ctx.send("❌ A cog with that name already exists!")

    with open(cog_file, "w", encoding="utf-8") as f:
        f.write(code)

    try:
        bot.load_extension(f"cogs.{cog_name}")
        await ctx.send(f"✅ Cog `{cog_name}` added and loaded successfully!")
    except Exception as e:
        await ctx.send(f"❌ Error loading cog:\n```{e}```")

@bot.command(name="announce", description="Announce a message to server admins.", hidden=True)
async def announce(ctx, mode, *, text: str):
    app_info = await bot.application_info()
    if ctx.author.id != app_info.owner.id:
        return await ctx.send("🚫 Only the bot owner can use this command.")

    if mode == "silent":
        ping_method = ""
    elif mode == "loud":
        ping_method = "@everyone"
    else:
        return await ctx.send("❌ Invalid mode. Use `silent` or `loud`.")

    # Check for an attachment
    image_url = None
    if ctx.message.attachments:
        # Use the first attachment
        image_url = ctx.message.attachments[0].url

    sent_count = 0
    for guild in bot.guilds:
        guild_id = str(guild.id)
        guild_config = server_config.get(guild_id)
        if not guild_config:
            continue

        admin_role_id = guild_config.get("admin_role_id")
        alert_channel_id = guild_config.get("alert_channel_id")

        admin_role = guild.get_role(admin_role_id) if admin_role_id else None
        alert_channel = guild.get_channel(alert_channel_id) if alert_channel_id else None

        if admin_role and alert_channel:
            embed = discord.Embed(
                title="Update from Bot Developers",
                description=text,
                color=discord.Color.green()
            )
            if image_url:
                embed.set_image(url=image_url)  # Attach the image if present

            await alert_channel.send(ping_method, embed=embed)
            sent_count += 1

    await ctx.send(f"✅ Announcement sent to {sent_count} servers' alert channels.")


@bot.command(name="restart", hidden=True)
async def reload(ctx, module_name: str):
    print(bot.extensions)
    if ctx.author.id not in bot_owner_id:
        await ctx.send("You do not have permission to use this command.")
        return
    if module_name == "main":
        await ctx.send("Restarting bot...")
        subprocess.Popen(["python", "main.py"])
        os._exit(0)

# --- New command: Switch mode ---
@bot.command(name="mode", hidden=True)
async def switch_mode(ctx, new_mode: str):
    if ctx.author.id not in bot_owner_id:
        return await ctx.send("🚫 Only the bot owner can use this command.")

    global MODE
    if new_mode.lower() not in ["production", "maintenance"]:
        return await ctx.send("❌ Invalid mode. Use `production` or `maintenance`.")

    MODE = new_mode.lower()

    # Save to bot_mode.json so it persists
    with open("bot_mode.json", "w") as f:
        json.dump({"mode": MODE}, f, indent=4)

    if MODE == "maintenance":
        await ctx.send("🚧 Bot switched to maintenance mode.")
    else:
        await bot.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(type=discord.ActivityType.watching, name="For Malicious Links")
        )
        await ctx.send("✅ Bot switched to production mode.")

# --- 9/11 Announcements ---
events = {
    (8, 46): "At 8:46 AM, American Airlines Flight 11 struck the North Tower of the World Trade Center. Panic set in immediately, and people did not know if it was an accident or not.",
    (9, 3): "At 9:03 AM, United Airlines Flight 175 struck the South Tower of the World Trade Center, marking the events deliberate and planned.",
    (9, 37): "At 9:37 AM, American Airlines Flight 77 crashed into the Pentagon.",
    (9, 59): "At 9:59 AM, the South Tower collapsed, a feat that no one thought was possible.",
    (10, 3): "At 10:03 AM, United Airlines Flight 93 crashed in Pennsylvania after passengers fought back after they learned of the attacks on the towers.",
    (10, 28): 'At 10:28 AM, the North Tower collapsed, marking the last event of the attacks, and beginning the search of "Ground Zero" for survivors.',
    (10, 30): "This very day in 2001, events happened that no one thought were possible, which led to the increase in security at airports and marked the beginning of the Global Attack on Terrorism. \n\n We remember the thousands of innocent people who lost their lives doing their jobs and protecting the country. \nFrom the attacks, 2,977 people died, with thousands more injured. \n As you go about your day, remember the countless first responders rushing into the tower, and thank them for their service. \n\n Please join me in a moment of silence as we remember the fallen. \n\n Thank you."
}

# Hardcoded list of channels to send 9/11 announcements to
sept11_channels = [
    1083980465117077504,  # replace with your channel IDs
    1206768473250857050,
    1259877484065722450,
]


OWNER_ID = 1227388850574200974  # 👈 your Discord ID

@tasks.loop(seconds=10)
async def removal_watcher():
    print("[Watcher] Tick...")

    try:
        with open("pending_removals.json", "r") as f:
            data = f.read().strip()
            pending = json.loads(data) if data else {}
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[Watcher] Failed to load pending_removals.json: {e}")
        pending = {}

    if not pending:
        return

    for sid in list(pending.keys()):
        gid = int(sid)
        guild = bot.get_guild(gid)
        if not guild:
            continue

        # Move the DM interaction into the bot's loop
        bot.loop.create_task(handle_removal(guild))

        del pending[sid]

    with open("pending_removals.json", "w") as f:
        json.dump(pending, f, indent=4)


async def handle_removal(guild):
    """Runs inside the bot's main loop to avoid cross-loop issues."""
    owner_user = bot.get_user(OWNER_ID) or await bot.fetch_user(OWNER_ID)

    # Step 1 — Ask you for a reason
    try:
        await owner_user.send(
            f"🛑 Preparing to remove **{guild.name}** (`{guild.id}`).\n"
            "Please reply with a short reason for removal within 2 minutes."
        )
    except Exception:
        print(f"[Watcher] Could not DM you before removal of {guild.name}")
        return

    def check(msg):
        return msg.author.id == OWNER_ID and msg.channel.type.name == "private"

    try:
        response = await bot.wait_for("message", check=check, timeout=120)
        reason = response.content
    except asyncio.TimeoutError:
        reason = "No reason provided (timed out)."

    # Step 2 — DM the server owner
    if guild.owner:
        try:
            await guild.owner.send(
                f"Hello {guild.owner.mention},\n\n"
                f"My developer has decided to remove **{bot.user.name}** from your server **{guild.name}**.\n\n"
                f"**Reason:** {reason}\n\n"
                "If you believe this was a mistake, please contact the developer directly."
            )
        except Exception as e:
            print(f"[Watcher] Could not DM owner of {guild.name}: {e}")

    # Step 3 — Leave the guild
    try:
        await guild.leave()
        print(f"[Watcher] Successfully left guild: {guild.name}")
    except Exception as e:
        print(f"[Watcher] Error leaving guild {guild.name}: {e}")




# --- Before loop to ensure bot is ready ---
@removal_watcher.before_loop
async def before_removal_watcher():
    await bot.wait_until_ready()
    print("[Watcher] Removal watcher started.")

@tasks.loop(minutes=1)
async def sept11_announce():
    now = datetime.datetime.now()
    if now.month == 9 and now.day == 11:
        key = (now.hour, now.minute)
        if key in events:
            sent_count = 0
            for channel_id in sept11_channels:
                channel = bot.get_channel(channel_id)
                if channel:
                    try:
                        await channel.send(f"🇺🇸 {events[key]}")
                        sent_count += 1
                    except Exception as e:
                        print(f"❌ Could not send message in channel {channel_id}: {e}")
            print(f"✅ Sent 9/11 message to {sent_count} channel(s) at {now.hour}:{now.minute:02d}")


# --- Before loop for your 9/11 task ---
@sept11_announce.before_loop
async def before_sept11_announce():
    await bot.wait_until_ready()


# --- Events ---
# --- Start the loop in on_ready ---
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    if not removal_watcher.is_running():
        removal_watcher.start()

    if MODE == "maintenance":
        await bot.change_presence(status=discord.Status.invisible)
        print("🚧 Bot is in maintenance mode.")
    else:
        await bot.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="For Malicious Links")
        )
        print("✅ Bot is in production mode.")

    # Start the 9/11 announcements loop
    if not sept11_announce.is_running():
        sept11_announce.start()

    if os.path.exists("reload_message.json"):
        try:
            with open("reload_message.json", "r") as f:
                data = json.load(f)
            channel = bot.get_channel(data["channel_id"])
            if channel:
                msg = await channel.fetch_message(data["message_id"])
                await msg.edit(content="✅ Reload complete!")
        except Exception as e:
            print(f"⚠️ Could not edit reload message: {e}")
        finally:
            os.remove("reload_message.json")

# --- Main entrypoint function for launcher ---
async def start_bot():
    load_all_cogs()
    await bot.start(TOKEN)

