"""Compression queue, job priority, worker telemetry, and presets management.

Implements dynamic priority adjustment with queue dispatcher kickoff, full multi-layer
job cancellation, worker status and CPU core telemetry, and compression preset queries.
"""
from __future__ import annotations

import uuid
from typing import Any

from .. import audit as audit_mod
from ..log import get_logger
from ..profiles import PROFILES
from ..resources import cores_for

log = get_logger("oxmit.panel.queue")

SLOT_STAGES = ("reserved", "downloading", "probing", "checking", "copying", "encoding")


async def update_job_priority(
    db: Any,
    engine: Any,
    job_id: str,
    priority: int,
    actor: str = "owner",
    client_ip: str = "?",
) -> dict[str, Any]:
    """Adjust job queue priority (1-100) and wake queue dispatcher."""
    try:
        jid = uuid.UUID(job_id)
    except (ValueError, TypeError):
        raise ValueError("Invalid job ID format")

    if not isinstance(priority, int) or priority < 1 or priority > 100:
        raise ValueError("Priority must be an integer between 1 and 100")

    row = await db.fetchrow(
        """
        UPDATE jobs
        SET priority = $2, updated_at = now()
        WHERE id = $1::uuid AND status = 'queued'
        RETURNING id, priority, status
        """,
        jid,
        priority,
    )
    if not row:
        existing = await db.fetchrow("SELECT id, status FROM jobs WHERE id = $1::uuid", jid)
        if not existing:
            raise KeyError("Job not found")
        raise ValueError(f"Job is {existing['status']}, not queued")

    if hasattr(engine, "kick_dispatch"):
        engine.kick_dispatch()

    await audit_mod.log_action(
        db,
        actor,
        "admin",
        "job.priority",
        str(jid),
        f"priority={priority}",
        "web",
        client_ip,
    )

    return {"status": "ok", "job_id": str(jid), "priority": priority}


async def cancel_job_task(
    db: Any,
    engine: Any,
    job_id: str,
    actor: str = "owner",
    client_ip: str = "?",
) -> dict[str, Any]:
    """Execute complete multi-layer cancellation for an active or queued job."""
    try:
        jid = uuid.UUID(job_id)
    except (ValueError, TypeError):
        raise ValueError("Invalid job ID format")

    row = await db.fetchrow(
        "SELECT * FROM jobs WHERE id = $1::uuid AND status IN ('queued', 'processing')",
        jid,
    )
    if not row:
        raise KeyError("Job not found or not in cancellable status")

    ok = await engine.cancel_job(row, by_admin=True, reason="webpanel")
    await audit_mod.log_action(
        db,
        actor,
        "admin",
        "job.cancel",
        str(jid),
        f"cancelled={ok}",
        "web",
        client_ip,
    )

    return {"status": "ok", "job_id": str(jid)}


def get_compression_presets(cfg: Any = None) -> dict[str, Any]:
    """List compression presets and active profile parameters."""
    profiles_list = [
        {
            "key": p.key,
            "encore_name": p.encore_name,
            "title": p.title,
            "title_fa": p.title_fa,
            "description": p.description,
            "version": p.version,
            "max_short_side": p.max_short_side,
            "target_width": p.target_width,
            "active": (p.key == "edu480"),
        }
        for p in PROFILES
    ]

    active_config = {
        "profile": "edu480",
        "version": 2,
        "crf": getattr(cfg, "edu480_crf", 25),
        "preset": getattr(cfg, "edu480_preset", "veryfast"),
        "max_fps": getattr(cfg, "edu480_max_fps", 30.0),
        "audio_kbps": getattr(cfg, "edu480_audio_kbps", 64),
    }

    return {
        "active": "edu480",
        "active_config": active_config,
        "profiles": profiles_list,
    }


async def get_worker_telemetry(
    db: Any,
    engine: Any,
    cfg: Any = None,
    redis_client: Any = None,
) -> dict[str, Any]:
    """Retrieve transcode worker slots, Encore queue depth, and Redis memory statistics."""
    worker_names = list(
        getattr(cfg, "worker_container_names", ("oxmit-encore-worker-1", "oxmit-encore-worker-2"))
    )

    slots: list[Any] = []
    try:
        slots = await db.fetch(
            """
            SELECT j.id::text AS id, j.stage, j.progress, j.worker_id, j.reserved_at,
                   j.output_name, j.source_filename, u.first_name, j.requester_tg_id
            FROM jobs j LEFT JOIN users u ON u.tg_id = j.requester_tg_id
            WHERE j.status = 'processing' AND j.stage = ANY($1::text[])
            ORDER BY j.reserved_at
            """,
            list(SLOT_STAGES),
        )
    except Exception as exc:
        log.warning("Worker slot fetch error: %s", exc)

    active_count = len(slots)
    per_worker_cores = cores_for(
        active_count,
        getattr(cfg, "cores_single_job", 7.0),
        getattr(cfg, "cores_dual_job", 3.2),
        getattr(cfg, "cores_floor", 1.0),
    )

    workers = []
    for idx, wname in enumerate(worker_names):
        matching_slot = None
        for s in slots:
            slot_worker = s.get("worker_id") or ""
            if slot_worker == wname or f"worker-{idx + 1}" in slot_worker:
                matching_slot = s
                break

        if not matching_slot and idx < len(slots):
            matching_slot = slots[idx]

        if matching_slot:
            current_job = {
                "id": matching_slot["id"],
                "stage": matching_slot.get("stage"),
                "progress": matching_slot.get("progress", 0),
                "name": matching_slot.get("output_name") or matching_slot.get("source_filename"),
                "user": matching_slot.get("first_name"),
                "user_id": matching_slot.get("requester_tg_id"),
                "since": matching_slot.get("reserved_at").isoformat()
                if hasattr(matching_slot.get("reserved_at"), "isoformat")
                else str(matching_slot.get("reserved_at") or ""),
            }
            status = "busy"
        else:
            current_job = None
            status = "idle"

        workers.append(
            {
                "id": f"worker-{idx + 1}",
                "name": wname,
                "status": status,
                "current_job": current_job,
                "cores_allocated": per_worker_cores,
            }
        )

    # Encore queue count
    encore_queue = 0
    if hasattr(engine, "encre") and hasattr(engine.encre, "queue_count"):
        try:
            encore_queue = await engine.encre.queue_count() or 0
        except Exception:
            encore_queue = 0

    # Redis telemetry
    redis_info = {"status": "ok", "used_bytes": 0, "max_bytes": 0}
    if redis_client:
        try:
            info = await redis_client.info("memory")
            redis_info["used_bytes"] = int(info.get("used_memory") or 0)
            redis_info["max_bytes"] = int(info.get("maxmemory") or 0)
        except Exception:
            redis_info["status"] = "error"

    return {
        "workers": workers,
        "slots_total": len(worker_names),
        "slots_busy": active_count,
        "encore_queue": encore_queue,
        "redis": redis_info,
    }
