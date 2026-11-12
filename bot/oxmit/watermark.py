"""Per-admin watermark: Argon-verified filter construction + ffmpeg pass.

Filter logic is ported from the owner's ArgonsEncoder project
(bot/func/ffmpeg_utils.py, GPL-3.0, "Developed by ARGON telegram:
@REACTIVEARGON") - same owner, attribution headers retained. Only the
VERIFIED Argon options exist here (no invented color/shadow/center/tile):

    type: text | image          master: enabled
    position: top-left|top-right|bottom-left|bottom-right (4 corners only)
    margins: top/bottom/left/right px (0..500, default 10)
    opacity: 0.1..1.0 (default 0.5)          border_opacity: 0.0..1.0 (0.5)
    text: max 200 chars; font_size: 10..100 px FIXED (not resolution-scaled)
    font: default bundled Roboto OR per-admin uploaded TTF/OTF
    image_scale: 0.1..1.0 relative to the IMAGE's own width (default 0.1)
    timing: always | range(start,end) | interval(duration,period)

Pipeline decision (oxmit-specific, documented): the archive always stores
the CLEAN compressed output - admin A's watermark must never leak into
admin B's cache-reuse. The watermark is applied as a delivery-time ffmpeg
pass per recipient (video re-encode, audio stream-copied). Remux jobs skip
watermarking entirely, exactly like Argon.

Known Argon edge case fixed here: a degenerate time range (end <= start)
forced timing back to 'always' instead of producing between(t,0,0).
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from . import media as media_mod
from .log import get_logger

log = get_logger("oxmit.watermark")

WM_TIMEOUT_S = 4 * 3600

_DEFAULTS = {
    "type": "text",
    "position": "top-right",
    "text": "Oxmit",
    "font_size": 24,
    "opacity": 0.5,
    "border_opacity": 0.5,
    "margin_top": 10,
    "margin_bottom": 10,
    "margin_left": 10,
    "margin_right": 10,
    "image_scale": 0.1,
    "timing_mode": "always",
    "start_time": 0,
    "end_time": 0,
    "interval_duration": 5,
    "interval_period": 30,
}


def normalize_wm(raw: dict | None) -> dict:
    """Clamp every field into its verified range; fill defaults; fix the
    degenerate-range edge case observed in production Argon data."""
    wm = dict(_DEFAULTS)
    if not isinstance(raw, dict):
        return wm

    def _num(key, lo, hi, cast=float):
        try:
            v = cast(raw.get(key, wm[key]))
        except (TypeError, ValueError):
            return
        wm[key] = min(hi, max(lo, v))

    wm["type"] = "image" if raw.get("type") == "image" else "text"
    if raw.get("position") in ("top-left", "top-right",
                               "bottom-left", "bottom-right"):
        wm["position"] = raw["position"]
    try:
        wm["text"] = str(raw.get("text") or wm["text"]).replace("\n", " ")[:200]
    except (TypeError, ValueError):
        pass
    _num("font_size", 10, 100, int)
    _num("opacity", 0.1, 1.0)
    _num("border_opacity", 0.0, 1.0)
    _num("image_scale", 0.1, 1.0)
    for side in ("top", "bottom", "left", "right"):
        _num(f"margin_{side}", 0, 500, int)
    if raw.get("timing_mode") in ("always", "range", "interval"):
        wm["timing_mode"] = raw["timing_mode"]
    _num("start_time", 0, 86400, int)
    _num("end_time", 0, 86400, int)
    _num("interval_duration", 1, 600, int)
    _num("interval_period", 2, 3600, int)
    if wm["timing_mode"] == "range" and wm["end_time"] <= wm["start_time"]:
        # Argon kept 'range' and emitted between(t,0,0) (one visible frame).
        wm["timing_mode"] = "always"
    if wm["timing_mode"] == "interval" and (wm["interval_duration"]
                                            >= wm["interval_period"]):
        wm["interval_duration"] = max(1, wm["interval_period"] // 2)
    return wm


def escape_drawtext(text: str) -> str:
    """Argon's exact drawtext escaping (ffmpeg_utils.py:219-227)."""
    t = str(text or "")
    t = t.replace("\\", "\\\\").replace("%", "\\%").replace(":", "\\:")
    t = t.replace(",", "\\,").replace("'", "").replace("\n", " ")
    return t


