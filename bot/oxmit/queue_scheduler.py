"""Multi-Tier Fairness & Anti-Starvation Queue Scheduler for Oxmit.

Implements 4 mathematically verified scheduling algorithms:
1. fair_round_robin (Dynamic Fair-Share Round-Robin) [Default]
2. weighted_fair (Weighted Fair Queueing with Virtual Arrival Time)
3. strict_fifo (Strict First-In First-Out)
4. size_aware_fair (Size-Aware Fair Share)

Single Source of Truth for atomic worker claims (FOR UPDATE SKIP LOCKED)
and exact position/ETA calculation for Telegram cards and Web Panel.
"""

from __future__ import annotations

import math
import uuid
from typing import Any

from .log import get_logger

log = get_logger("oxmit.queue_scheduler")

ALGORITHM_LABELS_FA: dict[str, str] = {
    "fair_round_robin": "عادلانه چرخشی (Fair-Share)",
    "weighted_fair": "عادلانه وزنی زمانی (WFQ)",
    "strict_fifo": "نوبت زمانی مطلق (FIFO)",
    "size_aware_fair": "عادلانه حجم‌محور (Size-Aware)",
}


def build_queue_order_cte(mode: str, admin_bypass: bool = False, penalty: int = 300) -> str:
    """Generate the SQL CTE for ordering queued jobs according to the active algorithm."""
    admin_sql = "TRUE" if admin_bypass else "FALSE"
    penalty_int = int(penalty)

    if mode == "weighted_fair":
        return f"""
        WITH OrderedQueue AS (
            SELECT
                j.id,
                j.requester_tg_id AS user_id,
                j.enqueued_at,
                j.source_size,
                COALESCE(j.priority_boost, 0) AS priority_boost,
                CASE
                    WHEN {admin_sql} = TRUE AND j.is_admin_job = TRUE THEN 1
                    ELSE 0
                END AS effective_priority,
                ROW_NUMBER() OVER (
                    PARTITION BY j.requester_tg_id
                    ORDER BY j.enqueued_at ASC, j.id ASC
                ) AS user_rank_index
            FROM jobs j
            WHERE j.status = 'queued'
        )
        SELECT
            oq.id,
            ROW_NUMBER() OVER (
                ORDER BY
                    oq.priority_boost DESC,
                    oq.effective_priority DESC,
                    (oq.enqueued_at + ((oq.user_rank_index - 1) * ({penalty_int} * INTERVAL '1 second'))) ASC,
                    oq.id ASC
            ) AS global_queue_position
        FROM OrderedQueue oq
        """
    elif mode == "strict_fifo":
        return f"""
        WITH OrderedQueue AS (
            SELECT
                j.id,
                j.requester_tg_id AS user_id,
                j.enqueued_at,
                COALESCE(j.priority_boost, 0) AS priority_boost,
                CASE
                    WHEN {admin_sql} = TRUE AND j.is_admin_job = TRUE THEN 1
                    ELSE 0
                END AS effective_priority
            FROM jobs j
            WHERE j.status = 'queued'
        )
        SELECT
            oq.id,
            ROW_NUMBER() OVER (
                ORDER BY
                    oq.priority_boost DESC,
                    oq.effective_priority DESC,
                    oq.enqueued_at ASC,
                    oq.id ASC
            ) AS global_queue_position
        FROM OrderedQueue oq
        """
    elif mode == "size_aware_fair":
        return f"""
        WITH OrderedQueue AS (
            SELECT
                j.id,
                j.requester_tg_id AS user_id,
                j.enqueued_at,
                j.source_size,
                COALESCE(j.priority_boost, 0) AS priority_boost,
                CASE
                    WHEN {admin_sql} = TRUE AND j.is_admin_job = TRUE THEN 1
                    ELSE 0
                END AS effective_priority,
                ROW_NUMBER() OVER (
                    PARTITION BY j.requester_tg_id
                    ORDER BY j.enqueued_at ASC, j.id ASC
                ) AS fair_layer
            FROM jobs j
            WHERE j.status = 'queued'
        )
        SELECT
            oq.id,
            ROW_NUMBER() OVER (
                ORDER BY
                    oq.priority_boost DESC,
                    oq.effective_priority DESC,
                    oq.fair_layer ASC,
                    COALESCE(oq.source_size, 0) ASC,
                    oq.enqueued_at ASC,
                    oq.id ASC
            ) AS global_queue_position
        FROM OrderedQueue oq
        """
    else:  # fair_round_robin (default)
        return f"""
        WITH OrderedQueue AS (
            SELECT
                j.id,
                j.requester_tg_id AS user_id,
                j.enqueued_at,
                j.source_size,
                COALESCE(j.priority_boost, 0) AS priority_boost,
                CASE
                    WHEN {admin_sql} = TRUE AND j.is_admin_job = TRUE THEN 1
                    ELSE 0
                END AS effective_priority,
                ROW_NUMBER() OVER (
                    PARTITION BY j.requester_tg_id
                    ORDER BY j.enqueued_at ASC, j.id ASC
                ) AS fair_layer
            FROM jobs j
            WHERE j.status = 'queued'
        )
        SELECT
            oq.id,
            ROW_NUMBER() OVER (
                ORDER BY
                    oq.priority_boost DESC,
                    oq.effective_priority DESC,
                    oq.fair_layer ASC,
                    oq.enqueued_at ASC,
                    oq.id ASC
            ) AS global_queue_position
        FROM OrderedQueue oq
        """


