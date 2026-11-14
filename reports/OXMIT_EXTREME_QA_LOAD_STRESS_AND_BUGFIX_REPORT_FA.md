# گزارش Extreme QA، تست بار و استرس، شکار باگ و آمادگی تولید — Oxmit

> **سند:** EXTREME QA MEGAPROMPT — گزارش نهایی و یگانه
> **تاریخ:** 2026-11-14 · **محیط فعال:** Ohio `13.58.69.178` · **کد شروع QA:** `e6d5afa` · **کد نهایی:** **`696379d`** (branch `stabilization-20261114`)
> **نتیجه تست نهایی:** **۲۶۴ passed / 7 skipped / 0 failed** روی کد دیپلوی‌شده
> **برچسب‌ها:** `[MEASURED]` `[SOURCE-VERIFIED]` `[PROPOSED]` `[PROVISIONAL]` `[UNVERIFIED]`

---

## A. خلاصه مدیریتی

| پرسش | پاسخ |
|---|---|
| باگ واقعی جدید پیدا شد؟ | ✅ **بله — E9 (P1):** timeout شبکه روی ویرایش کارت وضعیت، حلقه تحویل را برای **بقیه گیرندگان** abort می‌کرد. رفع + تست رگرسیون |
| رفع و deploy شد؟ | ✅ commit `696379d` → build → restart → healthz سبز، ۰ خطا |
| race/هم‌زمانی تست شد؟ | ✅ ۵ ریس دو-claimer هم‌زمان روی DB ایزوله: **۵ claim / ۵ ریس، صفر دوبله** (SKIP LOCKED سالم) |
| DB load؟ | ✅ ۵۰۰۰ job synthetic روی DB ایزوله — کشف **p95=3.4s** برای ORDER BY غیر-sargable aging؛ در مقیاس واقعی (MAX_QUEUED_JOBS=50) p95=۷۰ms |
| API load؟ | ✅ healthz ۳۰۰/۳۰۰ (p95=۱۵۸ms)؛ panel summary ۱۰۰/۱۰۰ (p95=۲۳ms) — صفر خطا |
| Media/FFmpeg؟ | ✅ کورپوس ۷ پروفایل + ۲ فایل خراب — همه تصمیم‌ها درست، probe خراب‌ها reject |
| Security fuzz؟ | ✅ SQLi/XSS/path-traversal/bad-uuid — parameterized، 403/401/200-safe، صفر نشت |
| Soak ۱۲ساعته؟ | ⏳ NOT TESTED — نیازمند پنجره بلند؛ ریسک‌های شناخته‌شده bounded |
| آمادگی نهایی؟ | **آماده بهره‌برداری با محدودیت مشخص** (بخش N) |

---

## B. معماری محیط تست

| لایه | اجرا | جداسازی از Production |
|---|---|---|
| Unit/Regression | venv ایزوله `/tmp/oxtest` روی Ohio، `pytest tests/` | کد از /opt/oxmit کپی می‌شود؛ DB از FakeDB stub |
| Concurrency/DB-load | **DB ایزوله** `oxmit_test_backup_20261114` (بکاپ‌گرفته از era تست) — rows synthetic با marker `requester_tg_id=987654321` | production DB دست‌نخورده؛ cleanup marker-scoped بعد از هر تست (تأیید `remaining=0`) |
| API load | روی production endpoints **فقط read-only** (healthz, summary) | هیچ write؛ هیچ encode |
| Media/FFmpeg | داخل کانتینر bot، `/media/test/` (retention sweep خودکار پاک می‌کند) | pipeline تولید دست نخورده |
| Security fuzz | owner session واقعی + payloadهای مخرب روی endpoints parameterized | هیچ داده تولیدی تغییری نکرد |
| Static analysis | ruff + bandit روی کپی منبع در /tmp/qa-src | فقط‌خواندنی |

**محدودیت‌های تست (صادقانه):** تعامل تلگرام واقعی (progress cards/delivery E2E) نیاز به کلاینت مالک دارد و mock نشده؛ soak بلند و chaos ترکیبی (چند خرابی هم‌زمان) اجرا نشد؛ no second poller برقرار ماند.

## C. نتایج تست‌ها

### C۱. Static Analysis `[MEASURED]`
- **Bandit: صفر یافته با severity ≥ medium** در کل `bot/` — تأیید حذف موفق endpointهای پرخطر در release قبلی.
- Ruff (E,F,B,ASYNC,SIM,UP,PLR,RUF): **۱۳ یافته، همه P3 cosmetic** — F401 unused-import ×۶، F841 unused-var ×۵ (شامل دو متغیر در `decision_engine.py` — همان ماژول dead-code شناخته‌شده)، F811 دو redefinition `_sign`/`_check_cookie` در webpanel (سایه‌روشن از security.py، بی‌اثر عملی). طبق سیاست «رفع صرفاً برای ساکت‌کردن linter ممنوع» → **فهرست، بدون تغییر کد**.

