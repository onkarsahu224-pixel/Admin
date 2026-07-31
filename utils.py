"""Small shared helpers used across handlers."""

from __future__ import annotations

from telegram import Bot
from telegram.error import TelegramError


async def is_owner(bot: Bot, group_id: int, user_id: int) -> bool:
    """Only the Telegram group's creator counts as the 'owner' who gets
    full control over the bot for that group, per the project spec:
    everything stays in the owner's hands."""
    try:
        member = await bot.get_chat_member(group_id, user_id)
        return member.status == "creator"
    except TelegramError:
        return False


async def is_admin_or_owner(bot: Bot, group_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(group_id, user_id)
        return member.status in ("creator", "administrator")
    except TelegramError:
        return False


def set_pending(context, user_id: int, action: str, payload: dict | None = None):
    pending = context.application.bot_data.setdefault("pending", {})
    pending[user_id] = {"action": action, "payload": payload or {}}


def pop_pending(context, user_id: int):
    pending = context.application.bot_data.get("pending", {})
    return pending.pop(user_id, None)


def peek_pending(context, user_id: int):
    pending = context.application.bot_data.get("pending", {})
    return pending.get(user_id)
