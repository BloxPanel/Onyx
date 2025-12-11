import os
import json
import requests
from flask import Flask, redirect, request, session, render_template, jsonify
from dotenv import load_dotenv
from datetime import datetime, timedelta
import subprocess
import logging
from main import bot
import traceback
import io
import sys
import asyncio

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8", mode="a"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("bot")

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
if "RENDER" in os.environ:
    DISCORD_REDIRECT_URI = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/callback"
else:
    DISCORD_REDIRECT_URI = "http://127.0.0.1:5000/callback"
DISCORD_API_BASE = "https://discord.com/api"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")  # e.g., "yourusername/yourrepo"
GITHUB_COMMITS_CACHE = {"timestamp": None, "commits": []}
GITHUB_CACHE_DURATION = timedelta(minutes=10)  # Cache for 10 minutes

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "server_config.json")

SERVER_CONFIG_PATH = "server_config.json"
REMOVED_SERVERS_PATH = "removed_servers.json"
PENDING_REMOVALS_PATH = "pending_removals.json"

def load_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


def load_server_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def fetch_github_commits():
    """Fetch latest commits from GitHub with caching."""
    now = datetime.utcnow()
    if GITHUB_COMMITS_CACHE["timestamp"] and now - GITHUB_COMMITS_CACHE["timestamp"] < GITHUB_CACHE_DURATION:
        return GITHUB_COMMITS_CACHE["commits"]

    if not GITHUB_TOKEN or not GITHUB_REPO:
        return []

    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    url = f"https://api.github.com/repos/{GITHUB_REPO}/commits"

    try:
        res = requests.get(url, headers=headers)
        if res.status_code != 200:
            print(f"GitHub API error: {res.status_code} {res.text}")
            return []

        commits = res.json()
        simplified_commits = [
            {"message": c["commit"]["message"], "date": c["commit"]["author"]["date"]} 
            for c in commits[:20]  # latest 20 commits
        ]

        GITHUB_COMMITS_CACHE["timestamp"] = now
        GITHUB_COMMITS_CACHE["commits"] = simplified_commits
        return simplified_commits

    except Exception as e:
        print(f"Failed to fetch commits: {e}")
        return []


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/discord-login")
def discord_login():
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds"
    }
    url = f"{DISCORD_API_BASE}/oauth2/authorize?{requests.compat.urlencode(params)}"
    return redirect(url)


@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Missing code", 400

    # Exchange code for access token
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "scope": "identify guilds"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    token_res = requests.post(f"{DISCORD_API_BASE}/oauth2/token", data=data, headers=headers)
    access_token = token_res.json().get("access_token")
    if not access_token:
        return "Failed to get access token", 400

    # Fetch user info
    user_res = requests.get(f"{DISCORD_API_BASE}/users/@me", headers={"Authorization": f"Bearer {access_token}"})
    user = user_res.json()
    session["user"] = user
    session["access_token"] = access_token

    # Fetch user guilds (store only IDs)
    guilds_res = requests.get(f"{DISCORD_API_BASE}/users/@me/guilds", headers={"Authorization": f"Bearer {access_token}"})
    user_guilds = guilds_res.json()
    session["user_guild_ids"] = [str(g["id"]) for g in user_guilds]

    return redirect("/dashboard")


@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/login")

    user = session["user"]
    user_guild_ids = session.get("user_guild_ids", [])

    server_config = load_server_config()

    shared_servers = []
    for gid in user_guild_ids:
        if gid in server_config:
            cfg = server_config[gid]
            shared_servers.append({
                "id": gid,
                "name": cfg.get("name", "Unknown Server"),
                "icon": cfg.get("icon")
            })

    return render_template("dashboard.html", user=user, shared_servers=shared_servers)


@app.route("/server/<server_id>")
def manage_server(server_id):
    if "user" not in session:
        return redirect("/login")

    user = session["user"]
    user_id = int(user["id"])

    user_guild_ids = session.get("user_guild_ids", [])
    if server_id not in user_guild_ids:
        return render_template("403.html"), 403

    server_config = load_server_config()
    guild_config = server_config.get(server_id)
    if not guild_config:
        return "❌ Server config not found.", 404

    owner_id = guild_config.get("owner_id")
    admin_role_id = guild_config.get("admin_role_id")

    guild_info = {
        "id": server_id,
        "name": guild_config.get("name", "Unknown Server"),
        "icon": guild_config.get("icon")
    }

    # Allow access if user is owner
    if owner_id and user_id == owner_id:
        return render_template("manage_server.html", user=user, server=guild_info, config=guild_config)

    # Allow access if user has admin role
    if admin_role_id:
        headers = {"Authorization": f"Bot {os.getenv('DISCORD_TOKEN_ID')}"}
        member_res = requests.get(f"https://discord.com/api/v10/guilds/{server_id}/members/{user_id}", headers=headers)
        if member_res.status_code == 200:
            member_data = member_res.json()
            roles = [int(r) for r in member_data.get("roles", [])]
            if int(admin_role_id) in roles:
                return render_template("manage_server.html", user=user, server=guild_info, config=guild_config)

    return redirect("/denied")