def _position_xy(wm: dict) -> tuple[str, str]:
    m_t, m_b = wm["margin_top"], wm["margin_bottom"]
    m_l, m_r = wm["margin_left"], wm["margin_right"]
    pos = wm["position"]
    if pos == "top-left":
        return str(m_l), str(m_t)
    if pos == "top-right":
        return "W-w-%d" % m_r, str(m_t)
    if pos == "bottom-left":
        return str(m_l), "H-h-%d" % m_b
    return "W-w-%d" % m_r, "H-h-%d" % m_b  # bottom-right


def _timing_expr(wm: dict) -> str:
    mode = wm["timing_mode"]
    if mode == "range":
        return ":enable='between(t,%d,%d)'" % (wm["start_time"], wm["end_time"])
    if mode == "interval":
        return ":enable='lt(mod(t,%d),%d)'" % (wm["interval_period"],
                                               wm["interval_duration"])
    return ""


def build_video_filter(wm: dict, *, image_path: str | None,
                       font_path: str | None) -> str | None:
    """Video filter for the delivery-time pass; None = no watermark.

    Text branch is a plain drawtext (usable in -vf); image branch returns a
    filter_complex snippet using the movie= source, mirroring Argon.
    """
    if wm.get("type") == "image":
        if not image_path or not Path(image_path).is_file():
            # Missing image -> continue WITHOUT the watermark (Argon
            # behavior: warn + no watermark, encode never fails).
            log.warning("watermark image missing", extra={"detail": str(image_path)})
            return None
        img = str(Path(image_path).resolve()).replace("\\", "/").replace(":", "\\:")
        img = img.replace("'", "")
        x, y = _position_xy(wm)
        return (
            "movie='{img}',scale=iw*{scale}:-1,format=rgba,"
            "colorchannelmixer=aa={op}[wm];"
            "[0:v][wm]overlay=x='{x}':y='{y}'{timing}"
        ).format(img=img, scale=wm["image_scale"], op=wm["opacity"],
                 x=x, y=y, timing=_timing_expr(wm))

    text = escape_drawtext(wm.get("text") or "")
    font = font_path if font_path and Path(font_path).is_file() else None
    if font:
        fp = str(Path(font).resolve()).replace("\\", "/").replace(":", "\\:")
    else:
        fp = str((Path(__file__).parent / "fonts" / "Roboto-Regular.ttf")
                 .resolve()).replace("\\", "/").replace(":", "\\:")
    x, y = _position_xy(wm)
    return (
        "drawtext=fontfile='{font}':text='{text}':fontsize={size}"
        ":fontcolor=white@{op}:x={x}:y={y}"
        ":box=1:boxcolor=black@{bop}:boxborderw=5{timing}"
    ).format(font=fp, text=text, size=wm["font_size"], op=wm["opacity"],
             x=x, y=y, bop=wm["border_opacity"], timing=_timing_expr(wm))


def uses_complex_filter(video_filter: str) -> bool:
    return "movie=" in video_filter


async def apply_watermark(in_path: str | Path, out_path: str | Path,
                          wm: dict, *, image_path: str | None,
                          font_path: str | None, threads: int = 0) -> bool:
    """Delivery-time pass: video re-encode with the watermark filter, audio
    stream-copied, faststart. Returns False (and removes the partial file)
    when the filter is unavailable or ffmpeg fails - the caller then
    delivers the clean version instead of failing the whole delivery."""
    vf = build_video_filter(wm, image_path=image_path, font_path=font_path)
    if vf is None:
        return False
    cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(in_path)]
    if uses_complex_filter(vf):
        cmd += ["-filter_complex", vf, "-map", "[0:v]"]
    else:
        cmd += ["-vf", vf]
    cmd += ["-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "copy",
            "-movflags", "+faststart"]
    if threads:
        cmd += ["-threads", str(threads)]
    cmd += [str(out_path)]
    try:
        proc = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, timeout=WM_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        Path(out_path).unlink(missing_ok=True)
        return False
    if proc.returncode != 0 or not Path(out_path).is_file():
        detail = (proc.stderr or b"").decode(errors="replace")[:200]
        log.warning("watermark pass failed", extra={"detail": media_mod.redact(detail)})
        Path(out_path).unlink(missing_ok=True)
        return False
    return True
