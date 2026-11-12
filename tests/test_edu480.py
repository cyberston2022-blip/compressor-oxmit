"""EDU480 profile helpers: output naming, geometry, transcode decision, ETA."""
import pytest

from oxmit import edu480
from oxmit.config import Settings


# ---------------------------------------------------------------- naming
@pytest.mark.parametrize("raw,expected", [
    ("University Lecture 01", "University Lecture 01.mp4"),
    ("درس مهندسی برق", "درس مهندسی برق.mp4"),
    ("Lecture 01.mkv", "Lecture 01.mp4"),
    ("درس دانشگاه.mp4", "درس دانشگاه.mp4"),
    ("a.mkv.mp4", "a.mp4"),
    ("Lecture v1.2", "Lecture v1.2.mp4"),          # ".2" is not an extension
    ("  spaced   name  ", "spaced name.mp4"),
    ("../../etc/passwd", "passwd.mp4"),            # traversal: last segment only
    ("C:\\Users\\x\\video.avi", "video.mp4"),
    ('bad:*?"<>|name', "bad name.mp4"),
    ("می‌خواهم", "می‌خواهم.mp4"),                   # ZWNJ (U+200C) preserved
    ("evil\u202egnp.mp4", "evilgnp.mp4"),          # bidi override removed
    ("con", "_con.mp4"),
])
def test_output_filename(raw, expected):
    assert edu480.output_filename(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", ".mp4", "...", "/", "\u202e", None])
def test_empty_names_rejected(raw):
    assert edu480.normalize_output_name(raw) is None


def test_empty_name_falls_back_to_source_then_video():
    assert edu480.output_filename("", "orig clip.mov") == "orig clip.mp4"
    assert edu480.output_filename(None, None) == "video.mp4"


def test_name_length_limits():
    long_fa = "ب" * 300
    stem = edu480.normalize_output_name(long_fa)
    assert len(stem) <= edu480.NAME_MAX_CHARS
    assert len(stem.encode()) <= edu480.NAME_MAX_BYTES


# -------------------------------------------------------------- geometry
@pytest.mark.parametrize("w,h,expected", [
    (1920, 1080, (854, 480)),
    (1280, 720, (854, 480)),
    (1080, 1920, (480, 854)),      # portrait: SHORT side -> 480, not width 854
    (1440, 1080, (640, 480)),      # 4:3
    (854, 480, None),              # already 480p: untouched
    (640, 360, None),              # never upscaled
    (639, 359, (640, 360)),        # odd dims -> nearest even, no real resize
    (3840, 2160, (854, 480)),
])
def test_target_dims(w, h, expected):
    assert edu480.target_dims(w, h) == expected


def test_filters_fps_cap_and_passthrough():
    vf, fpsf = edu480.video_filters({"width": 1920, "height": 1080, "fps": 59.94}, 30)
    assert vf == "scale=854:480:flags=lanczos" and fpsf == "fps=30"
    vf, fpsf = edu480.video_filters({"width": 640, "height": 360, "fps": 25}, 30)
    assert (vf, fpsf) == ("null", "null")


def test_encode_params_are_strings_and_single_profile():
    cfg = Settings()
    p = edu480.encode_params({"width": 1280, "height": 720, "fps": 30}, cfg, 3)
    assert p == {"crf": "25", "preset": "veryfast", "threads": "3",
                 "vf": "scale=854:480:flags=lanczos", "fpsf": "null",
                 "audio_bitrate": "64k"}


# --------------------------------------------------------------- decision
def _probe(**kw):
    base = {"width": 854, "height": 480, "vcodec": "h264", "acodec": "aac",
            "pix_fmt": "yuv420p", "fps": 25, "duration_s": 600,
            "bitrate": 600_000, "audio_bitrate": 64_000}
    base.update(kw)
    return base


def test_compliant_480p_is_remuxed_not_encoded():
    assert edu480.decide(_probe(), 45 << 20, Settings()).action == "remux"


@pytest.mark.parametrize("override,reason_part", [
    ({"bitrate": 3_000_000}, "bitrate"),           # 480p can still be heavy
    ({"width": 1280, "height": 720}, "above 480p"),
    ({"vcodec": "hevc"}, "codec"),
    ({"acodec": "opus"}, "audio"),
    ({"fps": 60}, "fps"),
    ({"pix_fmt": "yuv444p"}, "pixel"),
])
def test_non_compliant_sources_are_encoded(override, reason_part):
    d = edu480.decide(_probe(**override), 100 << 20, Settings())
    assert d.action == "encode" and reason_part in d.reason


def test_small_low_bitrate_720p_is_not_assumed_compressed():
    # Low size/bitrate alone never proves EDU480 compliance (spec #6).
    d = edu480.decide(_probe(width=1280, height=720, bitrate=300_000), 5 << 20, Settings())
    assert d.action == "encode"


# -------------------------------------------------------------------- ETA
def test_eta_scales_with_workload_and_slots():
    low1, high1 = edu480.eta_range([3600, 3600], 0, 1, 0.25)
    low2, high2 = edu480.eta_range([3600, 3600], 0, 2, 0.25)
    assert high1 > high2 and low1 > low2
    assert low1 <= 1800 <= high1               # 2h of media * 0.25 = 30 min
    # a 10-minute video ahead costs far less than a 4-hour one
    assert edu480.eta_range([600], 0, 1, 0.25)[1] < edu480.eta_range([14400], 0, 1, 0.25)[1]


def test_eta_empty_queue_is_zero():
    assert edu480.eta_range([], 0, 2, 0.25) == (0, 0)


def test_eta_formatting_fa():
    assert edu480.fmt_eta_range_fa(0, 30) == "کمتر از ۱ دقیقه"
    assert "ساعت" in edu480.fmt_eta_range_fa(3600, 5400)
