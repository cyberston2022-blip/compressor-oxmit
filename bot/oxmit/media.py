"""Media probing (ffprobe), streaming SHA-256 and perceptual fingerprints."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from PIL import Image

from .log import get_logger

log = get_logger("oxmit.media")

CHUNK = 4 * 1024 * 1024

# The Local Bot API stores downloads under a directory named after the bot
# token. Any stderr/path fragment quoting that tree must be redacted before
# it is stored, logged, or shown to a user (SEC-1). Note: the token itself
# contains a colon ("id:secret") — it must be consumed by the match.
_BOTAPI_PATH_RE = re.compile(r"/var/lib/telegram-bot-api/[^/\s\"'<>]+")

_REDACTED = "/var/lib/telegram-bot-api/<REDACTED>"


def redact(text: object) -> str:
    """Strip token-bearing Local Bot API paths from any error text."""
    return _BOTAPI_PATH_RE.sub(_REDACTED, str(text or ""))


class MediaError(Exception):
    """Raised for unusable media or probe failures."""


async def sha256_file(path: str | Path) -> str:
    def _run() -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            while True:
                block = fh.read(CHUNK)
                if not block:
                    break
                h.update(block)
        return h.hexdigest()

    return await asyncio.to_thread(_run)


async def copy_and_hash(src: str | Path, dst: str | Path) -> str:
    """Single-pass stream copy that computes SHA-256 while reading.

    Avoids a second full read of multi-GB sources. The destination is
    written atomically enough for our use (fixed job dir, no concurrent
    readers until the job row is committed).
    """

    def _run() -> str:
        h = hashlib.sha256()
        with open(src, "rb") as fin, open(dst, "wb") as fout:
            while True:
                block = fin.read(CHUNK)
                if not block:
                    break
                h.update(block)
                fout.write(block)
        return h.hexdigest()

    return await asyncio.to_thread(_run)


async def copy_with_progress(src: str | Path, dst: str | Path,
                             on_progress=None, chunk: int = 8 * 1024 * 1024) -> None:
    """Stream copy calling on_progress(bytes_done) after every chunk."""
    def _run() -> None:
        done = 0
        with open(src, "rb") as fin, open(dst, "wb") as fout:
            while True:
                block = fin.read(chunk)
                if not block:
                    break
                fout.write(block)
                done += len(block)
                if on_progress:
                    on_progress(done)
            # Flush to disk before declaring the copy complete: a crash right
            # after staging must not leave an os.replace'd-but-unflushed file.
            fout.flush()
            os.fsync(fout.fileno())
    return await asyncio.to_thread(_run)


def split_by_size(path: str | Path, out_dir: str | Path, max_bytes: int,
                  duration_s: float) -> list[Path]:
    """Split a media file at keyframes (stream copy) into parts under max_bytes.

    Deterministic segmentation via the segment muxer; parts are independently
    playable MP4s. Re-splits any part that still exceeds the limit. Returns
    the ordered part paths.
    """
    import subprocess as sp
    import math

    src = Path(path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    size = src.stat().st_size
    duration = max(duration_s, 1.0)
    seg_time = max(5.0, duration * (max_bytes / size) * 0.95)

    for attempt in range(6):
        for p in out.glob("part*"):
            p.unlink()
        cmd = [
            "ffmpeg", "-v", "error", "-i", str(src), "-c", "copy",
            "-map", "0", "-f", "segment", "-segment_time", f"{seg_time:.2f}",
            "-reset_timestamps", "1", "-movflags", "+faststart",
            str(out / "part%03d.mp4"),
        ]
        proc = sp.run(cmd, capture_output=True, timeout=3600)
        if proc.returncode != 0:
            raise MediaError(f"segment failed: {redact((proc.stderr or b'').decode(errors='replace')[:200])}")
        parts = sorted(out.glob("part*.mp4"))
        oversized = [p for p in parts if p.stat().st_size > max_bytes]
        if not oversized:
            return parts
        # Split the first oversized part again with a tighter estimate.
        big = oversized[0]
        seg_time = max(5.0, seg_time * (max_bytes / big.stat().st_size) * 0.9)
    raise MediaError("could not produce parts below the size limit")


def _probe_sync(path: str | Path) -> dict:
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError("ffprobe timeout") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or b"").decode(errors="replace")[:300]
        raise MediaError(f"ffprobe failed: {redact(detail)}")
    try:
        data = json.loads(proc.stdout.decode())
    except json.JSONDecodeError as exc:
        raise MediaError("ffprobe returned invalid JSON") from exc

    fmt = data.get("format", {})
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise MediaError("no video stream found")
    if video.get("dispositions", {}).get("attached_pic"):
        raise MediaError("attached picture, not a video")

    def _fps(s: dict) -> float | None:
        raw = s.get("avg_frame_rate") or s.get("r_frame_rate")
        if not raw or "/" not in raw:
            return None
        num, den = raw.split("/", 1)
        try:
            den_f = float(den)
            return round(float(num) / den_f, 3) if den_f else None
        except (ValueError, ZeroDivisionError):
            return None

    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = None
    for d_cand in (
        fmt.get("duration"),
        video.get("duration"),
        audio.get("duration") if audio else None,
        (fmt.get("tags") or {}).get("DURATION"),
        (video.get("tags") or {}).get("DURATION"),
    ):
        if d_cand:
            try:
                if isinstance(d_cand, str) and ":" in d_cand:
                    parts = d_cand.split(":")
                    if len(parts) == 3:
                        d_val = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                    else:
                        d_val = float(parts[-1])
                else:
                    d_val = float(d_cand)
                if d_val > 0:
                    duration = d_val
                    break
            except (TypeError, ValueError):
                pass
    bitrate = None
    try:
        bitrate = int(fmt.get("bit_rate") or 0) or None
    except (TypeError, ValueError):
        pass

    return {
        "filename": fmt.get("filename"),
        "container": (fmt.get("format_name") or "")[:64],
        "duration_s": duration,
        "size_bytes": int(fmt.get("size") or 0) or None,
        "bitrate": bitrate,
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": _fps(video),
        "vcodec": video.get("codec_name"),
        "pix_fmt": video.get("pix_fmt"),
        "acodec": audio.get("codec_name") if audio else None,
        "audio_channels": audio.get("channels") if audio else 0,
        "audio_bitrate": (audio.get("bit_rate") if audio else None),
        "streams": len(streams),
    }


async def probe_video(path: str | Path) -> dict:
    info = await asyncio.to_thread(_probe_sync, path)
    if not info.get("duration_s"):
        raise MediaError("missing duration (probe)")
    if info["duration_s"] > 24 * 3600:
        raise MediaError("duration exceeds 24h limit")
    return info


def _ahash_8x8(image_path: Path) -> int:
    img = Image.open(image_path).convert("L")
    img = img.resize((8, 8))
    pixels = list(img.getdata())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for idx, px in enumerate(pixels):
        if px > avg:
            bits |= 1 << idx
    return bits


def _fingerprint_sync(path: str | Path, duration: float, tmp_root: str, n: int = 8) -> list[int]:
    work = Path(tmp_root) / f"fp-{uuid.uuid4().hex[:12]}"
    work.mkdir(parents=True, exist_ok=True)
    hashes: list[int] = []
    try:
        for i in range(n):
            t = duration * (i + 0.5) / n
            out = work / f"f{i}.png"
            try:
                subprocess.run(
                    [
                        "ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path),
                        "-frames:v", "1", "-vf", "scale=8:8:flags=area,format=gray",
                        "-y", str(out),
                    ],
                    capture_output=True,
                    timeout=90,
                )
            except subprocess.TimeoutExpired:
                continue
            if out.exists():
                try:
                    hashes.append(_ahash_8x8(out))
                except Exception:  # noqa: BLE001 - corrupt frame file
                    continue
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if len(hashes) < max(3, n // 2):
        raise MediaError("fingerprint extraction failed")
    return hashes


async def fingerprint(path: str | Path, duration: float, tmp_root: str) -> list[int]:
    return await asyncio.to_thread(_fingerprint_sync, path, duration, tmp_root)


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def phash_distance(frames_a: list[int], frames_b: list[int]) -> tuple[float, int] | None:
    """Mean and max hamming distance over paired frames."""
    n = min(len(frames_a), len(frames_b))
    if n < 3:
        return None
    dists = [hamming(frames_a[i], frames_b[i]) for i in range(n)]
    return sum(dists) / n, max(dists)


def sanitize_filename(name: str | None, limit: int = 64) -> str:
    if not name:
        return "video"
    cleaned = []
    for ch in name:
        if ch.isalnum() or ch in " .-_()[]":
            cleaned.append(ch)
        else:
            cleaned.append("_")
    text = "".join(cleaned).strip(" ._")
    text = " ".join(text.split())[:limit]
    return text or "video"


def human_size(num: float | None) -> str:
    if not num:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024:
            return f"{num:.1f}{unit}" if unit != "B" else f"{int(num)}B"
        num /= 1024
    return f"{num:.1f}PB"


def remux_compatible(probe: dict) -> bool:
    """True when the source streams can be stream-copied into MP4.

    Video must be H.264 or HEVC and audio AAC/MP3/AC3/Opus (MP4-tolerated
    codecs). MP4-family containers are excluded (already compatible).
    """
    v = (probe.get("vcodec") or "").lower()
    a = (probe.get("acodec") or "").lower()
    container = (probe.get("container") or "").lower()
    if v not in ("h264", "hevc", "h265"):
        return False
    if a and a not in ("aac", "mp3", "ac3", "eac3", "opus"):
        return False
    if "mp4" in container and "matroska" not in container:
        return False
    return True


def remux_to_mp4(src: str | Path, dst: str | Path,
                 timeout: float = 3600.0) -> None:
    """Stream-copy remux into an MP4 with faststart (no re-encode).

    Video and first audio stream only; subtitles/attachments are dropped
    because several of them are not representable in MP4.
    Raises MediaError on failure.
    """
    import subprocess as sp

    cmd = [
        "ffmpeg", "-y", "-v", "error", "-i", str(src),
        "-map", "0:v:0", "-map", "0:a:0?",
        "-c", "copy", "-ignore_unknown",
        "-movflags", "+faststart",
        str(dst),
    ]
    try:
        proc = sp.run(cmd, capture_output=True, timeout=timeout)
    except sp.TimeoutExpired as exc:
        Path(dst).unlink(missing_ok=True)
        raise MediaError("remux timeout") from exc
    if proc.returncode != 0 or not Path(dst).is_file():
        Path(dst).unlink(missing_ok=True)
        raise MediaError(f"remux failed: {redact((proc.stderr or b'').decode(errors='replace')[:200])}")


def download_thumbnail(src: str | Path, dst: str | Path) -> bool:
    """Normalize a user photo into a small JPEG for sendVideo thumbnail.

    Returns True on success. aiogram requires an InputFile for the
    thumbnail field, so the photo is materialized on disk.
    """
    import subprocess as sp

    cmd = [
        "ffmpeg", "-y", "-v", "error", "-i", str(src),
        "-frames:v", "1", "-vf", "scale=320:-2", "-q:v", "7", str(dst),
    ]
    proc = sp.run(cmd, capture_output=True, timeout=60)
    if proc.returncode != 0 or not Path(dst).is_file():
        Path(dst).unlink(missing_ok=True)
        return False
    return True


def extract_thumbnail(video: str | Path, dst: str | Path, at_seconds: float) -> bool:
    """Grab one video frame as the sendVideo thumbnail.

    Bot API thumbnails must be a JPEG with width/height within 320x320, so
    the frame is fit-inside-scaled (works for portrait sources too).
    """
    import subprocess as sp

    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{max(0.0, float(at_seconds)):.2f}", "-i", str(video),
        "-frames:v", "1",
        "-vf", "scale=320:320:force_original_aspect_ratio=decrease",
        "-q:v", "7", str(dst),
    ]
    proc = sp.run(cmd, capture_output=True, timeout=120)
    if proc.returncode != 0 or not Path(dst).is_file():
        Path(dst).unlink(missing_ok=True)
        return False
    return True
