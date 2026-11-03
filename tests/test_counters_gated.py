"""Regression for NEW-001: lifecycle counters bump only when the guarded
state-transition UPDATE actually matched a row."""
ROW = {"id": "job-1", "status": "queued", "requester_tg_id": None,
       "status_message_id": None}


async def test_fail_job_bumps_once_on_successful_transition(engine, fake_db):
    fake_db.on_fetchval(lambda sql: "SET status = 'failed'" in sql, "job-1")
    await engine.fail_job(dict(ROW), "ffmpeg", "boom")
    assert len(fake_db.bumps("jobs_failed")) == 1


async def test_fail_job_no_bump_when_update_misses(engine, fake_db):
    # UPDATE matched nothing (job already terminal in the DB)
    fake_db.on_fetchval(lambda sql: "SET status = 'failed'" in sql, None)
    await engine.fail_job(dict(ROW), "ffmpeg", "boom")
    assert fake_db.bumps("jobs_failed") == []


async def test_mark_cancelled_no_bump_when_update_misses(engine, fake_db):
    fake_db.on_fetchval(lambda sql: "SET status = 'cancelled'" in sql, None)
    await engine._mark_cancelled(dict(ROW))
    assert fake_db.bumps("jobs_cancelled") == []


async def test_mark_cancelled_bumps_once_on_success(engine, fake_db):
    fake_db.on_fetchval(lambda sql: "SET status = 'cancelled'" in sql, "job-1")
    await engine._mark_cancelled(dict(ROW))
    assert len(fake_db.bumps("jobs_cancelled")) == 1


async def test_reconcile_counters_syncs_drift(fake_db):
    from oxmit.db import Database

    counter_values = {"jobs_encoded": 83, "jobs_failed": 6, "jobs_cancelled": 0,
                      "no_gain_events": 28, "archive_blocked": 10,
                      "deliveries_ok": 30, "deliveries_failed": 20}

    async def fetchval(sql, *args):
        if "FROM counters WHERE name" in sql:
            return counter_values.get(args[0])
        if "reuse_of IS NULL" in sql and "is_no_gain" not in sql:
            return 61                      # jobs_encoded actual
        if "is_no_gain AND status" in sql:
            return 24                      # no_gain_events actual
        if "archived IS FALSE" in sql:
            return 10                      # archive_blocked actual
        if "FROM deliveries WHERE status='ok'" in sql:
            return 30
        if "FROM deliveries WHERE status='failed'" in sql:
            return 18
        if "status='failed'" in sql:
            return 6
        if "status='cancelled'" in sql:
            return 0
        return 0

    db = Database("postgresql://stub")
    db.fetchval = fetchval
    updates = []
    db.execute = lambda sql, *a: updates.append(sql) or _done()

    async def _done():
        return "UPDATE 1"

    drift = await Database.reconcile_counters(db)
    assert drift["jobs_encoded"] == (83, 61)
    assert drift["no_gain_events"] == (28, 24)
    assert drift["deliveries_failed"] == (20, 18)
    assert "jobs_failed" not in drift      # already in sync
    assert "jobs_cancelled" not in drift
    assert updates, "drifted counters must be corrected"
