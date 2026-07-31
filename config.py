"""
Central configuration for the Points & Leaderboard Bot.
All secrets are loaded from environment variables so nothing sensitive
lives in the source code (safe to upload to Wispbyte / GitHub / etc).
"""

import os
from dotenv import load_dotenv

load_dotenv()  # loads variables from a local .env file if present

# ---- Required ----
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# ---- Defaults (overridable per-group from the /panel or /settings) ----
DEFAULT_STARTING_POINTS = int(os.getenv("DEFAULT_STARTING_POINTS", "1000"))
DEFAULT_PENALTY_POINTS = int(os.getenv("DEFAULT_PENALTY_POINTS", "50"))
DEFAULT_AUTO_DELETE = os.getenv("DEFAULT_AUTO_DELETE", "1") == "1"
DEFAULT_AUTO_MUTE_AT_ZERO = os.getenv("DEFAULT_AUTO_MUTE_AT_ZERO", "0") == "1"

# How many rows to show on the /leaderboard image
LEADERBOARD_SIZE = 15

# SQLite database file (relative path -> works out of the box on Wispbyte)
DB_PATH = os.getenv("DB_PATH", "bot_data.db")

# Fonts bundled with the project (used for the leaderboard image widget)
FONT_BOLD = os.path.join(os.path.dirname(__file__), "assets", "font_bold.ttf")
FONT_REGULAR = os.path.join(os.path.dirname(__file__), "assets", "font_regular.ttf")

# Timezone-naive hour (UTC) at which the monthly reset job runs on day 1
MONTHLY_RESET_HOUR_UTC = int(os.getenv("MONTHLY_RESET_HOUR_UTC", "0"))

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set. Add it as an environment variable "
        "(in Wispbyte: Startup tab -> Variables) before starting the bot."
    )
