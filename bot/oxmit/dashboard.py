"""Web dashboard v3: live job monitoring, queue, history, users, moderation,
system overview. Read APIs + owner-only moderation, mounted by webpanel.setup
(which owns authentication, sessions and CSRF).

Every number shown comes from the jobs/users/moderation tables or from
psutil - nothing is estimated except the explicitly labelled ETA. File
system paths are never returned (the Local Bot API path contains the token)
and no endpoint serves media files.
"""
from __future__ import annotations

import shutil
import time
import uuid
from datetime import datetime, timezone

from aiohttp import web

from . import audit as audit_mod
from . import edu480
from . import media as media_mod
from .jobqueue import SLOT_STAGES
from .log import get_logger
from .panel.security import require_owner

log = get_logger("oxmit.dashboard")

try:
    import psutil
except ImportError:  # optional
    psutil = None

VIEWS = ("active", "queue", "completed", "failed", "cancelled", "all")

_JOB_COLS = """
    j.id::text AS id, j.status, j.stage, j.profile, j.profile_version, j.priority,
    j.progress, j.retries, j.upload_attempts, j.source_size, j.output_size,
    j.output_name, j.source_filename, j.error_category,
    left(coalesce(j.error_message, ''), 300) AS err, j.decision, j.cancel_reason,
    j.enqueued_at, j.reserved_at, j.download_started_at, j.download_done_at,
    j.encode_started_at, j.encode_done_at, j.upload_started_at, j.delivered_at,
    j.completed_at, j.worker_id, (j.reuse_of IS NOT NULL) AS reused,
    m.duration_s, m.width, m.height, m.vcodec, m.acodec, m.fps, m.bitrate,
    j.requester_tg_id AS tg, u.first_name, u.username, u.is_blocked, u.is_vip
"""


