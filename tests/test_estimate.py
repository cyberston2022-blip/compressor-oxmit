"""Unit tests: estimate module must be total (never raise) and well-formed."""
import pytest

from oxmit.estimate import (estimate_encode_seconds, estimate_output_bytes,
                            format_size_range, format_time_range)
from oxmit.profiles import ESTIMATE_PARAMS


def test_output_bytes_well_formed_for_all_profiles_and_levels():
    for codec, crf, preset, target in ESTIMATE_PARAMS.values():
        for level in range(1, 21):
            low, high = estimate_output_bytes(
                600.0, 1280 * 720, codec, crf, audio_kbps=128, source_bytes=100 << 20)
            assert 0 <= low <= high
            slo, shi = estimate_encode_seconds(600.0, 1280 * 720, codec, preset)
            assert 0 <= slo <= shi


def test_estimate_totals_never_raise():
    assert estimate_output_bytes(None, 1, "h264", 23) == (0, 0)
    assert estimate_output_bytes(-5, 0, "h264", 23) == (0, 0)
    assert estimate_encode_seconds(None, 1, "hevc", "faster") == (0, 0)


def test_source_floor_and_ceiling():
    low, high = estimate_output_bytes(
        60.0, 1920 * 1080, "h264", 18, audio_kbps=128, source_bytes=10 << 20)
    assert low >= (10 << 20) * 0.04 - 1  # floor ratio respected
    assert high <= (10 << 20) * 3.0 + 1


def test_h264_bpp_calibrated_to_production():
    # 2026-11-14 calibration: 0.055 bpp at CRF 23 (~0.042 at CRF 25), set to
    # the measured HIGH edge from 15 production jobs (0.036 bpp at CRF 25).
    # A 1-hour 854x480@25 lecture must predict ~0.15-0.22 GB low edge -
    # the old generic 0.12 bpp rule predicted ~0.5 GB and caused no-gain
    # skips of files that really compressed 25-75%.
    low, high = estimate_output_bytes(
        3600.0, 854 * 480, "h264", 25, audio_kbps=64, source_bytes=0)
    assert 150_000_000 <= low <= 220_000_000
    assert low < high


def test_bpp_base_override_is_honored():
    # edu480.predict_guard passes cfg.estimate_bpp_h264 through; a large
    # base must raise the prediction (conservative guard), a tiny one lower it.
    mid_lo, _ = estimate_output_bytes(600.0, 854 * 480, "h264", 25,
                                      audio_kbps=64, source_bytes=0)
    big_lo, _ = estimate_output_bytes(600.0, 854 * 480, "h264", 25,
                                      audio_kbps=64, source_bytes=0, bpp_base=0.30)
    tiny_lo, _ = estimate_output_bytes(600.0, 854 * 480, "h264", 25,
                                       audio_kbps=64, source_bytes=0, bpp_base=0.01)
    assert tiny_lo < mid_lo < big_lo


def test_encode_seconds_calibrated_to_benchmark():
    # 2026-11-14: the owner's real 1h54m 720p lecture encoded a 240s segment
    # in ~37s wall on the production worker (6.5x realtime at 480p veryfast).
    # The whole file must estimate ~18 min, not hours (old model said 83min+).
    low, high = estimate_encode_seconds(6883.0, 409600, "h264", "veryfast")
    assert 400 <= low <= 1300
    assert high >= low
    assert high <= 6 * 3600


def test_format_helpers():
    text = format_size_range(1000, 2000)
    assert "1000" in text or "KB" in text
    assert format_time_range(30, 90)


def test_format_helpers_swap_reversed_input():
    assert format_size_range(2000, 1000)
    assert format_time_range(90, 30)
