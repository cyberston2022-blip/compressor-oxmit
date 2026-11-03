"""Environment-driven settings. All secrets come from the server-side .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


def _csv_ids(name: str) -> list[int]:
    out: list[int] = []
    for part in (os.getenv(name) or "").split(","):
        part = part.strip()
        if part:
            try:
                out.append(int(part))
            except ValueError:
                continue
    return out


@dataclass
class Settings:
    bot_token: str = ""
    api_id: int = 0
    api_hash: str = ""
    admin_ids: list[int] = field(default_factory=list)
    archive_channel_id: int | None = None

    local_bot_api_base: str = "http://telegram-bot-api:8081"
    max_upload_bytes: int = 2000 * 1024 * 1024

    encre_base: str = "http://encore-web:8080"
    encre_user: str = "bot"
    encre_password: str = ""

    pg_dsn: str = ""
    media_root: str = "/media"
    botapi_dir: str = "/var/lib/telegram-bot-api"

    max_source_bytes: int = 4 * 1024**3
    max_active_per_user: int = 2
    max_jobs_per_hour: int = 10
    max_queued: int = 50
    disk_min_free_bytes: int = 40 * 1024**3
    disk_pause_free_bytes: int = 20 * 1024**3
    job_retries: int = 2
    stuck_minutes: int = 90
    tmp_retention_hours: int = 24
    worker_replicas: int = 2
    worker_cpu_single: float = 7.0
    worker_cpu_multi: float = 3.2
    worker_cpu_min: float = 2.0
    worker_container_names: tuple[str, ...] = ("oxmit-encore-worker-1", "oxmit-encore-worker-2")
    docker_socket: str = "/var/run/docker.sock"

    similarity_reuse: bool = True
    sim_mean_max: int = 5
    sim_max_single: int = 12
    sim_duration_tol: float = 2.0

    max_jobs_per_day: int = 30
    target_min_mb: int = 5
    target_max_gb: int = 8
    min_video_kbps: int = 200
    progress_edit_seconds: int = 4
    split_upload: bool = True
    split_safety: float = 0.85
    segment_enabled: bool = False
    segment_min_duration: float = 900.0
    segment_length: float = 10.0
    workers_read_botapi: bool = False
    no_gain_threshold: float = 0.98
    max_concurrent_uploads: int = 2
    disk_defer: bool = True
    admission_need_factor: float = 2.2

    internal_secret: str = ""
    internal_test_token: str = ""
    internal_panel_token: str = ""
    enable_test_api: bool = False
    redis_url: str = "redis://redis:6379"
    owner_telegram_id: int = 0
    panel_public_url: str = ""
    owner_claim: bool = True

    def tier_defaults(self) -> dict:
        """Initial per-tier limits (env-overridable); the admin panel edits
        the persisted copy in app_config afterwards."""
        return {
            "normal": {
                "max_source_gb": _int("NORMAL_MAX_SOURCE_GB", _int("MAX_SOURCE_GB", 4)),
                "max_duration_min": _int("NORMAL_MAX_DURATION_MIN", 120),
                "daily_quota_gb": _int("NORMAL_DAILY_QUOTA_GB", 5),
                "max_active": _int("MAX_ACTIVE_PER_USER", 2),
                "max_per_hour": _int("MAX_JOBS_PER_HOUR_PER_USER", 10),
            },
            "vip": {
                "max_source_gb": _int("VIP_MAX_SOURCE_GB", 4),
                "max_duration_min": _int("VIP_MAX_DURATION_MIN", 360),
                "daily_quota_gb": _int("VIP_DAILY_QUOTA_GB", 20),
                "max_active": _int("VIP_MAX_ACTIVE_PER_USER", 4),
                "max_per_hour": _int("VIP_MAX_JOBS_PER_HOUR_PER_USER", 30),
            },
        }

    @property
    def media_incoming(self) -> str:
        return os.path.join(self.media_root, "incoming")

    @property
    def media_out(self) -> str:
        return os.path.join(self.media_root, "out")

    @property
    def media_tmp(self) -> str:
        return os.path.join(self.media_root, "tmp")

    @property
    def media_test(self) -> str:
        return os.path.join(self.media_root, "test")

    @property
    def media_thumbs(self) -> str:
        return os.path.join(self.media_root, "thumbs")


def load_settings() -> Settings:
    s = Settings()
    s.bot_token = os.getenv("BOT_TOKEN", "").strip()
    s.api_id = _int("TELEGRAM_API_ID", 0)
    s.api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    s.admin_ids = _csv_ids("ADMIN_TELEGRAM_IDS")
    ch = os.getenv("ARCHIVE_CHANNEL_ID", "").strip()
    s.archive_channel_id = int(ch) if ch else None

    s.local_bot_api_base = os.getenv("LOCAL_BOT_API_BASE", s.local_bot_api_base).rstrip("/")
    s.max_upload_bytes = _int("MAX_UPLOAD_MB", 2000) * 1024 * 1024

    s.encre_base = os.getenv("ENCRE_BASE", s.encre_base).rstrip("/")
    s.encre_user = os.getenv("ENCRE_USER", s.encre_user)
    s.encre_password = os.getenv("ENCRE_PASSWORD", "")

    s.pg_dsn = os.getenv("PG_DSN", "").strip()
    s.media_root = os.getenv("MEDIA_ROOT", s.media_root)
    s.botapi_dir = os.getenv("BOTAPI_DIR", s.botapi_dir)

    s.max_source_bytes = _int("MAX_SOURCE_GB", 4) * 1024**3
    s.max_active_per_user = _int("MAX_ACTIVE_PER_USER", 2)
    s.max_jobs_per_hour = _int("MAX_JOBS_PER_HOUR_PER_USER", 10)
    s.max_queued = _int("MAX_QUEUED_JOBS", 50)
    s.disk_min_free_bytes = _int("DISK_MIN_FREE_GB", 40) * 1024**3
    s.disk_pause_free_bytes = _int("DISK_PAUSE_FREE_GB", 20) * 1024**3
    s.job_retries = _int("JOB_RETRIES", 2)
    s.stuck_minutes = _int("STUCK_MINUTES", 90)
    s.tmp_retention_hours = _int("TMP_RETENTION_HOURS", 24)
    s.worker_replicas = _int("WORKER_REPLICAS", 2)
    s.worker_cpu_single = _float("WORKER_CPU_SINGLE", 7.0)
    s.worker_cpu_multi = _float("WORKER_CPU_MULTI", 3.2)
    s.worker_cpu_min = _float("WORKER_CPU_MIN", 2.0)
    s.worker_container_names = tuple(
        n.strip() for n in os.getenv(
            "WORKER_CONTAINER_NAMES",
            "oxmit-encore-worker-1,oxmit-encore-worker-2").split(",") if n.strip())
    s.docker_socket = os.getenv("DOCKER_SOCKET", "/var/run/docker.sock")

    s.similarity_reuse = _bool("SIMILARITY_REUSE", True)
    s.sim_mean_max = _int("SIMILARITY_MEAN_MAX", 5)
    s.sim_max_single = _int("SIMILARITY_MAX_SINGLE", 12)
    s.sim_duration_tol = _float("SIMILARITY_DURATION_TOL_S", 2.0)

    s.max_jobs_per_day = _int("MAX_JOBS_PER_DAY", 30)
    s.target_min_mb = _int("TARGET_MIN_MB", 5)
    s.target_max_gb = _int("TARGET_MAX_GB", 8)
    s.min_video_kbps = _int("MIN_VIDEO_KBPS", 200)
    s.progress_edit_seconds = _int("PROGRESS_EDIT_SECONDS", 4)
    s.split_upload = _bool("SPLIT_UPLOAD", True)
    s.split_safety = _float("SPLIT_SAFETY", 0.85)
    s.segment_enabled = _bool("SEGMENT_ENABLED", False)
    s.segment_min_duration = _float("SEGMENT_MIN_DURATION", 900.0)
    s.segment_length = _float("SEGMENT_LENGTH", 10.0)
    s.workers_read_botapi = _bool("WORKERS_READ_BOTAPI", False)
    s.no_gain_threshold = _float("NO_GAIN_THRESHOLD", 0.98)
    s.max_concurrent_uploads = _int("MAX_CONCURRENT_UPLOADS", 2)
    s.disk_defer = _bool("DISK_DEFER", True)
    s.admission_need_factor = _float("ADMISSION_NEED_FACTOR", 2.2)

    s.internal_secret = os.getenv("INTERNAL_SECRET", "")
    s.internal_test_token = os.getenv("INTERNAL_TEST_TOKEN", "")
    s.internal_panel_token = os.getenv("ADMIN_PANEL_TOKEN", "")
    s.enable_test_api = _bool("ENABLE_TEST_API", False)
    s.redis_url = os.getenv("REDIS_URL", s.redis_url).rstrip("/")
    s.owner_telegram_id = _int("OWNER_TELEGRAM_ID", 0)
    s.panel_public_url = os.getenv("PANEL_PUBLIC_URL", "").strip().rstrip("/")
    s.owner_claim = _bool("OWNER_CLAIM", True)
    return s
