"""Regression for the staging bug: run_job staged the source via
asyncio.to_thread(<async fn>) which silently created an un-awaited coroutine —
the copy never ran and Encore got a non-existent input path (worker ENOENT).
_stage_source must actually produce the staged file in BOTH paths."""
import os

import pytest

from oxmit.media import MediaError


@pytest.fixture
def staging_env(engine, tmp_path, monkeypatch):
    botapi = tmp_path / "botapi"
    videos = botapi / "videos"
    videos.mkdir(parents=True)
    monkeypatch.setattr(engine.cfg, "botapi_dir", str(botapi))
    monkeypatch.setattr(engine.cfg, "media_root", str(tmp_path / "media"))
    return engine, videos


async def test_stage_hardlink_path(staging_env, tmp_path):
    eng, videos = staging_env
    src = videos / "v.mp4"
    src.write_bytes(b"x" * 1000)
    out = await eng._stage_source("job-1", src, "v.mp4")
    assert os.path.isfile(out)
    assert os.path.getsize(out) == 1000
    assert "incoming" in out and "botapi" not in out  # token-free path


async def test_stage_copy_fallback_when_hardlink_fails(staging_env, tmp_path, monkeypatch):
    eng, videos = staging_env
    src = videos / "v.mp4"
    src.write_bytes(b"y" * 2048)

    def _exdev(*a, **k):
        raise OSError(18, "Invalid cross-device link")

    monkeypatch.setattr(os, "link", _exdev)
    out = await eng._stage_source("job-2", src, "v.mp4")
    assert os.path.isfile(out), "copy fallback must actually create the file"
    assert os.path.getsize(out) == 2048


async def test_stage_never_returns_missing_file(staging_env, tmp_path, monkeypatch):
    """The original incident: a no-op staging returned a path that did not
    exist and Encore failed with ENOENT. Staging must raise instead."""
    eng, videos = staging_env
    src = videos / "v.mp4"
    src.write_bytes(b"z" * 512)

    def _exdev(*a, **k):
        raise OSError(18, "Invalid cross-device link")

    monkeypatch.setattr(os, "link", _exdev)

    async def _noop(src, dst, on_progress=None, chunk=None):
        return None  # simulate the historical bug: the copy silently never ran

    monkeypatch.setattr("oxmit.media.copy_with_progress", _noop)
    with pytest.raises(MediaError):
        await eng._stage_source("job-3", src, "v.mp4")
    assert not os.path.isfile(
        str(tmp_path / "media" / "incoming" / "job-3" / "source.mp4"))


async def test_stage_skips_non_botapi_paths(staging_env, tmp_path):
    eng, videos = staging_env
    src = tmp_path / "elsewhere.mp4"
    src.write_bytes(b"a" * 10)
    out = await eng._stage_source("job-4", src, "elsewhere.mp4")
    assert str(out) == str(src)  # untouched
