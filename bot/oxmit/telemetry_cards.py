"""Telegram Telemetry Progress Cards & Formatters (v4.0).

Implements the 4-phase Telegram progress card lifecycle:
- Stage 0: Queued (در انتظار نوبت در صف)
- Stage 1: Download (در حال دانلود فایل از تلگرام)
- Stage 2: Encode (فشرده‌سازی / ادغام ویدیو)
- Stage 3: Upload (در حال آپلود در تلگرام)
- Completion: Summary of completed job with savings %

Includes standard progress bar renderer and natural Persian duration formatting.
"""

from __future__ import annotations

import math
from typing import Any
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def render_progress_bar(pct: float, length: int = 12) -> str:
    """Render a graphical progress bar clamped between 0 and 100%.

    Example: [■■■■■■■■□□□□] 69.62%
    """
    clamped = max(0.0, min(100.0, float(pct)))
    filled = int(round((clamped / 100.0) * length))
    empty = max(0, length - filled)
    return "[" + ("■" * filled) + ("□" * empty) + f"] {clamped:.2f}%"


def fmt_duration_fa(seconds: float | int | None) -> str:
    """Format duration in seconds into natural, friendly Persian text."""
    if seconds is None or seconds < 0:
        return "نامشخص"
    s = int(round(seconds))
    if s < 60:
        return f"{s} ثانیه"
    mins = s // 60
    rem_s = s % 60
    if mins < 60:
        if rem_s == 0:
            return f"{mins} دقیقه"
        return f"{mins} دقیقه و {rem_s} ثانیه"
    hours = mins // 60
    rem_m = mins % 60
    if rem_m == 0:
        return f"{hours} ساعت"
    return f"{hours} ساعت و {rem_m} دقیقه"


