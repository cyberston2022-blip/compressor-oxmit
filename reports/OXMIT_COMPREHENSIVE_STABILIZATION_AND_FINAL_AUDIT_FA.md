# گزارش جامع پایدارسازی، پیاده‌سازی معماری، Audit لاگ و Release تأییدشده — Oxmit

> **سند:** MEGA TASK 06 — گزارش نهایی و یگانه خروجی
> **تاریخ:** 2026-11-14 · **محیط فعال:** Ohio `13.58.69.178` (Static IP جدید — قبلاً 18.222.98.81)
> **کد قبلی:** `1699d98` · **کد جدید (deploy شده):** `afecaad` روی branch `stabilization-20261114`
> **وضعیت:** ✅ release با موفقیت build، deploy، راستی‌آزمایی شد و در حال سرویس‌دهی است
> **برچسب‌ها:** `[MEASURED]` `[SOURCE-VERIFIED]` `[PROPOSED]` `[PROVISIONAL]` `[UNVERIFIED]`

---

## A. خلاصه مدیریتی

| پرسش | پاسخ |
|---|---|
| Audit کامل انجام شد؟ | ✅ تولید فعلی + لاگ‌های همه ۷ کانتینر از لحظه deployment |
| باگ‌های واقعی رفع شد؟ | ✅ **۶ اصلاح کد + ۱ اصلاح عملیاتی** (بخش D) — همه با تست رگرسیون |
| پیاده‌سازی معماری؟ | ✅ هسته W-F/W-I/W-K/W-M پیاده شد (بخش E)؛ موارد سنگین‌تر با دلیل مستند به «باقی‌مانده» رفت (§N) |
| تست‌ها؟ | ✅ **۲۵۵ passed / 7 skipped / 0 failed** روی کد دیپلوی‌شده |
| Deploy به Ohio؟ | ✅ branch `stabilization-20261114` → commit `afecaad` → rebuild → restart → healthz سبز |
| Ohio تنها poller؟ | ✅ بله؛ سرور قدیم intact و غیر-polling |
| داده تولیدی سالم؟ | ✅ بکاپ pre-deploy با SHA-256؛ صفر عملیات تخریبی؛ صفر از دست رفتن داده |
| **noline-ending bug** | ⚠️ کشف و **رفع** شد (کامیت اول CRLF بود → amend به LF؛ متون پیام بدون CR تأیید شد) |

**کشف ستاره‌ی این release:** باگ P0 واقعی تولید — فایل‌های دانلودی Local Bot API با mode `0600` و دایرکتوری‌ها `0750` ساخته می‌شوند؛ با `WORKERS_READ_BOTAPI=true`، ورکر (uid 1000) نمی‌توانست منبع را بخواند و **ویدیوی واقعی مالک fail می‌شد**. رفع: chmod در `_stage_source` + اعتبارسنجی زنده با همان job.

---

## B. زیرساخت فعلی `[MEASURED]`

| | OLD (rollback، intact) | **NEW Ohio (فعال)** |
|---|---|---|
| IP | 77.113.85.253 | **13.58.69.178** (Static IP جدید — 18.222.98.81 قبلی منقضی) |
| CPU/RAM/دیسک | ۲ vCPU / 3.7GB / 77GB | ۸ vCPU / 15GB / 619GB (۶۱۲GB آزاد) |
| کد | `1699d98` | **`afecaad`** branch `stabilization-20261114` |
| کانتینرها | bot=exited، بقیه up | همه up؛ bot healthy؛ workerها drain-loop طبیعی (restart=39+، by-design) |
| Worker CPU | 1.8 (host-limited) | **nano=2.25e9 هر کدام = ۴٫۵ کل** (tuner تأیید) |

DB فعلی: users=9، jobs 12 completed/7 failed، archive=6، deliveries=8، audit=54، **۰ job فعال**؛ app_config: access_mode/limits/archive_channel_id/paused=false.

## C. Audit کامل لاگ

**بازه:** از deployment (2026-11-13 23:50 UTC) تا 2026-11-14 01:35 — همه ۷ کانتینر + journal.

