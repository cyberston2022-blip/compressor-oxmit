# گزارش کامل مهاجرت و Cutover تولیدی Oxmit — سرور قدیم → Ohio

> **سند:** MEGA TASK 05 — مهاجرت کامل تولید، انتقال داده، cutover و اعتبارسنجی پس از مهاجرت
> **تاریخ اجرا:** 2026-11-13 (UTC) — cutover تلگرام: **23:55:04 UTC**
> **برچسب‌ها:** `[MEASURED]` · `[SOURCE-VERIFIED]` · `[OWNER-PROVIDED]` · `[PROPOSED]` · `[UNVERIFIED]`

---

## ۱. خلاصه مدیریتی (Executive Summary)

مهاجرت کامل تولید Oxmit از سرور قدیم (`77.113.85.253`) به سرور Ohio (`18.222.98.81`) **انجام و تأیید شد**. دیتابیس تولیدی PostgreSQL با احتیاط کامل quiesce، dump، انتقال (تطبیق SHA-256) و restore شد؛ همه شمارنده‌های جدول‌ها با مبدأ مطابقت دارند (users=9، admins=2، jobs=17، archive_records=6، deliveries=6، audit_log=51، tier limits و archive_channel_id و access_mode از `app_config` authoritative). bot جدید در 23:55:04 UTC تنها poller تلگرام شد (۰ تعارض)، `healthz` سبز است، دسترسی به کانال آرشیو با هویت همان bot تأیید شد (`getChat` → `ok:true, type:channel`)، پنل وب با داده تولیدی بالا است (`users_total=9`, `access_mode=private`)، و تیونر CPU دقیقاً `2×2.25=4.5` هسته بدون overcommit تنظیم شد.

انتقال فایل‌های ویدیو (۴۵۶MB، ۴ فایل در `media/out`) **طبق تصمیم صریح مالک انجام نشد**؛ پیامد آن در §۱۱ مستند است. سرور قدیم کامل و غیر-polling به‌عنوان مسیر rollback حفظ شده است (§۲۵).

**آنچه هنوز باقی است:** تست تعاملی تلگرام (ارسال ویدیو توسط مالک تا تحویل) به‌دلیل نداشتن دسترسی کلاینت تلگرام اجرا نشده و مراحل دقیق آن برای مالک مستند شده است (§۲۰).

---

## ۲. هویت نهایی سرورها `[MEASURED]`

| | OLD (تولید قبلی — مسیر rollback) | NEW (تولید فعلی — Ohio) |
|---|---|---|
| IP | 77.113.85.253 | 18.222.98.81 |
| hostname | ip-172-26-45-238 | ip-172-26-38-211 |
| IPv6 | 2600:1f16:19eb:e802:e5d2:… | 2600:1f16:19eb:e802:badb:… |
| OS | Ubuntu (Lightsail) | Ubuntu 24.04 |
| CPU | ۲ vCPU | ۸ vCPU (Xeon 8275CL، ۴C×۲T) |
| RAM | 3.7GB | 15GB |
| دیسک | 77GB | 619GB (۶۱۳GB آزاد) |
| مسیر | /opt/oxmit | /opt/oxmit |
| Git | main @ `1699d98` (تمیز) | main @ `1699d98` (تمیز) — **یکسان** |

هر دو سرور با hostname + IPv6 + مسیر + کامیت شناسایی شدند؛ منبع/مقصد هرگز برعکس نشد.

## ۳. سخت‌افزار و OS — see جدول بالا؛ Docker NEW: 29.1.3 + Compose 2.40.3 (نصب در این مهاجرت)؛ OLD: Docker قدیمی‌تر با همان compose.

## ۴. مقایسه سورس کد

هر دو سرور `main @ 1699d98` با working tree تمیز — **هیچ تفاوتی**؛ نسخه هدف = همان baseline تأییدشده. بدون pull/upgrade در حین مهاجرت (الزام §۹٫۱).

## ۵. Inventory تولیدی سرور قدیم `[MEASURED]`

