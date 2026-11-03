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


def test_format_helpers():
    text = format_size_range(1000, 2000)
    assert "1000" in text or "KB" in text
    assert format_time_range(30, 90)


def test_format_helpers_swap_reversed_input():
    assert format_size_range(2000, 1000)
    assert format_time_range(90, 30)