| کانتینر | ERROR | Traceback | WARNING | ارزیابی |
|---|---:|---:|---:|---|
| oxmit-bot | **۱** | 0 | 0 | ERROR واقعی = باگ P0 (بخش D-1) |
| worker-1/2 | ۳/۰ | 0 | ۱۹۶×۲ | Java native-access warnings هر restart — noise انتظاری |
| encore-web / pg / redis / botapi | ۰ | ۰ | ≤۸ | سالم |

**Error register:**

| ID | خطا | تکرار | ریشه | رفع | تست رگرسیون | نتیجه |
|---|---|---|---|---|---|---|
| E1 | `ffprobe: Permission denied` روی staging symlink → **fail job واقعی مالک** (۷۲۰MB) | ۲ (دو requeue) | bot-api فایل‌ها را 0600 و dirs را 0750 می‌سازد؛ worker uid=1000 denied — روی قدیم dirs دستی 777 بود | FIX-1: chmod در `_stage_source` (فایل 0644 + dirs 0777 فقط داخل درخت botapi) | `test_stage_source_symlink_grants_worker_read`, `test_make_botapi_readable_*` | ✅ همان job پس از deploy کامل شد |
| E2 | `private_mode` روی submitهای test | — | OWNER_ONLY=true + tg غیرادمین | تنظیم فاز تست (نه باگ کد) | — | بسته |
| E3 | `rate_limited` با وجود env جدید | ۴ | **seed یک‌باره `app_config.limits`** — env بعدی بی‌اثر (طراحی) | مستند + رویه عملیاتی (گزارش مهاجرت) | — | مستند |
| E4 | tuner overcommit (4.5×۳=13.5) | طراحی | tuner یک مقدار را به همه replicaها می‌نوشت | FIX-6: `cores_for` per-replica clamp | `test_cores_for_three_replicas_no_overcommit` | ✅ nano=2.25×۲ |
| E5 | callback «query is too old» (قدیم) | ۱ | فشار دکمه حین پنجره تست | transient — نه باگ | — | بسته |
| E6 | **worker restart loop (۳۹+ restart)** | مستمر | طراحی drain-queue Encore (exit 0) | نه باگ؛ noise طراحی‌شده | — | مستند |
| E7 | duration `00:00:00` در خلاصه reuse | مستمر (تاریخی) | `or 0` روی duration NULL + probe خالی مسیر reuse | FIX-4 | `test_summary_text_unknown_duration`, `test_build_caption_unknown_duration` | ✅ |
| E8 | `m_w` KeyError در تست (artifact) | — | stub تستی | تست اصلاح شد | — | بسته |

**Post-fix evidence:** ۱۲۰–۳۰۰ ثانیه لاگ پس از deploy → ۰ ERROR، ۰ Traceback، healthz سبز، ۰ تعارض polling.

## D. Bug-fix register (کد تغییر یافته)

