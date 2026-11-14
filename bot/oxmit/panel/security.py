"""Security and authentication primitives for the Oxmit Web Management Panel.

Enforces strict owner-only authentication, dual-cookie compatibility
(`oxmit_session` and `oxmit_panel`), and double-submit CSRF validation.
"""
from __future__ import annotations

import functools
import hashlib
import hmac as hmac_mod
import inspect
import time
from typing import Any, Callable

from aiohttp import web

# Owner identity is configured exclusively via OWNER_TELEGRAM_ID in the
# protected environment. No hardcoded identifier, no first-admin fallback:
# when the variable is absent the owner-level panel API fails closed
# (SEC: canonical identity, V3 §25).


def _sign(token: str, data: str) -> str:
    """Compute HMAC-SHA256 signature for session cookie verification."""
    return hmac_mod.new(token.encode(), data.encode(), hashlib.sha256).hexdigest()


def _check_cookie(token: str, raw: str, sessions: dict) -> dict | None:
    """Validate the signed session cookie; return the session dict or None."""
    try:
        sid, exp_s, sig = raw.split(":", 2)
        exp = int(exp_s)
    except (ValueError, TypeError):
        return None
    if exp < int(time.time()):
        sessions.pop(sid, None)
        return None
    if not hmac_mod.compare_digest(_sign(token, f"{sid}:{exp}"), sig):
        return None
    session = sessions.get(sid)
    if session is None or session.get("exp") != exp:
        return None
    return session


def get_session(request: web.Request) -> dict | None:
    """Extract and validate the session cookie (oxmit_session or oxmit_panel).
    
    Caches the validated session on `request["session"]` to avoid redundant
    cryptographic checks within the same request lifecycle.
    """
    if "session" in request:
        return request["session"]

    app = getattr(request, "app", None)
    if app is None:
        return None

    token = app.get("panel_token")
    if not token and "cfg" in app:
        token = getattr(app["cfg"], "internal_panel_token", "")
    token = (token or "").strip()
    if not token:
        return None

    sessions = app.get("panel_sessions")
    if sessions is None:
        return None

    raw = request.cookies.get("oxmit_session") or request.cookies.get("oxmit_panel", "")
    if not raw:
        return None

    session = _check_cookie(token, raw, sessions)
    if session is not None:
        request["session"] = session
    return session


def is_owner_session(session: dict | None, configured_owner_id: int | None = None) -> bool:
    """Determine whether a session belongs to the verified bot owner.

    Fail closed: without an explicitly configured Owner identity
    (OWNER_TELEGRAM_ID) no session is ever treated as the owner. There is
    no hardcoded identifier and no first-administrator fallback.
    """
    if not session:
        return False
    if session.get("role") != "owner":
        return False
    if not configured_owner_id:
        return False

    tg_id = session.get("tg_id")
    actor = str(session.get("actor") or "")

    if tg_id == configured_owner_id:
        return True
    if actor == f"owner:{configured_owner_id}":
        return True

    return False


def validate_csrf(request: web.Request, session: dict) -> bool:
    """Enforce double-submit CSRF token validation on mutating requests."""
    if not session or not isinstance(session, dict):
        return False

    csrf_header = request.headers.get("X-CSRF") or request.headers.get("X-CSRF-Token")
    csrf_cookie = request.cookies.get("oxmit_csrf")

    if not csrf_header or not csrf_cookie:
        return False

    if not hmac_mod.compare_digest(csrf_header, csrf_cookie):
        return False

    session_csrf = session.get("csrf")
    if not session_csrf or not isinstance(session_csrf, str) or not hmac_mod.compare_digest(csrf_header, session_csrf):
        return False

    return True


def require_owner(handler: Callable[..., Any]) -> Callable[..., Any]:
    """Unified decorator for aiohttp request handlers.

    Enforces:
    - 401 Unauthorized if session is missing, expired, or tampered.
    - 403 Forbidden if user is authenticated but not the owner.
    - 403 Forbidden on mutating methods (POST, PUT, DELETE, PATCH) if CSRF is invalid.
    - Dynamically adapts to handlers expecting (request) or (request, session).
    """
    sig = inspect.signature(handler)
    params = list(sig.parameters.values())
    wants_session = (
        len(params) >= 2
        or any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params)
        or "session" in sig.parameters
    )

    @functools.wraps(handler)
    async def wrapped(request: web.Request, *args: Any, **kwargs: Any) -> web.Response:
        # 1. Authentication check
        session = get_session(request)
        if not session:
            return web.json_response({"error": "Unauthorized"}, status=401)

        # 2. Authorization check (fail closed without configured Owner)
        cfg = getattr(request, "app", {}).get("cfg") if hasattr(request, "app") else None
        configured_owner = getattr(cfg, "owner_telegram_id", None)
        if not is_owner_session(session, configured_owner):
            return web.json_response(
                {"error": "Forbidden: Owner access required"}, status=403
            )

        # 3. Double-Submit CSRF check on mutating methods
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            if not validate_csrf(request, session):
                return web.json_response(
                    {"error": "Invalid or missing CSRF token"}, status=403
                )

        # 4. Handler signature adaptation
        if wants_session:
            return await handler(request, session, *args, **kwargs)
        return await handler(request, *args, **kwargs)

    return wrapped
