"""Video merge service: DB-ordered sessions, compatibility decision, concat.

Ordering rule (spec 7.1-7.2): sequence numbers are assigned ATOMICALLY in
Postgres (item_count + 1 under the session row's row lock) and the merge
reads items ORDER BY seq — filesystem order and download completion order
are never consulted.

Merge strategy (spec 7.4): probe every staged item; when codecs, resolution,
fps, pixel format, sample rate and channel layout all match, use the concat
DEMUXER with stream copy (fast, lossless); otherwise re-encode through the
concat FILTER normalizing to the smallest common geometry — and say so to
the user instead of promising copy-speed.

The output is validated against the sum of item durations before delivery;
an incomplete/short output fails the session instead of being delivered.
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from . import media as media_mod
from .log import get_logger

log = get_logger("oxmit.merge")

COPY_FPS_TOL = 0.01
DURATION_TOL = 0.05  # ±5%: concat is deterministic, tighter than encodes
MERGE_TIMEOUT_S = 4 * 3600


class MergeError(Exception):
    """Raised for unusable merge inputs or failed ffmpeg runs."""


# ---------------------------------------------------------------------------
# session/item persistence
# ---------------------------------------------------------------------------

async def create_session(db, tg_id: int, chat_id: int, *, compress: bool,
                         profile: str | None, target_mb: int | None) -> dict:
    """Open a collecting session; one active session per user (partial
    unique index makes a concurrent second start fail instead of forking)."""
    row = await db.fetchrow(
        """
        INSERT INTO merge_sessions(tg_id, chat_id, status, compress, profile, target_mb)
        VALUES ($1, $2, 'collecting', $3, $4, $5)
        RETURNING *
        """,
        tg_id, chat_id, compress, profile, target_mb,
    )
    return dict(row)


async def add_item(db, session_id: str, media_id, staged_path: str,
                   size_bytes: int, duration_s: float | None) -> int:
    """Append one video with the next atomic sequence number.

    The session row UPDATE takes a row lock, so two concurrent adds from
    the same admin can never draw the same seq (spec 7.2). Returns seq.
    """
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                UPDATE merge_sessions
                SET item_count = item_count + 1,
                    total_bytes = total_bytes + $2,
                    updated_at = now()
                WHERE id = $1 AND status = 'collecting'
                RETURNING item_count
                """,
                session_id, size_bytes,
            )
            if row is None:
                raise MergeError("session not active")
            seq = row["item_count"]
            await conn.execute(
                """
                INSERT INTO merge_items(session_id, seq, media_id, staged_path, size_bytes)
                VALUES ($1, $2, $3, $4, $5)
                """,
                session_id, seq, media_id, staged_path, size_bytes,
            )
    log.info("merge item staged", extra={
        "detail": f"session={str(session_id)[:8]} seq={seq} size={size_bytes}"})
    return seq


async def get_session(db, session_id: str) -> dict | None:
    row = await db.fetchrow("SELECT * FROM merge_sessions WHERE id = $1", session_id)
    return dict(row) if row else None


async def get_active_session(db, tg_id: int) -> dict | None:
    row = await db.fetchrow(
        """
        SELECT * FROM merge_sessions
        WHERE tg_id = $1 AND status IN ('collecting', 'merging', 'compressing')
        ORDER BY created_at DESC LIMIT 1
        """,
        tg_id,
    )
    return dict(row) if row else None


async def list_items(db, session_id: str) -> list:
    return await db.fetch(
        """
        SELECT mi.seq, mi.staged_path, mi.size_bytes, mi.created_at,
               m.filename, m.duration_s, m.width, m.height
        FROM merge_items mi
        JOIN media_assets m ON m.id = mi.media_id
        WHERE mi.session_id = $1
        ORDER BY mi.seq
        """,
        session_id,
    )


