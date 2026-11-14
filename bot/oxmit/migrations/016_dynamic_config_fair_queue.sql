-- Migration 016: Dynamic Runtime Configuration & Multi-Tier Fair Queue Scheduler

CREATE TABLE IF NOT EXISTS system_settings (
    key             TEXT PRIMARY KEY,
    value           JSONB NOT NULL,
    value_type      TEXT NOT NULL DEFAULT 'str',
    title_fa        TEXT NOT NULL,
    description_fa  TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed default settings
INSERT INTO system_settings (key, value, value_type, title_fa, description_fa)
VALUES
    ('accepting_new_jobs', 'true'::jsonb, 'bool', 'وضعیت پذیرش ویدیوی جدید', 'روشن/خاموش کردن دریافت فایل جدید توسط ربات'),
    ('max_global_queue_size', '500'::jsonb, 'int', 'حداکثر ظرفیت کل صف انتظار', 'ظرفیت کل صف انتظار پردازش'),
    ('max_concurrent_jobs_per_user', '3'::jsonb, 'int', 'سقف مجاز ویدیوی همزمان هر کاربر', 'حداکثر تعداد کارهای در حال انتظار یا پردازش یک کاربر عادی'),
    ('max_concurrent_jobs_vip', '10'::jsonb, 'int', 'سقف مجاز ویدیوی کاربران ویژه (VIP)', 'سقف اختصاصی صف برای کاربران دارای وضعیت ویژه'),
    ('max_file_size_mb', '2000'::jsonb, 'int', 'حداکثر حجم مجاز فایل ورودی (MB)', 'حداکثر حجم فایل ویدیویی ارسالی مجاز'),
    ('active_encoding_workers', '2'::jsonb, 'int', 'تعداد ورکرهای همزمان انکودینگ', 'تعداد تسک‌های همزمان انکودینگ ویدیو'),
    ('active_download_workers', '4'::jsonb, 'int', 'تعداد دانلودهای همزمان از تلگرام', 'حداکثر دانلودهای همزمان فایل از سرور تلگرام'),
    ('active_upload_workers', '4'::jsonb, 'int', 'تعداد آپلودهای همزمان به تلگرام', 'حداکثر آپلودهای همزمان فایل به سرور تلگرام'),
    ('ffmpeg_threads_per_worker', '0'::jsonb, 'int', 'تعداد هسته CPU برای هر ورکر FFmpeg', 'تعداد هسته اختصاصی پردازش هر ورکر (0 = خودکار)'),
    ('queue_scheduling_mode', '"fair_round_robin"'::jsonb, 'string', 'الگوریتم عدالت و زمان‌بندی صف', 'الگوریتم زمان‌بندی صف (fair_round_robin, strict_fifo, weighted_fair, size_aware_fair)'),
    ('wfq_time_penalty_seconds', '300'::jsonb, 'int', 'جریمه زمانی هر ویدیوی اضافه در صف (ثانیه)', 'جریمه زمانی مجازی برای الگوریتم WFQ'),
    ('admin_queue_bypass', 'false'::jsonb, 'bool', 'اولویت ویژه ادمین‌ها در صف', 'بای‌پس صف برای ادمین‌ها (پیش‌فرض خاموش جهت عدالت و تست)'),
    ('progress_update_interval_sec', '4'::jsonb, 'int', 'بازه آپدیت پیام پیشرفت تلگرام (ثانیه)', 'فاصله زمانی بین ویرایش پیام‌های پیشرفت در تلگرام'),
    ('progress_bar_length', '12'::jsonb, 'int', 'تعداد خانه‌های نوار پیشرفت', 'تعداد کاراکترهای نوار پیشرفت گرافیکی'),
    ('auto_retry_failed_jobs', '1'::jsonb, 'int', 'تعداد تلاش مجدد خودکار هنگام خطا', 'تعداد دفعات تلاش مجدد خودکار در صورت بروز خطای موقت')
ON CONFLICT (key) DO NOTHING;

-- Extend jobs table for detailed lifecycle metrics & fairness scheduling
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS stage_progress DOUBLE PRECISION DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS processed_bytes BIGINT DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS total_bytes BIGINT DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS current_speed_bps DOUBLE PRECISION DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS eta_seconds DOUBLE PRECISION DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS initial_queue_pos INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS priority_boost INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS is_admin_job BOOLEAN DEFAULT FALSE;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS engine_info TEXT DEFAULT '';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS telegram_status_msg_id BIGINT DEFAULT NULL;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ DEFAULT NULL;

-- Custom per-user queue limits in users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_queue_limit INTEGER DEFAULT NULL;

-- Indexes for high-throughput fair queue queries
CREATE INDEX IF NOT EXISTS idx_jobs_fair_sched ON jobs (status, requester_tg_id, enqueued_at) WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS idx_jobs_priority_boost ON jobs (priority_boost DESC) WHERE status = 'queued';
