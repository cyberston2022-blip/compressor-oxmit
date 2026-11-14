"""Environment-driven settings. All secrets come from the server-side .env file.

Fail-fast: malformed numeric values are collected into _PARSE_ERRORS and
load_settings() refuses to boot on an invalid configuration (F16) instead of
silently running on defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

_PARSE_ERRORS: list[str] = []


def _bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        _PARSE_ERRORS.append(f"{name}: expected integer, got {raw!r}")
        return default


def _float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        _PARSE_ERRORS.append(f"{name}: expected number, got {raw!r}")
        return default


def _csv_ids(name: str) -> list[int]:
    out: list[int] = []
    for part in (os.getenv(name) or "").split(","):
        part = part.strip()
        if part:
            try:
                out.append(int(part))
            except ValueError:
                _PARSE_ERRORS.append(f"{name}: skipped invalid id {part!r}")
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
    # Accepted (persistent) job records waiting for a worker. Queue capacity
    # is metadata only - nothing is downloaded until a worker claims a job.
    max_queued: int = 5000
    disk_min_free_bytes: int = 40 * 1024**3
    disk_pause_free_bytes: int = 20 * 1024**3
    admission_floor_bytes: int = 5 * 1024**3
    job_retries: int = 2
    stuck_minutes: int = 90
    tuner_active_window_s: int = 180
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

    # Cache offers: when a compressed version of the source already exists,
    # ask the user (send existing / lower profile / cancel) instead of
    # silently reusing the archive. False restores the old silent behavior.
    cache_offer: bool = True

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

    # Master Performance & Compression Optimization flags
    adaptive_codec_enabled: bool = True
    adaptive_resolution_enabled: bool = True
    fastpath_copy_enabled: bool = True
    audio_copy_enabled: bool = True
    custom_encoding_mode: str = "adaptive"
    ffmpeg_threads_single: int = 6
    ffmpeg_threads_multi: int = 3
    target_accuracy_tolerance_pct: float = 2.0

    internal_secret: str = ""
    internal_test_token: str = ""
    internal_panel_token: str = ""
    enable_test_api: bool = False
    enable_test_api_requested: bool = False
    redis_url: str = "redis://redis:6379"
    owner_telegram_id: int = 0
    owner_only: bool = False
    panel_public_url: str = ""
    owner_claim: bool = True

    # ---- JIT queue / dispatcher ----
    # Concurrent encode slots (defaults to WORKER_REPLICAS). A slot is held
    # from claim (download) until the encode finishes; upload/delivery run
    # outside the slot so the encoder never idles while Telegram uploads.
    encode_slots: int = 0
    # Extra jobs that may be claimed (downloaded) ahead of a free encoder to
    # overlap download with encoding. 0 = strict just-in-time download.
    prefetch_jobs: int = 0
    lease_minutes: int = 20
    upload_retries: int = 5
    # Delete the Local Bot API copy of a source once no active job needs it.
    delete_botapi_source: bool = True
    # The telegram-bot-api container mounts /media read-only: outputs are
    # uploaded with file:// (no multipart copy through the HTTP socket).
    botapi_reads_media: bool = False
    # Private moderation/activity channel; empty = the archive channel.
    log_channel_id: int | None = None
    naming_timeout_min: int = 30
    support_session_min: int = 10

    # ---- EDU480 (the single active compression profile) ----
    # CRF 28 veryfast is the 2026-11-14 benchmark winner on real owner
    # sources: -26% size vs CRF 25 at identical encode speed (SSIM -0.005);
    # slower presets bought no size on lecture content and cost 25-40% CPU.
    edu480_crf: int = 28
    edu480_preset: str = "veryfast"
    edu480_scale_flags: str = "lanczos"
    edu480_max_fps: float = 30.0
    edu480_audio_kbps: int = 64
    # Predictive no-gain guard (deterministic bpp model, V3 §16): when the
    # low edge of the predicted EDU480 output reaches this fraction of the
    # source, the pipeline delivers the source instead of encoding. It is a
    # GUARD only — it can only skip encodes that the model is confident are
    # useless, never reject useful ones (cold-start safe). v2: calibrated
    # bpp (see estimate.py) and never fires when a real downscale happens.
    encode_predict_guard: bool = True
    predict_no_gain_ratio: float = 0.98
    # bpp at CRF 23 for the size model. Calibrated 2026-11-14 from 15 real
    # production encodes (0.036 bpp measured at CRF 25) + benchmarks; set to
    # the measured high edge so the guard stays conservative.
    estimate_bpp_h264: float = 0.055
    # Sources already <=480p, H.264 + AAC, <= this video bitrate and <= the
    # fps cap are compliant: they are remuxed (stream copy), not re-encoded.
    edu480_compliant_kbps: int = 700

    @property
    def slots(self) -> int:
        return max(1, self.encode_slots or self.worker_replicas)

    def tier_defaults(self) -> dict:
        """Initial per-tier limits (env-overridable); the admin panel edits
        the persisted copy in app_config afterwards."""
        return {
            "normal": {
                "max_source_gb": _int("NORMAL_MAX_SOURCE_GB", _int("MAX_SOURCE_GB", 4)),
                "max_duration_min": _int("NORMAL_MAX_DURATION_MIN", 360),
                "daily_quota_gb": _int("NORMAL_DAILY_QUOTA_GB", 5),
                "max_active": _int("MAX_ACTIVE_PER_USER", 1),
                "max_pending": _int("MAX_PENDING_PER_USER", 10),
                "max_per_hour": _int("MAX_JOBS_PER_HOUR_PER_USER", 10),
            },
            "vip": {
                "max_source_gb": _int("VIP_MAX_SOURCE_GB", 4),
                "max_duration_min": _int("VIP_MAX_DURATION_MIN", 720),
                "daily_quota_gb": _int("VIP_DAILY_QUOTA_GB", 20),
                "max_active": _int("VIP_MAX_ACTIVE_PER_USER", 2),
                "max_pending": _int("VIP_MAX_PENDING_PER_USER", 30),
                "max_per_hour": _int("VIP_MAX_JOBS_PER_HOUR_PER_USER", 30),
            },
        }

    def validate(self) -> list[str]:
        """Return a list of configuration problems (empty = OK). load_settings()
        refuses to boot on a non-empty list unless OXMIT_SKIP_VALIDATION=1."""
        errs = list(_PARSE_ERRORS)
        if "REPLACE_ME" in self.bot_token or self.bot_token.startswith("123456789:"):
            errs.append("BOT_TOKEN still contains the placeholder — set a real token")
        if not self.pg_dsn:
            errs.append("PG_DSN is required (PostgreSQL connection string)")
        if not self.internal_secret:
            errs.append("INTERNAL_SECRET is required (random string, internal API auth)")
        if self.enable_test_api_requested and not self.enable_test_api:
            errs.append("ENABLE_TEST_API=true is ignored because ENABLE_TEST_API_CONFIRM "
                        "is not set to I-UNDERSTAND-THIS-IS-PROD — set it or remove "
                        "ENABLE_TEST_API")
        if not 1 <= self.worker_replicas <= 16:
            errs.append(f"WORKER_REPLICAS={self.worker_replicas} outside 1..16")
        if len(self.worker_container_names) != self.worker_replicas:
            errs.append(
                f"WORKER_CONTAINER_NAMES has {len(self.worker_container_names)} entries "
                f"but WORKER_REPLICAS={self.worker_replicas} — the CPU tuner must match compose")
        if self.disk_pause_free_bytes >= self.disk_min_free_bytes:
            errs.append(
                f"DISK_PAUSE_FREE_GB ({self.disk_pause_free_bytes // 1024**3}) must be "
                f"smaller than DISK_MIN_FREE_GB ({self.disk_min_free_bytes // 1024**3}) "
                "— otherwise the disk gate locks permanently (pause low < resume high)")
        if self.admission_floor_bytes < 1024**3:
            errs.append("ADMISSION_FLOOR_GB must be >= 1 GiB")
        if not 30 <= self.tuner_active_window_s <= 3600:
            errs.append(f"TUNER_ACTIVE_WINDOW_S={self.tuner_active_window_s} outside 30..3600")
        if not 0.5 <= self.split_safety <= 1.0:
            errs.append(f"SPLIT_SAFETY={self.split_safety} outside 0.5..1.0")
        if not 0.5 <= self.no_gain_threshold <= 1.2:
            errs.append(f"NO_GAIN_THRESHOLD={self.no_gain_threshold} outside 0.5..1.2")
        if not (self.worker_cpu_min <= self.worker_cpu_multi <= self.worker_cpu_single):
            errs.append(
                f"worker CPU tiers must satisfy WORKER_CPU_MIN ({self.worker_cpu_min}) "
                f"<= WORKER_CPU_MULTI ({self.worker_cpu_multi}) <= "
                f"WORKER_CPU_SINGLE ({self.worker_cpu_single})")
        if self.target_min_mb >= self.target_max_gb * 1024:
            errs.append(
                f"TARGET_MIN_MB ({self.target_min_mb}) must be smaller than "
                f"TARGET_MAX_GB*1024 ({self.target_max_gb * 1024})")
        for name, val in (("MAX_ACTIVE_PER_USER", self.max_active_per_user),
                          ("MAX_JOBS_PER_HOUR_PER_USER", self.max_jobs_per_hour),
                          ("MAX_JOBS_PER_DAY", self.max_jobs_per_day),
                          ("MAX_QUEUED_JOBS", self.max_queued),
                          ("MAX_CONCURRENT_UPLOADS", self.max_concurrent_uploads),
                          ("STUCK_MINUTES", self.stuck_minutes)):
            if val < 1:
                errs.append(f"{name}={val} must be >= 1")
        if self.job_retries < 0:
            errs.append(f"JOB_RETRIES={self.job_retries} must be >= 0")
        # Ranges that previously slipped through: zero/negative values here
        # silently disable or break the mechanisms they feed.
        if self.admission_need_factor <= 0:
            errs.append(f"ADMISSION_NEED_FACTOR={self.admission_need_factor} must be > 0 "
                        "(<= 0 lets disk admission overcommit indefinitely)")
        if self.progress_edit_seconds < 1:
            errs.append(f"PROGRESS_EDIT_SECONDS={self.progress_edit_seconds} must be >= 1 "
                        "(< 1 floods Telegram with edits on every poll)")
        if self.max_upload_bytes <= 0:
            errs.append(f"MAX_UPLOAD_MB={self.max_upload_bytes // 1024 // 1024} must be > 0")
        if self.min_video_kbps <= 0:
            errs.append(f"MIN_VIDEO_KBPS={self.min_video_kbps} must be > 0")
        if self.tmp_retention_hours < 1:
            errs.append(f"TMP_RETENTION_HOURS={self.tmp_retention_hours} must be >= 1")
        if self.sim_duration_tol < 0:
            errs.append(f"SIMILARITY_DURATION_TOL_S={self.sim_duration_tol} must be >= 0")
        if self.segment_min_duration < 0:
            errs.append(f"SEGMENT_MIN_DURATION={self.segment_min_duration} must be >= 0")
        if self.max_source_bytes <= 0:
            errs.append(f"MAX_SOURCE_GB={self.max_source_bytes // 1024**3} must be > 0")
        if self.segment_enabled and self.segment_length <= 0:
            errs.append("SEGMENT_LENGTH must be > 0 when SEGMENT_ENABLED=true")
        if not 1 <= self.ffmpeg_threads_single <= 32:
            errs.append(f"FFMPEG_THREADS_SINGLE={self.ffmpeg_threads_single} outside 1..32")
        if not 1 <= self.ffmpeg_threads_multi <= 32:
            errs.append(f"FFMPEG_THREADS_MULTI={self.ffmpeg_threads_multi} outside 1..32")
        if self.custom_encoding_mode not in ("adaptive", "one_pass", "two_pass"):
            errs.append(f"CUSTOM_ENCODING_MODE={self.custom_encoding_mode} must be adaptive, one_pass, or two_pass")
        if not 0 <= self.prefetch_jobs <= 8:
            errs.append(f"PREFETCH_JOBS={self.prefetch_jobs} outside 0..8")
        if not 0 <= self.encode_slots <= 32:
            errs.append(f"ENCODE_SLOTS={self.encode_slots} outside 0..32")
        if not 18 <= self.edu480_crf <= 35:
            errs.append(f"EDU480_CRF={self.edu480_crf} outside 18..35")
        if not 0.005 <= self.estimate_bpp_h264 <= 0.30:
            errs.append(f"ESTIMATE_BPP_H264={self.estimate_bpp_h264} outside 0.005..0.30")
        if not 0.5 <= self.predict_no_gain_ratio <= 1.2:
            errs.append(f"PREDICT_NO_GAIN_RATIO={self.predict_no_gain_ratio} outside 0.5..1.2")
        if self.edu480_preset not in ("ultrafast", "superfast", "veryfast", "faster",
                                      "fast", "medium"):
            errs.append(f"EDU480_PRESET={self.edu480_preset} is not an x264 preset")
        if self.edu480_scale_flags not in ("lanczos", "bicubic", "bilinear", "fast_bilinear"):
            errs.append(f"EDU480_SCALE_FLAGS={self.edu480_scale_flags} is not a valid scaling filter")
        if not 10 <= self.edu480_max_fps <= 60:
            errs.append(f"EDU480_MAX_FPS={self.edu480_max_fps} outside 10..60")
        if self.lease_minutes < 5:
            errs.append(f"LEASE_MINUTES={self.lease_minutes} must be >= 5")
        return errs

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

    @property
    def media_watermarks(self) -> str:
        return os.path.join(self.media_root, "watermarks")


def load_settings() -> Settings:
    _PARSE_ERRORS.clear()  # repeated loads (tests/tools) must not see stale errors
    s = Settings()
    s.bot_token = os.getenv("BOT_TOKEN", "").strip()
    s.api_id = _int("TELEGRAM_API_ID", 0)
    s.api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    s.admin_ids = _csv_ids("ADMIN_TELEGRAM_IDS")
    ch = os.getenv("ARCHIVE_CHANNEL_ID", "").strip()
    if ch:
        try:
            s.archive_channel_id = int(ch)
        except ValueError:
            _PARSE_ERRORS.append(f"ARCHIVE_CHANNEL_ID: expected integer, got {ch!r}")

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
    s.max_queued = _int("MAX_QUEUED_JOBS", 5000)
    s.disk_min_free_bytes = _int("DISK_MIN_FREE_GB", 40) * 1024**3
    s.disk_pause_free_bytes = _int("DISK_PAUSE_FREE_GB", 20) * 1024**3
    s.admission_floor_bytes = _int("ADMISSION_FLOOR_GB", 5) * 1024**3
    s.job_retries = _int("JOB_RETRIES", 2)
    s.stuck_minutes = _int("STUCK_MINUTES", 90)
    s.tuner_active_window_s = _int("TUNER_ACTIVE_WINDOW_S", 180)
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
    s.cache_offer = _bool("CACHE_OFFER", True)

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

    # Performance & Optimization Settings
    s.adaptive_codec_enabled = _bool("ADAPTIVE_CODEC_ENABLED", True)
    s.adaptive_resolution_enabled = _bool("ADAPTIVE_RESOLUTION_ENABLED", True)
    s.fastpath_copy_enabled = _bool("FASTPATH_COPY_ENABLED", True)
    s.audio_copy_enabled = _bool("AUDIO_COPY_ENABLED", True)
    s.custom_encoding_mode = os.getenv("CUSTOM_ENCODING_MODE", "adaptive").strip().lower()
    s.ffmpeg_threads_single = _int("FFMPEG_THREADS_SINGLE", 6)
    s.ffmpeg_threads_multi = _int("FFMPEG_THREADS_MULTI", 3)
    s.target_accuracy_tolerance_pct = _float("TARGET_ACCURACY_TOLERANCE_PCT", 2.0)

    s.internal_secret = os.getenv("INTERNAL_SECRET", "")
    s.internal_test_token = os.getenv("INTERNAL_TEST_TOKEN", "")
    s.internal_panel_token = os.getenv("ADMIN_PANEL_TOKEN", "")
    s.enable_test_api_requested = _bool("ENABLE_TEST_API", False)
    # Double gate: ENABLE_TEST_API alone never enables the test routes — the
    # operator must confirm with the explicit sentinel (SEC-4).
    s.enable_test_api = s.enable_test_api_requested and (
        os.getenv("ENABLE_TEST_API_CONFIRM", "").strip() == "I-UNDERSTAND-THIS-IS-PROD")
    s.redis_url = os.getenv("REDIS_URL", s.redis_url).rstrip("/")
    s.owner_telegram_id = _int("OWNER_TELEGRAM_ID", 0)
    s.owner_only = _bool("OWNER_ONLY", False)
    s.panel_public_url = os.getenv("PANEL_PUBLIC_URL", "").strip().rstrip("/")
    s.owner_claim = _bool("OWNER_CLAIM", True)

    s.encode_slots = _int("ENCODE_SLOTS", 0)
    s.prefetch_jobs = _int("PREFETCH_JOBS", 0)
    s.lease_minutes = _int("LEASE_MINUTES", 20)
    s.upload_retries = _int("UPLOAD_RETRIES", 5)
    s.delete_botapi_source = _bool("DELETE_BOTAPI_SOURCE", True)
    s.botapi_reads_media = _bool("BOTAPI_READS_MEDIA", False)
    lc = os.getenv("LOG_CHANNEL_ID", "").strip()
    if lc:
        try:
            s.log_channel_id = int(lc)
        except ValueError:
            _PARSE_ERRORS.append(f"LOG_CHANNEL_ID: expected integer, got {lc!r}")
    s.naming_timeout_min = _int("NAMING_TIMEOUT_MIN", 30)
    s.support_session_min = _int("SUPPORT_SESSION_MIN", 10)
    s.edu480_crf = _int("EDU480_CRF", 28)
    s.edu480_preset = os.getenv("EDU480_PRESET", "veryfast").strip().lower()
    s.edu480_scale_flags = os.getenv("EDU480_SCALE_FLAGS", "lanczos").strip().lower()
    s.edu480_max_fps = _float("EDU480_MAX_FPS", 30.0)
    s.edu480_audio_kbps = _int("EDU480_AUDIO_KBPS", 64)
    s.edu480_compliant_kbps = _int("EDU480_COMPLIANT_KBPS", 700)
    s.encode_predict_guard = _bool("ENCODE_PREDICT_GUARD", True)
    s.predict_no_gain_ratio = _float("PREDICT_NO_GAIN_RATIO", 0.98)
    s.estimate_bpp_h264 = _float("ESTIMATE_BPP_H264", 0.055)

    errs = s.validate()
    if os.getenv("OXMIT_SKIP_VALIDATION", "") != "1" and errs:
        raise RuntimeError("Invalid configuration:\n- " + "\n- ".join(errs))
    return s