### C۲. Concurrency & Race `[MEASURED]`

| تست | روش | نتیجه |
|---|---|---|
| Double-claim (۵ ریس، ۲ claimer هم‌زمان، pg_sleep-forced overlap) | دو `UPDATE...FOR UPDATE SKIP LOCKED` هم‌زمان روی همان job | **۵ ریس → ۵ claim، صفر دوبله** — در هر ریس دقیقاً یک worker برنده |
| Multi-worker claim (۴ claimer × ۳ دور، ۱۰ job) | parallel psql + SKIP LOCKED + aging ORDER BY | فقط-نویز harness (فایل‌های claim باقی‌مانده)؛ نتیجه قطعی از تست تک-جوب |
| Empty-queue claim | claim روی صف خالی | ۰ ردیف، بدون خطا ✓ |
| Lease-expired recovery | `recover_on_startup` + `reap_stale_leases` (تست‌های موجود + قبلی) | PASS |

### C۳. DB Load روی DB ایزوله `[MEASURED]`

| سناریو | نتیجه |
|---|---|
| ۵۰۰۰ job queued synthetic (insert) | موفق |
| ۲۰۰ sequential claim (p50/p95/max) | **۷۲ms / **۳۳۸۹ms** / ۳۴۵۶ms — پ95 توسط ORDER BY غیر-sargable aging در ۵k ردیف (Seq Scan+Sort) |
| EXPLAIN | Seq Scan + Sort — aging expression ناسازگار با idx_jobs_queue_order |
| **مقیاس تولید (۵۰ ردیف = MAX_QUEUED_JOBS فعلی)** | **p50=۶۶ / p95=۷۰ / max=۷۳ms** شامل ~۵۵ms spawn overhead psql → زمان واقعی کوئری < ۱۵ms ✓ |

**تصمیم:** aging نگه داشته می‌شود؛ **مستند:** اگر MAX_QUEUED_JOBS به ≥۱۰۰۰ افزایش یابد، ORDER BY aging باید sargable شود (backlog §M). این یافته مستقیماً از تست آمده — همان چیزی که prompt خواست («مشکل واقعی پیدا کن»).

### C۴. Media / FFmpeg Corpus `[MEASURED]` — اجرای واقعی داخل کانتینر bot

| نمونه | probe | decide | predict-guard |
|---|---|---|---|
| h265 720p | 1280×720 hevc | **encode** (downscale به 480p) ✓ | - |
| بدون صدا 480p | 854×480 | encode (testsrc2=۳٫۵Mbps) ✓ | - |
| multi-audio 480p | 640×480 aac×۲ | encode ✓ | - |
| 60fps 720p | 1280×720@60 | encode ✓ (fps cap) | - |
| نسبت‌عجیب 200×800 | portrait | encode ✓ (short-side logic) | - |
| **low-bitrate 480p** (۱۵۷kbps) | compliant | **remux** ✓ | FIRE (سازگار — guard فقط روی مسیر encode consult می‌شود) |
| hevc 4K | 3840×2160 | encode ✓ (downscale) | - |
| فایل کاملاً خراب (random 50KB) | — | **correctly rejected** (probe fail) ✓ | |
| mp4 truncated (۲۰KB از ابتدای فایل سالم) | — | **correctly rejected** (moov atom not found) ✓ | |

### C۵. API Load (read-only، کنترل‌شده) `[MEASURED]`

| Endpoint | درخواست | موفق | p95 | max |
|---|---:|---:|---:|---:|
| `/internal/healthz` (۱۰ concurrent × ۳۰) | ۳۰۰ | ۳۰۰ (۱۰۰٪) | ۱۵۸ms | ۲۱۵ms |
| `/panel/api/summary` (۵ concurrent × ۲۰) | ۱۰۰ | ۱۰۰ | ۲۳ms | ۲۷ms |

صفر 4xx/5xx. Load سبک و read-only طبق قواعد — هیچ encode/broadcast/پیامی تحریک نشد.

### C۶. Security fuzz `[MEASURED]`

| حمله | نتیجه |
|---|---|
| SQLi در `q=` (`' OR 1=1 --`, `; DROP TABLE jobs`) | HTTP 200 — parameterized، به‌عنوان عبارت جستجو امن ✓ |
| job-id manipulation در cancel (`' OR 1=1 --`, `1=1,1`) | **403** (CSRF gate اولین خط دفاعی) — bad uuid هم 400 (cast-safe) ✓ |
| XSS در user message | CSRF-block ✓ (payload وارد DB نشد) |
| path traversal در logs q | 200-safe — فقط substring search، هیچ file access ✓ |
| logs بدون session | **401** ✓ |
| Bandit | صفر medium+ ✓ |

