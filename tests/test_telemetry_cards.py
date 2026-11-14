import pytest
from bot.oxmit.telemetry_cards import (
    render_progress_bar,
    fmt_duration_fa,
    render_stage_0_queued,
    render_stage_1_download,
    render_stage_2_encode,
    render_stage_3_upload,
    render_stage_complete,
    make_cancel_kb,
)


def test_render_progress_bar():
    assert render_progress_bar(0.0, length=12) == "[□□□□□□□□□□□□] 0.00%"
    assert render_progress_bar(100.0, length=12) == "[■■■■■■■■■■■■] 100.00%"
    assert render_progress_bar(50.0, length=12) == "[■■■■■■□□□□□□] 50.00%"
    assert render_progress_bar(8.33, length=12) == "[■□□□□□□□□□□□] 8.33%"


def test_fmt_duration_fa():
    assert fmt_duration_fa(24) == "24 ثانیه"
    assert fmt_duration_fa(80) == "1 دقیقه و 20 ثانیه"
    assert fmt_duration_fa(120) == "2 دقیقه"
    assert fmt_duration_fa(840) == "14 دقیقه"
    assert fmt_duration_fa(3660) == "1 ساعت و 1 دقیقه"


def test_render_stage_0_queued():
    txt = render_stage_0_queued(
        active_jobs=2,
        max_queue=500,
        total_queued=54,
        position=12,
        initial_position=12,
        jobs_ahead=11,
        algorithm_fa="عادلانه چرخشی (Fair-Share)",
        elapsed_seconds=80,
        eta_seconds=840,
        size_bytes=814780000,
        profile="edu480",
        user_name="MMLI",
        user_id=5208152418,
        job_id="0f03634a-1111-2222-3333-444444444444",
        bar_length=12,
    )
    assert "🎬 وضعیت پردازش ویدیو | Oxmit Engine" in txt
    assert "تسک‌های فعال سیستم: 2/500 (در صف: 54)" in txt
    assert "مرحله ۰ از ۳: در انتظار نوبت پردازش..." in txt
    assert "جایگاه فعلی شما در صف: نفر 12 از 54" in txt
    assert "کارهای جلوتر از شما: 11 ویدیو" in txt
    assert "الگوریتم صف: عادلانه چرخشی (Fair-Share)" in txt
    assert "زمان سپری‌شده در صف: 1 دقیقه و 20 ثانیه" in txt
    assert "زمان تخمینی تا شروع: حدود 14 دقیقه" in txt
    assert "کاربر: MMLI (5208152418)" in txt
    assert "#0f03634a" in txt


def test_render_stage_1_download():
    txt = render_stage_1_download(
        active_jobs=2,
        max_concurrent=20,
        processed_bytes=294523371,
        total_bytes=423030292,
        speed_bps=5337251,
        elapsed_seconds=55,
        eta_seconds=24,
        engine_name="TDLib v1.8.68",
        user_name="MMLI",
        user_id=5208152418,
        job_id="0f03634a",
    )
    assert "مرحله ۱ از ۳: در حال دانلود فایل..." in txt
    assert "سرعت دانلود: 5.09 MB/s" in txt
    assert "زمان باقی‌مانده (ETA): 24 ثانیه" in txt
    assert "موتور پردازش: TDLib v1.8.68" in txt


def test_render_stage_2_encode():
    txt = render_stage_2_encode(
        active_jobs=2,
        max_concurrent=20,
        pct=74.60,
        processed_bytes=626265000,
        total_bytes=839446000,
        speed_bps=29500000,
        fps=142,
        speed_x=4.8,
        elapsed_seconds=94,
        eta_seconds=7,
        profile="edu480",
        engine_name="FFmpeg v8.0.1",
        user_name="MMLI",
        user_id=5208152418,
        job_id="0f03634a",
    )
    assert "مرحله ۲ از ۳: فشرده‌سازی ویدیو (1/1)..." in txt
    assert "74.60%" in txt
    assert "142 fps | 4.8x" in txt
    assert "FFmpeg v8.0.1 (edu480)" in txt


def test_render_stage_3_upload():
    txt = render_stage_3_upload(
        active_jobs=2,
        max_concurrent=20,
        pct=16.60,
        uploaded_bytes=141818265,
        total_bytes=854425313,
        speed_bps=12897484,
        elapsed_seconds=112,
        eta_seconds=55,
        engine_name="TDLib v1.8.68",
        user_name="MMLI",
        user_id=5208152418,
        job_id="0f03634a",
    )
    assert "مرحله ۳ از ۳: در حال آپلود در تلگرام..." in txt
    assert "16.60%" in txt
    assert "سرعت آپلود: 12.30 MB/s" in txt


def test_render_stage_complete():
    txt = render_stage_complete(
        filename="watermarked.mp4",
        source_bytes=854425313,
        output_bytes=243374489,
        elapsed_seconds=138,
        job_id="0f03634a",
    )
    assert "✅ فشرده‌سازی ویدیو با موفقیت انجام شد!" in txt
    assert "watermarked.mp4" in txt
    assert "صرفه‌جویی" in txt
    assert "2 دقیقه و 18 ثانیه" in txt


def test_cancel_kb():
    kb = make_cancel_kb("test-uuid")
    assert kb.inline_keyboard[0][0].callback_data == "canc:test-uuid"
    assert "لغو" in kb.inline_keyboard[0][0].text
