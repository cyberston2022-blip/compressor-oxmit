"""Tests for media operations unlinking broken/partial outputs on failure."""
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from oxmit import media


def test_remux_unlinks_on_timeout(tmp_path):
    src = tmp_path / "in.mkv"
    dst = tmp_path / "out.mp4"
    src.write_bytes(b"dummy")
    dst.write_bytes(b"partial-data")

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=1)

    with patch("subprocess.run", side_effect=_timeout):
        with pytest.raises(media.MediaError, match="timeout"):
            media.remux_to_mp4(src, dst)

    assert not dst.exists(), "dst must be unlinked on timeout"


def test_remux_unlinks_on_error(tmp_path):
    src = tmp_path / "in.mkv"
    dst = tmp_path / "out.mp4"
    src.write_bytes(b"dummy")
    dst.write_bytes(b"corrupt-data")

    ret = subprocess.CompletedProcess(args=["ffmpeg"], returncode=1, stderr=b"error")

    with patch("subprocess.run", return_value=ret):
        with pytest.raises(media.MediaError, match="failed"):
            media.remux_to_mp4(src, dst)

    assert not dst.exists(), "dst must be unlinked on nonzero exit"


def test_download_thumbnail_cleanup_on_error(tmp_path):
    src = tmp_path / "photo.jpg"
    dst = tmp_path / "thumb.jpg"
    src.write_bytes(b"photo")
    dst.write_bytes(b"bad-thumb")

    ret = subprocess.CompletedProcess(args=["ffmpeg"], returncode=1, stderr=b"fail")
    with patch("subprocess.run", return_value=ret):
        ok = media.download_thumbnail(src, dst)

    assert ok is False
    assert not dst.exists(), "thumbnail dst must be unlinked on failure"


def test_extract_thumbnail_cleanup_on_error(tmp_path):
    video = tmp_path / "vid.mp4"
    dst = tmp_path / "thumb.jpg"
    video.write_bytes(b"video")
    dst.write_bytes(b"bad-thumb")

    ret = subprocess.CompletedProcess(args=["ffmpeg"], returncode=1, stderr=b"fail")
    with patch("subprocess.run", return_value=ret):
        ok = media.extract_thumbnail(video, dst, at_seconds=10.0)

    assert ok is False
    assert not dst.exists(), "extracted thumbnail dst must be unlinked on failure"
