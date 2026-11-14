"""Regression for BUG-001: redeliver() must not reference the undefined `row`
and must query media_assets with job["media_id"]."""


JOB_1 = "11111111-1111-4111-8111-111111111111"
JOB_2 = "22222222-2222-4222-8222-222222222222"


def _allow_requester(fake_db):
    fake_db.on_fetchval(lambda sql: "job_requesters" in sql, 1)


async def test_redeliver_does_not_raise_and_uses_job_media_id(engine, fake_db):
    _allow_requester(fake_db)

    async def fetchrow(sql, *args):
        fake_db.executed.append(("fetchrow", sql, args))
        if "FROM jobs WHERE id" in sql:
            return {
                "id": JOB_1, "status": "completed", "reuse_of": None,
                "output_media_id": None, "is_no_gain": False,
                "media_id": "m-1", "source_path": None,
            }
        return None

    fake_db.fetchrow = fetchrow
    ok, method = await engine.redeliver(JOB_1, 111, 222)
    # Nothing deliverable (no archive row / file_id / path) — but crucially
    # no NameError, and the src_asset query used job["media_id"].
    assert ok is False
    src_queries = [e for e in fake_db.executed
                   if e[0] == "fetchrow" and "media_assets WHERE id = $1" in e[1]]
    assert src_queries, "src_asset lookup missing"
    assert any(e[2] and str(e[2][0]) == "m-1" for e in src_queries)
    assert any("deliveries" in e[1] for e in fake_db.executed if e[0] == "execute")


async def test_redeliver_no_gain_path_uses_job_fields(engine, fake_db):
    _allow_requester(fake_db)

    async def fetchrow(sql, *args):
        fake_db.executed.append(("fetchrow", sql, args))
        if "FROM jobs WHERE id" in sql:
            return {
                "id": JOB_2, "status": "completed", "reuse_of": None,
                "output_media_id": "om-1", "is_no_gain": True,
                "media_id": "m-2", "source_path": None,
            }
        return None

    fake_db.fetchrow = fetchrow
    ok, method = await engine.redeliver(JOB_2, 111, 222)
    assert ok is False
    src_queries = [e for e in fake_db.executed
                   if e[0] == "fetchrow" and "media_assets WHERE id = $1" in e[1]]
    assert any(e[2] and str(e[2][0]) == "m-2" for e in src_queries)


async def test_redeliver_passes_duration_and_dimensions_to_delivery(engine, fake_db, monkeypatch):
    _allow_requester(fake_db)
    from oxmit import archive as archive_mod
    from unittest.mock import AsyncMock

    mock_deliver = AsyncMock(return_value=(True, "file_id", 12345))
    monkeypatch.setattr(archive_mod, "deliver_result", mock_deliver)

    async def fetchrow(sql, *args):
        fake_db.executed.append(("fetchrow", sql, args))
        if "FROM jobs WHERE id" in sql:
            return {
                "id": JOB_2, "status": "completed", "reuse_of": None,
                "output_media_id": None, "is_no_gain": True,
                "media_id": "m-2", "source_path": None,
            }
        if "FROM media_assets WHERE id" in sql:
            return {
                "tg_file_id": "file-xyz",
                "duration_s": 59.8,
                "width": 1280,
                "height": 720,
            }
        return None

    fake_db.fetchrow = fetchrow
    ok, method = await engine.redeliver(JOB_2, 111, 222)
    assert ok is True
    assert method == "file_id"
    mock_deliver.assert_awaited_once()
    kwargs = mock_deliver.await_args.kwargs
    assert kwargs.get("duration") == 60
    assert kwargs.get("width") == 1280
    assert kwargs.get("height") == 720

