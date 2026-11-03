"""Regression for BUG-002: cleanup_sweep must delete expired plain files and
symlinks (not just directories) and must sweep media/work."""
import os
import time


def _age(path, hours=48):
    old = time.time() - hours * 3600
    os.utime(path, (old, old))


async def test_expired_plain_file_is_unlinked(engine, tmp_path):
    test_dir = tmp_path / "test"
    test_dir.mkdir()
    old_file = test_dir / "fullrepro.mp4"
    old_file.write_bytes(b"x")
    fresh_file = test_dir / "gen_new.mp4"
    fresh_file.write_bytes(b"x")
    _age(old_file)

    await engine.cleanup_sweep()

    assert not old_file.exists()
    assert fresh_file.exists()


async def test_expired_directory_is_removed(engine, tmp_path):
    out_dir = tmp_path / "out"
    job_dir = out_dir / "job-1"
    job_dir.mkdir(parents=True)
    (job_dir / "out.mp4").write_bytes(b"x")
    _age(job_dir)

    await engine.cleanup_sweep()

    assert not job_dir.exists()


async def test_media_work_is_swept(engine, tmp_path):
    work = tmp_path / "work"
    stale = work / "encore-segment-job"
    stale.mkdir(parents=True)
    (stale / "seg.mp4").write_bytes(b"x")
    _age(stale)

    await engine.cleanup_sweep()

    assert not stale.exists()


async def test_symlink_is_unlinked(engine, tmp_path):
    test_dir = tmp_path / "test"
    test_dir.mkdir()
    target = tmp_path / "real.bin"
    target.write_bytes(b"x")
    link = test_dir / "link.bin"
    try:
        link.symlink_to(target)
    except OSError:
        return  # platform without symlink support
    _age(link)

    await engine.cleanup_sweep()

    assert not link.exists()
    assert target.exists()  # target untouched
