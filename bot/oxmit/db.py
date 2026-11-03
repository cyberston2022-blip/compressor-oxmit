"""asyncpg pool + simple file-based migrations."""

from __future__ import annotations

import pathlib

import asyncpg

from .log import get_logger

log = get_logger("oxmit.db")

MIGRATIONS_DIR = pathlib.Path(__file__).parent / "migrations"


class Database:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(self.dsn, min_size=2, max_size=10)
        await self.migrate()

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    async def migrate(self) -> None:
        assert self.pool
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "CREATE TABLE IF NOT EXISTS schema_migrations("
                    "name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
                )
            applied = {
                r["name"] for r in await conn.fetch("SELECT name FROM schema_migrations")
            }
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if path.name in applied:
                    continue
                sql = path.read_text(encoding="utf-8")
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations(name) VALUES($1)", path.name
                    )
                log.info("migration applied", extra={"event": path.name})

    # ---- thin helpers ----
    async def execute(self, sql: str, *args):
        assert self.pool
        return await self.pool.execute(sql, *args)

    async def fetch(self, sql: str, *args) -> list[asyncpg.Record]:
        assert self.pool
        return await self.pool.fetch(sql, *args)

    async def fetchrow(self, sql: str, *args) -> asyncpg.Record | None:
        assert self.pool
        return await self.pool.fetchrow(sql, *args)

    async def fetchval(self, sql: str, *args):
        assert self.pool
        return await self.pool.fetchval(sql, *args)

    async def bump(self, counter: str, by: int = 1) -> None:
        await self.execute(
            "INSERT INTO counters(name, value) VALUES($1, $2) "
            "ON CONFLICT(name) DO UPDATE SET value = counters.value + $2",
            counter,
            by,
        )

    async def get_counters(self) -> dict[str, int]:
        rows = await self.fetch("SELECT name, value FROM counters")
        return {r["name"]: r["value"] for r in rows}

    async def get_config(self, key: str):
        import json

        raw = await self.fetchval("SELECT value FROM app_config WHERE key = $1", key)
        return json.loads(raw) if raw else None

    async def set_config(self, key: str, value) -> None:
        import json

        await self.execute(
            "INSERT INTO app_config(key, value) VALUES($1, $2::jsonb) "
            "ON CONFLICT(key) DO UPDATE SET value = $2::jsonb, updated_at = now()",
            key,
            json.dumps(value),
        )

    # Counters reconstructible from row state. Event counters (requests_total,
    # bytes_*, dedup_*, level_escalations, archive_missing_detected) are
    # intentionally NOT touched - they count events, not rows.
    _RECONCILABLE = {
        "jobs_encoded": "SELECT count(*) FROM jobs WHERE status='completed' AND reuse_of IS NULL",
        "jobs_failed": "SELECT count(*) FROM jobs WHERE status='failed'",
        "jobs_cancelled": "SELECT count(*) FROM jobs WHERE status='cancelled'",
        "no_gain_events":
            "SELECT count(*) FROM jobs WHERE is_no_gain AND status='completed' AND reuse_of IS NULL",
        "archive_blocked":
            "SELECT count(*) FROM jobs WHERE status='completed' AND archived IS FALSE "
            "AND NOT is_no_gain AND reuse_of IS NULL",
        "deliveries_ok": "SELECT count(*) FROM deliveries WHERE status='ok'",
        "deliveries_failed": "SELECT count(*) FROM deliveries WHERE status='failed'",
    }

    async def reconcile_counters(self) -> dict[str, tuple[int, int]]:
        """Sync lifecycle counters with actual row state; returns corrected drift."""
        drift: dict[str, tuple[int, int]] = {}
        for name, sql in self._RECONCILABLE.items():
            actual = int(await self.fetchval(sql) or 0)
            current = await self.fetchval("SELECT value FROM counters WHERE name = $1", name)
            if current is None:
                await self.execute("INSERT INTO counters(name, value) VALUES($1, $2)", name, actual)
            elif int(current) != actual:
                drift[name] = (int(current), actual)
                await self.execute("UPDATE counters SET value = $2 WHERE name = $1", name, actual)
        return drift
