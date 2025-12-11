import discord
from discord.ext import commands
import textwrap
import io
import contextlib
import traceback
import re

class EvalCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="eval", hidden=True)
    async def _eval(self, ctx, *, code):
        # Only bot owner
        app_info = await self.bot.application_info()
        if ctx.author.id != app_info.owner.id:
            return await ctx.send("❌ You cannot use this command.")

        code = code.strip("` ").replace("python", "")
        func_code = f"async def func():\n{textwrap.indent(code, '    ')}"
        env = {"bot": self.bot, "ctx": ctx, "discord": discord, "__import__": __import__}

        try:
            exec(func_code, env)
            func = env["func"]

            # Capture stdout
            with contextlib.redirect_stdout(io.StringIO()) as f:
                result = await func()
                output = f.getvalue()

            # Prefer function return value, fallback to print output
            final_output = result if result is not None else output
            if not final_output:
                final_output = "✅ Code executed successfully with no output."

            await ctx.send(f"✅ Success:\n```\n{final_output}\n```")

        except Exception:
            # Format traceback safely
            tb = traceback.format_exc()
            tb = re.sub(r'File ".*?\.py"', 'File "<eval>"', tb)
            tb = tb.replace('<string>', '<eval>')
            await ctx.send(f"❌ Error:\n```\n{tb}\n```")

def setup(bot):
    bot.add_cog(EvalCog(bot))
