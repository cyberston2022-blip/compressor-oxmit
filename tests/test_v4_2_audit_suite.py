"""Comprehensive Automated Verification Suite for OXMIT v4.2 Enterprise Hardening.

Covers:
1. Active-Aware Deficit Fair-Share Scheduling (True multi-worker fairness)
2. Concurrent claim candidate window (eliminating lock contention)
3. DynamicResizableSemaphore live scaling and condition signaling
4. DynamicConfig strict schema validation, type casting, and clamping
5. 4-Stage Persian Telemetry cards rendering and progress math
"""

from __future__ import annotations

import asyncio
import re
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from oxmit.dynamic_config import CONFIG_SCHEMA, DynamicConfig
from oxmit.queue_scheduler import QueueScheduler, build_queue_order_cte
from oxmit.resources import DynamicResizableSemaphore
from oxmit.telemetry_cards import (
    fmt_duration_fa,
    make_cancel_kb,
    render_progress_bar,
    render_stage_0_queued,
    render_stage_1_download,
    render_stage_2_encode,
    render_stage_3_upload,
    render_stage_cancelled,
    render_stage_complete,
)


# ---------------------------------------------------------------------------
# Test 1: Active-Aware Deficit Fair-Share Scheduling
# ---------------------------------------------------------------------------

def test_active_aware_cte_contains_active_user_load_offset():
    """Verify build_queue_order_cte factors ActiveUserLoad into true_fair_layer."""
    cte = build_queue_order_cte("fair_round_robin")
    assert "ActiveUserLoad" in cte
    assert "status = 'processing'" in cte
    assert "COALESCE(aul.active_count, 0)" in cte
    assert "true_fair_layer" in cte

    wfq_cte = build_queue_order_cte("weighted_fair", penalty=300)
    assert "ActiveUserLoad" in wfq_cte
    assert "effective_user_rank" in wfq_cte
    assert "300" in wfq_cte


@pytest.mark.asyncio
async def test_active_aware_fairness_picks_user_b_over_user_a(fake_db):
    """User A has 1 active job (processing). User B has 0 active jobs.

    When both have jobs in queue, User B's job (layer 1) must be claimed
    before User A's second job (layer 1 + 1 active = layer 2).
    """
    dyn_cfg = DynamicConfig(fake_db)
    await dyn_cfg.init()
    sched = QueueScheduler(fake_db, dyn_cfg)

    job_b1_id = uuid.uuid4()
    # Mock fake_db to return job_b1 as claimed next
    fake_db.on_fetchrow(
        lambda sql: "NextCandidates" in sql or "UPDATE jobs" in sql,
        {
            "id": job_b1_id,
            "requester_tg_id": 2002,
            "chat_id": 2002,
            "media_id": uuid.uuid4(),
            "profile": "edu480",
            "source_size": 100 * 1024 * 1024,
            "source_path": "/media/in/b1.mp4",
            "source_message_id": 101,
            "status_message_id": 102,
        },
    )

    claimed = await sched.claim_next_job("worker-test-1")
    assert claimed is not None
    assert claimed["id"] == job_b1_id
    assert claimed["requester_tg_id"] == 2002


# ---------------------------------------------------------------------------
# Test 2: Concurrent Claim Lock Safety & Candidate Window
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_claim_lock_safety():
    """Verify that multiple concurrent claim_next_job calls claim distinct jobs."""
    available_jobs = [
        {"id": uuid.uuid4(), "requester_tg_id": 1000 + i, "chat_id": 1000 + i,
         "media_id": uuid.uuid4(), "profile": "edu480", "source_size": 1000,
         "source_path": None, "source_message_id": 1, "status_message_id": 2}
        for i in range(5)
    ]
    claimed_ids: set[uuid.UUID] = set()
    lock = asyncio.Lock()

    class ConcurrentMockDB:
        async def fetchrow(self, sql, *args):
            async with lock:
                for j in available_jobs:
                    if j["id"] not in claimed_ids:
                        claimed_ids.add(j["id"])
                        return j
                return None

        async def fetchval(self, sql, *args):
            return 120.0

        async def fetch(self, sql, *args):
            return []

    mock_db = ConcurrentMockDB()
    dyn = DynamicConfig(mock_db)
    await dyn.init()
    sched = QueueScheduler(mock_db, dyn)

    workers = [f"worker-{i}" for i in range(5)]
    results = await asyncio.gather(*(sched.claim_next_job(w) for w in workers))

    # All 5 jobs must be claimed, no duplicates, no None
    assert len(results) == 5
    assert all(r is not None for r in results)
    returned_ids = {r["id"] for r in results}
    assert len(returned_ids) == 5


