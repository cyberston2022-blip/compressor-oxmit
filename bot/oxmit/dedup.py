"""Deduplication queries: exact reuse, in-flight coalescing, similarity."""

from __future__ import annotations

import json

import asyncpg

from . import media as media_mod
from .config import Settings
from .log import get_logger

log = get_logger("oxmit.dedup")


async def find_reusable_parts(
    db: asyncpg.Pool, sha256: str, profile: str, version: int = 1
) -> list[asyncpg.Record]:
    """All valid archived parts for (source sha, profile, version), in order.

    Single-part results return a one-element list; split results return every
    part so reuse can deliver the complete set.
    """
    return await db.fetch(
        """
        SELECT ar.id, ar.source_media_id, ar.output_media_id, ar.channel_id,
               ar.message_id, ar.status, ar.file_unique_id, ar.created_at,
               ar.part_index, ar.part_total,
               ms.sha256 AS source_sha256,
               m2.size_bytes AS output_size,
               m2.tg_file_id AS output_tg_file_id,
               ms.tg_file_id AS source_tg_file_id,
               ms.size_bytes AS source_size
        FROM archive_records ar
        JOIN media_assets ms ON ms.id = ar.source_media_id
        LEFT JOIN media_assets m2 ON m2.id = ar.output_media_id
        WHERE ms.sha256 = $1
          AND ar.profile = $2
          AND ar.profile_version = $3
          AND ar.status IN ('active', 'no_gain')
        ORDER BY ar.part_index, ar.created_at
        """,
        sha256,
        profile,
        version,
    )


async def find_reusable_archive(
    db: asyncpg.Pool, sha256: str, profile: str, version: int = 1
) -> asyncpg.Record | None:
    """Latest valid archived result for (source sha, profile, version)."""
    rows = await find_reusable_parts(db, sha256, profile, version)
    return rows[0] if rows else None


async def find_inflight_job(
    db: asyncpg.Pool, sha256: str, profile: str, version: int = 1
) -> asyncpg.Record | None:
    return await db.fetchrow(
        """
        SELECT j.* FROM jobs j
        JOIN media_assets m ON m.id = j.media_id
        WHERE m.sha256 = $1
          AND j.profile = $2
          AND j.profile_version = $3
          AND j.status IN ('queued', 'processing')
        ORDER BY j.enqueued_at
        LIMIT 1
        """,
        sha256,
        profile,
        version,
    )


_FUZZY_WINDOW_S = 2.0
_FUZZY_SIZE_TOL = 0.02  # ±2% — a re-muxed/re-uploaded copy is never byte-identical


async def find_fuzzy_archive(
    db: asyncpg.Pool, *, size_bytes: int, name_norm: str,
    duration_s: float, profile: str,
) -> asyncpg.Record | None:
    """Archived result for a fuzzily-identical source.

    Matches (size ±2%, normalized name, duration ±window) instead of the exact
    SHA-256, so re-muxed or re-uploaded copies of the same video hit the
    previous compressed result. Exact-size matching could never fire: a copy
    with identical bytes is already caught by the SHA-256 layer (NEW-003).
    Returns the newest matching archive record.
    """
    if not size_bytes or not name_norm or not duration_s:
        return None
    return await db.fetchrow(
        """
        SELECT ar.id, ar.source_media_id, ar.output_media_id, ar.profile,
               ar.channel_id, ar.message_id, ar.status, ar.file_unique_id,
               ar.created_at, ar.part_index, ar.part_total,
               ms.sha256 AS source_sha256,
               m2.size_bytes AS output_size,
               m2.tg_file_id AS output_tg_file_id,
               ms.tg_file_id AS source_tg_file_id,
               ms.size_bytes AS source_size
        FROM archive_records ar
        JOIN media_assets ms ON ms.id = ar.source_media_id
        LEFT JOIN media_assets m2 ON m2.id = ar.output_media_id
        WHERE ar.profile = $1
          AND ar.status IN ('active', 'no_gain')
          AND ms.size_bytes BETWEEN ($2::numeric * {lo}) AND ($2::numeric * {hi})
          AND ms.name_norm = $3
          AND ms.duration_s BETWEEN $4 AND $5
        ORDER BY ar.created_at DESC
        LIMIT 1
        """.format(lo=str(1 - _FUZZY_SIZE_TOL), hi=str(1 + _FUZZY_SIZE_TOL)),
        profile, size_bytes, name_norm,
        max(0.0, duration_s - _FUZZY_WINDOW_S),
        duration_s + _FUZZY_WINDOW_S,
    )


