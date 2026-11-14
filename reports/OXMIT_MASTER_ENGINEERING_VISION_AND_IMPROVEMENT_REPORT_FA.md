# گزارش چشم‌انداز مهندسی جامع Oxmit — ارزیابی، انتخاب و پیاده‌سازی

> **سند:** MASTER ENGINEERING VISION — گزارش نهایی و یگانه (A..M طبق ساختار الزامی)
> **تاریخ:** 2026-11-14 · **محیط فعال:** Ohio `13.58.69.178` (Static IP — توجه: IP عمومی قبلی `18.222.98.81` با تخصیص Static جدید عوض شد؛ IPv6 و private IP ثابت مانده‌اند)
> **کد فعال:** branch `stabilization-20261114` → `e6d5afa` (بر پایه `afecaad` ← `1699d98`)
> **برچسب‌ها:** `[MEASURED]` `[SOURCE-VERIFIED]` `[PROPOSED]` `[PROVISIONAL]` `[UNVERIFIED]`

---

## A. خلاصه مدیریتی (Executive Summary)

**معماری فعلی (راستی‌آزمایی‌شده):** یک سرویس فشرده‌سازی ویدیو با صف ماندگار PostgreSQL، اکسیکیوتر SVT Encore با Redis صف داخلی، Local Telegram Bot API برای فایل تا 2GB، کانال آرشیو خصوصی به‌عنوان storage بادوام، پنل وب aiohttp با احراز هویت توکن/لینک یک‌بارمصرف، و dispatch داخلی با lease/heartbeat. این ترکیب سالم است و **نگه داشته شد**.

**مهم‌ترین یافته‌های این ارزیابی:**
1. سیستم پس از دو release قبلی (مهاجرت + پایدارسازی) از نظر امنیتی/صحت داده در وضعیت خوبی است؛ باگ P0 واقعی این هفته (staging chmod) رفع و deploy شد.
2. **بزرگ‌ترین ضعف باقی‌مانده:** تحویل تلگرام فاقد outbox/ledger است — نتیجه مبهم (`sent_unknown`) در این هفته واقعاً رخ داد و با reconciliation دستی حل شد؛ پیاده‌سازی کامل آن P1 فوری است.
3. **بزرگ‌ترین فرصت کارایی:** در مصرف واقعی، بیشتر صرفه از «انکود نکردن» می‌آید (dedup exact + guard جدید) نه از سریع‌ترکردن FFmpeg؛ ظرفیت محاسباتی فعلی (۲×2.25 CPU) برای بار فعلی کافی است.
4. پنل وب عملیاتی‌تر شد (terminal/env/SQL خام حذف، logs explorer اضافه)؛ مسیر تکامل آن به سمت یک API v4 منسجم باقی است.

**چهار بهبود در این اجرا پیاده، تست و deploy شد:** (۱) `sent_unknown` برای تحویل مبهم، (۲) anti-starvation aging در صف، (۳) logs explorer درون-پروسه‌ای + endpoint امن، (۴) redeliver ثبت delivered requester. جزئیات در §I؛ طبقه‌بندی کامل ایده‌ها در §M و بخش طبقه‌بندی.

## B. معماری واقعی (راستی‌آزمایی‌شده)

**اجزا و مسئولیت‌ها** (راستی‌آزمایی با بازرسی کد + سرور، این هفته):