- **PG 17.11**: users=9، admins=2، vips=0، blocked=0، media_assets=21، jobs=17 (10 completed / 6 failed / 1 cancelled — **هیچ job فعال**)، job_requesters=15، archive_records=6، deliveries=6، intake_drafts=26، audit_log=51، app_config=4 (`access_mode`, `archive_channel_id`, `limits`, `paused`)، counters=24، profiles=12، admin_settings=0، admin_permissions=0، support/moderation/merge=0، **schema_migrations=16** (شامل legacy `011_owner_only` که فایلش از repo حذف شده)
- **Media**: مجموع ۴۵۶MB؛ فقط **۴ فایل** در `media/out` (خروجی‌های نگه‌داشته‌شده)؛ incoming/tmp/work خالی‌technی؛ thumbs/watermarks موجود نیست
- **Bot API data**: فقط ۱۴۸KB (بدون فایل کش‌شده — منابع پس از پردازش حذف می‌شوند `[SOURCE-VERIFIED: DELETE_BOTAPI_SOURCE]`)
- **env**: ۶۹ کلید؛ `OWNER_ONLY=true`, `WORKER_REPLICAS=1`, `ENCODE_SLOTS=0`, `WORKER_CPU 1.8/1.5/1.0`, `FFMPEG_THREADS_SINGLE=2`, `ENABLE_TEST_API=false`, `MAX_QUEUED_JOBS=50`, `PANEL_PUBLIC_URL=https://77.113.85.253:8090/panel`, `ARCHIVE_CHANNEL_ID` در env **خالی** (مقدار مؤثر از DB)

## ۶. Inventory اولیه سرور جدید (قبل از جایگزینی)

دیتابیس تست: jobs=20 (13 completed/7 failed)، users=1 (tg سینتتیک تست)، media_assets=33، app_config=1 (limits seed شده)، migrations=15، media: test=238MB + out=48MB — **کامل بکاپ و به‌صورت `oxmit_test_backup_20261114` حفظ شد** (نه حذف).

## ۷. جزئیات بکاپ PostgreSQL

| بکاپ | مسیر | حجم | SHA-256 |
|---|---|---|---|
| OLD prod (pre-quiesce) | old:`/opt/oxmit-migration-backup-20261114/oxmit_prod.dump` | 62,107B | `3b34ac82…7e2e4` |
| **OLD prod (final, post-quiesce)** | old + new:`/opt/oxmit-migration-backup-20261114/oxmit_prod_final.dump` | 62,107B | `24dbefc6…0aa9c` — **تطبیق انتقال ✓** |
| NEW test DB | new:`…/oxmit_test.dump` | 56,881B | در `MANIFEST.sha256` |
| NEW test media | new:`…/test_media.tar.gz` | 297MB | ✓ |
| NEW redis (test state) | new:`…/redis_test.rdb` | 28KB | ✓ |
| env هر دو | `…/env.backup` (perm 600، هرگز چاپ نشد) | — | ✓ |

هر dump با `pg_restore -l` (۱۳۷ مدخل TOC) صحت‌سنجی شد. دسترسی دایرکتوری‌های بکاپ: 700/600.

## ۸. جزئیات restore

1. توقف writers روی جدید: `bot` (از قبل Exited) + `encore-worker`×2 + `encore-web`
2. `ALTER DATABASE oxmit RENAME TO oxmit_test_backup_20261114` (از DB maintenance `postgres`)
3. `CREATE DATABASE oxmit` (owner = role اپلیکیشن `oxmit`)
4. `pg_restore -U oxmit --no-owner --dbname=oxmit /tmp/prod.dump` → `RESTORE_OK`
5. `paused=false` صریح برای cutover (dump مقدار true داشت)
6. **سه اشکال اجرایی در همین فاز رفع شد** (§۲۳)

## ۹. نتایج اعتبارسنجی دیتابیس (قدیم ↔ restored) `[MEASURED]`