@app.route("/denied")
def denied():
    return render_template("403.html"), 403


@app.route("/load_config")
def load_config():
    server_id = request.args.get("server_id")
    if not server_id:
        return jsonify({"error": "Missing server_id"}), 400

    server_config = load_server_config()
    guild_config = server_config.get(server_id, {})

    # Prepare the data to return
    data = {
        "roles": {
            "admin_role_id": guild_config.get("admin_role_id"),
            "allowed_ping_role_id": guild_config.get("allowed_ping_role_id")
        },
        "channels": {
            "alert_channel_id": guild_config.get("alert_channel_id")
        },
        "permissions": guild_config.get("dangerous_perms", {})  # Empty dict if not defined
    }

    return jsonify(data)

@app.route("/settings")
def settings():
    if "user" not in session:
        return redirect("/login")
    user = session["user"]
    if str(user["id"]) != os.getenv("BOT_OWNER_ID"):
        return render_template("403.html"), 403
    return render_template("settings.html", user=user)

@app.route("/server/<server_id>/roles")
def server_roles(server_id):
    if "user" not in session:
        return redirect("/login")

    user = session["user"]
    server_config = load_server_config()
    guild_config = server_config.get(server_id)

    if not guild_config:
        return "❌ Server config not found.", 404

    server = {
        "id": server_id,
        "name": guild_config.get("name", "Unknown Server"),
        "icon": guild_config.get("icon")
    }

    # Roles info from your JSON config
    roles_list = [
        {"id": guild_config.get("admin_role_id"), "name": "Admin Role"},
        {"id": guild_config.get("allowed_ping_role_id"), "name": "Allowed Ping Role"},
    ]

    return render_template("roles.html", user=user, server=server, roles_list=roles_list)


@app.route("/server/<server_id>/channels")
def server_channels(server_id):
    if "user" not in session:
        return redirect("/login")

    user = session["user"]
    server_config = load_server_config()
    guild_config = server_config.get(server_id)

    if not guild_config:
        return "❌ Server config not found.", 404

    server = {
        "id": server_id,
        "name": guild_config.get("name", "Unknown Server"),
        "icon": guild_config.get("icon")
    }

    # Read channels directly from config
    channels_list = [
        {"id": guild_config.get("alert_channel_id"), "name": "Alert Channel"},
        {"id": guild_config.get("captcha_channel_id"), "name": "Captcha Channel"},
    ]

    return render_template("channels.html", user=user, server=server, channels_list=channels_list)


@app.route("/server/<server_id>/permissions")
def server_permissions(server_id):
    if "user" not in session:
        return redirect("/login")

    user = session["user"]
    server_config = load_server_config()
    guild_config = server_config.get(server_id)

    if not guild_config:
        return "❌ Server config not found.", 404

    server = {
        "id": server_id,
        "name": guild_config.get("name", "Unknown Server"),
        "icon": guild_config.get("icon")
    }

    permissions = guild_config.get("dangerous_perms", {})

    return render_template("permissions.html", user=user, server=server, permissions=permissions)

# --- Changelog route with GitHub commits ---
@app.route("/changelog")
def changelog():
    GITHUB_OWNER = "onyxbo"
    GITHUB_REPO = "onyxbot"
    TOKEN = os.getenv("GITHUB_TOKEN")

    headers = {"Authorization": f"token {TOKEN}"} if TOKEN else {}
    commits = []

    try:
        res = requests.get(
            f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/commits?sha=main",
            headers=headers
        )
        if res.status_code == 200:
            for item in res.json()[:10]:  # Last 10 commits
                commits.append({
                    "message": item["commit"]["message"],
                    "date": item["commit"]["committer"]["date"],
                    "url": item["html_url"]
                })
        else:
            print(f"GitHub API returned {res.status_code}: {res.text}")
    except Exception as e:
        print(f"Failed to fetch commits: {e}")

    return render_template("changelog.html", commits=commits)

BOT_MODE_PATH = os.path.join(os.path.dirname(__file__), "bot_mode.json")
BOT_GLOBAL_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "bot_global_settings.json")

