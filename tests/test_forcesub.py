"""Regression for BUG-007: only POSITIVE force-sub membership is cached."""
from types import SimpleNamespace

from oxmit import forcesub


class FakeBot:
    def __init__(self, status_by_user):
        self.status_by_user = status_by_user
        self.calls = []

    async def get_chat_member(self, channel_id, tg_id):
        self.calls.append(tg_id)
        return SimpleNamespace(status=self.status_by_user[tg_id], is_member=False)


class FakeEngine:
    def __init__(self, bot):
        self.bot = bot


def _db_with_forcesub(fake_db):
    fake_db.config_overrides = {
        "force_sub": {"enabled": True, "channel_id": -100123, "link": "https://t.me/x"}
    }
    return fake_db


async def test_member_is_cached(fake_db):
    bot = FakeBot({7: "member"})
    fake_db = _db_with_forcesub(fake_db)
    conf = await forcesub.gate(FakeEngine(bot), fake_db, 7)
    assert conf is None
    await forcesub.gate(FakeEngine(bot), fake_db, 7)
    assert bot.calls == [7]  # second call served from cache


async def test_non_member_is_not_cached(fake_db):
    bot = FakeBot({8: "left"})
    fake_db = _db_with_forcesub(fake_db)
    conf = await forcesub.gate(FakeEngine(bot), fake_db, 8)
    assert conf is not None  # blocked
    await forcesub.gate(FakeEngine(bot), fake_db, 8)
    assert bot.calls == [8, 8]  # re-checked every time (BUG-007)


async def test_api_error_fails_open(fake_db):
    class ExplodingBot:
        async def get_chat_member(self, channel_id, tg_id):
            raise forcesub.TelegramAPIError(None, "tg down")

    fake_db = _db_with_forcesub(fake_db)
    conf = await forcesub.gate(FakeEngine(ExplodingBot()), fake_db, 9)
    assert conf is None  # fail-open, never bricks the bot