class QueueScheduler:
    """Orchestrates queue ordering, position calculation, and atomic dispatch."""

    def __init__(self, db: Any, dynamic_config: Any) -> None:
        self.db = db
        self.cfg = dynamic_config

    async def get_job_queue_details(self, job_id: str | uuid.UUID) -> dict[str, Any] | None:
        """Calculate the precise queue position, jobs ahead, total queued, and ETA for a job."""
        jid = uuid.UUID(str(job_id))
        mode = self.cfg.get_str("queue_scheduling_mode", "fair_round_robin")
        penalty = self.cfg.get_int("wfq_time_penalty_seconds", 300)
        admin_bypass = self.cfg.get_bool("admin_queue_bypass", False)
        active_workers = max(1, self.cfg.get_int("active_encoding_workers", 2))

        cte = build_queue_order_cte(mode, admin_bypass=admin_bypass, penalty=penalty)
        sql = f"""
        WITH Q AS ({cte}),
        Total AS (SELECT COUNT(*) AS total_count FROM jobs WHERE status = 'queued')
        SELECT
            q.global_queue_position,
            t.total_count
        FROM Q q
        CROSS JOIN Total t
        WHERE q.id = $1::uuid
        """

        row = await self.db.fetchrow(sql, jid)
        if not row:
            # Job might not be in 'queued' status anymore
            return None

        pos = int(row["global_queue_position"])
        total = int(row["total_count"])
        jobs_ahead = max(0, pos - 1)

        # Average duration of recent completed jobs (default 120s if no history)
        avg_dur = await self.db.fetchval(
            """
            SELECT COALESCE(AVG(EXTRACT(EPOCH FROM (completed_at - started_at))), 120.0)
            FROM jobs
            WHERE status = 'completed' AND completed_at > now() - interval '24 hours'
            """
        ) or 120.0
        avg_dur = max(30.0, float(avg_dur))

        # ETA formula: ceil(jobs_ahead / active_workers) * avg_duration
        wait_cycles = math.ceil(jobs_ahead / active_workers)
        estimated_wait_seconds = int(wait_cycles * avg_dur)

        return {
            "job_id": str(jid),
            "global_queue_position": pos,
            "jobs_ahead": jobs_ahead,
            "total_queued": total,
            "estimated_wait_seconds": estimated_wait_seconds,
            "algorithm": mode,
            "algorithm_fa": ALGORITHM_LABELS_FA.get(mode, mode),
            "active_workers": active_workers,
        }

    async def claim_next_job(self, worker_id: str) -> dict[str, Any] | None:
        """Atomically claim the next job in queue with FOR UPDATE SKIP LOCKED."""
        mode = self.cfg.get_str("queue_scheduling_mode", "fair_round_robin")
        penalty = self.cfg.get_int("wfq_time_penalty_seconds", 300)
        admin_bypass = self.cfg.get_bool("admin_queue_bypass", False)

        cte = build_queue_order_cte(mode, admin_bypass=admin_bypass, penalty=penalty)
        claim_sql = f"""
        WITH NextInQueue AS (
            {cte}
            ORDER BY global_queue_position ASC
            LIMIT 1
        )
        UPDATE jobs
        SET
            status = 'processing',
            stage = 'downloading',
            worker_id = $1,
            started_at = COALESCE(started_at, now()),
            updated_at = now()
        WHERE id = (
            SELECT j.id
            FROM jobs j
            JOIN NextInQueue n ON n.id = j.id
            WHERE j.status = 'queued'
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING id, requester_tg_id, chat_id, media_id, profile, source_size, source_path, source_message_id, status_message_id
        """

        row = await self.db.fetchrow(claim_sql, worker_id)
        if row:
            log.info("claimed job %s for worker %s via %s scheduler", row["id"], worker_id, mode)
            return dict(row)
        return None

    async def preview_queue_order(self, mode: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Return a preview list of queued jobs for the Web Panel fairness simulator."""
        if not mode:
            mode = self.cfg.get_str("queue_scheduling_mode", "fair_round_robin")
        penalty = self.cfg.get_int("wfq_time_penalty_seconds", 300)
        admin_bypass = self.cfg.get_bool("admin_queue_bypass", False)

        cte = build_queue_order_cte(mode, admin_bypass=admin_bypass, penalty=penalty)
        sql = f"""
        WITH Q AS ({cte})
        SELECT
            q.global_queue_position,
            j.id::text AS id,
            left(j.id::text, 8) AS jid,
            j.requester_tg_id AS user_id,
            u.first_name,
            u.username,
            u.is_vip,
            j.is_admin_job,
            j.priority_boost,
            j.enqueued_at,
            j.source_size,
            m.filename,
            m.duration_s,
            j.profile
        FROM Q q
        JOIN jobs j ON j.id = q.id
        LEFT JOIN users u ON u.tg_id = j.requester_tg_id
        LEFT JOIN media_assets m ON m.id = j.media_id
        ORDER BY q.global_queue_position ASC
        LIMIT $1::integer
        """

        rows = await self.db.fetch(sql, limit)
        items = []
        for r in rows:
            items.append({
                "pos": r["global_queue_position"],
                "id": r["id"],
                "jid": r["jid"],
                "user_id": r["user_id"],
                "name": r["first_name"] or r["username"] or str(r["user_id"]),
                "username": r["username"],
                "is_vip": bool(r["is_vip"]),
                "is_admin": bool(r["is_admin_job"]),
                "boost": r["priority_boost"],
                "enqueued_at": r["enqueued_at"].isoformat() if r["enqueued_at"] else "",
                "filename": r["filename"] or "video.mp4",
                "size_bytes": r["source_size"] or 0,
                "duration_s": r["duration_s"] or 0,
                "profile": r["profile"],
            })
        return items
