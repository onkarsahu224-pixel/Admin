"""
All persistence lives here. We use aiosqlite so it plays nicely with the
async python-telegram-bot library (no blocking calls on the event loop).
One file (config.DB_PATH) is the whole database -> zero external services
needed, which keeps Wispbyte hosting simple.
"""

from __future__ import annotations

import aiosqlite
import datetime
from config import DB_PATH, DEFAULT_STARTING_POINTS, DEFAULT_PENALTY_POINTS

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    group_id INTEGER PRIMARY KEY,
    title TEXT,
    starting_points INTEGER DEFAULT 1000,
    penalty_points INTEGER DEFAULT 50,
    auto_delete INTEGER DEFAULT 1,
    auto_mute_at_zero INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS members (
    group_id INTEGER,
    user_id INTEGER,
    username TEXT,
    first_name TEXT,
    points INTEGER,
    violations INTEGER DEFAULT 0,
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS blacklist (
    group_id INTEGER,
    word TEXT,
    PRIMARY KEY (group_id, word)
);

CREATE TABLE IF NOT EXISTS rewards (
    group_id INTEGER,
    rank INTEGER,
    description TEXT,
    PRIMARY KEY (group_id, rank)
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER,
    month TEXT,
    user_id INTEGER,
    username TEXT,
    points INTEGER,
    rank INTEGER
);
"""


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


# ---------------------------------------------------------------- groups --
async def ensure_group(group_id: int, title: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO groups (group_id, title, starting_points, penalty_points,
                                    auto_delete, auto_mute_at_zero)
               VALUES (?, ?, ?, ?, 1, 0)
               ON CONFLICT(group_id) DO UPDATE SET title=excluded.title""",
            (group_id, title, DEFAULT_STARTING_POINTS, DEFAULT_PENALTY_POINTS),
        )
        await db.commit()


async def get_group_settings(group_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM groups WHERE group_id=?", (group_id,))
        row = await cur.fetchone()
        if row is None:
            await ensure_group(group_id)
            return await get_group_settings(group_id)
        return dict(row)


async def update_group_setting(group_id: int, field: str, value):
    assert field in {
        "starting_points",
        "penalty_points",
        "auto_delete",
        "auto_mute_at_zero",
        "title",
    }
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE groups SET {field}=? WHERE group_id=?", (value, group_id))
        await db.commit()


async def list_known_groups():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM groups")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# --------------------------------------------------------------- members --
async def ensure_member(group_id: int, user_id: int, username: str, first_name: str):
    settings = await get_group_settings(group_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO members (group_id, user_id, username, first_name, points, violations)
               VALUES (?, ?, ?, ?, ?, 0)
               ON CONFLICT(group_id, user_id) DO UPDATE SET
                    username=excluded.username, first_name=excluded.first_name""",
            (group_id, user_id, username or "", first_name or "", settings["starting_points"]),
        )
        await db.commit()


async def get_member(group_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM members WHERE group_id=? AND user_id=?", (group_id, user_id)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def find_member_by_username(group_id: int, username: str):
    username = username.lstrip("@").lower()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM members WHERE group_id=? AND lower(username)=?",
            (group_id, username),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def adjust_points(group_id: int, user_id: int, delta: int, count_violation: bool = False):
    async with aiosqlite.connect(DB_PATH) as db:
        if count_violation:
            await db.execute(
                """UPDATE members SET points = points + ?, violations = violations + 1
                   WHERE group_id=? AND user_id=?""",
                (delta, group_id, user_id),
            )
        else:
            await db.execute(
                "UPDATE members SET points = points + ? WHERE group_id=? AND user_id=?",
                (delta, group_id, user_id),
            )
        await db.commit()
        cur = await db.execute(
            "SELECT points FROM members WHERE group_id=? AND user_id=?", (group_id, user_id)
        )
        row = await cur.fetchone()
        return row[0] if row else None


async def set_points(group_id: int, user_id: int, value: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE members SET points=? WHERE group_id=? AND user_id=?",
            (value, group_id, user_id),
        )
        await db.commit()


async def get_leaderboard(group_id: int, limit: int = 15):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM members WHERE group_id=? ORDER BY points DESC LIMIT ?",
            (group_id, limit),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_rank(group_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT COUNT(*) + 1 FROM members
               WHERE group_id=? AND points > (
                   SELECT points FROM members WHERE group_id=? AND user_id=?)""",
            (group_id, group_id, user_id),
        )
        row = await cur.fetchone()
        return row[0] if row else None


# -------------------------------------------------------------- blacklist --
async def add_blacklist_words(group_id: int, words: list[str]):
    async with aiosqlite.connect(DB_PATH) as db:
        for w in words:
            await db.execute(
                "INSERT OR IGNORE INTO blacklist (group_id, word) VALUES (?, ?)",
                (group_id, w.lower().strip()),
            )
        await db.commit()


async def remove_blacklist_words(group_id: int, words: list[str]):
    async with aiosqlite.connect(DB_PATH) as db:
        for w in words:
            await db.execute(
                "DELETE FROM blacklist WHERE group_id=? AND word=?",
                (group_id, w.lower().strip()),
            )
        await db.commit()


async def get_blacklist(group_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT word FROM blacklist WHERE group_id=?", (group_id,))
        rows = await cur.fetchall()
        return [r[0] for r in rows]


# ---------------------------------------------------------------- rewards --
async def set_reward(group_id: int, rank: int, description: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO rewards (group_id, rank, description) VALUES (?, ?, ?)
               ON CONFLICT(group_id, rank) DO UPDATE SET description=excluded.description""",
            (group_id, rank, description),
        )
        await db.commit()


async def get_rewards(group_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM rewards WHERE group_id=? ORDER BY rank ASC", (group_id,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------- monthly reset --
async def archive_and_reset(group_id: int):
    """Save the current standings into history, then reset everyone's
    points back to the group's configured starting amount."""
    settings = await get_group_settings(group_id)
    month_label = datetime.date.today().strftime("%Y-%m")
    board = await get_leaderboard(group_id, limit=1000)

    async with aiosqlite.connect(DB_PATH) as db:
        for i, m in enumerate(board, start=1):
            await db.execute(
                """INSERT INTO history (group_id, month, user_id, username, points, rank)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (group_id, month_label, m["user_id"], m["username"], m["points"], i),
            )
        await db.execute(
            "UPDATE members SET points=?, violations=0 WHERE group_id=?",
            (settings["starting_points"], group_id),
        )
        await db.commit()

    return board[:3]
