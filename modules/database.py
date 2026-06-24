"""
modules/database.py - SQLite persistence layer for BY BOTS.

Responsibilities:
  - Create / migrate the `posts` and `meta` tables on first run.
  - Add performance index on post_id.
  - Check whether a post_id has already been processed (duplicate guard).
  - Persist newly processed posts.
  - Expose aggregate statistics (total posts, last scan time).
  - Retrieve recent posts for the /recent command.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

import config

logger = logging.getLogger(__name__)

# ── Schema ────────────────────────────────────────────────────────────────────
_CREATE_POSTS_TABLE = """
CREATE TABLE IF NOT EXISTS posts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id     TEXT    NOT NULL UNIQUE,
    author      TEXT    NOT NULL,
    post_url    TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    stored_at   TEXT    NOT NULL
);
"""

_CREATE_POST_ID_INDEX = """
CREATE INDEX IF NOT EXISTS idx_posts_post_id ON posts (post_id);
"""

_CREATE_META_TABLE = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


async def init_db() -> None:
    """Create tables and indexes if they don't exist. Safe to call multiple times."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(_CREATE_POSTS_TABLE)
        await db.execute(_CREATE_POST_ID_INDEX)
        await db.execute(_CREATE_META_TABLE)
        await db.commit()
    logger.info("Database initialised at '%s'.", config.DATABASE_PATH)


async def is_duplicate(post_id: str) -> bool:
    """Return True if *post_id* is already stored in the database."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM posts WHERE post_id = ? LIMIT 1", (post_id,)
        ) as cursor:
            return await cursor.fetchone() is not None


async def save_post(
    post_id: str,
    author: str,
    post_url: str,
    created_at: str,
) -> None:
    """Persist a processed post. Silently ignores duplicate inserts."""
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO posts (post_id, author, post_url, created_at, stored_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (post_id, author, post_url, created_at, now),
        )
        await db.commit()
    logger.debug("Saved post '%s' to database.", post_id)


async def get_total_posts() -> int:
    """Return the total number of posts stored in the database."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM posts") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_recent_posts(limit: int = 5) -> list[dict]:
    """Return the most recently stored posts as a list of dicts."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT post_id, author, post_url, created_at, stored_at "
            "FROM posts ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def set_meta(key: str, value: str) -> None:
    """Upsert a key/value pair in the meta table."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value)
        )
        await db.commit()


async def get_meta(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve a value from the meta table, returning *default* if absent."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        async with db.execute(
            "SELECT value FROM meta WHERE key = ? LIMIT 1", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default