| # | فایل/تابع | تغییر | تست |
|---|---|---|---|
| FIX-1 | `engine._stage_source` + جدید `_make_botapi_readable` | chmod فایل 0644 + dirs والد 0777 پیش از symlink؛ فقط داخل درخت botapi؛ fallback copy حفظ | `test_stage_source_symlink_grants_worker_read` + ۲ تست |
| FIX-2 | `panel/security.py`, `webpanel.py`, `dashboard.py`, `panel/bot_manager.py`, `engine.is_owner`, `handlers/support.py` | حذف هاردکد `829999317` و fallback «اولین ادمین»؛ **fail-closed** بدون `OWNER_TELEGRAM_ID` | `test_is_owner_session_fail_closed*`, `test_engine_is_owner_has_no_first_admin_fallback`, `test_support_owner_routing_is_config_only` |
| FIX-3 | `webpanel.py` (imports/routes Milestone-2)، حذف `panel/superadmin.py` + `test_panel_superadmin.py`، `dashboard_page.py` (۵ nav-tab)، `panel/bot_manager.py` (allowlist config) | حذف shell خام/SQL خام/env-raw/file-delete/FFmpeg-customizer بی‌اثر؛ config API فقط کلیدهای مجاز `{paused, access_mode, global_thumb_path}` | deploy-verify: همه `/panel/api/super/*` → **404**؛ `test_get_bot_config_filters_private_keys`, `test_update_bot_config_rejects_unknown_keys` |
| FIX-4 | `engine._summary_text`, `archive.build_caption`, `_deliver_to_requesters` (وراثت probe خروجی در reuse) | مدت نامعلوم → «نامشخص» (fa) / "unknown" (en)؛ هرگز ۰؛ مسیر reuse مدت را از probe media_asset خروجی می‌گیرد | `test_summary_text_*`, `test_build_caption_unknown_duration` |
| FIX-5 | `engine._reuse_archive` بازنویسی + جدید `_deliver_reuse` | تحویل reuse **async** (spawn) — حلقه نام‌گذاری چندفایلی هرگز روی ارسال آرشیو قفل نمی‌شود؛ bookkeeping sync؛ `deliver_cached_offer` acceptance را در لحظه پذیرش می‌شمارد | `test_reuse_archive_returns_without_delivering_inline`, `test_deliver_cached_offer_accepts_and_bumps` |
| FIX-6 | `resources.cores_for` (امضای جدید: active, **pool**, replicas, floor) + `tune()` | cap = pool/replicas → overcommit ساختاراً ناممکن؛ `WORKER_CPU_MULTI` فقط advisory؛ production: pool=4.5/۲=2.25 ✓ | `test_cores_for_*` (۴ تست شامل regression ۳×۴٫۵) |
| FIX-7 | `edu480.predict_guard` (جدید، pure) + `jobqueue._run_pipeline` + `config` (ENCODE_PREDICT_GUARD/PREDICT_NO_GAIN_RATIO) | guard قطعی bpp: اگر حد پایین خروجی پیش‌بینی ≥ ۹۸٪ منبع → `deliver_source` (بدون CPU)؛ evidence در `jobs.decision` | `test_predict_guard_*` (۴) |
| FIX-8 | `.env` Ohio | `PANEL_PUBLIC_URL=https://13.58.69.178:8090/panel` (IP static جدید) | curl panel 200 |

**تست‌های جدید:** `tests/test_stabilization.py` (۲۲ تست) + بازنویسی `tests/test_resources.py`.

## E. پیاده‌سازی معماری (مطابق V3 — بخش اجراشده)

- **W-F duration:** نمایش سه‌حالتی بدون schema change — `duration_state` ستون به «باقی‌مانده» موکول شد چون باگ کاربر-رو (`or 0`) کامل در لایه display رفع شد و وراثت probe در مسیر reuse اصلاح شد (تصمیم: رفع ریشه نمایشی کم‌ریسک‌تر از migration در این release).
- **W-I تصمیم‌گیری:** لایه guard قطعی (بدون ML/تاریخچه — cold-start safe: فقط skip موارد «مطمئن بی‌فایده») + evidence در `jobs.decision`؛ کلاس‌های کامل C1–C8 و مدل interval به «باقی‌مانده» (نیازمند کالیبراسیون داده واقعی).
- **W-K intake:** مسیر reuse دیگر هرگز intake را بلاک نمی‌کند (FIX-5) — هسته الزام §۱۳؛ FSM/user_seq کامل به «باقی‌مانده» (رفتار فعلی intake_drafts ترتیب created_at دارد و برای حجم فعلی کافی است).
- **W-M tuner:** واحد pool/per-replica + تست رگرسیون benchmark (بخش D/FIX-6).
- **W-G/H/J/L (deliver-outbox، storage ledger، dedup ادراکی، ETA per-pool):** **پیاده نشد** — دلیل: حجم تغییر بالا + ریسک تولید؛ سناریوی واقعی `sent_unknown` در این release رخ داد و با رویه reconciliation دستی حل شد (§K) — پیاده‌سازی کامل آن در فاز بعدی اولویت اول است.

## F. امنیت

- Owner: تک‌منبع env؛ fail-closed؛ بدون hardcode/first-admin؛ هویت تولیدی حفظ شد (چاپ نشد).
- پنل: terminal/SQL/env/files/ffmpeg حذف (تأیید 404)؛ config API allowlist؛ container restart/logs فقط owner+CSRF+audit (باقی مانده از قبل).
- Secretها: صفر secret در پاسخ API؛ .env هرگز چاپ نشد؛ logs redact حفظ شد.
- Sessions/CSRF/rate-limit: منطق موجود حفظ و با تست پوشش داده شد؛ session در DB به «باقی‌مانده».
- گزارش V3 (owner=829999317 hardcode) → **رفع شده**؛ diff شامل حذف کامل است.