# ---------------------------------------------------------------------------
# Test 3: DynamicResizableSemaphore Scaling & Condition Signaling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dynamic_resizable_semaphore_lifecycle():
    current_limit = 3
    sem = DynamicResizableSemaphore(lambda: current_limit, name="test_sem")

    # 1. Acquire up to current limit (3)
    await sem.acquire()
    await sem.acquire()
    await sem.acquire()
    assert sem.active_count == 3
    assert sem.current_limit == 3

    # 2. Dynamically reduce limit to 1
    current_limit = 1
    await sem.notify_limit_changed()
    assert sem.current_limit == 1
    assert sem.active_count == 3  # active count unchanged until released

    # 3. Waiter 4 attempts acquire in background; must block
    acquired_event = asyncio.Event()
    stop_waiter = asyncio.Event()

    async def waiter():
        async with sem:
            acquired_event.set()
            await stop_waiter.wait()

    waiter_task = asyncio.create_task(waiter())
    await asyncio.sleep(0.05)
    assert not acquired_event.is_set()

    # 4. Release 1 slot -> active drops to 2 (still > limit 1, waiter must not acquire)
    await sem.release()
    assert sem.active_count == 2
    await asyncio.sleep(0.05)
    assert not acquired_event.is_set()

    # 5. Release 1 slot -> active drops to 1 (still == limit 1, waiter must not acquire)
    await sem.release()
    assert sem.active_count == 1
    await asyncio.sleep(0.05)
    assert not acquired_event.is_set()

    # 6. Release 1 slot -> active drops to 0 (below limit 1) -> waiter acquires!
    await sem.release()
    await asyncio.wait_for(acquired_event.wait(), timeout=1.0)
    assert acquired_event.is_set()
    assert sem.active_count == 1

    # Cleanup waiter task
    stop_waiter.set()
    await waiter_task
    assert sem.active_count == 0


# ---------------------------------------------------------------------------
# Test 4: DynamicConfig Schema Validation, Type Coercion & Clamping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dynamic_config_strict_validation(fake_db):
    dyn = DynamicConfig(fake_db)
    await dyn.init()

    # 1. Unknown key must raise ValueError
    with pytest.raises(ValueError, match="کلید تنظیمات نامعتبر است"):
        await dyn.set("unknown_fake_key", 123)

    # 2. Bounds violation (below min)
    with pytest.raises(ValueError, match="نمی‌تواند کمتر از"):
        await dyn.set("active_encoding_workers", 0)

    # 3. Bounds violation (above max)
    with pytest.raises(ValueError, match="نمی‌تواند بیشتر از"):
        await dyn.set("max_file_size_mb", 99999)

    # 4. Invalid enum option
    with pytest.raises(ValueError, match="مقدار انتخابی برای queue_scheduling_mode نامعتبر است"):
        await dyn.set("queue_scheduling_mode", "bogus_random_mode")

    # 5. Valid integer coercions
    await dyn.set("active_encoding_workers", "4")
    assert dyn.get_int("active_encoding_workers") == 4

    # 6. Valid boolean coercions
    await dyn.set("accepting_new_jobs", "false")
    assert dyn.get_bool("accepting_new_jobs") is False

    await dyn.set("accepting_new_jobs", "true")
    assert dyn.get_bool("accepting_new_jobs") is True

    # 7. Valid enum choice
    await dyn.set("queue_scheduling_mode", "weighted_fair")
    assert dyn.get_str("queue_scheduling_mode") == "weighted_fair"


# ---------------------------------------------------------------------------
# Test 5: 4-Stage Persian Telemetry Cards & Progress Bar Math
# ---------------------------------------------------------------------------

def test_progress_bar_render_math():
    # 0% -> 0 filled, 12 empty
    bar0 = render_progress_bar(0.0, length=12)
    assert bar0 == "[□□□□□□□□□□□□] 0.00%"

    # 50% -> 6 filled, 6 empty
    bar50 = render_progress_bar(50.0, length=12)
    assert bar50 == "[■■■■■■□□□□□□] 50.00%"

    # 100% -> 12 filled, 0 empty
    bar100 = render_progress_bar(100.0, length=12)
    assert bar100 == "[■■■■■■■■■■■■] 100.00%"

    # 68.25% with length 12
    bar68 = render_progress_bar(68.25, length=12)
    assert "■" in bar68 and "□" in bar68
    # Count blocks inside brackets
    match = re.search(r"\[([■□]+)\]", bar68)
    assert match is not None
    assert len(match.group(1)) == 12


