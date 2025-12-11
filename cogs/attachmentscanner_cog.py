import discord, aiohttp, os, json
from oletools.olevba import VBA_Parser
from discord.ext import commands

# Import the same tracker used in security_cog
from cogs.security_cog import handled_by_security  

SUSPICIOUS_EXTENSIONS = [
    ".exe", ".js", ".vbs", ".bat", ".cmd",
    ".scr", ".msi", ".jar", ".docm", ".xlsm", ".pptm"
]

class AttachmentScanner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        os.makedirs("temp", exist_ok=True)
        # Load server config
        if os.path.exists("server_config.json"):
            with open("server_config.json", "r") as f:
                self.server_config = json.load(f)
        else:
            self.server_config = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Skip if SecurityCog already processed this message
        if message.id in handled_by_security:
            return
        handled_by_security.add(message.id)

        for attachment in message.attachments:
            await self.scan_attachment(message, attachment)

    async def download_attachment(self, attachment: discord.Attachment):
        f = f"temp/{attachment.filename}"
        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url) as r:
                if r.status == 200:
                    with open(f, "wb") as file:
                        file.write(await r.read())
        return f

    def is_suspicious_file(self, file_path: str):
        return os.path.splitext(file_path)[1].lower() in SUSPICIOUS_EXTENSIONS

    def has_macro(self, file_path: str):
        if not file_path.endswith((".docm", ".xlsm", ".pptm")):
            return False
        try:
            return VBA_Parser(file_path).detect_vba_macros()
        except:
            return False

    async def scan_attachment(self, message: discord.Message, attachment: discord.Attachment):
        f = await self.download_attachment(attachment)
        alert = self.is_suspicious_file(f) or self.has_macro(f)

        if alert:
            embed = discord.Embed(
                title="⚠️ Suspicious File Detected",
                description=(
                    f"**User:** {message.author.mention}\n"
                    f"**File:** {attachment.filename}\n"
                    f"**Channel:** {message.channel.mention}"
                ),
                color=discord.Color.red()
            )

            guild_id_str = str(message.guild.id)
            if guild_id_str in self.server_config:
                channel_id = self.server_config[guild_id_str].get("alert_channel_id")
                if channel_id:
                    channel = message.guild.get_channel(channel_id)
                    if channel:
                        try:
                            await channel.send(embed=embed)
                        except:
                            pass

            # Try deleting suspicious message
            try:
                await message.delete()
            except discord.NotFound:
                pass  # already deleted by SecurityCog
            except discord.Forbidden:
                alert_channel = message.guild.system_channel
                if alert_channel:
                    await alert_channel.send(
                        f"⚠️ Tried to delete a suspicious file from {message.author.mention}, but lacked permissions."
                    )

        os.remove(f)

def setup(bot):
    bot.add_cog(AttachmentScanner(bot))
