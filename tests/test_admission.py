"""Unit tests: admission control reject codes and admin bypass."""
import pytest

from oxmit.engine import AdmissionError

GB = 1024 ** 3


def _users_row(**over):
    row = {"is_blocked": False, "is_vip": False, "max_source_gb": None,
           "max_duration_min": None, "daily_quota_gb": None}
    row.update(over)
    return row


async def _admit(engine, fake_db, *, size=100 << 20, tg=1, admin=False):
    engine.state.archive_channel_id = -100123  # skip archive-not-configured gate
    fake_db.on_fetchrow(lambda sql: "FROM users" in sql, _users_row())
    fake_db.on_fetchval(lambda sql: "status IN ('queued','processing','deferred')" in sql, 0)
    fake_db.on_fetchval(lambda sql: "interval '1 hour'" in sql, 0)
    fake_db.on_fetchval(lambda sql: "interval '24 hours'" in sql and "sum" not in sql, 0)
    fake_db.on_fetchval(lambda sql: "sum(source_size)" in sql, 0)
    fake_db.on_fetchval(lambda sql: "status = 'queued'" in sql, 0)
    fake_db.on_fetchval(lambda sql: "sum(reserved_bytes)" in sql, 0)
    if not getattr(engine, "_disk_free_patched", False):
        # tmp_path sits on the system drive; give admission a roomy disk
        engine._disk_free = lambda: 200 * GB  # noqa: SLF001
        engine._disk_free_patched = True
    await engine.check_admission(tg, size, is_admin=admin)


async def test_happy_path_admits(engine, fake_db):
    await _admit(engine, fake_db)


async def test_blocked_user_rejected(engine, fake_db):
    engine.state.archive_channel_id = -100123
    fake_db.on_fetchrow(lambda sql: "FROM users" in sql, _users_row(is_blocked=True))
    with pytest.raises(AdmissionError) as exc:
        await engine.check_admission(1, 100 << 20)
    assert exc.value.code == "blocked_user"


async def test_oversize_rejected_for_normal_user(engine, fake_db):
    with pytest.raises(AdmissionError) as exc:
        await _admit(engine, fake_db, size=5 * GB)
    assert exc.value.code == "too_large_tier"


async def test_admin_bypasses_size_limit(engine, fake_db):
    engine.state.archive_channel_id = -100123
    engine._disk_free = lambda: 200 * GB
    fake_db.on_fetchrow(
        lambda sql: "SELECT tg_id FROM users WHERE is_admin" in sql,
        [{"tg_id": 1}],
    )
    await engine.check_admission(1, 6 * GB, is_admin=True)  # must not raise


async def test_queue_full_rejected(engine, fake_db):
    engine.state.archive_channel_id = -100123
    engine.cfg.max_queued = 2
    fake_db.on_fetchrow(lambda sql: "FROM users" in sql, _users_row())
    fake_db.on_fetchval(lambda sql: "status IN ('queued','processing','deferred')" in sql, 0)
    fake_db.on_fetchval(lambda sql: "interval '1 hour'" in sql, 0)
    fake_db.on_fetchval(lambda sql: "interval '24 hours'" in sql and "sum" not in sql, 0)
    fake_db.on_fetchval(lambda sql: "sum(source_size)" in sql, 0)
    fake_db.on_fetchval(lambda sql: "status = 'queued'" in sql, 2)
    with pytest.raises(AdmissionError) as exc:
        await engine.check_admission(1, 100 << 20)
    assert exc.value.code == "queue_full"


async def test_low_disk_does_not_reject_intake(engine, fake_db):
    """A queued job is a DB row, not a file: low disk must not reject or
    defer intake (the dispatcher holds downloads until space frees)."""
    engine.state.archive_channel_id = -100123
    engine._disk_free = lambda: 1 << 30  # 1 GB "free"
    fake_db.on_fetchrow(lambda sql: "FROM users" in sql, _users_row())
    fake_db.on_fetchval(lambda sql: "status IN ('queued','processing','deferred')" in sql, 0)
    fake_db.on_fetchval(lambda sql: "interval '1 hour'" in sql, 0)
    fake_db.on_fetchval(lambda sql: "interval '24 hours'" in sql and "sum" not in sql, 0)
    fake_db.on_fetchval(lambda sql: "sum(source_size)" in sql, 0)
    fake_db.on_fetchval(lambda sql: "status = 'queued'" in sql, 0)
    await engine.check_admission(1, 3 << 30)  # must not raise


async def test_pending_cap_rejects_with_clear_code(engine, fake_db):
    engine.state.archive_channel_id = -100123
    fake_db.on_fetchrow(lambda sql: "FROM users" in sql, _users_row())
    fake_db.on_fetchval(lambda sql: "status IN ('queued','processing','deferred')" in sql, 10)
    fake_db.on_fetchval(lambda sql: "status = 'queued'" in sql, 0)
    with pytest.raises(AdmissionError) as exc:
        await engine.check_admission(1, 100 << 20)
    assert exc.value.code == "user_pending" and exc.value.fmt["max_pending"] == 10


def test_queue_capacity_default_is_5000():
    from oxmit.config import Settings
    assert Settings().max_queued == 5000


async def test_duration_limit(engine, fake_db):
    fake_db.on_fetchrow(lambda sql: "FROM users" in sql, _users_row())
    with pytest.raises(AdmissionError) as exc:
        await engine.check_duration_limit(1, 7 * 3600)  # normal tier: 6h max
    assert exc.value.code == "too_long"
    await engine.check_duration_limit(1, 5 * 3600)  # 5h is within 6h limit
    await engine.check_duration_limit(1, 60)  # fine


def test_intake_and_queue_clock_rounding():
    from oxmit.handlers.intake import _clock as intake_clock
    from oxmit.jobqueue import _clock as queue_clock

    # Sub-second duration must round to 1s, never 0:00
    assert intake_clock(0.4) == "0:01"
    assert intake_clock(59.8) == "1:00"
    assert intake_clock(0) == "?"
    assert intake_clock(None) == "?"

    assert queue_clock(0.4) == "0:01"
    assert queue_clock(59.8) == "1:00"
    assert queue_clock(0) == "0:00"
