"""Bilingual strings (fa default, en optional) + tr() helper."""

from __future__ import annotations

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_EN_TO_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def normalize_digits(text: str | None) -> str:
    """Persian/Arabic digits -> Latin. One helper for every numeric input."""
    return (text or "").translate(_FA_DIGITS)


def to_fa_digits(text: any) -> str:
    """Latin digits -> Persian digits for UI formatting."""
    return str(text if text is not None else "").translate(_EN_TO_FA)

T: dict[str, dict[str, str]] = {
    "welcome": {
        "fa": (
            "👋 سلام علیکم {name}!\n\n"
            "🎬 ویدیویی که می‌خوای فشرده بشه رو بفرست (تا {max_gb} گیگابایت).\n"
            "♻️ اگر همین ویدیو قبلاً فشرده شده باشه، نسخهٔ موجود رو بهت پیشنهاد می‌دم تا فوراً تحویل بگیری."
        ),
        "en": (
            "👋 Hi {name}!\n\n"
            "🎬 Send the video you want compressed (up to {max_gb} GB).\n"
            "♻️ If this exact video was compressed before, I'll offer you the existing result for instant delivery."
        ),
    },
    "btn_compress": {"fa": "🎬 فشرده‌سازی", "en": "🎬 Compress"},
    "btn_level": {"fa": "🎚 درجه فشرده‌سازی — ۱ تا ۲۰", "en": "🎚 Compression level — 1 to 20"},
    "already_comp_short": {
        "fa": "فشرده‌سازی دوباره احتمالاً کاهش حجم قابل‌توجهی ایجاد نمی‌کند.",
        "en": "Re-compressing is unlikely to shrink this file significantly.",
    },
    "btn_edu_compress": {
        "fa": "🎓 فشرده‌سازی ویدیوی آموزشی (حداقل حجم + ۴۸۰p/۳۶۰p)",
        "en": "🎓 Educational Video Compression (Lowest size + 480p/360p)",
    },
    "btn_edu_compress_cut": {
        "fa": "🎓 فشرده‌سازی آموزشی ({cut}٪ کاهش حجم! | {res})",
        "en": "🎓 Educational Compress (~{cut}% cut! | {res})",
    },
    "btn_edu480": {
        "fa": "🟢 سبک — حجم کمتر، کیفیت مناسب (~{cut}٪ | ~{mb}MB)",
        "en": "🟢 Light — smaller size, good quality (~{cut}% | ~{mb}MB)",
    },
    "btn_edu360": {
        "fa": "🟡 متعادل — کیفیت بالاتر (~{cut}٪ | ~{mb}MB)",
        "en": "🟡 Balanced — higher quality (~{cut}% | ~{mb}MB)",
    },
    "btn_custom_target": {
        "fa": "🎯 حجم دلخواه — تعیین حجم نهایی",
        "en": "🎯 Custom target — set the final size",
    },
    "btn_rostam": {
        "fa": "⚔️ فشرده‌سازی افراطی «رستم و سیاوش»",
        "en": "⚔️ Rostam & Siavash Extreme Compression",
    },
    "btn_send_original": {
        "fa": "📥 ارسال نسخه اصلی (بدون افت کیفیت)",
        "en": "📥 Send Original (Direct Stream)",
    },
    "already_compressed_warning": {
        "fa": (
            "⚠️ **این ویدیو از قبل فشرده شده است!**\n\n"
            "تحلیل بیت‌ریت و محتوا نشان می‌دهد این فایل قبلاً تا حد زیادی فشرده شده است ({reason}). "
            "فشرده‌سازی عادی ممکن است حجم آن را کاهش ندهد یا کیفیت متن‌ها را بیهوده تخریب کند.\n\n"
            "می‌توانید نسخه اصلی را مستقیماً دریافت کنید یا وارد حالت فوق‌متراکم **«رستم و سیاوش»** شوید:"
        ),
        "en": (
            "⚠️ **This video is already heavily compressed!**\n\n"
            "Bitrate analysis shows this file is already near its entropy floor ({reason}). "
            "Normal compression may not reduce size or may degrade text clarity unnecessarily.\n\n"
            "You can keep the original or run **'Rostam & Siavash'** extreme compression:"
        ),
    },
    "custom_target_prompt": {
        "fa": (
            "🎯 **تعیین حجم دستی (حالت سرعت موشکی):**\n\n"
            "یکی از حجم‌های آماده را انتخاب کنید یا یک عدد به مگابایت بفرستید (مثلاً 150):\n\n"
            "⚡ *اولویت سرعت:* در این حالت برای رسیدن فوری به حجم دلخواه، کیفیت و رزولوشن هوشمندانه بهینه‌سازی شده و پردازش با حداکثر سرعت سرور انجام می‌شود."
        ),
        "en": (
            "🎯 **Manual Target Size (Rocket Speed Mode):**\n\n"
            "Select a quick size below or send a number in MB (e.g. 150):\n\n"
            "⚡ *Speed Priority:* Resolution and encoding are adapted to hit your target size at maximum server speed."
        ),
    },
    "rostam_accepted": {
        "fa": "⚔️ حالت «رستم و سیاوش» فعال شد — ویدیو با رزولوشن ۳۶۰p، فیلتر شارپ متن، نویزگیر زمانی و HEVC فوق‌متراکم فشرده می‌شود.",
        "en": "⚔️ 'Rostam & Siavash' active — video will be compressed with 360p, text unsharp, denoise and dense HEVC.",
    },
    "edu_accepted": {
        "fa": "🎓 حالت آموزشی فعال شد ({res}) — کار با حداکثر سرعت و حداقل حجم ثبت شد.",
        "en": "🎓 Educational mode active ({res}) — job queued with maximum speed and lowest size.",
    },
    "btn_cancel_job": {"fa": "❌ لغو", "en": "❌ Cancel"},
    "level_prompt": {
        "fa": (
            "🔢 یک عدد بین ۱ تا ۲۰ بفرست (درجهٔ فشرده‌سازی).\n"
            "عدد بزرگ‌تر = حجم کمتر و کمی افت کیفیت؛ ربات طوری تنظیم می‌کند که ویدیو واضح و قابل تماشا بماند. "
            "میزان کاهش حجم به محتوای ویدیو بستگی دارد."
        ),
        "en": (
            "🔢 Send a number between 1 and 20 (compression level).\n"
            "Higher = smaller file with slightly lower quality; the bot keeps the video "
            "watchable. The achieved size reduction depends on the content."
        ),
    },
    "level_invalid": {
        "fa": "❌ فقط یک عدد بین ۱ تا ۲۰ بفرست (مثلاً 15).",
        "en": "❌ Send a number between 1 and 20 (e.g. 15).",
    },
    "level_accepted": {
        "fa": "🎚 درجهٔ فشرده‌سازی: {level} — کار ثبت شد.",
        "en": "🎚 Compression level: {level} — job queued.",
    },
    "queue_position": {"fa": "موقعیت شما در صف: {n}", "en": "Your queue position: {n}"},
    "copy_progress": {
        "fa": "📋 آماده‌سازی فایل: {pct}٪ — {speed}MB/s",
        "en": "📋 Preparing file: {pct}% — {speed}MB/s",
    },
    "level_escalated": {
        "fa": "🔁 این ویدیو از قبل به‌خوبی فشرده شده بود؛ برای نتیجهٔ واقعی، مرحلهٔ قوی‌تر (HEVC) شروع شد — کیفیت محافظت می‌شود ولی زمان بیشتری می‌برد.",
        "en": "🔁 This video was already well compressed; the stronger HEVC pass has started — quality is protected but it takes longer.",
    },
    "cancel_expired": {
        "fa": "این پیام قدیمی است؛ ویدیو را دوباره بفرست.",
        "en": "This message is stale; please resend the video.",
    },
    "job_gone": {"fa": "این کار دیگر موجود نیست.", "en": "This job no longer exists."},
    "choose_profile_for": {"fa": "پروفایل را برای این فایل انتخاب کنید:", "en": "Pick a profile for this file:"},
    "menu_stats": {"fa": "آمار من", "en": "My stats"},
    "nothing_to_cancel": {"fa": "کار فعالی برای لغو نیست.", "en": "Nothing to cancel."},
    "cancelling": {"fa": "⏳ در حال لغو…", "en": "⏳ Cancelling…"},
    "cancelled": {"fa": "🚫 کار {job} لغو شد.", "en": "🚫 Job {job} cancelled."},
    "stage_copying": {"fa": "آماده‌سازی", "en": "Preparing"},
    "stage_queued": {"fa": "انتظار در صف", "en": "Queued"},
    "stage_encoding": {"fa": "فشرده‌سازی", "en": "Compressing"},
    "stage_validating_out": {"fa": "بررسی کیفیت خروجی", "en": "Validating output"},
    "stage_archiving": {"fa": "ذخیره‌سازی", "en": "Archiving"},
    "stage_delivering": {"fa": "ارسال فایل", "en": "Delivering"},
    "status_header": {
        "fa": "🧾 کار {job} | پروفایل: {profile}",
        "en": "🧾 Job {job} | Profile: {profile}",
    },
    "status_line": {
        "fa": "{stage} | {progress}٪ | {elapsed} گذشته {eta}",
        "en": "{stage} | {progress}% | {elapsed} elapsed {eta}",
    },
    "status_speed": {"fa": " | سرعت {speed}x", "en": " | speed {speed}x"},
    "eta_prefix": {"fa": "| حدود {eta} مانده", "en": "| ~{eta} left"},
    "status_done": {"fa": "✅ انجام شد! نتیجه در پیام بعدی.", "en": "✅ Done! Result in the next message."},
    "status_done_nogain": {
        "fa": "ℹ️ فشرده‌سازی صرفهٔ حجمی نداشت؛ نسخهٔ اصلی تحویل داده شد.",
        "en": "ℹ️ Compression had no size benefit; the original was delivered.",
    },
    "status_done_blocked": {
        "fa": "⚠️ فشرده‌سازی انجام شد ولی حجم خروجی از سقف تلگرام ({limit}) بیشتر است. مدیر مطلع شد.",
        "en": "⚠️ Done, but the output exceeds the Telegram limit ({limit}). An admin was notified.",
    },
    "status_failed": {"fa": "❌ پردازش ناموفق بود.", "en": "❌ Processing failed."},
    "status_retrying": {"fa": "↩️ خطای موقت؛ تلاش مجدد ({attempt})…", "en": "↩️ Temporary error; retrying ({attempt})…"},
    "status_cancelled": {"fa": "🚫 لغو شد.", "en": "🚫 Cancelled."},
    "status_joined": {
        "fa": "🔗 این فایل در حال پردازش است؛ نتیجهٔ همان کار به شما هم تحویل داده می‌شود.",
        "en": "🔗 This file is already being processed; you will receive the same result.",
    },
    "status_reused": {
        "fa": "♻️ نتیجهٔ آماده برای همین فایل پیدا شد (بدون پردازش مجدد).",
        "en": "♻️ An existing result for this file was found (no re-encode).",
    },
    "status_delivery_failed": {
        "fa": "پردازش کامل شد ولی ارسال ناموفق بود.",
        "en": "Processing finished but delivery failed.",
    },
    "btn_retry": {"fa": "🔄 تلاش مجدد", "en": "🔄 Retry"},
    "btn_error_details": {"fa": "ℹ️ جزئیات خطا", "en": "ℹ️ Error details"},
    "btn_redeliver": {"fa": "📥 دریافت مجدد", "en": "📥 Re-deliver"},
    "btn_custom_size": {"fa": "🎯 حجم دلخواه", "en": "🎯 Target size"},
    "err_details_none": {"fa": "جزئیات بیشتری ثبت نشده.", "en": "No further details recorded."},
    "retry_started": {"fa": "↩️ کار {job} دوباره در صف قرار گرفت.", "en": "↩️ Job {job} re-queued."},
    "retry_not_allowed": {
        "fa": "این کار قابل تلاش مجدد نیست.",
        "en": "This job cannot be retried.",
    },
    "submit_error": {
        "fa": "❌ خطای غیرمنتظره در ثبت درخواست پیش آمد. چند لحظه بعد دوباره تلاش کنید — اگر تکرار شد به ادمین گزارش دهید.",
        "en": "❌ An unexpected error occurred while submitting. Please try again shortly.",
    },
    "summary_header": {"fa": "✅ پردازش ویدیو با موفقیت انجام شد.", "en": "✅ Video processed successfully."},
    "summary_file": {"fa": "📁 فایل: {name}", "en": "📁 File: {name}"},
    "summary_size": {"fa": "💾 {src} → {out}", "en": "💾 {src} → {out}"},
    "summary_saved": {"fa": "📉 صرفه‌جویی: {saved} ({pct}٪)", "en": "📉 Saved: {saved} ({pct}%)"},
    "summary_saved_neg": {
        "fa": "📉 تغییر حجم: {delta} (افزایشی — سیاست no-gain اعمال شد)",
        "en": "📉 Size change: {delta} (increase — no-gain policy applied)",
    },
    "summary_duration": {"fa": "⏱ مدت ویدیو: {dur}", "en": "⏱ Duration: {dur}"},
    "summary_duration_unknown": {"fa": "⏱ مدت ویدیو: نامشخص", "en": "⏱ Duration: unknown"},
    "summary_res": {"fa": "📐 رزولوشن: {res}", "en": "📐 Resolution: {res}"},
    "summary_codec": {"fa": "🎞 کدک: {vc} / {ac}", "en": "🎞 Codec: {vc} / {ac}"},
    "summary_time": {"fa": "⌛ زمان پردازش: {mins}", "en": "⌛ Processing time: {mins}"},
    "summary_profile": {"fa": "⚙️ پروفایل: {profile}", "en": "⚙️ Profile: {profile}"},
    "summary_job": {"fa": "🆔 کد: {job}", "en": "🆔 ID: {job}"},
    "summary_source": {
        "fa": "{kind}",
        "en": "{kind}",
    },
    "summary_kind_new": {"fa": "🆕 فشرده‌سازی جدید", "en": "🆕 Newly encoded"},
    "summary_kind_reused": {"fa": "♻️ استفاده از نتیجهٔ موجود", "en": "♻️ Reused existing result"},
    "reject": {
        "fa": {
            "bad_profile": "پروفایل نامعتبر است.",
            "source_missing": "فایل منبع در دسترس نیست.",
            "download_failed": "دانلود فایل ممکن نشد؛ دوباره تلاش کنید.",
            "invalid_media": "فایل ویدیویی معتبر تشخیص داده نشد ({detail}).",
            "too_large": "حجم فایل بیشتر از حد مجاز ({max_gb}GB) است.",
            "disk": "فضای سرور کم است؛ بعداً تلاش کنید.",
            "user_busy": "شما {max_active} کار فعال دارید؛ صبر کنید.",
            "rate_limited": "محدودیت ارسال ساعتی؛ کمی بعد تلاش کنید.",
            "queue_full": "صف پردازش پر است؛ کمی بعد تلاش کنید.",
            "paused": "سرویس موقتاً متوقف است.",
            "blocked_user": "دسترسی شما مسدود است.",
            "archive_not_configured": "سرویس در حال راه‌اندازی است؛ کانال آرشیو هنوز تنظیم نشده.",
            "source_unavailable": "فایل منبع دیگر در دسترس نیست؛ دوباره ارسال کنید.",
            "daily_quota": "به سقف روزانه رسیدید ({quota} کار در ۲۴ ساعت).",
            "bad_target": "حجم هدف نامعتبر است ({detail}).",
            "too_long": "مدت ویدیو بیشتر از حد مجاز ({max_h}) است.",
            "daily_quota_bytes": "سهمیهٔ ۲۴ ساعتهٔ شما پر شد ({used} از {quota}).",
            "too_large_tier": "حجم فایل بیشتر از حد مجاز شما ({max_gb}GB) است.",
        },
        "en": {
            "bad_profile": "Invalid profile.",
            "source_missing": "Source file unavailable.",
            "download_failed": "Could not read the file; please try again.",
            "invalid_media": "Not a valid video file ({detail}).",
            "too_large": "File exceeds the {max_gb}GB limit.",
            "disk": "Server storage is low; try later.",
            "user_busy": "You already have {max_active} active jobs; please wait.",
            "rate_limited": "Hourly limit reached; try again later.",
            "queue_full": "Queue is full; try again later.",
            "paused": "Service is paused.",
            "blocked_user": "Your access is blocked.",
            "archive_not_configured": "Service is being set up; archive channel not configured yet.",
            "source_unavailable": "Source is gone; please resend.",
            "daily_quota": "Daily quota reached ({quota} jobs / 24h).",
            "bad_target": "Invalid target size ({detail}).",
            "too_long": "Video is longer than your allowed maximum ({max_h}).",
            "daily_quota_bytes": "Your 24h quota is used up ({used} of {quota}).",
            "too_large_tier": "File exceeds your size limit ({max_gb}GB).",
        },
    },
    "nogain_notice": {
        "fa": "ℹ️ خروجی مزیت حجمی نداشت ({out} در برابر {src})؛ نسخهٔ اصلی ارسال شد.",
        "en": "ℹ️ The output had no size benefit ({out} vs {src}); the original was delivered.",
    },
    "archive_setup_admin": {
        "fa": "🔧 کانال آرشیو تنظیم نشده.\n۱) /setarchive -100XXXXXXXXXX\n۲) پیام کانال را فوروارد کنید\n۳) پستی در کانال بگذارید.",
        "en": "🔧 Archive channel not set.\n1) /setarchive -100XXXXXXXXXX\n2) Forward a channel message\n3) Post anything in the channel.",
    },
    "archive_configured": {
        "fa": "✅ کانال آرشیو تنظیم شد: {channel} ({title})",
        "en": "✅ Archive channel set: {channel} ({title})",
    },
    "archive_verify_failed": {
        "fa": "❌ بات نتوانست در این چت پیام بگذارد ({error}). بات باید ادمین با حق ارسال باشد.",
        "en": "❌ Bot could not post in this chat ({error}). The bot must be an admin with post rights.",
    },
    "archive_missing": {
        "fa": "⚠️ رکورد آرشیو {archive} دیگر در دسترس نیست.",
        "en": "⚠️ Archive record {archive} is no longer available.",
    },
    "archive_proposal": {
        "fa": "📌 کانال «{channel}» به‌عنوان کانال آرشیو شناسایی شد.\nبا تأیید، همهٔ خروجی‌ها در آن ذخیره می‌شوند.",
        "en": "📌 Channel \"{channel}\" was detected as a candidate archive channel.\nOnce confirmed, all results are stored there.",
    },
    "btn_confirm_archive": {"fa": "✅ تأیید آرشیو", "en": "✅ Confirm archive"},
    "archive_fwd_detected": {
        "fa": "این پیام از کانال «{channel}» فوروارد شده است.",
        "en": "This message was forwarded from the channel \"{channel}\".",
    },
    "archive_blocked_admin": {
        "fa": "🚫 آرشیو مسدود شد: کار {job} — {out}. فایل تا {hours} ساعت روی سرور می‌ماند.",
        "en": "🚫 Archive blocked: job {job} — {out}. The file stays on the server for {hours}h.",
    },
    "admin_denied": {"fa": "این دستور فقط برای مدیران است.", "en": "Admins only."},
    "admin_panel_title": {"fa": "🛠 پنل مدیریت:", "en": "🛠 Admin panel:"},
    "admin_paused": {"fa": "⏸ پذیرش کار متوقف شد.", "en": "⏸ Intake paused."},
    "admin_resumed": {"fa": "▶️ سرویس فعال شد.", "en": "▶️ Service resumed."},
    "admin_retry_ok": {"fa": "↩️ کار {job} دوباره در صف قرار گرفت.", "en": "↩️ Job {job} re-queued."},
    "admin_ban_prompt": {
        "fa": "شناسهٔ عددی کاربر را بفرستید تا بن شود (مثلاً 123456789). برای رفع بن: unban 123456789",
        "en": "Send the numeric user ID to ban (e.g. 123456789). To unban: unban 123456789",
    },
    "admin_banned": {"fa": "🚫 کاربر {uid} بن شد.", "en": "🚫 User {uid} banned."},
    "admin_unbanned": {"fa": "✅ بن کاربر {uid} برداشته شد.", "en": "✅ User {uid} unbanned."},
    "admin_ban_usage": {
        "fa": "استفاده: شناسهٔ عددی برای بن؛ برای رفع بن: unban <شناسه>",
        "en": "Usage: numeric ID to ban; to unban: unban <id>",
    },
    "admin_broadcast_prompt": {
        "fa": "متن اطلاع‌رسانی را بفرستید (برای همهٔ کاربران ارسال می‌شود):",
        "en": "Send the announcement text (it will go to all users):",
    },
    "admin_broadcast_done": {
        "fa": "📢 ارسال شد به {ok} کاربر؛ {fail} ناموفق.",
        "en": "📢 Delivered to {ok} users; {fail} failed.",
    },
    "bcast_started": {
        "fa": "📢 ارسال در پس‌زمینه شروع شد؛ با دکمهٔ ⏹ قابل توقف است.",
        "en": "📢 Broadcast started in the background; stop it with ⏹.",
    },
    "bcast_progress": {
        "fa": "📢 پیشرفت اطلاع‌رسانی: {done}/{total} — موفق {ok} | ناموفق {fail}",
        "en": "📢 Broadcast progress: {done}/{total} — ok {ok} | failed {fail}",
    },
    "bcast_done": {
        "fa": "📢 اطلاع‌رسانی تمام شد: {ok} موفق | {fail} ناموفق | {skipped} رد شده",
        "en": "📢 Broadcast finished: {ok} delivered | {fail} failed | {skipped} skipped",
    },
    "bcast_stop_btn": {"fa": "⏹ توقف", "en": "⏹ Stop"},
    "bcast_already_running": {
        "fa": "📢 یک اطلاع‌رسانی دیگر در حال اجراست؛ اول همان را تمام یا متوقف کنید.",
        "en": "📢 Another broadcast is already running; finish or stop it first.",
    },
    "admin_thumb_btn": {"fa": "تامبنیل گلوبال", "en": "Global thumbnail"},
    "admin_thumb_prompt": {
        "fa": "🖼 یک عکس بفرست تا روی همهٔ ویدیوهای تحویلی گذاشته شود (یا «حذف» برای پاک کردن).",
        "en": "🖼 Send a photo to use as the thumbnail for all delivered videos (or 'حذف' to clear).",
    },
    "admin_thumb_saved": {"fa": "✅ تامبنیل گلوبال ذخیره شد.", "en": "✅ Global thumbnail saved."},
    "admin_thumb_cleared": {"fa": "🗑 تامبنیل گلوبال حذف شد.", "en": "🗑 Global thumbnail cleared."},
    "admin_user_btn": {"fa": "کاربر", "en": "User"},
    "admin_limits_btn": {"fa": "محدودیت‌ها", "en": "Limits"},
    "admin_user_prompt": {
        "fa": "👤 شناسهٔ عددی کاربر را بفرست (کاربر باید حداقل یک‌بار به ربات پیام داده باشد):",
        "en": "👤 Send the numeric user ID:",
    },
    "admin_user_notfound": {"fa": "کاربر پیدا نشد.", "en": "User not found."},
    "admin_users_title": {"fa": "👥 کاربران اخیر:", "en": "👥 Recent users:"},
    "admin_users_empty": {"fa": "هنوز کاربری ثبت نشده.", "en": "No users yet."},
    "tier_panel_title": {
        "fa": "🎚 محدودیت‌های طبقهٔ {tier}\nبا دکمه‌ها تنظیم کن — هر تغییر فوراً ذخیره می‌شود.",
        "en": "🎚 {tier} tier limits\nTap the buttons - every change saves instantly.",
    },
    "admin_limits_pick": {
        "fa": "🎚 محدودیت‌ها — طبقه را انتخاب کن:",
        "en": "🎚 Limits — pick a tier:",
    },
    "ulim_title": {
        "fa": "🎚 سقف اختصاصی کاربر {uid}\n«پیش‌فرض» یعنی تنظیم طبقهٔ او اعمال شود؛ تغییرها فوراً ذخیره می‌شوند.",
        "en": "🎚 Custom limits for user {uid}\n\"پیش‌فرض\" means the tier value applies; changes save instantly.",
    },
    "msg_prompt": {
        "fa": "✉️ متن پیام برای کاربر {uid} را بنویس (هر چه بنویسی مستقیم برایش ارسال می‌شود):",
        "en": "✉️ Write the message for user {uid} (it will be sent as-is):",
    },
    "msg_sent": {"fa": "✅ پیام به کاربر {uid} ارسال شد.", "en": "✅ Message sent to user {uid}."},
    "msg_fail": {
        "fa": "❌ ارسال به کاربر {uid} ناموفق بود (شاید بات را بلاک کرده).",
        "en": "❌ Could not message user {uid} (maybe they blocked the bot).",
    },
    "bcast_preview": {
        "fa": "📢 پیش‌نمایش اطلاع‌رسانی — گیرندگان: {n} کاربر. ارسال شود؟",
        "en": "📢 Broadcast preview — recipients: {n} users. Send it?",
    },
    "btn_send": {"fa": "✅ ارسال", "en": "✅ Send"},
    "btn_cancel": {"fa": "❌ انصراف", "en": "❌ Cancel"},
    "btn_back": {"fa": "↩️ بازگشت", "en": "↩️ Back"},
    "btn_default": {"fa": "♻️ پیش‌فرض", "en": "♻️ Defaults"},
    "admin_thumb_delete_btn": {"fa": "🗑 حذف تامبنیل", "en": "🗑 Delete thumbnail"},
    "pending_cancelled": {"fa": "لغو شد.", "en": "Cancelled."},
    "pending_saved": {"fa": "✅ ذخیره شد", "en": "✅ Saved"},
    "admin_monitor_btn": {"fa": "مانیتور زنده", "en": "Live monitor"},
    "admin_monitor_title": {"fa": "کارهای فعال:", "en": "Active jobs:"},
    "admin_monitor_stop": {"fa": "توقف", "en": "Stop"},
    "admin_monitor_stopped": {"fa": "مانیتور متوقف شد.", "en": "Monitor stopped."},
    "admin_monitor_idle": {"fa": "صف خالی است — مانیتور متوقف شد.", "en": "Queue is empty - monitor stopped."},
    "fsub_required": {
        "fa": "🔒 برای استفاده از ربات، اول در کانال عضو شو:",
        "en": "🔒 Join the channel first to use the bot:",
    },
    "fsub_btn_join": {"fa": "📢 عضویت در کانال", "en": "📢 Join the channel"},
    "fsub_btn_check": {"fa": "✅ بررسی عضویت", "en": "✅ Check membership"},
    "fsub_ok": {"fa": "✅ عضویت تأیید شد؛ ویدیو بفرست.", "en": "✅ Membership confirmed; send a video."},
    "fsub_still_not": {"fa": "❌ هنوز عضو کانال نشدی.", "en": "❌ You have not joined the channel yet."},
    "admin_fsub_btn": {"fa": "عضویت اجباری", "en": "Force-sub"},
    "admin_fsub_prompt": {
        "fa": ("🔒 شناسه یا آدرس کانال را بفرست:\n"
               "@mychannel یا -100XXXXXXXXXX یا https://t.me/...\n"
               "برای کانال خصوصی لینک دعوت هم بده: «-100... | https://t.me/+invite»\n"
               "غیرفعال‌سازی: off — (بات باید ادمینِ کانال باشد)"),
        "en": ("🔒 Send the channel id or address:\n"
               "@mychannel or -100XXXXXXXXXX or a t.me link\n"
               "Private channel: include an invite link: \"-100... | https://t.me/+invite\"\n"
               "Disable: off - (the bot must be a channel admin)"),
    },
    "admin_fsub_off": {"fa": "🔓 عضویت اجباری غیرفعال شد.", "en": "🔓 Force-sub disabled."},
    "admin_fsub_saved": {
        "fa": "✅ عضویت اجباری فعال شد روی {channel} (لینک: {link})",
        "en": "✅ Force-sub enabled for {channel} (link: {link})",
    },
    "admin_fsub_verify_failed": {
        "fa": "❌ تأیید نشد: {error}",
        "en": "❌ Verification failed: {error}",
    },
    "admin_recent_errors": {"fa": "❌ خطاهای اخیر:", "en": "❌ Recent errors:"},
    "admin_queue_view": {
        "fa": "📋 صف: {queued} در انتظار | {active} فعال | صف Encore: {encre}",
        "en": "📋 Queue: {queued} waiting | {active} active | Encore queue: {encre}",
    },
    "settings_thumb_failed": {
        "fa": "❌ ذخیرهٔ تصویر شاخص ناموفق بود ({error}).",
        "en": "❌ Could not save the thumbnail ({error}).",
    },
    "on": {"fa": "روشن", "en": "on"},
    "off": {"fa": "خاموش", "en": "off"},
    "custom_size_prompt": {
        "fa": "حجم هدف را به MB بفرستید (مثلاً 350). خروجی «حدود» این حجم خواهد بود.",
        "en": "Send the target size in MB (e.g. 350). The output will approximate it.",
    },
    "info_card": {
        "fa": (
            "🎬 {name}\n"
            "━━━━━━━━━━━━━━━\n"
            "📦 حجم: {size}{limit_note}\n"
            "⏱ مدت: {dur}\n"
            "📐 کیفیت تصویر: {res}\n\n"
            "یکی از گزینه‌های زیر را انتخاب کن 👇"
        ),
        "en": (
            "🎬 {name}\n"
            "━━━━━━━━━━━━━━━\n"
            "📦 Size: {size}{limit_note}\n"
            "⏱ Duration: {dur}\n"
            "📐 Resolution: {res}\n\n"
            "Pick one of the options below 👇"
        ),
    },
    "info_details": {
        "fa": "🧵 نوع: {kind}\n🎞 کدک: {codec}",
        "en": "🧵 Kind: {kind}\n🎞 Codec: {codec}",
    },
    "info_unavailable": {"fa": "نامشخص", "en": "unknown"},
    "info_kind_video": {"fa": "ویدیوی تلگرام", "en": "Telegram video"},
    "info_kind_doc": {"fa": "فایل ویدیویی", "en": "video document"},
    "status_queued_hint": {
        "fa": "⏳ کار در صف قرار گرفت — پیشرفت به‌صورت خودکار اینجا به‌روز می‌شود.",
        "en": "⏳ Job queued — progress updates will appear here.",
    },
    "cache_offer_title": {
        "fa": "♻️ نسخهٔ فشرده‌شدهٔ این ویدیو از قبل موجود است!",
        "en": "♻️ An already-compressed version of this video exists!",
    },
    "cache_offer_question": {
        "fa": "آیا همین نسخهٔ موجود را دریافت می‌کنید؟",
        "en": "Would you like to receive this existing version?",
    },
    "cache_quality": {"fa": "📐 کیفیت: {res}", "en": "📐 Resolution: {res}"},
    "cache_duration": {"fa": "⏱ مدت: {dur}", "en": "⏱ Duration: {dur}"},
    "cache_size": {"fa": "📦 حجم: {size}", "en": "📦 File size: {size}"},
    "cache_vcodec": {"fa": "🎞 کدک تصویر: {codec}", "en": "🎞 Video codec: {codec}"},
    "cache_acodec": {"fa": "🔊 صدا: {codec}", "en": "🔊 Audio: {codec}"},
    "cache_profile": {"fa": "🎚 پروفایل فشرده‌سازی: {profile}", "en": "🎚 Compression profile: {profile}"},
    "cache_versions_more": {
        "fa": "➕ {n} نسخهٔ فشرده‌شدهٔ دیگر هم برای این ویدیو موجود است.",
        "en": "➕ {n} more compressed version(s) exist for this video.",
    },
    "btn_use_cached": {
        "fa": "📩 ارسال نسخهٔ موجود",
        "en": "📩 Send existing version",
    },
    "btn_other_profile": {
        "fa": "🎛 انتخاب پروفایل دیگر",
        "en": "🎛 Choose another profile",
    },
    "restricted_grid_note": {
        "fa": "فقط پروفایل‌هایی که نسخه‌ای کم‌حجم‌تر و پایین‌تر از نسخهٔ موجود می‌سازند نمایش داده می‌شوند — هرگز از روی نسخهٔ فشرده بالا کشیده نمی‌شود و کیفیت ساختگی وعده داده نمی‌شود.",
        "en": "Only profiles producing a strictly lower-quality result than the existing version are shown — never upscaling a compressed copy, never promising quality it cannot deliver.",
    },
    "cache_none_available": {
        "fa": "⚠️ برای این ویدیو هیچ پروفایل پایین‌تری قابل ارائه نیست.",
        "en": "⚠️ No lower-quality profile can be offered for this video.",
    },
    "cache_unavailable": {
        "fa": "❌ متأسفانه نسخهٔ ذخیره‌شده دیگر در دسترس نیست (از کانال آرشیو حذف شده). می‌توانید فشرده‌سازی تازه را شروع کنید:",
        "en": "❌ The stored version is no longer available (removed from the archive channel). You can start a fresh compression:",
    },
    "cache_gone": {
        "fa": "⌛ این پیشنهاد قدیمی شده است؛ لطفاً ویدیو را دوباره بفرستید یا پروفایل دیگری انتخاب کنید.",
        "en": "⌛ This offer has expired; please resend the video or pick another profile.",
    },
    "cache_delivering": {
        "fa": "📩 در حال ارسال نسخهٔ موجود…",
        "en": "📩 Sending the existing version…",
    },
    "restricted_grid_title": {
        "fa": "🎛 پروفایل‌های مجاز برای این ویدیو:",
        "en": "🎛 Available profiles for this video:",
    },
    # ---- multi-admin: permissions / personal settings / merge ----
    "perm_denied": {
        "fa": "⛔️ این قابلیت برای حساب شما فعال نیست ({perm}).",
        "en": "⛔️ This capability is not enabled for your account ({perm}).",
    },
    "owner_title": {
        "fa": "👑 پنل Owner — مدیریت ادمین‌ها ({n}):",
        "en": "👑 Owner panel — administrator management ({n}):",
    },
    "own_title": {
        "fa": "👑 پنل مدیریت Owner",
        "en": "👑 Owner Management Panel",
    },
    "own_stats": {
        "fa": ("👥 کاربران: {users} | ⚙️ ادمین: {admins} | ⭐ VIP: {vips}\n"
               "🚫 مسدود: {blocked} | 🎞 کار ۲۴س: {jobs24} | 📋 صف فعال: {queued}"),
        "en": ("👥 Users: {users} | ⚙️ Admins: {admins} | ⭐ VIP: {vips}\n"
               "🚫 Blocked: {blocked} | 🎞 Jobs 24h: {jobs24} | 📋 Active queue: {queued}"),
    },
    "own_hint": {
        "fa": "یک بخش را انتخاب کنید؛ همهٔ تغییرها فوری و ثبت‌شده در گزارش هستند.",
        "en": "Pick a section; every change is instant and audit-logged.",
    },
    "own_btn_admins": {"fa": "👥 ادمین‌ها ({n})", "en": "👥 Administrators ({n})"},
    "own_btn_vip": {"fa": "⭐ کاربران VIP ({n})", "en": "⭐ VIP users ({n})"},
    "own_btn_addadmin": {"fa": "➕ افزودن ادمین", "en": "➕ Add administrator"},
    "own_btn_addvip": {"fa": "➕ افزودن VIP", "en": "➕ Add VIP"},
    "own_btn_audit": {"fa": "🧾 رویدادهای اخیر", "en": "🧾 Recent events"},
    "own_btn_refresh": {"fa": "🔄 بروزرسانی", "en": "🔄 Refresh"},
    "own_admins_title": {
        "fa": "👥 ادمین‌ها ({n}) — یکی را برای مدیریت انتخاب کنید:",
        "en": "👥 Administrators ({n}) — pick one to manage:",
    },
    "own_admins_hint": {
        "fa": "👑 = Owner | ⭐ = VIP | 🚫 = مسدود",
        "en": "👑 = Owner | ⭐ = VIP | 🚫 = blocked",
    },
    "own_admin_flags": {
        "fa": "وضعیت: VIP {vip} | مسدودسازی {ban}",
        "en": "Status: VIP {vip} | Blocked {ban}",
    },
    "own_btn_vip_toggle": {"fa": "⭐ {state} VIP", "en": "⭐ {state} VIP"},
    "own_btn_ban_toggle": {"fa": "🚫 {state} مسدودسازی", "en": "🚫 {state} block"},
    "own_btn_demote": {"fa": "🗑 سلب مدیریت ادمین", "en": "🗑 Remove administrator"},
    "own_btn_demote_yes": {"fa": "⚠️ بله، سلب مدیریت کن", "en": "⚠️ Yes, remove admin"},
    "own_demote_confirm": {
        "fa": "مطمئنی مدیریت «{name}» سلب شود؟ دسترسی‌های ویژگی‌ها او باقی می‌ماند ولی دیگر ادمین نخواهد بود.",
        "en": "Remove administrator \"{name}\"? Their feature grants are kept, but they will no longer be an admin.",
    },
    "own_demote_done": {"fa": "✅ مدیریت سلب شد.", "en": "✅ Administrator removed."},
    "own_demote_failed": {"fa": "❌ ناموفق: {why}", "en": "❌ Failed: {why}"},
    "own_add_admin_prompt": {
        "fa": "🔢 آیدی عددی یا @username کاربر را بفرستید تا ادمین شود:",
        "en": "Send the user's numeric ID or @username to promote them:",
    },
    "own_add_vip_prompt": {
        "fa": "🔢 آیدی عددی یا @username کاربر را بفرستید تا VIP شود:",
        "en": "Send the user's numeric ID or @username to make them VIP:",
    },
    "own_user_not_found": {
        "fa": "❌ کاربری برای «{ref}» پیدا نشد (باید حداقل یک‌بار با ربات چت کرده باشد).",
        "en": "❌ No user found for \"{ref}\" (they must have messaged the bot at least once).",
    },
    "own_user_missing": {"fa": "❌ کاربر یافت نشد.", "en": "❌ User not found."},
    "own_promote_failed": {"fa": "❌ افزودن ادمین ناموفق: {why}", "en": "❌ Promotion failed: {why}"},
    "own_admin_added": {"fa": "✅ «{name}» ادمین شد.", "en": "✅ \"{name}\" is now an administrator."},
    "own_vip_added": {"fa": "✅ «{name}» VIP شد.", "en": "✅ \"{name}\" is now VIP."},
    "own_vip_done": {"fa": "وضعیت VIP: {state}", "en": "VIP state: {state}"},
    "own_ban_done": {"fa": "وضعیت مسدودسازی: {state}", "en": "Block state: {state}"},
    "own_vip_title": {
        "fa": "⭐ کاربران VIP ({n}) — انتخاب برای مدیریت:",
        "en": "⭐ VIP users ({n}) — pick one to manage:",
    },
    "own_vip_hint": {
        "fa": "VIP فقط محدودیت‌های بیشتر می‌دهد؛ هرگز ادمین نمی‌کند.",
        "en": "VIP only grants higher limits; it never grants admin powers.",
    },
    "own_audit_title": {"fa": "🧾 رویدادهای مدیریتی اخیر:", "en": "🧾 Recent management events:"},
    "own_audit_empty": {"fa": "— هنوز رویدادی ثبت نشده.", "en": "— nothing recorded yet."},
    "owner_admin_title": {
        "fa": "⚙️ ادمین: {name} ({tg})",
        "en": "⚙️ Administrator: {name} ({tg})",
    },
    "owner_admin_conf": {
        "fa": "تنظیمات شخصی: {conf}",
        "en": "Personal configuration: {conf}",
    },
    "owner_is_target": {
        "fa": "این کاربر Owner است — دسترسی‌هایش همیشه کامل است و قابل تغییر نیست.",
        "en": "This user is the Owner — always full access, not editable.",
    },
    "owner_perm_done": {
        "fa": "انجام شد: {perm} → {state}",
        "en": "Done: {perm} → {state}",
    },
    "thumb_prompt": {
        "fa": "🖼 تامبنیل شخصی شما: {current}\n\nیک عکس بفرستید تا به‌عنوان تامبنیل اختصاصی شما (۳۲۰×۳۲۰) ذخیره شود. تامبنیل شخصی بر تامبنیل سراسری اولویت دارد.",
        "en": "🖼 Your personal thumbnail: {current}\n\nSend a photo to store it as your personal 320×320 thumbnail. Personal overrides the global one.",
    },
    "thumb_set": {"fa": "✅ تنظیم شده", "en": "✅ set"},
    "thumb_none": {"fa": "— تنظیم نشده", "en": "— not set"},
    "thumb_saved": {"fa": "✅ تامبنیل شخصی ذخیره شد.", "en": "✅ Personal thumbnail saved."},
    "thumb_deleted": {"fa": "🗑 تامبنیل شخصی حذف شد.", "en": "🗑 Personal thumbnail removed."},
    "thumb_invalid": {"fa": "❌ عکس قابل پردازش نبود؛ دوباره تلاش کنید.", "en": "❌ Could not process that photo; try again."},
    "btn_thumb_del": {"fa": "🗑 حذف تامبنیل من", "en": "🗑 Remove my thumbnail"},
    "wm_title": {"fa": "💧 تنظیمات واترمارک شخصی:", "en": "💧 Personal watermark settings:"},
    "wm_summary": {
        "fa": ("وضعیت: {state} فعال\nنوع: {typ} | موقعیت: {pos}\n"
               "متن: «{text}» | اندازه فونت: {size}\n"
               "شفافیت: {op}٪ | شفافیت پس‌زمینه: {bop}٪\n"
               "مقیاس تصویر: {scale}٪ | زمان‌بندی: {timing}"),
        "en": ("State: {state} enabled\nType: {typ} | Position: {pos}\n"
               "Text: \"{text}\" | Font size: {size}\n"
               "Opacity: {op}% | Box opacity: {bop}%\n"
               "Image scale: {scale}% | Timing: {timing}"),
    },
    "wm_hint": {
        "fa": "تغییرات فقط روی خروجی‌های خودتان اعمال می‌شود؛ واترمارک بعد از فشرده‌سازی و هنگام ارسال اضافه می‌شود (آرشیو تمیز می‌ماند). حالت remux واترمارک نمی‌گیرد.",
        "en": "Changes apply only to your own outputs; the watermark is added at delivery (archive stays clean). Remux is never watermarked.",
    },
    "wm_type_text": {"fa": "متن", "en": "text"},
    "wm_type_image": {"fa": "تصویر", "en": "image"},
    "wm_timing_always": {"fa": "همیشه", "en": "always"},
    "wm_timing_range": {"fa": "بازه زمانی", "en": "range"},
    "wm_timing_interval": {"fa": "متناوب", "en": "interval"},
    "btn_wm_type": {"fa": "🔤/🖼 نوع", "en": "🔤/🖼 Type"},
    "btn_wm_pos": {"fa": "📍 موقعیت", "en": "📍 Position"},
    "btn_wm_text": {"fa": "✏️ متن", "en": "✏️ Text"},
    "btn_wm_size": {"fa": "🔢 اندازه فونت", "en": "🔢 Font size"},
    "btn_wm_opacity": {"fa": "👓 شفافیت", "en": "👓 Opacity"},
    "btn_wm_border": {"fa": "⬛️ پس‌زمینه متن", "en": "⬛️ Text box"},
    "btn_wm_margins": {"fa": "📐 حاشیه‌ها", "en": "📐 Margins"},
    "btn_wm_timing": {"fa": "⏱ زمان‌بندی", "en": "⏱ Timing"},
    "btn_wm_image": {"fa": "🖼 تصویر واترمارک", "en": "🖼 Watermark image"},
    "btn_wm_font": {"fa": "🔤 فونت", "en": "🔤 Font"},
    "btn_wm_preview": {"fa": "👁 پیش‌نمایش", "en": "👁 Preview"},
    "btn_wm_toggle": {"fa": "🔁 فعال/غیرفعال", "en": "🔁 Enable/disable"},
    "btn_wm_reset": {"fa": "♻️ بازنشانی", "en": "♻️ Reset"},
    "btn_wm_m_top": {"fa": "بالا", "en": "top"},
    "btn_wm_m_bottom": {"fa": "پایین", "en": "bottom"},
    "btn_wm_m_left": {"fa": "چپ", "en": "left"},
    "btn_wm_m_right": {"fa": "راست", "en": "right"},
    "btn_back": {"fa": "↩️ بازگشت", "en": "↩️ Back"},
    "wm_type_now": {"fa": "نوع: {typ}", "en": "Type: {typ}"},
    "wm_send_text": {"fa": "متن واترمارک را بفرستید (حداکثر ۲۰۰ کاراکتر):", "en": "Send the watermark text (max 200 chars):"},
    "wm_send_size": {"fa": "اندازه فونت را بفرستید (۱۰ تا ۱۰۰ پیکسل):", "en": "Send the font size (10..100 px):"},
    "wm_send_opacity": {"fa": "شفافیت را بفرستید (۱۰ تا ۱۰۰ درصد):", "en": "Send opacity (10..100%):"},
    "wm_send_border": {"fa": "شفافیت پس‌زمینه را بفرستید (۰ تا ۱۰۰ درصد):", "en": "Send box opacity (0..100%):"},
    "wm_send_margin": {"fa": "حاشیهٔ {side} را به پیکسل بفرستید (۰ تا ۵۰۰):", "en": "Send the {side} margin in px (0..500):"},
    "wm_send_range": {"fa": "بازه زمانی را بفرستید: «شروع پایان» به ثانیه (مثلاً: 10 60)", "en": "Send the range: \"start end\" in seconds (e.g. 10 60)"},
    "wm_send_interval": {"fa": "بازه متناوب را بفرستید: «نمایش دوره» به ثانیه (مثلاً: 5 30)", "en": "Send the interval: \"show period\" in seconds (e.g. 5 30)"},
    "wm_send_img": {"fa": "تصویر واترمارک (PNG/JPG/WebP حداکثر ۵MB) را بفرستید:", "en": "Send the watermark image (PNG/JPG/WebP, max 5MB):"},
    "wm_send_font": {"fa": "فایل فونت (TTF/OTF حداکثر ۵MB) را بفرستید:", "en": "Send a font file (TTF/OTF, max 5MB):"},
    "wm_saved": {"fa": "✅ ذخیره شد.", "en": "✅ Saved."},
    "wm_saved_msg": {"fa": "✅ تنظیم واترمارک ذخیره شد.", "en": "✅ Watermark setting saved."},
    "wm_reset": {"fa": "♻️ به پیش‌فرض بازگشت.", "en": "♻️ Reset to defaults."},
    "wm_toggled": {"fa": "وضعیت واترمارک: {state}", "en": "Watermark state: {state}"},
    "wm_bad_value": {"fa": "❌ مقدار نامعتبر است.", "en": "❌ Invalid value."},
    "wm_img_saved": {"fa": "✅ تصویر واترمارک ذخیره شد (نوع: تصویر).", "en": "✅ Watermark image saved (type: image)."},
    "wm_font_saved": {"fa": "✅ فونت ذخیره شد.", "en": "✅ Font saved."},
    "wm_upload_failed": {"fa": "❌ آپلود/پردازش فایل ناموفق بود.", "en": "❌ Upload/processing failed."},
    "wm_font_invalid": {"fa": "❌ فقط فایل TTF/OTF تا ۵MB.", "en": "❌ Only TTF/OTF up to 5MB."},
    "wm_preview_rendering": {"fa": "⏳ در حال ساخت پیش‌نمایش…", "en": "⏳ Rendering preview…"},
    "wm_preview_noimg": {"fa": "⚠️ تصویر واترمارک تنظیم نشده.", "en": "⚠️ No watermark image set."},
    "wm_preview_failed": {"fa": "❌ پیش‌نمایش ساخته نشد.", "en": "❌ Preview failed."},
    "cap_prompt": {
        "fa": "📝 کپشن شخصی شما: {current}\nحالت: {mode}\n\nمتن جدید بفرستید (حداکثر ۱۰۰۰ کاراکتر). این کپشن روی ویدیوی خروجیِ خودتان می‌نشیند (تلگرامی، نه داخل ویدیو).",
        "en": "📝 Your personal caption: {current}\nMode: {mode}\n\nSend new text (max 1000 chars). It is applied to your delivered videos (Telegram-side, not burned in).",
    },
    "cap_none": {"fa": "— تنظیم نشده", "en": "— not set"},
    "cap_mode_replace": {"fa": "جایگزینی", "en": "replace"},
    "cap_mode_append": {"fa": "افزودن به انتها", "en": "append"},
    "cap_mode_now": {"fa": "حالت کپشن: {mode}", "en": "Caption mode: {mode}"},
    "cap_saved": {"fa": "✅ کپشن شخصی ذخیره شد.", "en": "✅ Personal caption saved."},
    "cap_deleted": {"fa": "🗑 کپشن شخصی حذف شد.", "en": "🗑 Personal caption removed."},
    "cap_bad": {"fa": "❌ متن نامعتبر.", "en": "❌ Invalid text."},
    "btn_cap_mode": {"fa": "🔁 تغییر حالت (جایگزینی/افزودن)", "en": "🔁 Toggle mode (replace/append)"},
    "btn_cap_del": {"fa": "🗑 حذف کپشن", "en": "🗑 Remove caption"},
    "mrg_started": {
        "fa": "🎬 جلسهٔ {kind} شروع شد.\nویدیوها را به ترتیب بفرستید — ترتیب ارسال دقیقاً حفظ می‌شود.",
        "en": "🎬 {kind} session started.\nSend the videos in order — the exact send order is preserved.",
    },
    "mrg_kind_merge": {"fa": "ادغام", "en": "merge"},
    "mrg_kind_compress": {"fa": "ادغام + فشرده‌سازی", "en": "merge + compress"},
    "mrg_rules": {
        "fa": "حداکثر {maxn} ویدیو. پس از ارسال همه، «اتمام و ادغام» را بزنید.",
        "en": "Up to {maxn} videos. When done, press \"Finish & merge\".",
    },
    "mrg_session": {"fa": "📋 جلسهٔ فعال شما — تعداد ویدیوها: {n}", "en": "📋 Your active session — videos so far: {n}"},
    "mrg_compress_note": {
        "fa": "🎯 حالت: ادغام + فشرده‌سازی (پروفایل: {profile}{target})",
        "en": "🎯 Mode: merge + compress (profile: {profile}{target})",
    },
    "mrg_btn_list": {"fa": "📋 فهرست ویدیوها", "en": "📋 List videos"},
    "mrg_btn_done": {"fa": "✅ اتمام و ادغام", "en": "✅ Finish & merge"},
    "mrg_added": {
        "fa": "➕ ویدیوی #{seq} اضافه شد (مجموع: {n}) — {name}",
        "en": "➕ Video #{seq} added (total: {n}) — {name}",
    },
    "mrg_items_title": {"fa": "📋 ترتیب ادغام ({n} ویدیو):", "en": "📋 Merge order ({n} videos):"},
    "mrg_item_line": {"fa": "#{seq}. {name} ({dur})", "en": "#{seq}. {name} ({dur})"},
    "mrg_need_two": {"fa": "⚠️ حداقل ۲ ویدیو لازم است.", "en": "⚠️ At least 2 videos are required."},
    "mrg_max_items": {"fa": "⚠️ حداکثر {maxn} ویدیو.", "en": "⚠️ Max {maxn} videos."},
    "mrg_no_session": {"fa": "جلسهٔ فعالی ندارید — /merge را بزنید.", "en": "No active session — use /merge."},
    "mrg_already_active": {"fa": "⚠️ جلسهٔ فعال دارید.", "en": "⚠️ You already have an active session."},
    "mrg_already_running": {"fa": "⏳ این جلسه در حال پردازش است.", "en": "⏳ This session is already processing."},
    "mrg_not_cancellable": {"fa": "⚠️ این جلسه دیگر قابل لغو نیست.", "en": "⚠️ This session can no longer be cancelled."},
    "mrg_cancelled": {"fa": "🚫 لغو شد.", "en": "🚫 Cancelled."},
    "mrg_cancelled_msg": {
        "fa": "🚫 جلسهٔ ادغام لغو و فایل‌های موقت پاک شدند.",
        "en": "🚫 Merge session cancelled and staged files cleaned.",
    },
    "mrg_session_closed": {"fa": "⚠️ این جلسه دیگر فعال نیست.", "en": "⚠️ This session is no longer active."},
    "mrg_download_failed": {"fa": "❌ دریافت فایل ناموفق بود.", "en": "❌ Download failed."},
    "mrg_invalid_video": {"fa": "❌ فایل ویدیوی معتبری نیست.", "en": "❌ Not a valid video file."},
    "mrg_stage_failed": {"fa": "❌ ذخیرهٔ فایل ناموفق بود.", "en": "❌ Staging failed."},
    "mrg_started_processing": {
        "fa": "⚙️ ادغام {n} ویدیو شروع شد ({kind})…",
        "en": "⚙️ Merging {n} videos ({kind})…",
    },
    "mrg_done": {"fa": "✅ ویدیوی ادغام‌شده آماده و ارسال شد.", "en": "✅ Merged video is ready and delivered."},
    "mrg_failed": {
        "fa": "❌ ادغام ناموفق بود: {reason}",
        "en": "❌ Merge failed: {reason}",
    },
    "mrg_compress_queued": {
        "fa": "✅ ادغام کامل شد — فشرده‌سازی با پروفایل عادی در صف قرار گرفت.",
        "en": "✅ Merge complete — compression queued through the standard flow.",
    },
    "mrg_compress_deferred": {
        "fa": "✅ ادغام کامل شد — فشرده‌سازی به‌دلیل ظرفیت دیسک موقتاً معلق شد (خودکار ادامه می‌یابد).",
        "en": "✅ Merge complete — compression deferred for disk capacity (auto-resumes).",
    },
    "mrg_compress_joined": {
        "fa": "✅ ادغام کامل شد — به یک فشرده‌سازی در حال اجرا ملحق شدید.",
        "en": "✅ Merge complete — joined an in-flight compression.",
    },
    "mrg_compress_reused": {
        "fa": "✅ نتیجهٔ مشابهی از قبل موجود بود و همان ارسال شد.",
        "en": "✅ An existing result matched and was delivered.",
    },
    "mrg_compress_offer": {
        "fa": "✅ ادغام کامل شد؛ نسخهٔ مشابهی موجود است — پیشنهاد ارسال شد.",
        "en": "✅ Merge complete; a similar version exists — offer sent.",
    },
    # ---- navigation hub (menu:/den: namespaces — NEW) ----
    "nav_title": {"fa": "منوی Oxmit", "en": "Oxmit menu"},
    "nav_vip_badge": {"fa": "⭐ حساب VIP شما فعال است.", "en": "⭐ Your VIP account is active."},
    "nav_hint": {
        "fa": "برای شروع کافی است ویدیو بفرستید — همین‌جا پردازش شروع می‌شود.",
        "en": "Just send a video to start — processing begins right here.",
    },
    "nav_btn_guide": {"fa": "🎬 راهنمای فشرده‌سازی", "en": "🎬 Compression guide"},
    "nav_btn_jobs": {"fa": "📋 کارهای من", "en": "📋 My jobs"},
    "nav_btn_vip": {"fa": "💎 مزایای VIP", "en": "💎 VIP benefits"},
    "nav_btn_branding": {"fa": "🎨 برندینگ من", "en": "🎨 My branding"},
    "nav_btn_merge": {"fa": "🔗 ادغام ویدیوها", "en": "🔗 Merge videos"},
    "nav_btn_mergecompress": {"fa": "🎞 ادغام + فشرده‌سازی", "en": "🎞 Merge + compress"},
    "nav_btn_ops": {"fa": "🛠 پنل عملیات", "en": "🛠 Operations panel"},
    "nav_btn_owner": {"fa": "👑 مدیریت Owner", "en": "👑 Owner management"},
    "nav_btn_settings": {"fa": "⚙️ تنظیمات", "en": "⚙️ Settings"},
    "nav_btn_help": {"fa": "❓ راهنما", "en": "❓ Help"},
    "nav_btn_home": {"fa": "🏠 خانه", "en": "🏠 Home"},
    "nav_btn_menu": {"fa": "🧭 منو", "en": "🧭 Menu"},
    "nav_btn_refresh": {"fa": "🔄 تازه‌سازی", "en": "🔄 Refresh"},
    "nav_guide": {
        "fa": (
            "🎬 راهنمای فشرده‌سازی\n"
            "━━━━━━━━━━━━━━━\n"
            "۱. ویدیو را بفرست (تا سقف حساب شما).\n"
            "۲. یکی از گزینه‌ها را انتخاب کن:\n"
            "   🟢 سبک — حجم کمتر، کیفیت مناسب\n"
            "   🟡 متعادل — کیفیت بالاتر\n"
            "   🎯 حجم دلخواه — خودت حجم نهایی را تعیین می‌کنی\n"
            "   🎚 درجه ۱–۲۰ — عدد بفرست (بالاتر = حجم کمتر)\n"
            "۳. پیشرفت را همان‌جا می‌بینی و فایل نهایی ارسال می‌شود.\n\n"
            "♻️ اگر همان ویدیو قبلاً فشرده شده باشد، نسخهٔ آماده را پیشنهاد می‌دهم."
        ),
        "en": (
            "🎬 Compression guide\n"
            "━━━━━━━━━━━━━━━\n"
            "1. Send your video.\n"
            "2. Pick an option: Light / Balanced / Custom size / Level 1-20.\n"
            "3. Watch live progress and receive the file.\n\n"
            "♻️ If this exact video was compressed before, an existing result is offered."
        ),
    },
    "nav_help": {
        "fa": (
            "❓ راهنمای Oxmit\n"
            "━━━━━━━━━━━━━━━\n"
            "🚀 شروع سریع: فقط ویدیو را بفرست.\n"
            "🎬 گزینه‌ها: سبک / متعادل / حجم دلخواه / درجه ۱–۲۰.\n"
            "♻️ اگر ویدیوی تکراری باشد، نسخهٔ آماده پیشنهاد می‌شود.\n"
            "📊 وضعیت کارها: /myjobs\n"
            "⏸ لغو: دکمهٔ روی کارت پیشرفت. 🔄 تلاش مجدد: روی کارت خطا.\n"
            "⭐ VIP: سقف‌های بالاتر (مدت/حجم روزانه/تعداد) — بدون قابلیت مدیریتی.\n"
            "🧭 همهٔ امکانات: /menu"
        ),
        "en": (
            "❓ Oxmit help\n"
            "━━━━━━━━━━━━━━━\n"
            "🚀 Quick start: just send a video.\n"
            "🎬 Options: Light / Balanced / Custom size / Level 1-20.\n"
            "♻️ Duplicate videos get an existing-result offer.\n"
            "📊 Job status: /myjobs\n"
            "⏸ Cancel: button on the progress card. 🔄 Retry: on the failure card.\n"
            "⭐ VIP: higher limits — no admin powers.\n"
            "🧭 Everything: /menu"
        ),
    },
    "nav_jobs_title": {"fa": "📋 کارهای اخیر شما", "en": "📋 Your recent jobs"},
    "nav_jobs_empty": {"fa": "— هنوز کاری ثبت نکرده‌ای. یک ویدیو بفرست!", "en": "— no jobs yet. Send a video!"},
    "nav_jobs_noname": {"fa": "بدون نام", "en": "unnamed"},
    "nav_st_queued": {"fa": "🟡 در صف", "en": "🟡 queued"},
    "nav_st_deferred": {"fa": "🕓 معلق (ظرفیت)", "en": "🕓 deferred"},
    "nav_st_processing": {"fa": "⚙️ در حال پردازش", "en": "⚙️ processing"},
    "nav_st_completed": {"fa": "🟢 تکمیل شده", "en": "🟢 completed"},
    "nav_st_failed": {"fa": "🔴 ناموفق", "en": "🔴 failed"},
    "nav_st_cancelled": {"fa": "🚫 لغو شده", "en": "🚫 cancelled"},
    "nav_vip_screen": {
        "fa": (
            "💎 مزایای حساب VIP\n"
            "━━━━━━━━━━━━━━━\n"
            "⏱ حداکثر مدت ویدیو: {hours} ساعت\n"
            "📦 سهمیه روزانه: {quota} گیگابایت\n"
            "⚙️ پردازش همزمان: {active} کار\n"
            "📨 درخواست در ساعت: {hourly}\n"
            "🚀 اولویت صف: {prio}\n\n"
            "ℹ️ VIP فقط سقف‌های بیشتر است و هیچ دسترسی مدیریتی اضافه نمی‌کند."
        ),
        "en": (
            "💎 VIP benefits\n"
            "━━━━━━━━━━━━━━━\n"
            "⏱ Max duration: {hours} h\n"
            "📦 Daily quota: {quota} GB\n"
            "⚙️ Concurrent jobs: {active}\n"
            "📨 Requests/hour: {hourly}\n"
            "🚀 Queue priority: {prio}\n\n"
            "ℹ️ VIP means higher limits only — never admin powers."
        ),
    },
    "nav_branding_title": {"fa": "تنظیمات برندینگ شما", "en": "Your branding settings"},
    "nav_branding_thumb": {"fa": "🖼 تامبنیل شخصی: {state}", "en": "🖼 Personal thumbnail: {state}"},
    "nav_branding_wm": {"fa": "💧 واترمارک: {state}", "en": "💧 Watermark: {state}"},
    "nav_branding_cap": {"fa": "📝 کپشن: {state} (حالت: {mode})", "en": "📝 Caption: {state} (mode: {mode})"},
    "nav_branding_info": {
        "fa": (
            "ℹ️ تنظیمات به‌صورت مستقل ذخیره می‌شوند؛ هر پردازش تنظیمات لحظهٔ ثبت خودش را\n"
            "دریافت می‌کند و تغییر امروز، کارهای قبلی را تغییر نمی‌دهد.\n"
            "آرشیو همیشه نسخهٔ تمیز را نگه می‌دارد و واترمارک هنگام ارسال اضافه می‌شود."
        ),
        "en": (
            "ℹ️ Settings are stored independently; each job keeps the settings from its\n"
            "own submission moment. The archive stores clean outputs; the watermark is\n"
            "applied at delivery."
        ),
    },
    "nav_branding_splitwarn": {
        "fa": "⚠️ خروجی‌های بزرگ‌تر از سقف تلگرام (چندپارتی) فعلاً برندینگ شخصی نمی‌گیرند.",
        "en": "⚠️ Outputs split into multiple parts currently skip personal branding.",
    },
    "nav_b_thumb": {"fa": "🖼 تامبنیل", "en": "🖼 Thumbnail"},
    "nav_b_wm": {"fa": "💧 واترمارک", "en": "💧 Watermark"},
    "nav_b_cap": {"fa": "📝 کپشن", "en": "📝 Caption"},
    "nav_b_preview": {"fa": "👁 نمای کلی برندینگ", "en": "👁 Branding overview"},
    "nav_preview_rendering": {"fa": "⏳ در حال ساخت پیش‌نمایش…", "en": "⏳ Building preview…"},
    "nav_preview_thumb": {"fa": "🖼 این تامبنیل شخصی ذخیره‌شدهٔ شماست.", "en": "🖼 This is your stored personal thumbnail."},
    "nav_preview_wm": {"fa": "💧 پیش‌نمایش تقریبی واترمارک (بوم سفید — جای‌گذاری واقعی روی ویدیوی شما انجام می‌شود).", "en": "💧 Approximate watermark preview (white canvas — applied to your real video at delivery)."},
    "nav_preview_cap": {"fa": "📝 کپشن شخصی شما:\n\n{caption}", "en": "📝 Your personal caption:\n\n{caption}"},
    "nav_send_command": {"fa": "برای ادامه این دستور را بفرست: {cmd}", "en": "Send this command to continue: {cmd}"},
    "nav_settings_hint": {
        "fa": "⚙️ تنظیمات با دستور /settings باز می‌شود — زبان، سبک تحویل (ویدیو/فایل) و اعلان نتیجه.\n\n📬 سبک تحویل: ویدیوی استریمی یا فایل پیوست\n🔔 اعلان: پیام خلاصه بعد از هر پردازش\n🌐 زبان: فارسی / English",
        "en": "⚙️ Open settings with /settings — language, delivery style (video/file) and result notifications.",
    },
    "den_text": {
        "fa": "⛔️ «{perm}» برای حساب شما فعال نیست.\nبرای فعال‌سازی باید Owner دسترسی بدهد.",
        "en": "⛔️ \"{perm}\" is not enabled for your account.\nOnly the Owner can enable it.",
    },
    "den_btn_request": {"fa": "📨 درخواست دسترسی", "en": "📨 Request access"},
    "den_sent": {"fa": "✅ درخواست شما برای Owner ارسال شد.", "en": "✅ Your request was sent to the Owner."},
    "den_rate_limited": {"fa": "⏳ درخواست قبلی‌ات ثبت شده؛ حداکثر ۳ درخواست در روز.", "en": "⏳ Request already sent; max 3 per day."},
    "den_already_granted": {"fa": "این قابلیت الان برای تو فعاله!", "en": "This capability is already enabled for you!"},
    "den_no_owner": {"fa": "⚠️ Owner تنظیم نشده است.", "en": "⚠️ Owner is not configured."},
    "den_failed": {"fa": "❌ ارسال درخواست ناموفق بود.", "en": "❌ Failed to send the request."},
    "den_owner_msg": {
        "fa": "📨 درخواست دسترسی:\n👤 {name} ({uid}) {uname}\n🧩 قابلیت: {perm}",
        "en": "📨 Access request:\n👤 {name} ({uid}) {uname}\n🧩 Capability: {perm}",
    },
    "own_btn_perm_open": {"fa": "👑 مدیریت دسترسی این ادمین", "en": "👑 Manage this admin"},
    # ---- watermark grouping (NEW wm:group:*) ----
    "wm_group_title": {"fa": "💧 واترمارک — {group}", "en": "💧 Watermark — {group}"},
    "wm_group_basic": {"fa": "تنظیمات پایه", "en": "Basic"},
    "wm_group_look": {"fa": "ظاهر و فونت", "en": "Appearance"},
    "wm_group_pos": {"fa": "موقعیت و حاشیه‌ها", "en": "Position & margins"},
    "wm_group_timing": {"fa": "زمان‌بندی", "en": "Timing"},
    "btn_wm_g_basic": {"fa": "🧩 تنظیمات پایه", "en": "🧩 Basic"},
    "btn_wm_g_look": {"fa": "🎨 ظاهر و فونت", "en": "🎨 Appearance"},
    "btn_wm_g_pos": {"fa": "📐 موقعیت و حاشیه‌ها", "en": "📐 Position & margins"},
    "btn_wm_g_timing": {"fa": "⏱ زمان‌بندی", "en": "⏱ Timing"},
    # ---- merge UX additions ----
    "mrg_banner": {
        "fa": "🔗 جلسه ادغام فعال است — این ویدیو به جلسه اضافه شد.",
        "en": "🔗 A merge session is active — this video was added to it.",
    },
    "mrg_order_title": {"fa": "🔗 ترتیب فعلی:", "en": "🔗 Current order:"},
    "mrg_total_size": {"fa": "📊 مجموع: {n} ویدیو | {size}", "en": "📊 Total: {n} videos | {size}"},
    "mrg_waiting_next": {"fa": "⏳ منتظر ویدیوی بعدی هستم («پایان و ادغام» هر وقت آماده بودی).", "en": "⏳ Waiting for the next video (finish whenever ready)."},
    "mrg_stage_preparing": {"fa": "۱/۵ آماده‌سازی فایل‌ها…", "en": "1/5 preparing files…"},
    "mrg_stage_analyze": {"fa": "۲/۵ بررسی سازگاری ویدیوها…", "en": "2/5 checking compatibility…"},
    "mrg_strategy_copy": {"fa": "⚡ ادغام سریع بدون بازانکود", "en": "⚡ fast merge without re-encoding"},
    "mrg_strategy_reencode": {"fa": "🎞 ادغام همراه با بازانکود برای سازگاری فایل‌ها", "en": "🎞 merging with re-encoding for compatibility"},
    "mrg_stage_merge": {"fa": "۳/۵ در حال ادغام…", "en": "3/5 merging…"},
    "mrg_stage_validate": {"fa": "۴/۵ اعتبارسنجی خروجی…", "en": "4/5 validating output…"},
    "mrg_stage_ready": {"fa": "۵/۵ آماده‌سازی برای ارسال…", "en": "5/5 preparing delivery…"},
    "mrg_done_summary": {
        "fa": "✅ ادغام با موفقیت انجام شد.\n\n🎬 تعداد ویدیوها: {count}\n⏱ مدت نهایی: {dur}\n📦 حجم نهایی: {size}\n⚡ روش: {strategy}",
        "en": "✅ Merge completed.\n\n🎬 Videos: {count}\n⏱ Final duration: {dur}\n📦 Final size: {size}\n⚡ Method: {strategy}",
    },
    "mrg_btn_compress_this": {"fa": "🎬 فشرده‌سازی همین خروجی", "en": "🎬 Compress this result"},
    "mrg_compress_started": {
        "fa": "✅ ادغام انجام شد.\n\n🎞 مرحله دوم: فشرده‌سازی ویدیو شروع شد.",
        "en": "✅ Merge done.\n\n🎞 Step two: compression has started.",
    },
    "mrg_compress_btn_denied": {
        "fa": "⛔️ این خروجی متعلق به جلسهٔ شما نیست یا دسترسی نداری.",
        "en": "⛔️ This result is not from your session or you lack permission.",
    },
    "mrg_compress_unavailable": {
        "fa": "⚠️ فایل این جلسه دیگر در دسترس نیست.",
        "en": "⚠️ This session's file is no longer available.",
    },
    "summary_degraded": {
        "fa": "⚠️ فایل اصلی در دسترس نبود؛ این نسخه از بهترین کپی موجود فشرده شده است.",
        "en": "⚠️ The original file was unavailable; this was encoded from the best available copy.",
    },
    "settings_title": {
        "fa": "⚙️ تنظیمات شما — با هر دکمه بین حالت‌ها جابه‌جا شوید:",
        "en": "⚙️ Your settings — tap a button to toggle it:",
    },
    "status_deferred": {
        "fa": "🕓 دیسک سرور پرتر از ظرفیت امن است؛ کار شما به‌صورت خودکار وقتی جا آزاد شد شروع می‌شود (بدون نیاز به ارسال مجدد).",
        "en": "🕓 Disk is temporarily at safe capacity; your job will start automatically when space frees up (no resend needed).",
    },
    "split_guide": {
        "fa": (
            "🧩 این خروجی به {n} بخش تقسیم شده (حجم بالای سقف ارسال تلگرام).\n"
            "بخش‌ها به ترتیب ارسال شدند و هر کدام جداگانه قابل پخش‌اند. "
            "برای اتصال: همهٔ پارت‌ها را در یک پوشه بگذارید و با فرمان "
            "\"copy /b part001.mp4+part002.mp4 out.mp4\" (ویندوز) یا "
            "\"cat part*.mp4 > out.mp4\" (لینوکس) به هم بچسبانید."
        ),
        "en": (
            "🧩 This output was delivered in {n} parts (above the Telegram upload limit).\n"
            "Parts were sent in order and each plays independently. To join: put all "
            "parts in one folder and run \"copy /b part001.mp4+part002.mp4 out.mp4\" "
            "(Windows) or \"cat part*.mp4 > out.mp4\" (Linux)."
        ),
    },
}