| جزء | وضعیت | محل |
|---|---|---|
| Intake متادیتا-محور + drafts نام‌گذاری | فعال؛ reuse دیگر intake را بلاک نمی‌کند (FIX این هفته) | `handlers/intake.py`, `jobqueue.register_job` |
| صف PostgreSQL + claim اتمیک (SKIP LOCKED + fairness + aging جدید) | فعال | `jobqueue._claim_next` |
| Download JIT + staging symlink/hardlink/copy | فعال؛ chmod worker-readability جدید | `engine._stage_source` |
| تحلیل: ffprobe+SHA+decide(remux/encode)+predict-guard | فعال | `edu480.decide`, `edu480.predict_guard`, `jobqueue._run_pipeline` |
| Encore submit/status/callback HMAC | فعال | `encore_client`, `internal_api` |
| validation خروجی + آرشیو idempotent | فعال | `engine.complete_job`, `archive` |
| Delivery زنجیره copy→file_id→upload + `sent_unknown` (جدید) | فعال | `archive.deliver_result`, `engine` |
| پنل وب (auth + داشبورد + jobs/users/broadcast/logs-explorer جدید) | فعال؛ unsafeها حذف | `webpanel`, `dashboard`, `panel/*` |
| monitoring: healthz + counters + audit_log + logs ring (جدید) | فعال | `internal_api`, `log.py`, `audit.py` |

**مسیرهای بحرانی:** intake→register (فقط متادیتا) → dispatch→claim→download→probe/sha→decision→Encore→validation→archive→delivery→cleanup؛ recovery: lease-reaper + `recover_on_startup` + delivery-unknown reconciliation (دستی در این نسخه).

**Dependency map (خلاصه):** bot ← PG + docker.sock + Local Bot API + Encore-web + Redis(فقط Encore)؛ workerها ← /media ro + redis + encore-web؛ هر چرخه dispatch هر ۵ ثانیه. حلقه‌های پس‌زمینه bounded (fingerprinter maxlen=200، sweep ۱۰min، dispatch lock).

## C. مرور الگوریتم‌ها (خوب/ضعیف/تغییر)

| ناحیه | خوب | ضعیف | تغییر این اجرا |
|---|---|---|---|
| Intake | متادیتا-محور، prompts ترتیبی با expiry/idempotency | ترتیب فقط created_at (هم‌ثانیه)؛ reuse sync قدیم | **رفع:** reuse async؛ user_seq همچنان backlog |
| Queue/Claim | SKIP LOCKED، fairness per-user، lease+reaper | نبود aging → امکان starvation لبه‌ای | **رفع:** aging +5/h cap 15 (validate روی DB ایزوله: 4h→اولویت 65 جلوتر از VIP تازه) |
| Scheduling/ظرفیت | tuner per-replica (pool=4.5، 2×2.25) | tuner نمی‌داند کدام worker مشغول است (مقدار یکسان به همه) | مستند؛ dynamic-allocator به backlog |
| Dedup | exact (شناسه+SHA) + own-output + in-flight join | ادراکی disconnect (fingerprinter می‌سازد، مصرف ندارد) | حفظ exact؛ ادراکی → backlog با گیت آماری |
| Decision | EDU480-compliant→remux؛ no-gain پس از encode؛ **predict-guard جدید** | مدل bpp دقیق نیست (±۳۰٪) | **رفع سطحی:** guard فقط وقتی مطمئن؛ کالیبراسیون → backlog |
| Encoding | EDU480 ثابت با vf/fps داینامیک؛ threads بر اساس slots | threads_single=5 روی host واقعی verification نشده | ثابت؛ benchmark واقعی → backlog |
| Download | JIT + shield/cancel + حذف ایمن منبع | progress نامعین (طراحی صادقانه فعلی) | بدون تغییر (درست) |
| Archive | idempotent per-part، missing detection | وابستگی به بقای پیام تلگرام | بدون تغییر؛ verify → backlog |
| Delivery | زنجیره fallback؛ flood_safe؛ **sent_unknown جدید** | بدون outbox/ledger؛ duplicate risk در retry مستند | **رفع حداقلی:** ردیف unknown + شمارنده مستقل؛ outbox کامل → backlog |
| Recovery | lease/heartbeat/recover_on_startup/drain-safe | merge نیمه‌کاره → failed همیشه | بدون تغییر (درست) |

## D. فرصت‌های کارایی (رتبه‌بندی)