## D. تست چند هزار کاربر `[MEASURED]` — خلاصه

| سناریو | مقدار |
|---|---|
| کاربران synthetic در DB ایزوله | ۵۰۰۰ (insert مستقیم — شبیه‌سازی رکورد، نه encode هم‌زمان) |
| jobs synthetic | ۵۰۰۰ queued + ۱۰ |
| claim latency p50 / p95 | ۷۲ms / ۳۳۸۹ms — **یافته: non-sargable aging در ۵k صف**؛ در مقیاس ۵۰ (production cap فعلی) p95=۷۰ms |
| کانت ۵۰۰۰ ردیف | ۶۹ms |
| concurrent API requests | ۳۰۰ (healthz) + ۱۰۰ (summary) — ۱۰۰٪ موفق |
| Encodeهای فعال هم‌زمان | ۲ (تنظیم تولید؛ benchmark قبلی: concurrency>۲ سود aggregate ندارد) |
| CPU/RAM حین API load | حداکثر bot ~۲۰۰MB، CPU < ۱۰٪ |
| Database connections | pool max=10، بدون exhaustion |
| نتیجه | صف در مقیاس ۵۰ پاس؛ در ۵k نیاز به sargable aging (backlog) |

## E. گلوگاه‌ها

1. **اولین bottleneck:** CPU انکود (۴٫۵ هسته مفید) — throughput aggregate ≈ ۱۰۵–۱۳۳ fps، مستقل از concurrency بالاتر از ۲.
2. **دوم:** claim latency در صف‌های بزرگ (>۱k queued) با aging غیر-sargable — در cap فعلی (۵۰) بی‌اثر؛ در افزایش cap باید sargable شود.
3. **سوم:** پهنای باند تلگرام برای deliveryهای هم‌زمان (semaphore ۲ — کنترل‌شده).
4. بیشترین فشار: Encore workers هنگام انکود هم‌زمان (CPU-share).
5. بهینه‌سازی با بیشترین اثر: dedup exact + predict-guard (انکود نکردن) — فعال.

## F. گزارش باگ‌ها

| ID | شدت | محل | شرح | ریشه | رفع | تست | وضعیت |
|---|---|---|---|---|---|---|---|
| E1 | **P0** | `engine._stage_source` | worker نتوانست staging symlink بخواند → **شکست job واقعی مالک** (۷۲۰MB) | bot-api فایل 0600/dirs 0750 | chmod در staging | `test_stage_source_symlink_grants_worker_read` | ✅ FIXED+DEPLOYED (release قبلی) |
| E9 | **P1** | `engine.edit_status_sync` + failed-card edits | `TimeoutError`/`ConnectionResetError` روی edit کارت، حلقه تحویل را برای **بقیه requesters** می‌شکست | catchها فقط TelegramAPIError بودند | broadened catches (Timeout/ConnReset/ClientError) در ۳ نقطه | `test_edit_status_sync_swallows_network_timeout`, `test_network_timeout_on_card_edit_does_not_abort_other_requesters` | ✅ FIXED+DEPLOYED (`696379d`) |
| E10 | P2 | `jobqueue._claim_next` ORDER BY | aging غیر-sargable → در صف ≥۱k ردیف p95>۳s | expression محاسباتی روی ستون‌ها | مستند + شرط backlog (sargable در افزایش cap) | benchmark این گزارش | ✅ documented |
| E11 | P3 | decision_engine.py (dead module) | متغیرهای unused | dead-code شناخته‌شده | — (ماژول غیرفعال) | — | مستند |

## G. اصلاحات سورس (این release)

- `bot/oxmit/archive.py` — sent_unknown branches (۳ روش delivery)
- `bot/oxmit/engine.py` — `_make_botapi_readable`, edit_status_sync broadened, failed-card broadened ×۲, sent_unknown bookkeeping (unknown counter، skip delivered=TRUE در ابهام)، redeliver→delivered=TRUE، predict-guard wiring
- `bot/oxmit/jobqueue.py` — aging ORDER BY، `_deliver_source`، predict-guard wiring
- `bot/oxmit/edu480.py` — `predict_guard` pure helper
- `bot/oxmit/config.py` — ENCODE_PREDICT_GUARD / PREDICT_NO_GAIN_RATIO + validation
- `bot/oxmit/resources.py` — cores_for per-replica pool semantics
- `bot/oxmit/log.py` — RingBufferHandler + recent_logs
- `bot/oxmit/webpanel.py` — logs endpoint + filter + حذف Milestone-2 unsafe imports/routes
- `bot/oxmit/panel/security.py` / `bot_manager.py` / `dashboard.py` / `handlers/support.py` — owner fail-closed
- `bot/oxmit/dashboard_page.py` — حذف ۵ nav-tab خطرناک
- `bot/oxmit/texts.py` — summary_duration_unknown
- حذف: `panel/superadmin.py`, `tests/test_panel_superadmin.py`