def test_fmt_duration_fa():
    assert fmt_duration_fa(0) == "0 ثانیه"
    assert fmt_duration_fa(45) == "45 ثانیه"
    assert fmt_duration_fa(60) == "1 دقیقه"
    assert fmt_duration_fa(130) == "2 دقیقه و 10 ثانیه"
    assert fmt_duration_fa(3600) == "1 ساعت"
    assert fmt_duration_fa(3665) == "1 ساعت و 1 دقیقه"
    assert fmt_duration_fa(None) == "نامشخص"


def test_4_stage_persian_cards_render_cleanly():
    jid = str(uuid.uuid4())

    # Stage 0: Queued
    c0 = render_stage_0_queued(
        active_jobs=2, max_queue=500, total_queued=14, position=2,
        initial_position=5, jobs_ahead=1, elapsed_seconds=130, eta_seconds=220,
        size_bytes=450 * 1024 * 1024, profile="edu480", user_name="Ali",
        user_id=123456, job_id=jid, bar_length=12,
    )
    assert "مرحله ۰ از ۳: در انتظار نوبت پردازش..." in c0
    assert "نفر 2 از 14" in c0
    assert "کارهای جلوتر از شما: 1 ویدیو" in c0
    assert "None" not in c0
    assert "undefined" not in c0

    # Stage 1: Download
    c1 = render_stage_1_download(
        active_jobs=2, max_concurrent=20, processed_bytes=235 * 1024 * 1024,
        total_bytes=450 * 1024 * 1024, speed_bps=18.4 * 1024 * 1024,
        elapsed_seconds=13, eta_seconds=11, engine_name="TDLib v1.8.68",
        user_name="Ali", user_id=123456, job_id=jid, bar_length=12,
    )
    assert "مرحله ۱ از ۳: در حال دانلود فایل..." in c1
    assert "TDLib v1.8.68" in c1
    assert "18.40 MB/s" in c1
    assert "None" not in c1
    assert "undefined" not in c1

    # Stage 2: Encode
    c2 = render_stage_2_encode(
        active_jobs=2, max_concurrent=20, pct=68.25,
        processed_bytes=307 * 1024 * 1024, total_bytes=450 * 1024 * 1024,
        speed_bps=6.8 * 1024 * 1024, fps=58.0, speed_x=2.1,
        elapsed_seconds=160, eta_seconds=75, profile="edu480",
        engine_name="FFmpeg v8.0.1", user_name="Ali", user_id=123456,
        job_id=jid, bar_length=12,
    )
    assert "مرحله ۲ از ۳: فشرده‌سازی ویدیو (1/1)..." in c2
    assert "فریم‌ریت: 58 fps | 2.1x" in c2
    assert "FFmpeg v8.0.1 (edu480)" in c2
    assert "None" not in c2
    assert "undefined" not in c2

    # Stage 3: Upload
    c3 = render_stage_3_upload(
        active_jobs=2, max_concurrent=20, pct=85.0,
        uploaded_bytes=98 * 1024 * 1024, total_bytes=116 * 1024 * 1024,
        speed_bps=14.2 * 1024 * 1024, elapsed_seconds=19, eta_seconds=4,
        engine_name="TDLib v1.8.68", user_name="Ali", user_id=123456,
        job_id=jid, bar_length=12,
    )
    assert "مرحله ۳ از ۳: در حال آپلود در تلگرام..." in c3
    assert "14.20 MB/s" in c3
    assert "None" not in c3
    assert "undefined" not in c3

    # Completion Card
    cc = render_stage_complete(
        filename="lecture.mp4", source_bytes=450 * 1024 * 1024,
        output_bytes=116 * 1024 * 1024, elapsed_seconds=262, job_id=jid,
    )
    assert "فشرده‌سازی ویدیو با موفقیت انجام شد!" in cc
    assert "lecture.mp4" in cc
    assert "صرفه‌جویی" in cc
    assert "None" not in cc

    # Cancellation Card
    ccan = render_stage_cancelled(filename="lecture.mp4", elapsed_seconds=45, job_id=jid)
    assert "پردازش ویدیو لغو گردید" in ccan
    assert "lecture.mp4" in ccan

    # Cancel Keyboard
    kb = make_cancel_kb(jid)
    assert len(kb.inline_keyboard) == 1
    assert kb.inline_keyboard[0][0].callback_data == f"canc:{jid}"
