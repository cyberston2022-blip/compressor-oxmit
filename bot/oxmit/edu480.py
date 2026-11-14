"""EDU480 — the single active compression profile, plus the pure helpers
the queue pipeline needs around it (output naming, transcode decision,
throughput-based waiting-time estimates).

Everything here is deterministic and side-effect free so it is unit-tested
directly; engine.py wires it into the job lifecycle.

EDU480 definition (profile version 2):
- H.264 (libx264), CRF ``EDU480_CRF`` (25), preset ``EDU480_PRESET``
  (veryfast), aq-mode 3, yuv420p, MP4 + faststart.
- Resolution: the SHORT side is scaled to 480 with Lanczos, aspect ratio is
  preserved, both dimensions are even, and nothing is ever upscaled. Portrait
  sources therefore become 480 px wide (not 854 px wide as the old fixed-
  width Encore profile produced), and 4:3 / sub-480p sources are not
  stretched or enlarged.
- Frame rate: capped at ``EDU480_MAX_FPS`` (30). 50/60 fps screen recordings
  halve their encode work with no loss of legibility.
- Audio: AAC ``EDU480_AUDIO_KBPS`` (64k) — clear speech at minimal size.

The exact scale/fps filters are computed here from the real ffprobe result
and passed to Encore as profileParams (``vf`` / ``fpsf``), so the Encore
profile never has to guess dimensions.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

PROFILE_KEY = "edu480"
PROFILE_VERSION = 2
MAX_SHORT_SIDE = 480

# ---------------------------------------------------------------------------
# output file naming
# ---------------------------------------------------------------------------

# Extensions a user may type out of habit; they are stripped and the result
# is always delivered as .mp4. Only known file extensions are removed so a
# name such as "Lecture v1.2" keeps its ".2".
KNOWN_EXTS = {
    "mp4", "mkv", "avi", "mov", "webm", "ts", "m2ts", "flv", "wmv", "mpg",
    "mpeg", "m4v", "3gp", "ogv", "vob", "mts", "f4v", "rm", "rmvb", "asf",
    "divx", "mxf", "m4a", "mp3", "wav", "aac", "txt", "pdf", "doc", "docx",
    "zip", "rar", "bin",
}
_EXT_RE = re.compile(r"\.([A-Za-z0-9]{1,5})$")
# Characters that are invalid on common filesystems / unsafe in paths.
_INVALID_FS = set('/\\:*?"<>|')
# Bidi overrides / isolates can visually spoof an extension ("exe.mp4").
# U+200C (ZWNJ) is NOT removed: it is a legitimate part of Persian words.
_BIDI_AND_INVISIBLE = {
    "​", "‍", "‎", "‏", "‪", "‫", "‬",
    "‭", "‮", "⁦", "⁧", "⁨", "⁩", "﻿",
}
_WIN_RESERVED = {"con", "prn", "aux", "nul",
                 *(f"com{i}" for i in range(1, 10)),
                 *(f"lpt{i}" for i in range(1, 10))}
NAME_MAX_CHARS = 100
NAME_MAX_BYTES = 200  # UTF-8; Persian letters take 2 bytes each


def normalize_output_name(raw: str | None) -> str | None:
    """User text -> safe output stem (WITHOUT extension), or None if empty.

    Accepts Persian and English. Strips any directory part and any extension
    the user typed, removes filesystem-invalid and invisible bidi characters,
    collapses whitespace and enforces a length limit. The caller appends
    ``.mp4``.
    """
    if raw is None:
        return None
    text = unicodedata.normalize("NFC", str(raw))
    # Path traversal / directory separators: keep only the last segment.
    text = re.split(r"[\\/]", text)[-1]
    out = []
    for ch in text:
        if ch in _BIDI_AND_INVISIBLE:
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("C") and ch != "‌":  # control/format/unassigned
            continue
        if ch in _INVALID_FS:
            out.append(" ")
            continue
        out.append(ch)
    text = " ".join("".join(out).split())
    # Strip typed extensions (repeatedly: "a.mkv.mp4").
    while True:
        m = _EXT_RE.search(text)
        if not m or m.group(1).lower() not in KNOWN_EXTS:
            break
        text = text[: m.start()].rstrip()
    text = text.strip(" .")
    if not text or set(text) <= {"."}:
        return None
    if text.lower() in _WIN_RESERVED:
        text = "_" + text
    if len(text) > NAME_MAX_CHARS:
        text = text[:NAME_MAX_CHARS].rstrip(" .")
    while len(text.encode("utf-8")) > NAME_MAX_BYTES:
        text = text[:-1]
    text = text.rstrip(" .")
    return text or None


def output_filename(stem: str | None, fallback: str | None = None) -> str:
    """Final delivered file name: ``<stem>.mp4`` (never empty)."""
    name = normalize_output_name(stem) or normalize_output_name(fallback) or "video"
    return name + ".mp4"


# ---------------------------------------------------------------------------
# geometry + filters
# ---------------------------------------------------------------------------

def _even(v: float) -> int:
    """Nearest even integer (853.3 -> 854, 1279 -> 1280), at least 2."""
    return max(2, 2 * int(round(v / 2.0)))


def target_dims(width: int | None, height: int | None,
                max_short: int = MAX_SHORT_SIDE) -> tuple[int, int] | None:
    """Output (w, h) for EDU480, or None when no scaling is needed.

    Short side becomes ``max_short`` (never larger than the source), the
    aspect ratio is preserved and both sides are even (yuv420p / x264
    requirement). Odd-sized sources that need no downscale still get an
    even crop-free size via a tiny 1px rounding scale.
    """
    if not width or not height or width <= 0 or height <= 0:
        return None
    short = min(width, height)
    if short <= max_short:
        if width % 2 == 0 and height % 2 == 0:
            return None
        return _even(width), _even(height)
    scale = max_short / short
    if width <= height:  # portrait (or square)
        return max_short, _even(height * scale)
    return _even(width * scale), max_short


def video_filters(probe: dict, max_fps: float) -> tuple[str, str]:
    """(scale filter, fps filter) for Encore's ``filters`` list.

    ``null`` is FFmpeg's pass-through filter, used when nothing must change.
    """
    dims = target_dims(probe.get("width"), probe.get("height"))
    vf = f"scale={dims[0]}:{dims[1]}:flags=lanczos" if dims else "null"
    fps = probe.get("fps") or 0
    try:
        fps = float(fps)
    except (TypeError, ValueError):
        fps = 0.0
    fpsf = f"fps={_fmt_fps(max_fps)}" if fps > max_fps + 0.5 else "null"
    return vf, fpsf


def _fmt_fps(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.3f}"


def encode_params(probe: dict, cfg, threads: int) -> dict:
    """profileParams for the Encore ``edu480`` profile (all strings)."""
    vf, fpsf = video_filters(probe, cfg.edu480_max_fps)
    return {
        "crf": str(cfg.edu480_crf),
        "preset": cfg.edu480_preset,
        "threads": str(max(1, int(threads))),
        "vf": vf,
        "fpsf": fpsf,
        "audio_bitrate": f"{int(cfg.edu480_audio_kbps)}k",
    }


# ---------------------------------------------------------------------------
# "does this need encoding at all?"
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Decision:
    action: str      # "encode" | "remux"
    reason: str


def video_kbps(probe: dict, size_bytes: int | None = None) -> int:
    """Approximate video-stream bitrate in kbps (container minus audio)."""
    total = int(probe.get("bitrate") or 0)
    dur = float(probe.get("duration_s") or 0)
    if not total and dur > 0 and size_bytes:
        total = int(size_bytes * 8 / dur)
    try:
        audio = int(probe.get("audio_bitrate") or 0)
    except (TypeError, ValueError):
        audio = 0
    return max(0, (total - audio) // 1000)


def decide(probe: dict, size_bytes: int, cfg) -> Decision:
    """Encode only when it can actually help.

    A source is EDU480-compliant (=> stream-copy remux to MP4, seconds
    instead of minutes) when ALL hold: short side <= 480, H.264 video,
    yuv420p (or unknown), AAC or no audio, fps within the cap, and video
    bitrate at or below ``EDU480_COMPLIANT_KBPS``. Resolution, size or
    codec alone never decide it (a 480p file can still be 3 Mbit/s).
    """
    w, h = probe.get("width"), probe.get("height")
    if not w or not h:
        return Decision("encode", "unknown dimensions")
    if min(w, h) > MAX_SHORT_SIDE:
        return Decision("encode", f"{w}x{h} above 480p")
    if (probe.get("vcodec") or "").lower() != "h264":
        return Decision("encode", f"video codec {probe.get('vcodec')}")
    pix = (probe.get("pix_fmt") or "yuv420p").lower()
    if pix not in ("yuv420p", "yuvj420p"):
        return Decision("encode", f"pixel format {pix}")
    ac = (probe.get("acodec") or "").lower()
    if ac and ac != "aac":
        return Decision("encode", f"audio codec {ac}")
    try:
        fps = float(probe.get("fps") or 0)
    except (TypeError, ValueError):
        fps = 0.0
    if fps > cfg.edu480_max_fps + 0.5:
        return Decision("encode", f"{fps:g} fps above cap")
    kbps = video_kbps(probe, size_bytes)
    if kbps <= 0 or kbps > cfg.edu480_compliant_kbps:
        return Decision("encode", f"video bitrate {kbps} kbps")
    if w % 2 or h % 2:
        return Decision("encode", "odd dimensions")
    return Decision("remux", f"already EDU480-compliant ({w}x{h}, {kbps} kbps)")


# ---------------------------------------------------------------------------
# waiting-time estimate (throughput model, never a fixed per-job guess)
# ---------------------------------------------------------------------------

# Prior until enough history exists: wall seconds of worker time per second
# of source media (download + probe + encode + validate). Replaced by the
# measured rolling value as soon as completed jobs exist.
DEFAULT_SEC_PER_MEDIA_SEC = 0.25
DEFAULT_MEDIA_DURATION_S = 1800.0  # unknown duration -> assume a 30 min lecture


def job_cost_seconds(duration_s: float | None, rate: float) -> float:
    dur = float(duration_s or 0) or DEFAULT_MEDIA_DURATION_S
    return max(20.0, dur * max(0.01, rate))


def eta_range(ahead_durations: list[float | None], active_remaining_s: float,
              slots: int, rate: float) -> tuple[int, int]:
    """(low, high) seconds until a job ahead of ``ahead_durations`` starts.

    Workload = remaining time of running jobs + estimated cost of every job
    ahead; it drains through ``slots`` parallel workers. Presented as a range
    because per-video cost varies (content, bitrate, Telegram speed).
    """
    work = max(0.0, active_remaining_s) + sum(
        job_cost_seconds(d, rate) for d in ahead_durations)
    per_slot = work / max(1, slots)
    return int(per_slot * 0.8), int(math.ceil(per_slot * 1.3))


def fmt_duration_fa(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "کمتر از ۱ دقیقه"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} دقیقه"
    h, m = divmod(minutes, 60)
    return f"{h} ساعت" + (f" و {m} دقیقه" if m else "")


def fmt_eta_range_fa(low: int, high: int) -> str:
    if high < 60:
        return "کمتر از ۱ دقیقه"
    if fmt_duration_fa(low) == fmt_duration_fa(high):
        return "حدود " + fmt_duration_fa(high)
    return f"{fmt_duration_fa(low)} تا {fmt_duration_fa(high)}"


def predict_guard(probe: dict, size_bytes: int, cfg) -> Decision | None:
    """Deterministic predictive no-gain guard (V3 §16 — no ML, no history).

    Returns a ``deliver_source`` Decision when the LOW edge of the predicted
    EDU480 output reaches ``cfg.predict_no_gain_ratio`` of the source size —
    i.e. when encoding is confidently useless. The guard can only SKIP
    encodes the model is confident about; it never fires on unknown sizes
    and never rejects a useful encode (cold-start safe by construction).
    """
    if not getattr(cfg, "encode_predict_guard", True):
        return None
    if not size_bytes:
        return None  # unknown source size: never guess (V3 §16)
    ratio = getattr(cfg, "predict_no_gain_ratio", 0.98)
    from . import estimate as estimate_mod  # local import: estimate is leaf-level

    predicted_low, predicted_high = estimate_mod.estimate_output_bytes(
        probe.get("duration_s"),
        estimate_mod.output_pixels(probe.get("width"), probe.get("height"), MAX_SHORT_SIDE),
        "h264", getattr(cfg, "edu480_crf", 25),
        audio_kbps=getattr(cfg, "edu480_audio_kbps", 64),
        source_bytes=size_bytes,
    )
    if predicted_low > 0 and predicted_low >= size_bytes * ratio:
        return Decision(
            "deliver_source",
            f"predictive no-gain (deterministic bpp guard v1): EDU480 output "
            f"~{estimate_mod.format_size_range(predicted_low, predicted_high)} vs source "
            f"{size_bytes} bytes (>= {ratio:.0%} of source)",
        )
    return None