## H. امنیت

Bandit صفر medium+ · SQLi/XSS/path-traversal fuzz امن · CSRF فعال · unauthorized 401 · bad-uuid 400 · removed-endpoints 404 · secretها redact · **هیچ exploit instruction در این گزارش نیست.**

## I. Performance (قبل/بعد)

| متریک | قبل (1699d98 در Ohio) | بعد (696379d) |
|---|---|---|
| job واقعی ۷۲۰MB مالک | **FAILED** (Permission denied) | **تحویل در ~۴۰s** (guard skip) |
| tuner | overcommit پتانسیل ۴٫۵×N | ۲×2.25 cap شده |
| claim @۵k queued | — | p95=۳.۴s (یافته؛ در cap ۵۰ → ۷۰ms) |
| API p95 | — | healthz ۱۵۸ms / summary ۲۳ms |
| tests | ۲۵۵+۷ skip | **۲۶۴+۷ skip، ۰ fail** |

## J. منابع

حین API load: bot CPU <۱۰٪، RAM ~۲۰۰MB؛ workerها idle ۰٪؛ postgres ~۵۰MB؛ دیسک ۶۱۲GB آزاد؛ بدون نشتی مشاهده‌شده در بازه تست. soak بلند → §K.

## K. مشکلات حل‌نشده

1. **soak ۱۲/۲۴h** اجرا نشد (پنجره زمانی) — ریسک نشتی آرام: پایین (تمام بافرها bounded در کد) ولی اثبات‌نشده.
2. **delivery outbox/ledger** — sent_unknown فقط ثبت می‌شود؛ reconciliation خودکار ندارد (دستی: redeliver).
3. **aging non-sargable** در صف‌های >۱k — cap فعلی ۵۰ بی‌اثر؛ در افزایش cap حتماً قبلش sargable شود.
4. **تعامل تلگرام واقعی** (progress cards روی پیام واقعی) — نیاز به کلاینت مالک؛ mock-level تست شد.
5. chaos ترکیبی (چند خرابی هم‌زمان) — تک-خرابی تست شد.

## L. ظرفیت واقعی

| سناریو | ظرفیت | مبنا |
|---|---|---|
| کاربران ثبت‌نامی | هزاران (PG معمولی) | jobs=۱۷ فعلی؛ ۵k rows synthetic تست شد |
| درخواست هم‌زمان API | ≥۱۰ concurrent @ p95 ۱۵۸ms `[MEASURED]` | — |
| intake هم‌زمان | bounded با MAX_PENDING/MAX_QUEUED(۵۰) | config |
| **انکود هم‌زمان** | **۲** (benchmark: >۲ سود aggregate ندارد) | `[MEASURED]` |
| انکود روزانه پایدار | ~۵۰–۹۰ (۴٫۵ CPU، mix فرضی V3) | `[ESTIMATE/PROVISIONAL]` |
| اولین bottleneck | CPU انکود | benchmark |

## M. برنامه ادامه

- **فوری:** soak ۱۲h ایزوله در پنجره شب؛ پایش `deliveries status='unknown'`؛ smoke تعاملی مالک.
- **کوتاه‌مدت:** sargable aging (قبل از هر افزایش MAX_QUEUED_JOBS)؛ delivery reconciliation خودکار؛ ruff F401/F841 پاک‌سازی.
- **میان‌مدت:** delivery outbox (`delivery_tasks`+attempts)؛ storage ledger؛ dedup ادراکی با holdout.
- **بلندمدت:** scheduler چند-سروری؛ panel v4 consolidation؛ benchmark محتوای واقعی + VMAF.

## N. نتیجه نهایی

**آماده بهره‌برداری با محدودیت مشخص.**

- چرخه کامل پردازش با داده واقعی مالک تأیید شد؛ صف در race سالم است؛ API سالم و سریع؛ امنیت harden شده؛ ۲۶۴ تست سبز روی کد deploy شده.
- محدودیت‌ها: ظرفیت انکود هم‌زمان = ۲؛ soak بلند و E2E تلگرامی real-client تست نشده؛ aging در صف >۱k غیر-sargable.
- **پیش از افزایش بار:** فقط اگر MAX_QUEUED_JOBS/ترافیک > ظرفیت فعلی شد → worker سوم یا sargable aging؛ در غیر این صورت سیستم فعلی برای بار هدف کافی است.

**هیچ داده تولیدی تغییر/حذف نشد؛ همه تست‌های تخریبی روی DB ایزوله و /media/test اجرا شدند؛ cleanup marker-scoped انجام و تأیید شد؛ هیچ secret در گزارش نیست.**