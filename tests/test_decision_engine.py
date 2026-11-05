"""Unit tests for oxmit.decision_engine."""

import pytest
from oxmit.decision_engine import (
    EncodingDecision,
    can_copy_audio,
    can_smart_bypass,
    detect_content_category,
    is_already_compressed,
    make_decision,
    select_adaptive_resolution,
    select_educational_resolution,
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
    # Verify owner mandate: downscaled to 480p, 1-pass veryfast for maximum speed
    assert dec.target_width == 854
    assert dec.target_height == 480
    assert dec.two_pass is False
    assert dec.profile_params["preset"] == "veryfast"


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


def test_select_educational_resolution_greater_than_480p():
    # 1080p (1920x1080) -> 854x480 Lanczos
    w, h, filt = select_educational_resolution(1920, 1080)
    assert w == 854 and h == 480
    assert "lanczos" in filt
    assert "854" in filt

    # 720p (1280x720) -> 854x480 Lanczos
    w, h, filt = select_educational_resolution(1280, 720)
    assert w == 854 and h == 480
    assert "lanczos" in filt

    # 4K (3840x2160) -> 854x480 Lanczos
    w, h, filt = select_educational_resolution(3840, 2160)
    assert w == 854 and h == 480
    assert "lanczos" in filt

    # 4:3 1024x768 -> 640x480 Lanczos
    w, h, filt = select_educational_resolution(1024, 768)
    assert w == 640 and h == 480
    assert "lanczos" in filt

    # Portrait 1080x1920 -> 480x854 Lanczos
    w, h, filt = select_educational_resolution(1080, 1920)
    assert w == 480 and h == 854
    assert "lanczos" in filt


def test_select_educational_resolution_480p_downscales_to_360p_with_unsharp():
    # 854x480 -> 640x360 with Lanczos + unsharp font sharpening
    w, h, filt = select_educational_resolution(854, 480)
    assert w == 640 and h == 360
    assert "lanczos" in filt
    assert "unsharp" in filt

    # 4:3 640x480 -> 480x360 with Lanczos + unsharp
    w, h, filt = select_educational_resolution(640, 480)
    assert w == 480 and h == 360
    assert "lanczos" in filt
    assert "unsharp" in filt

    # Portrait 480x854 -> 360x640 with Lanczos + unsharp
    w, h, filt = select_educational_resolution(480, 854)
    assert w == 360 and h == 640
    assert "lanczos" in filt
    assert "unsharp" in filt


def test_select_educational_resolution_preserves_native_at_or_below_360p():
    # 360p (640x360) -> preserve native, no filter
    w, h, filt = select_educational_resolution(640, 360)
    assert w == 640 and h == 360
    assert filt == ""

    # 240p (426x240) -> preserve native
    w, h, filt = select_educational_resolution(426, 240)
    assert w == 426 and h == 240
    assert filt == ""

    # Invalid input
    w, h, filt = select_educational_resolution(0, 0)
    assert w == 0 and h == 0 and filt == ""


def test_make_decision_educational_mode():
    probe_1080p = {
        "filename": "university_lecture_ch1.mp4",
        "width": 1920,
        "height": 1080,
        "duration_s": 3600.0,
        "vcodec": "h264",
        "acodec": "aac",
        "audio_bitrate_kbps": 192,
        "size_bytes": 1000 * 1024 * 1024,
    }

    # 1. 1080p educational video -> downscale to 480p, edu480 profile, veryfast, voice audio
    dec = make_decision(
        probe=probe_1080p,
        profile_key="educational",
        size_bytes=1000 * 1024 * 1024,
    )
    assert dec.action == "transcode"
    assert dec.effective_profile == "edu480"
    assert dec.target_width == 854
    assert dec.target_height == 480
    assert "lanczos" in dec.scale_filter
    assert dec.profile_params["preset"] == "veryfast"
    assert dec.profile_params["crf"] == "25"
    assert dec.profile_params["audio_bitrate"] == "64k"
    assert dec.audio_action == "encode"  # Re-encode 192k audio to 64k voice

    # 2. 480p educational video -> downscale to 360p, edu360 profile with unsharp
    probe_480p = {
        "filename": "python_tutorial_480.mp4",
        "width": 854,
        "height": 480,
        "duration_s": 1800.0,
        "vcodec": "h264",
        "acodec": "aac",
        "audio_bitrate_kbps": 128,
        "size_bytes": 200 * 1024 * 1024,
    }
    dec_480 = make_decision(
        probe=probe_480p,
        profile_key="educational",
        size_bytes=200 * 1024 * 1024,
    )
    assert dec_480.action == "transcode"
    assert dec_480.effective_profile == "edu360"
    assert dec_480.target_width == 640
    assert dec_480.target_height == 360
    assert "unsharp" in dec_480.scale_filter
    assert "unsharp" in dec_480.profile_params.get("vf", "")
    assert dec_480.profile_params["preset"] == "veryfast"
    assert dec_480.profile_params["crf"] == "26"
    assert dec_480.profile_params["audio_bitrate"] == "48k"

    # 3. 360p educational video -> preserve native resolution
    probe_360p = {
        "filename": "slide_360p.mp4",
        "width": 640,
        "height": 360,
        "duration_s": 600.0,
        "vcodec": "h264",
        "acodec": "aac",
        "size_bytes": 50 * 1024 * 1024,
    }
    dec_360 = make_decision(
        probe=probe_360p,
        profile_key="educational",
        size_bytes=50 * 1024 * 1024,
    )
    assert dec_360.effective_profile == "edu360"
    assert dec_360.target_width == 640
    assert dec_360.target_height == 360
    assert dec_360.scale_filter is None

    # 4. Educational mode never smart bypasses
    assert can_smart_bypass(probe_1080p, "educational", target_mb=None, size_bytes=1000 * 1024 * 1024) is False
    assert can_smart_bypass(probe_1080p, "rostam", target_mb=None, size_bytes=1000 * 1024 * 1024) is False


def test_is_already_compressed():
    # 1080p with very low bitrate (500 kbps) -> already compressed
    probe_dense = {
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "bitrate": 500000,
        "duration_s": 120.0,
    }
    is_comp, reason = is_already_compressed(probe_dense)
    assert is_comp is True
    assert "1080p" in reason

    # 1080p high bitrate (4000 kbps) -> not compressed
    probe_raw = {
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "bitrate": 4000000,
        "duration_s": 120.0,
    }
    is_comp, _ = is_already_compressed(probe_raw)
    assert is_comp is False

    # 480p with 180 kbps -> already compressed
    probe_480_dense = {
        "width": 854,
        "height": 480,
        "fps": 25.0,
        "bitrate": 180000,
        "duration_s": 60.0,
    }
    is_comp, reason = is_already_compressed(probe_480_dense)
    assert is_comp is True
    assert "480p" in reason


def test_make_decision_rostam():
    probe_1080p = {
        "filename": "compressed_lecture.mp4",
        "width": 1920,
        "height": 1080,
        "duration_s": 1200.0,
        "vcodec": "h264",
        "acodec": "aac",
        "audio_bitrate_kbps": 128,
        "bitrate": 400000,
        "size_bytes": 60 * 1024 * 1024,
    }
    dec = make_decision(
        probe=probe_1080p,
        profile_key="rostam",
        size_bytes=60 * 1024 * 1024,
    )
    assert dec.action == "transcode"
    assert dec.effective_profile == "rostam"
    assert dec.target_width == 640
    assert dec.target_height == 360
    assert dec.profile_params["crf"] == "32"
    assert dec.profile_params["preset"] == "superfast"
    assert "hqdn3d" in dec.profile_params["vf"]
    assert "unsharp" in dec.profile_params["vf"]
    assert dec.profile_params["audio_bitrate"] == "32k"


