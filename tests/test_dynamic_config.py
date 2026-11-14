import pytest
from unittest.mock import AsyncMock
from bot.oxmit.dynamic_config import DynamicConfig, DEFAULT_SETTINGS


@pytest.mark.asyncio
async def test_dynamic_config_defaults():
    db = AsyncMock()
    db.fetch.return_value = []
    cfg = DynamicConfig(db)
    await cfg.init()

    assert cfg.get_bool("accepting_new_jobs") is True
    assert cfg.get_int("max_global_queue_size") == 500
    assert cfg.get_int("active_encoding_workers") == 2
    assert cfg.get_str("queue_scheduling_mode") == "fair_round_robin"
    assert cfg.get_bool("admin_queue_bypass") is False
    assert cfg.get_int("progress_update_interval_sec") == 4
    assert cfg.get_int("progress_bar_length") == 12


@pytest.mark.asyncio
async def test_dynamic_config_db_load():
    db = AsyncMock()
    db.fetch.return_value = [
        {
            "key": "max_global_queue_size",
            "value": 1000,
            "value_type": "int",
            "title_fa": "ظرفیت",
            "description_fa": "",
            "updated_at": "2026-11-14T10:00:00Z",
        },
        {
            "key": "admin_queue_bypass",
            "value": True,
            "value_type": "bool",
            "title_fa": "بای پس",
            "description_fa": "",
            "updated_at": "2026-11-14T10:00:00Z",
        },
    ]
    cfg = DynamicConfig(db)
    await cfg.init()

    assert cfg.get_int("max_global_queue_size") == 1000
    assert cfg.get_bool("admin_queue_bypass") is True


@pytest.mark.asyncio
async def test_dynamic_config_set_and_listener():
    db = AsyncMock()
    db.fetch.return_value = []
    cfg = DynamicConfig(db)
    await cfg.init()

    changes = []
    cfg.subscribe(lambda k, v: changes.append((k, v)))

    await cfg.set("active_encoding_workers", 4)
    assert cfg.get_int("active_encoding_workers") == 4
    assert len(changes) == 1
    assert changes[0] == ("active_encoding_workers", 4)
    db.execute.assert_called_once()
