"""Just-in-time job queue: registration, dispatch, worker pipeline, moderation.

Lifecycle (one job row, persisted at every step)::

    intake (Telegram metadata only, nothing downloaded)
      -> QUEUED            persistent row; queue position / ETA shown to user
      -> RESERVED          dispatcher claimed it (FOR UPDATE SKIP LOCKED, lease)
      -> DOWNLOADING       Local Bot API getFile (first time bytes touch disk)
      -> PROBING           ffprobe of the real streams
      -> CHECKING          SHA-256: exact duplicate / own-output detection
      -> ENCODING          EDU480 on an Encore worker   (or REMUX if compliant)
      -> VALIDATING        output probe + duration check
      -> UPLOADING         archive channel upload (retried WITHOUT re-encoding)
      -> DELIVERING        copy to every requester (no forward attribution)
      -> COMPLETED         temp files + Local Bot API source removed

jobs.status stays coarse (queued/processing/completed/failed/cancelled) for
backwards compatibility; jobs.stage carries the fine-grained state above.

Concurrency model: an "encode slot" is held from RESERVED until ENCODING
finishes. Validation, upload and delivery run outside the slot so the next
job's download/encode overlaps them. The number of slots defaults to the
number of Encore worker replicas, i.e. the DB - not Encore's Redis queue - is
the real queue: Encore never holds more than ``slots`` jobs.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from . import audit as audit_mod
from . import edu480
from . import media as media_mod
from .encore_client import EncoreError
from .log import get_logger
from .telemetry_cards import (
    fmt_duration_fa,
    make_cancel_kb,
    render_progress_bar,
    render_stage_0_queued,
    render_stage_1_download,
    render_stage_2_encode,
    render_stage_3_upload,
    render_stage_complete,
)
from .texts import tr

log = get_logger("oxmit.jobqueue")

# Stages that occupy an encode slot (claimed .. encode finished).
SLOT_STAGES = ("reserved", "downloading", "probing", "checking", "copying", "encoding")
PRE_ENCODE_STAGES = ("reserved", "downloading", "probing", "checking", "copying")
# Completion pipeline owns the job; the poller must not re-trigger it.
POST_ENCODE_STAGES = ("completing", "validating", "archiving", "uploading",
                      "upload_retry", "delivering")

_REUSE_SQL = """
    SELECT ar.id, ar.source_media_id, ar.output_media_id, ar.channel_id,
           ar.message_id, ar.status, ar.file_unique_id, ar.created_at,
           ar.part_index, ar.part_total, ar.profile_version,
           ms.sha256 AS source_sha256,
           m2.size_bytes AS output_size,
           m2.tg_file_id AS output_tg_file_id,
           ms.tg_file_id AS source_tg_file_id,
           ms.size_bytes AS source_size
    FROM archive_records ar
    JOIN media_assets ms ON ms.id = ar.source_media_id
    LEFT JOIN media_assets m2 ON m2.id = ar.output_media_id
    WHERE {cond}
      AND ar.profile = 'edu480'
      AND ar.status IN ('active', 'no_gain')
      AND (ar.profile_version >= 2
           OR least(m2.width, m2.height) <= 480)
    ORDER BY ar.profile_version DESC, ar.created_at DESC, ar.part_index
    LIMIT 64
