"""Single-file HTML for the v3 management dashboard (served at /panel).

Fully offline (no CDN / web fonts). All dynamic values are inserted with
textContent or an escaping helper - never as raw HTML.
"""

PAGE = r"""<!doctype html><html dir="rtl" lang="fa"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oxmit — داشبورد</title>
<style>
:root{--bg:#f3f4f8;--card:#fff;--ink:#1d2129;--mut:#7d8394;--line:#e6e8ef;--soft:#f7f8fb;
--acc:#e8562a;--acc-soft:#fdeee7;--ok:#1f9d57;--ok-soft:#e6f6ed;--bad:#d64236;--bad-soft:#fcebea;
--warn:#c98a12;--warn-soft:#fdf4dc;--info:#2f6fd6;--info-soft:#e9f0fc;--shadow:0 6px 24px rgba(20,24,40,.07)}
@media (prefers-color-scheme:dark){:root{--bg:#12141a;--card:#1b1e26;--ink:#e7e9ef;--mut:#959bab;--line:#2a2e39;
--soft:#20242d;--acc-soft:#3a2219;--ok-soft:#173326;--bad-soft:#3a1d1b;--warn-soft:#382d14;--info-soft:#1b2a44;--shadow:none}}
*{box-sizing:border-box;margin:0}
[hidden]{display:none!important}
body{font-family:Tahoma,"Segoe UI",system-ui,sans-serif;background:var(--bg);color:var(--ink);font-size:13.5px;line-height:1.65}
header{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:14px 18px;background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
.logo{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,#ff7a45,var(--acc));color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800}
header h1{font-size:16px}
.badge{font-size:11px;padding:2px 9px;border-radius:99px;background:var(--soft);border:1px solid var(--line);color:var(--mut);white-space:nowrap}
.badge.owner{background:var(--acc-soft);color:var(--acc);border-color:transparent;font-weight:700}
.live{display:inline-flex;align-items:center;gap:6px;color:var(--mut);font-size:12px}
.dot{width:8px;height:8px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 3px var(--ok-soft)}
.dot.off{background:var(--bad);box-shadow:0 0 0 3px var(--bad-soft)}
.sp{flex:1}
a,button{font-family:inherit}
.btn{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:9px;padding:6px 12px;cursor:pointer;font-size:12.5px}
.btn:hover{background:var(--soft)}
.btn.pri{background:var(--acc);border-color:var(--acc);color:#fff}
.btn.danger{background:var(--bad);border-color:var(--bad);color:#fff}
main{padding:16px 18px;max-width:1500px;margin:0 auto}
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(132px,1fr));gap:10px;margin-bottom:14px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:11px 13px;box-shadow:var(--shadow)}
.kpi small{color:var(--mut);font-size:11.5px;display:block}
.kpi b{font-size:20px;display:block;font-variant-numeric:tabular-nums}
.kpi i{font-style:normal;color:var(--mut);font-size:11px}
.tabs{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:10px}
.tab{border:0;background:transparent;padding:7px 13px;border-radius:9px;cursor:pointer;color:var(--mut);font-size:13px}
.tab.on{background:var(--card);color:var(--acc);font-weight:700;box-shadow:var(--shadow);border:1px solid var(--line)}
.tab .n{font-size:10.5px;background:var(--soft);border-radius:99px;padding:0 7px;margin-inline-start:5px;color:var(--mut)}
.filters{display:flex;gap:8px;flex-wrap:wrap;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:9px;margin-bottom:10px}
.filters input{border:1px solid var(--line);background:var(--soft);color:var(--ink);border-radius:8px;padding:6px 9px;font-family:inherit;font-size:12.5px;min-width:0}
.filters label{font-size:11.5px;color:var(--mut)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);overflow:hidden}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{background:var(--soft);color:var(--mut);font-weight:600;text-align:right;padding:8px 10px;white-space:nowrap;border-bottom:1px solid var(--line)}
td{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
tr.row{cursor:pointer}
tr.row:hover td{background:var(--soft)}
.mut{color:var(--mut);font-size:11.5px}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;direction:ltr;unicode-bidi:isolate}
.ltr{direction:ltr;unicode-bidi:isolate;display:inline-block}
bdi{unicode-bidi:isolate}
.pill{display:inline-block;font-size:11px;border-radius:99px;padding:1px 8px;white-space:nowrap}
.p-queued{background:var(--warn-soft);color:var(--warn)}.p-processing{background:var(--info-soft);color:var(--info)}
.p-completed{background:var(--ok-soft);color:var(--ok)}.p-failed{background:var(--bad-soft);color:var(--bad)}
.p-cancelled{background:var(--soft);color:var(--mut)}.p-heavy{background:var(--bad-soft);color:var(--bad)}
.bar{height:6px;border-radius:99px;background:var(--soft);overflow:hidden;min-width:80px;margin-top:4px}
.bar span{display:block;height:100%;background:linear-gradient(90deg,#ff7a45,var(--acc))}
.empty{padding:28px;text-align:center;color:var(--mut)}
.pager{display:flex;gap:8px;align-items:center;justify-content:flex-end;padding:9px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media (max-width:820px){.grid2{grid-template-columns:1fr}}
.slot{display:flex;gap:10px;align-items:center;padding:10px 12px;border-bottom:1px solid var(--line)}
.slot:last-child{border-bottom:0}
.drawer{position:fixed;inset:0;background:rgba(10,12,18,.45);display:flex;justify-content:flex-start;z-index:20}
.panel{width:min(560px,100%);height:100%;overflow:auto;background:var(--card);padding:18px;box-shadow:var(--shadow)}
.panel h2{font-size:15px;margin-bottom:6px}
.kv{display:grid;grid-template-columns:150px 1fr;gap:4px 10px;font-size:12.5px;margin:10px 0}
.kv div:nth-child(odd){color:var(--mut)}
.tl{border-inline-start:2px solid var(--line);margin:8px 6px;padding-inline-start:12px}
.tl div{margin:4px 0;font-size:12.5px}
.tl div b{display:inline-block;min-width:170px;font-weight:600}
.err{background:var(--bad-soft);color:var(--bad);border-radius:9px;padding:8px 10px;font-size:12px;margin:8px 0;word-break:break-word}
@media (max-width:640px){main{padding:12px}header{padding:10px 12px}.kv{grid-template-columns:120px 1fr}}
</style></head><body>
<header>
  <div class="logo">O</div><h1>داشبورد فشرده‌سازی</h1>
  <span class="badge" id="role">…</span>
  <span class="live"><span class="dot" id="dot"></span><span id="upd">—</span></span>
  <span class="sp"></span>
  <a class="btn" href="/panel/legacy">پنل قدیمی</a>
  <button class="btn" id="logout">خروج</button>
</header>
<main>
  <section class="kpis" id="kpis"></section>
  <nav class="tabs" id="tabs"></nav>
  <div class="filters" id="filters">
    <input id="f-q" placeholder="شناسه کار / نام فایل" size="22">
    <input id="f-user" placeholder="آیدی عددی یا @username" size="20">
    <label>از <input id="f-from" type="date"></label>
    <label>تا <input id="f-to" type="date"></label>
    <button class="btn pri" id="f-go">اعمال</button>
    <button class="btn" id="f-clear">پاک‌کردن</button>
  </div>
  <section id="view"></section>
</main>
<div class="drawer" id="drawer" hidden><div class="panel" id="dpanel"></div></div>
<script>
"use strict";
const $=s=>document.querySelector(s);
const esc=v=>String(v==null?"":v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
const fa=n=>n==null?"—":Number(n).toLocaleString("fa-IR");
function size(b){if(b==null)return"—";const u=["B","KB","MB","GB","TB"];let i=0;b=Number(b);while(b>=1024&&i<4){b/=1024;i++}return`<span class="ltr">${b.toFixed(i?1:0)} ${u[i]}</span>`}
function dur(s){if(s==null)return"—";s=Math.max(0,Math.round(s));const h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=s%60;return`<span class="ltr">${h?`${h}:${String(m).padStart(2,"0")}:${String(x).padStart(2,"0")}`:`${m}:${String(x).padStart(2,"0")}`}</span>`}
function when(t){if(!t)return"—";const d=new Date(t);return d.toLocaleString("fa-IR",{dateStyle:"short",timeStyle:"medium"})}
function csrf(){const m=document.cookie.match(/(?:^|; )oxmit_csrf=([^;]+)/);return m?decodeURIComponent(m[1]):""}
async function api(p,opt){const r=await fetch(p,opt);if(r.status===401){location.reload();throw new Error("auth")}if(!r.ok){let e={};try{e=await r.json()}catch(_){}throw new Error(e.error||r.status)}return r.json()}
const ST={queued:"در صف",processing:"در حال پردازش",completed:"تکمیل",failed:"ناموفق",cancelled:"لغو"};
const STAGE={queued:"در صف",reserved:"رزرو",downloading:"دانلود",probing:"تحلیل",checking:"بررسی تکرار",copying:"آماده‌سازی",encoding:"فشرده‌سازی",validating:"اعتبارسنجی",completing:"اعتبارسنجی",archiving:"آپلود",uploading:"آپلود",upload_retry:"تلاش مجدد آپلود",delivering:"تحویل",completed:"تحویل شد",failed:"ناموفق",cancelled:"لغو"};
const nm=n=>{n=String(n==null?"":n);const m=/^(.*?)(\.[A-Za-z0-9]{1,5})$/.exec(n);if(m&&/[֐-ࣿיִ-ﻼ]/.test(m[1]))return`<span dir="rtl"><bdi>${esc(m[1])}</bdi><bdi dir="ltr">${esc(m[2])}</bdi></span>`;return`<bdi dir="${/^[^A-Za-z]*[֐-ࣿ]/.test(n)?"rtl":"ltr"}">${esc(n)}</bdi>`};
const pill=s=>`<span class="pill p-${esc(s)}">${esc(ST[s]||s)}</span>`;
const TABS=[["active","پردازش فعال"],["queue","صف انتظار"],["completed","تکمیل‌شده"],["failed","ناموفق"],["cancelled","لغوشده"],["users","کاربران"],["moderation","مدیریت محتوا"],["system","سیستم"]];
let tab="active",offset=0,me={role:"admin"},sys=null,timer=null;
const LIMIT=100;
function filt(){const q=new URLSearchParams();for(const[k,id]of[["q","#f-q"],["user","#f-user"],["from","#f-from"],["to","#f-to"]]){const v=$(id).value.trim();if(v)q.set(k,v)}return q}
function renderTabs(){$("#tabs").innerHTML=TABS.map(([k,l])=>{let n="";if(sys){if(k==="active")n=sys.processing;if(k==="queue")n=sys.queued}return`<button class="tab ${k===tab?"on":""}" data-t="${k}">${l}${n!==""?`<span class="n">${fa(n)}</span>`:""}</button>`}).join("");
$("#filters").hidden=["system","moderation"].includes(tab)}
$("#tabs").addEventListener("click",e=>{const b=e.target.closest(".tab");if(!b)return;tab=b.dataset.t;offset=0;renderTabs();load()});
$("#f-go").onclick=()=>{offset=0;load()};$("#f-clear").onclick=()=>{for(const id of["#f-q","#f-user","#f-from","#f-to"])$(id).value="";offset=0;load()};
$("#logout").onclick=async()=>{await fetch("/panel/logout",{method:"POST",headers:{"X-CSRF":csrf()}});location.reload()};
function kpis(s){const t=s.throughput;const k=[["در صف",fa(s.queued),`ظرفیت ${fa(s.queue_capacity)}`],["پردازشگرها",`${fa(s.slots_busy)}/${fa(s.slots_total)}`,s.paused?"⏸ پذیرش متوقف":"▶️ پذیرش فعال"],["تکمیل ۱ساعت",fa(t.completed_1h),`۲۴ساعت: ${fa(t.completed_24h)}`],["ناموفق ۲۴ساعت",fa(t.failed_24h),""],["میانگین انتظار",dur(t.avg_wait_s),"۲۴ ساعت اخیر"],["میانگین پردازش",dur(t.avg_processing_s),`${t.sec_per_media_sec} ث/ث ویدیو`],["CPU",s.cpu_pct==null?"—":s.cpu_pct+"%",s.load?`<span class="ltr">load ${s.load.map(Number).join(" / ")}</span>`:""],["RAM",s.ram_pct==null?"—":s.ram_pct+"%",s.ram_total?size(s.ram_used)+" / "+size(s.ram_total):""],["دیسک آزاد",size(s.disk_free),`${s.disk_pct}% پر`]];
$("#kpis").innerHTML=k.map(([a,b,c])=>`<div class="kpi"><small>${a}</small><b>${b}</b><i>${c}</i></div>`).join("")}
function userCell(u){return`${esc(u.name||"?")} ${u.username?`<span class="mut">@${esc(u.username)}</span>`:""}<div class="mono">${esc(u.id)}${u.banned?' <span class="pill p-failed">بن</span>':""}${u.vip?' <span class="pill p-queued">VIP</span>':""}</div>`}
function videoCell(j){const v=j.video;return`${nm(v.output_name)}<div class="mut">${nm(v.source_name||"")}</div><div class="mut">${size(v.size)} · ${dur(v.duration_s)} · <span class="ltr">${esc(v.resolution||"؟")}</span>${v.vcodec?" · "+esc(v.vcodec):""}${v.fps?" · "+esc(v.fps)+"fps":""}</div>`}
function jobsTable(data){const v=tab;if(!data.items.length)return`<div class="empty">موردی یافت نشد</div>`;
const head={active:["کار","کاربر","ویدیو","مرحله","ثبت","انتظار","پردازش","پردازشگر"],queue:["جایگاه","کار","کاربر","ویدیو","ثبت","زمان انتظار تا کنون"],completed:["کار","کاربر","ویدیو","حجم خروجی","ثبت","انتظار","پردازش","تحویل"],failed:["کار","کاربر","ویدیو","خطا","تلاش","ثبت"],cancelled:["کار","کاربر","ویدیو","دلیل","ثبت"]}[v]||["کار","کاربر","ویدیو","وضعیت","ثبت"];
const rows=data.items.map(j=>{const id=`<span class="mono">${esc(j.jid)}</span>${j.reused?' <span class="pill p-completed">کش</span>':""}`;let c;
if(v==="active")c=[id,userCell(j.user),videoCell(j),`${esc(STAGE[j.stage]||j.stage)}${j.stage==="encoding"?`<div class="bar"><span style="width:${Math.min(100,j.progress)}%"></span></div><span class="mut">${fa(j.progress)}%</span>`:""}`,when(j.ts.enqueued_at),dur(j.wait_s),dur(j.processing_s),`<span class="mono">${esc(j.worker||"")}</span>`];
else if(v==="queue")c=[`<b>${fa(j.position)}</b><div class="mut">${fa(j.ahead)} جلوتر</div>`,id,userCell(j.user),videoCell(j),when(j.ts.enqueued_at),dur(j.wait_s)];
else if(v==="completed")c=[id,userCell(j.user),videoCell(j),`${size(j.video.output_size)}${j.video.size&&j.video.output_size?`<div class="mut">−${Math.max(0,Math.round(100-100*j.video.output_size/j.video.size))}%</div>`:""}`,when(j.ts.enqueued_at),dur(j.wait_s),dur(j.processing_s),when(j.ts.delivered_at||j.ts.completed_at)];
else if(v==="failed")c=[id,userCell(j.user),videoCell(j),`<span class="pill p-failed">${esc(j.error?j.error.category:"")}</span><div class="mut">${esc(j.error?j.error.message.slice(0,140):"")}</div>`,fa(j.retries),when(j.ts.enqueued_at)];
else if(v==="cancelled")c=[id,userCell(j.user),videoCell(j),esc(j.cancel_reason||"—"),when(j.ts.enqueued_at)];
else c=[id,userCell(j.user),videoCell(j),pill(j.status),when(j.ts.enqueued_at)];
return`<tr class="row" data-id="${esc(j.id)}">${c.map(x=>`<td>${x}</td>`).join("")}</tr>`}).join("");
const pages=`<div class="pager"><span class="mut">${fa(offset+1)}–${fa(offset+data.items.length)} از ${fa(data.total)}</span><button class="btn" id="pv" ${offset?"":"disabled"}>قبلی</button><button class="btn" id="nx" ${offset+LIMIT<data.total?"":"disabled"}>بعدی</button></div>`;
return`<div class="scroll"><table><thead><tr>${head.map(h=>`<th>${h}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>${pages}`}
function usersTable(d){if(!d.items.length)return`<div class="empty">کاربری یافت نشد</div>`;return`<div class="mut" style="padding:8px 10px">«پرتکرار» = ≥ ${fa(d.heavy_threshold)} درخواست در ۲۴ ساعت</div><div class="scroll"><table><thead><tr><th>کاربر</th><th>۲۴ ساعت</th><th>در صف/فعال</th><th>تکمیل</th><th>ناموفق</th><th>کل</th><th>حجم ۲۴ساعت</th><th>آخرین فعالیت</th><th>وضعیت</th></tr></thead><tbody>${d.items.map(u=>`<tr class="row" data-user="${esc(u.id)}"><td>${esc(u.name||"?")} ${u.username?`<span class="mut">@${esc(u.username)}</span>`:""}<div class="mono">${esc(u.id)}</div></td><td><b>${fa(u.jobs24)}</b> ${u.heavy?'<span class="pill p-heavy">پرتکرار</span>':""}</td><td>${fa(u.pending)}</td><td>${fa(u.done)}</td><td>${fa(u.failed)}</td><td>${fa(u.total)}</td><td>${size(u.bytes24)}</td><td>${when(u.last_seen)}</td><td>${u.banned?`<span class="pill p-failed">بن</span><div class="mut">${esc(u.ban_reason||"")}</div>`:u.admin?'<span class="pill p-processing">ادمین</span>':'<span class="pill p-completed">فعال</span>'}</td></tr>`).join("")}</tbody></table></div>`}
function modView(d){const a=d.actions.length?`<div class="scroll"><table><thead><tr><th>زمان</th><th>کاربر</th><th>کار</th><th>اقدام</th><th>وضعیت کار هنگام اقدام</th><th>توسط</th><th>جزئیات</th></tr></thead><tbody>${d.actions.map(x=>`<tr class="row" data-id="${esc(x.job||"")}"><td>${when(x.at)}</td><td>${esc(x.name||"?")} ${x.username?"@"+esc(x.username):""}<div class="mono">${esc(x.user)}</div></td><td class="mono">${esc((x.job||"").slice(0,8))}</td><td>${x.action==="remove_and_ban"?"حذف ویدیو + بن":esc(x.action)}</td><td>${esc(ST[x.status_before]||x.status_before||"")} / ${esc(STAGE[x.stage_before]||x.stage_before||"")}</td><td class="mono">${esc(x.actor||"")}</td><td class="mut">${esc(x.details||"")}${x.still_banned?"":" (رفع بن شده)"}</td></tr>`).join("")}</tbody></table></div>`:`<div class="empty">هنوز اقدامی ثبت نشده</div>`;
const b=d.banned.length?`<div class="scroll"><table><thead><tr><th>کاربر</th><th>زمان بن</th><th>دلیل</th></tr></thead><tbody>${d.banned.map(x=>`<tr><td>${esc(x.name||"?")} ${x.username?"@"+esc(x.username):""}<div class="mono">${esc(x.id)}</div></td><td>${when(x.at)}</td><td>${esc(x.reason||"—")}</td></tr>`).join("")}</tbody></table></div>`:`<div class="empty">کاربر مسدودی وجود ندارد</div>`;
return`<div class="grid2"><div class="card"><h3 style="padding:10px 12px;font-size:13px">تاریخچهٔ اقدامات</h3>${a}</div><div class="card"><h3 style="padding:10px 12px;font-size:13px">کاربران مسدود</h3>${b}</div></div>`}
function sysView(s){const w=s.workers.length?s.workers.map(x=>`<div class="slot row" data-id="${esc(x.job)}"><span class="pill p-processing">${esc(STAGE[x.stage]||x.stage)}</span><div style="flex:1"><b>${nm(x.name)}</b><div class="mut">${esc(x.user||"?")} · <span class="mono">${esc(x.user_id)}</span> · از ${when(x.since)}</div>${x.stage==="encoding"?`<div class="bar"><span style="width:${Math.min(100,x.progress)}%"></span></div>`:""}</div><span class="mono">${esc(x.jid)}</span></div>`).join(""):`<div class="empty">همهٔ پردازشگرها آزادند</div>`;
const st=Object.entries(s.stages||{}).map(([k,v])=>`<div>${esc(STAGE[k]||k)}</div><div>${fa(v)}</div>`).join("");
return`<div class="grid2"><div class="card"><h3 style="padding:10px 12px;font-size:13px">اسلات‌های پردازش (${fa(s.slots_busy)}/${fa(s.slots_total)}${s.prefetch?` + پیش‌دریافت ${fa(s.prefetch)}`:""})</h3>${w}</div><div class="card" style="padding:12px"><h3 style="font-size:13px">وضعیت سامانه</h3><div class="kv"><div>پروفایل فعال</div><div class="mono">${esc(s.profile)}</div><div>صف Encore</div><div>${fa(s.encore_queue)}</div><div>مراحل جاری</div><div><div class="kv" style="margin:0;grid-template-columns:120px 1fr">${st||"—"}</div></div><div>آپ‌تایم</div><div>${dur(s.uptime_s)}</div><div>هسته‌ها</div><div>${fa(s.cores)}</div><div>دیسک</div><div>${size(s.disk_free)} آزاد از ${size(s.disk_total)}</div></div></div></div>`}
async function load(){clearTimeout(timer);try{
  const s=await api("/panel/api/v3/system");sys=s;kpis(s);renderTabs();
  let html="";
  if(tab==="system")html=sysView(s);
  else if(tab==="users"){const q=$("#f-user").value.trim()||$("#f-q").value.trim();html=usersTable(await api("/panel/api/v3/users"+(q?"?q="+encodeURIComponent(q):"")))}
  else if(tab==="moderation")html=modView(await api("/panel/api/v3/moderation"));
  else{const q=filt();q.set("view",tab);q.set("limit",LIMIT);q.set("offset",offset);html=jobsTable(await api("/panel/api/v3/jobs?"+q))}
  $("#view").innerHTML=`<div class="card">${html}</div>`;
  const pv=$("#pv"),nx=$("#nx");if(pv)pv.onclick=()=>{offset=Math.max(0,offset-LIMIT);load()};if(nx)nx.onclick=()=>{offset+=LIMIT;load()};
  $("#dot").classList.remove("off");$("#upd").textContent="به‌روزرسانی "+new Date().toLocaleTimeString("fa-IR");
}catch(e){$("#dot").classList.add("off");$("#upd").textContent="خطای ارتباط"}
 const fast=["active","queue","system"].includes(tab);timer=setTimeout(load,document.hidden?30000:(fast?4000:15000))}
$("#view").addEventListener("click",e=>{const r=e.target.closest("[data-id]");if(r&&r.dataset.id)return openJob(r.dataset.id);const u=e.target.closest("[data-user]");if(u){$("#f-user").value=u.dataset.user;tab="all";offset=0;renderTabs();load()}});
$("#drawer").addEventListener("click",e=>{if(e.target.id==="drawer")$("#drawer").hidden=true});
async function openJob(id){let j;try{j=await api("/panel/api/v3/job/"+encodeURIComponent(id))}catch(e){return}
const t=j.ts,v=j.video;const tl=[["ثبت درخواست",t.enqueued_at],["ورود به پردازشگر (رزرو)",t.reserved_at],["شروع دانلود",t.download_started_at],["پایان دانلود",t.download_completed||t.download_done_at],["شروع فشرده‌سازی",t.encode_started_at],["پایان فشرده‌سازی",t.encode_done_at],["شروع آپلود",t.upload_started_at],["تحویل به کاربر",t.delivered_at],["پایان",t.completed_at]];
$("#dpanel").innerHTML=`<div style="display:flex;gap:8px;align-items:center"><h2>کار <span class="mono">${esc(j.id)}</span></h2><span class="sp"></span><button class="btn" id="dclose">بستن</button></div>
${pill(j.status)} <span class="badge">${esc(STAGE[j.stage]||j.stage||"")}</span> <span class="badge">${esc(j.profile)}</span>
${j.error?`<div class="err"><b>${esc(j.error.category||"")}</b> — ${esc(j.error.message||"")}</div>`:""}
<div class="kv"><div>کاربر</div><div>${userCell(j.user)}</div><div>نام اصلی فایل</div><div>${nm(v.source_name||"—")}</div><div>نام خروجی</div><div>${nm(v.output_name)}</div><div>حجم اصلی</div><div>${size(v.size)}</div><div>حجم خروجی</div><div>${size(v.output_size)}</div><div>مدت ویدیو</div><div>${dur(v.duration_s)}</div><div>رزولوشن</div><div>${esc(v.resolution||"—")}</div><div>کدک / fps</div><div>${esc(v.vcodec||"—")} / ${esc(v.acodec||"—")} · ${esc(v.fps||"—")}</div><div>تصمیم</div><div>${esc(j.decision||"—")}</div><div>جایگاه در صف</div><div>${j.position?fa(j.position)+" ("+fa(j.ahead)+" جلوتر)":"—"}</div><div>کل انتظار</div><div>${dur(j.wait_s)}</div><div>کل پردازش</div><div>${dur(j.processing_s)}</div><div>زمان فشرده‌سازی</div><div>${dur(j.encode_s)}</div><div>پیشرفت</div><div>${fa(j.progress)}%</div><div>پردازشگر</div><div class="mono">${esc(j.worker||"—")}</div><div>تلاش مجدد</div><div>${fa(j.retries)} (آپلود: ${fa(j.upload_attempts)})</div><div>دلیل لغو</div><div>${esc(j.cancel_reason||"—")}</div></div>
<h3 style="font-size:13px">زمان‌بندی</h3><div class="tl">${tl.map(([a,b])=>`<div><b>${a}</b>${when(b)}</div>`).join("")}</div>
<h3 style="font-size:13px">درخواست‌کنندگان</h3><div class="tl">${(j.requesters||[]).map(r=>`<div>${esc(r.name||"?")} <span class="mono">${esc(r.id)}</span> — ${r.delivered?"تحویل شد":"در انتظار"}</div>`).join("")||"—"}</div>
<h3 style="font-size:13px">تحویل‌ها</h3><div class="tl">${(j.deliveries||[]).map(d=>`<div>${when(d.at)} — <span class="mono">${esc(d.id)}</span> · ${esc(d.method||"")} · ${esc(d.status)}</div>`).join("")||"—"}</div>
${me.role==="owner"?`<div style="margin-top:14px"><button class="btn danger" id="dmod">🗑 حذف ویدیو و مسدودسازی کاربر</button><div class="mut">کار متوقف و فایل‌های همین کار حذف می‌شوند؛ کاربر به‌طور دائم مسدود می‌شود.</div></div>`:""}`;
$("#drawer").hidden=false;$("#dclose").onclick=()=>{$("#drawer").hidden=true};
const m=$("#dmod");if(m)m.onclick=async()=>{if(!confirm("حذف ویدیو و مسدودسازی کاربر "+j.user.id+"؟"))return;try{const r=await api("/panel/api/v3/job/"+encodeURIComponent(j.id)+"/moderate",{method:"POST",headers:{"X-CSRF":csrf()}});alert(r.already?"قبلاً اعمال شده بود":"انجام شد");$("#drawer").hidden=true;load()}catch(e){alert("خطا: "+e.message)}}}
document.addEventListener("visibilitychange",()=>{if(!document.hidden)load()});
(async()=>{try{me=await api("/panel/api/v3/me")}catch(e){}const r=$("#role");r.textContent=me.role==="owner"?"مالک":"ادمین";if(me.role==="owner")r.classList.add("owner");renderTabs();load()})();
</script></body></html>
"""
