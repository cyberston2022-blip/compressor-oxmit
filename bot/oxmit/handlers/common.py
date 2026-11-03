"""Shared handler helpers: user registration, admin checks."""

from __future__ import annotations

from aiogram.types import User


async def ensure_user(db, user: User):
    return await db.fetchrow(
        """
        INSERT INTO users(tg_id, first_name, username)
        VALUES ($1, $2, $3)
        ON CONFLICT (tg_id) DO UPDATE
        SET first_name = EXCLUDED.first_name, username = EXCLUDED.username,
            last_seen_at = now()
        RETURNING *
        """,
        user.id, user.first_name or "", user.username or "",
    )


async def is_admin(db, cfg, tg_id: int) -> bool:
    row = await db.fetchrow("SELECT is_admin FROM users WHERE tg_id = $1", tg_id)
    return bool(row and row["is_admin"]) or tg_id in cfg.admin_ids
