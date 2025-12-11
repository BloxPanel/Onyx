import discord, json, random, string
from discord.ext import commands
from discord.ui import View, Button, Modal, InputText
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

CONFIG_FILE = "server_config.json"

class CaptchaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pending = {}  # user_id -> (captcha_text, role_id)
        self.config = self.load_config()

    def load_config(self):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            return {}

    def get_server_config(self, guild_id):
        return self.config.get(str(guild_id), {})

    def generate_captcha(self):
        text = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        img = Image.new('RGB', (180, 60), 'white')
        x = 5
        try:
            font = ImageFont.truetype("arial.ttf", 36)
        except:
            font = ImageFont.load_default()
        for ch in text:
            cimg = Image.new('RGBA', (40, 50), (255, 255, 255, 0))
            d = ImageDraw.Draw(cimg)
            d.text((0, 0), ch, font=font, fill=(0, 0, 0))
            cimg = cimg.rotate(random.randint(-20, 20), expand=1)
            img.paste(cimg, (x, random.randint(5, 15)), cimg)
            x += 32
        buf = BytesIO()
        img.save(buf, 'PNG')
        buf.seek(0)
        return text, buf

    async def send_captcha(self, member: discord.Member):
        cfg = self.get_server_config(member.guild.id)
        channel_id = cfg.get("captcha_channel_id")
        role_id = cfg.get("captcha_verified_role_id")
        if not channel_id or not role_id:
            print(f"[CaptchaCog] CAPTCHA not configured for guild {member.guild.id}")
            return
        channel = member.guild.get_channel(channel_id)
        role = member.guild.get_role(role_id)
        if not channel or not role:
            print(f"[CaptchaCog] CAPTCHA channel or role not found in guild {member.guild.id}")
            return

        text, img = self.generate_captcha()
        self.pending[member.id] = (text, role.id)
        file = discord.File(img, filename="captcha.png")
        embed = discord.Embed(title="🔒 CAPTCHA Verification",
                              description="Click verify and type the text in the image.",
                              color=discord.Color.orange())
        embed.set_image(url="attachment://captcha.png")
        view = View()
        view.add_item(VerifyButton(self, member))
        await channel.send(content=member.mention, embed=embed, file=file, view=view)

    @commands.slash_command(name="captcha_test", description="Trigger a test CAPTCHA for a user")
    async def captcha_test(self, ctx: discord.ApplicationContext, member: discord.Member):
        await ctx.defer(ephemeral=True)
        await self.send_captcha(member)
        await ctx.respond(f"✅ CAPTCHA sent to {member.mention}", ephemeral=True)
    captcha_test.hidden_tag = True  # Right after the function

class VerifyButton(Button):
    def __init__(self, cog, member):
        super().__init__(label="✅ Verify", style=discord.ButtonStyle.green)
        self.cog = cog
        self.member = member

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.member.id:
            return await interaction.response.send_message("❌ This CAPTCHA isn’t for you!", ephemeral=True)
        pending = self.cog.pending.get(self.member.id)
        if not pending:
            return await interaction.response.send_message("⚠️ CAPTCHA expired", ephemeral=True)
        text, role_id = pending
        await interaction.response.send_modal(CaptchaModal(self.cog, self.member, text, role_id))

class CaptchaModal(Modal):
    def __init__(self, cog, member, correct_text, role_id):
        super().__init__(title="CAPTCHA Verification")
        self.cog = cog
        self.member = member
        self.correct_text = correct_text
        self.role_id = role_id
        self.add_item(InputText(label="Enter the text"))

    async def callback(self, interaction: discord.Interaction):
        answer = self.children[0].value.strip().upper()
        if answer == self.correct_text.upper():
            del self.cog.pending[self.member.id]
            role = self.member.guild.get_role(self.role_id)
            if role:
                await self.member.add_roles(role)
                await interaction.response.send_message(f"✅ Verified! Role `{role.name}` added", ephemeral=True)
            else:
                await interaction.response.send_message("✅ Verified! (Role not found)", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Wrong CAPTCHA", ephemeral=True)

def setup(bot):
    bot.add_cog(CaptchaCog(bot))