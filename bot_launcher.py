import asyncio
import importlib
import os
import main  # your main.py
import subprocess

# --- Configuration ---
CHECK_INTERVAL = 5  # seconds between file checks
COG_FOLDER = "cogs"
RESTART_FLAG_FILE = "restart_flag.json"

# --- Track modification times ---
watched_files = {"main.py": os.path.getmtime("main.py")}
for f in os.listdir(COG_FOLDER):
    if f.endswith(".py"):
        watched_files[f"{COG_FOLDER}/{f}"] = os.path.getmtime(f"{COG_FOLDER}/{f}")


async def hot_reload_loop():
    while True:
        await asyncio.sleep(CHECK_INTERVAL)

        # Scan cogs folder for new files
        for f in os.listdir(COG_FOLDER):
            if f.endswith(".py"):
                path = f"{COG_FOLDER}/{f}"
                if path not in watched_files:
                    watched_files[path] = os.path.getmtime(path)
                    cog_name = f"cogs.{f[:-3]}"
                    try:
                        main.bot.load_extension(cog_name)
                        print(f"✅ Detected and loaded new cog: {cog_name}")
                    except Exception as e:
                        import traceback
                        print(f"❌ Failed to load new cog {cog_name}:\n{''.join(traceback.format_exception(e))}")

        # Check for modifications
        for path in list(watched_files.keys()):
            try:
                mtime = os.path.getmtime(path)
                if mtime != watched_files[path]:
                    watched_files[path] = mtime
                    if path == "main.py":
                        importlib.reload(main)
                        print(f"♻️ Reloaded main.py")
                    else:
                        cog_name = f"cogs.{os.path.basename(path)[:-3]}"
                        try:
                            if cog_name in main.bot.extensions:
                                main.bot.reload_extension(cog_name)
                                print(f"♻️ Reloaded {cog_name}")
                            else:
                                await main.bot.load_extension(cog_name)
                                print(f"✅ Loaded {cog_name} (was not loaded before)")
                        except Exception as e:
                            import traceback
                            print(f"❌ Failed to load/reload {cog_name}:\n{''.join(traceback.format_exception(e))}")
            except FileNotFoundError:
                print(f"⚠️ File deleted: {path}")
                del watched_files[path]


async def restart_watcher():
    while True:
        await asyncio.sleep(2)  # check every 2 seconds
        if os.path.exists(RESTART_FLAG_FILE) or os.path.exists("join_restart_flag.json"):
            flag_type = "dashboard" if os.path.exists(RESTART_FLAG_FILE) else "join"
            flag_file = RESTART_FLAG_FILE if os.path.exists(RESTART_FLAG_FILE) else "join_restart_flag.json"

            print(f"♻️ {flag_type.title()} restart flag detected! Restarting bot...")
            os.remove(flag_file)

            # Cancel all other tasks
            for task in asyncio.all_tasks():
                if task is not asyncio.current_task():
                    task.cancel()

            subprocess.Popen(["python", "bot_launcher.py"], creationflags=subprocess.CREATE_NEW_CONSOLE)
            print("Bot restart successfully initiated!")

            await main.bot.close()
            break


async def main_runner():
    try:
        await asyncio.gather(
            main.start_bot(),     # your main.py bot
            hot_reload_loop(),     # file watcher loop
            restart_watcher()
        )
    except asyncio.CancelledError:
        # This happens when the bot is closed for a restart
        print("🛑 Bot tasks cancelled (expected on restart).")


if __name__ == "__main__":
    try:
        asyncio.run(main_runner())
    except KeyboardInterrupt:
        print("🛑 Bot stopped manually.")