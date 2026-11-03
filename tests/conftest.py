"""Shared fixtures: FakeDB (records every call, returns scripted rows),
a JobEngine factory on tmp-path media roots, and sys.path wiring so the
`oxmit` package resolves from bot/ without installation."""
import sys
from pathlib import Path

import pytest

BOT_DIR = Path(__file__).resolve().parent.parent / "bot"
sys.path.insert(0, str(BOT_DIR))


class FakeDB:
    """Predicate-based stub for the asyncpg pool wrapper.

    Matchers are (predicate(sql), value) pairs, first match wins. Instance
    attribute overrides (db.fetchrow = fn) also work for dynamic tests.
    Every call is recorded in `executed` as (kind, sql, args).
    """

    def __init__(self):
        self.executed = []
        self._fetchval = []
        self._fetchrow = []
        self._fetch = []

    def on_fetchval(self, match, value):
        self._fetchval.append((match, value))

    def on_fetchrow(self, match, value):
        self._fetchrow.append((match, value))

    def on_fetch(self, match, value):
        self._fetch.append((match, value))

    async def execute(self, sql, *args):
        self.executed.append(("execute", sql, args))
        return "UPDATE 1"

    async def fetchval(self, sql, *args):
        self.executed.append(("fetchval", sql, args))
        for match, value in self._fetchval:
            if match(sql):
                return value
        return None

    async def fetchrow(self, sql, *args):
        self.executed.append(("fetchrow", sql, args))
        for match, value in self._fetchrow:
            if match(sql):
                return value
        return None

    async def fetch(self, sql, *args):
        self.executed.append(("fetch", sql, args))
        for match, value in self._fetch:
            if match(sql):
                return value
        return []

    async def get_config(self, key):
        return getattr(self, "config_overrides", {}).get(key)

    async def set_config(self, key, value):
        self.executed.append(("set_config", key, value))

    async def bump(self, counter, by=1):
        self.executed.append(("bump", counter, by))

    def bumps(self, name=None):
        return [e for e in self.executed if e[0] == "bump" and (name is None or e[1] == name)]


class StubEncre:
    pass


@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def engine(fake_db, tmp_path):
    from oxmit.config import Settings
    from oxmit.engine import JobEngine

    cfg = Settings(media_root=str(tmp_path))
    return JobEngine(fake_db, cfg, object(), StubEncre())
