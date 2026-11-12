"""Quality hierarchy (quality.py): pure logic, no DB.

Covers the spec rules: never upscale, strictly-lower-than-cache offers,
unverifiable inputs never yield offers, output-resolution validation.
"""
from oxmit.quality import (
    allowed_profiles,
    allowed_profiles_for_source,
    effective_short_side,
    group_versions,
    pick_best_version,
    resolution_note,
    version_short_side,
)

ALL_KEYS = ["level", "level265", "balanced", "highq", "small", "maxcomp",
            "tgcompat", "r1080", "r720", "r480", "educational", "edu480",
            "edu360", "rostam", "custom", "custom_2pass", "remux"]


def test_effective_short_side_scaling_never_upscale():
    assert effective_short_side("r720", 1920, 1080) == 720
    assert effective_short_side("r1080", 1280, 720) == 720   # capped by source
    assert effective_short_side("r480", 640, 360) == 360     # capped by source


def test_effective_short_side_keep_resolution():
    assert effective_short_side("balanced", 1920, 1080) == 1080
    assert effective_short_side("level", 854, 480) == 480


def test_effective_short_side_unknown_source_is_none():
    assert effective_short_side("r480", None, None) is None
    assert effective_short_side("balanced", 0, 1080) is None
    assert effective_short_side("nope", 1920, 1080) is None


def test_version_short_side():
    assert version_short_side(1920, 1080) == 1080
    assert version_short_side(480, 854) == 480
    assert version_short_side(None, 720) is None
    assert version_short_side(0, 0) is None


def test_allowed_profiles_spec_scenario():
    # Spec example: source 720p, cached 480p -> only 360p-tier may be offered.
    allowed = allowed_profiles(ALL_KEYS, 1280, 720, 480)
    assert set(allowed) == {"edu360", "rostam"}
    assert "r480" not in allowed      # equal tier is not strictly lower
    assert "r720" not in allowed      # would need a source we no longer trust
    assert "r1080" not in allowed
    assert "remux" not in allowed     # original, never "lower"
    assert "custom" not in allowed    # unverifiable target at grid time
    assert "level" not in allowed     # keeps source resolution (higher than cache)


def test_allowed_profiles_fullres_cache():
    # Cached version came from a keep-resolution profile at source tier:
    # every scaling profile strictly below the source short side is valid.
    allowed = allowed_profiles(ALL_KEYS, 1920, 1080, 1080)
    assert set(allowed) == {"r720", "r480", "edu480", "educational", "edu360", "rostam"}


def test_allowed_profiles_never_upscale_portrait():
    # Portrait source narrower than the target width must not offer the tier.
    allowed = allowed_profiles(["r480", "edu360"], 360, 640, None)
    assert allowed == []


def test_allowed_profiles_unknown_cache_short_circuits():
    assert allowed_profiles(ALL_KEYS, 1920, 1080, None) == []
    assert allowed_profiles(ALL_KEYS, 1920, 1080, 0) == []


def test_allowed_profiles_for_source_no_cache():
    allowed = allowed_profiles_for_source(ALL_KEYS, 1280, 720)
    # everything feasible except internal/unrankable profiles
    assert "remux" not in allowed
    assert "custom" not in allowed
    assert "custom_2pass" not in allowed
    assert "level265" not in allowed
    assert "r480" in allowed and "rostam" in allowed and "balanced" in allowed


def _ver(profile, w, h, bitrate=None, size=1000, status="active", created=None):
    return {"profile": profile, "profile_version": 1, "status": status,
            "archive_ids": ["a1"], "out_w": w, "out_h": h, "out_size": size,
            "out_duration": 60.0, "out_vcodec": "h264", "out_acodec": "aac",
            "out_bitrate": bitrate, "out_tg_file_id": "f", "created_at": created}


def test_pick_best_version_prefers_highest_resolution_then_bitrate():
    versions = [_ver("r480", 854, 480, bitrate=800),
                _ver("r720", 1280, 720, bitrate=500),
                _ver("level", 1280, 720, bitrate=900)]
    best = pick_best_version(versions)
    assert best["profile"] == "level"   # same short side as r720, higher bitrate


def test_pick_best_version_skips_unprobed():
    versions = [{"profile": "x", "out_w": None, "out_h": None},
                _ver("r480", 854, 480, bitrate=800)]
    assert pick_best_version(versions)["profile"] == "r480"
    assert pick_best_version([]) is None
    assert pick_best_version([{"profile": "x", "out_w": None, "out_h": None}]) is None


def test_group_versions_merges_split_parts():
    rows = [
        {"id": "p1", "profile": "r480", "profile_version": 1, "status": "active",
         "out_w": 854, "out_h": 480, "out_size": 500, "out_duration": 30.0,
         "out_vcodec": "h264", "out_acodec": "aac", "out_bitrate": 900,
         "out_tg_file_id": "f1", "created_at": 1},
        {"id": "p2", "profile": "r480", "profile_version": 1, "status": "active",
         "out_w": 854, "out_h": 480, "out_size": 400, "out_duration": 30.0,
         "out_vcodec": "h264", "out_acodec": "aac", "out_bitrate": 900,
         "out_tg_file_id": "f1", "created_at": 1},
        {"id": "p3", "profile": "r720", "profile_version": 1, "status": "active",
         "out_w": 1280, "out_h": 720, "out_size": 800, "out_duration": 60.0,
         "out_vcodec": "h264", "out_acodec": "aac", "out_bitrate": 1500,
         "out_tg_file_id": "f2", "created_at": 2},
    ]
    versions = group_versions(rows)
    assert len(versions) == 2
    r480 = next(v for v in versions if v["profile"] == "r480")
    assert r480["out_size"] == 900
    assert r480["archive_ids"] == ["p1", "p2"]


def test_group_versions_propagates_missing_status():
    rows = [
        {"id": "p1", "profile": "r480", "profile_version": 1, "status": "active",
         "out_w": 854, "out_h": 480, "out_size": 500, "out_duration": 30.0,
         "out_vcodec": "h264", "out_acodec": "aac", "out_bitrate": 900,
         "out_tg_file_id": "f1", "created_at": 1},
        {"id": "p2", "profile": "r480", "profile_version": 1, "status": "missing",
         "out_w": 854, "out_h": 480, "out_size": 400, "out_duration": 30.0,
         "out_vcodec": "h264", "out_acodec": "aac", "out_bitrate": 900,
         "out_tg_file_id": "f1", "created_at": 1},
    ]
    r480 = group_versions(rows)[0]
    assert r480["status"] == "missing"


def test_resolution_note_flags_oversized_output():
    note = resolution_note("r480", 1280, 720)
    assert note is not None and "480" in note
    assert resolution_note("r480", 854, 480) is None
    assert resolution_note("r480", 856, 482) is None   # within tolerance
    assert resolution_note("balanced", 1920, 1080) is None
    assert resolution_note("r480", None, None) is None
