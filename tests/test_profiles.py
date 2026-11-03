"""Unit tests: profiles (CRF ladder, target params, no-upscale variant)."""
from oxmit.profiles import (compute_target_params, crf_for_level,
                            preset_for_level, resolve_variant)


def test_crf_ladder_bounds_and_monotonic():
    assert crf_for_level(1) == 18
    assert crf_for_level(20) == 28
    values = [crf_for_level(l) for l in range(1, 21)]
    assert all(b >= a for a, b in zip(values, values[1:]))


def test_preset_ladder():
    assert preset_for_level(1) == "veryfast"
    assert preset_for_level(6) == "veryfast"
    assert preset_for_level(7) == "faster"
    assert preset_for_level(20) == "faster"


def test_compute_target_params_validation():
    assert compute_target_params(0, 60.0, 1 << 30)[1] == "bad_target"
    assert compute_target_params(1025, 60.0, 1 << 30)[1] == "bad_target"  # > source (1024 MB)
    assert compute_target_params(100, None, 1 << 30)[1] == "bad_target"   # no duration
    kbps, status = compute_target_params(100, 600.0, 200 << 20)
    assert status is None and kbps > 0
    # below quality floor -> clamped + flagged
    kbps, status = compute_target_params(2, 3600.0, 4 << 30, min_video_kbps=200)
    assert status == "low_bitrate" and kbps == 200


def test_resolve_variant_never_upscales():
    # 720p source asking for 1080p must downgrade, not upscale
    assert resolve_variant("r1080", 1280, 720) == "r720"
    # exact fit keeps the variant
    assert resolve_variant("r1080", 1920, 1080) == "r1080"
    # portrait narrow width cannot hit any width target
    assert resolve_variant("r1080", 720, 1280) == "balanced"
    # non-resolution profiles pass through unchanged
    assert resolve_variant("balanced", 640, 360) == "balanced"
    # unknown dimensions -> safe fallback
    assert resolve_variant("r720", None, None) == "balanced"
