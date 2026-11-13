"""Bot management operations for the Oxmit Web Management Panel.

Handles user querying, search and pagination, user banning/unbanning with active
task cancellation and cache invalidation, rate-limited broadcasting, and
dynamic runtime configuration.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .. import audit as audit_mod
from .. import permissions
from ..log import get_logger
from .security import OWNER_TELEGRAM_ID

log = get_logger("oxmit.panel.bot")


def _iso(dt: Any) -> str | None:
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt) if dt else None


async def list_bot_users(
    db: Any,
    query: str | None = None,
    status: str | None = None,
    page: int = 1,
    limit: int = 50,
) -> dict[str, Any]:
    """Retrieve paginated bot users enriched with job telemetry and moderation flags."""
    page = max(1, int(page))
    limit = max(1, min(100, int(limit)))
    offset = (page - 1) * limit

    where_clauses = ["TRUE"]
    args: list[Any] = []

    # Status filter
    if status:
        s = status.strip().lower()
        if s in ("blocked", "banned"):
            where_clauses.append("u.is_blocked = TRUE")
        elif s == "active":
            where_clauses.append("u.is_blocked = FALSE")
        elif s == "vip":
            where_clauses.append("u.is_vip = TRUE")
        elif s == "admin":
            where_clauses.append("u.is_admin = TRUE")

    # Search filter
    if query:
        q = query.strip().lstrip("@")
        if q.isdigit():
            args.append(int(q))
            where_clauses.append(f"u.tg_id = ${len(args)}")
        elif q:
            args.append(q.lower())
            where_clauses.append(
                f"(lower(u.username) LIKE '%' || ${len(args)} || '%' "
                f"OR lower(u.first_name) LIKE '%' || ${len(args)} || '%')"
            )

    where_sql = " AND ".join(where_clauses)

    count_sql = f"SELECT count(*) FROM users u WHERE {where_sql}"
    total = await db.fetchval(count_sql, *args) or 0

    args_page = list(args)
    args_page.append(limit)
    limit_idx = len(args_page)
    args_page.append(offset)
    offset_idx = len(args_page)

    data_sql = f"""
        SELECT u.tg_id, u.first_name, u.username, u.is_vip, u.is_blocked, u.is_admin,
               u.banned_at, u.ban_reason, u.last_seen_at, u.created_at, u.total_requests,
               count(j.id) FILTER (WHERE j.enqueued_at > now() - interval '24 hours') AS jobs24,
               count(j.id) FILTER (WHERE j.status IN ('queued','processing')) AS pending_jobs
        FROM users u LEFT JOIN jobs j ON j.requester_tg_id = u.tg_id
        WHERE {where_sql}
        GROUP BY u.tg_id
        ORDER BY u.last_seen_at DESC NULLS LAST, u.created_at DESC
        LIMIT ${limit_idx} OFFSET ${offset_idx}
    """
    rows = await db.fetch(data_sql, *args_page)

    users = []
    for r in rows:
        users.append(
            {
                "tg_id": r["tg_id"],
                "username": r["username"],
                "first_name": r["first_name"],
                "is_blocked": bool(r["is_blocked"]),
                "is_vip": bool(r["is_vip"]),
                "is_admin": bool(r["is_admin"]),
                "banned_at": _iso(r.get("banned_at")),
                "ban_reason": r.get("ban_reason"),
                "created_at": _iso(r.get("created_at")),
                "last_seen_at": _iso(r.get("last_seen_at")),
                "jobs_count": int(r.get("total_requests") or 0),
                "jobs24": int(r.get("jobs24") or 0),
                "pending_jobs": int(r.get("pending_jobs") or 0),
            }
        )

    return {
        "users": users,
        "total": int(total),
        "page": page,
        "limit": limit,
    }


async def ban_bot_user(
    db: Any,
    engine: Any,
    cfg: Any,
    tg_id: int,
    ban: bool | None = None,
    reason: str | None = None,
    actor: str = "owner",
    client_ip: str = "?",
) -> dict[str, Any]:
    """Ban or unban a user with cache invalidation and active job cancellation."""
    owner_id = getattr(cfg, "owner_telegram_id", None) or OWNER_TELEGRAM_ID
    if tg_id in (OWNER_TELEGRAM_ID, owner_id):
        raise PermissionError("Cannot ban the bot owner")

    if ban is None:
        curr = await db.fetchval("SELECT is_blocked FROM users WHERE tg_id = $1", tg_id)
        if curr is None:
            raise KeyError("User not found")
        ban_state = not bool(curr)
    else:
        ban_state = bool(ban)

    ban_reason = reason or ("banned_via_panel" if ban_state else None)

    updated = await db.fetchrow(
        """
        UPDATE users
        SET is_blocked = $2,
            banned_at = CASE WHEN $2 THEN now() ELSE NULL END,
            ban_reason = CASE WHEN $2 THEN $3 ELSE NULL END
        WHERE tg_id = $1
        RETURNING tg_id, is_blocked
        """,
        tg_id,
        ban_state,
        ban_reason,
    )
    if not updated:
        raise KeyError("User not found")

    # Invalidate in-memory caches
    permissions.invalidate_cache(tg_id)
    if hasattr(engine, "invalidate_lang"):
        engine.invalidate_lang(tg_id)
    if hasattr(engine, "invalidate_tiers"):
        engine.invalidate_tiers()

    # Cancel active and queued jobs if user is banned
    if ban_state:
        try:
            jobs = await db.fetch(
                "SELECT * FROM jobs WHERE requester_tg_id = $1 AND status IN ('queued', 'processing')",
                tg_id,
            )
            for j in jobs:
                try:
                    await engine.cancel_job(j, by_admin=True, reason="user_banned")
                except Exception as exc:
                    log.warning("Failed to cancel job %s for banned user %s: %s", j.get("id"), tg_id, exc)
            await db.execute(
                "UPDATE intake_drafts SET status = 'cancelled' WHERE tg_id = $1 AND status IN ('waiting', 'awaiting_name')",
                tg_id,
            )
        except Exception as exc:
            log.warning("Exception during post-ban cleanup: %s", exc)

    await audit_mod.log_action(
        db,
        actor,
        "admin",
        "user.ban",
        tg_id,
        f"blocked={ban_state} reason={ban_reason}",
        "web",
        client_ip,
    )

    return {"status": "ok", "tg_id": tg_id, "is_blocked": ban_state}


class BroadcastManager:
    """Manages web broadcast tasks with progress tracking and cooperative cancellation."""

    def __init__(self, db: Any, engine: Any) -> None:
        self.db = db
        self.engine = engine
        self.tasks: dict[str, dict[str, Any]] = {}
        self._stop_events: dict[str, asyncio.Event] = {}

    async def start_broadcast(
        self,
        message: str,
        parse_mode: str = "HTML",
        target: str = "all",
        actor: str = "owner",
    ) -> dict[str, Any]:
        """Launch background message broadcast."""
        message = (message or "").strip()
        if not message:
            raise ValueError("Broadcast message cannot be empty")

        broadcast_id = str(uuid.uuid4())
        where = "is_blocked = FALSE"
        if target == "vip":
            where += " AND is_vip = TRUE"
        elif target == "active":
            where += " AND last_seen_at > now() - interval '30 days'"

        try:
            rows = await self.db.fetch(
                f"SELECT tg_id FROM users WHERE {where} ORDER BY last_seen_at DESC NULLS LAST"
            )
            recipient_ids = [r["tg_id"] for r in rows]
        except Exception:
            recipient_ids = []

        stop_event = asyncio.Event()
        self._stop_events[broadcast_id] = stop_event

        info: dict[str, Any] = {
            "broadcast_id": broadcast_id,
            "status": "running",
            "target": target,
            "total": len(recipient_ids),
            "sent": 0,
            "failed": 0,
            "skipped": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "error": None,
        }
        self.tasks[broadcast_id] = info

        async def _run() -> None:
            try:
                bot = getattr(self.engine, "bot", None)
                pm = None if parse_mode.lower() == "plain" else parse_mode
                for tg_id in recipient_ids:
                    if stop_event.is_set():
                        info["status"] = "stopped"
                        break
                    try:
                        if bot and hasattr(bot, "send_message"):
                            await bot.send_message(tg_id, message, parse_mode=pm)
                        info["sent"] += 1
                    except Exception as exc:
                        log.debug("Broadcast send error for user %s: %s", tg_id, exc)
                        info["failed"] += 1
                    # Polite rate limit (~25 messages/sec)
                    await asyncio.sleep(0.04)

                if info["status"] == "running":
                    info["status"] = "completed"
            except Exception as exc:
                info["status"] = "failed"
                info["error"] = str(exc)
            finally:
                info["completed_at"] = datetime.now(timezone.utc).isoformat()
                self._stop_events.pop(broadcast_id, None)

        asyncio.create_task(_run())
        return {
            "status": "started",
            "broadcast_id": broadcast_id,
            "recipients_count": len(recipient_ids),
        }

    def get_broadcast(self, broadcast_id: str) -> dict[str, Any] | None:
        """Fetch live broadcast status."""
        return self.tasks.get(broadcast_id)

    def stop_broadcast(self, broadcast_id: str) -> bool:
        """Cooperatively abort active broadcast."""
        stop_event = self._stop_events.get(broadcast_id)
        if stop_event:
            stop_event.set()
            task = self.tasks.get(broadcast_id)
            if task and task["status"] == "running":
                task["status"] = "stopped"
            return True
        return False


async def get_bot_config(db: Any, state: Any) -> dict[str, Any]:
    """Retrieve runtime configuration toggles."""
    config: dict[str, Any] = {
        "access_mode": str(getattr(state, "access_mode", "private")).strip('"'),
        "paused": getattr(state, "paused", False),
        "global_thumb": getattr(state, "global_thumb", None) is not None,
        "global_thumb_path": getattr(state, "global_thumb", None),
    }
    try:
        rows = await db.fetch("SELECT key, value FROM app_config")
        for r in rows:
            val = r["value"]
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except Exception:
                    pass
                if isinstance(val, str):
                    val = val.strip('"')
            config[r["key"]] = val
    except Exception:
        pass
    if "access_mode" in config and isinstance(config["access_mode"], str):
        config["access_mode"] = config["access_mode"].strip('"')
    return config


async def update_bot_config(
    db: Any,
    state: Any,
    payload: dict[str, Any],
    actor: str = "owner",
    client_ip: str = "?",
) -> dict[str, Any]:
    """Persist dynamic configuration adjustments in app_config and memory."""
    if not isinstance(payload, dict):
        return {"status": "error", "error": "payload must be a dictionary"}

    updated: dict[str, Any] = {}
    if "key" in payload and "value" in payload:
        items = [(payload["key"], payload["value"])]
    elif "settings" in payload and isinstance(payload["settings"], dict):
        items = list(payload["settings"].items())
    else:
        items = [(k, v) for k, v in payload.items() if k not in ("csrf", "token")]

    for k, v in items:
        await db.set_config(k, v)
        updated[k] = v
        if k == "paused":
            state.paused = bool(v)
        elif k == "access_mode":
            state.access_mode = str(v).strip('"')
        elif k == "global_thumb_path":
            state.global_thumb = v

    await audit_mod.log_action(
        db,
        actor,
        "admin",
        "bot.config.update",
        None,
        str(updated),
        "web",
        client_ip,
    )

    return {"status": "ok", "updated": updated}
