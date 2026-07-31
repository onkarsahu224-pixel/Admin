import re

from telegram import Update, ChatPermissions
from telegram.error import TelegramError
from telegram.ext import ContextTypes

import database as db


def _contains_blacklisted(text: str, blacklist: list[str]) -> list[str]:
    text_l = text.lower()
    hits = []
    for word in blacklist:
        pattern = r"(?<!\w)" + re.escape(word) + r"(?!\w)"
        if re.search(pattern, text_l):
            hits.append(word)
    return hits


async def moderate_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not message.text or user.is_bot:
        return

    await db.ensure_group(chat.id, chat.title or "")
    await db.ensure_member(chat.id, user.id, user.username, user.first_name)

    blacklist = await db.get_blacklist(chat.id)
    if not blacklist:
        return

    hits = _contains_blacklisted(message.text, blacklist)
    if not hits:
        return

    settings = await db.get_group_settings(chat.id)
    penalty = settings["penalty_points"]
    new_points = await db.adjust_points(chat.id, user.id, -penalty, count_violation=True)

    if settings["auto_delete"]:
        try:
            await message.delete()
        except TelegramError:
            pass

    warn_text = (
        f"🚫 *{user.first_name}*, that message broke the group rules!\n"
        f"⚠️ -{penalty} points ({len(hits)} flagged word(s))\n"
        f"💰 New balance: *{new_points}* points"
    )
    warning_msg = await context.bot.send_message(chat.id, warn_text, parse_mode="Markdown")

    if new_points is not None and new_points <= 0 and settings["auto_mute_at_zero"]:
        try:
            await context.bot.restrict_chat_member(
                chat.id, user.id, permissions=ChatPermissions(can_send_messages=False)
            )
            await context.bot.send_message(
                chat.id,
                f"🔇 *{user.first_name}* has been muted for reaching 0 points. "
                "An admin can lift this from the group settings.",
                parse_mode="Markdown",
            )
        except TelegramError:
            pass
