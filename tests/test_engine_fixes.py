"""Spec tests for the improvement batch (F2 / F4 + admission quota).

These are pure-unit tests on JobEngine with FakeDB.  Two of them encode the
DESIRED post-fix behaviour and are expected to fail until the corresponding
bot/oxmit fixes land:

* F2 - ``retry_user_job`` must increment ``retries`` (``retries + 1``) and
  guard the reset with ``retries < $n`` so a concurrent failure cannot race
  the user retry back to unlimited attempts.  Marked xfail(strict=False)
  with reason "pending F2 fix" until then.
* F4 - ``_stage_source`` must not blindly reuse an existing staged file: a
  stale/partial copy (size mismatch vs the source) must be re-copied.
  Marked xfail(strict=False) with reason "pending F4 fix".
"""
import asyncio
import os
import uuid

import pytest

from oxmit.engine import AdmissionError

GB = 1024 ** 3
MB = 1024 ** 2


def _failed_job_row(retries: int, tg_id: int = 7) -> dict:
    return {
        "id": uuid.uuid4(),
        "status": "failed",
        "requester_tg_id": tg_id,
        "retries": retries,
        "error_category": "encore_api",
    }


def _users_row(**over):
    row = {"is_blocked": False, "is_vip": False, "max_source_gb": None,
           "max_duration_min": None, "daily_quota_gb": None}
    row.update(over)
    return row


def _script_disk(fake_db):
    fake_db.on_fetchval(lambda sql: "status IN ('queued','processing','deferred')" in sql, 0)
    fake_db.on_fetchval(lambda sql: "interval '1 hour'" in sql, 0)
    fake_db.on_fetchval(lambda sql: "interval '24 hours'" in sql and "sum" not in sql, 0)
    fake_db.on_fetchval(lambda sql: "sum(source_size)" in sql, 0)
    fake_db.on_fetchval(lambda sql: "status = 'queued'" in sql, 0)
    fake_db.on_fetchval(lambda sql: "sum(reserved_bytes)" in sql, 0)


async def _drain_bg(engine):
    """Let spawned background tasks (run_job on a missing row) finish."""
    for _ in range(3):
        await asyncio.sleep(0)
    for t in list(engine._bg_tasks):
        try:
            await asyncio.wait_for(t, timeout=1)
        except Exception:  # noqa: BLE001 - background best-effort
            pass


# ---------------------------------------------------------------------------
# (a) retry_user_job limit
# ---------------------------------------------------------------------------

async def test_retry_user_job_rejects_at_limit(engine, fake_db):
    """A failed job whose retries reached the cap (job_retries + 2) must be
    rejected with the reason "limit", not requeued forever."""
    row = _failed_job_row(retries=engine.cfg.job_retries + 2)
    fake_db.on_fetchrow(
        lambda sql: "FROM jobs WHERE id" in sql and "media_assets" not in sql, row)

    ok, reason = await engine.retry_user_job(str(row["id"]), tg_id=7)

    assert ok is False
    assert reason == "limit"
    assert not any(e[0] == "execute" for e in fake_db.executed), \
        "no UPDATE may run once the retry cap is reached"


async def test_retry_user_job_below_limit_increments_and_guards(
        engine, fake_db):
    """F2 SPEC: below the cap, the user retry must issue an UPDATE that
    (1) increments retries via ``retries + 1`` in the SQL, and
    (2) guards the reset with ``retries < $n`` so a concurrent failure path
    cannot lose increments (the historic bug: retries was never incremented,
    making user retries unbounded)."""
    row = _failed_job_row(retries=1)
    fake_db.on_fetchrow(
        lambda sql: "FROM jobs WHERE id" in sql and "media_assets" not in sql, row)

    ok, _reason = await engine.retry_user_job(str(row["id"]), tg_id=7)
    assert ok is True

    await _drain_bg(engine)
    updates = [e for e in fake_db.executed
               if e[0] == "execute" and "UPDATE jobs" in e[1]]
    assert updates, "retry must issue the requeue UPDATE"
    sql = updates[-1][1]
    assert "retries + 1" in sql, (
        "F2: retry_user_job must increment retries (retries + 1) in the UPDATE")
    assert "retries < $" in sql, (
        "F2: retry_user_job must guard the requeue with retries < $n")
    assert "status='failed'" in sql.replace(" ", "").replace("status = 'failed'", "status='failed'"), \
        "the UPDATE must stay conditional on status='failed'"


test_retry_user_job_below_limit_increments_and_guards = pytest.mark.xfail(
    reason="pending F2 fix: retry_user_job does not increment retries yet",
    strict=False,
)(test_retry_user_job_below_limit_increments_and_guards)


