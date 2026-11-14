"""Structured JSON logging on stdout. Secrets are never logged."""

from __future__ import annotations

import collections
import json
import logging
import sys
import time

EXTRA_KEYS = (
    "job_id",
    "user_id",
    "media_id",
    "encore_job",
    "event",
    "detail",
    "profile",
    "status",
    "duration_ms",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in EXTRA_KEYS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    root.addHandler(_RING)
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


def get_logger(name: str = "oxmit") -> logging.Logger:
    return logging.getLogger(name)


class RingBufferHandler(logging.Handler):
    """In-process bounded tail of the bot's own structured logs.

    Powering the panel's logs explorer (V3 §10.7, lite version): no Docker
    access, no growth risk (deque maxlen), entries already redacted at the
    source. Worker / Encore / PostgreSQL logs live in other containers and
    are NOT captured here — that limitation is documented, not hidden.
    """

    def __init__(self, maxlen: int = 2000):
        super().__init__(level=logging.DEBUG)
        self.buf: collections.deque = collections.deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
            }
            for key in ("job_id", "user_id", "encore_job"):
                value = getattr(record, key, None)
                if value is not None:
                    entry[key] = value
            self.buf.append(entry)
        except Exception:  # noqa: BLE001 — logging must never raise
            pass


_RING = RingBufferHandler()


def recent_logs() -> list[dict]:
    """Newest-last snapshot of the in-process log ring buffer."""
    return list(_RING.buf)