async def find_fuzzy_inflight_job(
    db: asyncpg.Pool, *, size_bytes: int, name_norm: str,
    duration_s: float, profile: str,
) -> asyncpg.Record | None:
    """Active job for a fuzzily-identical source -> new request joins it."""
    if not size_bytes or not name_norm or not duration_s:
        return None
    return await db.fetchrow(
        """
        SELECT j.* FROM jobs j
        JOIN media_assets m ON m.id = j.media_id
        WHERE j.profile = $1
          AND j.status IN ('queued', 'processing')
          AND m.size_bytes BETWEEN ($2::numeric * {lo}) AND ($2::numeric * {hi})
          AND m.name_norm = $3
          AND m.duration_s BETWEEN $4 AND $5
        ORDER BY j.enqueued_at
        LIMIT 1
        """.format(lo=str(1 - _FUZZY_SIZE_TOL), hi=str(1 + _FUZZY_SIZE_TOL)),
        profile, size_bytes, name_norm,
        max(0.0, duration_s - _FUZZY_WINDOW_S),
        duration_s + _FUZZY_WINDOW_S,
    )


def _load_frames(raw: str | None) -> list[int]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [int(x) for x in data.get("frames", [])]
    except (json.JSONDecodeError, TypeError, AttributeError):
        return []


async def find_similar_archive(
    db: asyncpg.Pool,
    cfg: Settings,
    sha256: str | None,
    duration_s: float,
    phash_frames: list[int],
    profile: str,
    version: int = 1,
    acodec: str | None = None,
    audio_channels: int | None = None,
) -> asyncpg.Record | None:
    """Conservative near-duplicate search against already-archived sources.

    Candidates are pre-filtered by duration (indexed, cheap). Only sources
    with computed fingerprints compete, thresholds are strict by default, and
    the audio stream identity must match - video-only perceptual matching
    alone can false-match files that share visuals but differ in content.
    """
    if not cfg.similarity_reuse or not phash_frames:
        return None
    lo = max(0.0, duration_s - cfg.sim_duration_tol)
    hi = duration_s + cfg.sim_duration_tol
    candidates = await db.fetch(
        """
        SELECT m.id, m.sha256, m.duration_s, m.phash, ar.id AS archive_id
        FROM media_assets m
        JOIN archive_records ar
          ON ar.source_media_id = m.id
         AND ar.profile = $2 AND ar.profile_version = $3
         AND ar.status IN ('active', 'no_gain')
        WHERE m.fingerprinted
          AND m.duration_s BETWEEN $4 AND $5
          AND m.sha256 IS DISTINCT FROM $1
          AND coalesce(m.acodec, '') = coalesce($6, '')
          AND coalesce(m.audio_channels, 0) = coalesce($7, 0)
        ORDER BY ar.created_at DESC
        LIMIT 50
        """,
        sha256,
        profile,
        version,
        lo,
        hi,
        acodec or "",
        audio_channels or 0,
    )
    best = None
    best_score: tuple[float, int] | None = None
    for row in candidates:
        frames = _load_frames(row["phash"])
        dist = media_mod.phash_distance(phash_frames, frames)
        if dist is None:
            continue
        mean_d, max_d = dist
        if mean_d <= cfg.sim_mean_max and max_d <= cfg.sim_max_single:
            if best_score is None or (mean_d, max_d) < best_score:
                best_score = (mean_d, max_d)
                best = row
    if best is None:
        return None
    log.info(
        "similarity candidate accepted",
        extra={
            "event": "dedup_similarity",
            "detail": f"mean={best_score[0]:.1f} max={best_score[1]} sha={best['sha256'][:12]}",
        },
    )
    return best