## G. دیتابیس

- **هیچ migration اجرا نشد** — همه تغییرات این release بدون تغییر schema (decision TEXT از مهاجرت 015 موجود بود). بکاپ pre-deploy: `/opt/oxmit-stabilization-backup-20261114/oxmit_pre_stabilization.dump` (63,056B، SHA `32855466…`، `pg_restore -l` ✓ ۱۳۷ TOC) + `env.backup`.
- integrity: شمارنده‌ها پس از deploy مطابق؛ reconcile خودکار boot: `jobs_failed: 7→6` (اصلاح صحیح شمارش بعد از تبدیل job قبلی به completed) ✓.

## H. کارایی `[MEASURED]`

- tuner مؤثر: `nano=2250000000` ×۲ = ۴٫۵ کل (بدون overcommit) — لاگ: `active=0 cores=2.25 containers=2`
- مرجع aggregate fps (سینتتیک، concurrency=2): ۱۰۴٫۹–۱۳۳٫۳ — benchmark سنگین در ساعت پیک اجرا نشد (الزام §۱۷٫۴)
- **مورد واقعی:** ویدیوی مالک (۷۲۰MB، ۱۱۵دقیقه، 720p ~۸۳۶kbps) → guard: خروجی پیش‌بینی ۶۷۷MB–۱٫۳GB ≥ ۹۸٪ منبع → **DELIVER_SOURCE در ~۴۰ ثانیه** به‌جای fail قبلی/انکود ~۴۵ دقیقه بی‌فایده ✓ — اولین اثبات عملی ارزش guard

## I. تست‌ها

- Baseline قبل از تغییر: اجرا نشد به‌صورت جدا (تغییرات هم‌زمان اعمال شد)؛ پس از تغییر: **۲۵۵ passed / 7 skipped / 0 failed** روی **کد دیپلوی‌شده** (`/opt/oxmit`) با venv ایزوله Ohio.
- تست‌های جدید: ۲۲ (test_stabilization) + بازنویسی test_resources (۶ تست tuner) + به‌روزرسانی test_cache_offer (معنای جدید cache_accepted).
- حذف‌شده: `test_panel_superadmin.py` (endpointها حذف شدند؛ پوشش: assert 404 در deploy-verify).
- **NOT TESTED:** smoke تعاملی تلگرام چندفایلی/پیشرفت/تحویل چندگیرنده — نیازمند کلاینت مالک (دستورالعمل در گزارش مهاجرت §۲۰).

## J. Deployment

- قبلی: `1699d98` → جدید: **`afecaad`** (branch `stabilization-20261114`) — زمان deploy: ~01:19–01:35 UTC 2026-11-14
- ترتیب: backup → stop bot → build → up bot → verify (healthz/404/panel/logs) → **requeue job مالک → تحویل موفق**
- نکته: کامیت اولیه CRLF بود → amend به LF (متون پیام بدون CR تأیید: `texts-with-CR: NONE`)
- دو restart bot انجام شد (deploy + tuner-env) — بین آن‌ها یک تحویل در-flight cancel شد → `sent_unknown` → با redeliver کنترل‌شده حل شد (§K) — درس عملی: از این پس restart فقط وقتی queue/delivery خالی (مستند در §K)

## K. Recovery و rollback

- بکاپ‌ها: migration-backup (قدیم+جدید) + pre-stabilization (جدید) — همه SHA-256 با manifest.
- سرور قدیم: intact، bot=exited، هیچ migration روی آن اجرا نشد.
- **incident مستند:** حین deploy، تحویل job مالک حین `docker compose up -d bot` (tuner env) cancel شد → `job_requesters.delivered=false` بدون ردیف deliveries (sent_unknown واقعی) → **reconciliation**: `engine.redeliver` از داخل کانتینر → `True file_id` + ردیف deliveries ثبت شد. ریسک دوبله: send اولیه ممکن است رسیده باشد (نامعلوم) — مالک می‌تواند کپی اضافه را حذف کند.
- درس: deployها باید بین تحویل‌ها انجام شوند؛ V3 delivery_tasks/outbox این شکاف را بسته می‌کند (باقی‌مانده §N).

