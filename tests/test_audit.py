"""NEW-005: audit trail — every action inserts exactly one row; failures are
swallowed so auditing never breaks the caller's flow."""
from oxmit.audit import log_action, recent


async def test_log_action_inserts(fake_db):
    await log_action(fake_db, "admin:1", "admin", "user.ban", 42,
                     "new=True", source="telegram", ip="1.2.3.4")
    inserts = [e for e in fake_db.executed if e[0] == "execute" and "audit_log" in e[1]]
    assert len(inserts) == 1
    args = inserts[0][2]
    assert args[0] == "admin:1" and args[2] == "user.ban" and args[5] == "telegram"


async def test_log_action_none_targets_become_null(fake_db):
    await log_action(fake_db, "admin:1", "admin", "system.cleanup", None, None)
    args = [e for e in fake_db.executed if "audit_log" in e[1]][0][2]
    assert args[3] is None and args[4] is None


async def test_log_action_swallows_db_failure():
    class ExplodingDB:
        async def execute(self, *a, **k):
            raise RuntimeError("db gone")

    await log_action(ExplodingDB(), "admin:1", "admin", "user.ban")  # must not raise


async def test_recent_passes_filters(fake_db):
    fake_db.on_fetch(lambda sql: "FROM audit_log" in sql,
                     [{"ts": "t", "actor": "a", "role": "admin", "action": "user.ban",
                       "target": "1", "details": None, "source": "web", "ip": None}])
    rows = await recent(fake_db, limit=10, action="user.ban")
    assert rows and rows[0]["action"] == "user.ban"
