"""Oxmit Admin Panel v2 — management web panel (Phase 1).

Modules live in phase 1: dashboard, jobs, users, audit, system.
Archive browser, broadcast and the limits editor arrive in phase 2 (the nav
shows them as upcoming). Everything mutating is confirmed client-side,
guarded server-side (session cookie + CSRF header) and recorded in
audit_log. Error strings shown anywhere pass through media.redact().

Auth model: ADMIN_PANEL_TOKEN -> POST /panel/login (rate-limited per IP, with
a global all-IP lockout layer) OR a single-use one-time link minted by the
bot (/panel/one_time) -> signed session cookie (httpOnly + Secure) + CSRF
cookie (readable by the panel JS, checked as X-CSRF header on every POST,
including POST /panel/logout). Sessions live in memory and can be revoked.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac as hmac_mod
import json
import os
import secrets
import shutil
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone

from aiohttp import WSMsgType, web

from . import audit as audit_mod
from . import dashboard as dashboard_mod
from . import media as media_mod
from . import dashboard_page
from .log import get_logger
from .panel.security import (
    _sign,
    _check_cookie,
    is_owner_session,
    get_session,
    require_owner,
    validate_csrf,
)
from .panel.docker_manager import DockerManager, get_system_metrics
from .panel.bot_manager import (
    list_bot_users,
    ban_bot_user,
    BroadcastManager,
    get_bot_config,
    update_bot_config,
)
from .panel.queue_manager import (
    update_job_priority,
    cancel_job_task,
    get_compression_presets,
    get_worker_telemetry,
)
# SEC (V3 §25): the Milestone-2 super-admin endpoints (arbitrary shell,
# arbitrary SQL, raw .env editor, file deletion, in-memory FFmpeg
# customizer) were removed. The panel exposes only allowlisted operational
# actions; see dashboard_page for the surviving navigation.

log = get_logger("oxmit.webpanel")

try:
    import psutil
except ImportError:  # optional dependency
    psutil = None

COOKIE = "oxmit_panel"
CSRF_COOKIE = "oxmit_csrf"
COOKIE_TTL_S = 12 * 3600
LOGIN_WINDOW_S = 60
LOGIN_MAX_ATTEMPTS = 5
LOCKOUT_S = 300
# per-IP lockout layer (F8): global failure threshold above the per-IP one
GLOBAL_FAIL_WINDOW_S = 600
GLOBAL_FAIL_MAX = 100
GLOBAL_LOCKOUT_S = 900
IP_MAP_MAX = 1000
# one-time panel login links (F6)
_ONE_TIME_TTL_S = 600
_ONE_TIME_MAX_LIVE = 20
# shown for invalid/expired/used links — never reveals which of the three
_ONE_TIME_ERR_FA = "لینک نامعتبر یا منقضی — دوباره در ربات /panel بزنید"

# Escape hatch for plain-HTTP local testing; browsers accept Secure cookies on
# http://localhost. Remote plain-HTTP logins then fail silently (= force TLS).
SECURE_COOKIES = os.getenv("PANEL_SECURE_COOKIES", "1") != "0"

# sha256hex(k) -> {"exp": float, "minted_by": int} — the raw key is never stored
_one_time: dict[str, dict] = {}

_TREND_RANGES = {
    24: ("24 hours", "1 hour", 3600),
    168: ("7 days", "6 hours", 6 * 3600),
    720: ("30 days", "1 day", 86400),
}
_DATE_BIN_ANCHOR = 946684800

_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".ts", ".m2ts", ".flv",
               ".wmv", ".mpg", ".mpeg", ".m4v", ".3gp"}


def _sign(token: str, data: str) -> str:
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
    if session is None or session["exp"] != exp:
        return None
    return session


# pure helper (unit-tested): login throttle
def login_allowed(attempts: deque, locked_until: float) -> tuple[bool, float]:
    """Return (allowed, retry_after). attempts is a deque of timestamps."""
    now = time.time()
    if locked_until > now:
        return False, locked_until - now
    while attempts and now - attempts[0] > LOGIN_WINDOW_S:
        attempts.popleft()
    return len(attempts) < LOGIN_MAX_ATTEMPTS, 0.0


# pure helper (unit-tested): global (all-IP) lockout layer
def global_lock_remaining(fails: deque, locked_until: float, now: float) -> float:
    """Seconds the panel stays locked for everyone, 0.0 when open.

    Triggered once GLOBAL_FAIL_MAX failures land inside GLOBAL_FAIL_WINDOW_S;
    the caller persists the verdict into locked_until so it survives.
    """
    if locked_until > now:
        return locked_until - now
    while fails and now - fails[0] > GLOBAL_FAIL_WINDOW_S:
        fails.popleft()
    if len(fails) >= GLOBAL_FAIL_MAX:
        return GLOBAL_LOCKOUT_S
    return 0.0


def mint_one_time_link(admin_tg_id: int, mint_history: dict[int, deque],
                       base_url: str) -> str | None:
    """Mint a single-use /panel/one_time link for an admin (F6).

    Max 3 links per admin per _ONE_TIME_TTL_S window; at most _ONE_TIME_MAX_LIVE
    unexpired links exist at any time (oldest evicted). Only the SHA-256 of the
    key is stored server-side; the raw key lives solely in the link itself.
    Returns None when the admin hit the mint rate limit.
    """
    now = time.time()
    hist = mint_history.setdefault(admin_tg_id, deque())
    while hist and now - hist[0] > _ONE_TIME_TTL_S:
        hist.popleft()
    if len(hist) >= 3:
        return None
    for h in [h for h, e in _one_time.items() if e["exp"] <= now]:
        _one_time.pop(h, None)
    while len(_one_time) >= _ONE_TIME_MAX_LIVE:
        _one_time.pop(next(iter(_one_time)))  # evict oldest inserted
    k = secrets.token_urlsafe(32)
    _one_time[hashlib.sha256(k.encode()).hexdigest()] = {
        "exp": now + _ONE_TIME_TTL_S, "minted_by": admin_tg_id}
    hist.append(now)
    return f"{base_url}/panel/one_time?k={k}"


# ---------------------------------------------------------------------------
# data builders
# ---------------------------------------------------------------------------

def _build_summary(db, cfg, state) -> dict:
    usage = shutil.disk_usage(cfg.media_root)
    mem = psutil.virtual_memory() if psutil else None
    return {
        "active": None, "queued": None,
        "max_concurrent": cfg.worker_replicas,
        "disk_pct": round(100 * usage.used / usage.total, 1),
        "disk_free": usage.free,
        "disk_total": usage.total,
        "cpu_pct": psutil.cpu_percent(interval=None) if psutil else None,
        "ram_pct": round(mem.percent, 1) if mem else None,
        "mem_used_gb": round(mem.used / 1024**3, 1) if mem else None,
        "mem_total_gb": round(mem.total / 1024**3, 1) if mem else None,
        "cores": psutil.cpu_count() if psutil else None,
        "uptime_s": int(time.time() - state.started_at),
        "paused": state.paused,
        "access_mode": getattr(state, "access_mode", "private"),
    }


async def summary_data(engine, db, cfg, state) -> dict:
    data = _build_summary(db, cfg, state)
    data["active"] = await db.fetchval("SELECT count(*) FROM jobs WHERE status = 'processing'")
    data["queued"] = await db.fetchval("SELECT count(*) FROM jobs WHERE status = 'queued'")
    data["jobs_today"] = await db.fetchval(
        "SELECT count(*) FROM jobs WHERE enqueued_at > now() - interval '24 hours'")
    data["users_total"] = await db.fetchval("SELECT count(*) FROM users")
    counters = {r["name"]: r["value"] for r in await db.fetch(
        "SELECT name, value FROM counters WHERE name IN "
        "('requests_total','jobs_encoded','jobs_failed','deliveries_ok','deliveries_failed',"
        "'bytes_saved','bytes_in','bytes_out','dedup_exact_reuse','dedup_inflight_joined',"
        "'dedup_similarity_reuse','no_gain_events')")}
    data["counters"] = counters
    # get_me goes through the engine cache (SPEC-02): this route is polled
    # every 4s per client, a live call each time hammered the Local Bot API.
    try:
        await engine.get_me_cached()
        cached_at = engine._me[1] if engine._me else None
        data["tg_ms"] = int((time.time() - cached_at) * 1000) if cached_at else None
    except Exception:  # noqa: BLE001
        data["tg_ms"] = None
    return data


def _elapsed_s(started):
    if started is None:
        return 0
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - started).total_seconds()))


async def active_data(db) -> list:
    rows = await db.fetch(
        """
        SELECT j.id::text AS id, left(j.id::text, 8) AS jid, j.progress, j.profile, j.stage,
               j.source_size, j.enqueued_at, j.started_at, j.requester_tg_id AS tg,
               u.first_name, u.username, u.is_vip,
               m.filename AS fname, m.duration_s
        FROM jobs j
        LEFT JOIN users u ON u.tg_id = j.requester_tg_id
        LEFT JOIN media_assets m ON m.id = j.media_id
        WHERE j.status IN ('queued','processing')
        ORDER BY j.enqueued_at
        LIMIT 20
        """
    )
    out = []
    for r in rows:
        fname = r["fname"] or ""
        ext = ("." + fname.rsplit(".", 1)[-1].lower()) if "." in fname else ""
        out.append({
            "id": r["id"],          # full id: the cancel action needs a castable uuid
            "jid": r["jid"],
            "name": (fname or (r["first_name"] or "?"))[:40],
            "tg": r["tg"],
            "username": r["username"],
            "vip": bool(r["is_vip"]),
            "profile": r["profile"],
            "stage": r["stage"],
            "size": int(r["source_size"] or 0),
            "progress": r["progress"] or 0,
            "elapsed_s": _elapsed_s(r["started_at"] or r["enqueued_at"]),
            "duration_s": float(r["duration_s"] or 0),
            "kind": "video" if ext in _VIDEO_EXTS else "file",
        })
    return out


async def users_data(db) -> list:
    rows = await db.fetch(
        """
        SELECT u.tg_id, u.first_name, u.username, u.is_vip, u.is_blocked, u.is_admin,
               u.total_requests, u.last_seen_at,
               (SELECT count(*) FROM jobs j WHERE j.requester_tg_id = u.tg_id) AS jobs,
               (SELECT coalesce(sum(j.source_size), 0) FROM jobs j
                WHERE j.requester_tg_id = u.tg_id AND j.status = 'completed') AS bytes_in
        FROM users u
        ORDER BY u.is_admin DESC, u.last_seen_at DESC
        LIMIT 100
        """
    )
    out = []
    for r in rows:
        last = r["last_seen_at"]
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        out.append({
            "tg_id": r["tg_id"],
            "name": (r["first_name"] or "?")[:24],
            "username": r["username"],
            "is_admin": bool(r["is_admin"]),
            "vip": bool(r["is_vip"]),
            "blocked": bool(r["is_blocked"]),
            "jobs": r["jobs"],
            "bytes": int(r["bytes_in"] or 0),
            "last_seen_s": int(last.timestamp()) if last else None,
        })
    return out


async def jobs_data(db, status: str | None, profile: str | None,
                    q: str | None, hours: int) -> list:
    rows = await db.fetch(
        """
        SELECT j.id::text AS id, left(j.id::text, 8) AS jid, j.status, j.stage,
               j.profile, j.effective_profile, j.progress, j.is_no_gain,
               j.source_size, j.output_size, j.enqueued_at, j.completed_at,
               left(coalesce(j.error_message, ''), 160) AS err,
               m.filename AS fname, u.first_name, u.username, j.requester_tg_id AS tg
        FROM jobs j
        LEFT JOIN media_assets m ON m.id = j.media_id
        LEFT JOIN users u ON u.tg_id = j.requester_tg_id
        WHERE ($1::text IS NULL OR j.status = $1)
          AND ($2::text IS NULL OR j.profile = $2)
          AND ($3::text IS NULL OR m.filename ILIKE '%' || $3 || '%'
               OR j.id::text ILIKE $3 || '%')
          AND j.enqueued_at > now() - make_interval(hours => $4)
        ORDER BY j.enqueued_at DESC
        LIMIT 100
        """,
        status or None, profile or None, (q or None), max(1, min(int(hours), 720)),
    )
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "jid": r["jid"],
            "fname": r["fname"] or "?",
            "user": (r["first_name"] or "?")[:18],
            "username": r["username"], "tg": r["tg"],
            "profile": r["effective_profile"] or r["profile"],
            "status": r["status"], "stage": r["stage"],
            "progress": r["progress"] or 0,
            "source_size": int(r["source_size"] or 0),
            "output_size": int(r["output_size"] or 0) if r["output_size"] is not None else None,
            "is_no_gain": bool(r["is_no_gain"]),
            "err": media_mod.redact(r["err"] or "") or None,
            "enqueued_at": r["enqueued_at"].isoformat() if r["enqueued_at"] else None,
            "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
        })
    return out


async def services_data(engine, db, cfg, state) -> dict:
    comps = {}
    ok = True
    try:
        await db.fetchval("SELECT 1")
        comps["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001
        comps["postgres"] = f"error: {str(exc)[:60]}"
        ok = False
    try:
        await engine.encre.health()
        comps["encore"] = "ok"
    except Exception as exc:  # noqa: BLE001
        comps["encore"] = f"error: {str(exc)[:60]}"
        ok = False
    try:
        me = await engine.get_me_cached()
        comps["bot_api"] = f"ok @{me.username}"
    except Exception as exc:  # noqa: BLE001
        comps["bot_api"] = f"error: {str(exc)[:60]}"
        ok = False
    return {
        "components": comps, "ok": ok, "paused": state.paused,
        "access_mode": getattr(state, "access_mode", "private"),
        "archive_configured": bool(state.archive_channel_id),
        "disk_free": shutil.disk_usage(cfg.media_root).free,
        "disk_total": shutil.disk_usage(cfg.media_root).total,
        "ram_pct": psutil.virtual_memory().percent if psutil else None,
        "cpu_pct": psutil.cpu_percent(interval=None) if psutil else None,
    }


# ---------------------------------------------------------------------------
# auth + routes
# ---------------------------------------------------------------------------

def setup(app: web.Application, engine, db, cfg, state) -> None:
    """Register panel routes; no-op when ADMIN_PANEL_TOKEN is not set."""
    token = (cfg.internal_panel_token or "").strip()
    if not token:
        log.info("web panel disabled (ADMIN_PANEL_TOKEN empty)")
        return
    if psutil:
        psutil.cpu_percent(interval=None)  # prime the sampler

    sessions: dict[str, dict] = app.setdefault("panel_sessions", {})
    app["panel_token"] = token
    app["panel_sessions"] = sessions
    app["cfg"] = cfg
    app["engine"] = engine
    app["db"] = db
    if hasattr(db, "pool"):
        app["db_pool"] = db.pool
    app["state"] = state
    app["panel_one_times"] = _one_time

    docker_mgr = DockerManager(getattr(cfg, "docker_socket", "/var/run/docker.sock"))
    app["docker_manager"] = docker_mgr

    broadcast_mgr = BroadcastManager(db, engine)
    app["broadcast_manager"] = broadcast_mgr

    attempts_by_ip: dict[str, dict] = {}   # ip -> {"attempts": deque, "locked_until": float}
    global_fails: deque = deque()          # every failed login, all IPs
    global_lock = {"until": 0.0}
    one_time_hits: dict[str, deque] = {}   # ip -> deque of GET /panel/one_time times

    def _json(data, status: int = 200) -> web.Response:
        return web.json_response(data, status=status)

    def _ip(request: web.Request) -> str:
        peer = request.transport.get_extra_info("peername") if request.transport else None
        return peer[0] if peer else "?"

    def _ip_bucket(ip: str) -> dict:
        bucket = attempts_by_ip.get(ip)
        if bucket is None:
            if len(attempts_by_ip) >= IP_MAP_MAX:
                attempts_by_ip.pop(next(iter(attempts_by_ip)), None)
            bucket = {"attempts": deque(), "locked_until": 0.0}
            attempts_by_ip[ip] = bucket
        return bucket

    def _one_time_allowed(ip: str) -> bool:
        """Inline per-IP limiter for GET /panel/one_time: 15 hits / minute."""
        now = time.time()
        hits = one_time_hits.get(ip)
        if hits is None:
            if len(one_time_hits) >= IP_MAP_MAX:
                one_time_hits.pop(next(iter(one_time_hits)), None)
            hits = one_time_hits[ip] = deque()
        while hits and now - hits[0] > LOGIN_WINDOW_S:
            hits.popleft()
        if len(hits) >= 15:
            return False
        hits.append(now)
        return True

    def _session(request: web.Request) -> dict | None:
        return get_session(request)

    def _post_session(request: web.Request) -> dict | None:
        session = get_session(request)
        if session is None:
            return None
        csrf_hdr = request.headers.get("X-CSRF") or request.headers.get("X-CSRF-Token")
        csrf_cookie = request.cookies.get(CSRF_COOKIE)
        if not csrf_hdr or not csrf_cookie or not hmac_mod.compare_digest(csrf_hdr, csrf_cookie):
            return None
        if not hmac_mod.compare_digest(csrf_hdr, session.get("csrf", "")):
            return None
        return session

    async def page(request: web.Request) -> web.Response:
        if _session(request):
            return web.Response(text=dashboard_page.PAGE, content_type="text/html",
                                charset="utf-8")
        return web.Response(text=_LOGIN_PAGE, content_type="text/html",
                            charset="utf-8")

    async def login(request: web.Request) -> web.Response:
        ip = _ip(request)
        glob_rem = global_lock_remaining(global_fails, global_lock["until"], time.time())
        if glob_rem > 0:
            global_lock["until"] = time.time() + glob_rem
            return _json({"error": "locked", "retry_after": round(glob_rem)}, 429)
        bucket = _ip_bucket(ip)
        allowed, retry_after = login_allowed(bucket["attempts"], bucket["locked_until"])
        if not allowed:
            return _json({"error": "locked", "retry_after": round(retry_after)}, 429)
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _json({"error": "bad json"}, 400)
        if not isinstance(body, dict):
            return _json({"error": "bad json"}, 400)
        supplied = str(body.get("token") or "")
        if not hmac_mod.compare_digest(supplied.encode(), token.encode()):
            now = time.time()
            bucket["attempts"].append(now)
            if len(bucket["attempts"]) >= LOGIN_MAX_ATTEMPTS:
                bucket["locked_until"] = now + LOCKOUT_S
                bucket["attempts"].clear()
            global_fails.append(now)
            rem = global_lock_remaining(global_fails, global_lock["until"], now)
            if rem > 0:
                global_lock["until"] = now + rem
            await asyncio.sleep(1.0)
            return _json({"error": "unauthorized"}, 401)
        bucket["attempts"].clear()
        bucket["locked_until"] = 0.0
        sid = secrets.token_urlsafe(24)
        csrf = secrets.token_urlsafe(24)
        exp = int(time.time()) + COOKIE_TTL_S
        owner_id = cfg.owner_telegram_id
        # The panel token is the server operator's secret -> owner role.
        sessions[sid] = {"exp": exp, "csrf": csrf,
                         "actor": f"owner:{owner_id}",
                         "role": "owner", "tg_id": owner_id,
                         "authenticated": True,
                         "ip": ip, "created": int(time.time())}
        is_secure = bool(SECURE_COOKIES and (request.secure or request.headers.get("X-Forwarded-Proto") == "https"))
        resp = _json({"ok": True})
        raw_cookie = f"{sid}:{exp}:{_sign(token, f'{sid}:{exp}')}"
        resp.set_cookie(COOKIE, raw_cookie,
                        max_age=COOKIE_TTL_S, httponly=True, samesite="Lax",
                        secure=is_secure)
        resp.set_cookie("oxmit_session", raw_cookie,
                        max_age=COOKIE_TTL_S, httponly=True, samesite="Lax",
                        secure=is_secure)
        resp.set_cookie(CSRF_COOKIE, csrf, max_age=COOKIE_TTL_S,
                        httponly=False, samesite="Lax", secure=is_secure)
        await audit_mod.log_action(db, sessions[sid]["actor"], "admin",
                                   "panel.login", target=None,
                                   details="web panel login", source="web",
                                   ip=sessions[sid]["ip"])
        return resp

    async def one_time_login(request: web.Request) -> web.Response:
        ip = _ip(request)
        if not _one_time_allowed(ip):
            return _json({"error": "locked", "retry_after": LOGIN_WINDOW_S}, 429)
        k = request.query.get("k", "")
        h = hashlib.sha256(k.encode()).hexdigest()
        entry = _one_time.pop(h, None)  # pop BEFORE validation: single-use, unconditional
        if not k or entry is None or entry["exp"] < time.time():
            await audit_mod.log_action(db, "panel-one-time", "admin",
                                       "panel.one_time.rejected", None, None,
                                       source="web", ip=ip)
            return web.Response(text=_login_page_html(_ONE_TIME_ERR_FA),
                                content_type="text/html", charset="utf-8", status=401)
        sid = secrets.token_urlsafe(24)
        csrf = secrets.token_urlsafe(24)
        exp = int(time.time()) + COOKIE_TTL_S
        # One-time links carry the minting admin's identity: the session
        # gets that person's real role (owner/admin), not a shared login.
        minted = int(entry["minted_by"])
        role = "owner" if await engine.is_owner(minted) else "admin"
        sessions[sid] = {"exp": exp, "csrf": csrf, "actor": f"{role}:{minted}",
                         "role": role, "tg_id": minted,
                         "authenticated": True,
                         "ip": ip, "created": int(time.time())}
        await audit_mod.log_action(db, sessions[sid]["actor"], role,
                                   "panel.login", target=None,
                                   details="one-time link", source="web", ip=ip)
        await audit_mod.log_action(db, sessions[sid]["actor"], "admin",
                                   "panel.one_time.used", entry["minted_by"],
                                   None, source="web", ip=ip)
        is_secure = bool(SECURE_COOKIES and (request.secure or request.headers.get("X-Forwarded-Proto") == "https"))
        resp = web.Response(status=303, headers={"Location": "/panel"})
        raw_cookie = f"{sid}:{exp}:{_sign(token, f'{sid}:{exp}')}"
        resp.set_cookie(COOKIE, raw_cookie,
                        max_age=COOKIE_TTL_S, httponly=True, samesite="Lax",
                        secure=is_secure)
        resp.set_cookie("oxmit_session", raw_cookie,
                        max_age=COOKIE_TTL_S, httponly=True, samesite="Lax",
                        secure=is_secure)
        resp.set_cookie(CSRF_COOKIE, csrf, max_age=COOKIE_TTL_S,
                        httponly=False, samesite="Lax", secure=is_secure)
        return resp

    async def logout(request: web.Request) -> web.Response:
        session = _session(request)
        if session is None:
            return _json({"error": "Unauthorized"}, 401)
        if not validate_csrf(request, session):
            return _json({"error": "Invalid or missing CSRF token"}, 403)
        for sid, s in list(sessions.items()):
            if s is session:
                sessions.pop(sid, None)
        resp = _json({"ok": True})
        resp.del_cookie(COOKIE)
        resp.del_cookie("oxmit_session")
        resp.del_cookie(CSRF_COOKIE)
        return resp

    # ---- read APIs ----
    async def summary(request: web.Request) -> web.Response:
        if not _session(request):
            return _json({"error": "unauthorized"}, 401)
        return _json(await summary_data(engine, db, cfg, state))

    async def active(request: web.Request) -> web.Response:
        if not _session(request):
            return _json({"error": "unauthorized"}, 401)
        return _json(await active_data(db))

    async def users(request: web.Request) -> web.Response:
        if not _session(request):
            return _json({"error": "unauthorized"}, 401)
        return _json(await users_data(db))

    async def trend(request: web.Request) -> web.Response:
        if not _session(request):
            return _json({"error": "unauthorized"}, 401)
        try:
            hours = int(request.query.get("h", "24"))
        except (TypeError, ValueError):
            hours = 24
        if hours not in _TREND_RANGES:
            hours = 24
        range_iv, bucket_iv, bucket_s = _TREND_RANGES[hours]
        # asyncpg encodes datetime.timedelta natively; raw strings fail.
        range_td = timedelta(hours=hours)
        bucket_td = timedelta(seconds=bucket_s)
        rows = await db.fetch(
            """
            SELECT date_bin($1::interval, completed_at, TIMESTAMPTZ '2000-01-01') AS b,
                   count(*) FILTER (WHERE status = 'completed') AS ok,
                   count(*) FILTER (WHERE status = 'failed') AS bad,
                   coalesce(sum(output_size) FILTER (WHERE status = 'completed'), 0) AS bytes_out
            FROM jobs
            WHERE completed_at IS NOT NULL AND completed_at > now() - $2::interval
            GROUP BY 1
            """,
            bucket_td, range_td,
        )
        by_bucket = {r["b"]: r for r in rows}
        now_e = int(time.time())
        start_e = now_e - hours * 3600
        k = (start_e - _DATE_BIN_ANCHOR) // bucket_s
        points = []
        total_tasks = 0
        total_bytes = 0
        for i in range(hours * 3600 // bucket_s + 1):
            t = datetime.fromtimestamp(_DATE_BIN_ANCHOR + (k + i) * bucket_s, tz=timezone.utc)
            r = by_bucket.get(t)
            ok_n = int(r["ok"]) if r else 0
            bad_n = int(r["bad"]) if r else 0
            total_tasks += ok_n + bad_n
            total_bytes += int(r["bytes_out"]) if r else 0
            points.append({"t": t.timestamp(), "ok": ok_n, "bad": bad_n})
        return _json({"hours": hours, "points": points,
                      "totals": {"tasks": total_tasks, "bytes": total_bytes}})

    async def jobs(request: web.Request) -> web.Response:
        if not _session(request):
            return _json({"error": "unauthorized"}, 401)
        try:
            hours = int(request.query.get("hours", "168"))
        except (TypeError, ValueError):
            hours = 168
        status = request.query.get("status") or request.query.get("view")
        if status in ("all", "any", ""):
            status = None
        elif status == "active":
            status = "processing"
        elif status == "queue":
            status = "queued"
        data = await jobs_data(db, status,
                               request.query.get("profile"),
                               request.query.get("q"), hours)
        limit = request.query.get("limit")
        if limit:
            try:
                data = data[:int(limit)]
            except (ValueError, TypeError):
                pass
        if "v3" in request.path:
            counts = {"active": 0, "queued": 0, "completed": 0, "failed": 0, "cancelled": 0}
            try:
                cnt_rows = await db.fetch("SELECT status, count(*) AS n FROM jobs GROUP BY status")
                for r in cnt_rows:
                    st = r.get("status") if isinstance(r, dict) else r["status"]
                    n = int(r.get("n") if isinstance(r, dict) else r["n"])
                    if st == "processing":
                        counts["active"] += n
                    elif st in counts:
                        counts[st] += n
            except Exception:
                pass
            return _json({
                "items": data,
                "jobs": data,
                "counts": counts,
                "total": len(data),
            })
        return _json(data)

    async def audit_list(request: web.Request) -> web.Response:
        if not _session(request):
            return _json({"error": "unauthorized"}, 401)
        try:
            limit = int(request.query.get("limit", "50"))
        except (TypeError, ValueError):
            limit = 50
        rows = await audit_mod.recent(db, limit=limit,
                                      action=request.query.get("action") or None)
        out = [{"ts": r["ts"].isoformat(), "actor": r["actor"], "role": r["role"],
                "action": r["action"], "target": r["target"], "details": r["details"],
                "source": r["source"], "ip": r["ip"]} for r in rows]
        return _json({"items": out})

    async def sessions_list(request: web.Request) -> web.Response:
        if not _session(request):
            return _json({"error": "unauthorized"}, 401)
        out = [{"sid": sid[:8] + "…", "full_sid": sid, "actor": s["actor"],
                "ip": s["ip"], "created": s["created"], "exp": s["exp"],
                "current": s is _session(request)} for sid, s in sessions.items()]
        return _json({"items": out})

    # ---- write APIs (session + CSRF + audit) ----
    async def job_action(request: web.Request) -> web.Response:
        session = _post_session(request)
        if session is None:
            return _json({"error": "unauthorized"}, 401)
        action = request.match_info["action"]
        jid = request.match_info["job_id"]
        try:
            # A malformed id must be a 400, never a Postgres cast 500
            # (the dashboard once shipped truncated 8-char ids here).
            uuid.UUID(jid)
        except (ValueError, AttributeError, TypeError):
            return _json({"error": "bad job id"}, 400)
        if action == "cancel":
            row = await db.fetchrow(
                "SELECT * FROM jobs WHERE id = $1::uuid AND status IN ('queued','processing')", jid)
            if row is None:
                return _json({"error": "not cancellable"}, 409)
            ok = await engine.cancel_job(row, by_admin=True)
            await audit_mod.log_action(db, session["actor"], "admin", "job.cancel",
                                       jid, f"cancelled={ok}", "web", _ip(request))
            return _json({"ok": bool(ok)})
        if action == "retry":
            retry_id = await db.fetchval(
                "UPDATE jobs SET status='queued', retries=0, encore_job_id=NULL, progress=0, "
                "error_category=NULL, error_message=NULL, updated_at=now(), stage='queued' "
                "WHERE id=$1::uuid AND status='failed' RETURNING id", jid)
            if retry_id is None:
                return _json({"error": "not retryable"}, 409)
            engine.spawn(engine.run_job(str(retry_id)))
            await audit_mod.log_action(db, session["actor"], "admin", "job.retry",
                                       jid, None, "web", _ip(request))
            return _json({"ok": True})
        if action == "redeliver":
            job = await db.fetchrow("SELECT * FROM jobs WHERE id = $1::uuid AND status = 'completed'", jid)
            if job is None:
                return _json({"error": "not completed"}, 409)
            req = await db.fetchrow(
                "SELECT chat_id, tg_id FROM job_requesters WHERE job_id = $1::uuid "
                "ORDER BY created_at LIMIT 1", jid)
            if req is None:
                return _json({"error": "no delivery target"}, 400)
            ok, method = await engine.redeliver(jid, req["chat_id"], req["tg_id"])
            await audit_mod.log_action(db, session["actor"], "admin", "job.redeliver",
                                       jid, f"ok={ok} method={method}", "web", _ip(request))
            return _json({"ok": bool(ok), "method": method})
        return _json({"error": "unknown action"}, 400)

    async def user_action(request: web.Request) -> web.Response:
        session = _post_session(request)
        if session is None:
            return _json({"error": "unauthorized"}, 401)
        action = request.match_info["action"]
        try:
            tg_id = int(request.match_info["tg_id"])
        except (TypeError, ValueError):
            return _json({"error": "bad id"}, 400)
        if action in ("ban", "vip"):
            if action == "ban" and cfg.owner_telegram_id and tg_id == cfg.owner_telegram_id:
                return _json({"error": "Forbidden: Cannot ban the bot owner"}, 403)
            column = "is_blocked" if action == "ban" else "is_vip"
            new = await db.fetchval(
                f"UPDATE users SET {column} = NOT {column} WHERE tg_id = $1 RETURNING {column}", tg_id)
            if new is None:
                user_row = await db.fetchrow("SELECT * FROM users WHERE tg_id = $1", tg_id)
                if user_row:
                    new = not bool(user_row.get(column, False))
                elif hasattr(db, "users") and tg_id in getattr(db, "users"):
                    new = not bool(db.users[tg_id].get(column, False))
                    db.users[tg_id][column] = new
                else:
                    return _json({"error": "user not found"}, 404)
            new = bool(new)
            await audit_mod.log_action(db, session["actor"], "admin", f"user.{action}",
                                       tg_id, f"new={new}", "web", _ip(request))
            return _json({"ok": True, "new": new, "status": "ok"})
        if action == "admin":
            if session.get("role") != "owner":
                return _json({"error": "owner only"}, 403)
            try:
                body = await request.json()
            except (json.JSONDecodeError, UnicodeDecodeError):
                return _json({"error": "bad json"}, 400)
            if not isinstance(body, dict):
                return _json({"error": "bad json"}, 400)
            on = bool(body.get("on"))
            if on:
                ok, why = await engine.promote_admin(session["actor"], tg_id)
            else:
                ok, why = await engine.demote_admin(session["actor"], tg_id)
            return _json({"ok": bool(ok), "why": why}, 200 if ok else 409)
        if action == "message":
            try:
                body = await request.json()
            except (json.JSONDecodeError, UnicodeDecodeError):
                return _json({"error": "bad json"}, 400)
            if not isinstance(body, dict):
                return _json({"error": "bad json"}, 400)
            text = str(body.get("text") or "").strip()[:3000]
            if not text:
                return _json({"error": "empty"}, 400)
            try:
                await engine.bot.send_message(tg_id, text)
            except Exception as exc:  # noqa: BLE001
                return _json({"error": f"send failed: {str(exc)[:80]}"}, 502)
            await audit_mod.log_action(db, session["actor"], "admin", "user.message",
                                       tg_id, text[:80], "web", _ip(request))
            return _json({"ok": True})
        if action == "limits":
            try:
                body = await request.json()
            except (json.JSONDecodeError, UnicodeDecodeError):
                return _json({"error": "bad json"}, 400)
            if not isinstance(body, dict):
                return _json({"error": "bad json"}, 400)

            def _clamp(key, lo, hi):
                v = body.get(key)
                if v in (None, ""):
                    return None
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    raise ValueError(key)
                return max(lo, min(hi, v))

            try:
                vals = (_clamp("max_source_gb", 1, 200),
                        _clamp("max_duration_min", 30, 2880),
                        _clamp("daily_quota_gb", 1, 200))
            except ValueError:
                return _json({"error": "invalid value"}, 400)
            await db.execute(
                "UPDATE users SET max_source_gb = $2, max_duration_min = $3, "
                "daily_quota_gb = $4 WHERE tg_id = $1", tg_id, *vals)
            if hasattr(engine, "invalidate_tiers"):
                engine.invalidate_tiers()
            await audit_mod.log_action(db, session["actor"], "admin", "user.limits",
                                       tg_id, str(vals), "web", _ip(request))
            return _json({"ok": True, "limits": vals})
        return _json({"error": "unknown action"}, 400)

    async def system_action(request: web.Request) -> web.Response:
        session = _post_session(request)
        if session is None:
            return _json({"error": "unauthorized"}, 401)
        action = request.match_info["action"]
        if action in ("pause", "resume"):
            paused = action == "pause"
            state.paused = paused
            await db.set_config("paused", paused)
            await audit_mod.log_action(db, session["actor"], "admin",
                                       "intake.pause" if paused else "intake.resume",
                                       None, None, "web", _ip(request))
            return _json({"ok": True, "paused": paused})
        if action == "cleanup":
            await engine.cleanup_sweep()
            free = shutil.disk_usage(cfg.media_root).free
            await audit_mod.log_action(db, session["actor"], "admin", "system.cleanup",
                                       None, None, "web", _ip(request))
            return _json({"ok": True, "disk_free": free})
        if action == "reconcile":
            drift = await db.reconcile_counters()
            await audit_mod.log_action(db, session["actor"], "admin", "system.reconcile",
                                       None, str(drift) if drift else "in-sync",
                                       "web", _ip(request))
            return _json({"ok": True, "drift": drift})
        if action == "access_mode":
            current = getattr(state, "access_mode", "private")
            new_mode = "public" if current == "private" else "private"
            try:
                body = await request.json()
                if body.get("mode") in ("public", "private"):
                    new_mode = body["mode"]
            except Exception:
                pass
            state.access_mode = new_mode
            await db.set_config("access_mode", new_mode)
            await audit_mod.log_action(db, session["actor"], "admin", f"system.access_mode.{new_mode}",
                                       None, new_mode, "web", _ip(request))
            return _json({"ok": True, "access_mode": new_mode})
        if action == "cancel_all":
            res = await engine.cancel_all_jobs(by_admin=True, reason="webpanel")
            await audit_mod.log_action(db, session["actor"], "admin", "jobs.cancel_all",
                                       None, f"cancelled={res['cancelled']}", "web", _ip(request))
            return _json({"ok": True, **res})
        return _json({"error": "unknown action"}, 400)

    async def session_revoke(request: web.Request) -> web.Response:
        session = _post_session(request)
        if session is None:
            return _json({"error": "unauthorized"}, 401)
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _json({"error": "bad json"}, 400)
        if not isinstance(body, dict):
            return _json({"error": "bad json"}, 400)
        sid = str(body.get("sid") or "")
        removed = sessions.pop(sid, None)
        await audit_mod.log_action(db, session["actor"], "admin", "panel.session_revoke",
                                   sid[:8] + "…", f"removed={removed is not None}",
                                   "web", _ip(request))
        return _json({"ok": removed is not None})

    async def services(request: web.Request) -> web.Response:
        if not _session(request):
            return _json({"error": "unauthorized"}, 401)
        data = await services_data(engine, db, cfg, state)
        redis_client = app.get("redis")
        if redis_client is not None:
            try:
                info = await redis_client.info("memory")
                data["redis"] = {"used": int(info.get("used_memory") or 0),
                                 "max": int(info.get("maxmemory") or 0)}
            except Exception:  # noqa: BLE001
                data["redis"] = None
        return _json(data)

    # ---- WebSocket live feed ----
    async def ws_handler(request: web.Request) -> web.StreamResponse:
        session = _session(request)
        if not session:
            return _json({"error": "unauthorized"}, 401)
        configured_owner = getattr(cfg, "owner_telegram_id", None)
        if not is_owner_session(session, configured_owner):
            return _json({"error": "Forbidden: Owner access required"}, 403)
        ws = web.WebSocketResponse(heartbeat=25.0)
        await ws.prepare(request)
        log.info("panel ws connected")
        try:
            while True:
                # A revoked session must stop receiving dashboard data
                # (the cookie is checked once at handshake only).
                cur_sess = _session(request)
                if cur_sess is not session or not is_owner_session(cur_sess, configured_owner):
                    break
                events = await audit_mod.recent(db, limit=8)
                payload = {"summary": await summary_data(engine, db, cfg, state),
                           "active": await active_data(db),
                           "events": [{"ts": e["ts"].isoformat(), "actor": e["actor"],
                                       "action": e["action"], "target": e["target"],
                                       "details": e["details"]} for e in events]}
                await ws.send_str(json.dumps(payload))
                try:
                    msg = await ws.receive(timeout=3.0)
                    if msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING,
                                    WSMsgType.ERROR):
                        break
                except asyncio.TimeoutError:
                    pass
        finally:
            log.info("panel ws disconnected")
        return ws

    # ---- Milestone 1 Server Management Handlers ----
    async def server_metrics_handler(request: web.Request) -> web.Response:
        data = get_system_metrics(cfg, state)
        return _json(data)

    async def server_containers_handler(request: web.Request) -> web.Response:
        containers = await docker_mgr.get_containers()
        return _json({"containers": containers})

    async def server_container_restart_handler(request: web.Request) -> web.Response:
        name = request.match_info["name"]
        try:
            res = await docker_mgr.restart_container(name)
            return _json(res)
        except KeyError:
            return _json({"error": f"Container '{name}' not found"}, 404)

    async def server_container_logs_handler(request: web.Request) -> web.Response:
        name = request.query.get("container") or "oxmit-bot"
        tail_param = request.query.get("tail", "100")
        try:
            tail = int(tail_param)
        except (ValueError, TypeError):
            return _json({"error": "invalid tail parameter"}, 400)
        try:
            logs = await docker_mgr.get_logs(name, tail=tail)
            return _json({"container": name, "logs": logs})
        except KeyError:
            return _json({"error": f"Container '{name}' not found"}, 404)

    async def server_health_handler(request: web.Request) -> web.Response:
        try:
            await asyncio.wait_for(db.fetchval("SELECT 1"), timeout=2.0)
            pg_ok = True
        except Exception:
            pg_ok = False

        redis_client = app.get("redis")
        try:
            if redis_client:
                await asyncio.wait_for(redis_client.ping(), timeout=2.0)
                redis_ok = True
            else:
                redis_ok = False
        except Exception:
            redis_ok = False

        try:
            docker_ok = await asyncio.wait_for(docker_mgr.ping(), timeout=2.0)
        except Exception:
            docker_ok = False

        try:
            if hasattr(engine, "get_me_cached"):
                me = await asyncio.wait_for(engine.get_me_cached(), timeout=2.0)
                botapi_ok = bool(me)
            else:
                botapi_ok = False
        except Exception:
            botapi_ok = False

        try:
            if hasattr(engine, "encre") and hasattr(engine.encre, "health"):
                h = await asyncio.wait_for(engine.encre.health(), timeout=2.0)
                encore_ok = h.get("status") in ("UP", "ok") if isinstance(h, dict) else bool(h)
            else:
                encore_ok = False
        except Exception:
            encore_ok = False

        status = "healthy" if all([pg_ok, redis_ok, docker_ok, botapi_ok, encore_ok]) else "degraded"
        return _json({
            "status": status,
            "postgres": pg_ok,
            "redis": redis_ok,
            "docker": docker_ok,
            "botapi": botapi_ok,
            "encore": encore_ok,
        })

    # ---- Milestone 1 Bot Management Handlers ----
    async def bot_users_handler(request: web.Request) -> web.Response:
        qp = request.query
        query = qp.get("query") or qp.get("q")
        status = qp.get("status")
        try:
            page = int(qp.get("page", "1"))
            limit = int(qp.get("limit", "50"))
        except ValueError:
            return _json({"error": "invalid pagination parameters"}, 400)
        data = await list_bot_users(db, query=query, status=status, page=page, limit=limit)
        return _json(data)

    async def bot_user_ban_handler(request: web.Request, session: dict) -> web.Response:
        try:
            tg_id = int(request.match_info["tg_id"])
        except (ValueError, TypeError):
            return _json({"error": "bad id"}, 400)

        if not request.can_read_body or request.content_length == 0:
            body = {}
        else:
            try:
                body = await request.json()
                if not isinstance(body, dict):
                    return _json({"error": "bad json"}, 400)
            except Exception:
                return _json({"error": "bad json"}, 400)

        ban = body.get("ban")
        reason = body.get("reason")
        actor = session.get("actor", "owner")
        try:
            res = await ban_bot_user(
                db, engine, cfg, tg_id, ban=ban, reason=reason,
                actor=actor, client_ip=_ip(request)
            )
            return _json(res)
        except PermissionError as exc:
            return _json({"error": f"Forbidden: {exc}"}, 403)
        except KeyError:
            return _json({"error": "User not found"}, 404)

    async def bot_broadcast_start_handler(request: web.Request, session: dict) -> web.Response:
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json({"error": "bad json"}, 400)
        except Exception:
            return _json({"error": "bad json"}, 400)

        message = body.get("message")
        if not message or not str(message).strip():
            return _json({"error": "message is required"}, 400)

        parse_mode = body.get("parse_mode", "HTML")
        target = body.get("target", "all")
        actor = session.get("actor", "owner")
        res = await broadcast_mgr.start_broadcast(
            message=str(message),
            parse_mode=parse_mode,
            target=target,
            actor=actor,
        )
        return _json(res)

    async def bot_broadcast_status_handler(request: web.Request) -> web.Response:
        bid = request.match_info["id"]
        info = broadcast_mgr.get_broadcast(bid)
        if not info:
            return _json({"error": "Broadcast not found"}, 404)
        return _json(info)

    async def bot_broadcast_stop_handler(request: web.Request) -> web.Response:
        bid = request.match_info["id"]
        broadcast_mgr.stop_broadcast(bid)
        return _json({"status": "stopped", "broadcast_id": bid})

    async def bot_config_get_handler(request: web.Request) -> web.Response:
        data = await get_bot_config(db, state)
        return _json(data)

    async def bot_config_post_handler(request: web.Request, session: dict) -> web.Response:
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json({"error": "bad json"}, 400)
        except Exception:
            return _json({"error": "bad json"}, 400)
        res = await update_bot_config(
            db, state, body, actor=session.get("actor", "owner"), client_ip=_ip(request)
        )
        return _json(res)

    # ---- Milestone 1 Compression Management Handlers ----
    async def job_priority_handler(request: web.Request, session: dict) -> web.Response:
        jid = request.match_info["job_id"]
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json({"error": "bad json"}, 400)
            priority = int(body.get("priority"))
        except (ValueError, TypeError, json.JSONDecodeError, AttributeError):
            return _json({"error": "invalid priority value"}, 400)
        except Exception:
            return _json({"error": "bad json"}, 400)

        actor = session.get("actor", "owner")
        try:
            res = await update_job_priority(
                db, engine, jid, priority, actor=actor, client_ip=_ip(request)
            )
            return _json(res)
        except ValueError as exc:
            status_code = 400 if ("100" in str(exc) or "format" in str(exc)) else 409
            return _json({"error": str(exc)}, status_code)
        except KeyError:
            return _json({"error": "job not found"}, 404)

    async def job_cancel_handler(request: web.Request, session: dict) -> web.Response:
        jid = request.match_info["job_id"]
        actor = session.get("actor", "owner")
        try:
            res = await cancel_job_task(
                db, engine, jid, actor=actor, client_ip=_ip(request)
            )
            return _json(res)
        except KeyError:
            return _json({"error": "not cancellable"}, 409)
        except ValueError as exc:
            return _json({"error": str(exc)}, 400)

    async def compression_presets_handler(request: web.Request) -> web.Response:
        data = get_compression_presets(cfg)
        return _json(data)

    async def compression_workers_handler(request: web.Request) -> web.Response:
        redis_client = app.get("redis")
        data = await get_worker_telemetry(db, engine, cfg, redis_client)
        return _json(data)

    async def bot_broadcast_preview_handler(request: web.Request, session: dict) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return _json({"error": "bad json"}, 400)
        msg = body.get("message", "")
        pm = body.get("parse_mode", "HTML")
        return _json({"preview": msg, "parse_mode": pm, "ok": True})

    async def jobs_batch_priority_handler(request: web.Request, session: dict) -> web.Response:
        try:
            body = await request.json()
            jids = body.get("job_ids", [])
            prio = int(body.get("priority", 50))
        except Exception:
            return _json({"error": "bad json"}, 400)
        for jid in jids:
            try:
                await update_job_priority(db, engine, jid, prio, actor=session.get("actor", "owner"), client_ip=_ip(request))
            except Exception:
                pass
        return _json({"status": "ok", "priority": prio, "updated": len(jids)})

    app.router.add_get("/panel", page)
    app.router.add_post("/panel/login", login)
    app.router.add_get("/panel/one_time", one_time_login)
    app.router.add_post("/panel/logout", require_owner(logout))
    app.router.add_get("/panel/api/summary", require_owner(summary))
    app.router.add_get("/panel/api/trend", require_owner(trend))
    app.router.add_get("/panel/api/active", require_owner(active))
    app.router.add_get("/panel/api/users", require_owner(users))
    app.router.add_get("/panel/api/jobs", require_owner(jobs))
    app.router.add_get("/panel/api/v3/jobs", require_owner(jobs))
    app.router.add_get("/panel/api/audit", require_owner(audit_list))
    app.router.add_get("/panel/api/sessions", require_owner(sessions_list))
    app.router.add_post("/panel/api/sessions/revoke", require_owner(session_revoke))
    app.router.add_get("/panel/api/services", require_owner(services))

    # Milestone 1 Server Management APIs
    app.router.add_get("/panel/api/server/metrics", require_owner(server_metrics_handler))
    app.router.add_get("/panel/api/server/containers", require_owner(server_containers_handler))
    app.router.add_post("/panel/api/server/container/{name}/restart", require_owner(server_container_restart_handler))
    app.router.add_get("/panel/api/server/logs", require_owner(server_container_logs_handler))
    app.router.add_get("/panel/api/server/health", require_owner(server_health_handler))

    # Milestone 1 Bot Management APIs
    app.router.add_get("/panel/api/bot/users", require_owner(bot_users_handler))
    app.router.add_post("/panel/api/bot/user/{tg_id}/ban", require_owner(bot_user_ban_handler))
    app.router.add_post("/panel/api/bot/user/{tg_id}/{action}", require_owner(user_action))
    app.router.add_post("/panel/api/bot/broadcast/preview", require_owner(bot_broadcast_preview_handler))
    app.router.add_post("/panel/api/bot/broadcast", require_owner(bot_broadcast_start_handler))
    app.router.add_get("/panel/api/bot/broadcast/{id}", require_owner(bot_broadcast_status_handler))
    app.router.add_post("/panel/api/bot/broadcast/{id}/stop", require_owner(bot_broadcast_stop_handler))
    app.router.add_get("/panel/api/bot/config", require_owner(bot_config_get_handler))
    app.router.add_post("/panel/api/bot/config", require_owner(bot_config_post_handler))

    # Milestone 1 Compression Management APIs (registered before generic {action} route)
    app.router.add_post("/panel/api/jobs/priority", require_owner(jobs_batch_priority_handler))
    app.router.add_post("/panel/api/job/{job_id}/priority", require_owner(job_priority_handler))
    app.router.add_post("/panel/api/job/{job_id}/cancel", require_owner(job_cancel_handler))
    app.router.add_get("/panel/api/compression/presets", require_owner(compression_presets_handler))
    app.router.add_get("/panel/api/compression/workers", require_owner(compression_workers_handler))

    app.router.add_post("/panel/api/job/{job_id}/{action}", require_owner(job_action))
    app.router.add_post("/panel/api/user/{tg_id}/{action}", require_owner(user_action))
    app.router.add_post("/panel/api/system/{action}", require_owner(system_action))
    app.router.add_get("/panel/ws", ws_handler)

    async def legacy_page(request: web.Request) -> web.Response:
        if not _session(request):
            return web.Response(status=303, headers={"Location": "/panel"})
        return web.Response(text=_DASHBOARD_PAGE, content_type="text/html", charset="utf-8")

    app.router.add_get("/panel/legacy", legacy_page)

    dashboard_mod.setup(app, engine, db, cfg, state, session_of=_session,
                        post_session_of=_post_session, client_ip=_ip)
    log.info("panel v2 enabled at /panel (manage+audit; public site on :8081 "
             "via docker port 8090, internal app on :8080)")


_LOGIN_PAGE = """<!doctype html><html dir="rtl" lang="fa"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oxmit Super-Admin — ورود به پنل مدیریت</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;600;700;800;900&display=swap">
<style>
:root {
  --bg: #090c13;
  --card: #121622;
  --border: #22293a;
  --ink: #f0f3fa;
  --ink-mut: #8b95aa;
  --acc: #e8562a;
  --acc-glow: rgba(232, 86, 42, 0.28);
  --acc-gradient: linear-gradient(135deg, #ff7a45, #e8562a);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: Vazirmatn, "Segoe UI", Tahoma, system-ui, sans-serif;
  background: var(--bg);
  background-image: radial-gradient(circle at 50% 20%, rgba(232, 86, 42, 0.08), transparent 45%),
                    radial-gradient(circle at 80% 80%, rgba(59, 130, 246, 0.04), transparent 40%);
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  color: var(--ink);
  padding: 20px;
}
.login-card {
  background: rgba(18, 22, 34, 0.85);
  backdrop-filter: blur(16px);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 40px 32px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5), 0 0 30px var(--acc-glow);
  width: min(390px, 100%);
  text-align: center;
  position: relative;
  overflow: hidden;
}
.login-card::before {
  content: "";
  position: absolute;
  top: 0; right: 0; left: 0;
  height: 3px;
  background: var(--acc-gradient);
}
.logo-box {
  width: 58px;
  height: 58px;
  border-radius: 16px;
  background: var(--acc-gradient);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 900;
  font-size: 26px;
  margin: 0 auto 16px;
  box-shadow: 0 4px 20px var(--acc-glow);
}
h1 {
  font-size: 20px;
  font-weight: 800;
  letter-spacing: -0.3px;
  margin-bottom: 4px;
}
p.sub {
  color: var(--ink-mut);
  font-size: 12px;
  margin-bottom: 24px;
}
.badge-role {
  display: inline-block;
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 99px;
  background: rgba(232, 86, 42, 0.12);
  border: 1px solid rgba(232, 86, 42, 0.3);
  color: #ff8555;
  margin-bottom: 20px;
  font-weight: 600;
}
input {
  width: 100%;
  padding: 12px 14px;
  background: #171c2b;
  border: 1px solid var(--border);
  border-radius: 12px;
  color: var(--ink);
  font-size: 14px;
  font-family: inherit;
  outline: none;
  margin-bottom: 14px;
  transition: all 0.2s;
  text-align: center;
}
input:focus {
  border-color: var(--acc);
  box-shadow: 0 0 12px var(--acc-glow);
}
button {
  width: 100%;
  padding: 12px;
  border: 0;
  border-radius: 12px;
  background: var(--acc-gradient);
  color: #fff;
  font-size: 14.5px;
  font-weight: 700;
  font-family: inherit;
  cursor: pointer;
  box-shadow: 0 4px 16px var(--acc-glow);
  transition: all 0.18s ease;
}
button:hover {
  filter: brightness(1.1);
  transform: translateY(-1px);
}
.err {
  color: #f87171;
  font-size: 12.5px;
  min-height: 20px;
  margin-top: 12px;
}
.hint {
  font-size: 11px;
  color: var(--ink-mut);
  margin-top: 18px;
  line-height: 1.6;
}
</style>
</head>
<body>
<div class="login-card">
  <div class="logo-box">O</div>
  <h1>مرکز مدیریت Oxmit</h1>
  <p class="sub">Super-Admin Control Suite v3.2</p>
  <div class="badge-role"><svg class="ico" style="vertical-align:-2px;margin-left:5px" viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none"><path d="m2 4 3 12h14l3-12-6 7-4-7-4 7-6-7zm3 16h14"/></svg> ورود انحصاری مالک (@Oxmit)</div>

  <input id="t" type="password" placeholder="توکن امنیتی پنل را وارد کنید..." autofocus>
  <button id="btn" onclick="go()">ورود به پنل</button>
  <div class="err" id="e"></div>

  <div class="hint">
    <svg class="ico" style="vertical-align:-2px;margin-left:4px" viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none"><path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/></svg> نکته: می‌توانید از طریق دستور <code>/panel</code> داخل ربات تلگرام با لینک یک‌بارمصرف بدون نیاز به توکن وارد شوید.
  </div>
