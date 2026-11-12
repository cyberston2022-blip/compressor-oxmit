# OXMIT — UX/UI Implementation Report
**Date:** 2026-11-06 · **Spec:** `docs/OXMIT_UX_UI_REDESIGN_SPEC.md` · **Backend reference:** `docs/ARGON_INTEGRATION_AND_UX_FLOW_AUDIT.md`
**Status:** implemented + tested (194/194 local, 194/194 server after deploy). **NOT deployed to production / container NOT restarted** — awaiting owner authorization (deployment instructions in §21).

---

## 1. Executive Summary

The role-aware navigation layer, Personal Branding Center, guided merge feedback, actionable permission denials, and the compression UX improvements from the redesign spec are now implemented in the existing aiogram codebase. The compression pipeline, permissions backend, merge ordering, and branding isolation are untouched — every change is a presentation/navigation layer over the live handlers, plus one small staged-progress addition inside `engine.merge_job`.

## 2. Baseline
- Git: branch `performance/size-speed-optimization` @ `ec16406`, 51 modified/untracked files (multi-round uncommitted work — preserved; no branch juggling, stage backups exist on the server).
- Baseline tests before this round: **186 passed / 0 failed** (local + server).
- Production container state at start: running the previous build (argon features active), healthy.

## 3. Final Architecture

New router **`nav`** (`bot/oxmit/handlers/nav.py`), registered `menu → settings → nav → owner → personal → adminpanel → admin → merge → intake` (`bot.py`). It handles only commands/callbacks in the NEW `menu:` and `den:` namespaces plus `/branding`, `/myjobs` — no media handlers, so intake/merge routing is untouched. The branding hub reaches the personal editors through two integration points:
- `pr:thumb|wm|cap` callbacks handled inside `personal.py` (shared starters `_start_thumb/_start_wm/_start_cap` used by both commands and callbacks);
- `nav.bind_personal_router(personal_router)` — set in `bot.py` — exposes `api_render_wm_preview(chat_id, uid, caption)` for the branding overview.

## 4. New Commands
| Command | Scope | Behavior |
|---|---|---|
| `/menu` | everyone | role-aware hub (SCR-M0) |
| `/help` | everyone | 5-section Persian help (SCR-H2) |
| `/myjobs` | everyone | last 5 of OWN jobs (requester or job_requesters membership), status icons, 8-char id prefix only |
| `/branding` | permitted admins | alias of the branding hub (SCR-B0) |

Command registration (`engine.refresh_admin_commands`) rewritten: default scope = `start, menu, myjobs, settings, help` (clean Persian descriptions — mojibake fixed); admin scope adds `admin, panel, branding, thumb, wm, cap, merge`; the Owner's own scope additionally gets `owner`. Typed commands still run real permission checks.

## 5. New Menu Structure (role tables)
- **Regular:** راهنمای فشرده‌سازی · کارهای من · تنظیمات · راهنما
- **VIP:** + مزایای VIP (real tier values from `tiers_config()`, "VIP never grants admin powers" note)
- **Admin:** + برندینگ من (only if ≥1 branding perm; sub-entries per grant) · ادغام ویدیوها (`merge.use`) · ادغام+فشرده‌سازی (`merge_compress.use`) · پنل عملیات
- **Owner:** everything + 👑 مدیریت Owner
Visibility is computed per request via `permissions.effective_perms`; hidden ≠ authorized (handlers re-check).

## 6. Branding Center
`menu:branding`/`/branding` → overview reading `admin_settings` verbatim with four honest states (not configured / configured-disabled / enabled / asset-file-missing for thumbnails), the isolation explainer, and the split-part warning. Entries: `pr:thumb`, `pr:wm`, `pr:cap` (permission-checked), plus `menu:bpreview` — the overview preview sends (a) the stored personal thumbnail photo, (b) the existing white-canvas watermark preview (labeled "approximate"), (c) the caption text. **No configuration is mutated by the preview.**

## 7. Watermark Navigation
`/wm` now opens a grouped main screen: 🧩 پایه · 🎨 ظاهر · 📐 موقعیت · ⏱ زمان‌بندی · 👁 پیش‌نمایش · 🔁 فعال/غیرفعال · ♻️ بازنشانی. Groups route via NEW callbacks `wm:group:basic|look|pos|timing`; all existing callbacks (`wm:type/text/size/opacity/border/img/font`, `wmpos:`, `wmm:`, `wmt:`) and value ranges are preserved; value edits return to the grouped main screen. Persian-digit inputs normalized via `texts.normalize_digits` (added `wm_scale` input 10..100% → 0.1..1.0).