| # | فرصت | اثر | نوع شواهد | وضعیت |
|---|---|---|---|---|
| ۱ | dedup exact + own-output (دور زدن انکود) | بالا — صفر CPU در hit | `[MEASURED]` job واقعی reuse در ۴۰s | فعال از قبل |
| ۲ | **predictive no-gain guard** | بالا — جلوگیری از انکود بی‌فایده (نمونه واقعی: ۷۲۰MB → skip) | `[MEASURED]` این هفته + مدل `[PROVISIONAL]` | ✅ پیاده شد |
| ۳ | aging صف | متوسط (کیفیت عدالت در مقیاس) | `[PROPOSED]` + validate SQL | ✅ پیاده شد |
| ۴ | tuner per-replica (رفع overcommit) | متوسط — 74→104 fps در concurrency=3 | `[MEASURED]` benchmark Ohio | ✅ قبلاً + این اجرا تست |
| ۵ | WORKERS_READ_BOTAPI chmod (صفر کپی staging) | متوسط — حذف کپی چند-GB per job | `[MEASURED]` (job واقعی پس از رفع) | ✅ |
| ۶ | preset/CRF tuning per content-class | متوسط | `[UNVERIFIED]` — نیاز benchmark محتوای واقعی | backlog |
| ۷ | x265 escalation | کم تا متوسط، هزینه CPU ۲–۳× | `[UNVERIFIED]` | REJECT تا benchmark |
| ۸ | AV1 / hw accel | نامشخص | سخت‌افزار فاقد hw؛ compat تلگرام | REJECT فعلاً |
| ۹ | two-pass | کم برای این workload | زمان ۲× | REJECT پیش‌فرض |

## E. نقشه راه پنل وب

**موجود و فعال (بعد از hardening این هفته):** auth توکن+one-time (HMAC cookie+CSRF+rate-limit+lockout)، داشبورد KPI، jobs فیلترپذیر + job-detail timeline، users + ban/vip/limits، broadcast با preview/stop، worker/container status+restart+logs، audit_log viewer، sessions revoke، WebSocket زنده، **logs explorer جدید** (`/panel/api/logs` — ring buffer درون-پروسه، owner-only، فیلتر level/job/متن؛ محدودیت مستند: فقط پروسه bot).
**حذف‌شده (امنیت):** shell خام، SQL خام، env-raw، file-delete، FFmpeg customizer بی‌اثر — همه 404 تأیید شد.
**نقشه آینده (اولویت):** ① delivery monitoring با unknown-state، ② queue-ops با تفکیک pause-intake/encode، ③ یکپارچه‌سازی API نسخه‌ها به v4 واحد + session در DB، ④ job timeline با eventها (decisions/evidence)، ⑤ UI لاگ‌ها روی endpoint جدید.

## F. مرور امنیت

| یافته | شدت | وضعیت |
|---|---|---|
| هاردکد owner + fallback اولین ادمین | High | ✅ رفع (fail-closed، تک‌منبع env) |
| shell/SQL/env خام در پنل | Critical | ✅ حذف کامل (404) |
| secret در پاسخ env API | High | ✅ حذف (endpoint حذف شد) |
| get/update app_config بدون allowlist | Medium | ✅ allowlist + reject |
| session در RAM (ری‌استارت = خروج همه) | Medium | ⏳ backlog (DB store) |
| update_bot_config بدون allowlist | Medium | ✅ رفع + تست |
| CSRF/authz panel | Low (سالم) | حفظ + require_owner روی همه |
| توکن/secret در لاگ | — | redact حفظ؛ هیچ secret چاپ نشد |

## G. تحلیل منابع و ظرفیت