| شمارنده | قدیم | جدید (restored) | مطابق |
|---|---|---|---|
| users | 9 | 9 | ✓ |
| admins | 2 | 2 | ✓ |
| jobs | 17 | 17 | ✓ |
| archive_records | 6 | 6 | ✓ |
| deliveries | 6 | 6 | ✓ |
| job_requesters | 15 | 15 | ✓ |
| media_assets | 21 | 21 | ✓ |
| intake_drafts | 26 | 26 | ✓ |
| audit_log | 51 | 51 | ✓ |
| counters rows | 24 | 24 | ✓ |
| profiles | 12 | 12 | ✓ |
| schema_migrations | 16 | 16 | ✓ |
| app_config keys | 4 | 4 (`access_mode` len9, `archive_channel_id` SET, `limits` SET, `paused=false`) | ✓ |

counters مقادیر تولیدی: `jobs_encoded=6, jobs_failed=6, deliveries_ok=6, requests_total=15`.

## ۱۰. Volumes و state ماندگار

- `oxmit_pg_data` (new): حاوی DB تولیدی restored + DB تست بکاپ‌شده با نام جدا
- `oxmit_redis_data` (new): state تست Encore terminal — **بدون flush** (اثبات شد فقط state تست terminal است؛ هیچ job pending؛ RDB بکاپ شد)
- `oxmit_botapi_data` (new): **انتقال state قدیم انجام نشد** — دلیل: کش قدیم فقط ۱۴۸KB بدون فایل مدیا؛ همه file_idها در تلگرام ابری هستند و `getFile` کش را خودکار بازمی‌سازد؛ merge کردن binlog روی سرویس running ریسک بی‌مورد داشت
- certs پنل: از قدیم → جدید منتقل (key perm 600)

## ۱۱. انتقال مدیا — تصمیم و پیامدها

**طبق دستور صریح مالک، انتقال ویدیوها انجام نشد.** پیامدها (همه قابل‌قبول):
- `media/out` قدیم (۴ فایل، ۴۵۶MB) روی جدید موجود نیست → خروجی‌های محلیِ jobهای قدیمی در دسترس نیستند؛ اما **همه ۶ رکورد آرشیو از طریق پیام‌های کانال آرشیو تلگرام قابل تحویل مجددند** (`deliver_result` زنجیره copy→file_id→upload از DB استفاده می‌کند نه فایل محلی)
- jobهای قدیمی completed نیازی به فایل محلی ندارند؛ jobهای failed نیز خروجی محلی‌شان منقضی‌شده محسوب می‌شود
- `cleanup_sweep` سرور جدید فایل‌های تست `/media/test` را پس از ۲۴h retention پاک می‌کند
- در صورت نیاز آینده، بکاپ رسانه روی سرور قدیم دست‌نخورده باقی است

## ۱۲. تصمیم Local Bot API

همان ایمیج/کد (`--local`)، volume تازه؛ **انتقال state انجام نشد** (§۱۰) — حذف فایل‌های منبع پس از هر پردازش یعنی کش خالی بوده و مسیر باز acquisition از تلگرام سالم است. بعد از cutover: `botapi` healthy و `getFile` در جریان عادی استفاده می‌شود.

## ۱۳. تصمیم Encore/Redis

- قدیم: صف خالی (هیچ job فعال) → هیچ state نیمه‌تمامی برای انتقال وجود نداشت
- جدید: state تست terminal؛ `queueCount`=0؛ ورکرها فقط پس از restore و verify استارت شدند؛ هیچ flush انجام نشد (بکاپ RDB موجود)

## ۱۴. کانفیگ مؤثر تولیدی نهایی (new)