# ---------------------------------------------------------------------------
# (b) admission quota
# ---------------------------------------------------------------------------

async def test_daily_job_count_quota_rejects(engine, fake_db, monkeypatch):
    """A user at the per-day job cap is rejected with daily_quota."""
    engine.cfg.max_jobs_per_day = 2
    engine.state.archive_channel_id = -100123
    fake_db.on_fetchrow(lambda sql: "FROM users" in sql, _users_row())
    # register BEFORE _script_disk: FakeDB matchers are first-match-wins
    fake_db.on_fetchval(
        lambda sql: "interval '24 hours'" in sql and "sum" not in sql, 2)
    _script_disk(fake_db)
    with pytest.raises(AdmissionError) as exc:
        await engine.check_admission(7, 100 * MB)
    assert exc.value.code == "daily_quota"


async def test_daily_byte_quota_rejects(engine, fake_db, monkeypatch):
    """A user whose last-24h source volume plus this request exceeds the
    tier/user byte quota is rejected with daily_quota_bytes."""
    engine.state.archive_channel_id = -100123
    fake_db.on_fetchrow(lambda sql: "FROM users" in sql,
                        _users_row(daily_quota_gb=1))
    # register BEFORE _script_disk: FakeDB matchers are first-match-wins
    fake_db.on_fetchval(lambda sql: "sum(source_size)" in sql, 900 * MB)
    _script_disk(fake_db)
    with pytest.raises(AdmissionError) as exc:
        await engine.check_admission(7, 200 * MB)  # 900MB used + 200MB > 1GB
    assert exc.value.code == "daily_quota_bytes"


async def test_daily_byte_quota_allows_under_quota(engine, fake_db, monkeypatch):
    engine.state.archive_channel_id = -100123
    engine._disk_free = lambda: 200 * GB  # noqa: SLF001
    fake_db.on_fetchrow(lambda sql: "FROM users" in sql,
                        _users_row(daily_quota_gb=1))
    _script_disk(fake_db)
    fake_db.on_fetchval(lambda sql: "sum(source_size)" in sql, 500 * MB)
    await engine.check_admission(7, 200 * MB)  # 500MB + 200MB <= 1GB: must not raise


# ---------------------------------------------------------------------------
# (c) atomic staging (F4)
# ---------------------------------------------------------------------------

@pytest.fixture
def staging_env(engine, tmp_path, monkeypatch):
    botapi = tmp_path / "botapi"
    videos = botapi / "videos"
    videos.mkdir(parents=True)
    monkeypatch.setattr(engine.cfg, "botapi_dir", str(botapi))
    monkeypatch.setattr(engine.cfg, "media_root", str(tmp_path / "media"))
    return engine, videos


async def test_stage_reuses_matching_staged_file(staging_env):
    """Sanity (currently true): an intact staged copy with a matching size
    is reused without re-copying."""
    eng, videos = staging_env
    src = videos / "v.mp4"
    src.write_bytes(b"x" * 1000)
    staged_dir = os.path.join(eng.cfg.media_incoming, "job-ok")
    os.makedirs(staged_dir, exist_ok=True)
    staged = os.path.join(staged_dir, "source.mp4")
    with open(staged, "wb") as f:
        f.write(b"x" * 1000)

    out = await eng._stage_source("job-ok", src, "v.mp4")

    assert os.path.isfile(out)
    assert os.path.getsize(out) == 1000


async def test_stage_recopies_on_size_mismatch(staging_env):
    """F4 SPEC: a stale/partial staged file (size mismatch vs the source)
    must NOT be handed to Encore - staging must re-copy so the staged file
    ends up byte-complete (atomic temp-file + rename is the desired shape)."""
    eng, videos = staging_env
    src = videos / "v.mp4"
    src.write_bytes(b"x" * 1000)
    staged_dir = os.path.join(eng.cfg.media_incoming, "job-stale")
    os.makedirs(staged_dir, exist_ok=True)
    staged = os.path.join(staged_dir, "source.mp4")
    with open(staged, "wb") as f:
        f.write(b"x" * 100)  # truncated leftovers from a crashed copy

    out = await eng._stage_source("job-stale", src, "v.mp4")

    assert os.path.getsize(out) == 1000, (
        "F4: size-mismatched staged file must be re-copied from the source")


test_stage_recopies_on_size_mismatch = pytest.mark.xfail(
    reason="pending F4 fix: _stage_source reuses any existing staged file "
           "without verifying its size",
    strict=False,
)(test_stage_recopies_on_size_mismatch)
