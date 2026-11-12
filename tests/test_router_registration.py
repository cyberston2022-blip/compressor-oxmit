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


def test_filename_text_handler_is_registered():
    # The output-name answer is the second step of every submission.
    assert "on_name_text" in _handler_names(_router(), "message")


def test_media_intake_handler_is_registered():
    assert "on_media" in _handler_names(_router(), "message")


def test_naming_buttons_registered():
    assert "on_name_button" in _handler_names(_router(), "callback_query")


def test_core_job_callbacks_are_registered():
    names = _handler_names(_router(), "callback_query")
    assert {"on_cancel_btn", "on_retry", "on_redeliver"} <= names


def test_no_profile_picker_remains():
    # EDU480 is the only profile: no profile-grid / level / cache-offer handlers.
    names = _handler_names(_router(), "callback_query") | _handler_names(_router(), "message")
    assert not names & {"on_profile_pick", "on_percent_text", "on_use_cached",
                        "on_compress_profile_btn", "on_custom_size"}
