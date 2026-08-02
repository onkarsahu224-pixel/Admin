import asyncio
import datetime

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from image_utils import render_leaderboard_animation
from config import LEADERBOARD_SIZE


async def _keep_upload_animation(bot, chat_id: int):
    """Repeats Telegram's native 'uploading video...' animation every few
    seconds for as long as generation takes, instead of a static placeholder
    text message. This is a built-in Telegram indicator, so it costs nothing
    extra to render and feels alive to the user even during a longer render."""
    try:
        while True:
            await bot.send_chat_action(chat_id, action="upload_video")
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


async def send_leaderboard(bot, chat_id: int, group_title: str):
    animation_task = asyncio.create_task(_keep_upload_animation(bot, chat_id))
    try:
        rows = await db.get_leaderboard(chat_id, limit=LEADERBOARD_SIZE)
        updated_label = "Updated " + datetime.datetime.utcnow().strftime("%b %d, %Y %H:%M UTC")
        mp4_bytes = await render_leaderboard_animation(bot, group_title, rows, updated_label)
    finally:
        animation_task.cancel()
    await bot.send_animation(
        chat_id,
        animation=mp4_bytes,
        caption="🏆 *Live Leaderboard* — stay respectful, climb the ranks!",
        parse_mode="Markdown",
    )


async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("This command only works inside a group.")
        return
    await db.ensure_group(chat.id, chat.title or "")
    await send_leaderboard(context.bot, chat.id, chat.title or "")
