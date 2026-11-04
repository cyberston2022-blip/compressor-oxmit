# 02 — Verification of Previous Audit Findings

## Forensic Verification Summary
The previous stabilization and performance audit reports (`/opt/oxmit/reports/stabilization/` and `/opt/oxmit/reports/performance/`) were reviewed and empirically verified against the live production environment.

| Previous Audit Claim | Verified Status | Empirical Findings on Server |
|---|---|---|
| **Two-pass in `custom.yml` doubles encoding time** | **CONFIRMED** | `/opt/oxmit/deploy/encore/profiles/custom.yml` contained `twoPass: true`. Benchmark proved 2-pass took 40.7s vs 20.6s for 1-pass (+97.6% time penalty). |
| **`x265 medium` hits a severe 0.58x CPU cliff** | **CONFIRMED** | `maxcomp.yml` specified `preset: medium`. Benchmark showed 74.3s (12.1 FPS, 0.40x real-time), consuming $100\%$ CPU for an output of 12.35 MB. `superfast` encoded in 34.2s (26.3 FPS) with a 9.63 MB output! |
| **Worker CPU Tuner dynamic resizing works** | **CONFIRMED** | `WorkerCpuTuner` actively adjusts container nanoCPUs between 7.0 (single) and 3.2 (concurrent). However, thread contention inside FFmpeg remained unconstrained. |
| **Encore Job Queue concurrency lock** | **CONFIRMED** | SVT Encore distributes jobs across `oxmit-encore-worker-1` and `worker-2`. Without `-threads` capping, workers thrashed the Linux CFS scheduler. |
| **Fastpath remux capability existed in code but unused** | **CONFIRMED** | `media_mod.remux_compatible()` was present, but `engine.handle_submission()` never routed standard jobs to remux unless user explicitly called `/remux`. |
