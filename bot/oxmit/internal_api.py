"""Internal aiohttp API: health, Encore progress callbacks, test harness.

Bound to the docker-internal network and 127.0.0.1 on the host only.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac as hmac_mod
import json
import os
import shutil
import ssl
import subprocess
import time
import uuid as uuid_mod
from collections import deque
from pathlib import Path

from aiohttp import web

from . import texts
from . import webpanel
from .engine import AdmissionError
from .log import get_logger

log = get_logger("oxmit.internal")

# Test API abuse bounds (SEC-4): the token is static, so bound the damage it
# can do even when it leaks. GEN_MAX_PER_HOUR caps synthetic-file generation,
# ACTIVE_SUBMITS caps concurrent encode submissions through the test path.
GEN_MAX_PER_HOUR = 10
ACTIVE_SUBMITS = 2


def _json(data, status: int = 200) -> web.Response:
    return web.json_response(data, status=status)


def build_app(engine, db, cfg, state, redis_client=None) -> web.Application:
    app = web.Application()
    app["engine"] = engine
    app["db"] = db
    app["cfg"] = cfg
    app["state"] = state
    app["redis"] = redis_client
    webpanel.setup(app, engine, db, cfg, state)

    gen_history: deque[float] = deque(maxlen=GEN_MAX_PER_HOUR)
    submit_sem = asyncio.Semaphore(ACTIVE_SUBMITS)

    async def healthz(request: web.Request) -> web.Response:
        components = {}
        ok = True
        try:
            await db.fetchval("SELECT 1")
            components["postgres"] = "ok"
        except Exception as exc:  # noqa: BLE001
            components["postgres"] = f"error: {str(exc)[:80]}"
            ok = False
        try:
            await engine.encre.health()
            components["encore"] = "ok"
        except Exception as exc:  # noqa: BLE001
            components["encore"] = f"error: {str(exc)[:80]}"
        try:
            me = await engine.bot.get_me()
            components["bot_api"] = f"ok @{me.username}"
            state.bot_username = me.username or ""
        except Exception as exc:  # noqa: BLE001
            components["bot_api"] = f"error: {str(exc)[:80]}"
        if redis_client is not None:
            try:
                info = await redis_client.info("memory")
                used = int(info.get("used_memory") or 0)
                maxmem = int(info.get("maxmemory") or 0)
                pct = f" ({100 * used // maxmem}%)" if maxmem else ""
                components["redis"] = f"ok used={used}B{pct}"
            except Exception as exc:  # noqa: BLE001
                components["redis"] = f"error: {str(exc)[:80]}"
                ok = False
        free = shutil.disk_usage(cfg.media_root).free
        components["disk_free"] = free
        if free < cfg.disk_pause_free_bytes:
            ok = False
        return _json(
            {
                "ok": ok,
                "paused": state.paused,
                "archive_configured": bool(state.archive_channel_id),
                "uptime_s": int(time.time() - state.started_at),
                "components": components,
            },
            status=200 if ok else 503,
        )

    async def encore_callback(request: web.Request) -> web.Response:
        job = request.query.get("job", "")
        sig = request.query.get("sig", "")
        if not job or not sig:
            return _json({"error": "missing params"}, status=400)
        expected = engine._callback_sig(job)
        if not hmac_mod.compare_digest(expected, sig):
            return _json({"error": "bad signature"}, status=403)
        try:
            payload = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _json({"error": "bad json"}, status=400)
        progress = int(payload.get("progress") or 0)
        await db.execute(
            "UPDATE jobs SET progress = GREATEST(progress, $2), "
            "progress_changed_at = CASE WHEN progress < $2 THEN now() "
            "ELSE progress_changed_at END, updated_at = now() "
            "WHERE id = $1::uuid",
            job, max(0, min(100, progress)),
        )
        status = payload.get("status")
        if status in ("SUCCESSFUL", "FAILED", "CANCELLED"):
            engine.spawn(engine.poll_job(job))
        return _json({"ok": True})

    def _authorized(request: web.Request) -> bool:
        token = request.headers.get("X-Test-Token", "")
        return bool(cfg.internal_test_token) and hmac_mod.compare_digest(
            token, cfg.internal_test_token
        )

    async def test_gen(request: web.Request) -> web.Response:
        if not _authorized(request):
            return _json({"error": "unauthorized"}, status=401)
        now = time.time()
        while gen_history and now - gen_history[0] > 3600:
            gen_history.popleft()
        if len(gen_history) >= GEN_MAX_PER_HOUR:
            return _json({"error": "rate limited"}, status=429)
        gen_history.append(now)
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = {}
        secs = min(int(body.get("secs") or 30), 600)
        big = bool(body.get("big"))
        w, h = (1920, 1080) if big else (1280, 720)
        rate = "30"
        Path(cfg.media_test).mkdir(parents=True, exist_ok=True)
        out = Path(cfg.media_test) / f"gen_{uuid_mod.uuid4().hex[:10]}.mp4"
        vf = "testsrc2=size=%dx%d:rate=%s:duration=%d" % (w, h, rate, secs)
        cmd = [
            "ffmpeg", "-v", "error",
            "-f", "lavfi", "-i", vf,
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p",
        ]
        if big:
            cmd += ["-b:v", "6M"]
        cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", "-y", str(out)]
        proc = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, timeout=600
        )
        if proc.returncode != 0 or not out.is_file():
            return _json({"error": (proc.stderr or b"").decode(errors="replace")[:300]}, status=500)
        return _json({"path": str(out), "size": out.stat().st_size, "secs": secs, "big": big})

    async def test_submit(request: web.Request) -> web.Response:
        if not _authorized(request):
            return _json({"error": "unauthorized"}, status=401)
        if submit_sem.locked():
            return _json({"error": "too many concurrent test jobs"}, status=429)
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _json({"error": "bad json"}, status=400)
        path = body.get("path")
        profile = body.get("profile") or "balanced"
        if not path or not Path(path).is_file():
            return _json({"error": "path missing"}, status=400)
        try:
            async with submit_sem:
                result = await engine.handle_submission(
                    tg_id=int(body.get("tg_id") or 900000001),
                    chat_id=body.get("chat_id"),
                    source_msg_id=None,
                    status_msg_id=None,
                    size_bytes=Path(path).stat().st_size,
                    filename=Path(path).name,
                    profile_key=profile,
                    local_path=path,
                    allow_no_archive=bool(body.get("allow_no_archive")),
                    target_mb=body.get("target_mb"),
                )
        except AdmissionError as exc:
            return _json({"error": exc.code, "detail": exc.fmt}, status=409)
        return _json(result)

    async def test_job(request: web.Request) -> web.Response:
        if not _authorized(request):
            return _json({"error": "unauthorized"}, status=401)
        job_id = request.match_info["job_id"]
        row = await db.fetchrow("SELECT * FROM jobs WHERE id = $1::uuid", job_id)
        if not row:
            return _json({"error": "not found"}, status=404)
        data = dict(row)
        import datetime as _dt

        for k, v in list(data.items()):
            if isinstance(v, _dt.datetime):
                data[k] = v.isoformat()
            elif isinstance(v, uuid_mod.UUID):
                data[k] = str(v)
        return _json(data)

    async def stats(request: web.Request) -> web.Response:
        if not _authorized(request):
            return _json({"error": "unauthorized"}, status=401)
        counters = await db.get_counters()
        rows = await db.fetch(
            "SELECT status, count(*) AS n FROM jobs GROUP BY status"
        )
        return _json(
            {
                "counters": counters,
                "jobs_by_status": {r["status"]: r["n"] for r in rows},
                "archive_configured": bool(state.archive_channel_id),
            }
        )

    async def test_redeliver(request: web.Request) -> web.Response:
        if not _authorized(request):
            return _json({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _json({"error": "bad json"}, status=400)
        job_id = body.get("job_id")
        chat_id = int(body.get("chat_id") or 0)
        tg_id = int(body.get("tg_id") or chat_id)
        if not job_id or not chat_id:
            return _json({"error": "job_id and chat_id required"}, status=400)
        ok, method = await engine.redeliver(job_id, chat_id, tg_id)
        return _json({"ok": ok, "method": method})

    app.router.add_get("/internal/healthz", healthz)
    app.router.add_post("/internal/encore-callback", encore_callback)
    if cfg.enable_test_api:
        app.router.add_post("/internal/test/gen", test_gen)
        app.router.add_post("/internal/test/submit", test_submit)
        app.router.add_get("/internal/test/job/{job_id}", test_job)
        app.router.add_post("/internal/test/redeliver", test_redeliver)
    else:
        log.info("test API disabled (set ENABLE_TEST_API=true to enable)")
    app.router.add_get("/internal/stats", stats)
    return app


async def start_internal_api(engine, db, cfg, state, redis_client=None,
                             port: int = 8080) -> web.AppRunner:
    runner = web.AppRunner(build_app(engine, db, cfg, state, redis_client))
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("internal api started", extra={"detail": f"port={port}"})

    # --- Phase 3: public panel site (panel routes only, optionally TLS) ---
    panel_app = web.Application()
    panel_app["engine"] = engine
    panel_app["db"] = db
    panel_app["cfg"] = cfg
    panel_app["state"] = state
    panel_app["redis"] = redis_client
    webpanel.setup(panel_app, engine, db, cfg, state)
    panel_runner = web.AppRunner(panel_app)
    await panel_runner.setup()
    ssl_ctx = None
    cert_dir = os.getenv("PANEL_CERT_DIR", "")
    if cert_dir:
        crt = os.path.join(cert_dir, "panel.crt")
        key = os.path.join(cert_dir, "panel.key")
        if os.path.isfile(crt) and os.path.isfile(key):
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_ctx.load_cert_chain(crt, key)
            log.info("panel TLS enabled (self-signed)")
    panel_site = web.TCPSite(panel_runner, "0.0.0.0", 8081, ssl_context=ssl_ctx)
    await panel_site.start()
    log.info("panel site started on 0.0.0.0:8081",
             extra={"detail": "tls" if ssl_ctx else "http"})
    return runner
