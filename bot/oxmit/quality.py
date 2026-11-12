"""Centralized quality hierarchy for cached-version reuse.

Single source of truth for the questions every caller must answer the same
way (intake grid, cache offers, degraded-source fallback):

- What output quality would profile X actually produce from source S?
- Which stored derivative is the best already-compressed version?
- Which profiles may still be offered once a cached version exists?
  (strictly lower than the cache, never upscaling, never claiming a
  quality the source cannot deliver)

All functions are pure so they can be unit-tested without a database.
"""
from __future__ import annotations

from .profiles import BY_KEY, Profile

# Profiles that never re-encode below the source tier or whose output
# quality cannot be ranked against a cached version at offer time:
# - remux delivers the original (never "lower" than any cached version);
# - custom/custom_2pass target an arbitrary size the grid cannot verify;
# - level265 is an internal escalation, never user-selected.
_NON_OFFERABLE = frozenset({"remux", "custom", "custom_2pass", "level265"})

# Odd-dimension tolerance when validating an output's actual short side
# (rounding to /2 and mod-2 scalers make exact equality unreliable).
RES_TOLERANCE_PX = 8


def effective_short_side(profile_key: str, src_w: int | None, src_h: int | None) -> int | None:
    """Short side a profile would actually produce from the given source.

    Scaling profiles cap at their target (never upscaling: the effective
    value is the min of target and source). Keep-resolution profiles keep
    the source short side. Unknown source dimensions return None - the
    caller must treat "unknown" as "cannot verify, do not offer".
    """
    prof = BY_KEY.get(profile_key)
    if prof is None:
        return None
    if prof.max_short_side == 0:
        if not src_w or not src_h or src_w <= 0 or src_h <= 0:
            return None
        return min(src_w, src_h)
    if not src_w or not src_h or src_w <= 0 or src_h <= 0:
        return None
    return min(prof.max_short_side, min(src_w, src_h))


def version_short_side(out_w: int | None, out_h: int | None) -> int | None:
    """Actual short side of a stored derivative (from its probed dims)."""
    if not out_w or not out_h or out_w <= 0 or out_h <= 0:
        return None
    return min(out_w, out_h)


def group_versions(rows: list) -> list[dict]:
    """Collapse split-part archive rows into one entry per cached version.

    Input rows (from dedup.find_cached_versions) carry per-part metadata;
    parts of one version share dims/codecs and their sizes add up.
    Returns dicts with the fields the offer card and hierarchy need.
    """
    groups: dict[tuple, dict] = {}
    order: list[tuple] = []
    for r in rows:
        key = (r["profile"], r["profile_version"])
        if key not in groups:
            groups[key] = {
                "profile": r["profile"],
                "profile_version": r["profile_version"],
                "status": r["status"],
                "archive_ids": [],
                "out_w": r["out_w"],
                "out_h": r["out_h"],
                "out_size": 0,
                "out_duration": r["out_duration"],
                "out_vcodec": r["out_vcodec"],
                "out_acodec": r["out_acodec"],
                "out_bitrate": r["out_bitrate"],
                "out_tg_file_id": r["out_tg_file_id"],
                "created_at": r["created_at"],
            }
            order.append(key)
        g = groups[key]
        g["archive_ids"].append(r["id"])
        g["out_size"] += r["out_size"] or 0
        # An 'active' part outranks 'no_gain' for delivery; a version is
        # only deliverable if every part is deliverable, but downgrade the
        # label conservatively: any missing part -> missing version.
        if r["status"] == "missing":
            g["status"] = "missing"
    return [groups[k] for k in order]


def pick_best_version(versions: list[dict]) -> dict | None:
    """Best cached version: highest actual short side, then bitrate, then newest.

    Split parts and no_gain entries (whose stored output IS the source)
    rank naturally by their probed dims.
    """
    best: dict | None = None
    best_rank: tuple | None = None
    for v in versions:
        short = version_short_side(v.get("out_w"), v.get("out_h"))
        if short is None:
            continue
        ca = v.get("created_at")
        if hasattr(ca, "timestamp"):
            ts = float(ca.timestamp())
        elif isinstance(ca, (int, float)):
            ts = float(ca)
        else:
            ts = 0.0
        rank = (short, v.get("out_bitrate") or 0, ts)
        if best_rank is None or rank > best_rank:
            best, best_rank = v, rank
    return best


def allowed_profiles(profile_keys: list[str], src_w: int | None, src_h: int | None,
                     cached_short: int | None) -> list[str]:
    """Profiles that may be offered after the user declined a cached version.

    Rules enforced here (and nowhere else):
    - strictly lower quality than the best cached version (cached_short);
    - never upscaling: the profile's effective output short side must fit
      inside the real source dims;
    - unrankable profiles (remux, custom) and internal ones are excluded;
    - unknown source dims or unknown cache quality -> nothing is offered
      rather than guessing.
    """
    if not cached_short:
        return []
    allowed: list[str] = []
    for key in profile_keys:
        if key in _NON_OFFERABLE:
            continue
        eff = effective_short_side(key, src_w, src_h)
        if eff is None:
            continue
        if eff < cached_short:
            allowed.append(key)
    return allowed


def allowed_profiles_for_source(profile_keys: list[str], src_w: int | None,
                                src_h: int | None) -> list[str]:
    """Profiles valid for a source with no cache context (fresh encode).

    Still enforces no-upscaling and drops unrankable/internal profiles so
    the degraded-source grid cannot offer quality the (derivative) source
    does not have.
    """
    allowed: list[str] = []
    for key in profile_keys:
        if key in _NON_OFFERABLE:
            continue
        if effective_short_side(key, src_w, src_h) is not None:
            allowed.append(key)
    return allowed


def resolution_note(profile_key: str, out_w: int | None, out_h: int | None) -> str | None:
    """Warning when an output's actual short side exceeds the profile cap.

    Used by job completion to validate the real output against what the
    profile promised (the bot must never claim a quality tier the file
    does not have). Returns None when everything matches.
    """
    prof: Profile | None = BY_KEY.get(profile_key)
    actual = version_short_side(out_w, out_h)
    if prof is None or prof.max_short_side == 0 or actual is None:
        return None
    if actual > prof.max_short_side + RES_TOLERANCE_PX:
        return (f"output {actual}p exceeds profile cap {prof.max_short_side}p "
                f"({out_w}x{out_h})")
    return None