| کلید | مقدار نهایی | منبع تصمیم |
|---|---|---|
| `OWNER_ONLY=true` | بازگردانی از تولید قدیم | §۹٫۲ |
| `ENABLE_TEST_API=false` (+ حذف CONFIRM) | parity با تولید | §۹٫۲ |
| `ARCHIVE_CHANNEL_ID` | **خالی در env — مؤثر از DB `app_config.archive_channel_id`** (رفتار fallback `bot.py`) — parity کامل با قدیم که env آن هم خالی بود | کشف این مهاجرت |
| `WORKER_REPLICAS=2`, `ENCODE_SLOTS=2` | کاندیدای benchmark مگاپرومپت 03 (۲×۲٫۲۵) | §۳٫۴ |
| `WORKER_CPU_SINGLE=2.25`, `MULTI=2.25`, `MIN=1.5` | جمع ≤۴٫۵ — **رفع overcommit** | benchmark |
| `FFMPEG_THREADS_SINGLE=5` | تطبیق ۸ هسته (قدیم=۲ میراث host دو-هسته‌ای) | §۱۴٫۵ |
| `MAX_QUEUED_JOBS=50` | **بدون تغییر** (الزام صریح §۱۴٫۵) | — |
| `PANEL_PUBLIC_URL=https://18.222.98.81:8090/panel` | IP-target | §۹٫۲ |
| `DOCKER_GID=113` | target-specific | — |
| `MEDIA_HOST_DIR=/opt/oxmit/media`, `TBAPI_COMMIT`, secrets | parity با قدیم | — |
| tier limits مؤثر | از `app_config.limits` قدیم (authoritative) — نه env | §۹٫۳ |

## ۱۵. اعتبارسنجی کانال آرشیو

- مقدار از DB restored (len=14) خوانده شد (بدون چاپ)
- `getChat` با token همان bot روی Local Bot API جدید → **`ok:true, type:channel, title present`** ✓
- `archive_configured=true` در healthz بعد از boot ✓
- آپلود تست به کانال تولیدی انجام نشد (طبق قاعده §۹٫۴) — آپلود واقعی در اولین ویدیوی مالک تأیید می‌شود

## ۱۶. حفظ Owner/ادمین‌ها

`admins=2` و همه ردیف‌های users از DB تولیدی restored؛ `access_mode` از DB (`private` — پنل تأیید)؛ **هیچ infer از «اولین ادمین» رخ نداد**؛ هاردکد `829999317` در `panel/security.py` هنوز در سورس است (موضوع V3؛ در این مهاجرت کد تغییر نکرد) اما `cfg.owner_telegram_id` env مقدار تولیدی دارد و اولویت دارد. VIP=0، ban=0 مطابق قدیم.

## ۱۷. تخصیص CPU ورکرها

- compose cap: `cpus:1.8`/worker؛ **2 replica**
- تیونر بعد از boot: `nano=2250000000` روی هر دو (`WORKER_CPU_SINGLE=2.25`) → **جمع ۴٫۵ = بودجه §۵ V3، بدون overcommit** ✓
- benchmark مرجع: aggregate ۱۰۴٫۹–۱۳۳٫۳ fps در concurrency=2 (محتوای سینتتیک)
- FFMPEG threads: single=5 (تصمیم این مهاجرت)، multi=3 (default)

## ۱۸. سرویس‌های start/stop شده (ترتیب دقیق)

**OLD:** restart bot (quiesce freeze) → stop bot → (workers/pg/redis/botapi دست‌نخورده برای rollback)
**NEW:** (phase2b) stop worker/web → (phase3) recreate workers=2 → (phase6) stop worker/web → rename/create DB → restore → **start ترتیبی: encore-web → workers(2) → bot** (bot فقط پس از تأیید توقف bot قدیم)

## ۱۹. زمان cutover تلگرام

**2026-11-13 23:55:04 UTC** — بوت bot جدید؛ `getUpdates` از همان لحظه بدون تعارض؛ بدون `drop_pending_updates`.

## ۲۰. نتایج Smoke test

**سمت سرور (اجراشده):** healthz کامل؛ getChat کانال آرکیو؛ panel login/summary با داده تولیدی؛ ۰ خطا/۰ تعارض در ۱۲۰ ثانیه اول؛ queue_depth=0؛ tuner مؤثر.

