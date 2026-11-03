"""Append-only audit trail for every admin action (panel v2, NEW-005).

Both the web panel and the Telegram admin panel funnel their mutating
actions through log_action() so operators can always answer "who did what,
when, from where". Insert-only by design: nothing updates or deletes rows.
"""
from __future__ import annotations

from .log import get_logger

log = get_logger("oxmit.audit")


async def log_action(db, actor: str, role: str, action: str, target=None,
                     details=None, source: str = "web", ip: str | None = None) -> None:
    """Record one admin action. Never raises into the caller's flow."""
    try:
        await db.execute(
            "INSERT INTO audit_log(actor, role, action, target, details, source, ip) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7)",
            actor, role, action,
            str(target) if target is not None else None,
            str(details) if details is not None else None,
            source, ip,
        )
    except Exception:  # noqa: BLE001 - audit must not break the action itself
        log.exception("audit insert failed", extra={"event": action, "detail": actor})


async def recent(db, limit: int = 20, action: str | None = None) -> list:
    try:
        return await db.fetch(
            "SELECT ts, actor, role, action, target, details, source, ip FROM audit_log "
            "WHERE ($1::text IS NULL OR action = $1) "
            "ORDER BY ts DESC LIMIT $2",
            action, max(1, min(int(limit), 200)),
        )
    except Exception:  # noqa: BLE001
        log.exception("audit read failed")
        return []
