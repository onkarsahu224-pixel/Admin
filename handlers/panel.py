from telegram import Update
from telegram.ext import ContextTypes

import database as db
import keyboards as kb
from utils import is_owner, set_pending, pop_pending, peek_pending
from handlers.leaderboard import send_leaderboard


async def _owned_groups(bot, user_id: int):
    all_groups = await db.list_known_groups()
    owned = []
    for g in all_groups:
        if await is_owner(bot, g["group_id"], user_id):
            owned.append(g)
    return owned


async def panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type != "private":
        await update.message.reply_text("Please message me privately and send /panel there. 🔒")
        return

    owned = await _owned_groups(context.bot, user.id)
    if not owned:
        await update.message.reply_text(
            "You don't own any groups I'm currently an admin in.\n"
            "Add me to your group as *admin* first, then send /panel again.",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text(
        "🛠️ *Your Admin Panel*\nSelect a group to manage:",
        parse_mode="Markdown",
        reply_markup=kb.groups_menu(owned),
    )


async def _edit(query, text, markup):
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)


async def panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data
    await query.answer()

    if data == "back_groups":
        owned = await _owned_groups(context.bot, user.id)
        await _edit(query, "🛠️ *Your Admin Panel*\nSelect a group to manage:", kb.groups_menu(owned))
        return

    parts = data.split(":")
    action = parts[0]
    group_id = int(parts[1])

    if not await is_owner(context.bot, group_id, user.id):
        await query.answer("⛔ Owner access only.", show_alert=True)
        return

    group = await db.get_group_settings(group_id)
    title = group.get("title") or str(group_id)

    if action == "grp":
        await _edit(query, f"🛠️ *{title}*\nWhat would you like to manage?", kb.group_main_menu(group_id))

    elif action == "bl_menu":
        await _edit(query, f"🚫 *Blacklist — {title}*", kb.blacklist_menu(group_id))

    elif action == "bl_add":
        set_pending(context, user.id, "bl_add", {"group_id": group_id})
        await _edit(query, "✍️ Send the word(s) to add, separated by spaces.", kb.back_button(group_id, "bl_menu"))

    elif action == "bl_remove":
        set_pending(context, user.id, "bl_remove", {"group_id": group_id})
        await _edit(query, "✍️ Send the word(s) to remove, separated by spaces.", kb.back_button(group_id, "bl_menu"))

    elif action == "bl_list":
        words = await db.get_blacklist(group_id)
        text = ", ".join(words) if words else "No blacklisted words yet."
        await _edit(query, f"🚫 *Blacklisted words — {title}*\n\n{text}", kb.back_button(group_id, "bl_menu"))

    elif action == "pts_menu":
        await _edit(query, f"⭐ *Points — {title}*", kb.points_menu(group_id))

    elif action in ("pts_add", "pts_remove", "pts_set"):
        set_pending(context, user.id, action, {"group_id": group_id})
        verb = {"pts_add": "add", "pts_remove": "remove", "pts_set": "set"}[action]
        await _edit(
            query,
            f"✍️ Send `@username amount` to {verb} points.\n"
            "(The user must have sent at least one message in the group already.)",
            kb.back_button(group_id, "pts_menu"),
        )

    elif action == "rw_menu":
        await _edit(query, f"🎁 *Rewards — {title}*", kb.rewards_menu(group_id))

    elif action == "rw_set":
        rank = int(parts[2])
        set_pending(context, user.id, "rw_set", {"group_id": group_id, "rank": rank})
        await _edit(query, f"✍️ Send the reward description for rank #{rank}.", kb.back_button(group_id, "rw_menu"))

    elif action == "rw_list":
        rewards = await db.get_rewards(group_id)
        text = "\n".join(f"#{r['rank']}: {r['description']}" for r in rewards) or "No rewards configured yet."
        await _edit(query, f"🎁 *Rewards — {title}*\n\n{text}", kb.back_button(group_id, "rw_menu"))

    elif action == "set_menu":
        await _edit(query, f"⚙️ *Settings — {title}*", kb.settings_menu(group_id, group))

    elif action == "set_start":
        set_pending(context, user.id, "set_start", {"group_id": group_id})
        await _edit(query, "✍️ Send the new starting points value (number).", kb.back_button(group_id, "set_menu"))

    elif action == "set_penalty":
        set_pending(context, user.id, "set_penalty", {"group_id": group_id})
        await _edit(query, "✍️ Send the new penalty points value (number).", kb.back_button(group_id, "set_menu"))

    elif action == "set_toggle_delete":
        await db.update_group_setting(group_id, "auto_delete", 0 if group["auto_delete"] else 1)
        group = await db.get_group_settings(group_id)
        await _edit(query, f"⚙️ *Settings — {title}*", kb.settings_menu(group_id, group))

    elif action == "set_toggle_mute":
        await db.update_group_setting(group_id, "auto_mute_at_zero", 0 if group["auto_mute_at_zero"] else 1)
        group = await db.get_group_settings(group_id)
        await _edit(query, f"⚙️ *Settings — {title}*", kb.settings_menu(group_id, group))

    elif action == "view_lb":
        await query.message.reply_text("🖼️ Generating leaderboard...")
        await send_leaderboard(context.bot, group_id, title)

    elif action == "reset_confirm":
        await _edit(
            query,
            f"⚠️ *Reset leaderboard for {title}?*\nThis archives current standings, announces winners "
            "with your configured rewards, and resets everyone's points.",
            kb.confirm_reset(group_id),
        )

    elif action == "reset_do":
        top3 = await db.archive_and_reset(group_id)
        rewards = {r["rank"]: r["description"] for r in await db.get_rewards(group_id)}
        medals = ["🥇", "🥈", "🥉"]
        lines = [
            f"{medals[i]} {m['first_name'] or m['username']} — {m['points']} pts\n   ↳ Reward: {rewards.get(i+1, '🎉 Congratulations!')}"
            for i, m in enumerate(top3)
        ]
        announcement = "🏁 *Monthly Leaderboard Reset!*\n\n" + ("\n\n".join(lines) if lines else "No members ranked this month.")
        announcement += "\n\n🔄 Everyone's points have been reset for the new month. Good luck! 🍀"
        await context.bot.send_message(group_id, announcement, parse_mode="Markdown")
        await send_leaderboard(context.bot, group_id, title)
        await _edit(query, f"✅ Leaderboard reset & winners announced in *{title}*.", kb.group_main_menu(group_id))