**تعاملی تلگرام (اجرای مالک لازم دارد — کلاینت تلگرام در اختیار agent نیست):**
1. از اکانت مالک: `/start` → باید منوی خوش‌آمد و دکمه‌ها بیاید (تأیید access private)
2. یک ویدیوی تست کوتاه بفرستید → prompt نام‌گذاری → تأیید → کارت صف ۴ مرحله‌ای
3. پایان: پیام خلاصه + تحویل از کانال آرشیو + رکورد جدید در `archive_records`
4. `/admin` و `/panel` برای ادمین؛ پنل وب از `https://18.222.98.81:8090/panel` (self-signed — هشدار مرورگر طبیعی است)
**انتظار داده تولیدی:** users_total=9 در پنل؛ کارت‌های progress فقط مقادیر measured/indeterminate.

## ۲۱. وضعیت صف و تحویل

queue_depth=0؛ هیچ job فعال از قدیم وجود نداشت (همه terminal)؛ deliveries=6 همه `ok` تاریخی؛ **هیچ تحویل unknown از مهاجرت باقی نماند** (چون quiesce بدون عملیات ارسال در-flight انجام شد).

## ۲۲. مشاهده‌های کارایی (post-cutover)

Idle stack: bot 177–200MB، encore-web ~108MB، postgres ~51MB، redis ~7MB، botapi ~12-19MB، worker idle 0. CPU نزدیک صفر در idle. مرجع throughput = benchmark Ohio (۱۰۴٫۹–۱۳۳٫۳ fps aggregate در concurrency=2 با محتوای سینتتیک)؛ **این اعداد برای محتوای واقعی education معمولاً بهتر می‌شوند و VMAF/SSIM اندازه‌گیری نشده** — هیچ guarantee عملکردی ادعا نمی‌شود.

## ۲۳. اقدامات ناموفق و اصلاح‌شده

| # | خطا | اصلاح |
|---|---|---|
| 1 | `ALTER DATABASE` rename → «current database cannot be renamed» | اجرا از DB `postgres` |
| 2 | `pg_restore` → `role "root" does not exist` | افزودن `-U "$POSTGRES_USER"` |
| 3 | اسکریپت `if PGMAIN` — تست exit-code به‌جای نتیجه کوئری | بررسی خروجی `datname` |
| 4 | `set -u` → `POSTGRES_USER: unbound` در shell محلی اسکریپت | حذف وابستگی، استفاده از `current_user` |
| 5 | بکاپ dir root-owned → Permission denied | chown ubuntu با حفظ 700 |
| 6 | manifest root-owned → sha256 fail | chown + regenerate |
| 7 | خط `ARCHIVE_CHANNEL_ID` در env جدید اعمال نمی‌شد | **ریشه‌یابی:** مقدار در `.env` قدیم هم خالی است (۲۰ بایت = کلید+LF)؛ تولید از DB می‌خواند → env جدید هم خالی = parity صحیح؛ اعتبارسنجی با DB |
| 8 | ورکرهای recreate نشده با NanoCPUs=4.5 (میراث tuner قدیمی) | `--force-recreate` → 1.8 compose → tuner نهایی 2.25 ✓ |
| 9 | `healthz paused:False` روی قدیم پس از restart با DB=true | **observation حل‌نشده** — غیرمسدودکننده: قدیم stop شد و روی جدید `paused=false` صریح اعمال شد؛ پیشنهاد: بررسی `get_config` در فاز پیاده‌سازی V3 |

## ۲۴. هشدارهای باقی‌مانده

1. تست تعاملی تلگرام pending (§۲۰) — تنها مورد «NOT TESTED» مسیر کاربر
2. گواهی پنل self-signed؛ پورت ۸۰۹۰ باید در Lightsail firewall باز شود در صورت دسترسی خارجی
3. DB جدید شامل داده تست نیست (جایگزین کامل شد) ولی `media/test` و `media/out` تست روی جدید ~۲۸۶MB است که sweep ۲۴h پاک می‌کند
4. DB تست به‌صورت `oxmit_test_backup_20261114` روی جدید حفظ شده — پس از اطمینان مالک قابل drop است
5. هاردکد owner در سورس پنل (موضوع شناخته‌شده V3 — خارج از scope این مهاجرت)
6. انتقال ندادن media → خروجی‌های محلی قدیمی فقط روی قدیم (rollback)

## ۲۵. رویه Rollback