## L. جدول وضعیت نهایی

| معیار | وضعیت |
|---|---|
| خطای بحرانی تکرارشونده بی‌توضیح | PASS (صفر؛ E1 رفع) |
| worker restart loop | WARNING (طراحی drain — مستند) |
| tuner overcommit | PASS (2.25×۲، تست رگرسیون) |
| poller دوم | PASS (فقط Ohio) |
| درصد جعلی progress | PASS (کد تغییر نکرده؛ honest) |
| duration=00:00:00 | PASS (رفع + تست) |
| قفل naming توسط delivery | PASS (FIX-5 + تست) |
| duplicate logical delivery | WARNING (outbox کامل → §N؛ incident با reconciliation حل شد) |
| blind retry پس از send مبهم | PASS (retry خودکار وجود ندارد؛ redeliver دستی) |
| حذف منبع قبل از archive confirm | PASS (منطق فعلی حفظ) |
| race رزرو storage | WARNING (چک فعلی + margin؛ ledger → §N) |
| hardcode owner | PASS (حذف + fail-closed) |
| shell/SQL endpoint | PASS (حذف؛ 404 تأیید) |
| secret در پنل | PASS (allowlist config) |
| reset کانفیگ روی restart | PASS (seed فقط بار اول؛ مستند) |
| اکشن‌های شکسته پنل | PASS (اکشن‌های fake حذف) |
| ناسازگاری DB | PASS (reconcile + counts) |
| تست‌های deterministic مسیرهای جدید | PASS (۲۲ تست جدید) |
| migration امن | PASS (بدون migration) |
| فقط یک poller | PASS |
| قدیم intact | PASS |
| smoke تعاملی تلگرام | **NOT TESTED** (نیازمند کلاینت مالک) |

## M. خلاصه دستورات/تغییرات (بدون secret)

Ohio: audit scripts (۷ کانتینر) · `chmod 777` dirs botapi (عملیاتی موقت تا کد) · requeue `bd4c109e` (۳×) · بکاپ pre-deploy + sha256 · `sed PANEL_PUBLIC_URL/WORKER_CPU_SINGLE` · `git checkout -b stabilization-20261114; git add -A bot tests; commit` (×۲: ابتدایی + amend LF) · `compose build bot; up -d --force-recreate bot` · verify (healthz/404×۵/panel 200/logs/NanoCPUs/getChat قبلی) · `engine.redeliver` via exec · `pytest` ×۴ (venv /tmp/oxtest).
Local: ویرایش ۱۳ فایل (فهرست §D) + ۲ فایل تست + حذف ۲ فایل.

## N. باقی‌مانده (واقعاً باز)

1. **Delivery outbox/`delivery_tasks`** با `sent_unknown` + reconciliation خودکار (V3 §20) — incident این هفته اهمیتش را اثبات کرد.
2. **Storage ledger** (`job_storage`) با هویت inode (V3 §16).
3. **dedup ادراکی** coarse-to-fine + گیت آماری (V3 §11-13) — exact/provenance مسیر فعال و ایمن.
4. **ETA per-pool simulator** + نمونه‌های per-stage (V3 §13).
5. **FSM intake با user_seq** + delivery_tasks برای چندفایل سنگین (V3 §11).
6. **panel v4 consolidation** (ادغام ۴ نسل API؛ broadcast یکپارچه؛ session در DB؛ duration_state ستون).
7. **Smoke تعاملی تلگرام** توسط مالک (چندفایل + تحویل چندگیرنده).
8. پاک‌سازی پس از تأیید مالک: `oxmit_test_backup_20261114`، بکاپ‌های قدیمی، سرور قدیم (≥۷ روز).

---

**جمع‌بندی:** سیستم اکنون روی Ohio با commit `afecaad` فعال و پایدار است؛ ۶ باگ واقعی (شامل ۱ باگ P0 تولیدی که همان روز توسط مالک فعال شد) رفع و با تست رگرسیون پوشش داده شدند؛ سطح امنیتی پنل ارتقا یافت؛ و هیچ داده تولیدی از دست نرفت.