- CPU: ۸ vCPU؛ بودجه انکود ۴٫۵ (۲ worker × 2.25) — **تأیید `docker inspect` (nano=2.25e9)**؛ بقیه برای OS/PG/Redis/bot/botapi/Encore-web.
- benchmark مرجع (سینتتیک testsrc2 1080p60s): concurrency=2 → aggregate ۱۰۴٫۹–۱۳۳٫۳ fps `[MEASURED]`؛ بیش از ۲ هم‌زمانی بهبود aggregate نمی‌دهد → سیاست فعلی ۲×2.25 درست است.
- RAM هر انکود ~۳۱۰MB — سقف 2.5G امن.
- دیسک: ۶۱۲GB آزاد؛ retention ۲۴h + sweep idempotent؛ رزرو پیش از claim با نیاز `size×2.2+5GiB` فعلی حفظ شد (ledger کامل → backlog).
- **ظرفیت کاربر (صادقانه):** registered=هزاران ممکن است؛ محدودکننده واقعی «encode jobs/day» است — با mix فرضی V3 و ۲ worker، ~۵۰–۸۰ انکود روزانه پایدار `[ESTIMATE, PROVISIONAL]`؛ عبور از آن نیازمند worker سوم/host بزرگ‌تر — تصمیم با داده واقعی آینده.

## H. نقشه محصول (ارزش‌محور)

1. **دقت تصمیم** (کاهش انکود بی‌فایده) — بیشترین ارزش/هزینه.
2. **اعتماد کاربر** — progress صادقانه موجود؛ اضافه: وضعیت تحویل شفاف.
3. **عملیات مالک** — logs explorer (انجام شد)، delivery/unknown monitoring، daily summary.
4. **plans/limits پیشرفته** — فقط در صورت درخواست محصول؛ policy layer واحد (بدون hardcode).
5. **analytics** — بعد از تجمع داده واقعی (jobs الان evidence را ذخیره می‌کنند).

## I. خلاصه پیاده‌سازی این اجرا (تغییرات واقعی)

| فایل | تغییر | دلیل | تست |
|---|---|---|---|
| `archive.deliver_result` | شاخه `sent_unknown` برای Timeout/ConnectionReset/ClientError (به‌جای false-failure یا تلاش روش بعدی) | تلگرام ممکن است عملیات را دریافت کرده باشد؛ retry کورکورانه = دوبله | `test_deliver_result_timeout_returns_sent_unknown` |
| `engine._deliver_to_requesters` / `_deliver_reuse` / `redeliver` | ردیف deliveries با status=`unknown` + شمارنده `deliveries_unknown`؛ skip delivered=TRUE در ابهام؛ redeliver → delivered=TRUE | صداقت حالت + قابلیت redeliver | `test_deliver_to_requesters_records_unknown_state`, `test_redeliver_marks_requester_delivered` |
| `jobqueue._claim_next` | aging (+5/h، cap +15) در ORDER BY | ضد گرسنگی | validate SQL روی DB ایزوله (۴h→اول) |
| `log.py` + `webpanel` | `RingBufferHandler` (maxlen 2000) + `filter_log_entries` + `GET /panel/api/logs` (owner) | logs explorer امن بدون docker access | `test_filter_log_entries_*`, `test_ring_buffer_handler_*` |
| — | deploy: commit `e6d5afa`، build+restart bot، بکاپ pre (`f8f24d17…`) | — | ۲۶۲ passed / 0 failed |

## J. ایده‌های به‌تعویق‌افتاده و رد‌شده

