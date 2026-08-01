from telegram import Update
from telegram.ext import ContextTypes

import database as db


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text(
            "👋 *Welcome!*\n\n"
            "I'm a Points & Leaderboard bot for Telegram groups.\n\n"
            "➕ Add me to your group as *admin* (with delete-messages permission) "
            "and I'll automatically:\n"
            "• Give every member 1000 starting points ⭐\n"
            "• Deduct points for abusive / blacklisted words 🚫\n"
            "• Keep a live, auto-updating leaderboard 📊\n"
            "• Reward the top members at month's end 🎁\n\n"
            "If you're the *creator* of a group I'm in, send /panel here "
            "to open your admin control panel.",
            parse_mode="Markdown",
        )
        return

    await db.ensure_group(chat.id, chat.title or "")
    await db.ensure_member(chat.id, user.id, user.username, user.first_name)
    settings = await db.get_group_settings(chat.id)
    await update.message.reply_text(
        f"✅ *{user.first_name}* is registered with *{settings['starting_points']}* starting points!\n"
        "Use /leaderboard to see the live rankings, /mypoints to check your score.",
        parse_mode="Markdown",
    )


async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    await db.ensure_group(chat.id, chat.title or "")
    settings = await db.get_group_settings(chat.id)

    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        await db.ensure_member(chat.id, member.id, member.username, member.first_name)

    names = ", ".join(m.first_name for m in update.message.new_chat_members if not m.is_bot)
    if names:
        await update.message.reply_text(
            f"🎉 Welcome, *{names}*!\n"
            f"You've been credited with *{settings['starting_points']}* points ⭐\n"
            "Keep it clean and climb the /leaderboard! 🏆",
            parse_mode="Markdown",
        )


async def mypoints_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        await update.message.reply_text("This command only works inside a group.")
        return

    await db.ensure_member(chat.id, user.id, user.username, user.first_name)
    member = await db.get_member(chat.id, user.id)
    rank = await db.get_rank(chat.id, user.id)
    violations = member["violations"]
    await update.message.reply_text(
        f"⭐ *{user.first_name}'s Stats*\n\n"
        f"🏅 Rank: #{rank}\n"
        f"💰 Points: {member['points']}\n"
        f"🚫 Violations: {violations}",
        parse_mode="Markdown",
    )


async def rules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("This command only works inside a group.")
        return
    settings = await db.get_group_settings(chat.id)
    rewards = await db.get_rewards(chat.id)
    reward_lines = "\n".join(f"{'🥇🥈🥉'[r['rank']-1] if r['rank'] <= 3 else '🎁'} #{r['rank']}: {r['description']}"
                              for r in rewards) or "Not set yet — ask the group owner!"
    await update.message.reply_text(
        "📜 *Group Rules*\n\n"
        f"• Every new member starts with *{settings['starting_points']}* points ⭐\n"
        f"• Abusive / blacklisted words cost you *{settings['penalty_points']}* points 🚫\n"
        "• Climb the leaderboard by staying respectful and active!\n"
        "• Top members get rewarded at the end of every month 🎁\n\n"
        "*Current Rewards:*\n" + reward_lines,
        parse_mode="Markdown",
    )
