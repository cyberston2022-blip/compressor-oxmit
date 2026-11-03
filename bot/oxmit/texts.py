"""Bilingual strings (fa default, en optional) + tr() helper."""

from __future__ import annotations

T: dict[str, dict[str, str]] = {
    "welcome": {
        "fa": (
            "👋 سلام علیکم {name}!\n\n"
            "🎬 ویدیویی که می‌خوای فشرده بشه رو بفرست (تا {max_gb} گیگابایت).\n"
            "♻️ اگر همین ویدیو قبلاً فشرده شده باشه، همون نتیجه فوراً برات ارسال می‌شه."
        ),
        "en": (
            "👋 Hi {name}!\n\n"
            "🎬 Send the video you want compressed (up to {max_gb} GB).\n"
            "♻️ If this exact video was compressed before, the existing result is sent instantly."
        ),
    },
    "btn_compress": {"fa": "🎬 فشرده‌سازی", "en": "🎬 Compress"},
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
    "cancelled": {"fa": "🚫 کار {job} لغو شد.", "en": "🚫 Job {job} cancelled."},
    "stage_copying": {"fa": "آماده‌سازی فایل", "en": "Preparing file"},
    "stage_queued": {"fa": "در صف", "en": "Queued"},
    "stage_encoding": {"fa": "فشرده‌سازی", "en": "Encoding"},
    "stage_validating_out": {"fa": "بررسی خروجی", "en": "Validating output"},
    "stage_archiving": {"fa": "آرشیو", "en": "Archiving"},
    "stage_delivering": {"fa": "ارسال نتیجه", "en": "Delivering"},
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
    "summary_header": {"fa": "✅ خلاصهٔ نتیجه", "en": "✅ Result summary"},
    "summary_file": {"fa": "📁 فایل: {name}", "en": "📁 File: {name}"},
    "summary_size": {"fa": "💾 {src} → {out}", "en": "💾 {src} → {out}"},
    "summary_saved": {"fa": "📉 صرفه‌جویی: {saved} ({pct}٪)", "en": "📉 Saved: {saved} ({pct}%)"},
    "summary_saved_neg": {
        "fa": "📉 تغییر حجم: {delta} (افزایشی — سیاست no-gain اعمال شد)",
        "en": "📉 Size change: {delta} (increase — no-gain policy applied)",
    },
    "summary_duration": {"fa": "⏱ مدت ویدیو: {dur}", "en": "⏱ Duration: {dur}"},
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
            "📋 اطلاعات فایل\n"
            "📁 نام: {name}\n"
            "💾 حجم: {size}{limit_note}\n"
            "⏱ مدت: {dur}\n"
            "📐 رزولوشن: {res}\n"
            "🎞 کدک: {codec}\n"
            "🧵 نوع: {kind}"
        ),
        "en": (
            "📋 File info\n"
            "📁 Name: {name}\n"
            "💾 Size: {size}{limit_note}\n"
            "⏱ Duration: {dur}\n"
            "📐 Resolution: {res}\n"
            "🎞 Codec: {codec}\n"
            "🧵 Kind: {kind}"
        ),
    },
    "info_unavailable": {"fa": "نامشخص", "en": "unknown"},
    "info_kind_video": {"fa": "ویدیوی تلگرام", "en": "Telegram video"},
    "info_kind_doc": {"fa": "فایل ویدیویی", "en": "video document"},
    "status_queued_hint": {
        "fa": "⏳ کار در صف قرار گرفت — پیشرفت به‌صورت خودکار اینجا به‌روز می‌شود.",
        "en": "⏳ Job queued — progress updates will appear here.",
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