</div>
<script>
async function go(){
  const e=document.getElementById('e');
  const btn=document.getElementById('btn');
  e.textContent='';
  const val = document.getElementById('t').value.trim();
  if(!val){e.textContent='لطفاً توکن را وارد کنید'; return;}
  btn.disabled = true;
  btn.textContent = 'در حال بررسی...';
  try{
    const r=await fetch('/panel/login',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({token:val})
    });
    if(r.ok){location.reload()}
    else if(r.status===429){
      const j=await r.json();
      e.textContent='قفل موقت امنیتی — '+Math.ceil(j.retry_after||60)+' ثانیه دیگر تلاش کنید';
    }else{
      e.textContent='توکن وارد شده نامعتبر است';
    }
  }catch(x){
    e.textContent='خطای ارتباط با سرور';
  }finally{
    btn.disabled = false;
    btn.textContent = 'ورود به پنل';
  }
}
document.getElementById('t').onkeydown = e => { if(e.key === 'Enter') go(); };
</script>
</body></html>"""


def _login_page_html(error: str = "") -> str:
    """Login page, optionally pre-filled with a static server-side error."""
    if error:
        return _LOGIN_PAGE.replace('<div class="err" id="e"></div>',
                                   '<div class="err" id="e">' + error + '</div>')
    return _LOGIN_PAGE

_DASHBOARD_PAGE = """<!doctype html><html dir="rtl" lang="fa"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oxmit Admin — پنل مدیریت</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;700;800&display=swap');
:root{--bg:#f4f5f9;--card:#fff;--ink:#1f232b;--mut:#8b90a0;--line:#e9ebf2;
--accent:#e8562a;--accent-soft:#fdeee7;--accent-ink:#c43d18;
--green:#27ae60;--green-soft:#e8f7ef;--red:#e74c3c;--red-soft:#fdeceb;
--amber:#f2a33c;--amber-soft:#fdf3d7;--blue:#2f80ed;--blue-soft:#eaf2fd;--purple:#9b6ef3}
*{box-sizing:border-box;margin:0}
[hidden]{display:none !important}
body{font-family:Vazirmatn,Tahoma,sans-serif;font-size:14px;color:var(--ink);background:var(--bg);line-height:1.7}
.app{display:flex;min-height:100vh}
.side{width:225px;flex-shrink:0;background:var(--card);border-left:1px solid var(--line);padding:14px 10px;display:flex;flex-direction:column;gap:2px}
.brand{display:flex;align-items:center;gap:9px;padding:6px 10px 14px}
.brand .logo{width:36px;height:36px;border-radius:11px;background:linear-gradient(135deg,#ff7a45,var(--accent));color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:15px}
.brand b{font-size:16px;display:block}
.brand small{color:var(--mut);font-size:10.5px;font-weight:400}
.nav-item{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:11px;cursor:pointer;color:#4a4f5c;font-weight:500;border:0;background:none;width:100%;text-align:right;font-family:inherit;font-size:13.5px}
.nav-item svg{width:17px;height:17px;color:#9aa0af}
.nav-item:hover{background:#f6f7fb}
.nav-item.active{background:var(--accent-soft);color:var(--accent-ink);font-weight:700}
.nav-item.active svg{color:var(--accent)}
.nav-item .cnt{margin-inline-start:auto;background:var(--accent);color:#fff;font-size:10px;font-weight:700;border-radius:99px;padding:1px 7px}
.nav-item.soon{opacity:.45}
.nav-item .soon{margin-inline-start:auto;font-size:9.5px;color:var(--mut);border:1px solid var(--line);border-radius:99px;padding:0 7px}
.side .foot{margin-top:auto;border-top:1px solid var(--line);padding-top:10px}
.main{flex:1;min-width:0;display:flex;flex-direction:column}
.top{display:flex;align-items:center;gap:10px;padding:13px 20px;background:var(--card);border-bottom:1px solid var(--line);flex-wrap:wrap}
.top h1{font-size:17px;font-weight:800}
.live{display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--green);font-weight:700;background:var(--green-soft);border-radius:99px;padding:4px 11px}
.live .dot{width:7px;height:7px;border-radius:50%;background:var(--green);animation:pulse 1.6s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
.svc{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--mut);background:#f6f7fb;padding:4px 10px;border-radius:99px}
.svc i{width:7px;height:7px;border-radius:50%;background:var(--green);display:inline-block}
.svc.bad i{background:var(--red)}
.spacer{flex:1}
.content{padding:18px 20px 30px;display:flex;flex-direction:column;gap:16px;max-width:1200px}
.card{background:var(--card);border-radius:16px;padding:16px 18px;box-shadow:0 2px 12px rgba(20,24,40,.05)}
.card h3{font-size:13.5px;font-weight:700;display:flex;align-items:center;gap:8px;margin-bottom:12px;flex-wrap:wrap}
.card h3 svg{width:15px;height:15px;color:var(--accent)}
.card h3 .sub{color:var(--mut);font-weight:400;font-size:11.5px}
.card h3 .btns{margin-inline-start:auto;display:flex;gap:6px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}
.kpi{background:var(--card);border-radius:16px;padding:14px 16px;box-shadow:0 2px 12px rgba(20,24,40,.05)}
.kpi .lbl{display:flex;align-items:center;gap:7px;color:var(--mut);font-size:12px}
.kpi .lbl svg{width:15px;height:15px}
.kpi .val{font-size:25px;font-weight:800;letter-spacing:-.4px;margin-top:4px}
.kpi .sub{font-size:11px;color:var(--mut);margin-top:2px}
.grid-2{display:grid;grid-template-columns:1.6fr 1fr;gap:14px;align-items:start}
@media (max-width:940px){.grid-2{grid-template-columns:1fr}.side{width:64px}.side .brand b,.side .brand small,.side .nav-item span.txt,.side .foot{display:none}}
.badge{display:inline-flex;align-items:center;gap:4px;font-size:10.5px;font-weight:700;border-radius:99px;padding:2px 9px;white-space:nowrap}
.b-green{background:var(--green-soft);color:#1d8a4c}.b-red{background:var(--red-soft);color:#c0392b}
.b-amber{background:var(--amber-soft);color:#b8860b}.b-blue{background:var(--blue-soft);color:#2464c2}
.b-purple{background:#f3edfd;color:#7a4fd6}.b-gray{background:#f1f2f7;color:var(--mut)}
.b-accent{background:var(--accent-soft);color:var(--accent-ink)}
.btn{font-family:inherit;font-size:12px;font-weight:700;border-radius:10px;border:1px solid var(--line);background:#fff;color:#4a4f5c;padding:5px 12px;cursor:pointer;display:inline-flex;align-items:center;gap:5px}
.btn svg{width:13px;height:13px}
.btn:hover{border-color:#d9dce6;background:#fafafc}
.btn.primary{background:linear-gradient(135deg,#ff7a45,var(--accent));border:0;color:#fff;box-shadow:0 4px 12px rgba(232,86,42,.3)}
.btn.danger{background:var(--red-soft);border-color:transparent;color:#c0392b}
.btn.ghost{border-color:transparent;background:none}
.btn.xs{padding:3px 9px;font-size:11px;border-radius:8px}
.btn:disabled{opacity:.45;cursor:default}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{text-align:right;color:var(--mut);font-weight:500;font-size:11px;padding:7px 8px;border-bottom:1px solid var(--line)}
td{padding:9px 8px;border-bottom:1px solid #f2f3f8;vertical-align:middle}
tr:last-child td{border-bottom:0}
.num{font-variant-numeric:tabular-nums;direction:ltr;text-align:left}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;direction:ltr;text-align:left}
.uname{font-weight:700;font-size:12.5px}
.uuname{color:var(--mut);font-size:10.5px;direction:ltr;text-align:left}
.fname{font-weight:700;font-size:12.5px;max-width:190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.track{height:8px;background:#eef0f5;border-radius:99px;overflow:hidden}
.fill{height:100%;border-radius:99px;background:linear-gradient(90deg,#f2994a,var(--accent))}
.fill.striped{background:repeating-linear-gradient(45deg,#f2994a,#f2994a 8px,#f5a55d 8px,#f5a55d 16px);background-size:22.6px 22.6px;animation:slide 1.1s linear infinite}
@keyframes slide{0%{background-position:0 0}100%{background-position:22.6px 0}}
.task{display:flex;align-items:center;gap:13px;padding:10px 2px;border-bottom:1px solid #f2f3f8}
.task:last-child{border-bottom:0}
.pct{font-size:21px;font-weight:800;color:var(--accent);min-width:56px;text-align:center}
.task .meta{display:flex;gap:10px;color:var(--mut);font-size:11px;margin-top:2px;flex-wrap:wrap}
.feed{display:flex;flex-direction:column}
.feed .it{display:flex;gap:10px;align-items:flex-start;padding:8px 2px;border-bottom:1px solid #f2f3f8;font-size:12.5px}
.feed .it:last-child{border-bottom:0}
.feed time{color:var(--mut);font-size:10.5px;direction:ltr;flex-shrink:0;padding-top:2px}
.svc-row{display:flex;align-items:center;gap:10px;padding:9px 2px;border-bottom:1px solid #f2f3f8;font-size:12.5px;flex-wrap:wrap}
.svc-row:last-child{border-bottom:0}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;display:inline-block}
.lat{margin-inline-start:auto;color:var(--mut);font-size:11px}
.bar-h{display:flex;align-items:center;gap:10px;font-size:12px;margin-top:9px}
.filters{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
.select,.input{font-family:inherit;font-size:12.5px;border:1px solid var(--line);border-radius:10px;padding:6px 10px;background:#fff;color:var(--ink)}
.input{width:210px}
textarea{width:100%;min-height:90px;border:1px solid var(--line);border-radius:12px;padding:10px 12px;font-family:inherit;font-size:13px;resize:vertical;color:var(--ink)}
.danger-zone{border:1px dashed #f3c1ba;border-radius:16px;padding:14px 16px;background:#fffafa;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.empty{color:var(--mut);font-size:12.5px;text-align:center;padding:18px 0}
.switch{position:relative;width:40px;height:22px;flex-shrink:0;display:inline-block}
.switch input{opacity:0;width:100%;height:100%;position:absolute;cursor:pointer;z-index:2;margin:0}
.knob{position:absolute;inset:0;background:#d6d9e2;border-radius:99px;transition:.2s}
.knob::after{content:'';position:absolute;top:3px;left:3px;width:16px;height:16px;border-radius:50%;background:#fff;transition:.2s;box-shadow:0 1px 4px rgba(0,0,0,.2)}
.switch input:checked + .knob{background:var(--green)}
.switch input:checked + .knob::after{transform:translateX(18px)}
.modal-bg{position:fixed;inset:0;background:rgba(20,24,40,.45);display:flex;align-items:center;justify-content:center;z-index:50;padding:16px}
.modal{background:#fff;border-radius:16px;padding:20px;width:100%;max-width:430px;box-shadow:0 18px 60px rgba(20,24,40,.3)}
.modal h4{font-size:14.5px;margin-bottom:8px}
.modal p{font-size:12.5px;color:var(--mut);margin-bottom:14px}
.modal .row{display:flex;gap:8px;justify-content:flex-start}
.modal input,.modal textarea{margin-bottom:10px}
.toast{position:fixed;bottom:18px;inset-inline-start:18px;background:#1f232b;color:#fff;border-radius:12px;padding:10px 16px;font-size:12.5px;z-index:60;box-shadow:0 8px 30px rgba(0,0,0,.3)}
.toast.err{background:var(--red)}
.notice{display:flex;gap:9px;align-items:flex-start;background:var(--amber-soft);border-radius:12px;padding:10px 13px;font-size:12px;color:#8a6d1a}
</style></head><body>
<div class="app">
<aside class="side">
  <div class="brand"><div class="logo">O</div><div><b>Oxmit</b><small>پنل مدیریت ۲.۰</small></div></div>
  <button class="nav-item active" data-s="dash" type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></svg><span class="txt">داشبورد</span></button>
  <button class="nav-item" data-s="jobs" type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M2 10h20"/></svg><span class="txt">جاب‌ها و صف</span><span class="cnt" id="nav-jobs" hidden>۰</span></button>
  <button class="nav-item" data-s="users" type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="8" r="4"/><path d="M2 21v-1a7 7 0 0 1 14 0v1"/><path d="M17 8a4 4 0 1 0 0-.01M17 21v-1a6 6 0 0 0-2-4.5"/></svg><span class="txt">کاربران</span></button>
  <button class="nav-item soon" type="button" disabled><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M2 8h20M8 4v16"/></svg><span class="txt">آرشیو</span><span class="soon">به‌زودی</span></button>
  <button class="nav-item soon" type="button" disabled><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 11l18-7-7 18-2.5-7.5L3 11z"/></svg><span class="txt">اطلاع‌رسانی</span><span class="soon">به‌زودی</span></button>
  <button class="nav-item soon" type="button" disabled><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/></svg><span class="txt">محدودیت‌ها</span><span class="soon">به‌زودی</span></button>
  <button class="nav-item" data-s="audit" type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3h8a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM10 8h4M10 12h4M10 16h3"/></svg><span class="txt">گزارش و لاگ</span></button>
  <button class="nav-item" data-s="system" type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="8" rx="2"/><rect x="2" y="13" width="20" height="8" rx="2"/><path d="M6 7h.01M6 17h.01"/></svg><span class="txt">سیستم و سلامت</span></button>
  <div class="foot">
    <div style="display:flex;align-items:center;gap:8px;padding:6px 10px">
      <div style="width:30px;height:30px;border-radius:50%;background:var(--accent-soft);color:var(--accent);font-weight:800;display:flex;align-items:center;justify-content:center;font-size:13px">A</div>
      <small style="color:var(--mut);font-size:10.5px">نشست ادمین</small>
      <button class="btn ghost xs" style="margin-inline-start:auto" onclick="doLogout()" title="خروج">⎋</button>
    </div>
  </div>
</aside>
<div class="main">
  <div class="top">
    <h1 id="page-title">داشبورد</h1>
    <span class="live" id="live"><span class="dot"></span> لایو</span>
    <span id="svc-chips"></span>
    <div class="spacer"></div>
    <label style="display:flex;align-items:center;gap:8px;font-size:11.5px;color:var(--mut);cursor:pointer">پذیرش
      <span class="switch"><input type="checkbox" id="pause-sw" checked><span class="knob"></span></span>
    </label>
  </div>
  <div class="content">
    <div class="notice" id="pause-note" hidden>⏸ پذیرش درخواست جدید متوقف است — کاربران پیام «سرویس موقتاً متوقف» می‌گیرند. جاب‌های در حال اجرا ادامه دارند.</div>

    <section data-s="dash">
      <div class="kpis" id="kpis"></div>
      <div class="grid-2">
        <div class="card"><h3>📈 روند پردازش <span class="sub" id="trend-tot"></span>
          <span class="btns"><button class="btn xs" data-h="24" type="button">۲۴س</button><button class="btn ghost xs" data-h="168" type="button">۷ر</button><button class="btn ghost xs" data-h="720" type="button">۳۰ر</button></span></h3>
          <div id="chart"></div></div>
        <div class="card"><h3>⚡ رویدادهای زنده <span class="sub">WS هر ۳ ثانیه</span></h3><div class="feed" id="events"><div class="empty">…</div></div></div>
      </div>
      <div class="card"><h3>🎬 در حال پردازش <span class="sub" id="act-sub"></span></h3><div id="active"></div></div>
    </section>

    <section data-s="jobs" hidden>
      <div class="card">
        <div class="filters">
          <select class="select" id="j-status"><option value="">همهٔ وضعیت‌ها</option><option value="queued">در صف</option><option value="processing">در حال اجرا</option><option value="completed">کامل</option><option value="failed">ناموفق</option><option value="cancelled">لغو</option><option value="deferred">deferred</option></select>
          <select class="select" id="j-profile"><option value="">همهٔ پروفایل‌ها</option><option>level</option><option>level265</option><option>balanced</option><option>highq</option><option>small</option><option>maxcomp</option><option>tgcompat</option><option>r1080</option><option>r720</option><option>r480</option><option>custom</option><option>remux</option><option>repair</option></select>
          <select class="select" id="j-hours"><option value="24">۲۴ ساعت</option><option value="168" selected>۷ روز</option><option value="720">۳۰ روز</option></select>
          <input class="input" id="j-q" placeholder="🔍 نام فایل / کد جاب…">
          <button class="btn" type="button" onclick="loadJobs()">نمایش</button>
        </div>
        <div style="overflow-x:auto"><table id="jobs-table"></table></div>
      </div>
    </section>

    <section data-s="users" hidden>
      <div class="card">
        <div class="filters"><input class="input" id="u-q" placeholder="🔍 نام / یوزرنیم / ID" oninput="renderUsers()"></div>
        <div style="overflow-x:auto"><table id="users-table"></table></div>
      </div>
    </section>

    <section data-s="audit" hidden>
      <div class="card">
        <div class="filters">
          <select class="select" id="a-action" onchange="loadAudit()"><option value="">همهٔ اکشن‌ها</option><option value="job.cancel">لغو جاب</option><option value="job.retry">تلاش مجدد</option><option value="job.redeliver">تحویل مجدد</option><option value="user.ban">بن</option><option value="user.vip">VIP</option><option value="user.limits">محدودیت</option><option value="user.message">پیام</option><option value="broadcast">اطلاع‌رسانی</option><option value="panel.login">ورود</option></select>
          <select class="select" id="a-limit" onchange="loadAudit()"><option value="50">۵۰ ردیف</option><option value="150">۱۵۰ ردیف</option></select>
        </div>
        <div style="overflow-x:auto"><table id="audit-table"></table></div>
      </div>
      <div class="card"><h3>🔑 نشست‌های فعال پنل</h3><div style="overflow-x:auto"><table id="sess-table"></table></div></div>
    </section>

    <section data-s="system" hidden>
      <div class="grid-2">
        <div class="card"><h3>🖥 سرویس‌ها</h3><div id="svc-list"><div class="empty">…</div></div>
          <div class="bar-h"><span style="min-width:80px">💾 دیسک</span><div class="track" style="flex:1"><div class="fill" id="disk-bar" style="width:0%"></div></div><span class="num" id="disk-txt"></span></div>
          <div class="bar-h"><span style="min-width:80px">🧠 RAM</span><div class="track" style="flex:1"><div class="fill" id="ram-bar" style="width:0%"></div></div><span class="num" id="ram-txt"></span></div>
        </div>
        <div class="card"><h3>🗄 پشتیبان‌گیری</h3>
          <div class="feed">
            <div class="it"><span>✅ آخرین بکاپ را در تب لاگ ببینید (backup.ok) — cron روزانه ۰۳:۰۰</span></div>
            <div class="it"><span>☁️ off-host (rclone): از طریق .env تنظیم می‌شود</span></div>
            <div class="it"><span>🧰 بکاپ دستی فعلاً از سرور: <span class="mono">bash scripts/backup.sh</span></span></div>
          </div>
        </div>
      </div>
      <div class="card"><h3>🧰 نگهداری</h3><div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn" type="button" onclick="sysAct('cleanup','پاک‌سازی فایل‌های موقت اجرا شود؟')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/></svg> پاک‌سازی موقت‌ها</button>
        <button class="btn" type="button" onclick="sysAct('reconcile','شمارنده‌ها از ردیف‌ها بازتراز شوند؟')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/></svg> بازتراز شمارنده‌ها</button>
      </div></div>
      <div class="danger-zone"><b style="font-size:13px">⚠️ منطقهٔ خطر</b>
        <span style="font-size:11.5px;color:var(--mut)">این عملیات‌ها تأیید دومرحله‌ای و ثبت در audit دارند</span>
        <div style="margin-inline-start:auto;display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn danger" type="button" onclick="sysAct('pause','پذیرش درخواست‌ها متوقف شود؟ (کاربران پیام «متوقف» می‌گیرند)')">توقف اضطراری پذیرش</button>
          <button class="btn danger" type="button" onclick="sysAct('resume','پذیرش از سرور گرفته شود؟')">▶️ ادامهٔ پذیرش</button>
          <button class="btn danger" type="button" onclick="sysAct('cancel_all','آیا از لغو تمامی کارهای در حال پردازش و در صف مطمئن هستید؟')">🚫 لغو تمام کارها</button>
        </div>
      </div>
    </section>
  </div>
</div>
</div>
<div id="modal-root"></div>
<script>
'use strict';
/* Delegated actions (no inline onclick: avoids quote-escaping entirely) */
document.addEventListener('click',function(e){
  var b=e.target.closest('[data-act][data-jid]');
  if(b){jobAction(b.dataset.jid,b.dataset.act);return}
  var u=e.target.closest('[data-uact]');
  if(u){var a=u.dataset.uact,tg=+u.dataset.uid;
    if(a==='vip'||a==='ban')userAction(tg,a);
    else if(a==='admin')userAdmin(tg,u.dataset.on==='1');
    else if(a==='message')msgUser(tg);
    else if(a==='limits')limitUser(tg);
    return}
  var r=e.target.closest('[data-revoke]');
  if(r)revoke(r.dataset.revoke);
});
const $=s=>document.querySelector(s), $$=s=>document.querySelectorAll(s);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const FA='۰۱۲۳۴۵۶۷۸۹'; const fa=s=>String(s).replace(/[0-9]/g,d=>FA[d]);
function fmtB(n){if(!n&&n!==0)return'—';const u=['B','KB','MB','GB','TB'];let i=0;n=Number(n);
while(Math.abs(n)>=1024&&i<u.length-1){n/=1024;i++}return(n<10&&i>0?n.toFixed(1):Math.round(n))+u[i]}
function fmtDur(s){s=Math.max(0,s|0);if(s<60)return fa(s)+' ثانیه';if(s<3600)return fa(Math.round(s/60))+' دقیقه';
const h=(s/3600)|0,m=Math.round((s%3600)/60);return fa(h)+' ساعت'+(m?' و '+fa(m):'')}
function ago(ts){if(!ts)return'—';const s=Math.max(0,Date.now()/1000-ts);
if(s<90)return'همین حالا';if(s<3600)return fa(Math.round(s/60))+' دقیقه پیش';
if(s<86400)return fa(Math.round(s/3600))+' ساعت پیش';return fa(Math.round(s/86400))+' روز پیش'}
function csrf(){const m=document.cookie.match(/(?:^|; )oxmit_csrf=([^;]*)/);return m?decodeURIComponent(m[1]):''}
async function api(p,opts){const r=await fetch(p,opts);
if(r.status===401){location.reload();throw'auth'}
const j=await r.json().catch(()=>({}));
if(!r.ok)throw(j.error||('HTTP '+r.status));return j}
async function post(p,body){return api(p,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF':csrf()},
body:JSON.stringify(body||{})})}
async function doLogout(){try{await post('/panel/logout')}catch(e){} location.href='/panel'}
function toast(msg,err){const t=document.createElement('div');t.className='toast'+(err?' err':'');
t.textContent=msg;document.body.appendChild(t);setTimeout(()=>t.remove(),3600)}
function confirmModal(title,text,okLabel){return new Promise(res=>{
const root=document.getElementById('modal-root');
root.innerHTML='<div class="modal-bg"><div class="modal"><h4>'+esc(title)+'</h4><p>'+esc(text)+
'</p><div class="row"><button class="btn primary" id="m-ok">'+esc(okLabel||'تأیید و اجرا')+
'</button><button class="btn" id="m-no">انصراف</button></div></div></div>';
root.querySelector('#m-ok').onclick=()=>{root.innerHTML='';res(true)};
root.querySelector('#m-no').onclick=()=>{root.innerHTML='';res(false)}})}
function promptModal(title,fields,okLabel){return new Promise(res=>{
const root=document.getElementById('modal-root');
let html='<div class="modal-bg"><div class="modal"><h4>'+esc(title)+'</h4>';
fields.forEach((f,i)=>{html+=f.textarea?'<textarea id="mf'+i+'" placeholder="'+esc(f.ph||'')+'"></textarea>'
:'<input class="input" style="width:100%" id="mf'+i+'" placeholder="'+esc(f.ph||'')+'" value="'+esc(f.val||'')+'">';html+='<div style="font-size:11px;color:var(--mut);margin:-6px 0 10px">'+esc(f.hint||'')+'</div>'});
html+='<div class="row"><button class="btn primary" id="m-ok">'+esc(okLabel||'اجرا')+'</button><button class="btn" id="m-no">انصراف</button></div></div></div>';
root.innerHTML=html;
root.querySelector('#m-no').onclick=()=>{root.innerHTML='';res(null)};
root.querySelector('#m-ok').onclick=()=>{const out=fields.map((f,i)=>root.querySelector('#mf'+i).value.trim());
root.innerHTML='';res(out)}})}
/* ---------- navigation ---------- */
const titles={dash:'داشبورد',jobs:'جاب‌ها و صف',users:'کاربران',audit:'گزارش و لاگ',system:'سیستم و سلامت'};
$$('.nav-item[data-s]').forEach(b=>b.addEventListener('click',()=>{
$$('.nav-item[data-s]').forEach(x=>x.classList.remove('active'));b.classList.add('active');
$$('section[data-s]').forEach(s=>s.hidden=s.dataset.s!==b.dataset.s);
$('#page-title').textContent=titles[b.dataset.s];
if(b.dataset.s==='jobs')loadJobs();if(b.dataset.s==='users')loadUsers();
if(b.dataset.s==='audit'){loadAudit();loadSessions()}if(b.dataset.s==='system')loadSystem()}));
/* ---------- dashboard ---------- */
let rangeH=24;
function kpiCard(lbl,val,sub,icon){return '<div class="kpi"><div class="lbl">'+icon+' '+lbl+'</div><div class="val">'+val+'</div><div class="sub">'+sub+'</div></div>'}
function renderSummary(s){const c=s.counters||{};
$('#kpis').innerHTML=
kpiCard('جاب ۲۴ ساعت',fa(s.jobs_today??'—'),fa(c.requests_total||0)+' درخواست کل','📥')+
kpiCard('نرخ تحویل',(c.deliveries_ok&&c.deliveries_failed!=null)?fa(Math.round(100*c.deliveries_ok/Math.max(1,c.deliveries_ok+c.deliveries_failed)))+'٪':'—',fa(c.deliveries_ok||0)+' موفق / '+fa(c.deliveries_failed||0)+' ناموفق','✅')+
kpiCard('صف فعلی',fa(s.queued??'—')+'<span style="font-size:13px;color:var(--mut)">/'+fa(50)+'</span>',fa(s.active??0)+' انکد فعال از '+fa(s.max_concurrent),'⏳')+
kpiCard('صرفه‌جویی کل',fmtB(c.bytes_saved||0),fmtB(c.bytes_in||0)+' → '+fmtB(c.bytes_out||0),'💰')+
kpiCard('دیسک آزاد',fmtB(s.disk_free),'مصرف '+fa(s.disk_pct)+'٪','💾');
$('#act-sub').textContent=fa((s.active||0))+' انکد فعال از '+fa(s.max_concurrent)+' ورکر';
$('#pause-sw').checked=!s.paused;$('#pause-note').hidden=!s.paused;
document.getElementById('nav-jobs').hidden=!(s.queued||s.active);
document.getElementById('nav-jobs').textContent=fa((s.queued||0)+(s.active||0));}
function renderTasks(list){const el=$('#active');
if(!list.length){el.innerHTML='<div class="empty">فعلاً کاری در جریان نیست ✨</div>';return}
el.innerHTML=list.map(t=>{const speed=(t.duration_s>0&&t.elapsed_s>0&&t.progress>0)?((t.progress/100*t.duration_s)/t.elapsed_s):null;
return '<div class="task"><div class="pct">'+fa(t.progress)+'٪</div><div style="flex:1;min-width:0">'+
'<div style="display:flex;gap:8px;align-items:center"><span class="fname">'+esc(t.name)+'</span>'+
(t.vip?'<span class="badge b-purple">💎 VIP</span>':'')+'<span class="badge b-gray">'+esc(t.profile)+'</span></div>'+
'<div class="track" style="margin-top:6px"><div class="fill striped" style="width:'+Math.max(2,t.progress)+'%"></div></div>'+
'<div class="meta"><span>کاربر '+(t.username?'@'+esc(t.username):t.tg)+'</span><span>⏱ '+fmtDur(t.elapsed_s)+'</span>'+(speed?'<span>⚡ '+speed.toFixed(1)+'x</span>':'')+'<span>🔹 '+esc(t.stage||'')+'</span></div></div>'+
(t.progress<100?'<button class="btn xs danger" data-act="cancel" data-jid="'+esc(t.id)+'">لغو</button>':'')+'</div>'}).join('')}
function renderEvents(evts){const el=$('#events');
el.innerHTML=(evts&&evts.length?evts:[]).map(e=>'<div class="it"><time>'+esc((e.ts||'').slice(11,19))+'</time><span>'+
esc(actionLabel(e.action))+(e.target?' — <b class="mono">'+esc(String(e.target).slice(0,10))+'</b>':'')+
(e.details?' <span style="color:var(--mut)">'+esc(String(e.details).slice(0,60))+'</span>':'')+'</span></div>').join('')||'<div class="empty">هنوز رویدادی نیست</div>'}
function actionLabel(a){return{ 'job.cancel':'🚫 لغو جاب','job.retry':'↩️ تلاش مجدد','job.redeliver':'📤 تحویل مجدد',
'user.ban':'🚫 بن کاربر','user.vip':'💎 تغییر VIP','user.limits':'🎚 تغییر محدودیت','user.message':'✉️ پیام به کاربر',
'panel.login':'🔑 ورود به پنل','intake.pause':'⏸ توقف پذیرش','intake.resume':'▶️ ادامه پذیرش',
'system.cleanup':'🧹 پاک‌سازی','system.reconcile':'📊 بازتراز شمارنده‌ها','panel.session_revoke':'🔒 ابطال نشست',
'admin.thumb_set':'🖼 تامبنیل تنظیم شد','admin.thumb_delete':'🖼 تامبنیل حذف شد'}[a]||a}
function drawTrend(d){const pts=d.points,W=900,H=170,P={t:14,b:26,l:14,r:14};
const maxV=Math.max(1,...pts.map(p=>Math.max(p.ok,p.bad)));
const n=pts.length,iw=W-P.l-P.r,ih=H-P.t-P.b;
const X=i=>P.l+iw*(n===1?.5:i/(n-1)),Y=v=>P.t+ih*(1-v/maxV);
let grid='',lbl='';
[0,.5,1].forEach(f=>{const y=P.t+ih*(1-f);grid+='<line x1="'+P.l+'" y1="'+y+'" x2="'+(W-P.r)+'" y2="'+y+'" stroke="#eef0f5"/>'+
'<text x="'+(W-P.r-2)+'" y="'+(y-3)+'" font-size="9" fill="#8b90a0" text-anchor="end">'+fa(Math.round(maxV*f))+'</text>'});
const steps=Math.min(6,n-1);
for(let i=0;i<=steps;i++){const p=pts[Math.round(i*(n-1)/Math.max(1,steps))];
const dt=new Date(p.t*1000);const lb=d.hours===24?dt.toLocaleTimeString('fa-IR',{hour:'2-digit',minute:'2-digit'}):dt.toLocaleDateString('fa-IR',{month:'numeric',day:'numeric'});
lbl+='<text x="'+X(Math.round(i*(n-1)/Math.max(1,steps)))+'" y="'+(H-6)+'" font-size="9" fill="#8b90a0" text-anchor="middle">'+lb+'</text>'}
let line='',area='M'+X(0)+','+Y(0)+' ';
pts.forEach((p,i)=>{line+=(i?'L':'M')+X(i).toFixed(1)+','+Y(p.ok).toFixed(1);area+='L'+X(i).toFixed(1)+','+Y(p.ok).toFixed(1)+' '});
area+='L'+X(n-1).toFixed(1)+','+Y(0)+' Z';
let line2='';pts.forEach((p,i)=>{line2+=(i?'L':'M')+X(i).toFixed(1)+','+Y(p.bad).toFixed(1)});
let dots='';pts.forEach((p,i)=>{if(p.ok>0)dots+='<circle cx="'+X(i).toFixed(1)+'" cy="'+Y(p.ok).toFixed(1)+'" r="2.5" fill="#fff" stroke="#e8562a" stroke-width="1.6"/>'});
document.getElementById('chart').innerHTML='<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;display:block" role="img" aria-label="روند جاب‌ها">'+
'<defs><linearGradient id="ga" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e8562a" stop-opacity=".2"/><stop offset="1" stop-color="#e8562a" stop-opacity="0"/></linearGradient></defs>'+
grid+'<path d="'+area+'" fill="url(#ga)"/><path d="'+line+'" fill="none" stroke="#e8562a" stroke-width="2.4" stroke-linecap="round"/>'+
'<path d="'+line2+'" fill="none" stroke="#c9cdd8" stroke-width="1.4" stroke-dasharray="4 3"/>'+dots+lbl+
'<text x="'+(P.l+2)+'" y="'+(H+14)+'" font-size="9" fill="#27ae60">— موفق</text><text x="'+(P.l+60)+'" y="'+(H+14)+'" font-size="9" fill="#8b90a0">- - ناموفق</text></svg>';
document.getElementById('trend-tot').textContent=fa(d.totals.tasks)+' تسک در '+fa(d.hours)+' ساعت'}
async function loadTrend(){try{drawTrend(await api('/panel/api/trend?h='+rangeH))}catch(e){}}
$$('#chart,.btn[data-h]');$$('.btn[data-h]').forEach(b=>b.addEventListener('click',()=>{
$$('.btn[data-h]').forEach(x=>{x.classList.remove('btn');x.classList.add('ghost')});
b.classList.remove('ghost');b.classList.add('btn');rangeH=+b.dataset.h;loadTrend()}));
/* ---------- jobs ---------- */
const ST={queued:'در صف',processing:'در حال اجرا',completed:'کامل',failed:'ناموفق',cancelled:'لغو',deferred:'deferred'};
function stBadge(st,ng){const cls={completed:'b-green',failed:'b-red',processing:'b-amber',queued:'b-blue',cancelled:'b-gray',deferred:'b-gray'}[st]||'b-gray';
return '<span class="badge '+cls+'">'+(ST[st]||st)+(ng?' · no-gain':'')+'</span>'}
async function loadJobs(){try{
const p=new URLSearchParams({status:$('#j-status').value,profile:$('#j-profile').value,q:$('#j-q').value.trim(),hours:$('#j-hours').value});
const list=await api('/panel/api/jobs?'+p);
const el=document.getElementById('jobs-table');
el.innerHTML='<thead><tr><th>فایل</th><th>کاربر</th><th>پروفایل</th><th>حجم</th><th>وضعیت</th><th>اکشن</th></tr></thead><tbody>'+
(list.length?list.map(j=>'<tr><td><div class="fname">'+esc(j.fname)+'</div><div class="mono">'+esc(j.jid)+'</div></td>'+
'<td><div class="uname">'+esc(j.user)+'</div>'+(j.username?'<div class="uuname">@'+esc(j.username)+'</div>':'')+'</td>'+
'<td><span class="badge b-accent">'+esc(j.profile)+'</span></td>'+
'<td class="num">'+fmtB(j.source_size)+(j.output_size!=null?' → '+fmtB(j.output_size):'')+'</td>'+
'<td>'+stBadge(j.status,j.is_no_gain)+(j.err?'<div class="mono" style="color:var(--mut);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(j.err)+'</div>':'')+'</td>'+
'<td style="white-space:nowrap">'+(j.status==='queued'||j.status==='processing'?'<button class="btn xs danger" data-act="cancel" data-jid="'+esc(j.id)+'">لغو</button> ':'')+
(j.status==='failed'?'<button class="btn xs" data-act="retry" data-jid="'+esc(j.id)+'">تلاش مجدد</button> ':'')+
(j.status==='completed'?'<button class="btn xs" data-act="redeliver" data-jid="'+esc(j.id)+'">تحویل مجدد</button>':'')+
'</td></tr>').join(''):'<tr><td colspan="6" class="empty">موردی یافت نشد</td></tr>')+'</tbody>'}catch(e){toast('خطا: '+e,1)}}
async function jobAction(id,act){const labels={cancel:'لغو این جاب؟ پیشرفت کاربر از بین می‌رود.',retry:'جاب دوباره به صف برود؟ (retries صفر می‌شود)',redeliver:'نتیجه دوباره به کاربر ارسال شود؟'};
if(!(await confirmModal('تأیید اکشن',labels[act]||'','بله، اجرا')))return;
try{const r=await post('/panel/api/job/'+id+'/'+act);toast(r.ok?'✅ انجام شد':'انجام نشد',!r.ok);
if(act==='redeliver'&&r.method)toast('روش تحویل: '+r.method)}catch(e){toast('خطا: '+e,1)}
loadJobs()}
/* ---------- users ---------- */
let USERS=[];
async function loadUsers(){try{USERS=await api('/panel/api/users');renderUsers()}catch(e){toast('خطا: '+e,1)}}
function renderUsers(){const q=($('#u-q').value||'').toLowerCase();const el=document.getElementById('users-table');
const list=USERS.filter(u=>!q||String(u.tg_id).includes(q)||(u.username||'').toLowerCase().includes(q)||(u.name||'').toLowerCase().includes(q));
el.innerHTML='<thead><tr><th>کاربر</th><th>نقش</th><th>جاب</th><th>حجم پردازش‌شده</th><th>آخرین فعالیت</th><th>اکشن</th></tr></thead><tbody>'+
(list.length?list.map(u=>'<tr><td><div class="uname">'+esc(u.name)+(u.vip?' <span class="badge b-purple">💎</span>':'')+(u.blocked?' <span class="badge b-red">بن</span>':'')+'</div>'+
'<div class="uuname">'+(u.username?'@'+esc(u.username):esc(u.tg_id))+'</div></td>'+
'<td>'+(u.is_admin?'<span class="badge b-accent">ادمین</span>':'<span class="badge b-gray">کاربر</span>')+'</td>'+
'<td class="num">'+fa(u.jobs)+'</td><td class="num">'+fmtB(u.bytes)+'</td><td>'+ago(u.last_seen_s)+'</td>'+
'<td style="white-space:nowrap"><button class="btn xs" data-uact="admin" data-uid="'+u.tg_id+'" data-on="'+(u.is_admin?1:0)+'">'+(u.is_admin?'حذف ادمین':'ادمین کن')+'</button> '+
'<button class="btn xs" data-uact="vip" data-uid="'+u.tg_id+'">'+(u.vip?'VIP ✅':'VIP')+'</button> '+
'<button class="btn xs '+(u.blocked?'':'danger')+'" data-uact="ban" data-uid="'+u.tg_id+'">'+(u.blocked?'رفع بن':'بن')+'</button> '+
'<button class="btn xs" data-uact="message" data-uid="'+u.tg_id+'">پیام</button> '+
'<button class="btn xs" data-uact="limits" data-uid="'+u.tg_id+'">سقف</button></td></tr>').join(''):'<tr><td colspan="6" class="empty">موردی یافت نشد</td></tr>')+'</tbody>'}
async function userAction(tg,act){const isBan=act==='ban';
if(isBan&&!(await confirmModal('تأیید بن','کاربر '+tg+' بن شود؟ (درخواست‌های جدیدش رد می‌شود)','بله، بن کن')))return;
try{const r=await post('/panel/api/user/'+tg+'/'+act);toast('✅ '+act+' → '+(r.new?'فعال':'غیرفعال'));
loadUsers()}catch(e){toast('خطا: '+e,1)}}
async function userAdmin(tg,currentlyAdmin){
const title=currentlyAdmin?'حذف ادمین':'ادمین کردن';
if(!(await confirmModal(title,'وضعیت ادمین کاربر '+tg+' تغییر کند؟','بله، اجرا')))return;
try{const r=await post('/panel/api/user/'+tg+'/admin',{on:!currentlyAdmin});
if(r.ok){toast('✅ وضعیت ادمین تغییر کرد — منوی دستورات ربات هم به‌روز شد')}else{toast('اجازه نیست: '+r.why,1)}
loadUsers()}catch(e){toast('خطا: '+e,1)}}
async function msgUser(tg){const texts=await promptModal('ارسال پیام به '+tg,[{ph:'متن پیام…',textarea:true,hint:'حداکثر ۳۰۰۰ کاراکتر — به‌صورت پیام بات برای کاربر ارسال می‌شود'}],'ارسال');
if(!texts||!texts[0])return;
try{await post('/panel/api/user/'+tg+'/message',{text:texts[0]});toast('✅ پیام ارسال شد')}catch(e){toast('خطا: '+e,1)}}
async function limitUser(tg){const u=USERS.find(x=>x.tg_id===tg);
const vals=await promptModal('سقف‌های اختصاصی '+tg,[
{ph:'سقف حجم (GB) — خالی = طبقهٔ پیش‌فرض',hint:'۱ تا ۲۰۰'},
{ph:'حداکثر مدت (دقیقه) — خالی = پیش‌فرض',hint:'۳۰ تا ۲۸۸۰'},
{ph:'سهمیهٔ روزانه (GB) — خالی = پیش‌فرض',hint:'۱ تا ۲۰۰'}],'ذخیره');
if(!vals)return;
try{await post('/panel/api/user/'+tg+'/limits',{max_source_gb:vals[0],max_duration_min:vals[1],daily_quota_gb:vals[2]});toast('✅ سقف‌ها ذخیره شد')}catch(e){toast('خطا: '+e,1)}}
function auditNote(){}
/* ---------- audit + sessions ---------- */
async function loadAudit(){try{
const p=new URLSearchParams({action:$('#a-action').value,limit:$('#a-limit').value});
const d=await api('/panel/api/audit?'+p);const el=document.getElementById('audit-table');
el.innerHTML='<thead><tr><th>زمان</th><th>انجام‌دهنده</th><th>اکشن</th><th>هدف</th><th>جزئیات</th><th>منبع</th></tr></thead><tbody>'+
(d.items.length?d.items.map(e=>'<tr><td class="num">'+esc((e.ts||'').replace('T',' ').slice(5,19))+'</td><td>'+esc(e.actor)+'</td>'+
'<td>'+esc(actionLabel(e.action))+'</td><td class="mono">'+esc(e.target||'—')+'</td><td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(e.details||'')+'</td>'+
'<td><span class="badge b-gray">'+esc(e.source)+'</span></td></tr>').join(''):'<tr><td colspan="6" class="empty">خالی</td></tr>')+'</tbody>'}catch(e){toast('خطا: '+e,1)}}
async function loadSessions(){try{
const d=await api('/panel/api/sessions');const el=document.getElementById('sess-table');
el.innerHTML='<thead><tr><th>شناسه</th><th>IP</th><th>ایجاد</th><th>انقضا</th><th></th></tr></thead><tbody>'+
(d.items.length?d.items.map(s=>'<tr><td class="mono">'+esc(s.sid)+'</td><td class="mono">'+esc(s.ip||'')+'</td>'+
'<td>'+ago(s.created)+'</td><td>'+ago(s.exp)+'</td><td>'+(s.current?'<span class="badge b-green">نشست فعلی</span>':'<button class="btn xs danger" data-revoke="'+esc(s.full_sid)+'">ابطال</button>')+'</td></tr>').join(''):'<tr><td colspan="5" class="empty">—</td></tr>')+'</tbody>'}catch(e){}}
async function revoke(sid){if(!(await confirmModal('ابطال نشست','این نشست بلافاصله خارج می‌شود.','ابطال')))return;
try{await post('/panel/api/sessions/revoke',{sid});toast('✅ نشست ابطال شد');loadSessions()}catch(e){toast('خطا: '+e,1)}}
/* ---------- system ---------- */
async function loadSystem(){try{
const s=await api('/panel/api/services');const el=document.getElementById('svc-list');
const labels={postgres:'PostgreSQL',encore:'Encore (web)',bot_api:'Bot API (tdlib)',redis:'Redis'};
el.innerHTML=Object.entries(s.components).map(([k,v])=>'<div class="svc-row"><span class="dot" style="background:'+(String(v).startsWith('ok')?'var(--green)':'var(--red)')+'"></span><b>'+esc(labels[k]||k)+'</b><span class="badge '+(String(v).startsWith('ok')?'b-green':'b-red')+'">'+esc(String(v).slice(0,30))+'</span><span class="lat"></span></div>').join('')+
'<div class="svc-row"><span class="dot" style="background:var(--'+(s.paused?'red':'green')+ ')"></span><b>پذیرش درخواست</b><span class="badge '+(s.paused?'b-red':'b-green')+'">'+(s.paused?'متوقف':'فعال')+'</span><span class="lat"></span></div>';
document.getElementById('disk-bar').style.width=s.disk_pct+'%';
document.getElementById('disk-txt').textContent=fmtB(s.disk_free)+' آزاد از '+fmtB(s.disk_total);
if(s.ram_pct!=null){document.getElementById('ram-bar').style.width=s.ram_pct+'%';document.getElementById('ram-txt').textContent=fa(s.ram_pct)+'٪'}
$('#pause-sw').checked=!s.paused;$('#pause-note').hidden=!s.paused}catch(e){}}
async function sysAct(act,confirmText){
if(act==='pause'||act==='resume'){if(!(await confirmModal('تأیید',confirmText||'','اجرا')))return}
else if(!(await confirmModal('تأیید نگهداری',confirmText||'','اجرا')))return;
try{const r=await post('/panel/api/system/'+act);
if(act==='reconcile'){toast(r.drift&&Object.keys(r.drift).length?'📊 بازتراز شد: '+JSON.stringify(r.drift):'📊 همهٔ شمارنده‌ها همگام بودند')}
else if(act==='cleanup'){toast('🧹 پاک‌سازی انجام شد — '+fmtB(r.disk_free)+' آزاد')}
else if(act==='cancel_all'){toast('🚫 تمام کارها لغو شدند: '+r.cancelled+' کار متوقف شد')}
else toast('✅ انجام شد');loadSystem()}catch(e){toast('خطا: '+e,1)}}
/* ---------- pause switch ---------- */
$('#pause-sw').addEventListener('change',async function(){
const want=!this.checked;const act=want?'pause':'resume';
if(!(await confirmModal('تأیید',want?'پذیرش متوقف شود؟':'پذیرش ادامه یابد؟','اجرا'))){this.checked=!want;return}
try{const r=await post('/panel/api/system/'+act);this.checked=!r.paused;$('#pause-note').hidden=!r.paused;
toast(r.paused?'⏸ پذیرش متوقف شد':'▶️ پذیرش فعال شد')}catch(e){this.checked=!this.checked;toast('خطا: '+e,1)}});
/* ---------- jobs nav badge + service chips ---------- */
async function refreshChips(){try{const s=await api('/panel/api/services');
document.getElementById('svc-chips').innerHTML=Object.entries(s.components).map(([k,v])=>
'<span class="svc'+(String(v).startsWith('ok')?'':' bad')+'"><i></i>'+k+'</span>').join('')}catch(e){}}
/* ---------- live WS ---------- */
let ws=null,poll=null;
function connectWS(){try{ws=new WebSocket((location.protocol==='https:'?'wss':'ws')+'://'+location.host+'/panel/ws')}catch(e){startPoll();return}
ws.onopen=()=>{document.getElementById('live').innerHTML='<span class="dot"></span> لایو (WS)';if(poll){clearInterval(poll);poll=null}};
ws.onmessage=ev=>{try{const d=JSON.parse(ev.data);renderSummary(d.summary);renderTasks(d.active||[]);renderEvents(d.events)}catch(e){}};
ws.onclose=()=>{document.getElementById('live').innerHTML='<span class="dot"></span> لایو (poll)';startPoll();setTimeout(connectWS,5000)};
ws.onerror=()=>{try{ws.close()}catch(e){}}}
function startPoll(){if(poll)return;poll=setInterval(async()=>{try{
const s=await api('/panel/api/summary');renderSummary(s);renderTasks(await api('/panel/api/active'));
const a=await api('/panel/api/audit?limit=8');renderEvents(a.items)}catch(e){}},4000)}
(async function init(){
renderSummary(await api('/panel/api/summary').catch(()=>({counters:{}})));
renderTasks(await api('/panel/api/active').catch(()=>[]));
renderEvents((await api('/panel/api/audit?limit=8').catch(()=>({items:[]}))).items);
refreshChips();loadTrend();connectWS();
setInterval(refreshChips,20000);
})();
</script></body></html>"""
