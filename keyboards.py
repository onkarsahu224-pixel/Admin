"""
Every button the bot ever shows is built here, keeping callback_data
strings consistent in one place.

callback_data format: "action:group_id:extra"
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def groups_menu(groups: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"👥 {g['title'] or g['group_id']}", callback_data=f"grp:{g['group_id']}")]
        for g in groups
    ]
    return InlineKeyboardMarkup(rows)


def group_main_menu(group_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🚫 Blacklist Words", callback_data=f"bl_menu:{group_id}"),
            InlineKeyboardButton("⭐ Points", callback_data=f"pts_menu:{group_id}"),
        ],
        [
            InlineKeyboardButton("🎁 Rewards", callback_data=f"rw_menu:{group_id}"),
            InlineKeyboardButton("⚙️ Settings", callback_data=f"set_menu:{group_id}"),
        ],
        [
            InlineKeyboardButton("📊 View Leaderboard", callback_data=f"view_lb:{group_id}"),
        ],
        [
            InlineKeyboardButton("🔄 Reset Leaderboard Now", callback_data=f"reset_confirm:{group_id}"),
        ],
        [InlineKeyboardButton("⬅️ Back to Groups", callback_data="back_groups")],
    ]
    return InlineKeyboardMarkup(rows)


def blacklist_menu(group_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("➕ Add Word(s)", callback_data=f"bl_add:{group_id}")],
        [InlineKeyboardButton("➖ Remove Word(s)", callback_data=f"bl_remove:{group_id}")],
        [InlineKeyboardButton("📋 List All", callback_data=f"bl_list:{group_id}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"grp:{group_id}")],
    ]
    return InlineKeyboardMarkup(rows)


def points_menu(group_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("➕ Add Points", callback_data=f"pts_add:{group_id}")],
        [InlineKeyboardButton("➖ Remove Points", callback_data=f"pts_remove:{group_id}")],
        [InlineKeyboardButton("🎯 Set Exact Points", callback_data=f"pts_set:{group_id}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"grp:{group_id}")],
    ]
    return InlineKeyboardMarkup(rows)


def rewards_menu(group_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("🥇 Set 1st Place Reward", callback_data=f"rw_set:{group_id}:1")],
        [InlineKeyboardButton("🥈 Set 2nd Place Reward", callback_data=f"rw_set:{group_id}:2")],
        [InlineKeyboardButton("🥉 Set 3rd Place Reward", callback_data=f"rw_set:{group_id}:3")],
        [InlineKeyboardButton("📋 View Current Rewards", callback_data=f"rw_list:{group_id}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"grp:{group_id}")],
    ]
    return InlineKeyboardMarkup(rows)


def settings_menu(group_id: int, settings: dict) -> InlineKeyboardMarkup:
    auto_del = "✅ ON" if settings["auto_delete"] else "❌ OFF"
    auto_mute = "✅ ON" if settings["auto_mute_at_zero"] else "❌ OFF"
    rows = [
        [InlineKeyboardButton(
            f"🎬 Starting Points: {settings['starting_points']}",
            callback_data=f"set_start:{group_id}")],
        [InlineKeyboardButton(
            f"⚠️ Penalty per Violation: {settings['penalty_points']}",
            callback_data=f"set_penalty:{group_id}")],
        [InlineKeyboardButton(
            f"🗑️ Auto-delete bad messages: {auto_del}",
            callback_data=f"set_toggle_delete:{group_id}")],
        [InlineKeyboardButton(
            f"🔇 Auto-mute at 0 points: {auto_mute}",
            callback_data=f"set_toggle_mute:{group_id}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"grp:{group_id}")],
    ]
    return InlineKeyboardMarkup(rows)


def confirm_reset(group_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("✅ Yes, reset & announce winners", callback_data=f"reset_do:{group_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"grp:{group_id}"),
        ]
    ]
    return InlineKeyboardMarkup(rows)


def back_button(group_id: int, to: str = "grp") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"{to}:{group_id}")]])
