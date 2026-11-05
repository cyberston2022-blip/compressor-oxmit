"""Job orchestration: admission, dedup, Encore submission, completion, delivery."""

from __future__ import annotations

import asyncio
import hashlib
import hmac as hmac_mod
import json
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramRetryAfter
from aiogram.types import (BotCommand, BotCommandScopeChat, FSInputFile,
                           InlineKeyboardButton, InlineKeyboardMarkup)

from . import archive as archive_mod
from . import audit as audit_mod
from . import decision_engine, dedup, media as media_mod
from .config import Settings
from .encore_client import EncoreClient, EncoreError, EncoreNotFound
from .log import get_logger
from .profiles import (BY_KEY, compute_target_params, crf_for_level,
                       preset_for_level, resolve_variant)
from .texts import tr

log = get_logger("oxmit.engine")

TRANSIENT_CATEGORIES = {"encore_api", "download", "network", "stuck", "archive", "source_unavailable"}
MUX_ERROR_MARKERS = ("error muxing a packet", "invalid argument", "non monotonic")
COPY_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".ts", ".m2ts", ".flv", ".wmv",
             ".mpg", ".mpeg", ".m4v", ".3gp"}


@dataclass
class RuntimeState:
    archive_channel_id: int | None = None
    paused: bool = False
    started_at: float = field(default_factory=time.time)
    bot_username: str = ""
    global_thumb: str | None = None


class AdmissionError(Exception):
    def __init__(self, code: str, **fmt) -> None:
        super().__init__(code)
        self.code = code
        self.fmt = fmt


class AdmissionDeferred(Exception):
    """Disk capacity is temporarily unavailable - defer, don't reject."""

    def __init__(self, need: int) -> None:
        super().__init__("deferred")
        self.need = need


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_uuid(value) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _ensure_tz(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _fmt_clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _load_json(v):
    if not v:
        return None
    if isinstance(v, dict):
        return v
    try:
        return json.loads(v)
    except (json.JSONDecodeError, TypeError):
        return None


def _permalink(channel_id, message_id) -> str | None:
    """t.me/c/ deep link for private supergroups/channels (-100 prefix only).

    Anything else (legacy group ids, plain chat ids) has no c/ link form;
    callers store NULL instead of a dead URL.
    """
    if not channel_id or not message_id:
        return None
    s = str(channel_id)
    if s.startswith("-100") and len(s) > 4:
        return f"https://t.me/c/{s[4:]}/{message_id}"
    return None


async def db_set_admin(db, tg_id: int, value: bool) -> None:
    """Promote/demote; creates the row if the target never used the bot."""
    await db.execute(
        "INSERT INTO users(tg_id, is_admin) VALUES ($1, $2) "
        "ON CONFLICT (tg_id) DO UPDATE SET is_admin = EXCLUDED.is_admin",
        tg_id, value,
    )


class Fingerprinter:
    """Serial background worker computing perceptual fingerprints."""

    def __init__(self, db, cfg: Settings) -> None:
        self.db = db
        self.cfg = cfg
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=200)

    def submit(self, media_id, path: str, duration: float) -> None:
        try:
            self.queue.put_nowait((str(media_id), path, duration))
        except asyncio.QueueFull:
            log.warning("fingerprint queue full, skipping", extra={"media_id": str(media_id)})

    async def run(self) -> None:
        while True:
            media_id, path, duration = await self.queue.get()
            try:
                frames = await media_mod.fingerprint(path, duration, self.cfg.media_tmp)
                await self.db.execute(
                    "UPDATE media_assets SET phash = $2::jsonb, fingerprinted = TRUE "
                    "WHERE id = $1 AND fingerprinted = FALSE",
                    uuid.UUID(media_id),
                    json.dumps({"frames": frames}),
                )
                log.info("fingerprint stored", extra={"media_id": media_id})
            except (media_mod.MediaError, OSError) as exc:
                log.info("fingerprint skipped",
                         extra={"media_id": media_id, "detail": str(exc)[:150]})
            except Exception:  # noqa: BLE001
                log.exception("fingerprint worker error", extra={"media_id": media_id})
            finally:
                self.queue.task_done()


