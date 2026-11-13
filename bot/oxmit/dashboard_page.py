"""Single-file HTML for the comprehensive Oxmit Super-Admin Web Panel.
"""

PAGE = r"""<!doctype html><html dir="rtl" lang="fa"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oxmit Super-Admin — مرکز کنترل فوق پیشرفته</title>
<style>
:root {
  --bg: #0a0d14;
  --card: #121622;
  --card-hover: #171d2c;
  --panel: #161b29;
  --border: #22293a;
  --border-focus: #e8562a;
  --ink: #f0f3fa;
  --ink-mut: #8b95aa;
  --ink-dim: #5a6478;
  --acc: #e8562a;
  --acc-glow: rgba(232, 86, 42, 0.25);
  --acc-gradient: linear-gradient(135deg, #ff7a45, #e8562a);
  --blue: #3b82f6;
  --blue-glow: rgba(59, 130, 246, 0.2);
  --green: #10b981;
  --green-glow: rgba(16, 185, 129, 0.2);
  --red: #ef4444;
  --red-glow: rgba(239, 68, 68, 0.2);
  --amber: #f59e0b;
  --amber-glow: rgba(245, 158, 11, 0.2);
  --purple: #8b5cf6;
  --shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
  --glass: rgba(18, 22, 34, 0.75);
}

* { box-sizing: border-box; margin: 0; padding: 0; }
[hidden] { display: none !important; }
body {
  font-family: Vazirmatn, "Segoe UI", Tahoma, system-ui, sans-serif;
  background: var(--bg);
  color: var(--ink);
  font-size: 13.5px;
  line-height: 1.6;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* Glassmorphism Header */
header {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  padding: 12px 24px;
  background: var(--glass);
  backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 50;
}
.logo-box {
  display: flex;
  align-items: center;
  gap: 10px;
}
.logo-icon {
  width: 36px;
  height: 36px;
  border-radius: 11px;
  background: var(--acc-gradient);
  box-shadow: 0 0 16px var(--acc-glow);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 900;
  color: #fff;
  font-size: 18px;
}
.logo-text h1 {
  font-size: 16px;
  font-weight: 800;
  letter-spacing: -0.3px;
}
.logo-text small {
  font-size: 11px;
  color: var(--ink-mut);
  display: block;
  margin-top: -3px;
}

.header-badges {
  display: flex;
  align-items: center;
  gap: 8px;
}
.badge {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 99px;
  background: #192030;
  border: 1px solid var(--border);
  color: var(--ink-mut);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.badge.owner {
  background: rgba(232, 86, 42, 0.12);
  border-color: rgba(232, 86, 42, 0.35);
  color: #ff8555;
  font-weight: 700;
}
.badge.online {
  background: rgba(16, 185, 129, 0.12);
  border-color: rgba(16, 185, 129, 0.35);
  color: #34d399;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 8px var(--green);
  animation: pulse 2s infinite;
}
.dot.off {
  background: var(--red);
  box-shadow: 0 0 8px var(--red);
  animation: none;
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.85); }
}

.sp { flex: 1; }

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
button, a.btn {
  border: 1px solid var(--border);
  background: #181e2b;
  color: var(--ink);
  padding: 6px 14px;
  border-radius: 9px;
  font-size: 12.5px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.18s ease;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  text-decoration: none;
}
button:hover, a.btn:hover {
  background: #202738;
  border-color: #2e374d;
}
button.pri, a.btn.pri {
  background: var(--acc-gradient);
  border-color: transparent;
  color: #fff;
  font-weight: 600;
  box-shadow: 0 2px 10px var(--acc-glow);
}
button.pri:hover, a.btn.pri:hover {
  filter: brightness(1.1);
}
button.danger, a.btn.danger {
  background: rgba(239, 68, 68, 0.15);
  border-color: rgba(239, 68, 68, 0.35);
  color: #f87171;
}
button.danger:hover, a.btn.danger:hover {
  background: rgba(239, 68, 68, 0.25);
}
button.success {
  background: rgba(16, 185, 129, 0.15);
  border-color: rgba(16, 185, 129, 0.35);
  color: #34d399;
}

/* Nav Tabs bar */
.nav-wrap {
  background: #10141f;
  border-bottom: 1px solid var(--border);
  padding: 4px 24px 0;
  display: flex;
  gap: 4px;
  overflow-x: auto;
  scrollbar-width: none;
}
.nav-wrap::-webkit-scrollbar { display: none; }
.nav-tab {
  padding: 10px 15px;
  border: 0;
  background: transparent;
  color: var(--ink-mut);
  font-size: 13px;
  font-weight: 500;
  border-radius: 8px 8px 0 0;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 7px;
  transition: all 0.15s ease;
}
.nav-tab:hover {
  color: var(--ink);
  background: rgba(255, 255, 255, 0.03);
}
.nav-tab.active {
  color: var(--acc);
  font-weight: 700;
  border-bottom-color: var(--acc);
  background: rgba(232, 86, 42, 0.06);
}
.nav-tab .badge-count {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 99px;
  background: #1f2738;
  color: var(--ink-mut);
}
.nav-tab.active .badge-count {
  background: var(--acc);
  color: #fff;
}

/* Main Content Area */
main {
  flex: 1;
  padding: 20px 24px;
  max-width: 1650px;
  width: 100%;
  margin: 0 auto;
}

/* KPI Ribbon */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}
.kpi-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 13px;
  padding: 13px 16px;
  box-shadow: var(--shadow);
  position: relative;
  overflow: hidden;
  transition: transform 0.18s, border-color 0.18s;
}
.kpi-card:hover {
  transform: translateY(-2px);
  border-color: #2e374d;
}
.kpi-card::before {
  content: "";
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 2px;
  background: var(--card-accent, transparent);
}
.kpi-card.acc { --card-accent: var(--acc); }
.kpi-card.blue { --card-accent: var(--blue); }
.kpi-card.green { --card-accent: var(--green); }
.kpi-card.red { --card-accent: var(--red); }
.kpi-card.amber { --card-accent: var(--amber); }
.kpi-card.purple { --card-accent: var(--purple); }

.kpi-card small {
  font-size: 11.5px;
  color: var(--ink-mut);
  display: block;
  margin-bottom: 4px;
}
.kpi-card .val {
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.5px;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}
.kpi-card .sub {
  font-size: 10.5px;
  color: var(--ink-dim);
  margin-top: 3px;
}

/* Cards & Sections */
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 18px;
  box-shadow: var(--shadow);
  margin-bottom: 18px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.card-head h2 {
  font-size: 15px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
}
.card-head .actions {
  display: flex;
  gap: 8px;
}

/* Tables */
.table-wrap {
  overflow-x: auto;
  border-radius: 10px;
  border: 1px solid var(--border);
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
  text-align: right;
}
th {
  background: #161c2a;
  color: var(--ink-mut);
  font-weight: 600;
  padding: 10px 14px;
  white-space: nowrap;
  border-bottom: 1px solid var(--border);
}
td {
  padding: 10px 14px;
  border-bottom: 1px solid #1a2030;
  vertical-align: middle;
}
tr:last-child td { border-bottom: 0; }
tr.clickable { cursor: pointer; transition: background 0.15s; }
tr.clickable:hover td { background: var(--card-hover); }

.mono {
  font-family: ui-monospace, Consolas, monospace;
  direction: ltr;
  unicode-bidi: isolate;
}
.pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 99px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.p-active { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }
.p-queue { background: rgba(245, 158, 11, 0.15); color: #fbbf24; }
.p-done { background: rgba(16, 185, 129, 0.15); color: #34d399; }
.p-fail { background: rgba(239, 68, 68, 0.15); color: #f87171; }
.p-cancel { background: rgba(100, 116, 139, 0.15); color: #94a3b8; }

/* Progress bar */
.prog-bar {
  height: 6px;
  border-radius: 99px;
  background: #1f2738;
  overflow: hidden;
  width: 90px;
  display: inline-block;
  vertical-align: middle;
  margin-left: 8px;
}
.prog-bar span {
  display: block;
  height: 100%;
  background: var(--acc-gradient);
  border-radius: 99px;
}

/* Forms & Inputs */
input, select, textarea {
  background: #171c2b;
  border: 1px solid var(--border);
  color: var(--ink);
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.18s;
}
input:focus, select:focus, textarea:focus {
  border-color: var(--border-focus);
}

/* Grid layout */
.grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.grid-3 {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px;
}
@media (max-width: 960px) {
  .grid-2 { grid-template-columns: 1fr; }
}

/* Terminal Console UI */
.terminal-box {
  background: #06080d;
  border: 1px solid #1c2233;
  border-radius: 12px;
  font-family: "JetBrains Mono", ui-monospace, Consolas, monospace;
  font-size: 12.5px;
  direction: ltr;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  height: 480px;
}
.terminal-bar {
  background: #10141f;
  padding: 8px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #1c2233;
  font-size: 11.5px;
  color: #7d889e;
}
.terminal-dots {
  display: flex;
  gap: 6px;
}
.terminal-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.terminal-dot.r { background: #ef4444; }
.terminal-dot.y { background: #f59e0b; }
.terminal-dot.g { background: #10b981; }
.terminal-output {
  flex: 1;
  padding: 14px;
  overflow-y: auto;
  color: #d1d5db;
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.5;
}
.terminal-output .out-stdout { color: #10b981; }
.terminal-output .out-stderr { color: #f87171; }
.terminal-output .out-cmd { color: #60a5fa; font-weight: 600; margin-top: 8px; }
.terminal-input-bar {
  display: flex;
  background: #0d111a;
  border-top: 1px solid #1c2233;
  padding: 8px 12px;
  gap: 8px;
  align-items: center;
}
.terminal-prompt {
  color: #e8562a;
  font-weight: 700;
  user-select: none;
}
.terminal-input {
  flex: 1;
  background: transparent;
  border: 0;
  color: #fff;
  font-family: inherit;
  font-size: 13px;
  outline: none;
}
.terminal-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.chip {
  background: #161c2a;
  border: 1px solid var(--border);
  color: #93c5fd;
  font-size: 11px;
  padding: 3px 9px;
  border-radius: 6px;
  cursor: pointer;
  font-family: ui-monospace, Consolas, monospace;
}
.chip:hover {
  background: #1f273a;
  border-color: #3b82f6;
}

/* Modals & Toasts */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 16px;
}
.modal-box {
  background: #141824;
  border: 1px solid #2a3348;
  border-radius: 16px;
  width: min(580px, 100%);
  max-height: 85vh;
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0,0,0,0.6);
  padding: 24px;
}
.modal-box h3 {
  font-size: 16px;
  font-weight: 800;
  margin-bottom: 12px;
  color: var(--ink);
}
.toast-container {
  position: fixed;
  bottom: 24px;
  left: 24px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 200;
}
.toast {
  background: #192030;
  border: 1px solid var(--border);
  color: var(--ink);
  padding: 10px 16px;
  border-radius: 10px;
  font-size: 12.5px;
  box-shadow: var(--shadow);
  display: flex;
  align-items: center;
  gap: 10px;
  animation: slideUp 0.25s ease;
}
.toast.success { border-color: rgba(16, 185, 129, 0.4); background: #0f2320; }
.toast.error { border-color: rgba(239, 68, 68, 0.4); background: #281216; }
@keyframes slideUp {
  from { transform: translateY(20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

/* Container Cards */
.container-card {
  background: #141824;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.container-card.healthy { border-color: rgba(16, 185, 129, 0.3); }
.container-card.unhealthy { border-color: rgba(239, 68, 68, 0.3); }
.container-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.container-name {
  font-weight: 700;
  font-size: 13.5px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.container-actions {
  display: flex;
  gap: 6px;
}

/* Slider Controls */
.slider-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
}
.slider-label {
  display: flex;
  justify-content: space-between;
  font-size: 12.5px;
  color: var(--ink-mut);
}
.slider-label b { color: var(--ink); }
input[type="range"] {
  accent-color: var(--acc);
}

/* Empty state */
.empty {
  text-align: center;
  padding: 40px 16px;
  color: var(--ink-mut);
}
</style>
</head>
<body>

<!-- Header -->
<header>
  <div class="logo-box">
    <div class="logo-icon">O</div>
    <div class="logo-text">
      <h1>مرکز مدیریت Oxmit</h1>
      <small>Super-Admin Control Suite v3.2</small>
    </div>
  </div>

  <div class="header-badges">
    <span class="badge owner" id="badge-role">👑 مالک ربات (@Oxmit)</span>
    <span class="badge" id="badge-access">🌐 عمومی</span>
    <span class="badge" id="badge-intake">▶️ پذیرش فعال</span>
    <span class="badge online" id="badge-ws"><span class="dot" id="dot-ws"></span> لایو</span>
  </div>

  <span class="sp"></span>

  <div class="header-actions">
    <button id="btn-toggle-access" title="تغییر دسترسی عمومی/خصوصی">🔒/🌐 تغییر دسترسی</button>
    <button id="btn-toggle-intake" title="توقف یا ادامه پذیرش ربات">⏸/▶️ پذیرش</button>
    <button class="danger" id="btn-cancel-all" title="لغو اضطراری تمام کارهای صف">🔴 لغو اضطراری همه</button>
    <a class="btn" href="/panel/legacy" target="_blank" title="مشاهده نسخه ساده">داشبورد قدیم</a>
    <button class="danger" id="btn-logout">خروج</button>
  </div>
</header>

<!-- Navigation Tabs -->
<nav class="nav-wrap" id="nav-tabs">
  <button class="nav-tab active" data-tab="overview">📊 داشبورد و آمار</button>
  <button class="nav-tab" data-tab="tasks">⚡ صف و انکودینگ <span class="badge-count" id="tab-cnt-active">0</span></button>
  <button class="nav-tab" data-tab="docker">🐳 کانتینرهای داکر</button>
  <button class="nav-tab" data-tab="bot_users">🤖 مدیریت ربات و کاربران</button>
  <button class="nav-tab" data-tab="terminal">🖥️ وب‌ترمینال زنده</button>
  <button class="nav-tab" data-tab="sql_console">🗄️ کنسول SQL و دیتابیس</button>
  <button class="nav-tab" data-tab="files">📁 فایل‌منیجر سرور</button>
  <button class="nav-tab" data-tab="ffmpeg">🎬 تنظیمات انکودر FFmpeg</button>
  <button class="nav-tab" data-tab="env_editor">⚙️ متغیرهای محیطی .env</button>
  <button class="nav-tab" data-tab="audit">📋 لاگ‌های امنیتی (Audit)</button>
</nav>

<!-- Main Container -->
<main>
  <!-- KPI Ribbon (Always visible or contextual) -->
  <section class="kpi-grid" id="kpi-grid">
    <div class="kpi-card acc">
      <small>کارهای در حال فشرده‌سازی</small>
      <div class="val" id="kpi-active">0</div>
      <div class="sub" id="kpi-active-sub">ورکرها در حال پردازش</div>
    </div>
    <div class="kpi-card amber">
      <small>صف انتظار انکود</small>
      <div class="val" id="kpi-queue">0</div>
      <div class="sub">در انتظار نوبت پردازش</div>
    </div>
    <div class="kpi-card green">
      <small>فشرده‌شده امروز</small>
      <div class="val" id="kpi-completed">0</div>
      <div class="sub">تکمیل موفق ویدیوها</div>
    </div>
    <div class="kpi-card red">
      <small>ناموفق / خطادار</small>
      <div class="val" id="kpi-failed">0</div>
      <div class="sub">مشکلات انکود یا منبع</div>
    </div>
    <div class="kpi-card blue">
      <small>فضای آزاد هارد سرور</small>
      <div class="val" id="kpi-disk">—</div>
      <div class="sub" id="kpi-disk-sub">در پوشه /media و روت</div>
    </div>
    <div class="kpi-card purple">
      <small>مصرف رم سرور (RAM)</small>
      <div class="val" id="kpi-ram">—</div>
      <div class="sub" id="kpi-ram-sub">از مجموع حافظه اصلی</div>
    </div>
    <div class="kpi-card">
      <small>مصرف پردازنده (CPU)</small>
      <div class="val" id="kpi-cpu">—</div>
      <div class="sub" id="kpi-uptime">آپ‌تایم: —</div>
    </div>
  </section>

  <!-- View 1: Overview Dashboard -->
  <section id="view-overview" class="view-panel">
    <div class="grid-2">
      <div class="card">
        <div class="card-head">
          <h2>📊 وضعیت سرویس‌های زیرساخت</h2>
          <button class="btn" id="btn-refresh-svc">بروزرسانی</button>
        </div>
        <div id="overview-svc-list">
          <div class="empty">در حال دریافت وضعیت سرویس‌ها...</div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <h2>⚡ پردازش‌های جاری سرور</h2>
          <span class="badge" id="active-tasks-badge">0 تسک</span>
        </div>
        <div id="overview-active-tasks">
          <div class="empty">هیچ کاری در حال پردازش نیست</div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h2>📈 آخرین رخدادهای سیستم و فعالیت‌ها</h2>
      </div>
      <div class="table-wrap">
        <table id="table-recent-events">
          <thead>
            <tr>
              <th>زمان</th>
              <th>عامل</th>
              <th>اکشن</th>
              <th>هدف</th>
              <th>جزئیات</th>
            </tr>
          </thead>
          <tbody>
            <tr><td colspan="5" class="empty">در حال بارگذاری...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <!-- View 2: Queue & Transcoding Tasks -->
  <section id="view-tasks" class="view-panel" hidden>
    <div class="card">
      <div class="card-head">
        <h2>⚡ مدیریت کارهای فشرده‌سازی ویدیو</h2>
        <div class="actions">
          <select id="task-filter-status">
            <option value="active">در حال پردازش (Active)</option>
            <option value="queue">در صف انتظار (Queued)</option>
            <option value="completed">تکمیل‌شده (Completed)</option>
            <option value="failed">ناموفق (Failed)</option>
            <option value="cancelled">لغو شده (Cancelled)</option>
          </select>
          <input type="text" id="task-filter-q" placeholder="شناسه کار یا نام فایل..." style="width:200px">
          <button class="btn pri" id="btn-task-refresh">جستجو و فیلتر</button>
        </div>
      </div>
      <div class="table-wrap">
        <table id="table-tasks">
          <thead>
            <tr>
              <th>شناسه کار</th>
              <th>نام فایل</th>
              <th>کاربر</th>
              <th>وضعیت / درصد</th>
              <th>کیفیت</th>
              <th>حجم اولیه / خروجی</th>
              <th>زمان ایجاد</th>
              <th>عملیات</th>
            </tr>
          </thead>
          <tbody>
            <tr><td colspan="8" class="empty">در حال دریافت داده‌های صف...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <!-- View 3: Docker Containers -->
  <section id="view-docker" class="view-panel" hidden>
    <div class="card">
      <div class="card-head">
        <h2>🐳 کانتینرهای داکر سرویس Oxmit (/var/run/docker.sock)</h2>
        <div class="actions">
          <button class="btn pri" id="btn-refresh-docker">بروزرسانی وضعیت</button>
        </div>
      </div>
      <div class="grid-3" id="docker-cards-grid">
        <div class="empty">در حال واکشی کانتینرهای داکر...</div>
      </div>
    </div>
  </section>

  <!-- View 4: Bot & Users -->
  <section id="view-bot_users" class="view-panel" hidden>
    <div class="card">
      <div class="card-head">
        <h2>🤖 مدیریت کاربران ربات تلگرام</h2>
        <div class="actions">
          <input type="text" id="user-search-input" placeholder="آیدی عددی یا @username...">
          <button class="btn pri" id="btn-user-search">جستجو</button>
          <button class="btn success" id="btn-open-broadcast">📢 ارسال پیام همگانی</button>
        </div>
      </div>
      <div class="table-wrap">
        <table id="table-users">
          <thead>
            <tr>
              <th>آیدی تلگرام</th>
              <th>نام کاربری</th>
              <th>سهمیه روزانه</th>
              <th>مصرف امروز</th>
              <th>وضعیت حساب</th>
              <th>آخرین فعالیت</th>
              <th>عملیات</th>
            </tr>
          </thead>
          <tbody>
            <tr><td colspan="7" class="empty">برای مشاهده کاربران جستجو کنید یا کلید اعمال را بزنید...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <!-- View 5: Web Terminal -->
  <section id="view-terminal" class="view-panel" hidden>
    <div class="card">
      <div class="card-head">
        <h2>🖥️ وب‌ترمینال زنده سرور لینوکس (Linux Shell & Docker Exec)</h2>
        <div class="actions">
          <button class="btn" id="btn-term-clear">پاک‌کردن کنسول</button>
        </div>
      </div>

      <div class="terminal-chips">
        <span class="chip" data-cmd="docker ps">docker ps</span>
        <span class="chip" data-cmd="docker stats --no-stream">docker stats</span>
        <span class="chip" data-cmd="df -h">df -h</span>
        <span class="chip" data-cmd="free -m">free -m</span>
        <span class="chip" data-cmd="uptime">uptime</span>
        <span class="chip" data-cmd="ls -la /opt/oxmit">ls -la /opt/oxmit</span>
        <span class="chip" data-cmd="tail -n 40 /opt/oxmit/docker-compose.yml">cat docker-compose</span>
      </div>

      <div class="terminal-box">
        <div class="terminal-bar">
          <div class="terminal-dots">
            <span class="terminal-dot r"></span>
            <span class="terminal-dot y"></span>
            <span class="terminal-dot g"></span>
          </div>
          <div>root@77.113.85.253 — bash</div>
          <div id="term-status">آماده</div>
        </div>
        <div class="terminal-output" id="term-output">
خوش آمدید! این یک کنسول وب زنده برای مدیریت سرور است.
برای اجرای دستور در کادر زیر تایپ کرده و Enter را فشار دهید یا روی چیپ‌های بالای کنسول کلیک کنید.
        </div>
        <div class="terminal-input-bar">
          <span class="terminal-prompt">$</span>
          <input type="text" class="terminal-input" id="term-input" placeholder="دستور مورد نظر خود را وارد کنید (مثال: docker ps)..." autocomplete="off">
          <button class="btn pri" id="btn-term-send">اجرا</button>
        </div>
      </div>
    </div>
  </section>

  <!-- View 6: PostgreSQL SQL Console & Backup -->
  <section id="view-sql_console" class="view-panel" hidden>
    <div class="grid-2">
      <div class="card">
        <div class="card-head">
          <h2>🗄️ کنسول کوئری SQL (PostgreSQL)</h2>
          <button class="btn success" id="btn-db-backup">📦 بکاپ‌گیری فوری (pg_dump)</button>
        </div>
        <div style="margin-bottom:10px">
          <textarea id="sql-query-input" rows="6" style="width:100%;font-family:ui-monospace,monospace;font-size:13px;direction:ltr" placeholder="SELECT * FROM tasks ORDER BY created_at DESC LIMIT 20;"></textarea>
        </div>
        <div style="display:flex;gap:8px;justify-content:flex-end">
          <button class="btn" id="btn-sql-snippet-tasks">تسک‌های اخیر</button>
          <button class="btn" id="btn-sql-snippet-users">کاربران پرمصرف</button>
          <button class="btn pri" id="btn-sql-run">▶️ اجرای کوئری</button>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <h2>📊 جداول پایگاه داده و حجم ذخیره‌سازی</h2>
          <button class="btn" id="btn-refresh-tables">بروزرسانی</button>
        </div>
        <div class="table-wrap" style="max-height:280px;overflow-y:auto">
          <table id="table-db-tables">
            <thead>
              <tr>
                <th>نام جدول</th>
                <th>حجم روی دیسک</th>
              </tr>
            </thead>
            <tbody>
              <tr><td colspan="2" class="empty">در حال واکشی اطلاعات دیتابیس...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h2>خروجی کوئری</h2>
        <span class="badge" id="sql-result-count">۰ ردیف</span>
      </div>
      <div class="table-wrap" id="sql-result-wrap" style="max-height:350px;overflow-y:auto">
        <div class="empty">کوئری هنوز اجرا نشده است.</div>
      </div>
    </div>
  </section>

  <!-- View 7: Server File Explorer -->
  <section id="view-files" class="view-panel" hidden>
    <div class="card">
      <div class="card-head">
        <h2>📁 مرورگر فایل سرور (/opt/oxmit و /media)</h2>
        <div class="actions">
          <input type="text" id="files-current-path" value="/opt/oxmit" style="width:280px;direction:ltr">
          <button class="btn pri" id="btn-files-go">مرور مسیر</button>
          <button class="btn" id="btn-files-media">📁 پوشه /media</button>
        </div>
      </div>
      <div class="table-wrap">
        <table id="table-files">
          <thead>
            <tr>
              <th>نام فایل / دایرکتوری</th>
              <th>نوع</th>
              <th>حجم</th>
              <th>آخرین تغییر</th>
              <th>عملیات</th>
            </tr>
          </thead>
          <tbody>
            <tr><td colspan="5" class="empty">در حال خواندن فایل‌ها...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <!-- View 8: FFmpeg Encoder Customizer -->
  <section id="view-ffmpeg" class="view-panel" hidden>
    <div class="card" style="max-width:850px">
      <div class="card-head">
        <h2>🎬 تنظیمات سفارشی انکودر FFmpeg (بدون نیاز به ویرایش کد)</h2>
        <button class="btn pri" id="btn-ffmpeg-save">💾 ذخیره و اعمال آنی</button>
      </div>

      <div class="slider-group">
        <div class="slider-label">
          <span>ضریب فشرده‌سازی ویدیو (CRF) - کیفیت بهتر به سمت چپ (18-51):</span>
          <b id="val-ffmpeg-crf">28</b>
        </div>
        <input type="range" id="ffmpeg-crf" min="18" max="51" value="28">
      </div>

      <div class="grid-2">
        <div class="slider-group">
          <label style="color:var(--ink-mut);font-size:12px;margin-bottom:4px;display:block">پریست سرعت انکود (Preset):</label>
          <select id="ffmpeg-preset">
            <option value="ultrafast">ultrafast (سریع‌ترین - حجم بیشتر)</option>
            <option value="superfast">superfast</option>
            <option value="veryfast">veryfast</option>
            <option value="faster">faster</option>
            <option value="fast">fast</option>
            <option value="medium" selected>medium (پیش‌فرض تعادلی)</option>
            <option value="slow">slow (فشرده‌تر)</option>
            <option value="slower">slower</option>
            <option value="veryslow">veryslow (بسیار سنگین)</option>
          </select>
        </div>

        <div class="slider-group">
          <label style="color:var(--ink-mut);font-size:12px;margin-bottom:4px;display:block">کدک ویدیو (Video Codec):</label>
          <select id="ffmpeg-vcodec">
            <option value="libx264" selected>H.264 (libx264) — سازگاری عمومی ۱۰۰٪</option>
            <option value="libx265">H.265 / HEVC (libx265) — فشرده‌سازی فوق‌العاده بالا</option>
            <option value="copy">کپی مستقیم بدون فشرده‌سازی مجدد (copy)</option>
          </select>
        </div>
      </div>

      <div class="grid-2">
        <div class="slider-group">
          <label style="color:var(--ink-mut);font-size:12px;margin-bottom:4px;display:block">سقف رزولوشن (Max Resolution):</label>
          <select id="ffmpeg-res">
            <option value="480">480p (SD)</option>
            <option value="720" selected>720p (HD - پیش‌فرض تلگرام)</option>
            <option value="1080">1080p (Full HD)</option>
            <option value="2160">4K (Original)</option>
          </select>
        </div>

        <div class="slider-group">
          <label style="color:var(--ink-mut);font-size:12px;margin-bottom:4px;display:block">سقف فریم‌ریت (Max FPS):</label>
          <select id="ffmpeg-fps">
            <option value="24">24 FPS</option>
            <option value="30" selected>30 FPS (پیش‌فرض)</option>
            <option value="60">60 FPS</option>
          </select>
        </div>
      </div>

      <div class="slider-group">
        <label style="color:var(--ink-mut);font-size:12px;margin-bottom:4px;display:block">فیلترهای سفارشی اضافی (-vf Arguments):</label>
        <input type="text" id="ffmpeg-extra-vf" placeholder="مثال: unsharp=5:5:1.0:5:5:0.0" style="direction:ltr">
      </div>
    </div>
  </section>

  <!-- View 9: Environment Variables (.env) -->
  <section id="view-env_editor" class="view-panel" hidden>
    <div class="card">
      <div class="card-head">
        <h2>⚙️ ویرایشگر زنده متغیرهای محیطی (/opt/oxmit/.env)</h2>
        <div class="actions">
          <button class="btn" id="btn-env-add">➕ افزودن متغیر</button>
          <button class="btn pri" id="btn-env-save">💾 ذخیره تغییرات .env</button>
        </div>
      </div>
      <p style="color:var(--ink-mut);font-size:12.5px;margin-bottom:14px">
        توجه: پس از ذخیره تغییرات برای متغیرهای هسته، ممکن است نیاز به ری‌استارت کانتینر مربوطه از تب داکر داشته باشید.
      </p>
      <div id="env-vars-container">
        <div class="empty">در حال خواندن فایل .env سرور...</div>
      </div>
    </div>
  </section>

  <!-- View 10: Audit Logs -->
  <section id="view-audit" class="view-panel" hidden>
    <div class="card">
      <div class="card-head">
        <h2>📋 ثبت رخدادها و لاگ‌های امنیتی (Security Audit)</h2>
        <div class="actions">
          <button class="btn pri" id="btn-audit-refresh">بروزرسانی لاگ‌ها</button>
        </div>
      </div>
      <div class="table-wrap">
        <table id="table-audit">
          <thead>
            <tr>
              <th>زمان ثبت</th>
              <th>انجام‌دهنده</th>
              <th>عملیات</th>
              <th>هدف</th>
              <th>جزئیات</th>
              <th>IP منبع</th>
            </tr>
          </thead>
          <tbody>
            <tr><td colspan="6" class="empty">در حال بارگذاری لاگ‌های امنیتی...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</main>

<!-- Log Viewer Modal -->
<div class="modal-overlay" id="modal-logs" hidden>
  <div class="modal-box" style="width:min(880px,96%)">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <h3 id="modal-log-title">📋 لاگ‌های کانتینر</h3>
      <button class="btn" id="btn-close-log-modal">بستن</button>
    </div>
    <div class="terminal-box" style="height:420px">
      <div class="terminal-output" id="modal-log-content">در حال دریافت لاگ‌ها...</div>
    </div>
  </div>
</div>

<!-- Broadcast Modal -->
<div class="modal-overlay" id="modal-broadcast" hidden>
  <div class="modal-box">
    <h3>📢 ارسال پیام همگانی به کاربران ربات</h3>
    <p style="color:var(--ink-mut);font-size:12px;margin-bottom:12px">این پیام از طریق بات تلگرام به تمامی کاربران ارسال خواهد شد.</p>
    <div style="margin-bottom:12px">
      <textarea id="broadcast-text" rows="5" style="width:100%" placeholder="متن پیام همگانی خود را اینجا بنویسید..."></textarea>
    </div>
    <div style="display:flex;justify-content:flex-end;gap:8px">
      <button class="btn" id="btn-close-broadcast">انصراف</button>
      <button class="btn pri" id="btn-send-broadcast">🚀 ارسال به همه کاربران</button>
    </div>
  </div>
</div>

<!-- Toast Container -->
<div class="toast-container" id="toasts"></div>

<script>
"use strict";

const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
const fa = n => n == null ? "—" : Number(n).toLocaleString("fa-IR");

function toast(msg, type="info") {
  const c = $("#toasts");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  c.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function csrf() {
  const m = document.cookie.match(/(?:^|; )oxmit_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

async function api(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  if (opts.method && opts.method.toUpperCase() !== "GET") {
    headers["X-CSRF"] = csrf();
  }
  const r = await fetch(path, Object.assign({}, opts, { headers }));
  if (r.status === 401) {
    location.reload();
    throw new Error("سشن منقضی شده است");
  }
  if (!r.ok) {
    const err = await r.json().catch(() => ({ error: r.statusText }));
    throw new Error(err.error || `خطای HTTP ${r.status}`);
  }
  return await r.json().catch(() => ({}));
}

/* Tab Switching */
let currentTab = "overview";
function switchTab(tabId) {
  currentTab = tabId;
  $$(".nav-tab").forEach(b => b.classList.toggle("active", b.dataset.tab === tabId));
  $$(".view-panel").forEach(p => p.hidden = (p.id !== `view-${tabId}`));
  loadTabData(tabId);
}
$("#nav-tabs").addEventListener("click", e => {
  const b = e.target.closest(".nav-tab");
  if (b && b.dataset.tab) switchTab(b.dataset.tab);
});

function loadTabData(tabId) {
  if (tabId === "overview") loadOverview();
  else if (tabId === "tasks") loadTasks();
  else if (tabId === "docker") loadDocker();
  else if (tabId === "bot_users") loadBotUsers();
  else if (tabId === "terminal") { $("#term-input").focus(); }
  else if (tabId === "sql_console") loadDbTables();
  else if (tabId === "files") loadFiles($("#files-current-path").value);
  else if (tabId === "ffmpeg") loadFFmpeg();
  else if (tabId === "env_editor") loadEnv();
  else if (tabId === "audit") loadAudit();
}

/* Overview and KPIs */
async function loadOverview() {
  try {
    const [summary, metrics, services] = await Promise.all([
      api("/panel/api/summary").catch(() => ({})),
      api("/panel/api/server/metrics").catch(() => ({})),
      api("/panel/api/services").catch(() => ({}))
    ]);

    // KPI values
    const c = summary.counters || {};
    $("#kpi-active").textContent = fa(c.active || 0);
    $("#kpi-queue").textContent = fa(c.queued || 0);
    $("#kpi-completed").textContent = fa(c.completed || 0);
    $("#kpi-failed").textContent = fa(c.failed || 0);

    if (metrics.disk) {
      $("#kpi-disk").textContent = `${fa(metrics.disk.free_gb)} GB آزاد`;
      $("#kpi-disk-sub").textContent = `از ${fa(metrics.disk.total_gb)} GB (${fa(metrics.disk.used_percent)}٪ مصرف)`;
    }
    if (metrics.memory) {
      $("#kpi-ram").textContent = `${fa(metrics.memory.percent)}٪`;
      $("#kpi-ram-sub").textContent = `${fa(metrics.memory.used_mb)} MB از ${fa(metrics.memory.total_mb)} MB`;
    }
    if (metrics.cpu) {
      $("#kpi-cpu").textContent = `${fa(metrics.cpu.percent)}٪ (${metrics.cpu.count} Core)`;
    }
    if (metrics.uptime) {
      $("#kpi-uptime").textContent = `آپ‌تایم: ${fa(metrics.uptime.days)} روز و ${fa(metrics.uptime.hours)} ساعت`;
    }

    // Badge states
    if (services.access_mode) {
      $("#badge-access").textContent = services.access_mode === "private" ? "🔒 خصوصی" : "🌐 عمومی";
    }
    if (services.paused != null) {
      $("#badge-intake").textContent = services.paused ? "⏸ پذیرش متوقف" : "▶️ پذیرش فعال";
    }

    // Services list
    const comps = services.components || {};
    const svcLabels = { postgres: "PostgreSQL پایگاه داده", encore: "Encore سرور انکودینگ", bot_api: "Bot API (Telegram)", redis: "Redis صف پیام" };
    $("#overview-svc-list").innerHTML = Object.entries(comps).map(([k, v]) => `
      <div style="display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid var(--border)">
        <b>${esc(svcLabels[k] || k)}</b>
        <span class="badge ${String(v).startsWith('ok') ? 'online' : ''}">${esc(v)}</span>
      </div>
    `).join("") || '<div class="empty">موردی یافت نشد</div>';

    // Recent events
    const auditData = await api("/panel/api/audit?limit=7").catch(() => ({ items: [] }));
    const rows = (auditData.items || []).map(e => `
      <tr>
        <td class="mono">${esc((e.ts||"").replace("T"," ").slice(5,19))}</td>
        <td><b>${esc(e.actor)}</b></td>
        <td><span class="badge">${esc(e.action)}</span></td>
        <td class="mono">${esc(e.target || "—")}</td>
        <td>${esc(e.details || "")}</td>
      </tr>
    `).join("");
    $("#table-recent-events tbody").innerHTML = rows || '<tr><td colspan="5" class="empty">خالی</td></tr>';

  } catch (err) {
    console.error("Overview error", err);
  }
}

/* Tasks Tab */
async function loadTasks() {
  const status = $("#task-filter-status").value;
  const q = $("#task-filter-q").value.trim();
  try {
    const data = await api(`/panel/api/jobs?view=${status}&q=${encodeURIComponent(q)}&limit=50`);
    const items = data.items || [];
    $("#tab-cnt-active").textContent = items.length;

    if (!items.length) {
      $("#table-tasks tbody").innerHTML = '<tr><td colspan="8" class="empty">تسک فشرده‌سازی در این بخش یافت نشد.</td></tr>';
      return;
    }

    const rows = items.map(t => {
      const pct = t.progress_pct || 0;
      return `
        <tr class="clickable">
          <td class="mono">#${esc(t.id)}</td>
          <td><b>${esc(t.file_name || t.target_name || "بدون نام")}</b></td>
          <td class="mono">${esc(t.user_id || "—")}</td>
          <td>
            <span class="pill p-${esc(t.status || 'queue')}">${esc(t.status_fa || t.status)}</span>
            ${t.status === 'processing' ? `<div class="prog-bar"><span style="width:${pct}%"></span></div> ${pct}٪` : ''}
          </td>
          <td><span class="badge">${esc(t.preset || "default")}</span></td>
          <td class="mono">${esc(t.size_human || "—")}</td>
          <td class="mono">${esc((t.created_at || "").slice(0, 19).replace("T", " "))}</td>
          <td>
            ${t.status === 'processing' || t.status === 'queued' ?
              `<button class="btn danger" onclick="cancelJob('${esc(t.id)}')">لغو</button>` : '—'}
          </td>
        </tr>
      `;
    }).join("");
    $("#table-tasks tbody").innerHTML = rows;
  } catch (e) {
    toast(`خطا در بارگذاری تسک‌ها: ${e.message}`, "error");
  }
}

async function cancelJob(id) {
  if (!confirm(`آیا مطمئن هستید که کار #${id} متوقف و لغو شود؟`)) return;
  try {
    await api(`/panel/api/job/${id}/cancel`, { method: "POST" });
    toast(`تسک #${id} لغو شد`, "success");
    loadTasks();
  } catch (e) {
    toast(`خطای لغو کار: ${e.message}`, "error");
  }
}

/* Docker Tab */
async function loadDocker() {
  try {
    const d = await api("/panel/api/server/containers");
    const grid = $("#docker-cards-grid");
    if (!d.containers || !d.containers.length) {
      grid.innerHTML = '<div class="empty">کانتینری یافت نشد</div>';
      return;
    }

    grid.innerHTML = d.containers.map(c => `
      <div class="container-card ${c.state === 'running' ? 'healthy' : 'unhealthy'}">
        <div class="container-top">
          <span class="container-name">
            <span class="dot ${c.state === 'running' ? '' : 'off'}"></span>
            ${esc(c.name)}
          </span>
          <span class="badge ${c.state === 'running' ? 'online' : ''}">${esc(c.state)}</span>
        </div>
        <div style="font-size:11.5px;color:var(--ink-mut)">
          <div><b>تصویر:</b> <span class="mono">${esc(c.image)}</span></div>
          <div><b>وضعیت:</b> ${esc(c.status)}</div>
        </div>
        <div class="container-actions">
          <button class="btn" onclick="viewContainerLogs('${esc(c.name)}')">📄 لاگ‌ها</button>
          <button class="btn danger" onclick="restartContainer('${esc(c.name)}')">🔄 ری‌استارت</button>
        </div>
      </div>
    `).join("");
  } catch (e) {
    toast(`خطای دریافت وضعیت داکر: ${e.message}`, "error");
  }
}

async function restartContainer(name) {
  if (!confirm(`کانتینر ${name} ری‌استارت شود؟`)) return;
  toast(`در حال ری‌استارت ${name}...`);
  try {
    const res = await api(`/panel/api/server/container/${name}/restart`, { method: "POST" });
    toast(`کانتینر ${name} با موفقیت ری‌استارت شد`, "success");
    setTimeout(loadDocker, 2000);
  } catch (e) {
    toast(`خطای ری‌استارت: ${e.message}`, "error");
  }
}

async function viewContainerLogs(name) {
  $("#modal-logs").hidden = false;
  $("#modal-log-title").textContent = `📋 لاگ‌های کانتینر: ${name}`;
  $("#modal-log-content").textContent = "در حال بارگذاری آخرین لاگ‌ها...";
  try {
    const res = await api(`/panel/api/server/logs?name=${encodeURIComponent(name)}&tail=100`);
    $("#modal-log-content").textContent = res.logs || "هیچ لاگی ثبت نشده است.";
  } catch (e) {
    $("#modal-log-content").textContent = `خطا در دریافت لاگ: ${e.message}`;
  }
}
$("#btn-close-log-modal").onclick = () => $("#modal-logs").hidden = true;

/* Terminal Tab */
async function sendTermCmd(cmd) {
  if (!cmd) return;
  const out = $("#term-output");
  const el = document.createElement("div");
  el.className = "out-cmd";
  el.textContent = `$ ${cmd}`;
  out.appendChild(el);
  out.scrollTop = out.scrollHeight;

  $("#term-status").textContent = "در حال اجرا...";
  try {
    const r = await api("/panel/api/super/terminal", {
      method: "POST",
      body: JSON.stringify({ cmd })
    });
    if (r.stdout) {
      const s = document.createElement("div");
      s.className = "out-stdout";
      s.textContent = r.stdout;
      out.appendChild(s);
    }
    if (r.stderr) {
      const e = document.createElement("div");
      e.className = "out-stderr";
      e.textContent = r.stderr;
      out.appendChild(e);
    }
    $("#term-status").textContent = `کد خروجی: ${r.exit_code}`;
  } catch (e) {
    const errEl = document.createElement("div");
    errEl.className = "out-stderr";
    errEl.textContent = `خطا: ${e.message}`;
    out.appendChild(errEl);
    $("#term-status").textContent = "خطا";
  }
  out.scrollTop = out.scrollHeight;
  $("#term-input").value = "";
}

$("#btn-term-send").onclick = () => sendTermCmd($("#term-input").value.trim());
$("#term-input").onkeydown = e => { if (e.key === "Enter") sendTermCmd($("#term-input").value.trim()); };
$("#btn-term-clear").onclick = () => $("#term-output").innerHTML = "کنسول پاک شد.\n";
$$(".chip").forEach(c => c.onclick = () => {
  $("#term-input").value = c.dataset.cmd;
  sendTermCmd(c.dataset.cmd);
});

/* SQL Console */
async function loadDbTables() {
  try {
    const res = await api("/panel/api/super/db/tables");
    const tbody = $("#table-db-tables tbody");
    if (!res.rows || !res.rows.length) {
      tbody.innerHTML = '<tr><td colspan="2" class="empty">جدولی یافت نشد</td></tr>';
      return;
    }
    tbody.innerHTML = res.rows.map(t => `
      <tr class="clickable" onclick="selectSqlTable('${esc(t.table_name)}')">
        <td class="mono"><b>${esc(t.table_name)}</b></td>
        <td class="mono">${esc(t.size)}</td>
      </tr>
    `).join("");
  } catch (e) {
    toast(`خطای دریافت جداول: ${e.message}`, "error");
  }
}

function selectSqlTable(name) {
  $("#sql-query-input").value = `SELECT * FROM ${name} LIMIT 20;`;
  runSqlQuery();
}

async function runSqlQuery() {
  const query = $("#sql-query-input").value.trim();
  if (!query) return;
  const wrap = $("#sql-result-wrap");
  wrap.innerHTML = '<div class="empty">در حال اجرای کوئری...</div>';

  try {
    const res = await api("/panel/api/super/db/query", {
      method: "POST",
      body: JSON.stringify({ query })
    });

    if (res.error) {
      wrap.innerHTML = `<div class="empty" style="color:var(--red)">خطا: ${esc(res.error)}</div>`;
      $("#sql-result-count").textContent = "خطا";
      return;
    }

    if (res.status) {
      wrap.innerHTML = `<div class="empty" style="color:var(--green)">${esc(res.status)}</div>`;
      $("#sql-result-count").textContent = "انجام شد";
      return;
    }

    const rows = res.rows || [];
    const cols = res.columns || [];
    $("#sql-result-count").textContent = `${fa(rows.length)} ردیف`;

    if (!rows.length) {
      wrap.innerHTML = '<div class="empty">هیچ ردیفی بازگردانده نشد.</div>';
      return;
    }

    wrap.innerHTML = `
      <table>
        <thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead>
        <tbody>
          ${rows.map(r => `<tr>${cols.map(c => `<td class="mono">${esc(r[c])}</td>`).join("")}</tr>`).join("")}
        </tbody>
      </table>
    `;
  } catch (e) {
    wrap.innerHTML = `<div class="empty" style="color:var(--red)">خطا: ${esc(e.message)}</div>`;
  }
}
$("#btn-sql-run").onclick = runSqlQuery;
$("#btn-sql-snippet-tasks").onclick = () => {
  $("#sql-query-input").value = "SELECT id, status, user_id, progress_pct, created_at FROM tasks ORDER BY created_at DESC LIMIT 25;";
  runSqlQuery();
};
$("#btn-sql-snippet-users").onclick = () => {
  $("#sql-query-input").value = "SELECT telegram_id, username, is_banned, daily_quota, created_at FROM users ORDER BY created_at DESC LIMIT 25;";
  runSqlQuery();
};
$("#btn-db-backup").onclick = async () => {
  if (!confirm("آیا بکاپ کامل PostgreSQL (pg_dump) تهیه شود؟")) return;
  toast("در حال ایجاد نسخه پشتیبان پایگاه داده...");
  try {
    const res = await api("/panel/api/super/db/backup", { method: "POST" });
    if (res.ok) {
      toast(`✅ بکاپ در سرور ذخیره شد: ${res.path} (${Math.round(res.size/1024)} KB)`, "success");
    } else {
      toast(`خطای بکاپ: ${res.error}`, "error");
    }
  } catch (e) {
    toast(`خطای بکاپ: ${e.message}`, "error");
  }
};

/* File Explorer */
async function loadFiles(path) {
  try {
    const res = await api(`/panel/api/super/files?path=${encodeURIComponent(path)}`);
    const tbody = $("#table-files tbody");
    if (res.error) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty" style="color:var(--red)">${esc(res.error)}</td></tr>`;
      return;
    }
    $("#files-current-path").value = res.path;
    const entries = res.entries || [];
    if (!entries.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">پوشه خالی است</td></tr>';
      return;
    }

    tbody.innerHTML = entries.map(item => `
      <tr class="clickable">
        <td>
          ${item.is_dir ? '📁' : '📄'}
          <b ${item.is_dir ? `onclick="loadFiles('${esc(item.path)}')"` : ''}>${esc(item.name)}</b>
        </td>
        <td>${item.is_dir ? 'دایرکتوری' : 'فایل'}</td>
        <td class="mono">${item.is_dir ? '—' : (Math.round(item.size/1024) + ' KB')}</td>
        <td class="mono">${esc(item.mtime_str)}</td>
        <td>
          ${!item.is_dir ? `<button class="btn danger" onclick="deleteServerFile('${esc(item.path)}')">حذف</button>` : ''}
        </td>
      </tr>
    `).join("");
  } catch (e) {
    toast(`خطای مرورگر فایل: ${e.message}`, "error");
  }
}
$("#btn-files-go").onclick = () => loadFiles($("#files-current-path").value.trim());
$("#btn-files-media").onclick = () => loadFiles("/media");

async function deleteServerFile(path) {
  if (!confirm(`آیا مطمئن هستید که فایل زیر حذف شود؟\n${path}`)) return;
  try {
    const res = await api("/panel/api/super/files/delete", {
      method: "POST",
      body: JSON.stringify({ path })
    });
    if (res.ok) {
      toast(`فایل با موفقیت حذف شد`, "success");
      loadFiles($("#files-current-path").value);
    } else {
      toast(`خطا در حذف: ${res.error}`, "error");
    }
  } catch (e) {
    toast(`خطای حذف: ${e.message}`, "error");
  }
}

/* FFmpeg Settings */
async function loadFFmpeg() {
  try {
    const res = await api("/panel/api/super/ffmpeg");
    const p = res.params || {};
    if (p.crf) {
      $("#ffmpeg-crf").value = p.crf.value;
      $("#val-ffmpeg-crf").textContent = p.crf.value;
    }
    if (p.preset) $("#ffmpeg-preset").value = p.preset.value;
    if (p.video_codec) $("#ffmpeg-vcodec").value = p.video_codec.value;
    if (p.max_height) $("#ffmpeg-res").value = p.max_height.value;
    if (p.max_fps) $("#ffmpeg-fps").value = p.max_fps.value;
    if (p.extra_vf) $("#ffmpeg-extra-vf").value = p.extra_vf.value || "";
  } catch (e) {
    toast(`خطای بارگذاری تنظیمات FFmpeg: ${e.message}`, "error");
  }
}

$("#ffmpeg-crf").oninput = e => $("#val-ffmpeg-crf").textContent = e.target.value;

$("#btn-ffmpeg-save").onclick = async () => {
  const updates = {
    crf: Number($("#ffmpeg-crf").value),
    preset: $("#ffmpeg-preset").value,
    video_codec: $("#ffmpeg-vcodec").value,
    max_height: Number($("#ffmpeg-res").value),
    max_fps: Number($("#ffmpeg-fps").value),
    extra_vf: $("#ffmpeg-extra-vf").value.trim()
  };
  try {
    const res = await api("/panel/api/super/ffmpeg", {
      method: "POST",
      body: JSON.stringify(updates)
    });
    toast("✅ تنظیمات FFmpeg با موفقیت بروزرسانی شد", "success");
  } catch (e) {
    toast(`خطای ذخیره: ${e.message}`, "error");
  }
};

/* .env Editor */
let envVarsCache = {};
async function loadEnv() {
  try {
    const res = await api("/panel/api/super/env");
    const container = $("#env-vars-container");
    if (res.error) {
      container.innerHTML = `<div class="empty" style="color:var(--red)">${esc(res.error)}</div>`;
      return;
    }
    envVarsCache = res.vars || {};
    renderEnvEditor();
  } catch (e) {
    toast(`خطای خواندن .env: ${e.message}`, "error");
  }
}

function renderEnvEditor() {
  const c = $("#env-vars-container");
  const entries = Object.entries(envVarsCache);
  if (!entries.length) {
    c.innerHTML = '<div class="empty">هیچ متغیری یافت نشد</div>';
    return;
  }

  c.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:8px">
      ${entries.map(([k, v]) => `
        <div style="display:flex;gap:10px;align-items:center;background:#131824;padding:8px 12px;border-radius:8px;border:1px solid var(--border)">
          <span class="mono" style="min-width:220px;font-weight:700;color:#93c5fd">${esc(k)}</span>
          <input type="text" class="env-input mono" data-key="${esc(k)}" value="${esc(v)}" style="flex:1">
          <button class="btn danger" onclick="deleteEnvKey('${esc(k)}')">حذف</button>
        </div>
      `).join("")}
    </div>
  `;
}

function deleteEnvKey(k) {
  delete envVarsCache[k];
  renderEnvEditor();
}

$("#btn-env-add").onclick = () => {
  const k = prompt("نام متغیر جدید (مثال: LOG_LEVEL):");
  if (!k) return;
  const v = prompt("مقدار متغیر:");
  envVarsCache[k.trim()] = (v || "").trim();
  renderEnvEditor();
};

$("#btn-env-save").onclick = async () => {
  $$(".env-input").forEach(inp => {
    envVarsCache[inp.dataset.key] = inp.value;
  });
  toast("در حال ذخیره فایل .env...");
  try {
    const res = await api("/panel/api/super/env", {
      method: "POST",
      body: JSON.stringify({ vars: envVarsCache })
    });
    if (res.ok) {
      toast("✅ فایل .env با موفقیت ذخیره شد", "success");
    } else {
      toast(`خطای ذخیره: ${res.error}`, "error");
    }
  } catch (e) {
    toast(`خطای ذخیره: ${e.message}`, "error");
  }
};

/* Bot & Users */
async function loadBotUsers() {
  const q = $("#user-search-input").value.trim();
  try {
    const res = await api(`/panel/api/bot/users?q=${encodeURIComponent(q)}&limit=50`);
    const users = res.users || [];
    const tbody = $("#table-users tbody");
    if (!users.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty">کاربری یافت نشد</td></tr>';
      return;
    }
    tbody.innerHTML = users.map(u => `
      <tr>
        <td class="mono">${esc(u.telegram_id)}</td>
        <td><b>${esc(u.username ? '@'+u.username : 'بدون یوزرنیم')}</b></td>
        <td class="mono">${fa(u.daily_quota_files || 10)} فایل</td>
        <td class="mono">${fa(u.used_today_files || 0)}</td>
        <td>
          <span class="badge ${u.is_banned ? '' : 'online'}">
            ${u.is_banned ? '⛔ مسدود' : 'فعال'}
          </span>
        </td>
        <td class="mono">${esc((u.last_activity || u.created_at || '').slice(0, 16).replace('T', ' '))}</td>
        <td>
          <button class="btn ${u.is_banned ? 'success' : 'danger'}" onclick="toggleBanUser(${u.telegram_id}, ${!u.is_banned})">
            ${u.is_banned ? 'آزادسازی' : 'مسدودسازی'}
          </button>
        </td>
      </tr>
    `).join("");
  } catch (e) {
    toast(`خطای واکشی کاربران: ${e.message}`, "error");
  }
}
$("#btn-user-search").onclick = loadBotUsers;

async function toggleBanUser(tgId, ban) {
  const reason = ban ? prompt("دلیل مسدودسازی را وارد کنید (اختیاری):", "Spam") : "";
  try {
    await api(`/panel/api/bot/user/${tgId}/ban`, {
      method: "POST",
      body: JSON.stringify({ ban, reason })
    });
    toast(ban ? "کاربر مسدود شد" : "کاربر آزاد شد", "success");
    loadBotUsers();
  } catch (e) {
    toast(`خطای مسدودسازی: ${e.message}`, "error");
  }
}

/* Broadcast Modal */
$("#btn-open-broadcast").onclick = () => $("#modal-broadcast").hidden = false;
$("#btn-close-broadcast").onclick = () => $("#modal-broadcast").hidden = true;
$("#btn-send-broadcast").onclick = async () => {
  const msg = $("#broadcast-text").value.trim();
  if (!msg) return alert("متن پیام الزامی است");
  if (!confirm("آیا از ارسال پیام به همه کاربران ربات مطمئن هستید؟")) return;

  toast("در حال آماده‌سازی و ارسال پیام همگانی...");
  try {
    const res = await api("/panel/api/bot/broadcast", {
      method: "POST",
      body: JSON.stringify({ text: msg, parse_mode: "HTML" })
    });
    toast("✅ ارسال پیام همگانی آغاز شد", "success");
    $("#modal-broadcast").hidden = true;
    $("#broadcast-text").value = "";
  } catch (e) {
    toast(`خطای ارسال پیام: ${e.message}`, "error");
  }
};

/* Security Audit Tab */
async function loadAudit() {
  try {
    const res = await api("/panel/api/audit?limit=60");
    const tbody = $("#table-audit tbody");
    const items = res.items || [];
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">لاگی موجود نیست</td></tr>';
      return;
    }
    tbody.innerHTML = items.map(e => `
      <tr>
        <td class="mono">${esc((e.ts||'').replace('T',' ').slice(0,19))}</td>
        <td><b>${esc(e.actor)}</b></td>
        <td><span class="badge">${esc(e.action)}</span></td>
        <td class="mono">${esc(e.target || '—')}</td>
        <td>${esc(e.details || '')}</td>
        <td class="mono">${esc(e.ip || '—')}</td>
      </tr>
    `).join("");
  } catch (e) {
    toast(`خطای لاگ: ${e.message}`, "error");
  }
}

/* Quick Actions in Header */
$("#btn-toggle-access").onclick = async () => {
  if (!confirm("آیا حالت دسترسی ربات (Public / Private) تغییر داده شود؟")) return;
  try {
    const cfg = await api("/panel/api/bot/config");
    const nextMode = cfg.access_mode === "private" ? "public" : "private";
    await api("/panel/api/bot/config", {
      method: "POST",
      body: JSON.stringify({ access_mode: nextMode })
    });
    toast(`حالت ربات به ${nextMode === "private" ? "خصوصی" : "عمومی"} تغییر یافت`, "success");
    loadOverview();
  } catch (e) {
    toast(`خطا: ${e.message}`, "error");
  }
};

$("#btn-toggle-intake").onclick = async () => {
  if (!confirm("آیا وضعیت پذیرش ربات (Pause / Resume) تغییر داده شود؟")) return;
  try {
    const s = await api("/panel/api/services");
    const act = s.paused ? "resume" : "pause";
    await api(`/panel/api/system/${act}`, { method: "POST" });
    toast(`پذیرش ربات ${act === "pause" ? "متوقف شد" : "فعال شد"}`, "success");
    loadOverview();
  } catch (e) {
    toast(`خطا: ${e.message}`, "error");
  }
};

$("#btn-cancel-all").onclick = async () => {
  if (!confirm("⚠️ اخطار جدی!\nآیا از لغو تمامی کارهای در حال اجرا و صف فشرده‌سازی مطمئن هستید؟")) return;
  try {
    const res = await api("/panel/api/system/cancel_all", { method: "POST" });
    toast(`عملیات اضطراری: ${res.cancelled || 0} کار لغو شدند`, "success");
    loadOverview();
    if (currentTab === "tasks") loadTasks();
  } catch (e) {
    toast(`خطا: ${e.message}`, "error");
  }
};

$("#btn-logout").onclick = async () => {
  await api("/panel/logout", { method: "POST" }).catch(() => {});
  location.reload();
};

/* WebSocket Live Connection */
let ws = null;
function initLiveWs() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  try {
    ws = new WebSocket(`${proto}//${location.host}/panel/ws`);
    ws.onopen = () => {
      $("#dot-ws").classList.remove("off");
      $("#badge-ws").textContent = "لایو (WebSocket)";
    };
    ws.onmessage = ev => {
      try {
        const d = JSON.parse(ev.data);
        if (d.summary) {
          const c = d.summary.counters || {};
          $("#kpi-active").textContent = fa(c.active || 0);
          $("#kpi-queue").textContent = fa(c.queued || 0);
        }
      } catch (err) {}
    };
    ws.onclose = () => {
      $("#dot-ws").classList.add("off");
      $("#badge-ws").textContent = "پولینگ (پسیو)";
      setTimeout(initLiveWs, 6000);
    };
  } catch (e) {
    setTimeout(initLiveWs, 10000);
  }
}

// Initial Run
loadOverview();
initLiveWs();
setInterval(() => {
  if (!document.hidden && currentTab === "overview") loadOverview();
  else if (!document.hidden && currentTab === "tasks") loadTasks();
}, 6000);

</script>
</body>
</html>
"""