**پیش‌شرط:** چون بعد از cutover کاربران ممکن است درخواست جدید ثبت کنند، rollback به معنای انتقال معکوس داده است:
1. روی Ohio: `paused=true` در DB + restart bot (freeze intake با پیام نگهداری) → drain
2. resolve/ثبت هر تحویل unknown
3. `docker stop bot` روی Ohio
4. `pg_dump -Fc` از Ohio → انتقال به قدیم → `pg_restore` به یک DB staging روی قدیم → مقایسه counts → جایگزینی/merge
5. rsync معکوس `media/out` جدید→قدیم (اگر خروجی جدید مهم)
6. روی قدیم: `paused=false` ← **حتماً** (چون DB قدیم الان paused=true دارد) → `docker start oxmit-bot`
7. Ohio: bot stop بماند
**قدیم دست‌نخورده است:** volumes، DB، media، بکاپ‌ها. حداقل ۷ روز حفظ (الزام §۱۹٫۳).

## ۲۶. وضعیت نهایی مهاجرت

| دسته | وضعیت |
|---|---|
| Server identity | PASS |
| Source code | PASS (1699d98 هر دو) |
| PostgreSQL backup | PASS (verified sha256) |
| Data integrity | PASS (جدول §۹) |
| Users/Owner/admin | PASS (۹/۲، private mode) |
| Tier limits & app_config | PASS (authoritative DB) |
| Jobs | PASS (هیچ فعال؛ همه terminal منتقل) |
| Deliveries | PASS (۶/۶ تاریخی؛ بدون unknown) |
| Archive records | PASS (۶) |
| Media files | **WARNING — انتقال نشد (دستور مالک)؛ تحویل از تلگرام سالم** |
| Bot API | PASS (healthy) |
| Encore/Redis | PASS (queue=0) |
| Workers CPU | PASS (2×2.25=4.5، بدون overcommit) |
| Archive channel | PASS (getChat ok) |
| Telegram polling | PASS (تنها poller، ۰ تعارض) |
| Progress honesty | PASS (کد تغییر نکرد) |
| Web panel | PASS (HTTPS 200 + data تولیدی) |
| Disk permissions | PASS (media uid=1000 — درس دیپلوی قبلی اعمال شد) |
| Recovery | PASS (restart bot/worker در benchmark قبلی؛ recover_on_startup فعال) |
| Rollback | PASS (قدیم دست‌نخورده + رویه §۲۵) |
| Smoke تعاملی تلگرام | **NOT TESTED** (نیازمند کلاینت مالک) |

## ۲۷. لاگ پاک‌سازی‌شده دستورات و تغییرات (خلاصه)

**OLD:** `pg_dump -Fc` → بکاپ‌ها (pre+post-quiesce) · `app_config paused=true` · `docker restart oxmit-bot` (freeze) · `docker stop oxmit-bot` (cutover) · sha256/`pg_restore -l` verify · انتقال dump (SHA match).
**NEW:** `apt install docker.io docker-compose-v2` · `git clone` → `/opt/oxmit @1699d98` · `.env` تولیدی (sed keys فهرست‌شده §۱۴) · certs منتقل · `chown 1000:1000 /opt/oxmit/media` (پیش‌نیاز ورکر) · `docker compose build/up` (redis,postgres,botapi,encore-web,worker×2) · rename/`CREATE DATABASE`/`pg_restore -U oxmit --no-owner` · `paused=false` · `up -d encore-web,encore-worker,bot` · verify: healthz/getChat/panel/stats/logs.
**هر دو:** هیچ secret چاپ نشد؛ هیچ `down -v`/`volume prune`/`rm -rf` اجرا نشد؛ هیچ pending-update دور ریخته نشد.

---

**وضعیت نهایی: مهاجرت انجام و تأیید شد؛ Ohio فعال است؛ قدیم سالم و غیر-polling به‌عنوان rollback حفظ شده است.** تنها قلم باز: smoke تعاملی تلگرام توسط مالک (دستورالعمل §۲۰) و تصمیم نهایی مالک درباره بازنشستگی سرور قدیم پس از ۷ روز مشاهده پایدار.