| ایده | طبقه | دلیل |
|---|---|---|
| delivery outbox/`delivery_tasks` کامل | P1 — **به‌تعویق** | بزرگ‌ترین تغییر باقی‌مانده؛ نیازمند migration + تست fault-injection؛ ریسک فعلی با reconciliation دستی مهار شد |
| storage ledger + inode accounting | P1 — به‌تعویق | چک فعلی + margin کافی برای بار فعلی؛ در بار سنگین لازم |
| dedup ادراکی (dHash/aHash) | P1 — به‌تعویق | الزام holdout ≥۶۰۰ negative؛ زیرساخت آمار ساخته نشده |
| ETA per-pool simulator | P2 | مدل throughput فعلی صادقانه و کافی برای مقیاس فعلی |
| panel v4 rewrite کامل | P2 | hardening فعلی کافی؛ rewrite = ریسک بی‌مورد |
| ML برای decision | REJECT | deterministic + telemetry بهتر/ساده‌تر |
| x265 escalation پیش‌فرض | REJECT (فعلاً) | CPU ۲–۳× برای صرفه حاشیه‌ای |
| AV1/hw accel | REJECT | سخت‌افزار/compat ندارد |
| two-pass | REJECT | زمان ۲× بدون منفعت معنادار |
| stream-copy برای همه | REJECT | خلاف هدف کاهش حجم |
| microservices / RabbitMQ / Celery | REJECT | PostgreSQL queue کافی؛ هزینه عملیاتی نا justif |

## K. ریسک‌های باقی‌مانده

1. **delivery sent_unknown** بدون reconciliation خودکار — اقدام: پایش `deliveries status='unknown'` در پنل + redeliver دستی (مستند).
2. **ظرفیت encode** با رشد کاربران — مانیتور jobs/day؛ آستانه: اگر صف روزانه drain نمی‌شود → worker سوم/host بزرگ‌تر.
3. **duration_state ستون** هنوز schema-level نیست (رفع نمایشی کامل شد) — در migration بعدی.
4. وابستگی session پنل به RAM — ری‌استارت bot لاگین‌ها را می‌بندد.
5. benchmark واقعی (محتوای درسی واقعی + VMAF) انجام نشده — اعداد `[PROVISIONAL]`.

## L. ارزیابی نهایی مهندسی (صادقانه)

- **بار تولیدی فعلی:** آماده و پایدار — چرخه کامل با داده واقعی مالک تأیید شد؛ بدون خطای تکرارشونده.
- **هم‌زمانی بیشتر (۲–۳ انکود):** آماده از نظر نرم‌افزار (claim اتمیک، tuner بدون overcommit)؛ سقف واقعی با benchmark تعیین شود.
- **هزاران کاربر ثبت‌نامی:** از نظر DB/UX مشکلی نیست؛ محدودکننده، ظرفیت انکود روزانه است — با mix فعلی ~۵۰–۹۰ انکود/day روی همین سرور `[ESTIMATE]`.
- **workload بسیار بزرگ‌تر:** نیازمند worker/host دوم + scheduler جدا؛ معماری فعلی این گذار را بدون بازطراحی پشتیبانی می‌کند (claim اتمیک + slots env-محور).

## M. نقشه راه اولویت‌دار

| افق | اقدام | معیار اتمام |
|---|---|---|
| **فوری** | پایش `deliveries unknown` + smoke تعاملی مالک | صفر unknown معلق؛ تایید مالک روی چرخه ویدیو |
| **چرخه بعدی** | delivery outbox (`delivery_tasks`+attempts+reconciliation)؛ session در DB | duplicate=صفر در fault-injection؛ restart بدون logout |
| **میان‌مدت** | storage ledger + ادراکی dedup با گیت آماری؛ benchmark محتوای واقعی | precision≥99.5% holdout؛ throughput مستند |
| **بلندمدت** | scheduler چند-سروری؛ panel v4؛ analytics تصمیم | drain بدون از‌دست‌رفتن؛ کاهش انکود بی‌فایده ≥ ۲۰٪ |

---

**جمع‌بندی صادقانه:** ایده‌هایVision کم‌ارزش یا پرریسک رد/به‌تعویق افتادند؛ چهار بهبود واقعی پیاده، تست (۲۶۲ passed) و روی تولید deploy شد؛ هیچ داده‌ای از دست نرفت و هیچ secret افشا نشد.

**هیچ سرویس تولیدی متوقف یا داده‌ای تخریب نشد؛ فقط تغییرات این release روی branch `stabilization-20261114` commit و deploy شد.**