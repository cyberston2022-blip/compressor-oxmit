"""Merge service: strategy decision, normalization target, stale cleanup.
DB-backed ordering itself (atomic seq) is covered by the SQL constraints;
these tests pin the pure decision logic that picks the ffmpeg strategy.
"""
import pytest

from oxmit.merge import MergeError, decide_strategy, normalize_target


def _probe(**over):
    base = {"vcodec": "h264", "acodec": "aac", "width": 1280, "height": 720,
            "fps": 30.0, "pix_fmt": "yuv420p", "sample_rate": 48000,
            "channels": 2}
    base.update(over)
    return base


def test_compatible_streams_copy():
    probes = [_probe(), _probe(), _probe()]
    assert decide_strategy(probes) == ("copy", "streams compatible")


def test_resolution_mismatch_reencodes():
    probes = [_probe(), _probe(width=1920, height=1080)]
    strategy, why = decide_strategy(probes)
    assert strategy == "reencode"
    assert "width" in why


def test_codec_mismatch_reencodes():
    probes = [_probe(), _probe(vcodec="hevc")]
    assert decide_strategy(probes)[0] == "reencode"


def test_audio_presence_mismatch_reencodes():
    probes = [_probe(), _probe(acodec=None)]
    strategy, why = decide_strategy(probes)
    assert strategy == "reencode"
    assert "audio presence" in why


def test_fps_mismatch_reencodes():
    probes = [_probe(), _probe(fps=25.0)]
    assert decide_strategy(probes)[0] == "reencode"


def test_fps_within_tolerance_copies():
    probes = [_probe(fps=29.97), _probe(fps=29.97)]
    assert decide_strategy(probes)[0] == "copy"


def test_pix_fmt_mismatch_reencodes():
    probes = [_probe(), _probe(pix_fmt="yuv420p10le")]
    assert decide_strategy(probes)[0] == "reencode"


def test_single_input_and_empty_reencode():
    assert decide_strategy([_probe()])[0] == "reencode"
    assert decide_strategy([])[0] == "reencode"


def test_normalize_target_takes_minimum():
    probes = [_probe(width=1920, height=1080, fps=30.0),
              _probe(width=1280, height=720, fps=25.0),
              _probe(width=854, height=480, fps=30.0)]
    target = normalize_target(probes)
    assert target["width"] == 854
    assert target["height"] == 480
    assert target["fps"] == 25.0


def test_normalize_target_no_dims_is_safe():
    target = normalize_target([{"vcodec": "h264"}])
    assert target["width"] is None and target["fps"] is None


async def test_fail_stale_sessions_handles_null(fake_db):
    """Sweep hygiene must not crash when the DB returns NULL."""
    from oxmit.merge import fail_stale_sessions
    assert await fail_stale_sessions(fake_db, stale_hours=24) == 0