class JobEngine:
    def __init__(self, db, cfg: Settings, bot, encre: EncoreClient) -> None:
        self.db = db
        self.cfg = cfg
        self.bot = bot
        self.encre = encre
        self.state = RuntimeState(archive_channel_id=cfg.archive_channel_id)
        self.fingerprinter = Fingerprinter(db, cfg)
        self._submitting: set[str] = set()
        self._bg_tasks: set[asyncio.Task] = set()
        self._last_edit: dict[str, float] = {}
        self._last_text: dict[str, str] = {}
        self._me: tuple | None = None
        self._upload_sem = asyncio.Semaphore(max(1, cfg.max_concurrent_uploads))
        self._lang_cache: dict[int, str] = {}
        self._tiers_cache: tuple[dict, float] | None = None
        self._copy_state: dict[str, dict] = {}

    async def _report_copy_progress(self, job_id: str) -> None:
        """Edit the requester status card with live byte-progress + MB/s while
        the staging copy runs (fallback path when hardlink is unavailable)."""
        try:
            rows = await self.db.fetch(
                "SELECT chat_id, status_message_id, tg_id FROM job_requesters WHERE job_id = $1",
                _as_uuid(job_id),
            )
            while True:
                st = self._copy_state.get(job_id)
                if not st or not st["total"]:
                    return
                done, total, t0 = st["done"], st["total"], st["t0"]
                pct = int(100 * done / total)
                speed = (done / 1048576.0) / max(0.25, time.time() - t0)
                for r in rows:
                    lang = await self._lang(r["tg_id"])
                    self._edit_status(
                        r["chat_id"], r["status_message_id"],
                        tr("copy_progress", lang, pct=pct, speed=f"{speed:.1f}"),
                    )
                if done >= total:
                    return
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 - progress display is best-effort
            log.exception("copy progress reporter failed", extra={"job_id": job_id})

    def spawn(self, coro) -> None:
        """create_task with a strong reference and unhandled exception logging."""
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        def _on_done(t: asyncio.Task) -> None:
            self._bg_tasks.discard(t)
            if not t.cancelled():
                exc = t.exception()
                if exc:
                    log.error("unhandled exception in spawned task", exc_info=exc)
        task.add_done_callback(_on_done)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    async def admin_ids(self) -> list[int]:
        rows = await self.db.fetch("SELECT tg_id FROM users WHERE is_admin")
        return sorted({r["tg_id"] for r in rows} | set(self.cfg.admin_ids))

    async def is_owner(self, tg_id: int) -> bool:
        owner = self.cfg.owner_telegram_id
        if owner:
            return tg_id == owner
        admins = await self.admin_ids()
        return bool(admins) and tg_id == admins[0]

    async def promote_admin(self, actor: str, tg_id: int) -> tuple[bool, str]:
        row = await self.db.fetchrow("SELECT tg_id FROM users WHERE tg_id = $1", tg_id)
        if row is None:
            return False, "user_not_found"
        if tg_id in await self.admin_ids():
            return False, "already_admin"
        await db_set_admin(self.db, tg_id, True)
        await audit_mod.log_action(self.db, actor, "admin", "admin.promote",
                                   tg_id, None, "engine")
        await self.refresh_admin_commands()
        return True, "ok"

    async def demote_admin(self, actor: str, tg_id: int) -> tuple[bool, str]:
        if self.cfg.owner_telegram_id and tg_id == self.cfg.owner_telegram_id:
            return False, "is_owner"
        admins = await self.admin_ids()
        if tg_id not in admins:
            return False, "not_admin"
        if len(admins) <= 1:
            return False, "last_admin"
        await db_set_admin(self.db, tg_id, False)
        await audit_mod.log_action(self.db, actor, "admin", "admin.demote",
                                   tg_id, None, "engine")
        await self.refresh_admin_commands()
        return True, "ok"

    async def refresh_admin_commands(self) -> None:
        """Default command list for everyone + an admin-scoped list (with
        /admin and /panel) for every admin's private chat."""
        try:
            base = [BotCommand(command="start", description="???????? / Start"),
                    BotCommand(command="settings", description="?????? ?????????????? / Settings")]
            await self.bot.set_my_commands(base)
            admin_cmds = base + [
                BotCommand(command="admin", description="???? ?????? ?????????? / Admin panel"),
                BotCommand(command="panel", description="???? ?????? ???? / Web panel"),
            ]
            for aid in await self.admin_ids():
                await self.bot.set_my_commands(
                    admin_cmds,
                    scope=BotCommandScopeChat(chat_id=aid, type="chat"))
        except Exception:  # noqa: BLE001 - cosmetic; never break the flow
            log.exception("set_my_commands (admin scope) failed")

    async def notify_admins(self, text: str) -> None:
        for admin in await self.admin_ids():
            try:
                await self.bot.send_message(admin, text)
            except TelegramAPIError:
                pass

    async def _lang(self, tg_id: int | None) -> str:
        if not tg_id:
            return "fa"
        cached = self._lang_cache.get(tg_id)
        if cached:
            return cached
        lang = await self.db.fetchval("SELECT language FROM users WHERE tg_id = $1", tg_id)
        lang = lang or "fa"
        if len(self._lang_cache) > 5000:
            self._lang_cache.clear()
        self._lang_cache[tg_id] = lang
        return lang

    def invalidate_lang(self, tg_id: int) -> None:
        self._lang_cache.pop(tg_id, None)

    async def get_me_cached(self, ttl: float = 60.0):
        """Cached bot identity for frequent pollers (SPEC-02).

        The panel summary is polled every few seconds per client and the
        healthz route per monitor - a live get_me on each call burns Local
        Bot API quota. Refreshes only when cold/expired, keeps the last
        good value on Telegram errors, and refreshes state.bot_username.
        """
        now = time.time()
        if self._me and now - self._me[1] < ttl:
            return self._me[0]
        try:
            me = await self.bot.get_me()
        except TelegramAPIError:
            if self._me is not None:
                return self._me[0]
            raise
        self._me = (me, now)
        self.state.bot_username = me.username or ""
        return me

    def _global_thumb(self):
        """Admin-set global thumbnail as an FSInputFile, or None."""
        path = self.state.global_thumb
        if path and Path(path).is_file():
            return FSInputFile(path)
        return None

    async def _escalate_level_to_265(self, row) -> None:
        """Requeue a no-gain x264 level job as the HEVC escalation pass."""
        params = _load_json(row["profile_params"]) or {}
        try:
            x265_crf = int(str(params.get("crf", "28"))) + 5
        except (TypeError, ValueError):
            x265_crf = 33
        escalated = await self.db.fetchval(
            "UPDATE jobs SET status='queued', stage='queued', encore_job_id=NULL, "
            "progress=0, effective_profile='level265', profile_params=$2::jsonb, "
            "updated_at=now() WHERE id=$1 AND status IN ('queued','processing') RETURNING id",
            row["id"], json.dumps({"crf": str(x265_crf), "preset": "superfast"}),
        )
        if not escalated:
            return
        await self.db.bump("level_escalations")
        log.info("level escalated to HEVC pass",
                 extra={"job_id": str(row["id"]), "detail": f"crf={x265_crf}"})
        for r in await self.db.fetch(
            "SELECT chat_id, status_message_id, tg_id FROM job_requesters WHERE job_id = $1",
            row["id"],
        ):
            self._edit_status(
                r["chat_id"], r["status_message_id"],
                tr("level_escalated", await self._lang(r["tg_id"])), force=True,
            )
        self.spawn(self.run_job(str(row["id"])))

    async def _delivery_thumbnail(self, job_id: str, video_path: Path,
                                  out_probe: dict):
        """Thumbnail for a fresh upload: admin global thumb if set, else a
        frame grabbed from ~30% of the output video."""
        global_thumb = self._global_thumb()
        if global_thumb is not None:
            return global_thumb
        try:
            tmp = Path(self.cfg.media_tmp) / f"thumb-{job_id[:12]}.jpg"
            at = (out_probe.get("duration_s") or 0) * 0.3
            ok = await asyncio.to_thread(
                media_mod.extract_thumbnail, str(video_path), str(tmp), at
            )
            if ok:
                return FSInputFile(str(tmp))
        except Exception:  # noqa: BLE001 - thumbnail is best-effort
            pass
        return None

    async def resolve_local_path(self, file_path: str | None) -> Path | None:
        if not file_path:
            return None
        p = Path(file_path)
        if not p.is_absolute():
            p = Path(self.cfg.botapi_dir) / p
        try:
            return p if p.is_file() else None
        except OSError:
            # Never log the raw path: the local Bot API dir name contains the
            # bot token. A sanitized hint is enough for operators.
            log.warning("local bot api file not readable", extra={"detail": "permission denied"})
            return None

    def _disk_free(self) -> int:
        try:
            return shutil.disk_usage(self.cfg.media_root).free
        except OSError:
            return 0

    def _edit_status(self, chat_id: int | None, message_id: int | None, text: str,
                     markup: InlineKeyboardMarkup | None = None,
                     force: bool = False) -> None:
        if not chat_id or not message_id:
            return
        key = f"{chat_id}:{message_id}"
        # Text-diff guard (UX-03): identical text would raise
        # MessageNotModified and burn an API call - skip it early. This also
        # collapses duplicate "queued" edits from overlapping poll/callback
        # paths.
        if len(self._last_text) > 5000:
            self._last_text.clear()
        if not force and self._last_text.get(key) == text:
            return
        now = time.time()
        if len(self._last_edit) > 5000:
            self._last_edit.clear()
        if not force and now - self._last_edit.get(key, 0) < self.cfg.progress_edit_seconds:
            return
        self._last_edit[key] = now
        self._last_text[key] = text
        self.spawn(self.edit_status_sync(chat_id, message_id, text, markup))

    async def edit_status_sync(self, chat_id: int, message_id: int | None, text: str,
                               markup: InlineKeyboardMarkup | None = None) -> None:
        if not chat_id or not message_id:
            return
        try:
            await self.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text,
                reply_markup=markup,
            )
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
            try:
                await self.bot.edit_message_text(
                    chat_id=chat_id, message_id=message_id, text=text,
                    reply_markup=markup,
                )
            except TelegramAPIError:
                pass
        except TelegramAPIError:
            pass

    _STAGES = [("recv", "????"), ("queued", "????"), ("copy", "????"), ("encode", "??????"),
               ("validate", "????"), ("archive", "????"), ("deliver", "????")]

    def _stage_index(self, row) -> int:
        """0-based index of the current pipeline stage (7 = all done)."""
        stage = row["stage"] or row["status"]
        if row["status"] == "completed" or stage in ("completed", "delivering"):
            return 7
        return {"queued": 1, "deferred": 1, "copying": 2, "encoding": 3,
                "completing": 4, "validating": 4, "archiving": 5,
                "delivering": 6}.get(stage, 3)

    def _tracker_line(self, row) -> str:
        cur = self._stage_index(row)
        parts = []
        for i, (_key, icon) in enumerate(self._STAGES):
            mark = "???" if i < cur else ("???" if i == cur else "???")
            parts.append(icon + mark)
        return "???".join(parts)

    def _progress_text(self, row, lang: str, info: dict | None = None) -> str:
        info = info or {}
        tracker = self._tracker_line(row)
        lines = [tracker]
        if info.get("queue_pos"):
            lines.append(tr("queue_position", lang, n=info["queue_pos"]))
        if info.get("copy_pct") is not None:
            lines.append(tr("copy_progress", lang, pct=int(info["copy_pct"]),
                            speed=info.get("copy_speed") or 0))
        stage_key = {
            "queued": "stage_queued",
            "copying": "stage_copying",
            "encoding": "stage_encoding",
            "validating": "stage_validating_out",
            "archiving": "stage_archiving",
            "delivering": "stage_delivering",
        }.get(row["stage"] or row["status"], "stage_encoding")
        if info:
            try:
                progress = int(float(info.get("progress") or 0))
            except (TypeError, ValueError):
                progress = 0
        else:
            progress = int(row["progress"] or 0)
        started = _ensure_tz(row["started_at"]) or _ensure_tz(row["enqueued_at"])
        elapsed = _fmt_clock((_utcnow() - started).total_seconds()) if started else "-"
        eta = ""
        if info:
            speed = info.get("speed")
            keys = row.keys()
            src_dur = (row["source_duration"] if "source_duration" in keys
                       else (row["duration_s"] if "duration_s" in keys else None))
            if speed and speed > 0 and src_dur and progress > 0:
                remaining = (float(src_dur) * (100 - progress) / 100) / float(speed)
                eta = " " + tr("eta_prefix", lang, eta=_fmt_clock(remaining))
        speed_txt = ""
        if info and info.get("speed"):
            speed_txt = " " + tr("status_speed", lang, speed=f"{info['speed']:.1f}")
        filled = round(progress / 5)
        bar = "???" * filled + "???" * (20 - filled)
        header = tr("status_header", lang, job=str(row["id"])[:8], profile=row["profile"])
        line = tr("status_line", lang, stage=tr(stage_key, lang), progress=progress,
                  elapsed=elapsed, eta=eta + speed_txt)
        lines.append(header)
        lines.append(line)
        lines.append(f"[{bar}] {int(progress)}%")
        return "\n".join(lines)

    async def _user_pref(self, tg_id: int) -> dict:
        row = await self.db.fetchrow(
            "SELECT language, delivery_style, notify_done, show_meta, thumbnail_file_id "
            "FROM users WHERE tg_id = $1",
            tg_id,
        )
        return dict(row) if row else {
            "language": "fa", "delivery_style": "video", "notify_done": True,
            "show_meta": True, "thumbnail_file_id": None,
        }

    async def _set_stage(self, job_id, stage: str) -> None:
        await self.db.execute(
            "UPDATE jobs SET stage = $2, updated_at = now() WHERE id = $1",
            _as_uuid(job_id), stage,
        )

    async def _touch_completion_lease(self, job_id) -> bool:
        """Renew the completion lease (F3) around every long await.

        The completion claim expires once updated_at goes stale (10 min) so a
        crashed holder gets recovered; a live holder must therefore renew
        updated_at while it works, or a second runner re-claims and deletes
        the part files under the first one's feet. Fencing: the renewal only
        lands while the job is still inside the completion pipeline
        (stage completing/validating/archiving) and still active; once the
        job left those stages (completed/failed/cancelled by someone else)
        the heartbeat reports the lost lease.
        """
        renewed = await self.db.fetchval(
            "UPDATE jobs SET updated_at = now() "
            "WHERE id = $1 AND stage IN ('completing','validating','archiving') "
            "AND status IN ('queued','processing') RETURNING id",
            _as_uuid(job_id),
        )
        return renewed is not None

    async def _frames_for(self, media_id) -> list[int]:
        raw = await self.db.fetchval("SELECT phash FROM media_assets WHERE id = $1", media_id)
        if not raw:
            return []
        try:
            return [int(x) for x in json.loads(raw).get("frames", [])]
        except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
            return []

    # ------------------------------------------------------------------
    # tiers & limits
    # ------------------------------------------------------------------
    _LIMIT_KEYS = ("max_source_gb", "max_duration_min", "daily_quota_gb",
                   "max_active", "max_per_hour")

    async def tiers_config(self) -> dict:
        """Persisted tier limits (app_config 'limits'), seeded from env.

        Cached for 60s - admission hits this on every submission; the admin
        panel calls invalidate_tiers() after saving.
        """
        now = time.time()
        if self._tiers_cache and self._tiers_cache[1] > now:
            return self._tiers_cache[0]
        stored = await self.db.get_config("limits")
        if isinstance(stored, dict) and "normal" in stored and "vip" in stored:
            result = stored
        else:
            result = self.cfg.tier_defaults()
            await self.db.set_config("limits", result)
        self._tiers_cache = (result, now + 60)
        return result

    def invalidate_tiers(self) -> None:
        self._tiers_cache = None

    async def effective_limits(self, tg_id: int) -> dict:
        """Effective limits for a user: per-user override > tier > env default."""
        tiers = await self.tiers_config()
        user = await self.db.fetchrow(
            "SELECT is_vip, max_source_gb, max_duration_min, daily_quota_gb "
            "FROM users WHERE tg_id = $1",
            tg_id,
        )
        is_vip = bool(user and user["is_vip"])
        tier = tiers["vip"] if is_vip else tiers["normal"]
        gb = 1024**3

        def _num(override, key):
            try:
                value = int(override) if override is not None else None
            except (TypeError, ValueError):
                value = None
            return value if value and value > 0 else tier.get(key)

        max_source_gb = _num(user["max_source_gb"] if user else None, "max_source_gb")
        max_duration_min = _num(user["max_duration_min"] if user else None, "max_duration_min")
        daily_quota_gb = _num(user["daily_quota_gb"] if user else None, "daily_quota_gb")
        return {
            "tier": "vip" if is_vip else "normal",
            "max_source_bytes": int(max_source_gb or 4) * gb,
            "max_duration_s": int(max_duration_min or 0) * 60,
            "daily_quota_bytes": int(daily_quota_gb or 0) * gb,
            "max_active": max(1, int(tier.get("max_active") or 1)),
            "max_per_hour": max(1, int(tier.get("max_per_hour") or 1)),
            "priority": 60 if is_vip else 50,
        }

    # ------------------------------------------------------------------
    # admission
    # ------------------------------------------------------------------
    async def check_admission(self, tg_id: int, size_bytes: int,
                              allow_no_archive: bool = False,
                              is_admin: bool = False) -> None:
        if not allow_no_archive and not self.state.archive_channel_id:
            raise AdmissionError("archive_not_configured")
        if self.state.paused:
            raise AdmissionError("paused")
        user = await self.db.fetchrow("SELECT is_blocked FROM users WHERE tg_id = $1", tg_id)
        if user and user["is_blocked"]:
            raise AdmissionError("blocked_user")
        limits = await self.effective_limits(tg_id)
        # Admins bypass every per-user fairness limit (size, duration,
        # concurrency, rate, quota, queue cap). Physical disk safety and the
        # pause switch still apply to them - they protect the server itself.
        if not is_admin:
            if size_bytes > limits["max_source_bytes"]:
                raise AdmissionError("too_large_tier",
                                     max_gb=limits["max_source_bytes"] // 1024**3)
            # Per-user fairness first: deferred jobs also occupy a slot, otherwise
            # disk pressure would let a user stack unbounded deferred jobs.
            active = await self.db.fetchval(
                "SELECT count(*) FROM jobs WHERE requester_tg_id = $1 "
                "AND status IN ('queued','processing','deferred')",
                tg_id,
            )
            if active >= limits["max_active"]:
                raise AdmissionError("user_busy", max_active=limits["max_active"])
            hourly = await self.db.fetchval(
                "SELECT count(*) FROM jobs WHERE requester_tg_id = $1 "
                "AND enqueued_at > now() - interval '1 hour'",
                tg_id,
            )
            if hourly >= limits["max_per_hour"]:
                raise AdmissionError("rate_limited")
            daily = await self.db.fetchval(
                "SELECT count(*) FROM jobs WHERE requester_tg_id = $1 "
                "AND enqueued_at > now() - interval '24 hours'",
                tg_id,
            )
            if daily >= self.cfg.max_jobs_per_day:
                raise AdmissionError("daily_quota", quota=self.cfg.max_jobs_per_day)
            # Daily byte quota: total source volume of the last 24h.
            if limits["daily_quota_bytes"]:
                used_bytes = await self.db.fetchval(
                    "SELECT coalesce(sum(source_size), 0) FROM jobs "
                    "WHERE requester_tg_id = $1 "
                    "AND enqueued_at > now() - interval '24 hours' "
                    "AND status IN ('queued','processing','deferred','completed')",
                    tg_id,
                )
                if int(used_bytes or 0) + size_bytes > limits["daily_quota_bytes"]:
                    raise AdmissionError("daily_quota_bytes",
                                         quota=media_mod.human_size(limits["daily_quota_bytes"]),
                                         used=media_mod.human_size(int(used_bytes or 0)))
            queued = await self.db.fetchval("SELECT count(*) FROM jobs WHERE status = 'queued'")
            if queued >= self.cfg.max_queued:
                raise AdmissionError("queue_full")
        # Disk admission last: accounts for bytes already reserved by active
        # jobs (ArgonsEncoder-style reservation accounting, PostgreSQL-backed).
        need = int(size_bytes * self.cfg.admission_need_factor) \
            + self.cfg.admission_floor_bytes
        reserved = await self.db.fetchval(
            "SELECT coalesce(sum(reserved_bytes), 0) FROM jobs "
            "WHERE status IN ('queued', 'processing')"
        )
        free = max(0, self._disk_free() - int(reserved or 0))
        if free < need and self.cfg.disk_defer and not self.state.paused:
            raise AdmissionDeferred(need)
        if free < need:
            raise AdmissionError("disk")
        if free < self.cfg.disk_pause_free_bytes:
            await self._auto_pause()
            raise AdmissionError("disk")

    async def check_duration_limit(self, tg_id: int, duration_s: float | None,
                                   is_admin: bool = False) -> None:
        """Reject sources longer than the user's tier allows (post-probe)."""
        if is_admin or not duration_s:
            return
        limits = await self.effective_limits(tg_id)
        max_s = limits["max_duration_s"]
        if max_s and duration_s > max_s:
            hours = max_s / 3600
            max_h = f"{hours:.0f}h" if hours >= 1 else f"{max_s / 60:.0f}m"
            raise AdmissionError("too_long", max_h=max_h)

    async def _recheck_user_admission(self, conn, tg_id: int,
                                      size_bytes: int) -> None:
        """In-transaction admission recheck under the per-user advisory lock.

        check_admission is UX-only: it runs outside any lock, so two
        concurrent submissions can both pass it and overshoot the user's
        caps (F9 TOCTOU). This mirrors its per-user fairness checks against
        the same transaction that inserts the job row, raising the same
        AdmissionError codes the handlers already localize.
        """
        limits = await self.effective_limits(tg_id)
        active = await conn.fetchval(
            "SELECT count(*) FROM jobs WHERE requester_tg_id = $1 "
            "AND status IN ('queued','processing','deferred')",
            tg_id,
        )
        if int(active or 0) >= limits["max_active"]:
            raise AdmissionError("user_busy", max_active=limits["max_active"])
        hourly = await conn.fetchval(
            "SELECT count(*) FROM jobs WHERE requester_tg_id = $1 "
            "AND enqueued_at > now() - interval '1 hour'",
            tg_id,
        )
        if int(hourly or 0) >= limits["max_per_hour"]:
            raise AdmissionError("rate_limited")
        daily = await conn.fetchval(
            "SELECT count(*) FROM jobs WHERE requester_tg_id = $1 "
            "AND enqueued_at > now() - interval '24 hours'",
            tg_id,
        )
        if int(daily or 0) >= self.cfg.max_jobs_per_day:
            raise AdmissionError("daily_quota", quota=self.cfg.max_jobs_per_day)
        if limits["daily_quota_bytes"]:
            used_bytes = await conn.fetchval(
                "SELECT coalesce(sum(source_size), 0) FROM jobs "
                "WHERE requester_tg_id = $1 "
                "AND enqueued_at > now() - interval '24 hours' "
                "AND status IN ('queued','processing','deferred','completed')",
                tg_id,
            )
            if int(used_bytes or 0) + size_bytes > limits["daily_quota_bytes"]:
                raise AdmissionError("daily_quota_bytes",
                                     quota=media_mod.human_size(limits["daily_quota_bytes"]),
                                     used=media_mod.human_size(int(used_bytes or 0)))

    async def _auto_pause(self) -> None:
        if not self.state.paused:
            self.state.paused = True
            await self.db.set_config("paused", True)
            log.warning("auto-paused: disk below critical threshold")
            await self.notify_admins(
                f"?????? Disk below critical threshold; intake paused. "
                f"Free: {media_mod.human_size(self._disk_free())}"
            )

    async def auto_resume_if_ok(self) -> None:
        if self.state.paused and self._disk_free() > self.cfg.disk_min_free_bytes:
            self.state.paused = False
            await self.db.set_config("paused", False)
            log.info("auto-resumed: disk recovered")
            await self.notify_admins("?????? Disk recovered; service resumed.")

    # ------------------------------------------------------------------
    # submission
    # ------------------------------------------------------------------
    async def register_media(
        self, *, src_path: Path, size_bytes: int, filename: str,
        tg_file_id: str | None, tg_file_unique_id: str | None,
    ) -> tuple[uuid.UUID, str, dict, str]:
        """Probe and hash the source IN PLACE (no copy).

        The Local Bot API keeps downloaded files on its persistent volume, so
        the bot-api path is used directly as the job input. If the file is
        ever evicted before encoding, _refetch_source re-fetches it and makes
        a stable copy. Measured: in-place hash ~13s for 4GB vs ~33s for
        hash+copy, and no duplicate 4GB on disk.
        Returns (media_id, sha256, probe, stable_path).
        """
        probe = await media_mod.probe_video(src_path)
        if size_bytes <= 0:
            size_bytes = int(probe.get("size_bytes") or src_path.stat().st_size)
        # Hash BEFORE inserting: a failed hash must not leave a sha-less
        # media_assets row behind (POT-05).
        try:
            sha = await media_mod.sha256_file(src_path)
        except OSError as exc:
            # Bot-api file evicted mid-registration -> clean rejection.
            raise media_mod.MediaError(f"source unreadable: {media_mod.redact(str(exc))}") from exc
        # Fingerprint runs in the background worker ONLY: similarity dedup
        # compares against archived results, which are always minutes away -
        # keeping it on the submission critical path is pure latency.
        # Submission itself happens once, from run_job (SPEC-03): an eager
        # submit here raced the worker into hashing the same 4GB source twice.
        filename_clean = media_mod.sanitize_filename(filename)
        media_id = await self.db.fetchval(
            """
            INSERT INTO media_assets(
                sha256, size_bytes, filename, duration_s, width, height, fps,
                vcodec, acodec, audio_channels, container, bitrate,
                tg_file_id, tg_file_unique_id, probe, name_norm)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb,$16)
            RETURNING id
            """,
            sha, size_bytes, filename_clean,
            probe.get("duration_s"), probe.get("width"), probe.get("height"),
            probe.get("fps"), probe.get("vcodec"), probe.get("acodec"),
            probe.get("audio_channels"), probe.get("container"), probe.get("bitrate"),
            tg_file_id, tg_file_unique_id, json.dumps(probe),
            filename_clean.lower(),
        )
        return media_id, sha, probe, str(src_path)

    def _custom_params(self, target_mb, duration_s, size_bytes) -> tuple[dict | None, bool, str | None]:
        """Bitrate params for the custom/percent profile.

        Returns (params, low_bitrate, err); err "bad_target" -> params None.
        "low_bitrate" best-efforts at the quality floor (kbps clamped inside
        compute_target_params).
        """
        kbps, err = compute_target_params(
            int(target_mb or 0), duration_s, size_bytes,
            min_video_kbps=self.cfg.min_video_kbps,
        )
        if err == "bad_target":
            return None, False, err
        mr = int(kbps * 1.35)
        return ({"bv": f"{kbps}k", "mr": f"{mr}k", "bs": f"{mr * 2}k"},
                err == "low_bitrate", None)

    async def handle_submission(
        self, *, tg_id: int, chat_id: int | None, source_msg_id: int | None,
        status_msg_id: int | None, size_bytes: int, filename: str | None,
        profile_key: str, file_id: str | None = None, file_unique_id: str | None = None,
        local_path: str | None = None, allow_no_archive: bool = False,
        target_mb: int | None = None, compress_level: int | None = None,
    ) -> dict:
        prof = BY_KEY.get(profile_key)
        if not prof:
            raise AdmissionError("bad_profile")
        is_admin = tg_id in await self.admin_ids()
        profile_params: dict | None = None
        low_bitrate = False
        if profile_key == "custom":
            if not target_mb:
                raise AdmissionError("bad_target", detail="target size required")
            # bitrate computed after probing, below
        if profile_key == "level":
            if not compress_level:
                raise AdmissionError("bad_profile")
            profile_params = {
                "crf": str(crf_for_level(compress_level)),
                "preset": preset_for_level(compress_level),
            }
        deferred_need = None
        try:
            await self.check_admission(tg_id, size_bytes,
                                       allow_no_archive=allow_no_archive,
                                       is_admin=is_admin)
        except AdmissionDeferred as exc:
            deferred_need = exc.need

        if local_path:
            src_path = Path(local_path)
            if not src_path.is_file():
                raise AdmissionError("source_missing")
        else:
            try:
                tg_file = await self.bot.get_file(file_id)
            except TelegramAPIError as exc:
                log.warning("get_file failed", extra={"detail": str(exc)[:200]})
                raise AdmissionError("download_failed") from exc
            src_path = await self.resolve_local_path(tg_file.file_path)
            if src_path is None:
                raise AdmissionError("download_failed")

        try:
            media_id, sha, probe, stable_path = await self.register_media(
                src_path=src_path,
                size_bytes=size_bytes,
                filename=filename or src_path.name,
                tg_file_id=file_id,
                tg_file_unique_id=file_unique_id,
            )
        except media_mod.MediaError as exc:
            raise AdmissionError("invalid_media", detail=str(exc)[:120]) from exc

        await self.check_duration_limit(tg_id, probe.get("duration_s"), is_admin=is_admin)

        if profile_key == "custom":
            profile_params, low_bitrate, err = self._custom_params(
                target_mb, probe.get("duration_s"), size_bytes)
            if err:
                raise AdmissionError("bad_target", detail=str(target_mb))
        if profile_key == "remux" and not media_mod.remux_compatible(probe):
            raise AdmissionError("invalid_media", detail="remux not applicable (codec/container)")

        await self.db.bump("requests_total")
        await self.db.bump("bytes_in", size_bytes)
        if chat_id is not None:
            await self.db.execute(
                "UPDATE users SET last_seen_at = now(), total_requests = total_requests + 1 "
                "WHERE tg_id = $1",
                tg_id,
            )

        version = prof.version
        lock_key = f"{sha}:{profile_key}:v{version}"
        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                # Per-user admission lock first (F9), then the dedup key:
                # serialize a user's concurrent submissions so the in-tx
                # recheck below cannot be raced (Argons per-user pattern).
                if not is_admin:
                    await conn.execute(
                        "SELECT pg_advisory_xact_lock(hashtext($1)::bigint)",
                        f"admit:{tg_id}",
                    )
                    await self._recheck_user_admission(conn, tg_id, size_bytes)
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1)::bigint)", lock_key
                )
                reusable_parts = await dedup.find_reusable_parts(self.db, sha, profile_key, version)
                reusable = reusable_parts[0] if reusable_parts else None
                reuse_kind = "exact"
                similarity = False
                name_norm = media_mod.sanitize_filename(filename or src_path.name).lower()
                if reusable is None and profile_key in ("custom", "level"):
                    # Fuzzy layer: size + normalized name + duration window.
                    fuzzy = await dedup.find_fuzzy_archive(
                        self.db, size_bytes=size_bytes, name_norm=name_norm,
                        duration_s=probe.get("duration_s") or 0.0,
                        profile=profile_key,
                    )
                    if fuzzy is not None:
                        reusable_parts = await dedup.find_reusable_parts(
                            self.db, fuzzy["source_sha256"], profile_key, version
                        )
                        reusable = reusable_parts[0] if reusable_parts else None
                        reuse_kind = "fuzzy"
                if reusable is None and self.cfg.similarity_reuse:
                    frames = await self._frames_for(media_id)
                    if frames:
                        similar_src = await dedup.find_similar_archive(
                            self.db, self.cfg, sha,
                            probe.get("duration_s") or 0.0, frames,
                            profile_key, version,
                            acodec=probe.get("acodec"),
                            audio_channels=probe.get("audio_channels"),
                        )
                        if similar_src is not None:
                            reusable_parts = await dedup.find_reusable_parts(
                                self.db, similar_src["sha256"], profile_key, version
                            )
                            reusable = reusable_parts[0] if reusable_parts else None
                            similarity = reusable is not None
                if reusable is not None:
                    if (profile_key == "level" and reusable["status"] == "no_gain"
                            and profile_params):
                        # A previous CRF attempt already lost to this source -
                        # skip the doomed x264 pass, go straight to HEVC.
                        try:
                            x265_crf = int(str(profile_params.get("crf", "28"))) + 5
                        except (TypeError, ValueError):
                            x265_crf = 33
                        escal_job = await conn.fetchval(
                            """
                            INSERT INTO jobs(requester_tg_id, media_id, profile, profile_version,
                                             effective_profile, status, priority, source_size,
                                             source_path, source_message_id, status_message_id,
                                             progress_changed_at, stage, profile_params, reserved_bytes)
                            VALUES ($1,$2,$3,$4,'level265','queued',$5,$6,$7,$8,$9, now(),
                                    'queued', $10::jsonb, $11)
                            RETURNING id
                            """,
                            tg_id, media_id, profile_key, version,
                            (await self.effective_limits(tg_id))["priority"],
                            size_bytes, stable_path, source_msg_id, status_msg_id,
                            json.dumps({"crf": str(x265_crf), "preset": "superfast"}),
                            int(size_bytes * self.cfg.admission_need_factor)
                            + self.cfg.admission_floor_bytes,
                        )
                        await conn.execute(
                            """
                            INSERT INTO job_requesters
                                (job_id, tg_id, chat_id, source_message_id, status_message_id)
                            VALUES ($1, $2, $3, $4, $5)
                            ON CONFLICT (job_id, tg_id) DO NOTHING
                            """,
                            escal_job, tg_id, chat_id or 0, source_msg_id, status_msg_id,
                        )
                        await self.db.bump("level_escalations")
                        # no spawn: the poller submits it right after commit
                        return {"outcome": "queued", "job_id": str(escal_job),
                                "low_bitrate": False, "bitrate": probe.get("bitrate"),
                                "estimate": ""}
                    return await self._reuse_archive(
                        reusable_parts, tg_id=tg_id, chat_id=chat_id, status_msg_id=status_msg_id,
                        profile_key=profile_key, sha=sha, size_bytes=size_bytes,
                        reuse_kind="fuzzy" if reuse_kind == "fuzzy" else
                        ("similar" if similarity else "exact"),
                    )
                inflight = await dedup.find_inflight_job(self.db, sha, profile_key, version)
                if inflight is None and profile_key in ("custom", "level"):
                    inflight = await dedup.find_fuzzy_inflight_job(
                        self.db, size_bytes=size_bytes, name_norm=name_norm,
                        duration_s=probe.get("duration_s") or 0.0,
                        profile=profile_key,
                    )
                if inflight is not None:
                    await conn.execute(
                        """
                        INSERT INTO job_requesters
                            (job_id, tg_id, chat_id, source_message_id, status_message_id)
                        VALUES ($1,$2,$3,$4,$5)
                        ON CONFLICT (job_id, tg_id) DO NOTHING
                        """,
                        inflight["id"], tg_id, chat_id or 0, source_msg_id, status_msg_id,
                    )
                    await self.db.bump("dedup_inflight_joined")
                    return {"outcome": "joined", "job_id": str(inflight["id"])}

                # Adaptive Decision Engine: Smart fastpath, dynamic preset & rate control
                dec = decision_engine.make_decision(
                    probe=probe,
                    profile_key=profile_key,
                    size_bytes=size_bytes,
                    target_mb=target_mb,
                    compress_level=compress_level,
                    settings=self.cfg,
                    active_jobs=1,
                )
                if dec.action == "remux_only":
                    effective_profile = "remux"
                    profile_params = None
                elif profile_key in ("r1080", "r720", "r480"):
                    effective_profile = resolve_variant(profile_key, probe.get("width"), probe.get("height"))
                elif profile_key == "custom" and dec.two_pass:
                    effective_profile = "custom_2pass"
                    if dec.profile_params:
                        profile_params = dec.profile_params
                else:
                    effective_profile = dec.effective_profile
                    if dec.profile_params:
                        profile_params = dec.profile_params

                job_id = await conn.fetchval(
                    """
                    INSERT INTO jobs(requester_tg_id, media_id, profile, profile_version,
                                     effective_profile, status, priority, source_size,
                                     source_path, source_message_id, status_message_id,
                                     progress_changed_at, stage, profile_params, reserved_bytes)
                    VALUES ($1,$2,$3,$4,$5,$6,$14,$7,$8,$9,$10, now(),
                            $11, $12::jsonb, $13)
                    RETURNING id
                    """,
                    tg_id, media_id, profile_key, version,
                    effective_profile,
                    "deferred" if deferred_need else "queued",
                    size_bytes, stable_path, source_msg_id, status_msg_id,
                    "deferred" if deferred_need else "queued",
                    json.dumps(profile_params) if profile_params else None,
                    deferred_need or int(size_bytes * self.cfg.admission_need_factor)
                    + self.cfg.admission_floor_bytes,
                    70 if is_admin else (await self.effective_limits(tg_id))["priority"],
                )
                await conn.execute(
                    """
                    INSERT INTO job_requesters
                        (job_id, tg_id, chat_id, source_message_id, status_message_id)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (job_id, tg_id) DO NOTHING
                    """,
                    job_id, tg_id, chat_id or 0, source_msg_id, status_msg_id,
                )
        job_id = _as_uuid(job_id)
        if deferred_need:
            log.info("job deferred for disk capacity",
                     extra={"job_id": str(job_id), "detail": f"need={deferred_need}"})
            return {"outcome": "deferred", "job_id": str(job_id),
                    "bitrate": probe.get("bitrate"),
                    "estimate": self._estimate_text(profile_key, probe, deferred_need)}
        self.spawn(self.run_job(str(job_id)))
        return {"outcome": "queued", "job_id": str(job_id),
                "kbps": (profile_params or {}).get("bv"),
                "low_bitrate": low_bitrate,
                "bitrate": probe.get("bitrate"),
                "estimate": self._estimate_text(profile_key, probe, None, profile_params)}

    def _estimate_text(self, profile_key: str, probe: dict,
                       deferred_need: int | None = None,
                       profile_params: dict | None = None) -> str:
        """Early size/time estimate line (bpp model), or "" when unknown."""
        from . import estimate as est
        from .profiles import ESTIMATE_PARAMS

        if profile_key == "remux":
            return ""
        if profile_key == "custom" and profile_params:
            try:
                kbps = int(str(profile_params.get("bv", "0")).rstrip("k"))
                dur = probe.get("duration_s") or 0
                low = int(kbps * 1000 * dur / 8 * 0.85)
                high = int(kbps * 1000 * dur / 8 * 1.15)
                return est.format_size_range(low, max(high, low))
            except (TypeError, ValueError):
                return ""
        params = ESTIMATE_PARAMS.get(profile_key) or ESTIMATE_PARAMS["balanced"]
        codec, crf, preset, target_short = params
        if profile_key in ("level", "level265") and profile_params:
            try:
                crf = int(str(profile_params["crf"]))
            except (TypeError, ValueError, KeyError):
                pass
            else:
                preset = str(profile_params.get("preset") or preset)
        out_pixels = est.output_pixels(probe.get("width"), probe.get("height"), target_short)
        src_bytes = int(probe.get("size_bytes") or 0)
        audio = 96.0 if (target_short or 0) <= 480 else 128.0
        low, high = est.estimate_output_bytes(
            probe.get("duration_s"), out_pixels, codec, crf,
            audio_kbps=audio, source_bytes=src_bytes,
        )
        slo, shi = est.estimate_encode_seconds(
            probe.get("duration_s"), out_pixels, codec, preset,
        )
        parts = []
        if high > 0:
            parts.append(est.format_size_range(low, high))
        if shi > 0:
            parts.append(est.format_time_range(slo, shi))
        return " | ".join(parts)

    # ------------------------------------------------------------------
    # reuse path
    # ------------------------------------------------------------------
    async def _reuse_archive(self, reusable_parts, *, tg_id, chat_id, status_msg_id,
                             profile_key, sha, size_bytes, reuse_kind: str = "exact") -> dict:
        reusable = reusable_parts[0]
        archive_id = reusable["id"]
        source_size = reusable["source_size"] or size_bytes
        output_size = sum((r["output_size"] or 0) for r in reusable_parts)
        lang = await self._lang(tg_id)
        pref = await self._user_pref(tg_id)

        ok, method, delivered_msg = False, "none", None
        if chat_id is not None:
            try:
                if len(reusable_parts) > 1:
                    ids = [r["id"] for r in reusable_parts]
                    all_ok, delivered = await self._deliver_parts(
                        chat_id, ids, lang, len(reusable_parts)
                    )
                    ok, method, delivered_msg = all_ok, "parts", delivered
                else:
                    ok, method, delivered_msg = await self._deliver_archive_to(
                        chat_id, reusable, pref,
                        caption=tr("status_reused", lang),
                    )
            except TelegramAPIError as exc:
                log.warning("reuse delivery error", extra={"detail": str(exc)[:200]})

        if reusable["message_id"] and ok and method in ("file_id", "upload"):
            await self.db.execute(
                "UPDATE archive_records SET status = 'missing' "
                "WHERE id = $1 AND status = 'active'",
                archive_id,
            )
            await self.db.bump("archive_missing_detected")
            log.warning("archive message missing on reuse", extra={"detail": str(archive_id)})

        job_id = await self.db.fetchval(
            """
            INSERT INTO jobs(requester_tg_id, media_id, profile, profile_version,
                             effective_profile, status, source_size, output_size,
                             output_media_id, reuse_of, archived, is_no_gain,
                             status_message_id, stage,
                             enqueued_at, completed_at, progress)
            VALUES ($1, (SELECT source_media_id FROM archive_records WHERE id = $2),
                    $3, 1, $3, 'completed', $4, $5,
                    (SELECT output_media_id FROM archive_records WHERE id = $2),
                    $2, TRUE, FALSE, $6, 'completed', now(), now(), 100)
            RETURNING id
            """,
            tg_id, archive_id, profile_key, source_size, output_size, status_msg_id,
        )
        if chat_id is not None and pref.get("notify_done", True):
            await self.db.execute(
                """
                INSERT INTO deliveries(archive_id, job_id, tg_id, chat_id, message_id,
                                       method, status, error)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                """,
                archive_id, job_id, tg_id, chat_id, delivered_msg, method,
                "ok" if ok else "failed", None if ok else "all delivery methods failed",
            )
            await self.db.bump("deliveries_ok" if ok else "deliveries_failed")
            if ok:
                await self.edit_status_sync(chat_id, status_msg_id,
                                            tr("status_done", lang))
            else:
                try:
                    await self.bot.edit_message_text(
                        chat_id=chat_id, message_id=status_msg_id,
                        text=tr("status_delivery_failed", lang),
                        reply_markup=redeliver_markup(str(job_id)),
                    )
                except TelegramAPIError:
                    pass
        await self.db.bump({
            "exact": "dedup_exact_reuse",
            "fuzzy": "dedup_fuzzy_reuse",
            "similar": "dedup_similarity_reuse",
        }.get(reuse_kind, "dedup_exact_reuse"))
        if output_size and source_size > output_size:
            await self.db.bump("bytes_saved", source_size - output_size)
        log.info(
            "archive reused",
            extra={"job_id": str(job_id), "profile": profile_key,
                   "detail": f"method={method} reuse_kind={reuse_kind}"},
        )
        return {"outcome": "reused", "job_id": str(job_id), "delivered": ok}

    # ------------------------------------------------------------------
    # encode path
    # ------------------------------------------------------------------
    async def _stage_source(self, job_id: str, source: Path,
                            filename: str | None) -> str:
        """Expose the bot-api source under a token-free /media path.

        The bot-api volume and the /media bind are different devices, so a
        hardlink raises EXDEV and we fall back to a chunked copy with live
        progress on the user's status card. Returns the staged path.
        """
        used_path = str(source)
        if not used_path.startswith(self.cfg.botapi_dir):
            return used_path
        ext = Path(filename or "source.mp4").suffix.lower()
        if ext not in COPY_EXTS:
            ext = ".bin"
        staged = Path(self.cfg.media_incoming) / job_id / f"source{ext}"
        # Trust an existing staged file only when it matches the source size:
        # a crashed copy used to leave a truncated file that was silently
        # encoded later (F4).
        total = source.stat().st_size
        if staged.exists() and staged.stat().st_size == total:
            return str(staged)
        staged.parent.mkdir(parents=True, exist_ok=True)
        try:
            await asyncio.to_thread(os.link, source, staged)
        except OSError:
            # Cross-device fallback: copy to a .part sibling, verify the size,
            # then atomically swap it in. A crash mid-copy leaves at worst a
            # discarded .part, never a truncated "source" (Argons tmp+replace
            # pattern).
            part = staged.with_name(staged.name + ".part")
            self._copy_state[job_id] = {"done": 0, "total": total, "t0": time.time()}
            reporter = asyncio.create_task(self._report_copy_progress(job_id))
            try:
                await media_mod.copy_with_progress(
                    source, part,
                    lambda done: self._copy_state[job_id].update(done=done),
                )
                if not part.is_file() or part.stat().st_size != total:
                    raise media_mod.MediaError("staging failed: truncated copy")
                os.replace(part, staged)
            finally:
                self._copy_state.pop(job_id, None)
                reporter.cancel()
                if part.exists():
                    try:
                        part.unlink()
                    except OSError:
                        pass
        if not os.path.isfile(staged):
            raise media_mod.MediaError("staging failed: staged file missing")
        log.info("staging done", extra={
            "job_id": job_id,
            "detail": f"path={staged} size={os.path.getsize(staged)}"})
        return str(staged)

    async def run_job(self, job_id: str) -> None:
        if job_id in self._submitting:
            return
        self._submitting.add(job_id)
        try:
            row = await self.db.fetchrow(
                """
                SELECT j.id, j.media_id, j.effective_profile, j.status, j.encore_job_id,
                       j.source_path, j.source_size, j.input_params, j.profile_params,
                       j.requester_tg_id, j.status_message_id, j.retries,
                       m.duration_s, m.filename, m.fingerprinted
                FROM jobs j JOIN media_assets m ON m.id = j.media_id
                WHERE j.id = $1
                """,
                _as_uuid(job_id),
            )
            if row is None or row["status"] not in ("queued", "processing"):
                return
            if row["encore_job_id"]:
                return

            source = Path(row["source_path"]) if row["source_path"] else None
            if source is None or not source.is_file():
                source = await self._refetch_source(row)
            if source is None or not source.is_file():
                await self.fail_job(row, "source_unavailable", "source file vanished")
                return

            free = self._disk_free()
            reserved = await self.db.fetchval(
                "SELECT coalesce(sum(reserved_bytes), 0) FROM jobs "
                "WHERE status IN ('queued', 'processing') AND id <> $1",
                _as_uuid(job_id),
            )
            need = int((row["source_size"] or 0) * self.cfg.admission_need_factor) \
                + self.cfg.admission_floor_bytes
            if max(0, free - int(reserved or 0)) < need:
                if self.cfg.disk_defer:
                    # Capacity vanished between admission and start - defer
                    # instead of failing; promote_deferred picks it up later.
                    await self.db.execute(
                        "UPDATE jobs SET status='deferred', stage='deferred', "
                        "reserved_bytes=$2, updated_at=now() "
                        "WHERE id=$1 AND status IN ('queued','processing')",
                        _as_uuid(job_id), need,
                    )
                    for r in await self.db.fetch(
                        "SELECT chat_id, status_message_id, tg_id FROM job_requesters "
                        "WHERE job_id = $1",
                        _as_uuid(job_id),
                    ):
                        self._edit_status(
                            r["chat_id"], r["status_message_id"],
                            tr("status_deferred", await self._lang(r["tg_id"])), force=True,
                        )
                    return
                await self._retry_or_fail(row, "disk", "disk space below safe threshold")
                return

            # The source lives on the bot-api volume (hashed in place at
            # registration). Its absolute path contains the bot token, so it
            # must never be handed to Encore (which logs the full ffmpeg
            # command at INFO) ??? _stage_source aliases it into /media.
            used_path = await self._stage_source(job_id, source, row["filename"])

            await self._set_stage(job_id, "copying")
            await self.db.execute(
                "UPDATE jobs SET started_at = COALESCE(started_at, now()) WHERE id = $1",
                _as_uuid(job_id),
            )
            # Single fingerprint submission (SPEC-03): register_media used to
            # submit too - the worker's "WHERE fingerprinted = FALSE" guard
            # made the second pass pure wasted CPU on a 4GB decode.
            if not row["fingerprinted"]:
                self.fingerprinter.submit(row["media_id"], used_path,
                                          row["duration_s"] or 0.0)

            # --- remux utility: stream-copy container shift, no Encore job ---
            if (row["effective_profile"] or "") == "remux":
                out_dir = Path(self.cfg.media_out) / job_id
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / "out.mp4"
                await self.db.execute(
                    "UPDATE jobs SET status='processing', stage='encoding', "
                    "progress_changed_at=now(), updated_at=now() WHERE id = $1",
                    _as_uuid(job_id),
                )
                try:
                    await asyncio.to_thread(
                        media_mod.remux_to_mp4, used_path, str(out_path)
                    )
                except media_mod.MediaError as exc:
                    await self.fail_job(row, "remux", str(exc)[:200])
                    return
                full_row = await self.db.fetchrow(
                    "SELECT j.*, m.duration_s AS source_duration FROM jobs j "
                    "JOIN media_assets m ON m.id = j.media_id WHERE j.id = $1",
                    _as_uuid(job_id),
                )
                await self.complete_job(full_row, None)
                return

            callback = (
                f"http://bot:8080/internal/encore-callback"
                f"?job={job_id}&sig={self._callback_sig(job_id)}"
            )
            # Segmented (chunk-parallel) transcoding for long sources: Encore
            # splits the job into segmentLength chunks processed concurrently
            # by all workers against the shared work dir. Excluded: profiles
            # whose profileParams use SpEL (repair input-params interplay,
            # custom bitrate, level CRF).
            segment_length = None
            if (self.cfg.segment_enabled
                    and (row["duration_s"] or 0) >= self.cfg.segment_min_duration
                    and (row["effective_profile"] or "") not in
                    ("repair", "custom", "level")):
                segment_length = self.cfg.segment_length
            try:
                encore_id = await self.encre.submit_job(
                    profile=row["effective_profile"] or "balanced",
                    output_folder=f"{self.cfg.media_out}/{job_id}",
                    base_name="out",
                    input_uri=used_path,
                    external_id=job_id,
                    callback_uri=callback,
                    profile_params=_load_json(row["profile_params"]),
                    input_params=_load_json(row["input_params"]),
                    segment_length=segment_length,
                )
            except EncoreError as exc:
                await self._retry_or_fail(row, "encore_api", str(exc)[:300])
                return
            claimed = await self.db.execute(
                "UPDATE jobs SET encore_job_id = $2, status = 'processing', stage = 'encoding', "
                "progress_changed_at = now(), updated_at = now() "
                "WHERE id = $1 AND encore_job_id IS NULL AND status IN ('queued','processing')",
                _as_uuid(job_id), encore_id,
            )
            if claimed == "UPDATE 0":
                return
            log.info("job submitted to encore", extra={
                "job_id": job_id, "encore_job": encore_id,
                "detail": f"input exists={os.path.exists(used_path)}"})
        except Exception:  # noqa: BLE001
            log.exception("run_job crashed", extra={"job_id": job_id})
            try:
                row = await self.db.fetchrow("SELECT * FROM jobs WHERE id = $1", _as_uuid(job_id))
                if row and row["status"] in ("queued", "processing"):
                    await self.fail_job(row, "unknown", "internal error")
            except Exception:  # noqa: BLE001
                log.exception("fail_job after crash also failed", extra={"job_id": job_id})
        finally:
            self._submitting.discard(job_id)

    async def _refetch_source(self, row):
        """Re-create the stable media copy from the bot-api file if it vanished."""
        media = await self.db.fetchrow(
            "SELECT tg_file_id, filename FROM media_assets WHERE id = $1", row["media_id"]
        )
        if not media or not media["tg_file_id"]:
            return None
        try:
            tg_file = await self.bot.get_file(media["tg_file_id"])
        except TelegramAPIError:
            return None
        botapi_path = await self.resolve_local_path(tg_file.file_path)
        if botapi_path is None:
            return None
        ext = Path(media["filename"] or "source.mp4").suffix.lower()
        if ext not in COPY_EXTS:
            ext = ".bin"
        stable = Path(self.cfg.media_incoming) / f"m-{row['media_id']}" / f"source{ext}"
        stable.parent.mkdir(parents=True, exist_ok=True)
        sha = await media_mod.copy_and_hash(botapi_path, stable)
        await self.db.execute(
            "UPDATE media_assets SET sha256 = $2 WHERE id = $1", row["media_id"], sha
        )
        await self.db.execute(
            "UPDATE jobs SET source_path = $2 WHERE id = $1", row["id"], str(stable)
        )
        return stable

    def _callback_sig(self, job_id: str) -> str:
        return hmac_mod.new(
            self.cfg.internal_secret.encode(), job_id.encode(), hashlib.sha256
        ).hexdigest()

    # ------------------------------------------------------------------
    # reconciliation (poller)
    # ------------------------------------------------------------------
    async def promote_deferred(self) -> None:
        """Admit deferred jobs when disk capacity frees (ArgonsEncoder-style)."""
        if not self.cfg.disk_defer:
            return
        rows = await self.db.fetch(
            "SELECT id, requester_tg_id, reserved_bytes, source_size FROM jobs "
            "WHERE status = 'deferred' ORDER BY enqueued_at LIMIT 10"
        )
        if not rows:
            return
        reserved = await self.db.fetchval(
            "SELECT coalesce(sum(reserved_bytes), 0) FROM jobs "
            "WHERE status IN ('queued', 'processing')"
        )
        free = max(0, self._disk_free() - int(reserved or 0))
        for row in rows:
            # Re-evaluate the need with the CURRENT admission factor: a
            # deferred job's stored reservation may reflect an older factor
            # or a temporarily distorted admission state.
            need = int((row["source_size"] or 0) * self.cfg.admission_need_factor) \
                + self.cfg.admission_floor_bytes
            if free < need:
                continue
            # Per-user cap re-check (Argons queue_manager pattern): limits may
            # have changed while the job sat deferred - promotion must not
            # push the user past max_active. Per-job loop instead of one SQL
            # subquery because max_active resolves per user/tier in Python.
            limits = await self.effective_limits(row["requester_tg_id"])
            active = await self.db.fetchval(
                "SELECT count(*) FROM jobs WHERE requester_tg_id = $1 "
                "AND status IN ('queued','processing','deferred')",
                row["requester_tg_id"],
            )
            if int(active or 0) >= limits["max_active"]:
                continue
            free -= need
            await self.db.execute(
                "UPDATE jobs SET status='queued', stage='queued', "
                "reserved_bytes=$2, updated_at=now() "
                "WHERE id=$1 AND status='deferred'",
                row["id"], need,
            )
            log.info("deferred job promoted", extra={"job_id": str(row["id"])})
            self.spawn(self.run_job(str(row["id"])))

    async def poll_once(self) -> None:
        try:
            await self.promote_deferred()
        except Exception:  # noqa: BLE001
            log.exception("promote_deferred failed")
        rows = await self.db.fetch(
            "SELECT j.*, m.duration_s AS source_duration FROM jobs j "
            "JOIN media_assets m ON m.id = j.media_id "
            "WHERE j.status IN ('queued','processing') "
            "ORDER BY j.priority DESC, j.enqueued_at"
        )
        for row in rows:
            job_id = str(row["id"])
            if not row["encore_job_id"]:
                if row["status"] == "queued":
                    # live queue position on the user's status card
                    try:
                        pos = await self.db.fetchval(
                            "SELECT count(*) + 1 FROM jobs WHERE status IN ('queued','deferred') "
                            "AND (priority > $1 OR (priority = $1 AND enqueued_at < $2))",
                            row["priority"], row["enqueued_at"],
                        )
                        lang = await self._lang(row["requester_tg_id"])
                        self._edit_status(
                            row["requester_tg_id"], row["status_message_id"],
                            self._progress_text(row, lang, {"queue_pos": pos}),
                            markup=self._cancel_markup(job_id, lang),
                        )
                    except Exception:  # noqa: BLE001 - informational only
                        pass
                if job_id not in self._submitting:
                    self.spawn(self.run_job(job_id))
                continue
            try:
                await self.reconcile_job(row)
            except EncoreNotFound:
                await self._retry_or_fail(row, "encore_api", "encore job record missing")
            except EncoreError as exc:
                log.warning("poll reconcile error",
                            extra={"job_id": job_id, "detail": str(exc)[:200]})
            except Exception:  # noqa: BLE001
                log.exception("poll_once job error", extra={"job_id": job_id})

    async def poll_job(self, job_id: str) -> None:
        row = await self.db.fetchrow(
            "SELECT j.*, m.duration_s AS source_duration FROM jobs j "
            "JOIN media_assets m ON m.id = j.media_id WHERE j.id = $1",
            _as_uuid(job_id),
        )
        if row and row["encore_job_id"] and row["status"] in ("queued", "processing"):
            try:
                await self.reconcile_job(row)
            except EncoreNotFound:
                await self._retry_or_fail(row, "encore_api", "encore job record missing")
            except EncoreError as exc:
                log.warning("callback reconcile error",
                            extra={"job_id": job_id, "detail": str(exc)[:200]})

    async def reconcile_job(self, row) -> None:
        info = await self.encre.get_job(row["encore_job_id"])
        status = info.get("status")
        # Encore has been observed sending "37.5" - a bare int() would crash
        # the poll loop for that job (SPEC-01).
        try:
            progress = int(float(info.get("progress") or 0))
        except (TypeError, ValueError):
            progress = 0
        job_id = str(row["id"])

        if status == "IN_PROGRESS":
            changed = progress != row["progress"]
            if changed:
                await self.db.execute(
                    "UPDATE jobs SET progress = $2, progress_changed_at = now(), "
                    "updated_at = now(), status = 'processing' WHERE id = $1",
                    row["id"], progress,
                )
            reference = _ensure_tz(row["progress_changed_at"]) or _ensure_tz(row["started_at"]) \
                or _ensure_tz(row["enqueued_at"])
            if reference and _utcnow() - reference > timedelta(minutes=self.cfg.stuck_minutes):
                log.warning("job stuck, cancelling", extra={"job_id": job_id})
                try:
                    await self.encre.cancel_job(row["encore_job_id"])
                except EncoreError:
                    pass
                await self._retry_or_fail(row, "stuck", "no progress for too long")
                return
            await self._broadcast_progress(row, info)
            return

        if status == "SUCCESSFUL":
            await self.complete_job(row, info)
        elif status == "FAILED":
            await self._retry_or_fail(row, "ffmpeg",
                                      str(info.get("message") or "encore job failed")[:500])
        elif status == "CANCELLED":
            await self._mark_cancelled(row)
        # NEW/QUEUED: nothing to do yet

    def _cancel_markup(self, job_id: str, lang: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=tr("btn_cancel_job", lang),
                                 callback_data=f"canc:{job_id}")
        ]])

    async def _broadcast_progress(self, row, info: dict) -> None:
        primary_lang = await self._lang(row["requester_tg_id"])
        self._edit_status(
            row["requester_tg_id"], row["status_message_id"],
            self._progress_text(row, primary_lang, info),
            markup=self._cancel_markup(str(row["id"]), primary_lang),
        )
        for r in await self.db.fetch(
            "SELECT chat_id, status_message_id, tg_id FROM job_requesters "
            "WHERE job_id = $1 AND tg_id <> $2",
            row["id"], row["requester_tg_id"],
        ):
            lang = await self._lang(r["tg_id"])
            self._edit_status(
                r["chat_id"], r["status_message_id"],
                self._progress_text(row, lang, info),
                markup=self._cancel_markup(str(row["id"]), lang),
            )

    async def _retry_or_fail(self, row, category: str, detail: str) -> None:
        detail_l = detail.lower()
        is_mux_error = category == "ffmpeg" and any(
            marker in detail_l for marker in MUX_ERROR_MARKERS
        )
        current_params = _load_json(row["input_params"]) or {}
        # ffmpeg "exit 183 / Nothing was encoded" sources (decoder finds no
        # usable frames) are deliberately NOT routed through the repair
        # ladder: genpts/aresample cannot fix an empty stream, and a retry
        # would burn a full encode pass on a doomed input. They stay
        # cleanly categorized as `ffmpeg` with the message stored.
        # Two-stage repair for damaged sources:
        # 1st mux failure -> regenerate PTS + discard corrupt packets;
        # 2nd mux failure -> also switch to the `repair` profile (async audio).
        if is_mux_error and not current_params and row["retries"] < self.cfg.job_retries + 1:
            await self.db.execute(
                "UPDATE jobs SET status = 'queued', retries = retries + 1, "
                "encore_job_id = NULL, progress = 0, error_category = $2, "
                "error_message = $3, input_params = $4::jsonb, updated_at = now() "
                "WHERE id = $1 AND status IN ('queued','processing')",
                row["id"], category, detail,
                json.dumps({"fflags": "+genpts+discardcorrupt"}),
            )
            log.warning("retrying with genpts+discardcorrupt", extra={"job_id": str(row["id"])})
            self.spawn(self.run_job(str(row["id"])))
            return
        if (is_mux_error and current_params
                and row["effective_profile"] != "repair"
                and row["retries"] < self.cfg.job_retries + 2):
            await self.db.execute(
                "UPDATE jobs SET status = 'queued', retries = retries + 1, "
                "encore_job_id = NULL, progress = 0, error_category = $2, "
                "error_message = $3, effective_profile = 'repair', "
                "input_params = $4::jsonb, updated_at = now() "
                "WHERE id = $1 AND status IN ('queued','processing')",
                row["id"], category, detail,
                json.dumps({"fflags": "+genpts+discardcorrupt"}),
            )
            log.warning("retrying with repair profile", extra={"job_id": str(row["id"])})
            self.spawn(self.run_job(str(row["id"])))
            return
        if row["retries"] < self.cfg.job_retries and category in TRANSIENT_CATEGORIES:
            await self.db.execute(
                "UPDATE jobs SET status = 'queued', retries = retries + 1, "
                "encore_job_id = NULL, progress = 0, error_category = $2, "
                "error_message = $3, updated_at = now() "
                "WHERE id = $1 AND status IN ('queued','processing')",
                row["id"], category, detail,
            )
            self._edit_status(
                row["requester_tg_id"], row["status_message_id"],
                tr("status_retrying", await self._lang(row["requester_tg_id"]),
                   attempt=row["retries"] + 1), force=True,
            )
            for r in await self.db.fetch(
                "SELECT chat_id, status_message_id, tg_id FROM job_requesters WHERE job_id = $1",
                row["id"],
            ):
                self._edit_status(
                    r["chat_id"], r["status_message_id"],
                    tr("status_retrying", await self._lang(r["tg_id"]),
                       attempt=row["retries"] + 1), force=True,
                )
            self.spawn(self.run_job(str(row["id"])))
        else:
            await self.fail_job(row, category, detail)

    async def retry_user_job(self, job_id: str, tg_id: int) -> tuple[bool, str]:
        """User-facing bounded retry of a failed job (idempotent)."""
        row = await self.db.fetchrow("SELECT * FROM jobs WHERE id = $1", _as_uuid(job_id))
        if not row or row["status"] != "failed":
            return False, "not_failed"
        if row["requester_tg_id"] != tg_id and tg_id not in await self.admin_ids():
            return False, "not_allowed"
        if row["retries"] >= self.cfg.job_retries + 2:
            return False, "limit"
        # Admission-lite (F2): a requeue must respect the same fairness caps as
        # a fresh submission. Admins are exempt. The new reject reasons
        # ("queue_full"/"user_busy") have no dedicated localized string yet, so
        # both map to the existing generic "limit" reason - the button handler
        # shows the same "retry_not_allowed" text for every False reason.
        if tg_id not in await self.admin_ids():
            queued = await self.db.fetchval("SELECT count(*) FROM jobs WHERE status = 'queued'")
            if int(queued or 0) >= self.cfg.max_queued:
                return False, "limit"  # queue_full
            limits = await self.effective_limits(row["requester_tg_id"])
            active = await self.db.fetchval(
                "SELECT count(*) FROM jobs WHERE requester_tg_id = $1 "
                "AND status IN ('queued','processing','deferred')",
                row["requester_tg_id"],
            )
            if int(active or 0) >= limits["max_active"]:
                return False, "limit"  # user_busy
        # Atomic claim (Argons claim-with-TTL pattern): the increment and the
        # cap guard live in one conditional UPDATE so concurrent presses
        # cannot race each other back to unlimited retries.
        claimed = await self.db.execute(
            "UPDATE jobs SET status='queued', encore_job_id=NULL, progress=0, "
            "error_category=NULL, error_message=NULL, updated_at=now(), stage='queued', "
            "retries = retries + 1 "
            "WHERE id=$1 AND status='failed' AND retries < $2",
            row["id"], self.cfg.job_retries + 2,
        )
        if claimed == "UPDATE 0":
            return False, "limit"
        self.spawn(self.run_job(str(row["id"])))
        return True, str(row["id"])[:8]

    async def fail_job(self, row, category: str, detail: str) -> None:
        if row["status"] in ("completed", "failed", "cancelled"):
            return
        detail = media_mod.redact(detail)
        # Gate the counter on the actual state transition: concurrent
        # failure paths (callback + poller) used to double-count.
        failed = await self.db.fetchval(
            "UPDATE jobs SET status = 'failed', stage = 'failed', reserved_bytes = 0, error_category = $2, "
            "error_message = $3, completed_at = now(), updated_at = now() "
            "WHERE id = $1 AND status IN ('queued','processing') RETURNING id",
            row["id"], category, detail,
        )
        if not failed:
            return
        await self.db.bump("jobs_failed")
        log.error("job failed",
                  extra={"job_id": str(row["id"]), "status": category, "detail": detail[:300]})
        await self._cleanup_job_dirs(str(row["id"]), keep_output=False)
        # job_requesters includes the requester, so this single loop reaches
        # everyone - the requester used to get a second identical status_failed
        # edit right after the loop (UX-04).
        for r in await self.db.fetch(
            "SELECT chat_id, status_message_id, tg_id FROM job_requesters WHERE job_id = $1",
            row["id"],
        ):
            lang = await self._lang(r["tg_id"])
            self._edit_status(
                r["chat_id"], r["status_message_id"],
                tr("status_failed", lang), markup=failure_markup(str(row["id"]), lang),
                force=True,
            )

    async def _mark_cancelled(self, row) -> None:
        cancelled = await self.db.fetchval(
            "UPDATE jobs SET status = 'cancelled', stage = 'cancelled', reserved_bytes = 0, "
            "completed_at = now(), updated_at = now() "
            "WHERE id = $1 AND status IN ('queued','processing') RETURNING id",
            row["id"],
        )
        if not cancelled:
            return
        await self.db.bump("jobs_cancelled")
        await self._cleanup_job_dirs(str(row["id"]), keep_output=False)
        for r in await self.db.fetch(
            "SELECT chat_id, status_message_id, tg_id FROM job_requesters WHERE job_id = $1",
            row["id"],
        ):
            self._edit_status(r["chat_id"], r["status_message_id"],
                              tr("status_cancelled", await self._lang(r["tg_id"])),
                              force=True)

    async def cancel_job(self, row, by_admin: bool = False) -> bool:
        if row["status"] not in ("queued", "processing"):
            return False
        if row["encore_job_id"]:
            try:
                await self.encre.cancel_job(row["encore_job_id"])
            except EncoreError as exc:
                log.warning("encore cancel failed",
                            extra={"job_id": str(row["id"]), "detail": str(exc)[:150]})
        await self._mark_cancelled(row)
        log.info("job cancelled",
                 extra={"job_id": str(row["id"]), "detail": f"by_admin={by_admin}"})
        return True

    # ------------------------------------------------------------------
    # completion
    # ------------------------------------------------------------------
    async def complete_job(self, row, encore_info: dict | None = None) -> None:
        job_id = str(row["id"])
        if row["status"] in ("completed", "failed", "cancelled"):
            return
        # Atomic completion claim: the Encore completion callback and the
        # poller can both call reconcile for the same job; without this
        # claim, two concurrent _complete_split runs delete each other's
        # part files (observed: FileNotFoundError part001.mp4).
        claimed = await self.db.fetchval(
            "UPDATE jobs SET stage='completing', updated_at=now() "
            "WHERE id=$1 AND status IN ('queued','processing') "
            "AND (coalesce(stage,'') <> 'completing' "
            "     OR updated_at < now() - interval '10 minutes') RETURNING id",
            row["id"],
        )
        if claimed is None:
            return
        lang = await self._lang(row["requester_tg_id"])
        self._edit_status(row["requester_tg_id"], row["status_message_id"],
                          tr("stage_archiving", lang), force=True)
        await self._set_stage(job_id, "validating")

        out_dir = Path(self.cfg.media_out) / job_id
        media_filename = await self._media_filename(row)
        # Original-name output: strip any known media extension first, else
        # most files would end up as "name.mp4.mp4".
        stem = media_mod.sanitize_filename(media_filename, 60)
        low = stem.lower()
        for ext in COPY_EXTS:
            if low.endswith(ext):
                stem = stem[: -len(ext)].rstrip()
                break
        final_name = (stem or "video") + ".mp4"
        # Accept both the encore "out*" name and a previously renamed output
        # (a crash between rename and completion must not lose the file).
        candidates = sorted(
            (p for p in out_dir.iterdir()
             if p.is_file() and (p.name.startswith("out") or p.name == final_name)),
            key=lambda p: p.stat().st_size,
            reverse=True,
        ) if out_dir.is_dir() else []
        if not candidates:
            await self.fail_job(row, "ffmpeg", "no output file produced")
            return
        output_path = candidates[0]
        output_size = output_path.stat().st_size
        source_size = row["source_size"] or 0

        # F3: prove the lease before each long await; on a lost lease another
        # runner owns the completion - just stand down.
        if not await self._touch_completion_lease(job_id):
            log.warning("completion lease lost, standing down",
                        extra={"job_id": job_id})
            return
        try:
            out_probe = await media_mod.probe_video(output_path)
        except media_mod.MediaError as exc:
            await self.fail_job(row, "validation", f"output invalid: {exc}")
            return
        src_probe = await self._source_probe(row)
        src_duration = (src_probe or {}).get("duration_s")
        if src_duration and out_probe.get("duration_s"):
            ratio = out_probe["duration_s"] / src_duration
            if not (0.85 <= ratio <= 1.15):
                await self.fail_job(
                    row, "validation",
                    f"output duration {out_probe['duration_s']:.1f}s vs source {src_duration:.1f}s",
                )
                return

        # Deliver with the user's own filename instead of "out.mp4".
        renamed = output_path.parent / final_name
        if renamed != output_path and not renamed.exists():
            try:
                output_path = output_path.rename(renamed)
            except OSError:
                pass

        await self._set_stage(job_id, "archiving")
        if not await self._touch_completion_lease(job_id):
            log.warning("completion lease lost, standing down",
                        extra={"job_id": job_id})
            return
        out_sha = await media_mod.sha256_file(output_path)
        output_media_id = await self.db.fetchval(
            """
            INSERT INTO media_assets
                (sha256, size_bytes, filename, duration_s, width, height, fps,
                 vcodec, acodec, audio_channels, container, bitrate, probe)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb)
            RETURNING id
            """,
            out_sha, output_size, output_path.name,
            out_probe.get("duration_s"), out_probe.get("width"), out_probe.get("height"),
            out_probe.get("fps"), out_probe.get("vcodec"), out_probe.get("acodec"),
            out_probe.get("audio_channels"), out_probe.get("container"),
            out_probe.get("bitrate"), json.dumps(out_probe),
        )

        # Remux results are container shifts, not size reductions - the
        # no-gain policy does not apply to them.
        no_gain = (source_size > 0
                   and output_size >= source_size * self.cfg.no_gain_threshold
                   and row["profile"] != "remux")
        if no_gain and (row["effective_profile"] or "") == "level":
            # CRF x264 lost to an already-tight source (heavily pre-compressed
            # or grainy material) - one-shot escalation to the HEVC pass
            # instead of handing the original back.
            await self._escalate_level_to_265(row)
            return
        oversized = output_size > self.cfg.max_upload_bytes
        needs_split = oversized and self.cfg.split_upload and bool(self.state.archive_channel_id)
        blocked = (oversized and not needs_split) or not self.state.archive_channel_id
        job_short = job_id[:8]
        profile_row = await self.db.fetchrow(
            "SELECT title FROM profiles WHERE key = $1", row["profile"]
        )
        profile_title = (profile_row or {})["title"] if profile_row else row["profile"]
        caption = archive_mod.build_caption(
            media_filename, profile_title, out_probe,
            source_size, output_size, job_short,
        )

        # Admin global thumb if set, else grab a frame from the output so
        # every delivered/archived video gets a proper preview.
        thumbnail = await self._delivery_thumbnail(job_id, output_path, out_probe)

        if needs_split and not no_gain:
            ok = await self._complete_split(
                row, output_path, output_size, out_sha, output_media_id,
                out_probe, profile_title, media_filename, source_size, job_short,
                thumbnail=thumbnail,
            )
            if not ok:
                return  # fail_job already handled
            return

        if no_gain or blocked:
            status = "no_gain" if no_gain else "blocked"
            stored_output_id = row["media_id"] if no_gain else output_media_id
            inserted = await self.db.fetchval(
                """
                INSERT INTO archive_records
                    (source_media_id, output_media_id, profile, profile_version, channel_id,
                     message_id, status, sha256, validated)
                VALUES ($1,$2,$3,1,$4,0,$5,$6,TRUE)
            ON CONFLICT (source_media_id, profile, profile_version, part_index)
                WHERE status IN ('active','no_gain') DO NOTHING
            RETURNING id
            """,
            row["media_id"], stored_output_id, row["profile"],
            self.state.archive_channel_id or 0, status, out_sha,
        )
            archive_id = inserted or await self.db.fetchval(
                "SELECT id FROM archive_records WHERE source_media_id = $1 AND profile = $2 "
                "AND profile_version = 1 AND status IN ('active','no_gain')",
                row["media_id"], row["profile"],
            )
            if no_gain:
                await self.db.bump("no_gain_events")
            else:
                await self.db.bump("archive_blocked")
                reason = (
                    f"output {media_mod.human_size(output_size)} > "
                    f"{media_mod.human_size(self.cfg.max_upload_bytes)}"
                    if output_size > self.cfg.max_upload_bytes
                    else "archive channel not configured"
                )
                await self.notify_admins(
                    tr("archive_blocked_admin", "fa",
                       job=job_short, out=reason,
                       hours=self.cfg.tmp_retention_hours)
                )
            done = await self.db.fetchval(
                "UPDATE jobs SET status='completed', stage='completed', reserved_bytes=0, output_size=$2, "
                "output_media_id=$3, archived=FALSE, is_no_gain=$4, "
                "completed_at=now(), updated_at=now(), progress=100 "
                "WHERE id=$1 AND status IN ('queued','processing') RETURNING id",
                row["id"], output_size, stored_output_id, no_gain,
            )
            if not done:
                return
            await self.db.bump("jobs_encoded")
            await self._deliver_to_requesters(
                row, archive_id, stored_output_id, None,
                no_gain=no_gain, blocked=blocked, out_size=output_size,
                out_probe=out_probe,
            )
            await self._cleanup_job_dirs(job_id, keep_output=blocked, keep_source=no_gain)
            return

        # --- real archive upload ---
        # thumbnail was resolved earlier: admin global thumb or an
        # auto-grabbed output frame (aiogram needs an FSInputFile).
        if not await self._touch_completion_lease(job_id):
            log.warning("completion lease lost, standing down",
                        extra={"job_id": job_id})
            return
        try:
            sent = await self._archive_upload(
                path=output_path, caption=caption, thumbnail=thumbnail,
            )
        except TelegramBadRequest as exc:
            await self.fail_job(row, "archive",
                                f"archive upload failed: {str(exc)[:200]}")
            return
        except TelegramAPIError as exc:
            await self.fail_job(row, "archive",
                                f"archive upload failed: {str(exc)[:200]}")
            return
        archive_msg_id = sent.message_id
        out_file_id = sent.video.file_id if sent.video else None
        out_unique = sent.video.file_unique_id if sent.video else None
        await self.db.execute(
            "UPDATE media_assets SET tg_file_id = $2, tg_file_unique_id = $3 WHERE id = $1",
            output_media_id, out_file_id, out_unique,
        )
        permalink = _permalink(self.state.archive_channel_id, archive_msg_id)
        archive_insert_sql = """
            INSERT INTO archive_records
                (source_media_id, output_media_id, profile, profile_version, channel_id,
                 message_id, file_unique_id, permalink, status, sha256, validated)
            VALUES ($1,$2,$3,1,$4,$5,$6,$7,'active',$8,TRUE)
            ON CONFLICT (source_media_id, profile, profile_version, part_index)
                WHERE status IN ('active','no_gain') DO NOTHING
            RETURNING id
            """
        inserted = await self.db.fetchval(
            archive_insert_sql,
            row["media_id"], output_media_id, row["profile"], self.state.archive_channel_id,
            archive_msg_id, out_unique, permalink, out_sha,
        )
        if inserted is None and (row["effective_profile"] or "") == "level265":
            # A stale no_gain marker from the earlier x264 attempt must not
            # block archiving the stronger HEVC result.
            await self.db.execute(
                "DELETE FROM archive_records WHERE source_media_id = $1 AND profile = $2 "
                "AND profile_version = 1 AND status = 'no_gain'",
                row["media_id"], row["profile"],
            )
            inserted = await self.db.fetchval(
                archive_insert_sql,
                row["media_id"], output_media_id, row["profile"], self.state.archive_channel_id,
                archive_msg_id, out_unique, permalink, out_sha,
            )
        if inserted is None:
            archive_id = await self.db.fetchval(
                "SELECT id FROM archive_records WHERE source_media_id = $1 AND profile = $2 "
                "AND profile_version = 1 AND status IN ('active','no_gain')",
                row["media_id"], row["profile"],
            )
            try:
                await self.bot.delete_message(self.state.archive_channel_id, archive_msg_id)
            except TelegramAPIError:
                pass
            log.warning("duplicate archive upload removed",
                        extra={"job_id": job_id, "detail": str(archive_id)})
        else:
            archive_id = inserted
        done = await self.db.fetchval(
            "UPDATE jobs SET status='completed', stage='completed', reserved_bytes=0, output_size=$2, "
            "output_media_id=$3, archived=TRUE, completed_at=now(), updated_at=now(), "
            "progress=100 WHERE id=$1 AND status IN ('queued','processing') RETURNING id",
            row["id"], output_size, output_media_id,
        )
        if not done:
            return
        await self.db.bump("jobs_encoded")
        await self.db.bump("bytes_out", output_size)
        if source_size > output_size:
            await self.db.bump("bytes_saved", source_size - output_size)
        log.info(
            "job completed + archived",
            extra={"job_id": job_id, "encore_job": (encore_info or {}).get("id"),
                   "detail": f"{media_mod.human_size(source_size)} -> "
                             f"{media_mod.human_size(output_size)}"},
        )
        await self._deliver_to_requesters(
            row, archive_id, output_media_id, out_file_id,
            out_size=output_size, out_probe=out_probe,
        )
        await self._cleanup_job_dirs(job_id, keep_output=False)

    async def _complete_split(
        self, row, output_path: Path, output_size: int, out_sha: str,
        output_media_id, out_probe: dict, profile_title: str,
        media_filename: str, source_size: int, job_short: str,
        thumbnail=None,
    ) -> bool:
        """Archive an oversized output as independently playable parts.

        Idempotent: parts already recorded in archive_records are skipped on
        retry, so an interrupted split continues without duplicate uploads.
        """
        job_id = str(row["id"])
        lang = await self._lang(row["requester_tg_id"])
        split_bytes = int(self.cfg.max_upload_bytes * self.cfg.split_safety)
        parts_dir = Path(self.cfg.media_out) / job_id / "parts"
        # The split itself is the long await this lease exists for (F3):
        # split_by_size deletes stale part* files before segmenting.
        if not await self._touch_completion_lease(job_id):
            log.warning("completion lease lost before split, standing down",
                        extra={"job_id": job_id})
            return False
        try:
            parts = await asyncio.to_thread(
                media_mod.split_by_size, str(output_path), str(parts_dir),
                split_bytes, out_probe.get("duration_s") or 1.0,
            )
        except media_mod.MediaError as exc:
            await self.fail_job(row, "archive", f"split failed: {exc}")
            return False
        total = len(parts)
        log.info("output split for delivery",
                 extra={"job_id": job_id,
                        "detail": f"{total} parts, {media_mod.human_size(output_size)}"})

        # Idempotency: keep parts already archived from previous attempts.
        existing = await self.db.fetch(
            """
            SELECT id, part_index, message_id FROM archive_records
            WHERE source_media_id = $1 AND profile = $2 AND profile_version = 1
              AND status = 'active'
            ORDER BY part_index
            """,
            row["media_id"], row["profile"],
        )
        existing_map = {r["part_index"]: r for r in existing}
        first_id = existing[0]["id"] if existing else None
        archive_ids: list = []
        for i, part in enumerate(parts):
            if i in existing_map and existing_map[i]["message_id"]:
                archive_ids.append(existing_map[i]["id"])
                continue
            part_size = part.stat().st_size
            caption = archive_mod.build_caption(
                f"{media_filename} (part {i + 1}/{total})", profile_title,
                out_probe, source_size, part_size, job_short,
            )
            # F3: renew the lease before every part upload; if it is lost,
            # another runner re-claimed and is re-splitting - continuing here
            # would upload parts it is about to delete.
            if not await self._touch_completion_lease(job_id):
                log.warning("completion lease lost during split, standing down",
                            extra={"job_id": job_id, "detail": f"part {i + 1}/{total}"})
                return False
            try:
                sent = await self._archive_upload(
                    path=part, caption=caption, thumbnail=thumbnail,
                )
            except TelegramBadRequest as exc:
                await self.fail_job(row, "archive",
                                    f"part {i + 1} upload failed: {str(exc)[:150]}")
                return False
            except TelegramAPIError as exc:
                await self.fail_job(row, "archive",
                                    f"part {i + 1} upload failed: {str(exc)[:150]}")
                return False
            permalink = _permalink(self.state.archive_channel_id, sent.message_id)
            rec_id = await self.db.fetchval(
                """
                INSERT INTO archive_records
                    (source_media_id, output_media_id, profile, profile_version,
                     channel_id, message_id, file_unique_id, permalink, status,
                     sha256, validated, part_index, part_total, split_of)
                VALUES ($1,$2,$3,1,$4,$5,$6,$7,'active',$8,TRUE,$9,$10,$11)
                ON CONFLICT (source_media_id, profile, profile_version, part_index)
                    WHERE status IN ('active','no_gain') DO NOTHING
                RETURNING id
                """,
                row["media_id"], output_media_id, row["profile"],
                self.state.archive_channel_id, sent.message_id,
                (sent.video.file_unique_id if sent.video else None),
                permalink, out_sha, i, total, first_id,
            )
            if rec_id:
                archive_ids.append(rec_id)
            if first_id is None and rec_id:
                first_id = rec_id
        archive_ids = [a for a in archive_ids if a]
        done = await self.db.fetchval(
            "UPDATE jobs SET status='completed', stage='completed', reserved_bytes=0, output_size=$2, "
            "output_media_id=$3, archived=TRUE, completed_at=now(), updated_at=now(), "
            "progress=100 WHERE id=$1 AND status IN ('queued','processing') RETURNING id",
            row["id"], output_size, output_media_id,
        )
        if not done:
            return False
        await self.db.bump("jobs_encoded")
        await self.db.bump("bytes_out", output_size)
        if source_size > output_size:
            await self.db.bump("bytes_saved", source_size - output_size)
        await self._deliver_to_requesters(
            row, first_id, output_media_id, None,
            out_size=output_size, out_probe=out_probe,
            part_ids=archive_ids, part_total=total,
        )
        await self._cleanup_job_dirs(job_id, keep_output=False)
        return True

    async def _archive_upload(self, *, path: Path, caption: str,
                              thumbnail: FSInputFile | None,
                              max_attempts: int = 3):
        """Upload a video to the archive channel with bounded concurrency and
        exponential-backoff retry on transient errors (pattern: ArgonsEncoder
        UploadManager, reimplemented for Bot API)."""
        last_exc: Exception | None = None
        for attempt in range(max_attempts):
            try:
                async with self._upload_sem:
                    return await self.bot.send_video(
                        chat_id=self.state.archive_channel_id,
                        video=FSInputFile(str(path)),
                        caption=caption,
                        supports_streaming=True,
                        thumbnail=thumbnail,
                    )
            except TelegramRetryAfter as exc:
                last_exc = exc
                await asyncio.sleep(exc.retry_after + 1)
            except TelegramBadRequest:
                if thumbnail is not None:
                    # permanent rejection likely caused by the thumbnail -
                    # retry once without it before treating as transient
                    try:
                        async with self._upload_sem:
                            return await self.bot.send_video(
                                chat_id=self.state.archive_channel_id,
                                video=FSInputFile(str(path)),
                                caption=caption,
                                supports_streaming=True,
                            )
                    except TelegramRetryAfter as exc:
                        last_exc = exc
                        await asyncio.sleep(exc.retry_after + 1)
                    except TelegramAPIError as exc:
                        raise
                raise
            except TelegramAPIError as exc:
                last_exc = exc
                await asyncio.sleep(min(60, 5 * (2 ** attempt)))
        raise last_exc or TelegramAPIError("archive upload exhausted retries")

    async def _source_probe(self, row) -> dict | None:
        raw = await self.db.fetchval(
            "SELECT probe FROM media_assets WHERE id = $1", row["media_id"]
        )
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    async def _media_filename(self, row) -> str:
        name = await self.db.fetchval(
            "SELECT filename FROM media_assets WHERE id = $1", row["media_id"]
        )
        return name or "video"

    def _summary_text(self, lang: str, *, job_id: str, profile: str, filename: str,
                      source_size: int, output_size: int, probe: dict,
                      started, completed, new: bool, no_gain: bool = False) -> str:
        mins = "-"
        if started and completed:
            started_tz = _ensure_tz(started)
            completed_tz = _ensure_tz(completed)
            if started_tz and completed_tz:
                mins = f"{(completed_tz - started_tz).total_seconds() / 60:.0f}m"
        saved = source_size - output_size
        if saved > 0:
            pct = (saved / source_size * 100) if source_size else 0
            saved_line = tr("summary_saved", lang, saved=media_mod.human_size(saved),
                            pct=f"{pct:.0f}")
        else:
            saved_line = tr("summary_saved_neg", lang,
                            delta=media_mod.human_size(abs(saved)))
        res = f"{probe.get('width') or '?'}x{probe.get('height') or '?'}"
        dur = _fmt_clock(probe.get("duration_s") or 0)
        lines = [
            tr("summary_header", lang),
            tr("summary_file", lang, name=media_mod.sanitize_filename(filename, 40)),
            tr("summary_size", lang, src=media_mod.human_size(source_size),
               out=media_mod.human_size(output_size)),
            saved_line,
            tr("summary_duration", lang, dur=dur),
            tr("summary_res", lang, res=res),
            tr("summary_codec", lang,
               vc=(probe.get("vcodec") or "?").upper(),
               ac=(probe.get("acodec") or "?").upper()),
            tr("summary_time", lang, mins=mins),
            tr("summary_profile", lang, profile=profile),
            tr("summary_job", lang, job=job_id[:8]),
            tr("summary_source", lang, kind=tr(
                "summary_kind_reused" if not new else "summary_kind_new", lang)),
        ]
        if no_gain:
            lines.append(tr("status_done_nogain", lang))
        return "\n".join(lines)

    async def _deliver_parts(self, chat_id: int, archive_ids: list, lang: str,
                             total: int) -> tuple[bool, int]:
        """Deliver ordered archive parts to a chat. Returns (all_ok, delivered)."""
        delivered = 0
        all_ok = True
        for pid in archive_ids:
            rec = await self.db.fetchrow(
                "SELECT channel_id, message_id, status FROM archive_records WHERE id = $1", pid
            )
            if not rec or rec["status"] != "active":
                all_ok = False
                continue
            ok, method, mid = await archive_mod.deliver_result(
                self, chat_id=chat_id,
                archive_message_id=rec["message_id"] or 0,
                archive_channel_id=rec["channel_id"] or None,
            )
            if ok:
                delivered += 1
            elif method == "none" and rec["message_id"]:
                # The archive message itself is gone - mark it so future
                # lookups skip it and operators learn about the loss.
                await self.db.execute(
                    "UPDATE archive_records SET status='missing' "
                    "WHERE id=$1 AND status='active'", pid,
                )
                await self.db.bump("archive_missing_detected")
                await self.notify_admins(
                    tr("archive_missing", "fa", archive=str(pid)[:8])
                )
                all_ok = False
            else:
                all_ok = False
            await asyncio.sleep(1)  # pacing between multi-part sends
        if all_ok and total > 1:
            try:
                await self.bot.send_message(chat_id, tr("split_guide", lang, n=total))
            except TelegramAPIError:
                pass
        return all_ok, delivered

    async def _deliver_to_requesters(
        self, row, archive_id, output_media_id, out_file_id,
        no_gain: bool = False, blocked: bool = False, out_size: int = 0,
        out_probe: dict | None = None,
        part_ids: list | None = None, part_total: int = 1,
    ) -> None:
        reqs = await self.db.fetch(
            "SELECT * FROM job_requesters WHERE job_id = $1 AND delivered = FALSE", row["id"]
        )
        archive_row = None
        if archive_id:
            archive_row = await self.db.fetchrow(
                "SELECT * FROM archive_records WHERE id = $1", archive_id
            )
        out_asset = await self.db.fetchrow(
            "SELECT tg_file_id FROM media_assets WHERE id = $1", output_media_id
        ) if output_media_id else None
        src_asset = await self.db.fetchrow(
            "SELECT tg_file_id, width, height, duration_s, vcodec, acodec, probe FROM media_assets WHERE id = $1", row["media_id"]
        )
        source_size = row["source_size"] or 0
        started = row["started_at"]
        completed = row["completed_at"] or _utcnow()
        filename = await self._media_filename(row)
        out_probe = out_probe or {}
        if no_gain and src_asset:
            effective_probe = dict(src_asset.get("probe") or {})
            if not effective_probe:
                effective_probe = {
                    "width": src_asset.get("width"),
                    "height": src_asset.get("height"),
                    "duration_s": src_asset.get("duration_s"),
                    "vcodec": src_asset.get("vcodec"),
                    "acodec": src_asset.get("acodec"),
                }
        else:
            effective_probe = out_probe

        for r in reqs:
            lang = await self._lang(r["tg_id"])
            pref = await self._user_pref(r["tg_id"])
            summary = self._summary_text(
                lang, job_id=str(row["id"]), profile=row["profile"], filename=filename,
                source_size=source_size, output_size=out_size or source_size,
                probe=effective_probe,
                started=started, completed=completed,
                new=not row["reuse_of"], no_gain=no_gain,
            )
            if blocked:
                await self.edit_status_sync(
                    r["chat_id"], r["status_message_id"],
                    tr("status_done_blocked", lang,
                       limit=media_mod.human_size(self.cfg.max_upload_bytes)),
                )
                if pref.get("notify_done", True):
                    try:
                        await self.bot.send_message(r["chat_id"], summary)
                    except TelegramAPIError:
                        pass
                continue
            if no_gain:
                # The user already possesses the source they uploaded. If the
                # source itself cannot be re-delivered (above the upload
                # limit), skip the futile upload and just explain.
                if source_size > self.cfg.max_upload_bytes:
                    ok, method, mid = True, "already_have", None
                    await self.edit_status_sync(
                        r["chat_id"], r["status_message_id"],
                        tr("status_done_nogain", lang),
                    )
                else:
                    ok, method, mid = await archive_mod.deliver_result(
                        self,
                        chat_id=r["chat_id"],
                        file_id=src_asset["tg_file_id"] if src_asset else None,
                        file_path=row["source_path"],
                        caption=tr("nogain_notice", lang,
                                   out=media_mod.human_size(out_size),
                                   src=media_mod.human_size(source_size)),
                        as_document=pref.get("delivery_style") == "doc",
                        thumbnail=self._global_thumb(),
                    )
            else:
                if part_ids:
                    all_ok, delivered = await self._deliver_parts(
                        r["chat_id"], part_ids, lang, part_total,
                    )
                    ok, method, mid = all_ok, "parts", None
                elif pref.get("delivery_style") == "doc" and out_asset and out_asset["tg_file_id"]:
                    ok, method, mid = False, "none", None
                    try:
                        msg = await self.bot.send_document(
                            chat_id=r["chat_id"], document=out_asset["tg_file_id"],
                            caption=summary.split("\n")[0],
                        )
                        ok, method, mid = True, "doc_file_id", msg.message_id
                    except TelegramAPIError as exc:
                        log.info("doc delivery failed, falling back",
                                 extra={"detail": str(exc)[:150]})
                    if not ok:
                        ok, method, mid = await self._deliver_archive_to(
                            r["chat_id"], archive_row, pref)
                else:
                    ok, method, mid = await self._deliver_archive_to(
                        r["chat_id"], archive_row, pref)
            if (archive_row and archive_row["message_id"] and ok
                    and method in ("file_id", "upload")):
                await self.db.execute(
                    "UPDATE archive_records SET status='missing' "
                    "WHERE id=$1 AND status='active'",
                    archive_row["id"],
                )
                await self.db.bump("archive_missing_detected")
                await self.notify_admins(
                    tr("archive_missing", await self._lang(r["tg_id"]),
                       archive=str(archive_row["id"])[:8])
                )
                archive_row = None
            await self.db.execute(
                "UPDATE job_requesters SET delivered = TRUE WHERE job_id = $1 AND tg_id = $2",
                row["id"], r["tg_id"],
            )
            await self.db.execute(
                """
                INSERT INTO deliveries(archive_id, job_id, tg_id, chat_id, message_id,
                                       method, status, error)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                """,
                archive_id, row["id"], r["tg_id"], r["chat_id"], mid, method,
                "ok" if ok else "failed", None if ok else "all delivery methods failed",
            )
            await self.db.bump("deliveries_ok" if ok else "deliveries_failed")
            if not pref.get("notify_done", True):
                continue
            if not ok:
                try:
                    await self.bot.edit_message_text(
                        chat_id=r["chat_id"], message_id=r["status_message_id"],
                        text=tr("status_delivery_failed", lang),
                        reply_markup=redeliver_markup(str(row["id"])),
                    )
                    continue
                except TelegramAPIError:
                    pass
            await self.edit_status_sync(r["chat_id"], r["status_message_id"], summary)

    async def _deliver_archive_to(self, chat_id: int, archive_row, pref: dict,
                                  caption: str | None = None) -> tuple[bool, str, int | None]:
        return await archive_mod.deliver_result(
            self,
            chat_id=chat_id,
            archive_message_id=(archive_row["message_id"] if archive_row else 0),
            archive_channel_id=(archive_row["channel_id"] if archive_row else None),
            file_id=(archive_row["output_tg_file_id"] if archive_row and
                     "output_tg_file_id" in archive_row.keys() else None),
            caption=caption,
        )

    async def redeliver(self, job_id: str, chat_id: int, tg_id: int) -> tuple[bool, str]:
        job = await self.db.fetchrow("SELECT * FROM jobs WHERE id = $1", _as_uuid(job_id))
        if not job or job["status"] != "completed":
            return False, "job not completed"
        allowed = await self.db.fetchval(
            "SELECT 1 FROM job_requesters WHERE job_id = $1 AND tg_id = $2",
            _as_uuid(job_id), tg_id,
        )
        if not allowed and tg_id not in await self.admin_ids():
            return False, "not allowed"
        lang = await self._lang(tg_id)
        pref = await self._user_pref(tg_id)
        # Split results: deliver every archived part in order.
        part_rows = await self.db.fetch(
            """
            SELECT ar.id, ar.channel_id, ar.message_id, ar.status
            FROM archive_records ar
            WHERE ar.source_media_id = (SELECT media_id FROM jobs WHERE id = $1)
              AND ar.profile = (SELECT profile FROM jobs WHERE id = $1)
              AND ar.profile_version = 1
              AND ar.status IN ('active', 'no_gain')
            ORDER BY ar.part_index
            """,
            _as_uuid(job_id),
        )
        if len(part_rows) > 1:
            ids = [r["id"] for r in part_rows]
            all_ok, delivered = await self._deliver_parts(chat_id, ids, lang, len(part_rows))
            await self.db.bump("deliveries_ok" if all_ok else "deliveries_failed")
            return all_ok, f"parts:{delivered}"
        archive_row = None
        if job["reuse_of"]:
            archive_row = await self.db.fetchrow(
                "SELECT * FROM archive_records WHERE id = $1", job["reuse_of"]
            )
        elif job["output_media_id"]:
            archive_row = await self.db.fetchrow(
                "SELECT * FROM archive_records WHERE output_media_id = $1 "
                "AND status IN ('active','no_gain') ORDER BY created_at DESC LIMIT 1",
                job["output_media_id"],
            )
        out_asset = await self.db.fetchrow(
            "SELECT tg_file_id FROM media_assets WHERE id = $1", job["output_media_id"]
        ) if job["output_media_id"] else None
        src_asset = await self.db.fetchrow(
            "SELECT tg_file_id FROM media_assets WHERE id = $1", job["media_id"]
        )
        if job["is_no_gain"]:
            ok, method, mid = await archive_mod.deliver_result(
                self,
                chat_id=chat_id,
                file_id=(src_asset["tg_file_id"] if src_asset else None),
                file_path=job["source_path"],
                as_document=pref.get("delivery_style") == "doc",
                thumbnail=self._global_thumb(),
            )
        else:
            ok, method, mid = await self._deliver_archive_to(chat_id, archive_row, pref)
            if not ok and out_asset and out_asset["tg_file_id"]:
                ok, method, mid = await archive_mod.deliver_result(
                    self, chat_id=chat_id,
                    file_id=out_asset["tg_file_id"],
                    as_document=pref.get("delivery_style") == "doc",
                )
        await self.db.execute(
            """
            INSERT INTO deliveries(archive_id, job_id, tg_id, chat_id, message_id,
                                   method, status, error)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            """,
            archive_row["id"] if archive_row else None, job["id"], tg_id, chat_id, mid,
            method, "ok" if ok else "failed", None if ok else "redelivery failed",
        )
        await self.db.bump("deliveries_ok" if ok else "deliveries_failed")
        return ok, method

    # ------------------------------------------------------------------
    # cleanup + recovery
    # ------------------------------------------------------------------
    async def _cleanup_job_dirs(self, job_id: str, keep_output: bool,
                                keep_source: bool = False) -> None:
        def _rm(path: Path) -> None:
            shutil.rmtree(path, ignore_errors=True)

        if not keep_source:
            await asyncio.to_thread(_rm, Path(self.cfg.media_incoming) / job_id)
        if not keep_output:
            await asyncio.to_thread(_rm, Path(self.cfg.media_out) / job_id)
        thumb_path = Path(self.cfg.media_tmp) / f"thumb-{job_id[:12]}.jpg"
        if thumb_path.is_file():
            await asyncio.to_thread(thumb_path.unlink, True)

    async def cleanup_sweep(self) -> None:
        active = await self.db.fetch(
            "SELECT id, media_id FROM jobs WHERE status IN ('queued','processing')"
        )
        active_ids = {str(r["id"]) for r in active}
        active_media = {str(r["media_id"]) for r in active if r["media_id"]}
        cutoff = time.time() - self.cfg.tmp_retention_hours * 3600
        removed = 0
        for base in (self.cfg.media_incoming, self.cfg.media_out,
                     self.cfg.media_tmp, self.cfg.media_test,
                     os.path.join(self.cfg.media_root, "work")):
            root = Path(base)
            if not root.is_dir():
                continue
            for entry in root.iterdir():
                name = entry.name
                if name in active_ids:
                    continue
                if name.startswith("m-") and name[2:] in active_media:
                    continue  # stable media copy still needed by an active job
                try:
                    if entry.stat().st_mtime < cutoff:
                        # rmtree silently no-ops on plain files ??? delete them
                        # explicitly (BUG-002: media/test leaked test files).
                        if entry.is_dir() and not entry.is_symlink():
                            await asyncio.to_thread(shutil.rmtree, entry, ignore_errors=True)
                        else:
                            await asyncio.to_thread(entry.unlink, True)
                        removed += 1
                except OSError:
                    continue
        if removed:
            log.info("cleanup sweep removed dirs", extra={"detail": str(removed)})
        await self.auto_resume_if_ok()

    async def recover_on_startup(self) -> None:
        rows = await self.db.fetch(
            "SELECT id, status, encore_job_id FROM jobs WHERE status IN ('queued','processing')"
        )
        for row in rows:
            log.info("recovering job",
                     extra={"job_id": str(row["id"]), "status": row["status"]})
            if not row["encore_job_id"]:
                self.spawn(self.run_job(str(row["id"])))


def failure_markup(job_id: str, lang: str = "fa") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tr("btn_retry", lang), callback_data=f"rtry:{job_id}"),
         InlineKeyboardButton(text=tr("btn_error_details", lang),
                              callback_data=f"errd:{job_id}")],
    ])


def redeliver_markup(job_id: str, lang: str = "fa") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(
            text=tr("btn_redeliver", lang), callback_data=f"rdl:{job_id}"
        )]]
    )