async def set_status(db, session_id: str, status: str,
                     error: str | None = None) -> None:
    await db.execute(
        "UPDATE merge_sessions SET status = $2, error = $3, updated_at = now() "
        "WHERE id = $1",
        session_id, status, error,
    )


async def finish_session(db, session_id: str, result_path: str | None) -> None:
    await db.execute(
        "UPDATE merge_sessions SET status = 'completed', result_path = $2, "
        "updated_at = now() WHERE id = $1",
        session_id, result_path,
    )


async def fail_stale_sessions(db, stale_hours: int = 24) -> int:
    """Boot/sweep hygiene: collecting sessions abandoned for a day are
    cancelled (their staged files are cleaned by the caller). Returns count."""
    n = await db.fetchval(
        """
        WITH stale AS (
            UPDATE merge_sessions
            SET status = 'cancelled',
                error = 'expired (no activity)',
                updated_at = now()
            WHERE status = 'collecting'
              AND updated_at < now() - ($1 * interval '1 hour')
            RETURNING id
        )
        SELECT count(*) FROM stale
        """,
        stale_hours,
    )
    return int(n or 0)


# ---------------------------------------------------------------------------
# compatibility decision (pure, unit-tested)
# ---------------------------------------------------------------------------

def decide_strategy(probes: list[dict]) -> tuple[str, str]:
    """('copy', reason) when concat-demuxer stream copy is safe, else
    ('reencode', reason) describing what has to be normalized."""
    if not probes:
        return "reencode", "no inputs"
    if len(probes) == 1:
        return "reencode", "single input does not need concat copy"
    base = probes[0]
    for key in ("vcodec", "acodec", "width", "height", "pix_fmt",
                "sample_rate", "channels"):
        b = base.get(key)
        for i, p in enumerate(probes[1:], start=2):
            v = p.get(key)
            if key == "acodec":
                # an audio-less stream mixed with audio streams is the
                # classic silent-gap concat failure
                if bool(b) != bool(v):
                    return "reencode", f"item {i} audio presence differs"
            if b != v:
                return "reencode", f"item {i} {key}={v!r} != item 1 {b!r}"
    fps = base.get("fps")
    for i, p in enumerate(probes[1:], start=2):
        f = p.get("fps")
        if fps is None or f is None or abs((f or 0) - (fps or 0)) > COPY_FPS_TOL:
            return "reencode", f"item {i} fps={f} != item 1 {fps}"
    return "copy", "streams compatible"


def normalize_target(probes: list[dict]) -> dict:
    """Smallest-common output geometry for the re-encode strategy."""
    widths = [p.get("width") or 0 for p in probes if p.get("width")]
    heights = [p.get("height") or 0 for p in probes if p.get("height")]
    fpss = [p.get("fps") for p in probes if p.get("fps")]
    return {
        "width": min(widths) if widths else None,
        "height": min(heights) if heights else None,
        "fps": min(fpss) if fpss else None,
    }


# ---------------------------------------------------------------------------
# ffmpeg execution
# ---------------------------------------------------------------------------

def _concat_list_file(paths: list[str], work_dir: Path) -> Path:
    lst = work_dir / "concat.txt"
    lines = []
    for p in paths:
        q = str(Path(p).resolve()).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{q}'")
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lst


async def run_copy_merge(staged_paths: list[str], out_path: str,
                         work_dir: str) -> None:
    """Concat demuxer + stream copy. Raises MergeError on failure."""
    lst = _concat_list_file(staged_paths, Path(work_dir))
    cmd = [
        "ffmpeg", "-nostdin", "-y", "-v", "error",
        "-f", "concat", "-safe", "0", "-i", str(lst),
        "-c", "copy", "-movflags", "+faststart",
        str(out_path),
    ]
    try:
        proc = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, timeout=MERGE_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        raise MergeError("merge timeout") from exc
    if proc.returncode != 0 or not Path(out_path).is_file():
        detail = (proc.stderr or b"").decode(errors="replace")[:300]
        raise MergeError(f"concat copy failed: {media_mod.redact(detail)}")