async def handle_pending_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    pending = peek_pending(context, user.id)
    if not pending:
        await update.message.reply_text("Send /panel to open your admin control panel. 🛠️")
        return

    action = pending["action"]
    payload = pending["payload"]
    group_id = payload["group_id"]
    text = update.message.text.strip()

    if action == "bl_add":
        words = text.split()
        await db.add_blacklist_words(group_id, words)
        pop_pending(context, user.id)
        await update.message.reply_text(f"🚫 Added {len(words)} word(s) to the blacklist.")

    elif action == "bl_remove":
        words = text.split()
        await db.remove_blacklist_words(group_id, words)
        pop_pending(context, user.id)
        await update.message.reply_text(f"✅ Removed {len(words)} word(s) from the blacklist.")

    elif action in ("pts_add", "pts_remove", "pts_set"):
        parts = text.split()
        if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
            await update.message.reply_text("Format must be: `@username amount`", parse_mode="Markdown")
            return
        username, amount = parts[0], int(parts[1])
        member = await db.find_member_by_username(group_id, username)
        if not member:
            await update.message.reply_text(
                "⚠️ I don't have that user on record yet — ask them to send a message in the group first."
            )
            return
        if action == "pts_add":
            new_points = await db.adjust_points(group_id, member["user_id"], amount)
        elif action == "pts_remove":
            new_points = await db.adjust_points(group_id, member["user_id"], -amount)
        else:
            await db.set_points(group_id, member["user_id"], amount)
            new_points = amount
        pop_pending(context, user.id)
        await update.message.reply_text(f"✅ {username} now has *{new_points}* points.", parse_mode="Markdown")

    elif action == "rw_set":
        rank = payload["rank"]
        await db.set_reward(group_id, rank, text)
        pop_pending(context, user.id)
        await update.message.reply_text(f"🎁 Reward for rank #{rank} set to: {text}")

    elif action in ("set_start", "set_penalty"):
        if not text.isdigit():
            await update.message.reply_text("Please send a whole number.")
            return
        field = "starting_points" if action == "set_start" else "penalty_points"
        await db.update_group_setting(group_id, field, int(text))
        pop_pending(context, user.id)
        await update.message.reply_text("✅ Setting updated.")