def tr(key: str, lang: str = "fa", **kw) -> str:
    entry = T.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry["fa"]
    if kw:
        try:
            return text.format(**kw)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def reject_text(code: str, lang: str = "fa", **kw) -> str:
    table = T["reject"]
    text = table.get(lang, table["fa"]).get(code) or table["fa"].get(code, code)
    if kw:
        try:
            return text.format(**kw)
        except (KeyError, IndexError, ValueError):
            return text
    return text


# ---------------------------------------------------------------------------
# JIT queue / EDU480 / naming / support / moderation (migration 015)
# ---------------------------------------------------------------------------
T["reject"]["fa"].update({
    "user_pending": "شما {max_pending} ویدیوی در انتظار دارید؛ بعد از پردازش آن‌ها دوباره ارسال کنید.",
    "queue_full": "صف پردازش در حال حاضر کاملاً پر است ({cap} کار)؛ درخواست شما ثبت نشد. کمی بعد دوباره ارسال کنید.",
    "blocked_user": "⛔️ دسترسی شما به ربات مسدود شده است.",
    "private_mode": "🔒 ربات در حال حاضر در حالت خصوصی قرار دارد و تنها برای مدیران مجاز در دسترس است.",
})
T["reject"]["en"].update({
    "user_pending": "You already have {max_pending} videos waiting; send more after they finish.",
    "queue_full": "The processing queue is completely full ({cap} jobs); your request was NOT accepted. Please try again later.",
    "blocked_user": "⛔️ Your access to this bot is blocked.",
    "private_mode": "🔒 The bot is currently in private mode and only available to authorized administrators.",
})

