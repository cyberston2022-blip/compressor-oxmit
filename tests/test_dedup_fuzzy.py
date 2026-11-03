"""Regression for NEW-003: fuzzy dedup must use a ±2% size window (exact
byte equality could never match a re-muxed copy)."""
from oxmit.dedup import find_fuzzy_archive, find_fuzzy_inflight_job


def _last_call(fake_db, needle):
    calls = [e for e in fake_db.executed if needle in e[1]]
    assert calls, f"no query containing {needle!r}"
    sql, args = calls[-1][1], calls[-1][2]
    return sql, args


async def test_archive_query_uses_size_window(fake_db):
    await find_fuzzy_archive(fake_db, size_bytes=1_000_000,
                             name_norm="video.mp4", duration_s=60.0,
                             profile="level")
    sql, args = _last_call(fake_db, "archive_records")
    # regression (production incident): the interpolation must not leak a
    # stray "$" before the numeric literal — "$0.98" is a PG syntax error.
    assert "0.98" in sql and "1.02" in sql
    assert "$0.98" not in sql and "$1.02" not in sql
    assert "size_bytes = $2" not in sql          # exact match is gone
    assert args[1] == 1_000_000
    assert args[2] == "video.mp4"                # name gate stays exact
    assert args[3] == 58.0 and args[4] == 62.0   # duration ±2 s


async def test_inflight_query_uses_size_window(fake_db):
    await find_fuzzy_inflight_job(fake_db, size_bytes=2_000_000,
                                  name_norm="clip.mp4", duration_s=30.0,
                                  profile="custom")
    sql, _args = _last_call(fake_db, "FROM jobs j")
    assert "0.98" in sql and "1.02" in sql
    assert "$0.98" not in sql and "$1.02" not in sql


async def test_zero_inputs_short_circuit(fake_db):
    assert await find_fuzzy_archive(fake_db, size_bytes=0,
                                    name_norm="x", duration_s=10, profile="p") is None
    assert await find_fuzzy_archive(fake_db, size_bytes=10,
                                    name_norm="", duration_s=10, profile="p") is None