"""


def _group_first(rows) -> list:
    """Keep only the parts belonging to the first (best) archived result."""
    if not rows:
        return []
    first = rows[0]
    key = (first["source_media_id"], first["profile_version"])
    parts = [r for r in rows if (r["source_media_id"], r["profile_version"]) == key]
    return sorted(parts, key=lambda r: r["part_index"] or 0)


def _ts(dt) -> str:
    if dt is None:
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _clock(seconds: float) -> str:
    s_val = max(1, int(round(seconds))) if seconds > 0 else 0
    h, rem = divmod(s_val, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class SourceUnavailable(Exception):
    pass


class QueueMixin:
    """Mixed into JobEngine (engine.py). Uses self.db / self.cfg / self.bot /
    self.encre / self.state and the engine's delivery + completion code."""

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------
    def _init_queue(self) -> None:
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self._pipelines: dict[str, asyncio.Task] = {}
        self._dispatch_lock = asyncio.Lock()
        self._rate_cache: tuple[float, float] | None = None
        self._card_edit_at: dict[str, float] = {}
        self._disk_block_notified = 0.0

    def log_channel(self) -> int | None:
        return self.cfg.log_channel_id or self.state.archive_channel_id

    # ------------------------------------------------------------------
    # registration (metadata only - nothing is downloaded here)
    # ------------------------------------------------------------------
    async def find_reusable_by_unique_id(self, file_unique_id: str) -> tuple[list, str]:
        """Early recognition without downloading.

        (parts, kind): kind 'known_output' when the file IS one of our own
        EDU480 outputs (Telegram keeps file_unique_id across copies), or
        'unique_id' when this exact Telegram file was compressed before.
        """
        if not file_unique_id:
            return [], ""
        rows = await self.db.fetch(_REUSE_SQL.format(cond="ar.file_unique_id = $1"),
                                   file_unique_id)
        if rows:
            # Return the whole result group of that output (split results).
            src = rows[0]["source_media_id"]
            group = await self.db.fetch(
                _REUSE_SQL.format(cond="ar.source_media_id = $1"), src)
            return _group_first(group) or _group_first(rows), "known_output"
        rows = await self.db.fetch(_REUSE_SQL.format(cond="ms.tg_file_unique_id = $1"),
                                   file_unique_id)
        return _group_first(rows), ("unique_id" if rows else "")

    async def find_reusable_by_sha(self, sha: str) -> tuple[list, str]:
        rows = await self.db.fetch(_REUSE_SQL.format(cond="ms.sha256 = $1"), sha)
        if rows:
            return _group_first(rows), "exact"
        rows = await self.db.fetch(_REUSE_SQL.format(cond="ar.sha256 = $1"), sha)
        if rows:
            group = await self.db.fetch(
                _REUSE_SQL.format(cond="ar.source_media_id = $1"),
                rows[0]["source_media_id"])
            return _group_first(group) or _group_first(rows), "known_output"
        return [], ""

    async def register_job(
        self, *, tg_id: int, chat_id: int, source_msg_id: int | None,
        status_msg_id: int | None, file_id: str | None, file_unique_id: str | None,
        size_bytes: int, filename: str | None, mime: str | None = None,
        duration_s: float | None = None, width: int | None = None,
        height: int | None = None, output_name: str | None = None,
        local_path: str | None = None, allow_no_archive: bool = False,
    ) -> dict:
        """Admit a submission into the persistent queue.

        Raises AdmissionError on rejection. Returns {"outcome": ...} where
        outcome is queued | joined | reused.
        """
        is_admin = tg_id in await self.admin_ids()
        await self.check_admission(tg_id, size_bytes, is_admin=is_admin,
                                   allow_no_archive=allow_no_archive)
        if duration_s:
            await self.check_duration_limit(tg_id, duration_s, is_admin=is_admin)
        out_stem = edu480.normalize_output_name(output_name) \
            or edu480.normalize_output_name(filename) or "video"

        # -- early recognition: never download what we already have -------
        if file_unique_id:
            parts, kind = await self.find_reusable_by_unique_id(file_unique_id)
            if parts:
                await self.db.bump("dedup_unique_id_reuse")
                res = await self._reuse_archive(
                    parts, tg_id=tg_id, chat_id=chat_id, status_msg_id=status_msg_id,
                    profile_key=edu480.PROFILE_KEY, sha=parts[0]["source_sha256"] or "",
                    size_bytes=size_bytes, reuse_kind="exact")
                res["kind"] = kind
                return res

        lock_key = f"fu:{file_unique_id or local_path or uuid.uuid4().hex}"
        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                if not is_admin:
                    await conn.execute(
                        "SELECT pg_advisory_xact_lock(hashtext($1)::bigint)",
                        f"admit:{tg_id}")
                    await self._recheck_user_admission(conn, tg_id, size_bytes)
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1)::bigint)", lock_key)
                if file_unique_id:
                    inflight = await conn.fetchrow(
                        """
                        SELECT j.id FROM jobs j JOIN media_assets m ON m.id = j.media_id
                        WHERE m.tg_file_unique_id = $1 AND j.profile = 'edu480'
                          AND j.status IN ('queued', 'processing')
                        ORDER BY j.enqueued_at LIMIT 1
                        """, file_unique_id)
                    if inflight is not None:
                        await conn.execute(
                            """
                            INSERT INTO job_requesters
                                (job_id, tg_id, chat_id, source_message_id, status_message_id)
                            VALUES ($1,$2,$3,$4,$5) ON CONFLICT (job_id, tg_id) DO NOTHING
                            """, inflight["id"], tg_id, chat_id, source_msg_id, status_msg_id)
                        await self.db.bump("dedup_inflight_joined")
                        return {"outcome": "joined", "job_id": str(inflight["id"])}
                clean_src = media_mod.sanitize_filename(filename or "video", 120)
                media_id = await conn.fetchval(
                    """
                    INSERT INTO media_assets(size_bytes, filename, duration_s, width,
                        height, tg_file_id, tg_file_unique_id, name_norm, container)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id
                    """,
                    int(size_bytes or 0), clean_src, duration_s, width, height,
                    file_id, file_unique_id, clean_src.lower(), (mime or "")[:64] or None)
                dyn = getattr(self, "dynamic_config", None)
                admin_bypass = dyn.get_bool("admin_queue_bypass", False) if dyn else False
                priority = 70 if (is_admin and admin_bypass) else (await self.effective_limits(tg_id))["priority"]
                job_id = await conn.fetchval(
                    """
                    INSERT INTO jobs(requester_tg_id, media_id, profile, profile_version,
                        effective_profile, status, stage, priority, source_size,
                        source_path, source_message_id, status_message_id, chat_id,
                        output_name, source_filename, progress_changed_at, reserved_bytes,
                        is_admin_job, priority_boost)
                    VALUES ($1,$2,'edu480',$3,'edu480','queued','queued',$4,$5,$6,$7,$8,
                            $9,$10,$11, now(), 0, $12, 0)
                    RETURNING id
                    """,
                    tg_id, media_id, edu480.PROFILE_VERSION, priority, int(size_bytes or 0),
                    local_path, source_msg_id, status_msg_id, chat_id, out_stem,
                    (filename or "")[:255] or None, is_admin)
                await conn.execute(
                    """
                    INSERT INTO job_requesters
                        (job_id, tg_id, chat_id, source_message_id, status_message_id)
                    VALUES ($1,$2,$3,$4,$5) ON CONFLICT (job_id, tg_id) DO NOTHING
                    """, job_id, tg_id, chat_id, source_msg_id, status_msg_id)
        sched = getattr(self, "queue_scheduler", None)
        if sched:
            try:
                q_det = await sched.get_job_queue_details(str(job_id))
                if q_det:
                    await self.db.execute(
                        "UPDATE jobs SET initial_queue_pos = $2 WHERE id = $1",
                        job_id, q_det["global_queue_position"]
                    )
            except Exception as exc:
                log.warning("failed to set initial_queue_pos: %s", exc)
        await self.db.bump("requests_total")
        await self.db.bump("bytes_in", int(size_bytes or 0))
        await self.db.execute(
            "UPDATE users SET last_seen_at = now(), total_requests = total_requests + 1 "
            "WHERE tg_id = $1", tg_id)
        log.info("job registered (metadata only)", extra={
            "job_id": str(job_id), "user_id": tg_id,
            "detail": f"size={size_bytes} dur={duration_s}"})
        self.spawn(self.post_log_record(str(job_id)))
        self.kick_dispatch()
        info = await self.queue_info(str(job_id))
        return {"outcome": "queued", "job_id": str(job_id), **info}

    # ------------------------------------------------------------------
    # queue position + ETA (real data only)
    # ------------------------------------------------------------------
    async def throughput_rate(self) -> float:
        """Measured worker seconds per media second over recent jobs."""
        now = time.time()
        if self._rate_cache and now - self._rate_cache[1] < 60:
            return self._rate_cache[0]
        rate = None
        try:
            rate = await self.db.fetchval(
                """
                SELECT sum(extract(epoch FROM (x.encode_done_at - x.reserved_at)))
                       / NULLIF(sum(x.duration_s), 0)
                FROM (SELECT j.encode_done_at, j.reserved_at, m.duration_s
                      FROM jobs j JOIN media_assets m ON m.id = j.media_id
                      WHERE j.status = 'completed' AND j.reuse_of IS NULL
                        AND j.reserved_at IS NOT NULL AND j.encode_done_at IS NOT NULL
                        AND m.duration_s > 0
                      ORDER BY j.completed_at DESC LIMIT 50) x
                """)
        except Exception:  # noqa: BLE001 - estimate only
            rate = None
        try:
            rate = float(rate) if rate else edu480.DEFAULT_SEC_PER_MEDIA_SEC
        except (TypeError, ValueError):
            rate = edu480.DEFAULT_SEC_PER_MEDIA_SEC
        rate = min(max(rate, 0.01), 20.0)
        self._rate_cache = (rate, now)
        return rate

    async def _active_remaining_s(self, rate: float) -> tuple[float, int]:
        rows = await self.db.fetch(
            """
            SELECT j.progress, j.reserved_at, m.duration_s FROM jobs j
            JOIN media_assets m ON m.id = j.media_id
            WHERE j.status = 'processing' AND j.stage = ANY($1::text[])
            """, list(SLOT_STAGES))
        total = 0.0
        for r in rows:
            cost = edu480.job_cost_seconds(r["duration_s"], rate)
            prog = float(r["progress"] or 0)
            if prog > 0:
                total += cost * (100 - prog) / 100
            else:
                started = r["reserved_at"]
                elapsed = 0.0
                if started is not None:
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                total += max(cost * 0.1, cost - elapsed)
        return total, len(rows)

    async def queue_info(self, job_id: str) -> dict:
        """Position, jobs ahead, busy workers and an ETA for one job."""
        sched = getattr(self, "queue_scheduler", None)
        if sched:
            try:
                details = await sched.get_job_queue_details(str(job_id))
                if details:
                    init_pos = await self.db.fetchval(
                        "SELECT initial_queue_pos FROM jobs WHERE id = $1", uuid.UUID(str(job_id))
                    )
                    return {
                        "position": details["global_queue_position"],
                        "ahead": details["jobs_ahead"],
                        "busy": await self.busy_slots(),
                        "slots": details["active_workers"],
                        "total_queued": details["total_queued"],
                        "initial_position": init_pos or details["global_queue_position"],
                        "eta_seconds": details["estimated_wait_seconds"],
                        "algorithm_fa": details["algorithm_fa"],
                    }
            except Exception as exc:
                log.warning("queue_scheduler details error: %s", exc)

        row = await self.db.fetchrow(
            "SELECT status, priority, enqueued_at FROM jobs WHERE id = $1",
            uuid.UUID(job_id))
        if row is None or row["status"] != "queued":
            return {"position": 0, "ahead": 0}
        ahead_rows = await self.db.fetch(
            """
            SELECT m.duration_s FROM jobs j JOIN media_assets m ON m.id = j.media_id
            WHERE j.status = 'queued'
              AND (j.priority > $1 OR (j.priority = $1 AND j.enqueued_at < $2))
            """, row["priority"], row["enqueued_at"])
        rate = await self.throughput_rate()
        active_rem, busy = await self._active_remaining_s(rate)
        low, high = edu480.eta_range([r["duration_s"] for r in ahead_rows],
                                     active_rem if busy >= self.cfg.slots else 0.0,
                                     self.cfg.slots, rate)
        return {"position": len(ahead_rows) + 1, "ahead": len(ahead_rows),
                "busy": busy, "slots": self.cfg.slots,
                "eta_low": low, "eta_high": high}

    # ------------------------------------------------------------------
    # user-facing cards
    # ------------------------------------------------------------------
    def _job_kb(self, job_id: str, lang: str = "fa") -> InlineKeyboardMarkup:
        return make_cancel_kb(job_id)

    def queue_card_text(self, lang: str, *, name: str, size: int, dur, job_id: str,
                        info: dict, user_name: str = "", user_id: int | str = 0) -> str:
        if lang == "fa":
            dyn = getattr(self, "dynamic_config", None)
            bar_len = dyn.get_int("progress_bar_length", 12) if dyn else 12
            max_q = dyn.get_int("max_global_queue_size", 500) if dyn else 500
            pos = info.get("position", 1)
            ahead = info.get("ahead", max(0, pos - 1))
            total_q = info.get("total_queued", pos)
            init_pos = info.get("initial_position", pos)
            algo_fa = info.get("algorithm_fa", "عادلانه چرخشی (Fair-Share)")
            eta_s = info.get("eta_seconds", 0)
            return render_stage_0_queued(
                active_jobs=info.get("busy", 0),
                max_queue=max_q,
                total_queued=total_q,
                position=pos,
                initial_position=init_pos,
                jobs_ahead=ahead,
                algorithm_fa=algo_fa,
                elapsed_seconds=info.get("elapsed", 0.0),
                eta_seconds=eta_s,
                size_bytes=size,
                profile="edu480",
                user_name=user_name or name or "کاربر",
                user_id=user_id or 0,
                job_id=job_id,
                bar_length=bar_len,
            )
        eta = edu480.fmt_eta_range_fa(info.get("eta_low", 0), info.get("eta_high", 0)) \
            if lang != "en" else f"{info.get('eta_low', 0) // 60}-{info.get('eta_high', 0) // 60} min"
        return tr("queue_card", lang, name=name, size=media_mod.human_size(size),
                  dur=_clock(dur) if dur else "?", job=job_id[:8],
                  pos=info.get("position", "?"), ahead=info.get("ahead", "?"),
                  busy=info.get("busy", 0), slots=info.get("slots", self.cfg.slots),
                  eta=eta)

    async def _job_card_row(self, job_id: str):
        return await self.db.fetchrow(
            """
            SELECT j.*, m.duration_s AS m_duration, m.width AS m_w, m.height AS m_h,
                   m.fps AS m_fps, m.vcodec AS m_vcodec, m.acodec AS m_acodec,
                   m.bitrate AS m_bitrate,
                   u.first_name, u.username
            FROM jobs j
            JOIN media_assets m ON m.id = j.media_id
            LEFT JOIN users u ON u.tg_id = j.requester_tg_id
            WHERE j.id = $1
            """, uuid.UUID(str(job_id)))

    def stage_card_text(self, row, lang: str, info: dict | None = None) -> str:
        info = info or {}
        def _r(k, default=None):
            if hasattr(row, "get"):
                return row.get(k, default)
            try:
                return row[k]
            except Exception:
                return default

        stage = _r("stage") or _r("status") or "reserved"
        dyn = getattr(self, "dynamic_config", None)
        bar_len = dyn.get_int("progress_bar_length", 12) if dyn else 12

        def _since(col):
            v = _r(col)
            if v is None:
                return 0.0
            if getattr(v, "tzinfo", None) is None:
                v = v.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - v).total_seconds())

        if lang == "fa":
            jid = str(_r("id") or "")
            user_id = _r("requester_tg_id") or _r("tg_id") or _r("user_id") or 0
            user_name = _r("first_name") or _r("username") or str(user_id)
            source_size = int(_r("source_size") or 0)
            max_conc = dyn.get_int("active_encoding_workers", self.cfg.slots) if dyn else self.cfg.slots

            if stage in ("reserved", "downloading", "copying"):
                dl_workers = dyn.get_int("active_download_workers", 4) if dyn else 4
                processed = int(info.get("processed_bytes") or (_r("processed_bytes") or 0))
                total = max(1, int(_r("total_bytes") or source_size))
                speed = float(info.get("speed_bps") or (_r("current_speed_bps") or 0.0))
                elapsed = _since("download_started_at") or _since("reserved_at")
                eta = max(0.0, (total - processed) / speed) if speed > 0 else 0.0
                return render_stage_1_download(
                    active_jobs=1,
                    max_concurrent=dl_workers,
                    processed_bytes=processed,
                    total_bytes=total,
                    speed_bps=speed,
                    elapsed_seconds=elapsed,
                    eta_seconds=eta,
                    engine_name=str(_r("engine_info") or "TDLib v1.8.68"),
                    user_name=user_name,
                    user_id=user_id,
                    job_id=jid,
                    bar_length=bar_len,
                )
            elif stage in ("probing", "checking", "encoding"):
                pct = float(info.get("progress") or (_r("progress") or 0.0))
                processed = int((pct / 100.0) * source_size)
                speed_bps = float(info.get("speed_bps") or (_r("current_speed_bps") or 0.0))
                fps = float(info.get("fps") or 0.0)
                speed_x = float(info.get("speed") or 0.0)
                elapsed = _since("encode_started_at")
                dur = float(_r("m_duration") or 0.0)
                eta = (dur * (100.0 - pct) / 100.0) / speed_x if (speed_x > 0 and pct > 0 and dur > 0) else 0.0
                return render_stage_2_encode(
                    active_jobs=1,
                    max_concurrent=max_conc,
                    pct=pct,
                    processed_bytes=processed,
                    total_bytes=source_size,
                    speed_bps=speed_bps,
                    fps=fps,
                    speed_x=speed_x,
                    elapsed_seconds=elapsed,
                    eta_seconds=eta,
                    profile=str(_r("profile") or "edu480"),
                    engine_name="FFmpeg v8.0.1",
                    user_name=user_name,
                    user_id=user_id,
                    job_id=jid,
                    bar_length=bar_len,
                )
            else:  # uploading, completing, validating, archiving, upload_retry
                up_workers = dyn.get_int("active_upload_workers", 4) if dyn else 4
                out_size = int(_r("output_size") or source_size)
                pct = float(info.get("upload_progress") or (100.0 if stage == "completing" else (_r("progress") or 50.0)))
                uploaded = int((pct / 100.0) * out_size)
                speed_bps = float(info.get("speed_bps") or 0.0)
                elapsed = _since("upload_started_at") or _since("encode_done_at")
                eta = max(0.0, (out_size - uploaded) / speed_bps) if speed_bps > 0 else 0.0
                return render_stage_3_upload(
                    active_jobs=1,
                    max_concurrent=up_workers,
                    pct=pct,
                    uploaded_bytes=uploaded,
                    total_bytes=out_size,
                    speed_bps=speed_bps,
                    elapsed_seconds=elapsed,
                    eta_seconds=eta,
                    engine_name=str(_r("engine_info") or "TDLib v1.8.68"),
                    user_name=user_name,
                    user_id=user_id,
                    job_id=jid,
                    bar_length=bar_len,
                )

        icon, key = {
            "reserved": ("🟠", "st_reserved"), "downloading": ("📥", "st_downloading"),
            "probing": ("🔍", "st_probing"), "checking": ("🧮", "st_checking"),
            "copying": ("📋", "st_reserved"), "encoding": ("⚙️", "st_encoding"),
            "validating": ("🧪", "st_validating"), "completing": ("🧪", "st_validating"),
            "archiving": ("☁️", "st_uploading"), "uploading": ("☁️", "st_uploading"),
            "upload_retry": ("🔁", "st_upload_retry"),
        }.get(stage, ("⚙️", "st_encoding"))
        dims = edu480.target_dims(row["m_w"], row["m_h"])
        target = (f"{dims[0]}×{dims[1]}" if dims
                  else (f"{row['m_w']}×{row['m_h']}" if row["m_w"] else "480p"))

        if stage in ("reserved", "downloading", "copying"):
            body = tr("card_dl_body", lang, elapsed=_clock(_since("download_started_at")
                                                            or _since("reserved_at")),
                      size=media_mod.human_size(row["source_size"]))
        elif stage in ("probing", "checking"):
            kbps = edu480.video_kbps({"bitrate": row["m_bitrate"],
                                      "duration_s": row["m_duration"]}, row["source_size"])
            body = tr("card_probe_body", lang,
                      res=f"{row['m_w'] or '?'}×{row['m_h'] or '?'}",
                      fps=f"{row['m_fps'] or '?'}",
                      vcodec=(row["m_vcodec"] or "?").upper(),
                      acodec=(row["m_acodec"] or "-").upper(),
                      kbps=kbps or "?", target=target)
        elif stage == "encoding":
            try:
                pct = int(float(info.get("progress") or row["progress"] or 0))
            except (TypeError, ValueError):
                pct = 0
            pct = max(0, min(100, pct))
            speed = info.get("speed")
            eta = ""
            dur = row["m_duration"] or 0
            if speed and float(speed) > 0 and pct > 0 and dur:
                remaining = (float(dur) * (100 - pct) / 100) / float(speed)
                eta = tr("card_eta_suffix", lang, eta=_clock(remaining))
            filled = round(pct / 5)
            body = tr("card_enc_body", lang, bar="█" * filled + "░" * (20 - filled),
                      pct=pct, speed=(f"{float(speed):.1f}x" if speed else "…"),
                      elapsed=_clock(_since("encode_started_at")), eta=eta, target=target)
        else:
            body = tr("card_up_body", lang,
                      out=media_mod.human_size(row["output_size"]) if row["output_size"] else "…",
                      elapsed=_clock(_since("upload_started_at") or _since("encode_done_at")))
        return tr("stage_card", lang, icon=icon, stage=tr(key, lang),
                  name=edu480.output_filename(row["output_name"], row["source_filename"]),
                  size=media_mod.human_size(row["source_size"]),
                  dur=_clock(row["m_duration"]) if row["m_duration"] else "?",
                  job=str(row["id"])[:8], body=body)

    async def push_stage_card(self, job_id: str, info: dict | None = None,
                              force: bool = True) -> None:
        row = await self._job_card_row(job_id)
        if row is None:
            return
        for r in await self.db.fetch(
                "SELECT chat_id, status_message_id, tg_id FROM job_requesters "
                "WHERE job_id = $1 AND delivered = FALSE", row["id"]):
            lang = await self._lang(r["tg_id"])
            self._edit_status(r["chat_id"], r["status_message_id"],
                              self.stage_card_text(row, lang, info),
                              markup=self._job_kb(str(row["id"]), lang), force=force)

    async def refresh_queue_cards(self, budget: int = 15) -> None:
        """Re-render queued cards (position / ETA) - throttled to 10s on position changes."""
        sched = getattr(self, "queue_scheduler", None)
        dyn = getattr(self, "dynamic_config", None)
        rows = await self.db.fetch(
            """
            SELECT j.id, j.status_message_id, j.chat_id, j.requester_tg_id,
                   j.output_name, j.source_filename, j.source_size, j.enqueued_at,
                   j.initial_queue_pos, m.duration_s, u.first_name, u.username
            FROM jobs j
            JOIN media_assets m ON m.id = j.media_id
            LEFT JOIN users u ON u.tg_id = j.requester_tg_id
            WHERE j.status = 'queued'
            ORDER BY j.enqueued_at ASC
            LIMIT 500
            """
        )
        if not rows:
            return
        now = time.time()
        edits = 0
        if not hasattr(self, "_last_pos"):
            self._last_pos = {}
        for r in rows:
            jid = str(r["id"])
            if edits >= budget or not r["status_message_id"]:
                continue
            last_edit = self._card_edit_at.get(jid, 0.0)
            if now - last_edit < 10.0:
                continue

            q_info = await self.queue_info(jid)
            pos = q_info.get("position", 1)
            last_pos = self._last_pos.get(jid)
            # Only update if position has changed or 60s elapsed
            if last_pos is not None and last_pos == pos and (now - last_edit < 60.0):
                continue

            self._last_pos[jid] = pos
            self._card_edit_at[jid] = now
            elapsed = max(0.0, (datetime.now(timezone.utc) - (r["enqueued_at"].replace(tzinfo=timezone.utc) if r["enqueued_at"].tzinfo is None else r["enqueued_at"])).total_seconds()) if r["enqueued_at"] else 0.0
            q_info["elapsed"] = elapsed

            lang = await self._lang(r["requester_tg_id"])
            uname = r["first_name"] or r["username"] or str(r["requester_tg_id"])
            text = self.queue_card_text(
                lang,
                name=edu480.output_filename(r["output_name"], r["source_filename"]),
                size=r["source_size"] or 0,
                dur=r["duration_s"],
                job_id=jid,
                info=q_info,
                user_name=uname,
                user_id=r["requester_tg_id"],
            )
            chat = r["chat_id"] or r["requester_tg_id"]
            self._edit_status(chat, r["status_message_id"], text,
                              markup=self._job_kb(jid, lang), force=False)
            edits += 1

        if len(self._card_edit_at) > 20000:
            self._card_edit_at.clear()
            self._last_pos.clear()

    # ------------------------------------------------------------------
    # dispatcher
    # ------------------------------------------------------------------
    def kick_dispatch(self) -> None:
        self.spawn(self.dispatch_once())

    async def busy_slots(self) -> int:
        return int(await self.db.fetchval(
            "SELECT count(*) FROM jobs WHERE status = 'processing' "
            "AND stage = ANY($1::text[])", list(SLOT_STAGES)) or 0)

    async def dispatch_once(self) -> int:
        """Claim queued jobs while encode slots and disk allow. Returns #claimed."""
        if self._dispatch_lock.locked():
            return 0
        claimed = 0
        async with self._dispatch_lock:
            dyn = getattr(self, "dynamic_config", None)
            target_workers = dyn.get_int("active_encoding_workers", self.cfg.slots) if dyn else self.cfg.slots
            cap = target_workers + max(0, self.cfg.prefetch_jobs)
            busy = await self.busy_slots()
            sched = getattr(self, "queue_scheduler", None)
            while busy < cap:
                if sched:
                    nxt = await sched.claim_next_job(self.worker_id)
                else:
                    nxt = await self._claim_next(0)
                if nxt is None:
                    break
                job_id = str(nxt["id"])
                task = asyncio.create_task(self._run_pipeline(job_id))
                self._pipelines[job_id] = task
                self._bg_tasks.add(task)
                task.add_done_callback(lambda t, j=job_id: (
                    self._pipelines.pop(j, None), self._bg_tasks.discard(t)))
                busy += 1
                claimed += 1
        return claimed

    async def _claim_next(self, reserve_bytes: int):
        """Atomic FIFO claim with per-user fairness and anti-starvation aging.

        Users that already have a job in an encode slot sort behind users
        that have none, so one heavy submitter cannot occupy every worker
        while others wait; with no one else waiting, spare capacity is still
        used. SKIP LOCKED + the status predicate make double-claims
        impossible, also across several processes/servers.

        Aging (V3 §12.1): effective priority gains +5 per waiting hour, capped
        at +15, so a job that has waited ~3h outranks a freshly-submitted
        higher-priority job — no user/tier can starve indefinitely.
        """
        return await self.db.fetchrow(
            """
            UPDATE jobs SET status = 'processing', stage = 'reserved',
                   worker_id = $1, reserved_at = now(),
                   started_at = COALESCE(started_at, now()),
                   lease_expires_at = now() + make_interval(mins => $2),
                   reserved_bytes = $3, updated_at = now(), progress = 0
            WHERE id = (
                SELECT j.id FROM jobs j
                WHERE j.status = 'queued'
                ORDER BY (j.requester_tg_id IN (
                              -- hashed InitPlan (one tiny scan of the <=slots
                              -- processing rows) instead of a correlated
                              -- EXISTS per queued row: identical semantics,
                              -- keeps claim latency flat in deep queues
                              SELECT a.requester_tg_id FROM jobs a
                              WHERE a.status = 'processing'
                                AND a.stage = ANY($4::text[]))) DESC,
                         j.priority
                           + LEAST(15, FLOOR(EXTRACT(EPOCH FROM
                                 (now() - j.enqueued_at)) / 3600.0) * 5)::int
                           DESC,
                         j.enqueued_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1)
              AND status = 'queued'
            RETURNING id, requester_tg_id
            """,
            self.worker_id, int(self.cfg.lease_minutes), int(reserve_bytes),
            list(SLOT_STAGES))

    async def _notify_disk_block(self, need: int) -> None:
        now = time.time()
        if now - self._disk_block_notified < 3600:
            return
        self._disk_block_notified = now
        log.warning("dispatch held: insufficient disk for next job",
                    extra={"detail": f"need={need} free={self._disk_free()}"})
        await self.notify_admins(
            f"⚠️ صف متوقف است: فضای دیسک برای کار بعدی کافی نیست "
            f"(نیاز {media_mod.human_size(need)}، آزاد {media_mod.human_size(self._disk_free())}).")

    async def reap_stale_leases(self) -> None:
        """Requeue pre-encode jobs whose owner stopped heart-beating."""
        rows = await self.db.fetch(
            """
            SELECT id, retries FROM jobs
            WHERE status = 'processing' AND stage = ANY($1::text[])
              AND encore_job_id IS NULL
              AND lease_expires_at IS NOT NULL AND lease_expires_at < now()
            """, list(PRE_ENCODE_STAGES))
        for r in rows:
            jid = str(r["id"])
            if jid in self._pipelines:
                continue
            await self.db.execute(
                "UPDATE jobs SET status = 'queued', stage = 'queued', worker_id = NULL, "
                "lease_expires_at = NULL, reserved_bytes = 0, retries = retries + 1, "
                "updated_at = now() WHERE id = $1 AND status = 'processing' "
                "AND encore_job_id IS NULL", r["id"])
            log.warning("stale lease recovered, job requeued", extra={"job_id": jid})

    # ------------------------------------------------------------------
    # worker pipeline
    # ------------------------------------------------------------------
    async def _still_mine(self, job_id: str) -> bool:
        st = await self.db.fetchval(
            "SELECT status FROM jobs WHERE id = $1 AND worker_id = $2",
            uuid.UUID(job_id), self.worker_id)
        return st == "processing"

    async def _set_stage_ts(self, job_id: str, stage: str, ts_col: str | None = None) -> bool:
        extra = f", {ts_col} = now()" if ts_col else ""
        res = await self.db.execute(
            f"UPDATE jobs SET stage = $2{extra}, updated_at = now(), "
            "lease_expires_at = now() + make_interval(mins => $3) "
            "WHERE id = $1 AND status = 'processing'",
            uuid.UUID(job_id), stage, int(self.cfg.lease_minutes))
        return res != "UPDATE 0"

    async def _heartbeat(self, job_id: str) -> None:
        try:
            while True:
                await asyncio.sleep(60)
                await self.db.execute(
                    "UPDATE jobs SET lease_expires_at = now() + make_interval(mins => $2) "
                    "WHERE id = $1 AND status = 'processing'",
                    uuid.UUID(job_id), int(self.cfg.lease_minutes))
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001
            log.exception("lease heartbeat failed", extra={"job_id": job_id})

    async def _run_pipeline(self, job_id: str) -> None:
        hb = asyncio.create_task(self._heartbeat(job_id))
        row = None
        try:
            row = await self.db.fetchrow(
                """
                SELECT j.*, m.tg_file_id, m.tg_file_unique_id, m.duration_s AS m_duration,
                       m.fingerprinted, m.sha256 AS m_sha
                FROM jobs j JOIN media_assets m ON m.id = j.media_id WHERE j.id = $1
                """, uuid.UUID(job_id))
            if row is None or row["status"] != "processing":
                return
            await self.update_log_record(job_id, "processing")
            # 1) download (first moment the source touches the disk)
            await self._set_stage_ts(job_id, "downloading", "download_started_at")
            await self.push_stage_card(job_id)
            try:
                source = await self._acquire_source(row)
            except SourceUnavailable as exc:
                await self._retry_or_fail(row, "download", str(exc)[:200])
                return
            await self.db.execute(
                "UPDATE jobs SET download_done_at = now(), source_path = $2 WHERE id = $1",
                uuid.UUID(job_id), str(source))
            if not await self._still_mine(job_id):
                await self._discard_source(job_id, source)
                return
            # 2) probe
            await self._set_stage_ts(job_id, "probing")
            try:
                probe = await media_mod.probe_video(source)
            except media_mod.MediaError as exc:
                await self.fail_job(row, "invalid_media", str(exc)[:200])
                await self._discard_source(job_id, source)
                return
            size = int(probe.get("size_bytes") or source.stat().st_size)
            await self.db.execute(
                """
                UPDATE media_assets SET size_bytes = $2, duration_s = $3, width = $4,
                    height = $5, fps = $6, vcodec = $7, acodec = $8, audio_channels = $9,
                    container = $10, bitrate = $11, probe = $12::jsonb
                WHERE id = $1
                """, row["media_id"], size, probe.get("duration_s"), probe.get("width"),
                probe.get("height"), probe.get("fps"), probe.get("vcodec"),
                probe.get("acodec"), probe.get("audio_channels"), probe.get("container"),
                probe.get("bitrate"), json.dumps(probe))
            await self.push_stage_card(job_id)
            requester_admin = row["requester_tg_id"] in await self.admin_ids()
            try:
                await self.check_duration_limit(row["requester_tg_id"],
                                                probe.get("duration_s"),
                                                is_admin=requester_admin)
            except Exception as exc:  # AdmissionError("too_long")
                await self.fail_job(row, "too_long", f"duration {probe.get('duration_s')}s: {exc}")
                await self._discard_source(job_id, source)
                return
            # 3) exact duplicate / own output (content hash, before any encode)
            await self._set_stage_ts(job_id, "checking")
            sha = row["m_sha"] or await media_mod.sha256_file(source)
            await self.db.execute("UPDATE media_assets SET sha256 = $2 WHERE id = $1",
                                  row["media_id"], sha)
            parts, kind = await self.find_reusable_by_sha(sha)
            if parts and await self._still_mine(job_id):
                await self._complete_from_archive(row, parts, kind)
                await self._discard_source(job_id, source)
                return
            if not await self._still_mine(job_id):
                await self._discard_source(job_id, source)
                return
            # 4) decide: compliant sources are remuxed, never re-encoded
            decision = edu480.decide(probe, size, self.cfg)
            if decision.action == "encode":
                guard = edu480.predict_guard(probe, size, self.cfg)
                if guard is not None:
                    decision = guard
            await self.db.execute("UPDATE jobs SET decision = $2 WHERE id = $1",
                                  uuid.UUID(job_id), f"{decision.action}: {decision.reason}"[:300])
            log.info("edu480 decision", extra={"job_id": job_id,
                                                "detail": f"{decision.action} ({decision.reason})"})
            if not row["fingerprinted"] and self.cfg.similarity_reuse:
                self.fingerprinter.submit(row["media_id"], str(source), probe.get("duration_s") or 0.0)
            if decision.action == "remux":
                await self._run_remux(job_id, source)
                return
            if decision.action == "deliver_source":
                await self._deliver_source(job_id, source, probe)
                return
            await self._submit_encode(job_id, row, source, probe)
        except asyncio.CancelledError:
            # Cancelled by moderation / user cancel / shutdown. Status was set
            # by whoever cancelled; on shutdown it stays 'processing' and is
            # requeued by recover_on_startup.
            raise
        except Exception:  # noqa: BLE001
            log.exception("pipeline crashed", extra={"job_id": job_id})
            try:
                fresh = await self.db.fetchrow("SELECT * FROM jobs WHERE id = $1",
                                               uuid.UUID(job_id))
                if fresh and fresh["status"] == "processing" and not fresh["encore_job_id"]:
                    await self._retry_or_fail(fresh, "unknown", "internal pipeline error")
            except Exception:  # noqa: BLE001
                log.exception("pipeline failure handling failed", extra={"job_id": job_id})
        finally:
            hb.cancel()
            self.kick_dispatch()

    async def _acquire_source(self, row) -> Path:
        """Local path of the source; downloads via the Local Bot API only now."""
        if row["source_path"] and Path(row["source_path"]).is_file():
            return Path(row["source_path"])
        file_id = row["tg_file_id"]
        if not file_id:
            raise SourceUnavailable("no telegram file id and no local source")
        fut = asyncio.ensure_future(self.bot.get_file(file_id))
        try:
            tg_file = await asyncio.shield(fut)
        except asyncio.CancelledError:
            # The Local Bot API keeps downloading server-side; remove the
            # file as soon as it lands so a cancelled job leaves nothing.
            def _later(f: asyncio.Future) -> None:
                if f.cancelled() or f.exception() is not None:
                    return
                self.spawn(self._delete_botapi_path(f.result().file_path,
                                                    row["tg_file_unique_id"]))
            fut.add_done_callback(_later)
            raise
        except TelegramAPIError as exc:
            raise SourceUnavailable(f"getFile failed: {str(exc)[:150]}") from exc
        path = await self.resolve_local_path(tg_file.file_path)
        if path is None:
            raise SourceUnavailable("downloaded file not readable")
        return path

    async def _discard_source(self, job_id: str, source: Path | None) -> None:
        """Remove the job's source bytes unless another active job needs them."""
        if source is None:
            return
        await self._delete_botapi_path(str(source), None, exclude_job=job_id)

    async def _delete_botapi_path(self, path: str | None, file_unique_id: str | None,
                                  exclude_job: str | None = None) -> None:
        if not self.cfg.delete_botapi_source or not path:
            return
        p = Path(path)
        if not p.is_absolute():
            p = Path(self.cfg.botapi_dir) / p
        try:
            if not str(p.resolve()).startswith(str(Path(self.cfg.botapi_dir).resolve()) + os.sep):
                return  # never delete outside the Local Bot API tree
        except OSError:
            return
        try:
            exclude = uuid.UUID(exclude_job) if exclude_job else None
        except ValueError:
            exclude = None
        busy = await self.db.fetchval(
            """
            SELECT count(*) FROM jobs j JOIN media_assets m ON m.id = j.media_id
            WHERE j.status IN ('queued', 'processing')
              AND ($3::uuid IS NULL OR j.id <> $3::uuid)
              AND (j.source_path = $1 OR ($2::text IS NOT NULL AND m.tg_file_unique_id = $2))
            """, str(p), file_unique_id, exclude)
        if int(busy or 0) > 0:
            return
        try:
            await asyncio.to_thread(p.unlink, True)
            log.info("local bot api source removed", extra={"job_id": exclude_job or "-"})
        except OSError as exc:
            log.warning("could not remove bot api source",
                        extra={"detail": media_mod.redact(str(exc))[:120]})

    async def _complete_from_archive(self, row, parts, kind: str) -> None:
        """Exact duplicate found after download: deliver, skip the encode."""
        job_id = str(row["id"])
        first = parts[0]
        await self.db.bump("dedup_exact_reuse")
        done = await self.db.fetchval(
            """
            UPDATE jobs SET status = 'completed', stage = 'completed', reserved_bytes = 0,
                reuse_of = $2, output_media_id = $3, output_size = $4, archived = TRUE,
                progress = 100, completed_at = now(), encode_done_at = now(),
                decision = $5, updated_at = now()
            WHERE id = $1 AND status = 'processing' RETURNING id
            """, row["id"], first["id"], first["output_media_id"],
            sum(int(p["output_size"] or 0) for p in parts), f"reuse: {kind}")
        if not done:
            return
        fresh = await self.db.fetchrow(
            "SELECT j.*, m.duration_s AS source_duration FROM jobs j "
            "JOIN media_assets m ON m.id = j.media_id WHERE j.id = $1", row["id"])
        out_probe = await self.db.fetchval(
            "SELECT probe FROM media_assets WHERE id = $1", first["output_media_id"])
        try:
            out_probe = json.loads(out_probe) if out_probe else {}
        except (TypeError, ValueError):
            out_probe = {}
        await self._deliver_to_requesters(
            fresh, first["id"], first["output_media_id"], first["output_tg_file_id"],
            out_size=int(fresh["output_size"] or 0), out_probe=out_probe,
            part_ids=[p["id"] for p in parts] if len(parts) > 1 else None,
            part_total=len(parts))
        await self.db.execute("UPDATE jobs SET delivered_at = now() WHERE id = $1", row["id"])
        await self.update_log_record(job_id, "completed")
        await self._cleanup_job_dirs(job_id, keep_output=False)

    async def _run_remux(self, job_id: str, source: Path) -> None:
        out_dir = Path(self.cfg.media_out) / job_id
        out_dir.mkdir(parents=True, exist_ok=True)
        await self._set_stage_ts(job_id, "encoding", "encode_started_at")
        await self.db.execute(
            "UPDATE jobs SET effective_profile = 'remux' WHERE id = $1", uuid.UUID(job_id))
        try:
            await asyncio.to_thread(media_mod.remux_to_mp4, str(source),
                                    str(out_dir / "out.mp4"))
        except media_mod.MediaError as exc:
            row = await self.db.fetchrow("SELECT * FROM jobs WHERE id = $1", uuid.UUID(job_id))
            await self.fail_job(row, "remux", str(exc)[:200])
            return
        await self.db.execute(
            "UPDATE jobs SET encode_done_at = now(), stage = 'validating', reserved_bytes = 0 "
            "WHERE id = $1 AND status = 'processing'", uuid.UUID(job_id))
        full = await self.db.fetchrow(
            "SELECT j.*, m.duration_s AS source_duration FROM jobs j "
            "JOIN media_assets m ON m.id = j.media_id WHERE j.id = $1", uuid.UUID(job_id))
        if full and full["status"] == "processing":
            await self.complete_job(full, None)

    async def _deliver_source(self, job_id: str, source: Path, probe: dict) -> None:
        """Complete a job by delivering the SOURCE itself (predictive no-gain
        skip). The user already owns this media and the deterministic bpp
        guard says an encode would not shrink it meaningfully — so no CPU is
        spent and no degraded copy is produced. Mirrors the no_gain branch
        of the completion path; evidence lives in jobs.decision."""
        jid = uuid.UUID(job_id)
        done = await self.db.fetchval(
            "UPDATE jobs SET status = 'completed', stage = 'completed', progress = 100, "
            "archived = FALSE, is_no_gain = TRUE, output_size = source_size, "
            "reserved_bytes = 0, completed_at = now(), "
            "encode_done_at = COALESCE(encode_done_at, now()), updated_at = now() "
            "WHERE id = $1 AND status = 'processing' RETURNING id", jid)
        if not done:
            return
        await self.db.bump("no_gain_events")
        await self.db.bump("jobs_encoded")
        row = await self.db.fetchrow(
            "SELECT j.*, m.duration_s AS source_duration, m.tg_file_id, m.sha256 AS m_sha "
            "FROM jobs j JOIN media_assets m ON m.id = j.media_id WHERE j.id = $1", jid)
        if row is None:
            return
        await self.push_stage_card(job_id)
        await self._deliver_to_requesters(
            row, None, row["media_id"], row["tg_file_id"],
            no_gain=True, out_size=int(row["source_size"] or 0), out_probe=probe)
        await self._finish_delivery(row, keep_output=False, keep_source=True)
        self.kick_dispatch()

    async def _submit_encode(self, job_id: str, row, source: Path, probe: dict) -> None:
        used_path = await self._stage_source(job_id, source, row["source_filename"] or "source.mp4")
        others = int(await self.db.fetchval(
            "SELECT count(*) FROM jobs WHERE status = 'processing' AND stage = 'encoding'"
        ) or 0)
        threads = self.cfg.ffmpeg_threads_single if others == 0 \
            else self.cfg.ffmpeg_threads_multi
        params = edu480.encode_params(probe, self.cfg, threads)
        input_params = None
        try:
            input_params = json.loads(row["input_params"]) if row["input_params"] else None
        except (TypeError, ValueError):
            input_params = None
        if (row["profile_params"] and "aresample" in str(row["profile_params"])):
            params["af"] = "aresample=async=1:first_pts=0"
        callback = (f"http://bot:8080/internal/encore-callback"
                    f"?job={job_id}&sig={self._callback_sig(job_id)}")
        if not await self._still_mine(job_id):
            return
        try:
            encore_id = await self.encre.submit_job(
                profile="edu480", output_folder=f"{self.cfg.media_out}/{job_id}",
                base_name="out", input_uri=used_path, external_id=job_id,
                callback_uri=callback, profile_params=params, input_params=input_params)
        except EncoreError as exc:
            fresh = await self.db.fetchrow("SELECT * FROM jobs WHERE id = $1", uuid.UUID(job_id))
            await self._retry_or_fail(fresh, "encore_api", str(exc)[:300])
            return
        claimed = await self.db.execute(
            "UPDATE jobs SET encore_job_id = $2, stage = 'encoding', effective_profile = 'edu480', "
            "profile_params = $3::jsonb, encode_started_at = now(), progress = 0, "
            "progress_changed_at = now(), updated_at = now() "
            "WHERE id = $1 AND status = 'processing' AND encore_job_id IS NULL",
            uuid.UUID(job_id), encore_id, json.dumps(params))
        if claimed == "UPDATE 0":
            # Cancelled between our last check and the submit: stop the encode.
            try:
                await self.encre.cancel_job(encore_id)
            except EncoreError:
                pass
            return
        await self.push_stage_card(job_id)
        log.info("job submitted to encore", extra={"job_id": job_id, "encore_job": encore_id,
                                                    "detail": f"vf={params['vf']} fps={params['fpsf']}"})

    # ------------------------------------------------------------------
    # cancellation + moderation
    # ------------------------------------------------------------------
    def stop_pipeline(self, job_id: str) -> None:
        task = self._pipelines.get(str(job_id))
        if task is not None and not task.done():
            task.cancel()

    async def moderate_job(self, job_id: str, actor_id: int) -> dict:
        """Owner decision: remove the video and ban its submitter. Idempotent.

        Coordinates DB state, the in-process pipeline task (download), the
        Encore/FFmpeg process, temp storage, the Local Bot API source, the
        reusable archive and the channel record. Only files belonging to the
        targeted user's jobs are touched.
        """
        try:
            jid = uuid.UUID(str(job_id))
        except ValueError:
            return {"ok": False, "why": "bad_id"}
        row = await self.db.fetchrow("SELECT * FROM jobs WHERE id = $1", jid)
        if row is None:
            return {"ok": False, "why": "not_found"}
        target = row["requester_tg_id"]
        if await self.is_owner(target):
            return {"ok": False, "why": "is_owner"}
        inserted = await self.db.fetchval(
            """
            INSERT INTO moderation_actions(job_id, target_tg_id, action, actor_tg_id,
                job_status_before, job_stage_before, details)
            VALUES ($1, $2, 'remove_and_ban', $3, $4, $5, $6)
            ON CONFLICT DO NOTHING RETURNING id
            """, jid, target, actor_id, row["status"], row["stage"],
            "delivered before moderation" if row["status"] == "completed" else None)
        await self.db.execute(
            "UPDATE users SET is_blocked = TRUE, banned_at = COALESCE(banned_at, now()), "
            "ban_reason = COALESCE(ban_reason, $2) WHERE tg_id = $1",
            target, f"moderation: job {str(jid)[:8]}")
        # Cancel every active job of the banned user (queued ones simply
        # leave the queue; running ones are stopped at every layer).
        for j in await self.db.fetch(
                "SELECT * FROM jobs WHERE requester_tg_id = $1 "
                "AND status IN ('queued','processing')", target):
            await self.cancel_job(j, by_admin=True, reason="moderation")
        # The content must never be served again from the cache.
        blocked = await self.db.fetch(
            "UPDATE archive_records SET status = 'blocked' WHERE source_media_id = $1 "
            "AND status IN ('active','no_gain') RETURNING channel_id, message_id",
            row["media_id"])
        for b in blocked:
            if b["message_id"]:
                try:
                    await self.bot.delete_message(b["channel_id"], b["message_id"])
                except TelegramAPIError:
                    pass
        await self._cleanup_job_dirs(str(jid), keep_output=False)
        src = row["source_path"]
        if src:
            await self._delete_botapi_path(src, None)
        # Channel record: drop the video copy, leave an auditable text record.
        if row["log_chat_id"] and row["log_message_id"]:
            try:
                await self.bot.delete_message(row["log_chat_id"], row["log_message_id"])
            except TelegramAPIError:
                pass
            try:
                u = await self.db.fetchrow(
                    "SELECT first_name, username FROM users WHERE tg_id = $1", target)
                await self.bot.send_message(
                    row["log_chat_id"],
                    f"🗑 ویدیو حذف و کاربر مسدود شد\n🧾 کار: {str(jid)[:8]}\n"
                    f"👤 {(u['first_name'] if u else '') or ''} "
                    f"@{(u['username'] if u else '') or '-'} ({target})\n"
                    f"📍 وضعیت قبلی: {row['status']}/{row['stage'] or '-'}\n"
                    f"🕒 {_ts(datetime.now(timezone.utc))}")
            except TelegramAPIError:
                pass
        await audit_mod.log_action(self.db, f"owner:{actor_id}", "owner",
                                   "moderation.remove_ban", target,
                                   f"job={jid} status_before={row['status']}",
                                   source="telegram")
        if inserted:
            await self.db.bump("moderation_bans")
            try:
                await self.bot.send_message(target, tr("mod_user_notice", await self._lang(target)))
            except TelegramAPIError:
                pass
        return {"ok": True, "already": not bool(inserted), "target": target,
                "status_before": row["status"]}

    # ------------------------------------------------------------------
    # private channel activity record
    # ------------------------------------------------------------------
    def _mod_kb(self, job_id: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=tr("mod_btn_remove_ban", "fa"),
                                 callback_data=f"mod:ask:{job_id}")]])

    async def _log_caption(self, job_id: str, status: str) -> str | None:
        r = await self.db.fetchrow(
            """
            SELECT j.id, j.requester_tg_id, j.output_name, j.source_filename,
                   j.source_size, j.enqueued_at, m.duration_s,
                   u.first_name, u.username
            FROM jobs j JOIN media_assets m ON m.id = j.media_id
            LEFT JOIN users u ON u.tg_id = j.requester_tg_id WHERE j.id = $1
            """, uuid.UUID(job_id))
        if r is None:
            return None
        labels = {"queued": "🟡 در صف", "processing": "⚙️ در حال پردازش",
                  "completed": "✅ تحویل شد", "failed": "❌ ناموفق",
                  "cancelled": "🚫 لغو شد"}
        return tr("log_record", "fa",
                  name=(r["first_name"] or "?")[:40],
                  uname=f"@{r['username']}" if r["username"] else "",
                  uid=r["requester_tg_id"], job=str(r["id"]),
                  src=(r["source_filename"] or "-")[:80],
                  out=edu480.output_filename(r["output_name"], r["source_filename"]),
                  size=media_mod.human_size(r["source_size"]),
                  dur=_clock(r["duration_s"]) if r["duration_s"] else "?",
                  ts=_ts(r["enqueued_at"]),
                  status=labels.get(status, status))[:1024]

    async def post_log_record(self, job_id: str) -> None:
        """One channel record per job: a Telegram-side copy of the user's video
        (no server download/upload) + requester identity + moderation button."""
        chan = self.log_channel()
        if not chan:
            return
        row = await self.db.fetchrow(
            "SELECT chat_id, source_message_id, log_message_id FROM jobs WHERE id = $1",
            uuid.UUID(job_id))
        if row is None or row["log_message_id"]:
            return
        caption = await self._log_caption(job_id, "queued")
        msg_id = None
        try:
            if row["chat_id"] and row["source_message_id"]:
                m = await self.bot.copy_message(
                    chat_id=chan, from_chat_id=row["chat_id"],
                    message_id=row["source_message_id"], caption=caption,
                    reply_markup=self._mod_kb(job_id))
                msg_id = m.message_id
            else:
                m = await self.bot.send_message(chan, caption or job_id,
                                                reply_markup=self._mod_kb(job_id))
                msg_id = m.message_id
        except TelegramAPIError as exc:
            log.warning("channel log record failed", extra={"job_id": job_id,
                                                            "detail": str(exc)[:150]})
            return
        await self.db.execute(
            "UPDATE jobs SET log_chat_id = $2, log_message_id = $3 WHERE id = $1",
            uuid.UUID(job_id), chan, msg_id)

    async def update_log_record(self, job_id: str, status: str) -> None:
        try:
            jid = uuid.UUID(str(job_id))
        except ValueError:
            return
        row = await self.db.fetchrow(
            "SELECT log_chat_id, log_message_id, source_message_id FROM jobs WHERE id = $1",
            jid)
        if row is None or not row["log_message_id"]:
            return
        caption = await self._log_caption(job_id, status)
        try:
            if row["source_message_id"]:
                await self.bot.edit_message_caption(
                    chat_id=row["log_chat_id"], message_id=row["log_message_id"],
                    caption=caption, reply_markup=self._mod_kb(job_id))
            else:
                await self.bot.edit_message_text(
                    chat_id=row["log_chat_id"], message_id=row["log_message_id"],
                    text=caption or job_id, reply_markup=self._mod_kb(job_id))
        except TelegramAPIError:
            pass

    # ------------------------------------------------------------------
    # upload retry (never re-encodes)
    # ------------------------------------------------------------------
    async def resume_upload(self, job_id: str) -> bool:
        """Retry archive upload/delivery of an already-encoded output."""
        row = await self.db.fetchrow("SELECT * FROM jobs WHERE id = $1", uuid.UUID(job_id))
        if row is None or row["status"] not in ("failed", "processing"):
            return False
        if self._job_output_file(job_id) is None:
            return False
        ok = await self.db.fetchval(
            "UPDATE jobs SET status = 'processing', stage = 'upload_retry', "
            "error_category = NULL, error_message = NULL, completed_at = NULL, "
            "updated_at = now() "
            "WHERE id = $1 AND status IN ('failed','processing') RETURNING id",
            uuid.UUID(job_id))
        if not ok:
            return False
        full = await self.db.fetchrow(
            "SELECT j.*, m.duration_s AS source_duration FROM jobs j "
            "JOIN media_assets m ON m.id = j.media_id WHERE j.id = $1", uuid.UUID(job_id))
        self.spawn(self.complete_job(full, None, resume=True))
        return True

    async def schedule_upload_retry(self, row, detail: str) -> None:
        attempts = int(row["upload_attempts"] or 0) + 1 if "upload_attempts" in row.keys() else 1
        job_id = str(row["id"])
        if attempts > self.cfg.upload_retries:
            # Keep the encoded output for the retention window so a later
            # manual retry only uploads (fail_job keeps 'upload' outputs).
            await self.fail_job(row, "upload", detail)
            return
        delay = min(600, 15 * (2 ** (attempts - 1)))
        await self.db.execute(
            "UPDATE jobs SET stage = 'upload_retry', upload_attempts = $2, "
            "error_message = $3, updated_at = now() WHERE id = $1 AND status = 'processing'",
            row["id"], attempts, media_mod.redact(detail)[:300])
        log.warning("archive upload failed, retry scheduled (no re-encode)",
                    extra={"job_id": job_id, "detail": f"attempt={attempts} delay={delay}s"})
        await self.push_stage_card(job_id)

        async def _later():
            await asyncio.sleep(delay)
            await self.resume_upload(job_id)
        self.spawn(_later())

    # ------------------------------------------------------------------
    # startup recovery
    # ------------------------------------------------------------------
    async def recover_queue_on_startup(self) -> None:
        """Pre-encode work of a dead process is requeued (source kept if it
        was already downloaded - no second download); post-encode work is
        resumed from the existing output (no second encode)."""
        n = await self.db.execute(
            "UPDATE jobs SET status = 'queued', stage = 'queued', worker_id = NULL, "
            "lease_expires_at = NULL, reserved_bytes = 0, updated_at = now() "
            "WHERE status = 'processing' AND encore_job_id IS NULL "
            "AND stage = ANY($1::text[])", list(PRE_ENCODE_STAGES))
        if n and n != "UPDATE 0":
            log.warning("requeued interrupted pre-encode jobs", extra={"detail": n})
        for r in await self.db.fetch(
                "SELECT id FROM jobs WHERE status = 'processing' "
                "AND stage IN ('upload_retry','uploading','archiving','validating','completing') "
                "AND (encore_job_id IS NULL OR effective_profile = 'remux')"):
            if self._job_output_file(str(r["id"])) is not None:
                await self.resume_upload(str(r["id"]))
