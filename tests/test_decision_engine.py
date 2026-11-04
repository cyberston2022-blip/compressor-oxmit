"""Unit tests for oxmit.decision_engine."""

import pytest
from oxmit.decision_engine import (
    EncodingDecision,
    can_copy_audio,
    can_smart_bypass,
    detect_content_category,
    make_decision,
    select_adaptive_resolution,
)


def test_detect_content_category_keywords():
    assert detect_content_category({"filename": "zoom_lecture_01.mp4"}) == "screen_text"
    assert detect_content_category({"filename": "obs_screen_record.mkv"}) == "screen_text"
    assert detect_content_category({"filename": "slide_presentation.mp4"}) == "screen_text"


def test_detect_content_category_low_bpp():
    # 1080p30 with very low bitrate (300 kbps) -> bpp = 300000 / (1920*1080*30) = 0.0048 < 0.04
    probe = {
        "filename": "documentary.mp4",
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "bitrate": 300000,
        "duration_s": 60.0,
    }
    assert detect_content_category(probe) == "screen_text"


def test_detect_content_category_film():
    probe = {
        "filename": "movie_sample.mp4",
        "width": 1920,
        "height": 1080,
        "fps": 23.976,
        "bitrate": 8000000,
        "duration_s": 120.0,
    }
    assert detect_content_category(probe) == "film_motion"


def test_detect_content_category_general():
    probe = {
        "filename": "vacation_video.mp4",
        "width": 1280,
        "height": 720,
        "fps": 30.0,
        "bitrate": 3000000,
        "duration_s": 45.0,
    }
    assert detect_content_category(probe) == "general"


def test_can_smart_bypass():
    probe_ok = {
        "vcodec": "h264",
        "acodec": "aac",
        "pix_fmt": "yuv420p",
        "container": "mov,mp4,m4a,3gp,3g2,mj2",
        "rotation": 0,
    }
    # File is 8MB, user requested target_mb=10 -> Already meets constraint!
    assert can_smart_bypass(probe_ok, "custom", target_mb=10, size_bytes=8 * 1024 * 1024) is True

    # File is 15MB, user requested target_mb=10 -> Must compress
    assert can_smart_bypass(probe_ok, "custom", target_mb=10, size_bytes=15 * 1024 * 1024) is False

    # Incompatible codec (HEVC / VP9) -> Must transcode
    probe_hevc = dict(probe_ok, vcodec="hevc")
    assert can_smart_bypass(probe_hevc, "custom", target_mb=10, size_bytes=8 * 1024 * 1024) is False

    # Rotated video -> Must transcode to fix orientation
    probe_rot = dict(probe_ok, rotation=90)
    assert can_smart_bypass(probe_rot, "custom", target_mb=10, size_bytes=8 * 1024 * 1024) is False


def test_can_copy_audio():
    assert can_copy_audio({"acodec": "aac", "audio_channels": 2, "audio_sample_rate": 48000, "audio_bitrate_kbps": 128}) is True
    assert can_copy_audio({"acodec": "aac", "audio_channels": 1, "audio_sample_rate": 44100, "audio_bitrate_kbps": 96}) is True
    # Opus or Vorbis cannot be direct copied into strict MP4 AAC requirement
    assert can_copy_audio({"acodec": "opus", "audio_channels": 2, "audio_sample_rate": 48000, "audio_bitrate_kbps": 128}) is False
    # Excessive bitrate (>192 kbps) should be re-encoded to save space
    assert can_copy_audio({"acodec": "aac", "audio_channels": 2, "audio_sample_rate": 48000, "audio_bitrate_kbps": 320}) is False


def test_select_adaptive_resolution():
    # 4K downscales to 1080p
    w, h, filt = select_adaptive_resolution(3840, 2160, 2000, "general")
    assert w == 1920 and h == 1080

    # 1080p at low bitrate (500 kbps) for general video downscales to 720p
    w, h, filt = select_adaptive_resolution(1920, 1080, 500, "general")
    assert w == 1280 and h == 720

    # CRITICAL OWNER REQUIREMENT: Screen text at 1080p is NEVER downscaled to preserve text legibility
    w, h, filt = select_adaptive_resolution(1920, 1080, 500, "screen_text")
    assert w is None and h is None and filt is None

    # 720p at low bitrate is preserved, never downscaled or upscaled
    w, h, filt = select_adaptive_resolution(1280, 720, 300, "general")
    assert w is None and h is None and filt is None


def test_make_decision_custom_profile():
    probe = {
        "filename": "camera_clip.mp4",
        "width": 1920,
        "height": 1080,
        "duration_s": 60.0,
        "vcodec": "h264",
        "acodec": "aac",
        "pix_fmt": "yuv420p",
        "container": "mp4",
        "rotation": 0,
    }
    # 20MB file requested target 10MB -> Transcode
    dec = make_decision(
        probe=probe,
        profile_key="custom",
        size_bytes=20 * 1024 * 1024,
        target_mb=10,
    )
    assert dec.action == "transcode"
    assert dec.effective_profile == "custom"
    assert "bv" in dec.profile_params
    assert "mr" in dec.profile_params
    assert "bs" in dec.profile_params


def test_make_decision_balanced_speed_upgrade():
    probe = {"filename": "clip.mov", "duration_s": 30.0}
    dec = make_decision(probe=probe, profile_key="balanced", size_bytes=50 * 1024 * 1024)
    assert dec.effective_profile == "balanced"
    assert dec.profile_params["preset"] == "veryfast"
    assert dec.profile_params["crf"] == "22"


def test_make_decision_maxcomp_avoids_cliff():
    probe = {"filename": "clip.mov", "duration_s": 30.0}
    dec = make_decision(probe=probe, profile_key="maxcomp", size_bytes=50 * 1024 * 1024)
    assert dec.effective_profile == "maxcomp"
    # Presets must be superfast or faster, avoiding the 0.58x medium cliff
    assert dec.profile_params["preset"] in ("superfast", "faster")
    assert dec.profile_params["crf"] == "30"
