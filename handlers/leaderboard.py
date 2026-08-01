import datetime

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from image_utils import render_leaderboard
from config import LEADERBOARD_SIZE


async def send_leaderboard(bot, chat_id: int, group_title: str):
    rows = await db.get_leaderboard(chat_id, limit=LEADERBOARD_SIZE)
    updated_label = "Updated " + datetime.datetime.utcnow().strftime("%b %d, %Y %H:%M UTC")
    png_bytes = await render_leaderboard(bot, group_title, rows, updated_label)
    await bot.send_photo(
        chat_id,
        photo=png_bytes,
        caption="🏆 *Live Leaderboard* — stay respectful, climb the ranks!",
        parse_mode="Markdown",
    )


async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("This command only works inside a group.")
        return
    await db.ensure_group(chat.id, chat.title or "")
    await update.effective_message.reply_text("🖼️ Generating the live leaderboard widget...")
    await send_leaderboard(context.bot, chat.id, chat.title or "")
