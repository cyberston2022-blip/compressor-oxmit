"""Regression for SEC-1: token-bearing Local Bot API paths never survive into
persisted or displayed error strings."""
from oxmit.media import redact


def test_redact_strips_token_directory():
    raw = ("ffprobe failed for /var/lib/telegram-bot-api/12345:SECRETKEY/file_2.mp4: "
           "Permission denied")
    out = redact(raw)
    assert "12345:SECRETKEY" not in out
    assert "/var/lib/telegram-bot-api/<REDACTED>/file_2.mp4" in out
    assert "Permission denied" in out  # useful detail kept


def test_redact_multiple_occurrences_and_non_paths():
    raw = ("a /var/lib/telegram-bot-api/TOK1/a.mp4 then /var/lib/telegram-bot-api/TOK2/b.mk4 "
           "and no path here")
    out = redact(raw)
    assert "TOK1" not in out and "TOK2" not in out
    assert out.count("<REDACTED>") == 2


def test_redact_handles_none_and_empty():
    assert redact(None) == ""
    assert redact("") == ""


def test_media_error_interpolation_redacts(tmp_path, monkeypatch):
    """_probe_sync redacts ffprobe stderr before wrapping in MediaError."""
    import subprocess

    from oxmit import media as m

    class FakeProc:
        returncode = 1
        stderr = b"ffprobe failed for /var/lib/telegram-bot-api/TOKEN/x.mp4: boom"
        stdout = b""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeProc())
    try:
        m._probe_sync(tmp_path / "whatever.mp4")
    except m.MediaError as exc:
        assert "TOKEN" not in str(exc)
        assert "<REDACTED>" in str(exc)
    else:
        raise AssertionError("expected MediaError")


async def test_fail_job_persists_redacted_message(engine, fake_db):
    fake_db.on_fetchval(
        lambda sql: "SET status = 'failed'" in sql, "job-1"
    )
    token_path = "/var/lib/telegram-bot-api/SECRET_TOKEN/file.mp4"
    row = {"id": "job-1", "status": "queued", "requester_tg_id": None,
           "status_message_id": None}
    await engine.fail_job(row, "ffmpeg", f"ffprobe failed for {token_path}: boom")
    stored = [e for e in fake_db.executed if e[0] == "fetchval" and "error_message" in e[1]]
    assert stored, "error_message UPDATE missing"
    args = stored[0][2]
    assert all("SECRET_TOKEN" not in str(a) for a in args)
    assert any("<REDACTED>" in str(a) for a in args)