## 8. Compression UX
- Info card restructured (`🎬 name / size / duration / resolution` + separated details line) — no information removed.
- Option labels: 🟢 سبک / 🟡 متعادل / 🎯 حجم دلخواه / 🎚 درجه فشرده‌سازی — ۱ تا ۲۰ (profile keys & callbacks unchanged; estimates stay ranges).
- **Merged warning+cache card (P0):** when the already-compressed heuristic fires, intake now probes for a cached version FIRST (fuzzy identity match via `dedup.find_fuzzy_source`, before any hashing). If found → ONE combined card (cache details + "re-compressing won't help much" + 📩 `reuse:{key}` / 🎛 `cprof:{key}` / ⚔️ Rostam / ❌) — the offer entry uses the exact same shape as the submission-time offers, so `reuse:`/`cprof:`/`cq:` handlers work unchanged. If no cache → the single concise warning card (Rostam/remux), as before.
- Stage labels user-ized (آماده‌سازی / انتظار در صف / فشرده‌سازی / بررسی کیفیت خروجی / ذخیره‌سازی / ارسال فایل); completion summary header → "✅ پردازش ویدیو با موفقیت انجام شد." (fields unchanged, reuse/new distinction kept).

## 9. Merge UX
- Upload echo now includes the **active-session banner**, running total (count + size), and the **actual DB order** (`merge_items.seq`) as `۱. name → ۲. name → …` (spec §11.3/11.4).
- `engine.merge_job` sends ONE status message and edits it through real stages: آماده‌سازی → بررسی سازگاری → ادغام (+ human strategy line: ⚡ کپی سریع / 🎞 بازانکود) → اعتبارسنجی → آماده‌سازی ارسال. No invented percentages. Status message deleted after completion.
- Merge-only completion now sends the real summary (count, final duration, size, method) with the **[🎬 فشرده‌سازی همین خروجی]** button → `mg:compress:{session}` (NEW): re-checks session ownership, `completed` status, file existence, and `merge_compress.use` before submitting the stored result through `handle_submission` (duplicate-job safety via the existing in-flight dedup/admission).

## 10. Merge + Compress
`/merge compress [mb]` syntax unchanged (backward compatible; explicit target skips re-asking). Menu entry routes to the same command with a hint. Progress: merge stages → bridge message (`mrg_compress_started`) → the standard compression card takes over. Cache-offer/admission/dedup behave exactly as for any submission.

## 11. My Jobs
`nav._jobs_text`: single parameterized query over `jobs` LEFT JOIN `media_assets`, filtered by `requester_tg_id = $1 OR EXISTS(job_requesters …)` — a user sees only their own relationship. Status mapping is restricted to the 6 real DB statuses; filename trimmed; id shown as 8-char prefix; no paths/tokens/other users' data. Refresh = re-render.

## 12. VIP Screen
`menu:vip` renders the VIP tier from `engine.tiers_config()` (12h / 20GB / 4 / 30 / priority 60 by default) with the "higher limits, never admin powers" note. No invented usage counters; no expiry promises.

## 13. Owner Permission Matrix
`own:matrix` (NEW, read-only, owner-checked): every admin × the 6 permission keys as ✅/❌ lines (Persian short labels) + [مدیریت] jumps per admin into the existing per-admin screen. No mutations from the matrix.

## 14. Permission Requests
`den:req:{feature}` (NEW): validates the key, re-checks denial, requires admin, DB-backed anti-spam (counts `admin.perm_request` audit rows in the last 24 h, limit 3/day — no new table), notifies **only the Owner** (cfg id, or first-admin fallback) with a jump button, audits the request, confirms to the requester. Wired into: personal `_require`, intake `pk:` denial, merge denials.

## 15. Error and Recovery UX
Denial copy standardized (`den_text`), watermark-failure honesty lines already present, merge failure copy points to preserved inputs, expired-input states reuse the existing `cancel_expired` pattern. No tracebacks/FFmpeg output are reachable from user cards (existing redaction kept).

## 16. Source Code Changes