def _iso(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _secs(a, b):
    if a is None:
        return None
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b is None:
        b = datetime.now(timezone.utc)
    elif b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return max(0, int((b - a).total_seconds()))


def job_dict(r) -> dict:
    keys = set(r.keys()) if hasattr(r, "keys") else set()
    status = r.get("status", "queued")
    queued = status == "queued"
    reserved_at = r.get("reserved_at")
    completed_at = r.get("completed_at")
    wait_end = reserved_at if reserved_at else (None if queued else completed_at)
    jid_str = str(r.get("id") or "")
    profile_str = str(r.get("profile") or "edu480")
    profile_ver = r.get("profile_version", 1)
    source_fn = r.get("source_filename") or r.get("fname")
    out_fn = r.get("output_name")

    return {
        "id": jid_str, "jid": jid_str[:8], "status": status, "stage": r.get("stage"),
        "profile": f"{profile_str} v{profile_ver}",
        "priority": r.get("priority", 50), "progress": r.get("progress") or 0,
        "retries": r.get("retries", 0), "upload_attempts": r.get("upload_attempts", 0),
        "position": r.get("pos") if "pos" in keys else None,
        "ahead": (r["pos"] - 1) if "pos" in keys and r.get("pos") else None,
        "user": {"id": r.get("tg") or r.get("requester_tg_id"),
                 "name": r.get("first_name"),
                 "username": r.get("username"),
                 "banned": bool(r.get("is_blocked")),
                 "vip": bool(r.get("is_vip"))},
        "video": {
            "source_name": source_fn,
            "output_name": edu480.output_filename(out_fn, source_fn) if source_fn else out_fn,
            "size": int(r.get("source_size") or 0),
            "output_size": int(r["output_size"]) if r.get("output_size") is not None else None,
            "duration_s": float(r.get("duration_s") or 0) or None,
            "resolution": f"{r['width']}×{r['height']}" if r.get("width") else None,
            "vcodec": r.get("vcodec"), "acodec": r.get("acodec"),
            "fps": float(r["fps"]) if r.get("fps") else None,
            "bitrate": int(r["bitrate"]) if r.get("bitrate") else None,
        },
        "ts": {k: _iso(r.get(k)) for k in (
            "enqueued_at", "reserved_at", "download_started_at", "download_done_at",
            "encode_started_at", "encode_done_at", "upload_started_at", "delivered_at",
            "completed_at")},
        "wait_s": _secs(r.get("enqueued_at"), wait_end),
        "processing_s": (_secs(reserved_at, r.get("delivered_at") or completed_at)
                         if reserved_at else None),
        "encode_s": (_secs(r.get("encode_started_at"), r.get("encode_done_at"))
                     if r.get("encode_started_at") else None),
        "worker": r.get("worker_id"), "reused": bool(r.get("reused")),
        "decision": r.get("decision"), "cancel_reason": r.get("cancel_reason"),
        "error": ({"category": r.get("error_category"), "message": media_mod.redact(r.get("err"))}
                  if r.get("error_category") or r.get("err") else None),
    }


def _filters(q: str | None, user: str | None, dfrom: str | None, dto: str | None,
             args: list) -> str:
    """Parameterized WHERE fragments for search/filter (no string splicing
    of user input - only placeholders)."""
    parts = []
    if q:
        args.append(q.strip()[:120])
        n = len(args)
        parts.append(f"(j.id::text ILIKE ${n} || '%' OR j.source_filename ILIKE '%' || ${n} || '%'"
                     f" OR j.output_name ILIKE '%' || ${n} || '%')")
    if user:
        u = user.strip().lstrip("@")[:64]
        if u.isdigit():
            args.append(int(u))
            parts.append(f"j.requester_tg_id = ${len(args)}")
        elif u:
            args.append(u.lower())
            parts.append(f"lower(u.username) = ${len(args)}")
    for val, op in ((dfrom, ">="), (dto, "<")):
        if val:
            try:
                d = datetime.fromisoformat(val[:19]).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            args.append(d)
            parts.append(f"j.enqueued_at {op} ${len(args)}")
    return (" AND " + " AND ".join(parts)) if parts else ""


async def jobs_view(db, view: str, *, q=None, user=None, dfrom=None, dto=None,
                    limit: int = 100, offset: int = 0) -> dict:
    view = view if view in VIEWS else "active"
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    args: list = []
    extra = _filters(q, user, dfrom, dto, args)
    base_from = ("FROM jobs j LEFT JOIN media_assets m ON m.id = j.media_id "
                 "LEFT JOIN users u ON u.tg_id = j.requester_tg_id")
    if view == "queue":
        # Position is computed over the WHOLE queue first, filters apply after.
        inner = (f"SELECT {_JOB_COLS}, row_number() OVER "
                 f"(ORDER BY j.priority DESC, j.enqueued_at) AS pos {base_from} "
                 f"WHERE j.status = 'queued'")
        sql = (f"SELECT x.* FROM ({inner}) x JOIN jobs j ON j.id::text = x.id "
               f"LEFT JOIN users u ON u.tg_id = j.requester_tg_id WHERE TRUE{extra}")
        order = "ORDER BY x.pos"
        count_sql = (f"SELECT count(*) FROM jobs j LEFT JOIN users u "
                     f"ON u.tg_id = j.requester_tg_id WHERE j.status = 'queued'{extra}")
    else:
        where = {"active": "j.status = 'processing'", "completed": "j.status = 'completed'",
                 "failed": "j.status = 'failed'", "cancelled": "j.status = 'cancelled'",
                 "all": "TRUE"}[view]
        sql = f"SELECT {_JOB_COLS} {base_from} WHERE {where}{extra}"
        order = {"active": "ORDER BY j.reserved_at NULLS LAST",
                 "completed": "ORDER BY j.completed_at DESC NULLS LAST",
                 "failed": "ORDER BY j.completed_at DESC NULLS LAST",
                 "cancelled": "ORDER BY j.completed_at DESC NULLS LAST",
                 "all": "ORDER BY j.enqueued_at DESC"}[view]
        count_sql = f"SELECT count(*) {base_from} WHERE {where}{extra}"
    args_page = list(args) + [limit, offset]
    rows = await db.fetch(f"{sql} {order} LIMIT ${len(args) + 1} OFFSET ${len(args) + 2}",
                          *args_page)
    total = await db.fetchval(count_sql, *args)
    return {"view": view, "total": int(total or 0), "items": [job_dict(r) for r in rows]}


async def job_detail(db, job_id: str) -> dict | None:
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        return None
    r = await db.fetchrow(
        f"SELECT {_JOB_COLS} FROM jobs j LEFT JOIN media_assets m ON m.id = j.media_id "
        "LEFT JOIN users u ON u.tg_id = j.requester_tg_id WHERE j.id = $1", jid)
    if r is None:
        return None
    out = job_dict(r)
    reqs = await db.fetch(
        "SELECT jr.tg_id, jr.delivered, jr.created_at, u.first_name, u.username "
        "FROM job_requesters jr LEFT JOIN users u ON u.tg_id = jr.tg_id WHERE jr.job_id = $1",
        jid)
    out["requesters"] = [{"id": x["tg_id"], "name": x["first_name"], "username": x["username"],
                          "delivered": x["delivered"], "at": _iso(x["created_at"])} for x in reqs]
    dels = await db.fetch(
        "SELECT tg_id, method, status, created_at FROM deliveries WHERE job_id = $1 "
        "ORDER BY created_at", jid)
    out["deliveries"] = [{"id": x["tg_id"], "method": x["method"], "status": x["status"],
                          "at": _iso(x["created_at"])} for x in dels]
    return out


async def users_view(db, q: str | None = None, limit: int = 200) -> dict:
    args: list = []
    where = ""
    if q:
        s = q.strip().lstrip("@")[:64]
        if s.isdigit():
            args.append(int(s))
            where = "WHERE u.tg_id = $1"
        else:
            args.append(s.lower())
            where = "WHERE lower(u.username) LIKE '%' || $1 || '%' OR lower(u.first_name) LIKE '%' || $1 || '%'"
    args.append(max(1, min(int(limit), 500)))
    rows = await db.fetch(
        f"""
        SELECT u.tg_id, u.first_name, u.username, u.is_vip, u.is_blocked, u.is_admin,
               u.banned_at, u.ban_reason, u.last_seen_at, u.created_at,
               count(j.id) FILTER (WHERE j.enqueued_at > now() - interval '24 hours') AS jobs24,
               count(j.id) FILTER (WHERE j.status IN ('queued','processing')) AS pending,
               count(j.id) FILTER (WHERE j.status = 'completed') AS done,
               count(j.id) FILTER (WHERE j.status = 'failed') AS failed,
               count(j.id) AS total,
               coalesce(sum(j.source_size) FILTER (
                   WHERE j.enqueued_at > now() - interval '24 hours'), 0) AS bytes24
        FROM users u LEFT JOIN jobs j ON j.requester_tg_id = u.tg_id
        {where}
        GROUP BY u.tg_id
        ORDER BY jobs24 DESC, u.last_seen_at DESC
        LIMIT ${len(args)}
        """, *args)
    active = [int(r["jobs24"]) for r in rows if r["jobs24"]]
    avg = (sum(active) / len(active)) if active else 0
    threshold = max(10, int(avg * 3))
    items = []
    for r in rows:
        items.append({
            "id": r["tg_id"], "name": r["first_name"], "username": r["username"],
            "vip": bool(r["is_vip"]), "banned": bool(r["is_blocked"]),
            "admin": bool(r["is_admin"]), "banned_at": _iso(r["banned_at"]),
            "ban_reason": r["ban_reason"], "last_seen": _iso(r["last_seen_at"]),
            "joined": _iso(r["created_at"]),
            "jobs24": int(r["jobs24"]), "pending": int(r["pending"]),
            "done": int(r["done"]), "failed": int(r["failed"]), "total": int(r["total"]),
            "bytes24": int(r["bytes24"]),
            "heavy": int(r["jobs24"]) >= threshold,
        })
    return {"items": items, "heavy_threshold": threshold}


async def moderation_view(db, limit: int = 200) -> dict:
    rows = await db.fetch(
        """
        SELECT ma.id, ma.job_id::text AS job_id, ma.target_tg_id, ma.action,
               ma.actor_tg_id, ma.job_status_before, ma.job_stage_before,
               ma.details, ma.created_at, u.first_name, u.username, u.is_blocked
        FROM moderation_actions ma LEFT JOIN users u ON u.tg_id = ma.target_tg_id
        ORDER BY ma.created_at DESC LIMIT $1
        """, max(1, min(int(limit), 500)))
    banned = await db.fetch(
        "SELECT tg_id, first_name, username, banned_at, ban_reason FROM users "
        "WHERE is_blocked ORDER BY banned_at DESC NULLS LAST LIMIT 500")
    return {
        "actions": [{"id": r["id"], "job": r["job_id"], "user": r["target_tg_id"],
                     "name": r["first_name"], "username": r["username"],
                     "action": r["action"], "actor": r["actor_tg_id"],
                     "status_before": r["job_status_before"], "stage_before": r["job_stage_before"],
                     "details": r["details"], "at": _iso(r["created_at"]),
                     "still_banned": bool(r["is_blocked"])} for r in rows],
        "banned": [{"id": r["tg_id"], "name": r["first_name"], "username": r["username"],
                    "at": _iso(r["banned_at"]), "reason": r["ban_reason"]} for r in banned],
    }


async def system_view(engine, db, cfg, state) -> dict:
    usage = shutil.disk_usage(cfg.media_root)
    mem = psutil.virtual_memory() if psutil else None
    counts = {r["status"]: int(r["n"]) for r in await db.fetch(
        "SELECT status, count(*) AS n FROM jobs WHERE status IN "
        "('queued','processing') GROUP BY status")}
    stages = {r["stage"]: int(r["n"]) for r in await db.fetch(
        "SELECT stage, count(*) AS n FROM jobs WHERE status = 'processing' GROUP BY stage")}
    slots = await db.fetch(
        """
        SELECT j.id::text AS id, j.stage, j.progress, j.worker_id, j.reserved_at,
               j.output_name, j.source_filename, u.first_name, j.requester_tg_id
        FROM jobs j LEFT JOIN users u ON u.tg_id = j.requester_tg_id
        WHERE j.status = 'processing' AND j.stage = ANY($1::text[])
        ORDER BY j.reserved_at
        """, list(SLOT_STAGES))
    thr = await db.fetchrow(
        """
        SELECT count(*) FILTER (WHERE completed_at > now() - interval '1 hour') AS h1,
               count(*) FILTER (WHERE completed_at > now() - interval '24 hours') AS h24,
               avg(extract(epoch FROM (coalesce(delivered_at, completed_at) - reserved_at)))
                   FILTER (WHERE completed_at > now() - interval '24 hours'
                           AND reserved_at IS NOT NULL) AS avg_proc,
               avg(extract(epoch FROM (reserved_at - enqueued_at)))
                   FILTER (WHERE completed_at > now() - interval '24 hours'
                           AND reserved_at IS NOT NULL) AS avg_wait,
               count(*) FILTER (WHERE status = 'failed'
                                AND completed_at > now() - interval '24 hours') AS failed24
        FROM jobs WHERE status IN ('completed', 'failed') AND reuse_of IS NULL
        """)
    try:
        encore_q = await engine.encre.queue_count()
    except Exception:  # noqa: BLE001
        encore_q = None
    load = None
    try:
        load = [round(x, 2) for x in __import__("os").getloadavg()]
    except OSError:
        pass
    return {
        "time": _iso(datetime.now(timezone.utc)),
        "cpu_pct": psutil.cpu_percent(interval=None) if psutil else None,
        "cores": psutil.cpu_count() if psutil else None,
        "load": load,
        "ram_pct": round(mem.percent, 1) if mem else None,
        "ram_used": mem.used if mem else None, "ram_total": mem.total if mem else None,
        "disk_free": usage.free, "disk_total": usage.total,
        "disk_pct": round(100 * usage.used / usage.total, 1),
        "queued": counts.get("queued", 0), "processing": counts.get("processing", 0),
        "stages": stages, "slots_total": cfg.slots, "slots_busy": len(slots),
        "prefetch": cfg.prefetch_jobs, "queue_capacity": cfg.max_queued,
        "workers": [{"job": s["id"], "jid": s["id"][:8], "stage": s["stage"],
                     "progress": s["progress"], "worker": s["worker_id"],
                     "since": _iso(s["reserved_at"]),
                     "name": edu480.output_filename(s["output_name"], s["source_filename"]),
                     "user": s["first_name"], "user_id": s["requester_tg_id"]} for s in slots],
        "throughput": {"completed_1h": int(thr["h1"] or 0), "completed_24h": int(thr["h24"] or 0),
                       "failed_24h": int(thr["failed24"] or 0),
                       "avg_processing_s": int(thr["avg_proc"]) if thr["avg_proc"] else None,
                       "avg_wait_s": int(thr["avg_wait"]) if thr["avg_wait"] else None,
                       "sec_per_media_sec": round(await engine.throughput_rate(), 3)},
        "encore_queue": encore_q, "paused": state.paused,
        "uptime_s": int(time.time() - state.started_at),
        "profile": f"{edu480.PROFILE_KEY} v{edu480.PROFILE_VERSION} "
                   f"(CRF {cfg.edu480_crf}, {cfg.edu480_preset}, ≤{cfg.edu480_max_fps:g}fps)",
    }


def setup(app: web.Application, engine, db, cfg, state, *, session_of, post_session_of,
          client_ip) -> None:
    """Mount the v3 dashboard APIs. Auth helpers come from webpanel.setup."""

    def _json(data, status: int = 200) -> web.Response:
        return web.json_response(data, status=status)

    def _auth(handler):
        return require_owner(handler)

    async def me(request, session):
        return _json({"role": session.get("role", "owner"), "tg_id": session.get("tg_id"),
                      "actor": session.get("actor")})

    async def jobs(request, session):
        qp = request.query
        try:
            limit = int(qp.get("limit", "100"))
            offset = int(qp.get("offset", "0"))
        except ValueError:
            return _json({"error": "bad paging"}, 400)
        view = qp.get("view") or qp.get("status") or "active"
        if view == "queued":
            view = "queue"
        data = await jobs_view(db, view, q=qp.get("q"),
                               user=qp.get("user"), dfrom=qp.get("from"),
                               dto=qp.get("to"), limit=limit, offset=offset)
        # Compatibility: keep both 'jobs' and 'items', and provide 'counts'
        data["jobs"] = data.get("items", [])
        counts = {"active": 0, "queued": 0, "completed": 0, "failed": 0, "cancelled": 0}
        try:
            c_rows = await db.fetch("SELECT status, count(*) AS n FROM jobs GROUP BY status")
            for cr in c_rows:
                st = cr["status"]
                if st == "processing":
                    counts["active"] = int(cr["n"])
                elif st in counts:
                    counts[st] = int(cr["n"])
        except Exception:
            pass
        data["counts"] = counts
        return _json(data)

    async def job(request, session):
        data = await job_detail(db, request.match_info["job_id"])
        return _json(data) if data else _json({"error": "not found"}, 404)

    async def users(request, session):
        return _json(await users_view(db, request.query.get("q")))

    async def moderation(request, session):
        return _json(await moderation_view(db))

    async def system(request, session):
        return _json(await system_view(engine, db, cfg, state))

    async def moderate(request: web.Request, session: dict):
        jid = request.match_info["job_id"]
        actor = session.get("tg_id") or cfg.owner_telegram_id
        res = await engine.moderate_job(jid, actor)
        await audit_mod.log_action(db, session.get("actor", "owner"), "owner",
                                   "moderation.remove_ban", jid, str(res), "web",
                                   client_ip(request))
        return _json(res, 200 if res.get("ok") else 409)

    app.router.add_get("/panel/api/v3/me", require_owner(me))
    app.router.add_get("/panel/api/v3/jobs", require_owner(jobs))
    app.router.add_get("/panel/api/v3/job/{job_id}", require_owner(job))
    app.router.add_get("/panel/api/v3/users", require_owner(users))
    app.router.add_get("/panel/api/v3/moderation", require_owner(moderation))
    app.router.add_get("/panel/api/v3/system", require_owner(system))
    app.router.add_post("/panel/api/v3/job/{job_id}/moderate", require_owner(moderate))
