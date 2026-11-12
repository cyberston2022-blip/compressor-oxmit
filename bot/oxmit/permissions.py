"""Owner-managed, backend-enforced feature permissions (multi-admin).

Model:
- OWNER bypasses every check (full access, by definition).
- ADMIN: per-feature grants stored in admin_permissions. Secure default:
  compression.use=true, every other feature=false until granted.
- VIP / regular users are OUTSIDE this system: their existing compression
  rights are unchanged; VIP never implies admin or owner.

Enforcement rule: every entry point (command, callback, submission) re-checks
via has_perm() — hidden buttons are a UX nicety, never the security boundary.
Permissions are cached briefly per process and invalidated by the Owner UI.

Feature keys (stable strings, add new ones without touching check sites):
    compression.use      admin processing features (profile grid, admin flows)
    thumbnail.use        personal thumbnail configure + use
    watermark.use        personal watermark configure + use
    caption.use          personal caption configure + use
    merge.use            video merge
    merge_compress.use   merge + compress
    forcesub.manage      mandatory channel membership settings (OWNER-ONLY by
                         default; granted per admin by the Owner, never part
                         of the default grants)
"""
from __future__ import annotations

import time

from .log import get_logger

log = get_logger("oxmit.permissions")

PERMS: tuple[str, ...] = (
    "compression.use",
    "thumbnail.use",
    "watermark.use",
    "caption.use",
    "merge.use",
    "merge_compress.use",
    "forcesub.manage",
)

PERM_LABELS_FA = {
    "compression.use": "فشرده‌سازی استاندارد",
    "thumbnail.use": "تامبنیل شخصی",
    "watermark.use": "واترمارک",
    "caption.use": "کپشن شخصی",
    "merge.use": "ادغام ویدیو",
    "merge_compress.use": "ادغام + فشرده‌سازی",
    "forcesub.manage": "مدیریت عضویت اجباری",
}

PERM_LABELS_EN = {
    "compression.use": "Standard compression",
    "thumbnail.use": "Personal thumbnail",
    "watermark.use": "Watermark",
    "caption.use": "Personal caption",
    "merge.use": "Video merge",
    "merge_compress.use": "Merge + compress",
    "forcesub.manage": "Mandatory membership settings",
}

# Granted to every admin unless explicitly revoked (secure-but-usable base).
DEFAULT_ADMIN_GRANTS: frozenset[str] = frozenset({"compression.use"})

_CACHE: dict[str, tuple[float, bool]] = {}
_CACHE_TTL_S = 5.0


def invalidate_cache(tg_id: int | None = None) -> None:
    """Drop cached decisions (Owner UI calls this after every change)."""
    if tg_id is None:
        _CACHE.clear()
    else:
        _CACHE.pop(f"{tg_id}", None)


async def is_owner(engine, tg_id: int) -> bool:
    return await engine.is_owner(tg_id)


async def has_perm(engine, tg_id: int, perm: str) -> bool:
    """Backend authorization for one feature key.

    Owner -> always True. Non-admin -> False (regular users never reach
    admin features; their normal compression flow does not call this).
    Admin -> explicit grant row wins; absent row falls back to the default
    set. Cache TTL 5s keeps the hot path cheap; Owner edits invalidate.
    """
    if perm not in PERMS:
        log.warning("unknown permission key", extra={"detail": perm})
        return False
    if await engine.is_owner(tg_id):
        return True
    if tg_id not in await engine.admin_ids():
        return False

    key = f"{tg_id}"
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _CACHE_TTL_S:
        grants = cached[1]
    else:
        rows = await engine.db.fetch(
            "SELECT perm, granted FROM admin_permissions WHERE tg_id = $1", tg_id)
        grants = {r["perm"]: r["granted"] for r in rows}
        _CACHE[key] = (now, grants)
    if perm in grants:
        return bool(grants[perm])
    return perm in DEFAULT_ADMIN_GRANTS


async def effective_perms(engine, tg_id: int) -> dict[str, bool]:
    """Full decision map for one admin (Owner UI + admin self-view)."""
    result: dict[str, bool] = {}
    owner = await engine.is_owner(tg_id)
    admin = owner or tg_id in await engine.admin_ids()
    for perm in PERMS:
        if not admin:
            result[perm] = False
        elif owner:
            result[perm] = True
        else:
            result[perm] = await has_perm(engine, tg_id, perm)
    return result
