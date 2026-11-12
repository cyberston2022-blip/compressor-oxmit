"""Router-registration regression tests.

The intake router once lost a handler because a decorator merged onto the
previous line (parses as matrix-multiply, module still imports). These tests
pin the existence of every business-critical handler so a silent registration
death fails the suite instead of shipping.
"""
from types import SimpleNamespace

from oxmit.config import Settings
from oxmit.handlers.intake import build_router


def _router():
    db = SimpleNamespace(fetchrow=None, fetchval=None, fetch=None, execute=None)
    state = SimpleNamespace(archive_channel_id=None)
    return build_router(object(), db, Settings(media_root="."), state)


def _handler_names(router, observer: str) -> set[str]:
    return {h.callback.__name__ for h in getattr(router, observer).handlers}


def test_percent_text_handler_is_registered():
    # Regression: the @router.message decorator for on_percent_text once
    # merged onto the previous line -> level 1-20 flow went silently dead.
    assert "on_percent_text" in _handler_names(_router(), "message")


def test_media_intake_handler_is_registered():
    assert "on_media" in _handler_names(_router(), "message")


def test_cache_offer_handlers_are_registered():
    names = _handler_names(_router(), "callback_query")
    assert {"on_use_cached", "on_choose_other_profile",
            "on_restricted_pick"} <= names


def test_core_job_callbacks_are_registered():
    names = _handler_names(_router(), "callback_query")
    assert {"on_cancel_btn", "on_retry", "on_redeliver",
            "on_profile_pick"} <= names