| File | Functions/Classes | Changes | Reason |
|---|---|---|---|
| `bot/oxmit/handlers/nav.py` | NEW router; `build_role_menu`, `send_denial`, `on_menu*`, `_show_branding`, `on_den_request`, `on_myjobs` | NEW | navigation hub, my-jobs, VIP, branding overview, denial workflow |
| `bot/oxmit/handlers/personal.py` | `_start_thumb/_start_wm/_start_cap`, `on_pr_*`, `on_wm_group`, `api_render_wm_preview`, `_require` | rewritten | **fixed full-file mojibake corruption** (PowerShell encoding accident from the previous round — position labels and all Persian strings were double-encoded on the server), + grouped watermark nav, pr: entries, digits, denial |
| `bot/oxmit/handlers/intake.py` | `on_media`, `on_profile_pick` | precache combined card (fuzzy cache lookup before hashing), card/details copy, level label, denial wiring | duplicate-warning elimination, P0 spec |
| `bot/oxmit/handlers/merge_flow.py` | `on_merge_video`, `on_mg_compress_this` (NEW), `_throttled` | banner + order + totals echo; compress-existing-result action | merge UX spec §11/§12.5 |
| `bot/oxmit/handlers/owner.py` | `on_owner_matrix` (NEW), `_main_kb` | matrix report + button | owner visibility |
| `bot/oxmit/engine.py` | `refresh_admin_commands` (rewritten), `merge_job` (staged progress + summary + button) | — | command scopes, merge UX |
| `bot/oxmit/texts.py` | `normalize_digits` (NEW), ~60 new/edited keys | — | Persian copy, digits helper |
| `bot/oxmit/bot.py` | router wiring, sweep list | — | nav integration |
| `tests/test_nav.py` | NEW (8 tests) | menu roles, callback limits, registration, den:req rate-limit + owner-only notify | spec §25.2/25.3 |
| `tests/test_admin_system.py` | refresh scopes test updated | 5/12/13 counts | intentional command-scope change |

## 17. Database Changes
**None.** Every feature reuses existing tables (users, jobs, job_requesters, admin_settings, admin_permissions, merge_sessions, audit_log). No migration was needed.

## 18. Tests
- Baseline: 186 passed. Final: **194 passed / 0 failed** (Windows venv) — **194 passed on the server venv after deploy** (files copied; container NOT restarted).
- New: 8 nav tests (menu visibility per role incl. VIP/owner; forbidden rows absent; Telegram 64-byte callback limit; router registration; den:req notifies ONLY the owner + 3/day rate limit).
- Updated: refresh_admin_commands scope counts (intentional 5/12/13 change).
- Regression: all 186 previous tests still pass (compression, dedup, cache-offer, merge ordering, permissions, branding isolation, security).
- NOT executed: live Telegram interaction (container not restarted), real-device RTL rendering review, load conditions.

## 19. Known Limitations
- Everything in the spec §19/§48 P3 list (per-part branding, merge reorder, VIP expiry, live VIP usage dashboard) — intentionally out of scope.
- Unified preview is approximate (white-canvas watermark + real stored thumbnail + caption text) — honestly labeled in-copy.
- `/menu` ops/owner rows hand off to typed commands (`/admin`, `/owner`) rather than re-rendering those screens inline (documented shortcut pattern).

## 20. Mermaid Diagrams
Final navigation and interaction diagrams: see the spec `docs/OXMIT_UX_UI_REDESIGN_SPEC.md` §31–§42 — they match the implemented state (menu rows = role-gated; merge staged progress added; denial request flow added).

## 21. Deployment Instructions (for an authorized operator — NOT executed)
```bash
# 1. backup (code + git + db)
cd /opt/oxmit && tar czf ~/oxmit-pre-uxnav-$(date +%Y%m%d-%H%M).tar.gz bot tests docs
docker exec oxmit-postgres pg_dump -U oxmit oxmit | gzip > ~/oxmit-db-pre-uxnav-$(date +%Y%m%d-%H%M).sql.gz
# 2. tag rollback image
docker tag oxmit/bot:local oxmit/bot:rollback-pre-uxnav
# 3. rebuild + recreate (applies no migrations - none needed)
cd /opt/oxmit && docker compose build bot && docker compose up -d bot
# 4. verify
docker logs --since 2m oxmit-bot | grep -v actuator
curl -s http://127.0.0.1:8091/internal/healthz
```
Rollback: `docker tag oxmit/bot:rollback-pre-uxnav oxmit/bot:local && docker compose up -d bot`.

## 22. Remaining Work
- **P0/P1:** all implemented (see §4–§14).
- **P2 done:** owner matrix, merge completion summary + compress-later, settings hint, command descriptions.
- **P2 remaining:** unified real-frame preview (current = thumbnail + canvas watermark + caption text).
- **P3 (separate future work):** per-part branding, merge reorder, VIP expiry, VIP usage dashboard.
