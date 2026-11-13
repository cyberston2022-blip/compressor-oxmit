"""Unit and integration tests for Super-Admin modules (superadmin.py).
"""
import os
import tempfile
from pathlib import Path
import pytest
from oxmit.panel.superadmin import (
    ALLOWED_ROOTS,
    _is_safe_path,
    list_directory,
    delete_file,
    read_env_file,
    save_env_file,
    get_ffmpeg_params,
    update_ffmpeg_params,
    trigger_db_backup,
)


def test_is_safe_path_allowed_roots():
    for root in ALLOWED_ROOTS:
        assert _is_safe_path(root) is True
        assert _is_safe_path(f"{root}/sub/file.txt") is True


def test_is_safe_path_blocks_traversal_and_forbidden():
    assert _is_safe_path("/media/../etc/passwd") is False
    assert _is_safe_path("/media_secret") is False
    assert _is_safe_path("/etc/shadow") is False
    assert _is_safe_path("../../../windows/system32") is False


def test_list_directory_nonexistent():
    res = list_directory("/nonexistent_directory_12345")
    assert res.get("error") is not None
    assert res.get("entries") == []


def test_delete_file_safety(tmp_path):
    # Test path not allowed
    res = delete_file("/etc/passwd")
    assert res.get("ok") is False
    assert "not allowed" in res.get("error", "").lower()

    # Test directory delete blocked
    res_dir = delete_file("/media")
    assert res_dir.get("ok") is False


def test_env_file_lifecycle(tmp_path):
    env_file = tmp_path / ".env"
    initial_content = (
        "# Configuration File\n"
        "APP_NAME=Oxmit\n"
        "LOG_LEVEL=INFO\n"
        "# Database settings\n"
        "PG_PORT=5432\n"
    )
    env_file.write_text(initial_content, encoding="utf-8")

    # 1. Read
    read_res = read_env_file(str(env_file))
    assert read_res.get("vars", {}).get("APP_NAME") == "Oxmit"
    assert read_res.get("vars", {}).get("LOG_LEVEL") == "INFO"
    assert read_res.get("vars", {}).get("PG_PORT") == "5432"

    # 2. Modify one, delete one, add one
    updated_vars = {
        "APP_NAME": "Oxmit Pro",
        "PG_PORT": "5432",
        "NEW_KEY": "12345",
        # LOG_LEVEL is omitted -> must be removed!
    }
    save_res = save_env_file(updated_vars, str(env_file))
    assert save_res.get("ok") is True

    # 3. Re-read and assert
    reread = read_env_file(str(env_file))
    vars_now = reread.get("vars", {})
    assert vars_now.get("APP_NAME") == "Oxmit Pro"
    assert "LOG_LEVEL" not in vars_now
    assert vars_now.get("NEW_KEY") == "12345"

    # 4. Comments preserved
    content_now = env_file.read_text(encoding="utf-8")
    assert "# Configuration File" in content_now
    assert "# Database settings" in content_now


def test_ffmpeg_params():
    params = get_ffmpeg_params()
    assert "crf" in params
    assert "preset" in params
    assert "video_codec" in params
    assert "max_height" in params
    assert "max_fps" in params

    # Update valid
    res = update_ffmpeg_params({"crf": 26, "preset": "fast", "max_height": 720})
    assert res.get("ok") is True
    assert res.get("applied", {}).get("crf") == 26
    assert res.get("applied", {}).get("preset") == "fast"

    # Update invalid bounds
    res_bad = update_ffmpeg_params({"crf": 999, "preset": "invalid_preset"})
    assert res_bad.get("ok") is False
    assert "crf" in res_bad.get("errors", {})
    assert "preset" in res_bad.get("errors", {})


@pytest.mark.asyncio
async def test_trigger_db_backup_fallback(tmp_path):
    # Test backup trigger with invalid or mock URL creates snapshot without crash
    fake_url = "postgresql://user:pass@localhost:5432/testdb"
    res = await trigger_db_backup(fake_url, backup_dir=str(tmp_path))
    assert res.get("ok") is True
    assert os.path.exists(res.get("path"))
    assert res.get("size") > 0
