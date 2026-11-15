"""Tests for v4.2 UI & Data Synchronization Fixes.

Covers:
1. summary_data calculation, stage grouping and math.ceil safety.
2. get_containers returning both 'status' and 'state'.
3. preview_queue_order returning source_size, file_size_bytes, and size_formatted.
4. list_bot_users returning total_requests matching jobs count.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from oxmit.webpanel import summary_data
from oxmit.panel.docker_manager import DockerManager
from oxmit.queue_scheduler import QueueScheduler
from oxmit.panel.bot_manager import list_bot_users


@pytest.mark.asyncio
async def test_summary_data_no_math_name_error():
    """Verify summary_data runs without NameError and groups stages properly."""
    db = MagicMock()
    # Mock database queries
    async def mock_fetchval(query, *args):
        if "status = 'processing'" in query:
            return 6
        if "status = 'queued'" in query:
            return 15
        if "status = 'completed'" in query:
            return 42
        if "status = 'failed'" in query:
            return 3
        if "source_size - output_size" in query:
            return 1024 * 1024 * 500  # 500 MB
        if "SELECT count(*) FROM users" in query:
            return 100
        if "AVG(EXTRACT(EPOCH" in query:
            return 65.0
        return 0

    async def mock_fetch(query, *args):
        if "GROUP BY stage" in query:
            return [
                {"stage": "downloading", "cnt": 2},
                {"stage": "encoding", "cnt": 3},
                {"stage": "validating", "cnt": 1},
            ]
        if "SELECT name, value FROM counters" in query:
            return [{"name": "requests_total", "value": 500}]
        return []

    db.fetchval = AsyncMock(side_effect=mock_fetchval)
    db.fetch = AsyncMock(side_effect=mock_fetch)

    cfg = SimpleNamespace(
        media_root="/tmp",
        worker_replicas=3,
        owner_telegram_id=123456,
    )
    state = SimpleNamespace(
        started_at=1000.0,
        paused=False,
    )
    engine = SimpleNamespace(
        dynamic_config=None,
        get_me_cached=AsyncMock(),
        _me=None,
    )

    data = await summary_data(engine, db, cfg, state)
    assert data["active"] == 6
    assert data["queued"] == 15
    assert data["jobs_today"] == 45
    assert data["counters"]["active"] == 6
    assert data["counters"]["queued"] == 15
    assert data["counters"]["downloading"] == 2
    assert data["counters"]["encoding"] == 4  # 3 encoding + 1 validating
    assert data["counters"]["uploading"] == 0
    assert "est_clear_time_fa" in data["counters"]
    assert data["counters"]["est_clear_time_fa"] != ""


@pytest.mark.asyncio
async def test_docker_containers_has_state_and_status():
    """Verify get_containers exposes state key matching status."""
    dm = DockerManager()
    containers = await dm.get_containers()
    assert len(containers) > 0
    for c in containers:
        assert "status" in c
        assert "state" in c
        assert c["status"] == c["state"]


@pytest.mark.asyncio
async def test_preview_queue_order_file_size_fields():
    """Verify preview_queue_order returns source_size, file_size_bytes, and size_formatted."""
    db = MagicMock()
    async def mock_fetch(query, *args):
        return [{
            "global_queue_position": 1,
            "id": "11111111-1111-1111-1111-111111111111",
            "jid": "11111111",
            "user_id": 999,
            "first_name": "Ali",
            "username": "ali_user",
            "is_vip": False,
            "is_admin_job": False,
            "priority_boost": 0,
            "enqueued_at": datetime.now(timezone.utc),
            "source_size": 150 * 1024 * 1024,  # 150 MB
            "filename": "test.mp4",
            "duration_s": 120.0,
            "profile": "edu480",
        }]
    db.fetch = AsyncMock(side_effect=mock_fetch)
    cfg = MagicMock()
    cfg.get_str.return_value = "fair_round_robin"
    cfg.get_int.return_value = 300
    cfg.get_bool.return_value = False

    sched = QueueScheduler(db=db, dynamic_config=cfg)
    items = await sched.preview_queue_order(limit=1)
    assert len(items) == 1
    item = items[0]
    assert item["source_size"] == 150 * 1024 * 1024
    assert item["file_size_bytes"] == 150 * 1024 * 1024
    assert item["size_bytes"] == 150 * 1024 * 1024
    assert "MB" in item["size_formatted"] or "150" in item["size_formatted"]


@pytest.mark.asyncio
async def test_list_bot_users_total_requests():
    """Verify list_bot_users maps total_requests correctly."""
    db = MagicMock()
    db.fetchval = AsyncMock(return_value=1)
    async def mock_fetch(query, *args):
        return [{
            "tg_id": 12345,
            "username": "user1",
            "first_name": "Test User",
            "is_blocked": False,
            "is_vip": False,
            "is_admin": False,
            "banned_at": None,
            "ban_reason": None,
            "created_at": datetime.now(timezone.utc),
            "last_seen_at": datetime.now(timezone.utc),
            "total_requests": 0,
            "total_jobs": 12,  # User has 12 jobs in jobs table
            "jobs24": 3,
            "pending_jobs": 1,
        }]
    db.fetch = AsyncMock(side_effect=mock_fetch)

    res = await list_bot_users(db, page=1, limit=10)
    assert res["total"] == 1
    u = res["users"][0]
    assert u["total_requests"] == 12
    assert u["jobs_count"] == 12