@app.route("/api/owner/settings", methods=["GET", "POST"])
def api_owner_settings():
    # --- Ensure only bot owner can access ---
    if "user" not in session:
        return redirect("/login")

    user = session["user"]
    if str(user["id"]) != os.getenv("BOT_OWNER_ID", "").strip():
        return redirect("/denied")

    # --- GET: Return current settings ---
    if request.method == "GET":
        # Load server config
        server_config = load_server_config()

        # Load bot mode
        if os.path.exists(BOT_MODE_PATH):
            with open(BOT_MODE_PATH, "r") as f:
                bot_mode_data = json.load(f)
        else:
            bot_mode_data = {"mode": "production"}

        # Load global settings if exists
        if os.path.exists(BOT_GLOBAL_SETTINGS_PATH):
            with open(BOT_GLOBAL_SETTINGS_PATH, "r") as f:
                global_settings = json.load(f)
        else:
            global_settings = {
                "command_prefix": "!",
                "global_logging": True
            }

        # Transform servers for frontend
        servers = []
        for guild_id, guild_data in server_config.items():
            servers.append({
                "id": guild_id,
                "name": guild_data.get("name", "Unknown Server"),
                "owner_id": guild_data.get("owner_id"),
                "alert_channel_id": guild_data.get("alert_channel_id"),
                "admin_role_id": guild_data.get("admin_role_id"),
                "allowed_ping_role_id": guild_data.get("allowed_ping_role_id")
            })

        # --- Load dynamic bot logs ---
        try:
            with open("bot.log", "r", encoding="utf-8") as f:
                logs = f.readlines()[-50:]  # last 50 log lines
        except FileNotFoundError:
            logs = []

        return jsonify({
            "servers": servers,
            "logs": logs,
            "command_prefix": global_settings.get("command_prefix", "!"),
            "maintenance_mode": bot_mode_data.get("mode") == "maintenance",
            "global_logging": global_settings.get("global_logging", True)
        })

    # --- POST: Save settings ---
    elif request.method == "POST":
        data = request.json

        # --- Save maintenance mode separately ---
        new_mode = "maintenance" if data.get("maintenance_mode") else "production"
        with open(BOT_MODE_PATH, "w") as f:
            json.dump({"mode": new_mode}, f, indent=4)

        # --- Save remaining global settings ---
        global_settings = {
            "command_prefix": data.get("command_prefix", "!"),
            "global_logging": data.get("global_logging", True)
        }
        with open(BOT_GLOBAL_SETTINGS_PATH, "w") as f:
            json.dump(global_settings, f, indent=4)

        return jsonify({"status": "success", "message": "Settings saved!"})


RESTART_FLAG_FILE = "restart_flag.json"

@app.route("/api/owner/restart", methods=["POST"])
def api_restart_bot():
    if "user" not in session:
        return redirect("/login")

    user = session["user"]
    if str(user["id"]) != os.getenv("BOT_OWNER_ID"):
        return redirect("/denied")

    # Write a restart flag that the launcher will watch
    with open(RESTART_FLAG_FILE, "w") as f:
        f.write("restart")

    return jsonify({"status": "success", "message": "Bot restart initiated!"})

@app.route("/api/owner/eval", methods=["POST"])
def api_owner_eval():
    if "user" not in session:
        return redirect("/login")
    user = session["user"]
    if str(user["id"]) != os.getenv("BOT_OWNER_ID", "").strip():
        return redirect("/denied")

    data = request.json
    code = data.get("code", "")
    if not code:
        return jsonify({"status": "error", "output": "No code provided"}), 400

    # Wrap user code to capture 'output' variable automatically
    wrapped_code = "output = ''\n" + code
    wrapped_code += "\nif 'output' not in locals(): output = None"

    # Write to temp eval file
    with open("eval_queue.py", "w", encoding="utf-8") as f:
        f.write(wrapped_code)

    return jsonify({"status": "success", "output": "Code queued for execution."})

@app.route("/tos")
def tos():
    return render_template("tos.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/api/owner/servers/<int:server_id>/remove", methods=["POST"])
def remove_server(server_id):
    server_id_str = str(server_id)

    # Load data
    config = load_json(SERVER_CONFIG_PATH)
    removed = load_json(REMOVED_SERVERS_PATH)
    queue = load_json(PENDING_REMOVALS_PATH)

    # Check if server exists
    if server_id_str not in config:
        return jsonify({"success": False, "error": "Server not found in config"}), 404

    # Remove from server_config.json
    del config[server_id_str]
    save_json(SERVER_CONFIG_PATH, config)

    # Add to removed_servers.json
    removed[server_id_str] = {"removed": True}
    save_json(REMOVED_SERVERS_PATH, removed)

    # Queue for bot removal
    queue[server_id_str] = True
    save_json(PENDING_REMOVALS_PATH, queue)

    return jsonify({"success": True, "message": f"Server {server_id} removed and queued for bot leave"}), 200


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)