async def run_reencode_merge(staged_paths: list[str], out_path: str,
                             work_dir: str, target: dict,
                             durations: list[float] | None = None,
                             threads: int = 0) -> None:
    """Concat FILTER normalization to the smallest common geometry.

    Uses the concat FILTER (not the demuxer): real-world smoke testing
    showed the demuxer + fps filter drifts duration (4.3s vs 5.0s) when
    inputs have different time bases. Every video is scaled (never
    upscaled) to the min common size, fps-normalized, yuv420p; audio is
    resampled to 48k stereo AAC — inputs without audio get a silent track
    sized from their probe duration so mixed sets still concat cleanly.
    """
    n = len(staged_paths)
    durations = durations or [0.0] * n
    w = target.get("width")
    h = target.get("height")
    fps = target.get("fps") or 30
    scale = (f"scale={w}:{h}:force_original_aspect_ratio=decrease:"
             f"force_divisible_by=2" if w and h else
             "scale=trunc(iw/2)*2:trunc(ih/2)*2:force_original_aspect_ratio=decrease")
    cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error"]
    for p in staged_paths:
        cmd += ["-i", str(p)]
    parts = []
    concat_pairs = []
    for i in range(n):
        parts.append(f"[{i}:v]{scale},fps={fps},format=yuv420p,setsar=1[v{i}]")
        concat_pairs.append((f"[v{i}]", f"[a{i}]"))
    # audio chains: real stream resampled, or silence sized to the input
    for i, p in enumerate(staged_paths):
        has_audio = await _has_audio_stream(p)
        if has_audio:
            parts.append(f"[{i}:a]aresample=48000,aformat=sample_fmts=fltp:"
                         f"channel_layouts=stereo[a{i}]")
        else:
            d = max(0.1, durations[i] if durations and durations[i] else 1.0)
            parts.append(f"anullsrc=channel_layouts=stereo:sample_rate=48000,"
                         f"atrim=0:{d:.3f}[a{i}]")
    pairs = "".join(v + a for v, a in concat_pairs)
    parts.append(f"{pairs}concat=n={n}:v=1:a=1[v][a]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart"]
    if threads:
        cmd += ["-threads", str(threads)]
    cmd += [str(out_path)]
    try:
        proc = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, timeout=MERGE_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        raise MergeError("merge timeout") from exc
    if proc.returncode != 0 or not Path(out_path).is_file():
        detail = (proc.stderr or b"").decode(errors="replace")[:300]
        raise MergeError(f"concat re-encode failed: {media_mod.redact(detail)}")


async def _has_audio_stream(path: str) -> bool:
    probe = await media_mod.probe_video(path)
    return bool(probe.get("acodec"))


async def validate_output(out_path: str, expected_duration: float) -> float:
    """Probe the merged file; duration must be within ±5% of the item sum.
    Returns the actual duration; raises MergeError otherwise."""
    probe = await media_mod.probe_video(out_path)
    actual = probe.get("duration_s") or 0.0
    if expected_duration <= 0:
        return actual
    ratio = actual / expected_duration
    if not (1 - DURATION_TOL <= ratio <= 1 + DURATION_TOL):
        raise MergeError(
            f"merged duration {actual:.1f}s != expected {expected_duration:.1f}s")
    return actual


async def cleanup_session_files(db, session_id: str) -> None:
    """Best-effort removal of staged inputs and empty per-session dirs."""
    import shutil

    rows = await list_items(db, session_id)
    dirs: set[Path] = set()
    for r in rows:
        p = r["staged_path"]
        if p:
            f = Path(p)
            dirs.add(f.parent)
            await asyncio.to_thread(f.unlink, True)
    for d in dirs:
        try:
            if d.is_dir() and not any(d.iterdir()):
                await asyncio.to_thread(shutil.rmtree, d, True)
        except OSError:
            pass
