"""Unit tests: media helpers (sanitize, sizes, compat gates)."""
from oxmit.media import hamming, human_size, remux_compatible, sanitize_filename


def test_sanitize_filename():
    assert sanitize_filename(None) == "video"
    assert sanitize_filename("") == "video"
    traversal = sanitize_filename("../../../etc/passwd")
    assert "/" not in traversal and "\\" not in traversal  # no traversal
    assert traversal == "etc_passwd"
    assert sanitize_filename("My Video (2024) [1080p].mkv") == "My Video (2024) [1080p].mkv"
    out = sanitize_filename("x" * 200, limit=64)
    assert len(out) <= 64


def test_sanitize_keeps_persian_word_chars():
    # isalnum() covers Persian letters — they must survive
    assert sanitize_filename("ویدیو مهم.mp4") == "ویدیو مهم.mp4"


def test_human_size():
    assert human_size(None) == "?"
    assert human_size(0) == "?"
    assert human_size(500) == "500B"
    assert human_size(2048) == "2.0KB"
    assert human_size(3 * 1024 ** 3) == "3.0GB"


def test_hamming():
    assert hamming(0, 0) == 0
    assert hamming(0b1010, 0b0101) == 4


def test_remux_compatible():
    assert remux_compatible({"vcodec": "h264", "acodec": "aac", "container": "matroska"})
    assert not remux_compatible({"vcodec": "mpeg4", "acodec": "aac", "container": "avi"})
    assert not remux_compatible({"vcodec": "h264", "acodec": "flac", "container": "mkv"})
    # already-MP4 containers excluded
    assert not remux_compatible({"vcodec": "h264", "acodec": "aac", "container": "mp4"})
    # no audio at all is fine
    assert remux_compatible({"vcodec": "hevc", "acodec": None, "container": "matroska,webm"})