def make_cancel_kb(job_id: str) -> InlineKeyboardMarkup:
    """Inline keyboard with immediate cancellation button."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ لغو پردازش", callback_data=f"canc:{job_id}")
    ]])


def render_stage_0_queued(
    *,
    active_jobs: int = 0,
    max_queue: int = 500,
    total_queued: int = 1,
    position: int = 1,
    initial_position: int = 1,
    jobs_ahead: int = 0,
    algorithm_fa: str = "عادلانه چرخشی (Fair-Share)",
    elapsed_seconds: float = 0.0,
    eta_seconds: float = 0.0,
    size_bytes: int = 0,
    profile: str = "edu480",
    user_name: str = "کاربر",
    user_id: int | str = 0,
    job_id: str = "",
    bar_length: int = 12,
) -> str:
    """Stage 0: Queued phase card."""
    init_pos = max(1, initial_position or position or 1)
    # QueueProgress = max(5.0, min(95.0, (1 - (current_position - 1) / max(initial_position, 1)) * 100))
    raw_pct = (1.0 - (max(1, position) - 1.0) / float(init_pos)) * 100.0
    pct = max(5.0, min(95.0, raw_pct))
    bar = render_progress_bar(pct, length=bar_length)

    size_mb = (size_bytes or 0) / (1024 * 1024)
    elapsed_str = fmt_duration_fa(elapsed_seconds)
    eta_str = f"حدود {fmt_duration_fa(eta_seconds)}" if eta_seconds > 0 else "به زودی"
    short_id = str(job_id)[:8]

    return (
        f"🎬 وضعیت پردازش ویدیو | Oxmit Engine\n\n"
        f"📌 تسک‌های فعال سیستم: {active_jobs}/{max_queue} (در صف: {total_queued})\n"
        f"⏳ مرحله ۰ از ۳: در انتظار نوبت پردازش...\n\n"
        f"{bar}\n\n"
        f"📍 جایگاه فعلی شما در صف: نفر {position} از {total_queued}\n"
        f"👥 کارهای جلوتر از شما: {jobs_ahead} ویدیو\n"
        f"⚖️ الگوریتم صف: {algorithm_fa}\n"
        f"⏱️ زمان سپری‌شده در صف: {elapsed_str}\n"
        f"⏳ زمان تخمینی تا شروع: {eta_str}\n"
        f"📦 مشخصات فایل: {size_mb:.2f} MB | پروفایل: {profile}\n"
        f"👤 کاربر: {user_name} ({user_id})\n"
        f"🆔 شناسه تسک: #{short_id}"
    )


def render_stage_1_download(
    *,
    active_jobs: int = 1,
    max_concurrent: int = 20,
    processed_bytes: int = 0,
    total_bytes: int = 0,
    speed_bps: float = 0.0,
    elapsed_seconds: float = 0.0,
    eta_seconds: float = 0.0,
    engine_name: str = "TDLib v1.8.68",
    user_name: str = "کاربر",
    user_id: int | str = 0,
    job_id: str = "",
    bar_length: int = 12,
) -> str:
    """Stage 1: Downloading phase card."""
    total_b = max(1, total_bytes)
    pct = max(0.0, min(100.0, (processed_bytes / total_b) * 100.0))
    bar = render_progress_bar(pct, length=bar_length)
    processed_mb = processed_bytes / (1024 * 1024)
    total_mb = total_b / (1024 * 1024)
    speed_mb = (speed_bps or 0.0) / (1024 * 1024)
    short_id = str(job_id)[:8]

    return (
        f"🎬 وضعیت پردازش ویدیو | Oxmit Engine\n\n"
        f"📌 تسک‌های فعال سیستم: {active_jobs}/{max_concurrent}\n"
        f"📥 مرحله ۱ از ۳: در حال دانلود فایل...\n\n"
        f"{bar}\n\n"
        f"📦 حجم پردازش‌شده: {processed_mb:.2f} MB از {total_mb:.2f} MB\n"
        f"⚡ سرعت دانلود: {speed_mb:.2f} MB/s\n"
        f"⏳ زمان باقی‌مانده (ETA): {fmt_duration_fa(eta_seconds)}\n"
        f"⏱️ زمان سپری‌شده: {fmt_duration_fa(elapsed_seconds)}\n"
        f"☁️ مقصد آپلود: تلگرام (Telegram)\n"
        f"⚙️ موتور پردازش: {engine_name}\n"
        f"👤 کاربر: {user_name} ({user_id})\n"
        f"🆔 شناسه تسک: #{short_id}"
    )


def render_stage_2_encode(
    *,
    active_jobs: int = 1,
    max_concurrent: int = 20,
    pct: float = 0.0,
    processed_bytes: int = 0,
    total_bytes: int = 0,
    speed_bps: float = 0.0,
    fps: float = 0.0,
    speed_x: float = 0.0,
    elapsed_seconds: float = 0.0,
    eta_seconds: float = 0.0,
    profile: str = "edu480",
    engine_name: str = "FFmpeg v8.0.1",
    user_name: str = "کاربر",
    user_id: int | str = 0,
    job_id: str = "",
    part_idx: int = 1,
    total_parts: int = 1,
    bar_length: int = 12,
) -> str:
    """Stage 2: Encoding phase card."""
    bar = render_progress_bar(pct, length=bar_length)
    processed_mb = processed_bytes / (1024 * 1024)
    total_mb = max(1, total_bytes) / (1024 * 1024)
    speed_mb = (speed_bps or 0.0) / (1024 * 1024)
    short_id = str(job_id)[:8]

    speed_info = f"{speed_mb:.2f} MB/s"
    if fps > 0 or speed_x > 0:
        speed_info += f" (فریم‌ریت: {int(round(fps))} fps | {speed_x:.1f}x)"

    return (
        f"🎬 وضعیت پردازش ویدیو | Oxmit Engine\n\n"
        f"📌 تسک‌های فعال سیستم: {active_jobs}/{max_concurrent}\n"
        f"🎞️ مرحله ۲ از ۳: فشرده‌سازی ویدیو ({part_idx}/{total_parts})...\n\n"
        f"{bar}\n\n"
        f"📦 حجم پردازش‌شده: {processed_mb:.2f} MB از {total_mb:.2f} MB\n"
        f"⚡ سرعت پردازش: {speed_info}\n"
        f"⏳ زمان باقی‌مانده (ETA): {fmt_duration_fa(eta_seconds)}\n"
        f"⏱️ زمان سپری‌شده: {fmt_duration_fa(elapsed_seconds)}\n"
        f"☁️ مقصد آپلود: تلگرام (Telegram)\n"
        f"⚙️ موتور پردازش: {engine_name} ({profile})\n"
        f"👤 کاربر: {user_name} ({user_id})\n"
        f"🆔 شناسه تسک: #{short_id}"
    )


def render_stage_3_upload(
    *,
    active_jobs: int = 1,
    max_concurrent: int = 20,
    pct: float = 0.0,
    uploaded_bytes: int = 0,
    total_bytes: int = 0,
    speed_bps: float = 0.0,
    elapsed_seconds: float = 0.0,
    eta_seconds: float = 0.0,
    engine_name: str = "TDLib v1.8.68",
    user_name: str = "کاربر",
    user_id: int | str = 0,
    job_id: str = "",
    bar_length: int = 12,
) -> str:
    """Stage 3: Uploading phase card."""
    bar = render_progress_bar(pct, length=bar_length)
    uploaded_mb = uploaded_bytes / (1024 * 1024)
    total_mb = max(1, total_bytes) / (1024 * 1024)
    speed_mb = (speed_bps or 0.0) / (1024 * 1024)
    short_id = str(job_id)[:8]

    return (
        f"🎬 وضعیت پردازش ویدیو | Oxmit Engine\n\n"
        f"📌 تسک‌های فعال سیستم: {active_jobs}/{max_concurrent}\n"
        f"📤 مرحله ۳ از ۳: در حال آپلود در تلگرام...\n\n"
        f"{bar}\n\n"
        f"📦 حجم آپلودشده: {uploaded_mb:.2f} MB از {total_mb:.2f} MB\n"
        f"⚡ سرعت آپلود: {speed_mb:.2f} MB/s\n"
        f"⏳ زمان باقی‌مانده (ETA): {fmt_duration_fa(eta_seconds)}\n"
        f"⏱️ زمان سپری‌شده: {fmt_duration_fa(elapsed_seconds)}\n"
        f"☁️ مقصد آپلود: تلگرام (Telegram)\n"
        f"⚙️ موتور پردازش: {engine_name}\n"
        f"👤 کاربر: {user_name} ({user_id})\n"
        f"🆔 شناسه تسک: #{short_id}"
    )


def render_stage_complete(
    *,
    filename: str,
    source_bytes: int,
    output_bytes: int,
    elapsed_seconds: float,
    job_id: str,
) -> str:
    """Final completion summary card."""
    src_mb = (source_bytes or 0) / (1024 * 1024)
    out_mb = (output_bytes or 0) / (1024 * 1024)
    saved_bytes = max(0, (source_bytes or 0) - (output_bytes or 0))
    savings_pct = (saved_bytes / max(1, source_bytes or 1)) * 100.0 if source_bytes else 0.0
    short_id = str(job_id)[:8]

    return (
        f"✅ فشرده‌سازی ویدیو با موفقیت انجام شد!\n\n"
        f"🎞️ فایل: {filename}\n"
        f"📉 حجم اولیه: {src_mb:.2f} MB ➡️ حجم نهایی: {out_mb:.2f} MB ({savings_pct:.1f}٪ صرفه‌جویی)\n"
        f"⏱️ کل زمان پردازش: {fmt_duration_fa(elapsed_seconds)}\n"
        f"🆔 شناسه تسک: #{short_id}"
    )
