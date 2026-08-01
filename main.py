import datetime
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import database as db
from config import BOT_TOKEN, MONTHLY_RESET_HOUR_UTC
from handlers.basic import start_cmd, welcome_new_members, mypoints_cmd, rules_cmd
from handlers.leaderboard import leaderboard_cmd, send_leaderboard
from handlers.moderation import moderate_message
from handlers.panel import panel_cmd, panel_callback, handle_pending_text
from handlers.group_admin import (
    admin_cmd,
    addpoints_cmd,
    removepoints_cmd,
    setpoints_cmd,
    addblacklist_cmd,
    removeblacklist_cmd,
    blacklist_list_cmd,
    setreward_cmd,
    rewards_list_cmd,
    resetmonth_cmd,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def _post_init(application: Application):
    await db.init_db()
    logger.info("Database ready.")


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass  # keep the logs clean


def _start_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info(f"Health check server listening on port {port}")


async def monthly_auto_reset(context: ContextTypes.DEFAULT_TYPE):
    """Runs automatically on the 1st of every month: archives standings,
    announces the winners with the owner-configured rewards, and resets
    everyone back to their group's starting points."""
    groups = await db.list_known_groups()
    for g in groups:
        group_id = g["group_id"]
        try:
            top3 = await db.archive_and_reset(group_id)
            rewards = {r["rank"]: r["description"] for r in await db.get_rewards(group_id)}
            medals = ["🥇", "🥈", "🥉"]
            lines = [
                f"{medals[i]} {m['first_name'] or m['username']} — {m['points']} pts\n"
                f"   ↳ Reward: {rewards.get(i + 1, '🎉 Congratulations!')}"
                for i, m in enumerate(top3)
            ]
            announcement = (
                "🏁 *A New Month Has Begun — Leaderboard Reset!*\n\n"
                + ("\n\n".join(lines) if lines else "No members ranked last month.")
                + "\n\n🔄 Everyone's points have been reset. Good luck this month! 🍀"
            )
            await context.bot.send_message(group_id, announcement, parse_mode="Markdown")
            await send_leaderboard(context.bot, group_id, g["title"] or "")
        except Exception:
            logger.exception("Monthly reset failed for group %s", group_id)


def main():
    _start_health_server()

    application = ApplicationBuilder().token(BOT_TOKEN).post_init(_post_init).build()

    # ---- Group member / basic commands ----
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))
    application.add_handler(CommandHandler(["mypoints", "rank"], mypoints_cmd))
    application.add_handler(CommandHandler("rules", rules_cmd))
    application.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    application.add_handler(CommandHandler("rewards", rewards_list_cmd))

    # ---- Owner-only quick commands (work directly in the group) ----
    application.add_handler(CommandHandler("admin", admin_cmd))
    application.add_handler(CommandHandler("addpoints", addpoints_cmd))
    application.add_handler(CommandHandler("removepoints", removepoints_cmd))
    application.add_handler(CommandHandler("setpoints", setpoints_cmd))
    application.add_handler(CommandHandler("addblacklist", addblacklist_cmd))
    application.add_handler(CommandHandler("removeblacklist", removeblacklist_cmd))
    application.add_handler(CommandHandler("blacklist", blacklist_list_cmd))
    application.add_handler(CommandHandler("setreward", setreward_cmd))
    application.add_handler(CommandHandler("resetmonth", resetmonth_cmd))

    # ---- Owner admin panel (private chat, button-driven) ----
    application.add_handler(CommandHandler("panel", panel_cmd))
    application.add_handler(CallbackQueryHandler(panel_callback))

    # Pending text input for the panel (must come before the catch-all group moderation filter)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_pending_text)
    )

    # ---- Group moderation (blacklist scanning) ----
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, moderate_message)
    )

    # ---- Automatic monthly reward reset (1st of every month) ----
    application.job_queue.run_monthly(
        monthly_auto_reset,
        when=datetime.time(hour=MONTHLY_RESET_HOUR_UTC, minute=0, second=0, tzinfo=datetime.timezone.utc),
        day=1,
    )

    logger.info("Bot starting (polling mode)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
