"""Permission system: owner bypass, secure defaults, grant/revoke effect.

The security contract: checks are backend-side (has_perm), hidden buttons
are never trusted, and a revoked permission takes effect immediately.
"""
import pytest

from oxmit import permissions as perms
from oxmit.permissions import PERMS, effective_perms, has_perm, invalidate_cache


class StubEngine:
    def __init__(self, owner=None, admins=(), rows=None):
        self.owner = owner
        self.admin_ids_set = set(admins)
        self.rows = rows or []          # admin_permissions rows for tg_id
        self.db = self

        async def is_owner(tg_id):
            return tg_id == self.owner
        self.is_owner = is_owner

        async def admin_ids():
            return list(self.admin_ids_set)
        self.admin_ids = admin_ids

        async def fetch(sql, *args):
            assert "admin_permissions" in sql
            return self.rows
        self.fetch = fetch


OWNER, ADMIN_A, ADMIN_B, VIP, USER = 100, 200, 300, 400, 500


def _row(perm, granted=True):
    return {"perm": perm, "granted": granted}


@pytest.fixture(autouse=True)
def _clean_cache():
    invalidate_cache()
    yield
    invalidate_cache()


async def test_owner_bypasses_every_permission():
    eng = StubEngine(owner=OWNER, admins={OWNER, ADMIN_A})
    for perm in PERMS:
        assert await has_perm(eng, OWNER, perm) is True


async def test_admin_default_only_compression():
    eng = StubEngine(admins={ADMIN_A}, rows=[])
    assert await has_perm(eng, ADMIN_A, "compression.use") is True   # default
    for perm in PERMS:
        if perm != "compression.use":
            assert await has_perm(eng, ADMIN_A, perm) is False


async def test_granted_permission_allows_access():
    eng = StubEngine(admins={ADMIN_A}, rows=[_row("watermark.use")])
    assert await has_perm(eng, ADMIN_A, "watermark.use") is True
    assert await has_perm(eng, ADMIN_A, "merge.use") is False  # others untouched


async def test_revoked_permission_immediately_denied():
    eng = StubEngine(admins={ADMIN_A}, rows=[])
    assert await has_perm(eng, ADMIN_A, "compression.use") is True
    # Owner revokes: explicit granted=FALSE row overrides the default grant.
    eng.rows = [_row("compression.use", granted=False)]
    invalidate_cache(ADMIN_A)
    assert await has_perm(eng, ADMIN_A, "compression.use") is False


async def test_non_admin_always_denied():
    eng = StubEngine(admins={ADMIN_A}, rows=[_row("merge.use")])
    for perm in PERMS:
        assert await has_perm(eng, USER, perm) is False
        assert await has_perm(eng, VIP, perm) is False


async def test_unknown_perm_denied():
    eng = StubEngine(owner=OWNER)
    assert await has_perm(eng, OWNER, "not.a.perm") is False


async def test_effective_perms_shapes():
    owner_map = await effective_perms(
        StubEngine(owner=OWNER, admins={OWNER}), OWNER)
    assert all(owner_map.values()) and len(owner_map) == len(PERMS)

    admin_map = await effective_perms(
        StubEngine(admins={ADMIN_A}, rows=[_row("merge.use")]), ADMIN_A)
    assert admin_map["compression.use"] is True
    assert admin_map["merge.use"] is True
    assert admin_map["watermark.use"] is False

    user_map = await effective_perms(StubEngine(admins={ADMIN_A}), USER)
    assert not any(user_map.values())


async def test_cache_isolation_between_users():
    eng = StubEngine(admins={ADMIN_A, ADMIN_B},
                     rows=[_row("merge.use")])
    # rows are global in the stub, so both read the same table; keys must
    # still be cached per-user (invalidate one does not clear the other).
    await has_perm(eng, ADMIN_A, "merge.use")
    assert "200" in perms._CACHE
    invalidate_cache(ADMIN_A)
    assert "200" not in perms._CACHE
    await has_perm(eng, ADMIN_B, "merge.use")
    assert "300" in perms._CACHE and "200" not in perms._CACHE
