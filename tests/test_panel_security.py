"""Panel v2 security primitives: login throttle, session cookie signing,
and error redaction in job listings (SEC-1 enforcement at the panel)."""
import time
from collections import deque
from datetime import datetime

from oxmit import webpanel as wp


def test_login_allowed_then_locked():
    attempts = deque()
    allowed, _ = wp.login_allowed(attempts, 0.0)
    assert allowed
    for _ in range(wp.LOGIN_MAX_ATTEMPTS):
        attempts.append(time.time())
    allowed, _ = wp.login_allowed(attempts, 0.0)
    assert not allowed


def test_login_lockout_wins_over_window():
    attempts = deque()
    allowed, retry = wp.login_allowed(attempts, time.time() + 120)
    assert not allowed and retry > 100


def test_login_attempts_expire():
    attempts = deque([time.time() - wp.LOGIN_WINDOW_S - 5] * wp.LOGIN_MAX_ATTEMPTS)
    allowed, _ = wp.login_allowed(attempts, 0.0)
    assert allowed


def _mk_session(token, sessions):
    sid = "sid123"
    exp = int(time.time()) + 3600
    sessions[sid] = {"exp": exp, "csrf": "csrfval", "actor": "panel-admin"}
    return sid, exp, f"{sid}:{exp}:{wp._sign(token, f'{sid}:{exp}')}"


def test_cookie_roundtrip_valid():
    token = "T"; sessions = {}
    sid, exp, raw = _mk_session(token, sessions)
    session = wp._check_cookie(token, raw, sessions)
    assert session and session["csrf"] == "csrfval"


def test_cookie_rejects_tampered_signature():
    token = "T"; sessions = {}
    sid, exp, raw = _mk_session(token, sessions)
    bad = raw[:-4] + "0000"
    assert wp._check_cookie(token, bad, sessions) is None


def test_cookie_rejects_expired():
    token = "T"; sessions = {}
    sid = "sid1"; exp = int(time.time()) - 10
    sessions[sid] = {"exp": exp, "csrf": "c"}
    raw = f"{sid}:{exp}:{wp._sign(token, f'{sid}:{exp}')}"
    assert wp._check_cookie(token, raw, sessions) is None


def test_cookie_rejects_revoked_session():
    token = "T"; sessions = {}
    sid, exp, raw = _mk_session(token, sessions)
    sessions.pop(sid)  # revoked
    assert wp._check_cookie(token, raw, sessions) is None


def test_cookie_requires_matching_session_exp():
    token = "T"; sessions = {}
    sid, exp, raw = _mk_session(token, sessions)
    sessions[sid]["exp"] = exp + 1  # store tampered
    assert wp._check_cookie(token, raw, sessions) is None


async def test_jobs_data_redacts_token_paths(fake_db):
    token_path = "/var/lib/telegram-bot-api/SECRET_TOKEN/file.mp4"
    fake_db.on_fetch(lambda sql: "FROM jobs j" in sql, [{
        "id": "11111111-1111-4111-8111-111111111111", "jid": "11111111",
        "status": "failed", "stage": "failed", "profile": "level",
        "effective_profile": "level", "progress": 0, "is_no_gain": False,
        "source_size": 1, "output_size": None,
        "enqueued_at": datetime(2026, 11, 1, 12, 0),
        "completed_at": datetime(2026, 11, 1, 12, 1),
        "err": f"ffprobe failed for {token_path}: boom",
        "fname": "x.mp4", "first_name": "u", "username": None, "tg": 7,
    }])
    jobs = await wp.jobs_data(fake_db, None, None, None, 168)
    assert jobs and "SECRET_TOKEN" not in jobs[0]["err"]
    assert "<REDACTED>" in jobs[0]["err"]
