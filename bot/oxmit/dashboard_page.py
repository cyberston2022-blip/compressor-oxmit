"""Single-file HTML for the comprehensive Oxmit Super-Admin Web Panel.
"""

PAGE = r"""<!doctype html><html dir="rtl" lang="fa"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oxmit Super-Admin — مرکز کنترل فوق پیشرفته</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;600;700;800;900&display=swap">
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
.badge.warn {
  background: rgba(245, 158, 11, 0.12);
  border-color: rgba(245, 158, 11, 0.35);
  color: #fbbf24;
}
.badge.danger {
  background: rgba(239, 68, 68, 0.12);
  border-color: rgba(239, 68, 68, 0.35);
  color: #f87171;
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
  padding: 3px 10px;
  border-radius: 99px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.p-processing, .p-active { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.35); }
.p-queued, .p-queue { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.35); }
.p-completed, .p-done { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.35); }
.p-failed, .p-fail { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.35); }
.p-cancelled, .p-cancel { background: rgba(100, 116, 139, 0.15); color: #94a3b8; border: 1px solid rgba(100, 116, 139, 0.35); }

/* SVG Icons */
.ico {
  display: inline-block;
  vertical-align: -2.5px;
  margin-left: 6px;
  stroke: currentColor;
  flex-shrink: 0;
}
.nav-tab .ico {
  width: 16px;
  height: 16px;
  transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1), filter 0.2s;
}
.nav-tab:hover .ico,
.nav-tab.active .ico {
  transform: scale(1.15);
  filter: drop-shadow(0 0 6px var(--acc-glow));
}
.header-actions .ico, .badge .ico, .card-head .ico {
  width: 14px;
  height: 14px;
}

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

/* Responsive Layout */
@media (max-width: 960px) {
  header {
    padding: 10px 14px;
    gap: 10px;
  }
  .header-badges {
    flex-wrap: wrap;
    gap: 6px;
  }
  .header-actions {
    flex-wrap: wrap;
    gap: 6px;
    width: 100%;
    justify-content: flex-start;
  }
  .sp { display: none; }
  .nav-wrap {
    padding: 8px 12px;
    overflow-x: auto;
    white-space: nowrap;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: thin;
  }
  .nav-tab {
    padding: 7px 12px;
    font-size: 12px;
  }
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
    <span class="badge owner" id="badge-role"><svg class="ico" viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none"><path d="m2 4 3 12h14l3-12-6 7-4-7-4 7-6-7zm3 16h14"/></svg> مالک ربات <bdi dir="ltr">(@Oxmit)</bdi></span>
    <span class="badge" id="badge-access"><svg class="ico" viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg> عمومی</span>
    <span class="badge" id="badge-intake"><svg class="ico" viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none"><polygon points="6 3 20 12 6 21 6 3"/></svg> پذیرش فعال</span>
    <span class="badge online" id="badge-ws"><span class="dot" id="dot-ws"></span><span id="text-ws"> لایو <bdi dir="ltr">(WebSocket)</bdi></span></span>
  </div>

  <span class="sp"></span>

  <div class="header-actions">
    <button id="btn-toggle-access" title="تغییر دسترسی عمومی/خصوصی"><svg class="ico" viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg> تغییر دسترسی</button>
    <button id="btn-toggle-intake" title="توقف یا ادامه پذیرش ربات"><svg class="ico" viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none"><rect width="4" height="16" x="6" y="4"/><rect width="4" height="16" x="14" y="4"/></svg> توقف/ادامه پذیرش</button>
    <button class="danger" id="btn-cancel-all" title="لغو اضطراری تمام کارهای صف"><svg class="ico" viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none"><circle cx="12" cy="12" r="10"/><line x1="15" x2="9" y1="9" y2="15"/><line x1="9" x2="15" y1="9" y2="15"/></svg> لغو اضطراری همه</button>
    <a class="btn" href="/panel/legacy" target="_blank" title="مشاهده نسخه ساده"><svg class="ico" viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none"><path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg> داشبورد قدیم</a>
    <button class="danger" id="btn-logout"><svg class="ico" viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/></svg> خروج</button>
  </div>
</header>

<!-- Navigation Tabs -->
<nav class="nav-wrap" id="nav-tabs">
  <button class="nav-tab active" data-tab="overview"><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/></svg> داشبورد و آمار</button>
  <button class="nav-tab" data-tab="tasks"><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> صف و انکودینگ <span class="badge-count" id="tab-cnt-active">0</span></button>
  <button class="nav-tab" data-tab="config"><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg> تنظیمات هسته و صف</button>
  <button class="nav-tab" data-tab="docker"><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><path d="m7.5 4.27 9 5.15"/><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg> کانتینرهای داکر</button>
  <button class="nav-tab" data-tab="bot_users"><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg> مدیریت ربات و کاربران</button>
  <button class="nav-tab" data-tab="audit"><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/><path d="m9 12 2 2 4-4"/></svg> لاگ‌های امنیتی <bdi dir="ltr">(Audit)</bdi></button>
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
          <h2><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="var(--blue)" stroke-width="2" fill="none"><rect width="20" height="8" x="2" y="2" rx="2" ry="2"/><rect width="20" height="8" x="2" y="14" rx="2" ry="2"/><line x1="6" x2="6.01" y1="6" y2="6"/><line x1="6" x2="6.01" y1="18" y2="18"/></svg> وضعیت سرویس‌های زیرساخت</h2>
          <button class="btn" id="btn-refresh-svc">بروزرسانی</button>
        </div>
        <div id="overview-svc-list">
          <div class="empty">در حال دریافت وضعیت سرویس‌ها...</div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <h2><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="var(--amber)" stroke-width="2" fill="none"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> پردازش‌های جاری سرور</h2>
          <span class="badge" id="active-tasks-badge">0 تسک</span>
        </div>
        <div id="overview-active-tasks">
          <div class="empty">هیچ کاری در حال پردازش نیست</div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h2><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="var(--green)" stroke-width="2" fill="none"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg> آخرین رخدادهای سیستم و فعالیت‌ها</h2>
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
        <h2><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="var(--acc)" stroke-width="2" fill="none"><rect width="20" height="20" x="2" y="2" rx="2.18" ry="2.18"/><line x1="7" x2="7" y1="2" y2="22"/><line x1="17" x2="17" y1="2" y2="22"/><line x1="2" x2="22" y1="12" y2="12"/><line x1="2" x2="7" y1="7" y2="7"/><line x1="2" x2="7" y1="17" y2="17"/><line x1="17" x2="22" y1="17" y2="17"/><line x1="17" x2="22" y1="7" y2="7"/></svg> مدیریت کارهای فشرده‌سازی ویدیو</h2>
        <div class="actions">
          <select id="task-filter-status">
            <option value="active">در حال پردازش (Active)</option>
            <option value="queue">در صف انتظار (Queued)</option>
            <option value="completed">تکمیل‌شده (Completed)</option>
            <option value="failed">ناموفق (Failed)</option>
            <option value="cancelled">لغو شده (Cancelled)</option>
            <option value="all">همه کارها (All)</option>
          </select>
          <input type="text" id="task-filter-q" placeholder="شناسه کار یا نام فایل..." style="width:200px">
          <button class="btn pri" id="btn-task-refresh">جستجو و فیلتر</button>
          <button class="btn danger" id="btn-batch-cancel" onclick="batchCancelTasks()" style="display:none">لغو کارهای انتخاب‌شده</button>
        </div>
      </div>
      <div class="table-wrap">
        <table id="table-tasks">
          <thead>
            <tr>
              <th style="width:36px"><input type="checkbox" id="check-all-tasks" onchange="toggleSelectAllTasks(this)"></th>
              <th>شناسه کار</th>
              <th>جایگاه / وضعیت</th>
              <th>نام فایل</th>
              <th>کاربر</th>
              <th>کیفیت</th>
              <th>حجم اولیه / خروجی</th>
              <th>زمان ایجاد</th>
              <th>عملیات</th>
            </tr>
          </thead>
          <tbody>
            <tr><td colspan="9" class="empty">در حال دریافت داده‌های صف...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <!-- View 2.5: Dynamic Config & Queue Fairness Simulator -->
  <section id="view-config" class="view-panel" hidden>
    <div class="grid-2">
      <!-- Config Form -->
      <div class="card">
        <div class="card-head">
          <h2><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="var(--purple)" stroke-width="2" fill="none"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg> تنظیمات هسته و موتور صف (Dynamic Runtime Config)</h2>
          <button class="btn success" id="btn-save-config" onclick="saveDynamicConfig()"><svg class="ico" viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> ذخیره و اعمال آنی (Apply Live)</button>
        </div>

        <div style="display:flex;flex-direction:column;gap:18px;padding-top:10px">
          <!-- Group 1 -->
          <div style="background:var(--card-sub);padding:14px;border-radius:8px;border:1px solid var(--border)">
            <h4 style="margin:0 0 12px 0;color:var(--acc);font-size:14px;display:flex;align-items:center;gap:6px">
              ⚡ ظرفیت و محدودیت‌های همزمانی (Concurrency & Capacity)
            </h4>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
              <div>
                <label style="font-size:12px;color:var(--ink-dim);display:block;margin-bottom:4px">حداکثر طول مجاز کل صف (Global Queue Limit)</label>
                <input type="number" id="cfg-max_queue_size" min="10" max="5000" style="width:100%" placeholder="500">
              </div>
              <div>
                <label style="font-size:12px;color:var(--ink-dim);display:block;margin-bottom:4px">ورکرهای موازی انکود (Encoding Workers)</label>
                <input type="number" id="cfg-active_encoding_workers" min="1" max="16" style="width:100%" placeholder="3">
              </div>
              <div>
                <label style="font-size:12px;color:var(--ink-dim);display:block;margin-bottom:4px">حداکثر دانلودهای همزمان (Max Downloads)</label>
                <input type="number" id="cfg-max_active_downloads" min="1" max="16" style="width:100%" placeholder="5">
              </div>
              <div>
                <label style="font-size:12px;color:var(--ink-dim);display:block;margin-bottom:4px">حداکثر آپلودهای همزمان (Max Uploads)</label>
                <input type="number" id="cfg-max_active_uploads" min="1" max="16" style="width:100%" placeholder="4">
              </div>
            </div>
          </div>

          <!-- Group 2 -->
          <div style="background:var(--card-sub);padding:14px;border-radius:8px;border:1px solid var(--border)">
            <h4 style="margin:0 0 12px 0;color:var(--amber);font-size:14px;display:flex;align-items:center;gap:6px">
              ⚖️ الگوریتم زمان‌بندی و عدالت صف (Scheduling & Fairness)
            </h4>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
              <div style="grid-column:1 / -1">
                <label style="font-size:12px;color:var(--ink-dim);display:block;margin-bottom:4px">الگوریتم فعال پردازش صف</label>
                <select id="cfg-queue_scheduling_algorithm" style="width:100%">
                  <option value="fair_round_robin">Fair Round-Robin (عدالت گردشی میان کاربران)</option>
                  <option value="weighted_fair">Weighted Fair Queuing (وزن‌دار با اولویت VIP)</option>
                  <option value="strict_fifo">Strict FIFO (صف کلاسیک به ترتیب زمان ثبت)</option>
                  <option value="size_aware_fair">Size-Aware Fair (ترکیب فایل‌های سبک و سنگین)</option>
                </select>
              </div>
              <div>
                <label style="font-size:12px;color:var(--ink-dim);display:block;margin-bottom:4px">آستانه گرسنگی صف (ثانیه)</label>
                <input type="number" id="cfg-fairness_starvation_threshold_sec" min="60" max="86400" style="width:100%" placeholder="1800">
              </div>
              <div>
                <label style="font-size:12px;color:var(--ink-dim);display:block;margin-bottom:4px">وزن سوگیری اندازه فایل (0.0 تا 1.0)</label>
                <input type="number" step="0.1" id="cfg-fairness_size_bias_weight" min="0" max="1" style="width:100%" placeholder="0.5">
              </div>
              <div>
                <label style="font-size:12px;color:var(--ink-dim);display:block;margin-bottom:4px">فاصله بروزرسانی کارت صف تلگرام (ثانیه)</label>
                <input type="number" id="cfg-queue_card_throttle_sec" min="3" max="60" style="width:100%" placeholder="10">
              </div>
              <div>
                <label style="font-size:12px;color:var(--ink-dim);display:block;margin-bottom:4px">دور زدن صف توسط مدیران (Admin Bypass)</label>
                <select id="cfg-admin_queue_bypass" style="width:100%">
                  <option value="false">غیرفعال (مدیر هم در صف عادلانه قرار می‌گیرد)</option>
                  <option value="true">فعال (مدیر مستقیماً در صدر صف قرار می‌گیرد)</option>
                </select>
              </div>
            </div>
          </div>

          <!-- Group 3 -->
          <div style="background:var(--card-sub);padding:14px;border-radius:8px;border:1px solid var(--border)">
            <h4 style="margin:0 0 12px 0;color:var(--blue);font-size:14px;display:flex;align-items:center;gap:6px">
              👥 سیاست سهمیه کاربران (User Quotas & Concurrency)
            </h4>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
              <div>
                <label style="font-size:12px;color:var(--ink-dim);display:block;margin-bottom:4px">حداکثر کار همزمان کاربر عادی</label>
                <input type="number" id="cfg-user_active_job_limit" min="1" max="10" style="width:100%" placeholder="1">
              </div>
              <div>
                <label style="font-size:12px;color:var(--ink-dim);display:block;margin-bottom:4px">حداکثر کار همزمان کاربر VIP</label>
                <input type="number" id="cfg-vip_active_job_limit" min="1" max="20" style="width:100%" placeholder="3">
              </div>
              <div style="grid-column:1 / -1">
                <label style="font-size:12px;color:var(--ink-dim);display:block;margin-bottom:4px">زمان کول‌داون بین دو درخواست کاربر (ثانیه)</label>
                <input type="number" id="cfg-user_cooldown_seconds" min="0" max="300" style="width:100%" placeholder="0">
              </div>
            </div>
          </div>

          <!-- Group 4 -->
          <div style="background:var(--card-sub);padding:14px;border-radius:8px;border:1px solid var(--border)">
            <h4 style="margin:0 0 12px 0;color:var(--green);font-size:14px;display:flex;align-items:center;gap:6px">
              🛡️ نگهداری دیسک و پایداری (Disk & Safety)
            </h4>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
              <div>
                <label style="font-size:12px;color:var(--ink-dim);display:block;margin-bottom:4px">آستانه پاکسازی خودکار دیسک (GB)</label>
                <input type="number" step="0.5" id="cfg-temp_cleanup_threshold_gb" min="1" max="500" style="width:100%" placeholder="20.0">
              </div>
              <div>
                <label style="font-size:12px;color:var(--ink-dim);display:block;margin-bottom:4px">آستانه دیسک اضطراری توقف intake (GB)</label>
                <input type="number" step="0.5" id="cfg-emergency_disk_threshold_gb" min="1" max="100" style="width:100%" placeholder="5.0">
              </div>
              <div style="grid-column:1 / -1">
                <label style="font-size:12px;color:var(--ink-dim);display:block;margin-bottom:4px">حداکثر دفعات تلاش مجدد تسک‌های خطا (Retries)</label>
                <input type="number" id="cfg-max_job_retries" min="0" max="5" style="width:100%" placeholder="2">
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Live Fairness Simulator Preview -->
      <div class="card">
        <div class="card-head">
          <h2><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="var(--blue)" stroke-width="2" fill="none"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg> شبیه‌ساز زنده عدالت در صف (Live Queue Preview)</h2>
          <div class="actions">
            <select id="sim-algo-select" onchange="loadQueuePreview(this.value)">
              <option value="">الگوریتم فعلی سیستم</option>
              <option value="fair_round_robin">Fair Round-Robin</option>
              <option value="weighted_fair">Weighted Fair (WFQ)</option>
              <option value="strict_fifo">Strict FIFO</option>
              <option value="size_aware_fair">Size-Aware Fair</option>
            </select>
            <button class="btn" onclick="loadQueuePreview()">بروزرسانی</button>
          </div>
        </div>
        <p style="color:var(--ink-mut);font-size:12px;margin:8px 0 14px 0">
          این شبیه‌ساز، صف فعلی در دیتابیس را بر اساس الگوریتم انتخابی مرتب کرده و ترتیب دقیق ورود کارها به ورکرها را نشان می‌دهد.
        </p>
        <div class="table-wrap" style="max-height:560px;overflow-y:auto">
          <table id="table-queue-preview">
            <thead>
              <tr>
                <th style="width:50px">نوبت</th>
                <th>شناسه کار</th>
                <th>کاربر</th>
                <th>وضعیت</th>
                <th>حجم فایل</th>
                <th>زمان ورود</th>
                <th>امتیاز/وزن</th>
              </tr>
            </thead>
            <tbody>
              <tr><td colspan="7" class="empty">در حال دریافت داده‌های شبیه‌ساز صف...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </section>

  <!-- View 3: Docker Containers -->
  <section id="view-docker" class="view-panel" hidden>
    <div class="card">
      <div class="card-head">
        <h2><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="var(--blue)" stroke-width="2" fill="none"><path d="m7.5 4.27 9 5.15"/><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg> کانتینرهای داکر سرویس Oxmit (/var/run/docker.sock)</h2>
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
        <h2><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="var(--purple)" stroke-width="2" fill="none"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg> مدیریت کاربران ربات تلگرام</h2>
        <div class="actions">
          <input type="text" id="user-search-input" placeholder="آیدی عددی یا @username...">
          <button class="btn pri" id="btn-user-search">جستجو</button>
          <button class="btn success" id="btn-open-broadcast"><svg class="ico" viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/></svg> ارسال پیام همگانی</button>
        </div>
      </div>
      <div class="table-wrap">
        <table id="table-users">
          <thead>
            <tr>
              <th>آیدی تلگرام</th>
              <th>نام و نام خانوادگی</th>
              <th>نام کاربری</th>
              <th>کارهای ۲۴ ساعت</th>
              <th>کل درخواست‌ها</th>
              <th>وضعیت حساب</th>
              <th>آخرین فعالیت</th>
              <th>عملیات</th>
            </tr>
          </thead>
          <tbody>
            <tr><td colspan="8" class="empty">برای مشاهده کاربران جستجو کنید یا کلید اعمال را بزنید...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <!-- View 5: Web Terminal -->
  <section id="view-terminal" class="view-panel" hidden>
    <div class="card">
      <div class="card-head">
        <h2><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="var(--green)" stroke-width="2" fill="none"><polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/></svg> وب‌ترمینال زنده سرور لینوکس (Linux Shell & Docker Exec)</h2>
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
          <h2><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="var(--blue)" stroke-width="2" fill="none"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/><path d="M3 12A9 3 0 0 0 21 12"/></svg> کنسول کوئری SQL (PostgreSQL)</h2>
          <button class="btn success" id="btn-db-backup"><svg class="ico" viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/></svg> بکاپ‌گیری فوری (pg_dump)</button>
        </div>
        <div style="margin-bottom:10px">
          <textarea id="sql-query-input" rows="6" style="width:100%;font-family:ui-monospace,monospace;font-size:13px;direction:ltr" placeholder="SELECT * FROM jobs ORDER BY enqueued_at DESC LIMIT 20;"></textarea>
        </div>
        <div style="display:flex;gap:8px;justify-content:flex-end">
          <button class="btn" id="btn-sql-snippet-tasks">تسک‌های اخیر</button>
          <button class="btn" id="btn-sql-snippet-users">کاربران پرمصرف</button>
          <button class="btn pri" id="btn-sql-run"><svg class="ico" viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><polygon points="6 3 20 12 6 21 6 3"/></svg> اجرای کوئری</button>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <h2><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="var(--blue)" stroke-width="2" fill="none"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/></svg> جداول پایگاه داده و حجم ذخیره‌سازی</h2>
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
        <h2><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="var(--amber)" stroke-width="2" fill="none"><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/></svg> مرورگر فایل سرور <bdi dir="ltr">(/opt/oxmit و /media)</bdi></h2>
        <div class="actions">
          <input type="text" id="files-current-path" value="/media" style="width:280px;direction:ltr">
          <button class="btn pri" id="btn-files-go">مرور مسیر</button>
          <button class="btn" id="btn-files-up" title="یک پوشه بالاتر"><svg class="ico" viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><polyline points="18 15 12 9 6 15"/></svg> پوشه بالاتر (..)</button>
          <button class="btn" id="btn-files-media"><svg class="ico" viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/></svg> پوشه /media</button>
          <button class="btn" id="btn-files-opt"><svg class="ico" viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/></svg> پوشه /opt/oxmit</button>
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
        <h2><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="var(--acc)" stroke-width="2" fill="none"><line x1="4" x2="4" y1="21" y2="14"/><line x1="4" x2="4" y1="10" y2="3"/><line x1="12" x2="12" y1="21" y2="12"/><line x1="12" x2="12" y1="8" y2="3"/><line x1="20" x2="20" y1="21" y2="16"/><line x1="20" x2="20" y1="12" y2="3"/><line x1="1" x2="7" y1="14" y2="14"/><line x1="9" x2="15" y1="8" y2="8"/><line x1="17" x2="23" y1="16" y2="16"/></svg> تنظیمات سفارشی انکودر FFmpeg (بدون نیاز به ویرایش کد)</h2>
        <button class="btn pri" id="btn-ffmpeg-save"><svg class="ico" viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> ذخیره و اعمال آنی</button>
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
        <h2><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="var(--blue)" stroke-width="2" fill="none"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg> ویرایشگر زنده متغیرهای محیطی (/opt/oxmit/.env)</h2>
        <div class="actions">
          <button class="btn" id="btn-env-add"><svg class="ico" viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><line x1="12" x2="12" y1="5" y2="19"/><line x1="5" x2="19" y1="12" y2="12"/></svg> افزودن متغیر</button>
          <button class="btn pri" id="btn-env-save"><svg class="ico" viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> ذخیره تغییرات .env</button>
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
        <h2><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="var(--red)" stroke-width="2" fill="none"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/><path d="m9 12 2 2 4-4"/></svg> ثبت رخدادها و لاگ‌های امنیتی (Security Audit)</h2>
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
      <h3 id="modal-log-title"><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" x2="8" y1="13" y2="13"/><line x1="16" x2="8" y1="17" y2="17"/><line x1="10" x2="8" y1="9" y2="9"/></svg> لاگ‌های کانتینر</h3>
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
    <h3><svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/></svg> ارسال پیام همگانی به کاربران ربات</h3>
    <p style="color:var(--ink-mut);font-size:12px;margin-bottom:12px">این پیام از طریق بات تلگرام به تمامی کاربران ارسال خواهد شد.</p>
    <div style="margin-bottom:12px">
      <textarea id="broadcast-text" rows="5" style="width:100%" placeholder="متن پیام همگانی خود را اینجا بنویسید..."></textarea>
    </div>
    <div style="display:flex;justify-content:flex-end;gap:8px">
      <button class="btn" id="btn-close-broadcast">انصراف</button>
      <button class="btn pri" id="btn-send-broadcast"><svg class="ico" viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><line x1="22" x2="11" y1="2" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg> ارسال به همه کاربران</button>
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

const fmtBytes = b => {
  if (b == null || isNaN(b) || b === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(b) / Math.log(1024));
  return (b / Math.pow(1024, i)).toFixed(i > 1 ? 1 : 0) + " " + (units[i] || "B");
};

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
  else if (tabId === "config") { loadConfig(); loadQueuePreview(); }
  else if (tabId === "docker") loadDocker();
  else if (tabId === "bot_users") loadBotUsers();
  else if (tabId === "terminal") { $("#term-input").focus(); }
  else if (tabId === "sql_console") loadDbTables();
  else if (tabId === "files") loadFiles($("#files-current-path").value);
  else if (tabId === "ffmpeg") loadFFmpeg();
  else if (tabId === "env_editor") loadEnv();
  else if (tabId === "audit") loadAudit();
}

function renderActiveTasks(activeJobs) {
  const list = Array.isArray(activeJobs) ? activeJobs : (activeJobs && activeJobs.items ? activeJobs.items : []);
  const badge = $("#active-tasks-badge");
  if (badge) badge.textContent = `${list.length} تسک`;
  const container = $("#overview-active-tasks");
  if (!container) return;
  if (!list.length) {
    container.innerHTML = '<div class="empty">هیچ کاری در حال پردازش نیست</div>';
    return;
  }
  container.innerHTML = list.map(j => {
    const pct = Math.round(j.progress_pct !== undefined ? j.progress_pct : (j.progress || 0));
    const name = (j.video && (j.video.source_name || j.video.output_name)) || j.file_name || j.name || j.fname || "بدون نام";
    const jid = j.jid || (j.id ? String(j.id).slice(0, 8) : "");
    const profile = j.profile || "default";
    const stage = j.stage || (pct > 0 ? "در حال فشرده‌سازی" : "در صف پردازش");
    return `
      <div style="padding:10px 12px;margin-bottom:8px;background:var(--card-hover);border-radius:10px;border:1px solid var(--border)">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
          <span style="font-weight:600;font-size:0.9rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:70%">${esc(name)}</span>
          <span class="badge" style="background:rgba(232,86,42,0.15);color:var(--acc);border-color:rgba(232,86,42,0.3)"><bdi dir="ltr">${esc(profile)}</bdi></span>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:0.8rem;color:var(--ink-mut);margin-bottom:6px">
          <span class="mono">#${esc(jid)} · ${esc(stage)}</span>
          <span><bdi dir="ltr">${pct}%</bdi></span>
        </div>
        <div class="prog-bar" style="width:100%;height:6px;margin:0"><span style="width:${pct}%"></span></div>
      </div>
    `;
  }).join("");
}

/* Overview and KPIs */
async function loadOverview() {
  try {
    const [summary, metrics, services, activeJobs] = await Promise.all([
      api("/panel/api/summary").catch(() => ({})),
      api("/panel/api/server/metrics").catch(() => ({})),
      api("/panel/api/services").catch(() => ({})),
      api("/panel/api/active").catch(() => ([]))
    ]);

    // KPI values
    const c = summary.counters || {};
    const maxWorkers = c.max_concurrent || 3;
    const maxQueue = c.max_queue || 500;

    // Card 1: Active
    $("#kpi-active").textContent = `${fa(c.active || 0)} / ${fa(maxWorkers)}`;
    const dCnt = c.active_downloads || 0;
    const eCnt = c.active_encodes !== undefined ? c.active_encodes : (c.active || 0);
    const uCnt = c.active_uploads || 0;
    if ($("#kpi-active-sub")) {
      $("#kpi-active-sub").textContent = `${fa(dCnt)} دانلود | ${fa(eCnt)} انکود | ${fa(uCnt)} آپلود`;
    }

    // Card 2: Queued
    $("#kpi-queue").textContent = `${fa(c.queued || 0)} / ${fa(maxQueue)}`;
    const qSub = $("#kpi-queue").parentElement.querySelector(".sub");
    if (qSub) {
      qSub.textContent = c.est_clear_time_fa ? `تخلیه صف: ~${c.est_clear_time_fa}` : "در انتظار نوبت پردازش";
    }

    // Card 3: Completed Today
    $("#kpi-completed").textContent = `${fa(c.completed || 0)} ویدیو`;
    const compSub = $("#kpi-completed").parentElement.querySelector(".sub");
    if (compSub) {
      if (c.bytes_saved_today) {
        const gb = (c.bytes_saved_today / 1073741824).toFixed(1);
        compSub.textContent = `${gb} GB صرفه‌جویی حجم`;
      } else {
        compSub.textContent = "تکمیل موفق ویدیوها";
      }
    }

    // Card 4: Failed Today
    $("#kpi-failed").textContent = `${fa(c.failed || 0)} خطا`;

    if ($("#tab-cnt-active")) $("#tab-cnt-active").textContent = (c.active || 0) + (c.queued || 0);

    if (metrics.disk) {
      $("#kpi-disk").innerHTML = `<bdi dir="ltr">${fa(metrics.disk.free_gb)} GB</bdi> آزاد`;
      $("#kpi-disk-sub").innerHTML = `${fa(metrics.disk.used_percent)}% مصرف (${fa(metrics.disk.total_gb)} GB) <button class="btn" style="padding:2px 8px;font-size:10px;margin-right:6px;" onclick="cleanTempFiles(event)">🧹 پاکسازی موقت</button>`;
    }
    if (metrics.memory) {
      $("#kpi-ram").innerHTML = `<bdi dir="ltr">${fa(metrics.memory.percent)}%</bdi>`;
      $("#kpi-ram-sub").innerHTML = `<bdi dir="ltr">${fa(metrics.memory.used_mb)} MB / ${fa(metrics.memory.total_mb)} MB</bdi>`;
    }
    if (metrics.cpu) {
      $("#kpi-cpu").innerHTML = `<bdi dir="ltr">${fa(metrics.cpu.percent)}%</bdi> <span style="font-size:0.85em">(${metrics.cpu.count} Core)</span>`;
    }
    if (metrics.uptime) {
      $("#kpi-uptime").textContent = `آپ‌تایم: ${fa(metrics.uptime.days)} روز و ${fa(metrics.uptime.hours)} ساعت`;
    }

    // Badge states
    if (services.access_mode != null) {
      const mode = String(services.access_mode).replace(/"/g, "").trim();
      const badge = $("#badge-access");
      if (badge) {
        badge.classList.remove("online", "warn", "danger");
        if (mode === "public") badge.classList.add("online");
        else badge.classList.add("warn");
        badge.innerHTML = mode === "private" ?
          '<svg class="ico" viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg> خصوصی' :
          '<svg class="ico" viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg> عمومی';
      }
    }
    if (services.paused != null) {
      const badge = $("#badge-intake");
      if (badge) {
        badge.classList.remove("online", "danger");
        if (services.paused) badge.classList.add("danger");
        else badge.classList.add("online");
        badge.innerHTML = services.paused ?
          '<svg class="ico" viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none"><rect width="4" height="16" x="6" y="4"/><rect width="4" height="16" x="14" y="4"/></svg> پذیرش متوقف' :
          '<svg class="ico" viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none"><polygon points="6 3 20 12 6 21 6 3"/></svg> پذیرش فعال';
      }
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

    // Populate active tasks in overview
    renderActiveTasks(activeJobs);

    // Recent events
    const auditData = await api("/panel/api/audit?limit=7").catch(() => ({ items: [] }));
    const rows = (auditData.items || []).map(e => `
      <tr>
        <td class="mono"><bdi dir="ltr">${esc((e.ts||"").replace("T"," ").slice(5,19))}</bdi></td>
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
  const status = $("#task-filter-status") ? $("#task-filter-status").value : "active";
  const q = $("#task-filter-q") ? $("#task-filter-q").value.trim() : "";
  try {
    const p = new URLSearchParams();
    p.set("view", status);
    if (q) p.set("q", q);
    p.set("limit", "50");

    let data;
    try {
      data = await api(`/panel/api/v3/jobs?${p.toString()}`);
    } catch (_) {
      const fallbackStatus = status === "active" ? "processing" : (status === "queue" ? "queued" : status);
      data = await api(`/panel/api/jobs?status=${fallbackStatus}&q=${encodeURIComponent(q)}&limit=50`);
    }
    const items = Array.isArray(data) ? data : (data.items || data.jobs || []);
    if ($("#tab-cnt-active")) $("#tab-cnt-active").textContent = items.length;

    const checkAll = $("#check-all-tasks");
    if (checkAll) checkAll.checked = false;
    updateBatchCancelBtn();

    if (!items.length) {
      $("#table-tasks tbody").innerHTML = '<tr><td colspan="9" class="empty">تسک فشرده‌سازی در این بخش یافت نشد.</td></tr>';
      return;
    }

    const stMap = {
      processing: "در حال پردازش",
      queued: "در صف انتظار",
      completed: "تکمیل شده",
      failed: "خطادار / ناموفق",
      cancelled: "لغو شده"
    };

    const rows = items.map(t => {
      const id = t.id || t.job_id || "";
      const jid = t.jid || (typeof id === 'string' ? id.slice(0, 8) : id);
      const name = (t.video && (t.video.source_name || t.video.output_name)) || t.file_name || t.target_name || t.fname || "بدون نام";

      let userStr = "—";
      if (t.user && typeof t.user === "object") {
        const uname = t.user.username ? ` <bdi dir="ltr">(@${esc(t.user.username)})</bdi>` : "";
        userStr = (esc(t.user.name || "") + uname) || (t.user.id ? `<span class="mono">${esc(t.user.id)}</span>` : "—");
      } else {
        const uname = t.username ? ` <bdi dir="ltr">(@${esc(t.username)})</bdi>` : "";
        const displayName = t.first_name || t.user || "";
        userStr = (displayName ? esc(displayName) + uname : "") || (t.user_id || t.tg ? `<span class="mono">${esc(t.user_id || t.tg)}</span>` : "—");
      }

      const st = t.status || "queued";
      const stLabel = t.status_fa || stMap[st] || st;
      const pct = Math.round(t.progress_pct !== undefined ? t.progress_pct : (t.progress || 0));

      const rawSize = (t.video && (t.video.size || t.video.output_size)) || t.source_size || t.size || 0;
      const sizeStr = t.size_human || (rawSize ? fmtBytes(rawSize) : "—");

      const rawTime = t.created_at || (t.timings && t.timings.enqueued_at) || t.enqueued_at || "";
      const timeStr = rawTime ? String(rawTime).slice(0, 19).replace("T", " ") : "—";
      const profileName = t.profile || t.preset || "default";

      let stageBadge = "";
      if (st === 'queued') {
        const pos = t.queue_pos || t.position || '—';
        stageBadge = `<span class="badge" style="color:var(--amber);border-color:rgba(245,158,11,0.35)">جایگاه: ${fa(pos)}</span>`;
      } else if (st === 'processing') {
        const stageFa = t.stage_fa || (t.stage === 'download' ? 'دانلود' : (t.stage === 'upload' ? 'آپلود' : 'انکود'));
        stageBadge = `<div><span class="pill p-processing">${esc(stageFa)}</span> <div class="prog-bar" style="display:inline-block;width:50px;vertical-align:middle;margin:0 4px"><span style="width:${pct}%"></span></div> <bdi dir="ltr">${pct}%</bdi></div>`;
      } else if (st === 'completed') {
        stageBadge = `<span class="pill p-completed">${esc(stLabel)}</span>`;
      } else if (st === 'failed') {
        stageBadge = `<span class="pill p-failed">${esc(stLabel)}</span>`;
      } else {
        stageBadge = `<span class="pill p-${esc(st)}">${esc(stLabel)}</span>`;
      }

      let actionsHtml = "";
      if (st === 'queued') {
        actionsHtml = `<button class="btn pri" style="padding:2px 8px;font-size:11px" onclick="boostJob('${esc(id)}')">🚀 اولویت</button> <button class="btn danger" style="padding:2px 8px;font-size:11px" onclick="cancelJob('${esc(id)}')">❌ لغو</button>`;
      } else if (st === 'processing') {
        actionsHtml = `<button class="btn danger" style="padding:2px 8px;font-size:11px" onclick="cancelJob('${esc(id)}')">❌ لغو</button>`;
      } else if (st === 'failed' || st === 'cancelled') {
        actionsHtml = `<button class="btn success" style="padding:2px 8px;font-size:11px" onclick="retryJob('${esc(id)}')">🔄 تلاش مجدد</button>`;
      } else {
        actionsHtml = '—';
      }

      return `
        <tr>
          <td><input type="checkbox" class="task-check" value="${esc(id)}" onchange="updateBatchCancelBtn()"></td>
          <td class="mono">#${esc(jid)}</td>
          <td>${stageBadge}</td>
          <td><b>${esc(name)}</b></td>
          <td class="mono">${userStr}</td>
          <td><span class="badge"><bdi dir="ltr">${esc(profileName)}</bdi></span></td>
          <td class="mono"><bdi dir="ltr">${esc(sizeStr)}</bdi></td>
          <td class="mono"><bdi dir="ltr">${esc(timeStr)}</bdi></td>
          <td>${actionsHtml}</td>
        </tr>
      `;
    }).join("");
    $("#table-tasks tbody").innerHTML = rows;
  } catch (e) {
    toast(`خطا در بارگذاری تسک‌ها: ${e.message}`, "error");
  }
}

async function cancelJob(id) {
  const shortId = typeof id === 'string' ? id.slice(0, 8) : id;
  if (!confirm(`آیا مطمئن هستید که کار #${shortId} متوقف و لغو شود؟`)) return;
  try {
    await api(`/panel/api/job/${id}/cancel`, { method: "POST" });
    toast(`تسک #${shortId} با موفقیت لغو شد`, "success");
    loadTasks();
    if (currentTab === "overview") loadOverview();
  } catch (e) {
    toast(`خطای لغو کار: ${e.message}`, "error");
  }
}

async function boostJob(id) {
  const shortId = typeof id === 'string' ? id.slice(0, 8) : id;
  try {
    await api(`/panel/api/job/${id}/boost`, { method: "POST" });
    toast(`تسک #${shortId} با موفقیت به صدر صف منتقل شد`, "success");
    loadTasks();
  } catch (e) {
    toast(`خطای اولویت‌دهی: ${e.message}`, "error");
  }
}

async function retryJob(id) {
  const shortId = typeof id === 'string' ? id.slice(0, 8) : id;
  try {
    await api(`/panel/api/job/${id}/retry`, { method: "POST" });
    toast(`تسک #${shortId} برای پردازش مجدد ارسال شد`, "success");
    loadTasks();
  } catch (e) {
    toast(`خطای تلاش مجدد: ${e.message}`, "error");
  }
}

function toggleSelectAllTasks(master) {
  $$(".task-check").forEach(cb => cb.checked = master.checked);
  updateBatchCancelBtn();
}

function updateBatchCancelBtn() {
  const any = $$(".task-check:checked").length;
  const btn = $("#btn-batch-cancel");
  if (btn) btn.style.display = any > 0 ? "inline-block" : "none";
}

async function batchCancelTasks() {
  const selected = Array.from($$(".task-check:checked")).map(cb => cb.value);
  if (!selected.length) return;
  if (!confirm(`آیا از لغو ${selected.length} تسک انتخاب‌شده اطمینان دارید؟`)) return;
  let success = 0;
  for (const id of selected) {
    try {
      await api(`/panel/api/job/${id}/cancel`, { method: "POST" });
      success++;
    } catch (_) {}
  }
  toast(`${success} تسک با موفقیت لغو شدند`, "success");
  loadTasks();
}

async function cleanTempFiles(e) {
  if (e) e.stopPropagation();
  if (!confirm("آیا از پاکسازی تمام فایل‌های موقت دانلود و انکود اطمینان دارید؟")) return;
  try {
    const res = await api("/panel/api/system/cleanup_temp", { method: "POST" });
    toast(res.message || "پاکسازی فایل‌های موقت با موفقیت انجام شد", "success");
    loadOverview();
  } catch (err) {
    toast("خطا در پاکسازی: " + err.message, "danger");
  }
}

/* Dynamic Runtime Config */
async function loadConfig() {
  try {
    const res = await api("/panel/api/config");
    const settings = res.settings || {};
    for (const [k, v] of Object.entries(settings)) {
      const el = $(`#cfg-${k}`);
      if (el) {
        if (el.tagName === "SELECT") {
          el.value = String(v);
        } else {
          el.value = v;
        }
      }
    }
  } catch (e) {
    toast(`خطا در دریافت تنظیمات: ${e.message}`, "error");
  }
}

async function saveDynamicConfig() {
  const keys = [
    "max_queue_size", "max_active_downloads", "active_encoding_workers", "max_active_uploads",
    "queue_scheduling_algorithm", "fairness_starvation_threshold_sec", "fairness_size_bias_weight",
    "queue_card_throttle_sec", "admin_queue_bypass",
    "user_active_job_limit", "vip_active_job_limit", "user_cooldown_seconds",
    "temp_cleanup_threshold_gb", "emergency_disk_threshold_gb", "max_job_retries"
  ];
  const payload = {};
  for (const k of keys) {
    const el = $(`#cfg-${k}`);
    if (el) {
      let val = el.value;
      if (k === "admin_queue_bypass") {
        payload[k] = val === "true";
      } else if (k === "queue_scheduling_algorithm") {
        payload[k] = String(val);
      } else if (k.includes("weight") || k.includes("threshold_gb")) {
        payload[k] = parseFloat(val);
      } else {
        payload[k] = parseInt(val, 10);
      }
    }
  }
  try {
    const res = await api("/panel/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings: payload })
    });
    toast("تنظیمات با موفقیت ذخیره و به صورت آنی اعمال شدند", "success");
    loadOverview();
    loadQueuePreview();
  } catch (e) {
    toast(`خطا در ذخیره تنظیمات: ${e.message}`, "error");
  }
}

async function loadQueuePreview(algorithm) {
  const algo = algorithm !== undefined ? algorithm : ($("#sim-algo-select") ? $("#sim-algo-select").value : "");
  const tbody = $("#table-queue-preview tbody");
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7" class="empty">در حال محاسبه و شبیه‌سازی صف...</td></tr>';
  try {
    const url = algo ? `/panel/api/queue/preview?algorithm=${encodeURIComponent(algo)}` : `/panel/api/queue/preview`;
    const res = await api(url);
    const items = res.preview || res.items || [];
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty">در حال حاضر هیچ کاری در صف انتظار نیست</td></tr>';
      return;
    }
    tbody.innerHTML = items.map((it, idx) => {
      const jid = it.jid || (it.job_id ? String(it.job_id).slice(0, 8) : "—");
      const name = it.user_name || it.username || it.user_id || "کاربر";
      const isVip = Boolean(it.is_vip);
      const sizeStr = it.file_size_bytes ? fmtBytes(it.file_size_bytes) : "—";
      const timeStr = it.enqueued_at ? String(it.enqueued_at).slice(11, 19) : "—";
      const scoreStr = it.computed_score !== undefined ? Number(it.computed_score).toFixed(2) : (it.priority || "50");
      return `
        <tr>
          <td><span class="badge ${idx === 0 ? 'online' : ''}">#${idx + 1}</span></td>
          <td class="mono">#${esc(jid)}</td>
          <td><b>${esc(name)}</b></td>
          <td>${isVip ? '<span class="badge" style="color:var(--amber);border-color:rgba(245,158,11,0.35)">VIP ⭐</span>' : '<span class="badge">عادی</span>'}</td>
          <td class="mono"><bdi dir="ltr">${esc(sizeStr)}</bdi></td>
          <td class="mono">${esc(timeStr)}</td>
          <td class="mono">${esc(scoreStr)}</td>
        </tr>
      `;
    }).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty" style="color:var(--red)">خطا: ${esc(e.message)}</td></tr>`;
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
          <button class="btn" onclick="viewContainerLogs('${esc(c.name)}')"><svg class="ico" viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="2" fill="none"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" x2="8" y1="13" y2="13"/><line x1="16" x2="8" y1="17" y2="17"/><line x1="10" x2="8" y1="9" y2="9"/></svg> لاگ‌ها</button>
          <button class="btn danger" onclick="restartContainer('${esc(c.name)}')"><svg class="ico" viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="2" fill="none"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> ری‌استارت</button>
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
  $("#modal-log-title").innerHTML = `<svg class="ico" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" x2="8" y1="13" y2="13"/><line x1="16" x2="8" y1="17" y2="17"/><line x1="10" x2="8" y1="9" y2="9"/></svg> لاگ‌های کانتینر: ${esc(name)}`;
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
  $("#sql-query-input").value = "SELECT id, status, requester_tg_id, profile, progress, enqueued_at FROM jobs ORDER BY enqueued_at DESC LIMIT 25;";
  runSqlQuery();
};
$("#btn-sql-snippet-users").onclick = () => {
  $("#sql-query-input").value = "SELECT tg_id, first_name, username, total_requests, is_blocked, last_seen_at FROM users ORDER BY total_requests DESC LIMIT 25;";
  runSqlQuery();
};
$("#btn-db-backup").onclick = async () => {
  if (!confirm("آیا بکاپ کامل PostgreSQL (pg_dump) تهیه شود؟")) return;
  toast("در حال ایجاد نسخه پشتیبان پایگاه داده...");
  try {
    const res = await api("/panel/api/super/db/backup", { method: "POST" });
    if (res.ok) {
      toast(`بکاپ در سرور ذخیره شد: ${res.path} (${Math.round((res.size || 0)/1024)} KB)`, "success");
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

    tbody.innerHTML = entries.map(item => {
      const ico = item.is_dir ?
        '<svg class="ico" style="color:var(--amber)" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/></svg>' :
        '<svg class="ico" style="color:var(--ink-mut)" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" x2="8" y1="13" y2="13"/><line x1="16" x2="8" y1="17" y2="17"/><line x1="10" x2="8" y1="9" y2="9"/></svg>';
      return `
        <tr class="clickable">
          <td>
            ${ico}
            <b ${item.is_dir ? `onclick="loadFiles('${esc(item.path)}')"` : ''}>${esc(item.name)}</b>
          </td>
          <td>${item.is_dir ? 'دایرکتوری' : 'فایل'}</td>
          <td class="mono">${item.is_dir ? '—' : (Math.round(item.size/1024) + ' KB')}</td>
          <td class="mono"><bdi dir="ltr">${esc(item.mtime_str)}</bdi></td>
          <td>
            ${!item.is_dir ? `<button class="btn danger" onclick="deleteServerFile('${esc(item.path)}')">حذف</button>` : ''}
          </td>
        </tr>
      `;
    }).join("");
  } catch (e) {
    toast(`خطای مرورگر فایل: ${e.message}`, "error");
  }
}
$("#btn-files-go").onclick = () => loadFiles($("#files-current-path").value.trim());
$("#btn-files-media").onclick = () => loadFiles("/media");
$("#btn-files-opt")?.addEventListener("click", () => loadFiles("/opt/oxmit"));
$("#btn-files-up")?.addEventListener("click", () => {
  let cur = ($("#files-current-path")?.value || "/media").trim().replace(/\/+$/, "");
  let parent = cur.substring(0, cur.lastIndexOf("/")) || "/";
  loadFiles(parent);
});

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
    if (res.ok) {
      toast("تنظیمات FFmpeg با موفقیت بروزرسانی شد", "success");
    } else {
      const errMsgs = Object.entries(res.errors || {}).map(([k, v]) => `${k}: ${v}`).join(", ");
      toast(`خطای ذخیره: ${errMsgs || res.error || "نامعتبر"}`, "error");
    }
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
      toast("فایل .env با موفقیت ذخیره شد", "success");
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
      tbody.innerHTML = '<tr><td colspan="8" class="empty">کاربری یافت نشد</td></tr>';
      return;
    }
    tbody.innerHTML = users.map(u => {
      const tgId = u.tg_id || u.telegram_id || u.id;
      const isBlocked = Boolean(u.is_blocked || u.is_banned);
      const isVip = Boolean(u.is_vip);
      const lastActive = (u.last_seen_at || u.last_activity || u.created_at || '').slice(0, 16).replace('T', ' ');
      const todayJobs = u.jobs24 !== undefined ? u.jobs24 : (u.used_today_files || 0);
      const totalReq = u.total_requests || 0;
      const uname = u.username ? `<bdi dir="ltr">@${esc(u.username)}</bdi>` : '<span style="color:var(--ink-dim)">—</span>';
      const fname = esc(u.first_name || 'بدون نام');

      return `
        <tr>
          <td class="mono"><b>${esc(tgId)}</b></td>
          <td><b>${fname}</b> ${isVip ? '<span class="badge" style="color:var(--amber);border-color:rgba(245,158,11,0.35)">VIP ⭐</span>' : ''}</td>
          <td class="mono">${uname}</td>
          <td class="mono"><bdi dir="ltr">${fa(todayJobs)} کار</bdi></td>
          <td class="mono"><bdi dir="ltr">${fa(totalReq)}</bdi></td>
          <td>
            <span class="badge ${isBlocked ? 'danger' : 'online'}">
              ${isBlocked ? 'مسدود شده' : 'فعال'}
            </span>
          </td>
          <td class="mono"><bdi dir="ltr">${esc(lastActive || '—')}</bdi></td>
          <td>
            <button class="btn ${isBlocked ? 'success' : 'danger'}" style="padding:2px 6px;font-size:11px" onclick="toggleBanUser('${esc(tgId)}', ${!isBlocked})">
              ${isBlocked ? 'آزاد' : 'مسدود'}
            </button>
            <button class="btn ${isVip ? 'warn' : 'pri'}" style="padding:2px 6px;font-size:11px;margin-right:3px" onclick="toggleVipUser('${esc(tgId)}', ${!isVip})">
              ${isVip ? 'لغو VIP' : 'اعطای VIP'}
            </button>
            <button class="btn" style="padding:2px 6px;font-size:11px;margin-right:3px" onclick="setUserQueueLimit('${esc(tgId)}')">
              سقف صف
            </button>
            <button class="btn" style="padding:2px 6px;font-size:11px;margin-right:3px" onclick="sendDirectMessage('${esc(tgId)}')">
              پیام
            </button>
          </td>
        </tr>
      `;
    }).join("");
  } catch (e) {
    toast(`خطای واکشی کاربران: ${e.message}`, "error");
  }
}
$("#btn-user-search").onclick = loadBotUsers;

async function toggleBanUser(tgId, ban) {
  if (!tgId) { toast("شناسه تلگرام نامعتبر است", "error"); return; }
  const actionName = ban ? "مسدودسازی" : "آزادسازی";
  const reason = ban ? prompt("دلیل مسدودسازی کاربر را وارد کنید (اختیاری):", "تخلف از قوانین") : "";
  if (ban && reason === null) return; // user cancelled prompt
  try {
    await api(`/panel/api/bot/user/${tgId}/ban`, {
      method: "POST",
      body: JSON.stringify({ ban, reason: reason || "" })
    });
    toast(`کاربر #${tgId} با موفقیت ${ban ? "مسدود" : "آزاد"} شد`, "success");
    loadBotUsers();
  } catch (e) {
    toast(`خطای ${actionName}: ${e.message}`, "error");
  }
}

async function toggleVipUser(tgId, makeVip) {
  try {
    const res = await api(`/panel/api/user/${tgId}/vip`, { method: "POST" });
    toast(res.new ? "کاربر با موفقیت به VIP ارتقا یافت" : "وضعیت VIP کاربر لغو شد", "success");
    loadBotUsers();
  } catch (e) {
    toast(`خطای تغییر وضعیت VIP: ${e.message}`, "error");
  }
}

async function setUserQueueLimit(tgId) {
  const lim = prompt("سقف مجاز تعداد کارهای همزمان در صف برای این کاربر را وارد کنید (یا خالی برای سهمیه پیش‌فرض):");
  if (lim === null) return;
  const num = lim.trim() === "" ? null : parseInt(lim.trim(), 10);
  try {
    await api(`/panel/api/user/${tgId}/queue_limit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ custom_queue_limit: num })
    });
    toast("سقف صف کاربر با موفقیت بروزرسانی شد", "success");
    loadBotUsers();
  } catch (e) {
    toast(`خطای ثبت سقف صف: ${e.message}`, "error");
  }
}

async function sendDirectMessage(tgId) {
  const text = prompt(`متن پیام مستقیم از طرف ربات به کاربر #${tgId}:`);
  if (!text || !text.trim()) return;
  try {
    await api(`/panel/api/user/${tgId}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text.trim() })
    });
    toast("پیام با موفقیت به کاربر ارسال شد", "success");
  } catch (e) {
    toast(`خطای ارسال پیام: ${e.message}`, "error");
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
    toast("ارسال پیام همگانی آغاز شد", "success");
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
    const currentMode = String(cfg.access_mode || "private").replace(/"/g, "").trim();
    const nextMode = currentMode === "private" ? "public" : "private";
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
  if (!confirm("اخطار جدی: آیا از لغو تمامی کارهای در حال اجرا و صف فشرده‌سازی مطمئن هستید؟")) return;
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

/* Wire Refresh, Filters and Keyboard Listeners */
$("#btn-refresh-svc")?.addEventListener("click", () => loadOverview());
$("#btn-task-refresh")?.addEventListener("click", () => loadTasks());
$("#task-filter-status")?.addEventListener("change", () => loadTasks());
$("#btn-refresh-docker")?.addEventListener("click", () => loadDocker());
$("#btn-refresh-tables")?.addEventListener("click", () => loadDbTables());
$("#btn-audit-refresh")?.addEventListener("click", () => loadAudit());

/* Wire Enter key listeners */
$("#task-filter-q")?.addEventListener("keydown", e => {
  if (e.key === "Enter") {
    e.preventDefault();
    loadTasks();
  }
});
$("#user-search-input")?.addEventListener("keydown", e => {
  if (e.key === "Enter") {
    e.preventDefault();
    loadBotUsers();
  }
});
$("#files-current-path")?.addEventListener("keydown", e => {
  if (e.key === "Enter") {
    e.preventDefault();
    loadFiles($("#files-current-path").value.trim());
  }
});
$("#sql-query-input")?.addEventListener("keydown", e => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    runSqlQuery();
  }
});

/* Modal Dismissals & Keyboard Accessibility */
$("#modal-logs")?.addEventListener("click", e => {
  if (e.target.id === "modal-logs") $("#modal-logs").hidden = true;
});
$("#modal-broadcast")?.addEventListener("click", e => {
  if (e.target.id === "modal-broadcast") $("#modal-broadcast").hidden = true;
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    if ($("#modal-logs")) $("#modal-logs").hidden = true;
    if ($("#modal-broadcast")) $("#modal-broadcast").hidden = true;
  }
});

/* WebSocket Live Connection */
let ws = null;
function initLiveWs() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  try {
    ws = new WebSocket(`${proto}//${location.host}/panel/ws`);
    ws.onopen = () => {
      const dot = $("#dot-ws");
      if (dot) dot.classList.remove("off");
      const txt = $("#text-ws");
      if (txt) txt.textContent = " لایو (WebSocket)";
    };
    ws.onmessage = ev => {
      try {
        const d = JSON.parse(ev.data);
        if (d.summary) {
          const c = d.summary.counters || {};
          $("#kpi-active").textContent = fa(c.active || 0);
          $("#kpi-queue").textContent = fa(c.queued || 0);
          if (c.completed != null) $("#kpi-completed").textContent = fa(c.completed);
          if (c.failed != null) $("#kpi-failed").textContent = fa(c.failed);
        }
        if (d.active && currentTab === "overview") {
          renderActiveTasks(d.active);
        }
      } catch (err) {}
    };
    ws.onclose = () => {
      const dot = $("#dot-ws");
      if (dot) dot.classList.add("off");
      const txt = $("#text-ws");
      if (txt) txt.textContent = " پولینگ (پسیو)";
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
