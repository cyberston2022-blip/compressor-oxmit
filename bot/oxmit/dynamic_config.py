"""Dynamic Runtime Configuration Engine for Oxmit.

Provides instant hot-reloading of system parameters without restarting services.
Stores configuration in PostgreSQL (system_settings) with in-memory caching and
pub/sub or callback notification on modifications.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

from .log import get_logger

log = get_logger("oxmit.dynamic_config")

DEFAULT_SETTINGS: dict[str, dict[str, Any]] = {
    "accepting_new_jobs": {
        "val": True,
        "type": "bool",
        "title": "وضعیت پذیرش ویدیوی جدید",
        "desc": "روشن/خاموش کردن دریافت فایل جدید توسط ربات",
    },
    "max_global_queue_size": {
        "val": 500,
        "type": "int",
        "title": "حداکثر ظرفیت کل صف انتظار",
        "desc": "ظرفیت کل صف انتظار پردازش",
    },
    "max_concurrent_jobs_per_user": {
        "val": 3,
        "type": "int",
        "title": "سقف مجاز ویدیوی همزمان هر کاربر",
        "desc": "حداکثر تعداد کارهای در حال انتظار یا پردازش یک کاربر عادی",
    },
    "max_concurrent_jobs_vip": {
        "val": 10,
        "type": "int",
        "title": "سقف مجاز ویدیوی کاربران ویژه (VIP)",
        "desc": "سقف اختصاصی صف برای کاربران دارای وضعیت ویژه",
    },
    "max_file_size_mb": {
        "val": 2000,
        "type": "int",
        "title": "حداکثر حجم مجاز فایل ورودی (MB)",
        "desc": "حداکثر حجم فایل ویدیویی ارسالی مجاز",
    },
    "active_encoding_workers": {
        "val": 2,
        "type": "int",
        "title": "تعداد ورکرهای همزمان انکودینگ",
        "desc": "تعداد تسک‌های همزمان انکودینگ ویدیو (مقیاس‌پذیری پویا)",
    },
    "active_download_workers": {
        "val": 4,
        "type": "int",
        "title": "تعداد دانلودهای همزمان از تلگرام",
        "desc": "حداکثر دانلودهای همزمان فایل از سرور تلگرام",
    },
    "active_upload_workers": {
        "val": 4,
        "type": "int",
        "title": "تعداد آپلودهای همزمان به تلگرام",
        "desc": "حداکثر آپلودهای همزمان فایل به سرور تلگرام",
    },
    "ffmpeg_threads_per_worker": {
        "val": 0,
        "type": "int",
        "title": "تعداد هسته CPU برای هر ورکر FFmpeg",
        "desc": "تعداد هسته اختصاصی پردازش هر ورکر (0 = خودکار)",
    },
    "queue_scheduling_mode": {
        "val": "fair_round_robin",
        "type": "string",
        "title": "الگوریتم عدالت و زمان‌بندی صف",
        "desc": "الگوریتم زمان‌بندی صف (fair_round_robin, strict_fifo, weighted_fair, size_aware_fair)",
    },
    "wfq_time_penalty_seconds": {
        "val": 300,
        "type": "int",
        "title": "جریمه زمانی هر ویدیوی اضافه در صف (ثانیه)",
        "desc": "جریمه زمانی مجازی برای الگوریتم WFQ",
    },
    "admin_queue_bypass": {
        "val": False,
        "type": "bool",
        "title": "اولویت ویژه ادمین‌ها در صف",
        "desc": "بای‌پس صف برای ادمین‌ها (پیش‌فرض خاموش جهت عدالت و تست صف)",
    },
    "progress_update_interval_sec": {
        "val": 4,
        "type": "int",
        "title": "بازه آپدیت پیام پیشرفت تلگرام (ثانیه)",
        "desc": "فاصله زمانی بین ویرایش پیام‌های پیشرفت در تلگرام",
    },
    "progress_bar_length": {
        "val": 12,
        "type": "int",
        "title": "تعداد خانه‌های نوار پیشرفت",
        "desc": "تعداد کاراکترهای نوار پیشرفت گرافیکی",
    },
    "auto_retry_failed_jobs": {
        "val": 1,
        "type": "int",
        "title": "تعداد تلاش مجدد خودکار هنگام خطا",
        "desc": "تعداد دفعات تلاش مجدد خودکار در صورت بروز خطای موقت",
    },
}


class DynamicConfig:
    """Manages live dynamic settings with DB sync, memory cache, and hot-reload."""

    def __init__(self, db: Any) -> None:
        self.db = db
        self._cache: dict[str, Any] = {}
        self._meta: dict[str, dict[str, Any]] = {}
        self._listeners: list[Callable[[str, Any], Any]] = []

    async def init(self) -> None:
        """Load settings from DB and initialize defaults if missing."""
        # Populate defaults into cache first
        for k, info in DEFAULT_SETTINGS.items():
            self._cache[k] = info["val"]
            self._meta[k] = {
                "type": info["type"],
                "title_fa": info["title"],
                "desc_fa": info["desc"],
                "updated_at": datetime.now(timezone.utc),
            }

        try:
            rows = await self.db.fetch("SELECT key, value, value_type, title_fa, description_fa, updated_at FROM system_settings")
            for r in rows:
                k = r["key"]
                val = r["value"]
                # In asyncpg JSONB can be string or parsed python object
                if isinstance(val, str):
                    try:
                        val = json.loads(val)
                    except Exception:
                        pass
                self._cache[k] = val
                self._meta[k] = {
                    "type": r["value_type"],
                    "title_fa": r["title_fa"],
                    "desc_fa": r["description_fa"],
                    "updated_at": r["updated_at"],
                }
            log.info("dynamic config initialized with %d settings", len(self._cache))
        except Exception as exc:
            log.warning("failed to fetch system_settings, using defaults: %s", exc)

    def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        v = self._cache.get(key)
        if v is None:
            return default
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)

    def get_int(self, key: str, default: int = 0) -> int:
        v = self._cache.get(key)
        if v is None:
            return default
        try:
            return int(v)
        except (ValueError, TypeError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        v = self._cache.get(key)
        if v is None:
            return default
        try:
            return float(v)
        except (ValueError, TypeError):
            return default

    def get_str(self, key: str, default: str = "") -> str:
        v = self._cache.get(key)
        if v is None:
            return default
        return str(v)

    def get_all(self) -> list[dict[str, Any]]:
        """Return all settings formatted for the Web Panel."""
        items = []
        for k, val in self._cache.items():
            meta = self._meta.get(k, {})
            items.append({
                "key": k,
                "value": val,
                "type": meta.get("type", "string"),
                "title_fa": meta.get("title_fa", k),
                "description_fa": meta.get("desc_fa", ""),
                "updated_at": meta.get("updated_at", "").isoformat() if hasattr(meta.get("updated_at"), "isoformat") else str(meta.get("updated_at", "")),
            })
        return sorted(items, key=lambda x: x["key"])

    async def set(self, key: str, value: Any, admin_tg_id: int | None = None) -> None:
        """Update a setting in PostgreSQL and update local cache."""
        meta = DEFAULT_SETTINGS.get(key, {})
        val_type = meta.get("type", "string")

        # Cast to proper type
        if val_type == "bool":
            if isinstance(value, str):
                typed_val = value.lower() in ("true", "1", "yes", "on")
            else:
                typed_val = bool(value)
        elif val_type == "int":
            typed_val = int(value)
        elif val_type == "float":
            typed_val = float(value)
        else:
            typed_val = str(value)

        json_val = json.dumps(typed_val)
        await self.db.execute(
            """
            INSERT INTO system_settings(key, value, value_type, title_fa, description_fa, updated_at)
            VALUES($1, $2::jsonb, $3, $4, $5, now())
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = now()
            """,
            key,
            json_val,
            val_type,
            meta.get("title", key),
            meta.get("desc", ""),
        )

        self._cache[key] = typed_val
        if key in self._meta:
            self._meta[key]["updated_at"] = datetime.now(timezone.utc)

        log.info("setting '%s' updated to %r by %s", key, typed_val, admin_tg_id)

        # Notify any subscribed listeners (e.g. worker pool scaler)
        for listener in self._listeners:
            try:
                res = listener(key, typed_val)
                if hasattr(res, "__await__"):
                    await res
            except Exception as exc:
                log.warning("setting change listener error: %s", exc)

    def subscribe(self, callback: Callable[[str, Any], Any]) -> None:
        """Subscribe to live settings changes."""
        self._listeners.append(callback)
