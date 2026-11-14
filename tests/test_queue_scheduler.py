import pytest
from unittest.mock import AsyncMock
from bot.oxmit.dynamic_config import DynamicConfig
from bot.oxmit.queue_scheduler import QueueScheduler, build_queue_order_cte


def test_build_queue_order_cte():
    cte_rr = build_queue_order_cte("fair_round_robin")
    assert "fair_layer" in cte_rr
    assert "PARTITION BY j.requester_tg_id" in cte_rr

    cte_wfq = build_queue_order_cte("weighted_fair")
    assert "user_rank_index" in cte_wfq
    assert "INTERVAL '1 second'" in cte_wfq

    cte_fifo = build_queue_order_cte("strict_fifo")
    assert "fair_layer" not in cte_fifo
    assert "enqueued_at ASC" in cte_fifo

    cte_size = build_queue_order_cte("size_aware_fair")
    assert "source_size" in cte_size


@pytest.mark.asyncio
async def test_queue_scheduler_claim_next_job():
    db = AsyncMock()
    # Mock return of claim row
    db.fetchrow.return_value = {
        "id": "11111111-2222-3333-4444-555555555555",
        "requester_tg_id": 123456,
        "chat_id": 123456,
        "media_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "profile": "edu480",
        "source_size": 1000000,
        "source_path": None,
        "source_message_id": 10,
        "status_message_id": 11,
    }
    cfg = DynamicConfig(db)
    await cfg.init()
    sched = QueueScheduler(db, cfg)

    claimed = await sched.claim_next_job("worker-test")
    assert claimed is not None
    assert claimed["id"] == "11111111-2222-3333-4444-555555555555"
    db.fetchrow.assert_called_once()


@pytest.mark.asyncio
async def test_queue_scheduler_details():
    db = AsyncMock()
    db.fetchrow.return_value = {
        "global_queue_position": 5,
        "total_count": 20,
    }
    db.fetchval.return_value = 120.0
    cfg = DynamicConfig(db)
    await cfg.init()
    sched = QueueScheduler(db, cfg)

    details = await sched.get_job_queue_details("11111111-2222-3333-4444-555555555555")
    assert details is not None
    assert details["global_queue_position"] == 5
    assert details["jobs_ahead"] == 4
    assert details["total_queued"] == 20
    # active_workers default = 2, wait_cycles = ceil(4 / 2) = 2 -> 2 * 120 = 240s
    assert details["estimated_wait_seconds"] == 240
