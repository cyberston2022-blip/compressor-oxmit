"""Deterministic output-size and encode-time estimates.

Independent implementation of the public bits-per-pixel size heuristics for
x264/x265 (the bpp-vs-CRF rule of thumb: ~0.12 bpp at CRF 23, ~-13% per CRF
point; codec/preset factors from public encoder benchmarks). Returns a
(low, high) range so the UI can honestly present it as an estimate.

Pure helpers - no I/O. Every public function is total: it never raises and
always returns a well-formed (low, high) with low <= high, or (0, 0).
"""
from __future__ import annotations

import math

_PIXELS_1080P = 1920.0 * 1080.0
_ASSUMED_FPS = 30.0

_SIZE_LOW, _SIZE_HIGH = 0.7, 1.4
_SIZE_FLOOR_RATIO, _SIZE_CEIL_RATIO = 0.04, 3.0
_MIN_SIZE_BYTES = 40 * 1024

_TIME_LOW, _TIME_HIGH = 0.5, 2.0
_TIME_MIN, _TIME_MAX = 5, 6 * 3600

_CODEC_BPP = {"h264": 1.0, "x264": 1.0, "hevc": 0.55, "h265": 0.55, "x265": 0.55}
_CODEC_TIME = {"h264": 1.0, "x264": 1.0, "hevc": 2.5, "h265": 2.5, "x265": 2.5}
_PRESET_TIME = {"ultrafast": 6.0, "superfast": 4.5, "veryfast": 3.5,
                "faster": 2.6, "fast": 2.0, "medium": 1.0, "slow": 0.6}


def _duration(value) -> float | None:
    try:
        d = float(value)
    except (TypeError, ValueError):
        return None
    return d if math.isfinite(d) and d > 0 else None


def _crf(value) -> int:
    try:
        crf = int(round(float(str(value).strip())))
    except (TypeError, ValueError):
        return 23
    return crf if 0 <= crf <= 51 else 23


def _codec_key(codec: str | None) -> str:
    key = (codec or "").strip().lower()
    for known in ("hevc", "h265", "x265", "h264", "x264"):
        if known in key:
            return known
    return "h264"


def output_pixels(src_w: int | None, src_h: int | None,
                  target_short: int | None) -> float:
    """Estimated output frame pixels, never upscaling the source."""
    if not src_w or not src_h or src_w <= 0 or src_h <= 0:
        return _PIXELS_1080P
    src_pixels = float(src_w * src_h)
    if not target_short:
        return src_pixels
    src_short = min(src_w, src_h)
    out_short = min(src_short, target_short)
    return src_pixels * (out_short / src_short) ** 2


def estimate_output_bytes(duration_s, out_pixels: float, codec: str, crf: int,
                          audio_kbps: float = 128.0,
                          source_bytes: int = 0) -> tuple[int, int]:
    duration = _duration(duration_s)
    if duration is None or out_pixels <= 0:
        return (0, 0)
    bpp = 0.12 * (0.87 ** (_crf(crf) - 23)) * _CODEC_BPP.get(codec, 1.0)
    audio = min(max(audio_kbps, 0.0), 1024.0)
    point = (bpp * (out_pixels / _PIXELS_1080P) * _PIXELS_1080P
             * _ASSUMED_FPS * duration + audio * 1000.0 * duration) / 8.0
    if not math.isfinite(point) or point <= 0:
        return (0, 0)
    low, high = round(point * _SIZE_LOW), round(point * _SIZE_HIGH)
    if source_bytes > 0:
        floor, ceil = round(source_bytes * _SIZE_FLOOR_RATIO), round(source_bytes * _SIZE_CEIL_RATIO)
        low = min(max(low, floor), max(ceil, floor))
        high = min(max(high, floor), max(ceil, floor))
    low = max(low, _MIN_SIZE_BYTES)
    return low, max(high, low)


def estimate_encode_seconds(duration_s, out_pixels: float, codec: str,
                            preset: str) -> tuple[int, int]:
    duration = _duration(duration_s)
    if duration is None or out_pixels <= 0:
        return (0, 0)
    factor = _PRESET_TIME.get((preset or "medium").lower(), 1.0)
    divisor = max(factor * (out_pixels / _PIXELS_1080P), 0.01)
    point = duration * _CODEC_TIME.get(codec, 1.0) / divisor
    if not math.isfinite(point) or point <= 0:
        return (0, 0)
    low = min(max(round(point * _TIME_LOW), _TIME_MIN), _TIME_MAX)
    high = min(max(round(point * _TIME_HIGH), _TIME_MIN), _TIME_MAX)
    return low, max(high, low)


def format_range(low: int, high: int) -> str:
    low, high = max(1, low), max(1, high)
    if low > high:
        low, high = high, low
    return f"{low}\u2013{high}"


def format_size_range(low: int, high: int) -> str:
    def size(n: int) -> str:
        if n >= 1024**3:
            return f"{n / 1024**3:.2f}GB"
        if n >= 1024**2:
            return f"{n / 1024**2:.1f}MB"
        return f"{n / 1024:.0f}KB"
    return f"\U0001F3AF \u2248 {size(low)}\u2013{size(high)}"


def format_time_range(low: int, high: int) -> str:
    def hms(n: int) -> str:
        if n < 90:
            return f"{n}s"
        if n < 5400:
            return f"{max(1, round(n / 60))} min"
        return f"{max(1, round(n / 3600))} h"
    return f"\u23F1 \u2248 {hms(low)}\u2013{hms(high)}"
