"""Security and authentication primitives for the Oxmit Web Management Panel.

Enforces strict owner-only authentication, dual-cookie compatibility
(`oxmit_session` and `oxmit_panel`), double-submit CSRF validation,
and Redis-backed sessions, one-time OTP tokens, and distributed login rate-limiting.
"""
from __future__ import annotations

import functools
import hashlib
import hmac as hmac_mod
import inspect
import json
import os
import time
from typing import Any, Callable

from aiohttp import web
import redis.asyncio as aioredis

from ..log import get_logger

log = get_logger("oxmit.panel.security")

# Owner identity is configured exclusively via OWNER_TELEGRAM_ID in the
# protected environment. No hardcoded identifier, no first-admin fallback:
# when the variable is absent the owner-level panel API fails closed
# (SEC: canonical identity, V3 §25).

SESSION_KEY_PREFIX = "oxmit:session:"
OTP_KEY_PREFIX = "oxmit:otp:"
LOGIN_FAIL_PREFIX = "oxmit:login_fail:"
SESSION_TTL_SECONDS = 86400  # 24h sliding TTL
OTP_TTL_SECONDS = 180        # 3 min single-use
LOGIN_FAIL_WINDOW = 900      # 15 min lock window
LOGIN_FAIL_MAX = 5           # 5 attempts threshold

_redis_client: aioredis.Redis | None = None


def get_redis_client(redis_url: str | None = None) -> aioredis.Redis | None:
    """Get or initialize singleton Redis client for session and rate-limit storage."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    url = redis_url or os.environ.get("REDIS_URL", "")
    if not url:
        return None
    try:
        _redis_client = aioredis.from_url(url, decode_responses=True)
        return _redis_client
    except Exception as exc:
        log.warning("failed to connect redis client: %s", exc)
        return None


async def save_session_redis(sid: str, session_data: dict, r: aioredis.Redis | None = None) -> None:
    """Store session metadata in Redis with 24h TTL."""
    client = r or get_redis_client()
    if client is not None:
        try:
            key = f"{SESSION_KEY_PREFIX}{sid}"
            val = json.dumps(session_data)
            await client.set(key, val, ex=SESSION_TTL_SECONDS)
        except Exception as exc:
            log.warning("redis save session error: %s", exc)


async def load_session_redis(sid: str, r: aioredis.Redis | None = None) -> dict | None:
    """Load session from Redis and refresh 24h sliding TTL."""
    client = r or get_redis_client()
    if client is not None:
        try:
            key = f"{SESSION_KEY_PREFIX}{sid}"
            val = await client.get(key)
            if val:
                await client.expire(key, SESSION_TTL_SECONDS)
                return json.loads(val)
        except Exception as exc:
            log.warning("redis load session error: %s", exc)
    return None


async def delete_session_redis(sid: str, r: aioredis.Redis | None = None) -> None:
    """Purge session key from Redis upon logout or revocation."""
    client = r or get_redis_client()
    if client is not None:
        try:
            await client.delete(f"{SESSION_KEY_PREFIX}{sid}")
        except Exception:
            pass


async def save_otp_redis(token: str, otp_data: dict, r: aioredis.Redis | None = None) -> None:
    """Store one-time magic login token in Redis with 3 min TTL."""
    client = r or get_redis_client()
    if client is not None:
        try:
            key = f"{OTP_KEY_PREFIX}{token}"
            await client.set(key, json.dumps(otp_data), ex=OTP_TTL_SECONDS)
        except Exception as exc:
            log.warning("redis save otp error: %s", exc)


async def consume_otp_redis(token: str, r: aioredis.Redis | None = None) -> dict | None:
    """Single-use atomic GETDEL for one-time magic tokens."""
    client = r or get_redis_client()
    if client is not None:
        try:
            key = f"{OTP_KEY_PREFIX}{token}"
            val = await client.getdel(key)
            if val:
                return json.loads(val)
        except Exception:
            try:
                pipe = client.pipeline()
                pipe.get(key)
                pipe.delete(key)
                res = await pipe.execute()
                if res and res[0]:
                    return json.loads(res[0])
            except Exception as exc:
                log.warning("redis consume otp error: %s", exc)
    return None


async def check_login_rate_limit(ip: str, r: aioredis.Redis | None = None) -> tuple[bool, int]:
    """Check distributed login rate limit per IP. Returns (allowed, retry_after)."""
    client = r or get_redis_client()
    if client is not None:
        try:
            key = f"{LOGIN_FAIL_PREFIX}{ip}"
            cnt_str = await client.get(key)
            cnt = int(cnt_str) if cnt_str else 0
            if cnt >= LOGIN_FAIL_MAX:
                ttl = await client.ttl(key)
                return False, max(1, ttl)
            return True, 0
        except Exception as exc:
            log.warning("redis check login rate limit error: %s", exc)
    return True, 0


async def record_login_failure(ip: str, r: aioredis.Redis | None = None) -> int:
    """Atomic INCR + EXPIRE 900 on failed login attempt."""
    client = r or get_redis_client()
    if client is not None:
        try:
            key = f"{LOGIN_FAIL_PREFIX}{ip}"
            cnt = await client.incr(key)
            if cnt == 1 or cnt >= LOGIN_FAIL_MAX:
                await client.expire(key, LOGIN_FAIL_WINDOW)
            return cnt
        except Exception as exc:
            log.warning("redis record login failure error: %s", exc)
    return 1


async def reset_login_rate_limit(ip: str, r: aioredis.Redis | None = None) -> None:
    """Reset failed login count upon successful authentication."""
    client = r or get_redis_client()
    if client is not None:
        try:
            await client.delete(f"{LOGIN_FAIL_PREFIX}{ip}")
        except Exception:
            pass


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


async def resolve_session_async(request: web.Request) -> dict | None:
    """Async session resolver checking Redis first with fallback to in-memory sessions."""
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

    raw = request.cookies.get("oxmit_session") or request.cookies.get("oxmit_panel", "")
    if not raw:
        return None

    try:
        sid, exp_s, sig = raw.split(":", 2)
        exp = int(exp_s)
    except (ValueError, TypeError):
        return None

    if exp < int(time.time()):
        return None
    if not hmac_mod.compare_digest(_sign(token, f"{sid}:{exp}"), sig):
        return None

    # 1. Try Redis session store
    r_client = app.get("redis") or get_redis_client()
    session = await load_session_redis(sid, r_client)
    if session is not None:
        request["session"] = session
        return session

    # 2. Fallback to in-memory sessions
    sessions = app.get("panel_sessions")
    if sessions is not None:
        mem_session = sessions.get(sid)
        if mem_session is not None and mem_session.get("exp") == exp:
            request["session"] = mem_session
            return mem_session

    return None


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


@web.middleware
async def oxmit_session_middleware(request: web.Request, handler: Callable[..., Any]) -> web.Response:
    """Aiohttp middleware that pre-resolves Redis or memory sessions onto request['session']."""
    if "session" not in request:
        session = await resolve_session_async(request)
        if session:
            request["session"] = session
    return await handler(request)


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
        session = request.get("session")
        if session is None:
            session = await resolve_session_async(request) or get_session(request)
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
