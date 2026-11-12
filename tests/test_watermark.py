"""Watermark module: Argon-verified normalization, escaping, filters."""
from oxmit.watermark import (
    apply_watermark, build_video_filter, escape_drawtext, normalize_wm,
    uses_complex_filter,
)


def test_normalize_defaults():
    wm = normalize_wm(None)
    assert wm["type"] == "text" and wm["position"] == "top-right"
    assert wm["opacity"] == 0.5 and wm["font_size"] == 24
    assert wm["timing_mode"] == "always"


def test_normalize_clamps():
    wm = normalize_wm({"font_size": 999, "opacity": 5, "margin_left": -10,
                       "image_scale": 0.01, "start_time": 999999})
    assert wm["font_size"] == 100
    assert wm["opacity"] == 1.0
    assert wm["margin_left"] == 0
    assert wm["image_scale"] == 0.1
    assert wm["start_time"] == 86400


def test_degenerate_range_forces_always():
    """The exact Argon production bug: end<=start kept 'range' and rendered
    between(t,0,0) - one visible frame. Port must force 'always'."""
    wm = normalize_wm({"timing_mode": "range", "start_time": 0, "end_time": 0})
    assert wm["timing_mode"] == "always"


def test_interval_duration_clamped_under_period():
    wm = normalize_wm({"timing_mode": "interval", "interval_duration": 50,
                       "interval_period": 30})
    assert wm["interval_duration"] < wm["interval_period"]


def test_newlines_collapsed_and_length_clamped():
    wm = normalize_wm({"text": "a\nb" + "x" * 300})
    assert "\n" not in wm["text"] and len(wm["text"]) == 200


def test_escape_drawtext_argon_exact():
    assert escape_drawtext("a:b,c%d\\e'f") == "a\\:b\\,c\\%d\\\\ef"
    # Argon behavior: newline -> space
    assert escape_drawtext("line1\nline2") == "line1 line2"


def _wm(**over):
    return normalize_wm(over)


def test_text_filter_positions(tmp_path):
    f = build_video_filter(_wm(position="top-left"), image_path=None,
                           font_path=None)
    assert f.startswith("drawtext=") and ":x=10:y=10" in f
    font = tmp_path / "custom.ttf"
    font.write_bytes(b"x")
    f = build_video_filter(_wm(position="bottom-right", margin_right=22,
                               margin_bottom=33), image_path=None,
                           font_path=str(font))
    assert ":x=W-w-22" in f and ":y=H-h-33" in f
    assert "fontfile='" in f and "/custom.ttf" in f
    assert "white@0.5" in f and "black@0.5" in f and "boxborderw=5" in f


def test_text_filter_timing_range():
    f = build_video_filter(_wm(timing_mode="range", start_time=5, end_time=9),
                           image_path=None, font_path="/x.ttf")
    assert "enable='between(t,5,9)'" in f


def test_image_filter_is_complex_and_uses_movie(tmp_path):
    img = tmp_path / "wm.png"
    img.write_bytes(b"x")
    wm = _wm(type="image", image_scale=0.25)
    f = build_video_filter(wm, image_path=str(img), font_path=None)
    assert f is not None
    assert uses_complex_filter(f)
    assert "movie=" in f and "scale=iw*0.25:-1" in f
    assert "colorchannelmixer=aa=0.5" in f and "[0:v][wm]overlay" in f


def test_missing_image_returns_none_not_error():
    assert build_video_filter(_wm(type="image"), image_path=None,
                              font_path=None) is None


def test_text_escaping_in_filter():
    f = build_video_filter(_wm(text="hello: world, 100%"), image_path=None,
                           font_path="/x.ttf")
    assert "text='hello\\: world\\, 100\\%'" in f