T.update({
    "welcome2": {
        "fa": (
            "👋 سلام {name}!\n\n"
            "🎓 ویدیوی آموزشی‌ات را بفرست (تا {max_gb} گیگابایت) تا با پروفایل "
            "EDU480 فشرده شود: متن تخته و اسلایدها خوانا، صدا واضح، حجم بسیار کمتر.\n\n"
            "۱) ویدیو را بفرست\n۲) نام دلخواه فایل خروجی را بنویس (فارسی یا انگلیسی، بدون پسوند)\n"
            "۳) وضعیت صف و پیشرفت کار را زنده ببین"
        ),
        "en": (
            "👋 Hi {name}!\n\n"
            "🎓 Send your educational video (up to {max_gb} GB). It is compressed with "
            "the EDU480 profile: readable boards/slides, clear audio, much smaller file.\n\n"
            "1) Send the video\n2) Type the output file name (Persian or English, no extension)\n"
            "3) Watch the live queue position and progress"
        ),
    },
    "btn_contact": {"fa": "📨 ارتباط با مدیریت", "en": "📨 Contact management"},
    "btn_myjobs": {"fa": "📋 کارهای من", "en": "📋 My jobs"},
    "btn_menu": {"fa": "🧭 منو", "en": "🧭 Menu"},
    "name_prompt": {
        "fa": (
            "✅ ویدیو دریافت شد\n"
            "━━━━━━━━━━━━━━━\n"
            "🎞 {src}\n📦 {size} | ⏱ {dur}\n"
            "━━━━━━━━━━━━━━━\n"
            "✏️ نام فایل خروجی را بنویس (فارسی یا انگلیسی).\n"
            "فقط نام؛ پسوند لازم نیست — خروجی همیشه MP4 است.\n"
            "مثال: درس مهندسی برق ← درس مهندسی برق.mp4\n\n"
            "⚠️ ویدیو هنوز دانلود نشده و تا نوبتش در صف دانلود نمی‌شود."
        ),
        "en": (
            "✅ Video received\n"
            "━━━━━━━━━━━━━━━\n"
            "🎞 {src}\n📦 {size} | ⏱ {dur}\n"
            "━━━━━━━━━━━━━━━\n"
            "✏️ Type the output file name (Persian or English).\n"
            "Name only, no extension — the output is always MP4.\n"
            "Example: University Lecture 01 → University Lecture 01.mp4\n\n"
            "⚠️ The video is not downloaded yet; it is fetched only when its turn comes."
        ),
    },
    "name_waiting_turn": {
        "fa": "📥 ویدیوی «{src}» دریافت شد. اول نام ویدیوی قبلی را بنویس؛ بعد نام این یکی پرسیده می‌شود.",
        "en": "📥 Received «{src}». Name the previous video first; this one is asked next.",
    },
    "btn_keep_name": {"fa": "📎 همان نام اصلی", "en": "📎 Keep original name"},
    "btn_cancel_video": {"fa": "✖️ لغو این ویدیو", "en": "✖️ Cancel this video"},
    "name_invalid": {
        "fa": "❌ نام معتبر نیست. یک نام فارسی یا انگلیسی بنویس (حداکثر ۱۰۰ کاراکتر).",
        "en": "❌ Invalid name. Type a Persian or English name (max 100 characters).",
    },
    "name_accepted": {"fa": "📝 نام خروجی: {name}", "en": "📝 Output name: {name}"},
    "name_expired": {
        "fa": "⌛️ زمان نام‌گذاری این ویدیو تمام شد. برای پردازش دوباره ارسالش کن.",
        "en": "⌛️ Naming time for this video expired. Send it again to process it.",
    },
    "draft_cancelled": {"fa": "✖️ این ویدیو لغو شد.", "en": "✖️ This video was cancelled."},
    "queue_card": {
        "fa": (
            "🎬 ویدیوی شما در صف ثبت شد\n"
            "━━━━━━━━━━━━━━━\n"
            "📝 {name}\n📦 {size} | ⏱ {dur}\n"
            "🆔 {job}\n"
            "━━━━━━━━━━━━━━━\n"
            "🟡 وضعیت: در انتظار پردازش\n"
            "📌 جایگاه در صف: {pos}\n"
            "⏳ کارهای جلوتر: {ahead}\n"
            "⚙️ پردازشگرهای فعال: {busy}/{slots}\n"
            "🕒 زمان تخمینی انتظار: {eta}\n"
            "━━━━━━━━━━━━━━━\n"
            "ℹ️ ویدیوی اصلی هنوز دانلود نشده؛ وقتی نوبتش برسد دریافت می‌شود.\n"
            "(زمان انتظار تخمین است، نه تضمین.)"
        ),
        "en": (
            "🎬 Your video is in the queue\n"
            "━━━━━━━━━━━━━━━\n"
            "📝 {name}\n📦 {size} | ⏱ {dur}\n"
            "🆔 {job}\n"
            "━━━━━━━━━━━━━━━\n"
            "🟡 Status: waiting for a worker\n"
            "📌 Queue position: {pos}\n"
            "⏳ Jobs ahead: {ahead}\n"
            "⚙️ Active workers: {busy}/{slots}\n"
            "🕒 Estimated wait: {eta}\n"
            "━━━━━━━━━━━━━━━\n"
            "ℹ️ The original has not been downloaded yet; it is fetched when its turn comes.\n"
            "(Waiting time is an estimate, not a guarantee.)"
        ),
    },
    "stage_card": {
        "fa": "{icon} {stage}\n━━━━━━━━━━━━━━━\n📝 {name}\n📦 {size} | ⏱ {dur}\n🆔 {job}\n━━━━━━━━━━━━━━━\n{body}",
        "en": "{icon} {stage}\n━━━━━━━━━━━━━━━\n📝 {name}\n📦 {size} | ⏱ {dur}\n🆔 {job}\n━━━━━━━━━━━━━━━\n{body}",
    },
    "st_reserved": {"fa": "نوبت شما رسید — آماده‌سازی", "en": "Your turn — preparing"},
    "st_downloading": {"fa": "در حال دریافت ویدیو از تلگرام", "en": "Downloading from Telegram"},
    "st_probing": {"fa": "تحلیل جریان‌های تصویر و صدا", "en": "Analyzing video/audio streams"},
    "st_checking": {"fa": "بررسی تکراری‌بودن و نیاز به فشرده‌سازی", "en": "Checking duplicates / need to compress"},
    "st_encoding": {"fa": "فشرده‌سازی EDU480", "en": "Compressing (EDU480)"},
    "st_validating": {"fa": "بررسی سلامت خروجی", "en": "Validating output"},
    "st_uploading": {"fa": "ارسال فایل نهایی", "en": "Uploading result"},
    "st_upload_retry": {"fa": "ارسال ناموفق بود؛ تلاش دوباره (بدون فشرده‌سازی مجدد)", "en": "Upload failed; retrying (no re-encode)"},
    "card_dl_body": {
        "fa": "⏱ زمان سپری‌شده: {elapsed}\n📥 حجم: {size}\n(سرور محلی تلگرام درصد دانلود را گزارش نمی‌کند؛ پس از پایان دانلود مرحله تغییر می‌کند.)",
        "en": "⏱ Elapsed: {elapsed}\n📥 Size: {size}\n(The local Telegram server reports no download percentage; the stage changes when it completes.)",
    },
    "card_probe_body": {
        "fa": "🖥 {res} | 🎞 {fps} fps | {vcodec}/{acodec}\n📶 {kbps} kbps\n🎯 پروفایل: EDU480 → {target}",
        "en": "🖥 {res} | 🎞 {fps} fps | {vcodec}/{acodec}\n📶 {kbps} kbps\n🎯 Profile: EDU480 → {target}",
    },
    "card_enc_body": {
        "fa": "[{bar}] {pct}%\n⚡️ سرعت: {speed}\n⏱ سپری‌شده: {elapsed}{eta}\n🎯 EDU480 → {target}",
        "en": "[{bar}] {pct}%\n⚡️ Speed: {speed}\n⏱ Elapsed: {elapsed}{eta}\n🎯 EDU480 → {target}",
    },
    "card_eta_suffix": {"fa": "\n⌛️ باقی‌مانده (تخمین): {eta}", "en": "\n⌛️ Remaining (estimate): {eta}"},
    "card_up_body": {
        "fa": "☁️ حجم خروجی: {out}\n⏱ سپری‌شده: {elapsed}",
        "en": "☁️ Output size: {out}\n⏱ Elapsed: {elapsed}",
    },
    "remux_note": {
        "fa": "ℹ️ این ویدیو از قبل با استاندارد EDU480 سازگار بود؛ بدون فشرده‌سازی مجدد تحویل شد.",
        "en": "ℹ️ This video already met the EDU480 standard; delivered without re-encoding.",
    },
    "known_output": {
        "fa": "♻️ این فایل قبلاً توسط همین ربات فشرده شده است؛ نسخهٔ موجود بدون پردازش دوباره ارسال شد.",
        "en": "♻️ This file was already compressed by this bot; the existing result was sent without reprocessing.",
    },
    # ---- support / contact management ----
    "sup_open": {
        "fa": (
            "📨 ارتباط با مدیریت\n━━━━━━━━━━━━━━━\n"
            "پیامت را همین حالا بنویس (متن، عکس، ویس یا فایل).\n"
            "فقط مدیر ارشد آن را می‌بیند و پاسخ از طریق همین ربات برایت ارسال می‌شود.\n\n"
            "⏳ این گفتگو تا {mins} دقیقه باز است."
        ),
        "en": (
            "📨 Contact management\n━━━━━━━━━━━━━━━\n"
            "Write your message now (text, photo, voice or file).\n"
            "Only the owner sees it; the reply arrives through this bot.\n\n"
            "⏳ This conversation stays open for {mins} minutes."
        ),
    },
    "sup_sent": {"fa": "✅ پیامت به مدیریت تحویل شد. پاسخ از طریق همین ربات می‌رسد.",
                 "en": "✅ Your message was delivered to management. The reply will arrive here."},
    "sup_cancelled": {"fa": "✖️ ارتباط با مدیریت لغو شد.", "en": "✖️ Contact cancelled."},
    "sup_failed": {"fa": "❌ ارسال پیام ممکن نشد؛ کمی بعد تلاش کنید.",
                   "en": "❌ Could not deliver the message; try again later."},
    "sup_is_owner": {"fa": "👑 شما مدیر ارشد هستید؛ پیام‌های کاربران برای شما ارسال می‌شود.",
                     "en": "👑 You are the owner; user messages are delivered to you."},
    "sup_no_owner": {"fa": "مدیریت هنوز تنظیم نشده است.", "en": "Management is not configured yet."},
    "sup_rate": {"fa": "⏳ پیام‌های زیادی فرستادی؛ کمی بعد دوباره امتحان کن.",
                 "en": "⏳ Too many messages; please try again later."},
    "sup_owner_header": {
        "fa": "📨 پیام پشتیبانی #{mid}\n👤 {name} {uname}\n🆔 {uid}\n🕒 {ts}",
        "en": "📨 Support message #{mid}\n👤 {name} {uname}\n🆔 {uid}\n🕒 {ts}",
    },
    "sup_btn_reply": {"fa": "↩️ پاسخ", "en": "↩️ Reply"},
    "sup_reply_prompt": {
        "fa": "✍️ پاسخ به {name} ({uid}) را بنویس. (برای لغو: /cancel)",
        "en": "✍️ Write your reply to {name} ({uid}). (/cancel to abort)",
    },
    "sup_reply_sent": {"fa": "✅ پاسخ برای {uid} ارسال شد.", "en": "✅ Reply sent to {uid}."},
    "sup_reply_failed": {"fa": "❌ ارسال پاسخ ناموفق بود (کاربر ربات را مسدود کرده؟).",
                         "en": "❌ Reply failed (user may have blocked the bot)."},
    "sup_reply_header": {"fa": "💬 پاسخ مدیریت:", "en": "💬 Reply from management:"},
    # ---- channel log / moderation ----
    "log_record": {
        "fa": (
            "🎬 درخواست فشرده‌سازی\n"
            "👤 {name} {uname}\n🆔 کاربر: {uid}\n"
            "🧾 کار: {job}\n"
            "📁 فایل اصلی: {src}\n📝 نام خروجی: {out}\n"
            "📦 {size} | ⏱ {dur}\n"
            "🕒 ثبت: {ts}\n"
            "⚙️ پروفایل: EDU480\n"
            "📍 وضعیت: {status}"
        ),
        "en": (
            "🎬 Compression request\n"
            "👤 {name} {uname}\n🆔 User: {uid}\n"
            "🧾 Job: {job}\n"
            "📁 Source: {src}\n📝 Output: {out}\n"
            "📦 {size} | ⏱ {dur}\n"
            "🕒 Submitted: {ts}\n"
            "⚙️ Profile: EDU480\n"
            "📍 Status: {status}"
        ),
    },
    "mod_btn_remove_ban": {"fa": "🗑 حذف ویدیو و مسدودسازی کاربر", "en": "🗑 Remove video & ban user"},
    "mod_btn_confirm": {"fa": "⚠️ تأیید حذف و بن", "en": "⚠️ Confirm remove & ban"},
    "mod_btn_abort": {"fa": "انصراف", "en": "Abort"},
    "mod_only_owner": {"fa": "فقط مالک ربات می‌تواند این کار را انجام دهد.", "en": "Only the owner can do this."},
    "mod_done": {"fa": "✅ ویدیو حذف و کاربر مسدود شد.", "en": "✅ Video removed and user banned."},
    "mod_already": {"fa": "این مورد قبلاً اعمال شده است.", "en": "Already applied."},
    "mod_user_notice": {
        "fa": "⛔️ درخواست شما به دلیل نقض قوانین حذف شد و دسترسی شما مسدود است.",
        "en": "⛔️ Your request was removed for violating the rules and your access is blocked.",
    },
})
