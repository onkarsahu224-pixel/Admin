from telegram import Update
from telegram.ext import ContextTypes

import database as db
import keyboards as kb
from utils import is_owner
from handlers.leaderboard import send_leaderboard


async def _require_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    if not await is_owner(context.bot, chat.id, user.id):
        await update.message.reply_text("⛔ Only the group *owner* (creator) can do this.", parse_mode="Markdown")
        return False
    return True


def _reply_target(update: Update):
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    return None


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Opens the full button-based admin panel directly inside the group."""
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("Use /panel here instead — it lists every group you own.")
        return
    if not await _require_owner(update, context):
        return
    await db.ensure_group(chat.id, chat.title or "")
    await update.message.reply_text(
        f"🛠️ *Admin Panel — {chat.title}*\nEverything below is one tap away.",
        parse_mode="Markdown",
        reply_markup=kb.group_main_menu(chat.id),
    )


async def addpoints_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_owner(update, context):
        return
    target = _reply_target(update)
    if not target or not context.args:
        await update.message.reply_text("Usage: reply to a member's message with `/addpoints 100`", parse_mode="Markdown")
        return
    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Amount must be a number.")
        return
    chat = update.effective_chat
    await db.ensure_member(chat.id, target.id, target.username, target.first_name)
    new_points = await db.adjust_points(chat.id, target.id, amount)
    await update.message.reply_text(f"✅ Gave *{target.first_name}* +{amount} points. New total: *{new_points}*", parse_mode="Markdown")


async def removepoints_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_owner(update, context):
        return
    target = _reply_target(update)
    if not target or not context.args:
        await update.message.reply_text("Usage: reply to a member's message with `/removepoints 100`", parse_mode="Markdown")
        return
    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Amount must be a number.")
        return
    chat = update.effective_chat
    await db.ensure_member(chat.id, target.id, target.username, target.first_name)
    new_points = await db.adjust_points(chat.id, target.id, -amount)
    await update.message.reply_text(f"✅ Removed {amount} points from *{target.first_name}*. New total: *{new_points}*", parse_mode="Markdown")


async def setpoints_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_owner(update, context):
        return
    target = _reply_target(update)
    if not target or not context.args:
        await update.message.reply_text("Usage: reply to a member's message with `/setpoints 500`", parse_mode="Markdown")
        return
    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Amount must be a number.")
        return
    chat = update.effective_chat
    await db.ensure_member(chat.id, target.id, target.username, target.first_name)
    await db.set_points(chat.id, target.id, amount)
    await update.message.reply_text(f"✅ Set *{target.first_name}'s* points to *{amount}*.", parse_mode="Markdown")


async def addblacklist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_owner(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/addblacklist word1 word2 ...`", parse_mode="Markdown")
        return
    chat = update.effective_chat
    await db.add_blacklist_words(chat.id, context.args)
    await update.message.reply_text(f"🚫 Added {len(context.args)} word(s) to the blacklist.")


async def removeblacklist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_owner(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/removeblacklist word1 word2 ...`", parse_mode="Markdown")
        return
    chat = update.effective_chat
    await db.remove_blacklist_words(chat.id, context.args)
    await update.message.reply_text(f"✅ Removed {len(context.args)} word(s) from the blacklist.")


async def blacklist_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_owner(update, context):
        return
    chat = update.effective_chat
    words = await db.get_blacklist(chat.id)
    text = ", ".join(words) if words else "No blacklisted words yet."
    await update.message.reply_text(f"🚫 *Blacklisted words:*\n{text}", parse_mode="Markdown")


async def setreward_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_owner(update, context):
        return
    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: `/setreward 1 $10 Amazon Gift Card`", parse_mode="Markdown")
        return
    chat = update.effective_chat
    rank = int(context.args[0])
    description = " ".join(context.args[1:])
    await db.set_reward(chat.id, rank, description)
    await update.message.reply_text(f"🎁 Reward for rank #{rank} set to: {description}")


async def rewards_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    rewards = await db.get_rewards(chat.id)
    if not rewards:
        await update.message.reply_text("No rewards configured yet.")
        return
    lines = [f"#{r['rank']}: {r['description']}" for r in rewards]
    await update.message.reply_text("🎁 *Current Rewards*\n" + "\n".join(lines), parse_mode="Markdown")


async def resetmonth_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_owner(update, context):
        return
    chat = update.effective_chat
    top3 = await db.archive_and_reset(chat.id)
    rewards = {r["rank"]: r["description"] for r in await db.get_rewards(chat.id)}
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, m in enumerate(top3):
        reward_text = rewards.get(i + 1, "🎉 Congratulations!")
        lines.append(f"{medals[i]} {m['first_name'] or m['username']} — {m['points']} pts\n   ↳ Reward: {reward_text}")
    announcement = "🏁 *Monthly Leaderboard Reset!*\n\n" + ("\n\n".join(lines) if lines else "No members ranked this month.")
    announcement += "\n\n🔄 Everyone's points have been reset for the new month. Good luck! 🍀"
    await update.message.reply_text(announcement, parse_mode="Markdown")
    await send_leaderboard(context.bot, chat.id, chat.title or "")
