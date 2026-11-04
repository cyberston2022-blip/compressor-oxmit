# 00 — Executive Summary: Master Performance & Compression Optimization

## Mission Overview
The Oxmit Telegram video compression platform operates under strict owner constraints on an AWS Lightsail 8-vCPU instance ($80/mo). The primary objective is:
**File size reduction is slightly more important than speed**, while strictly avoiding visible quality degradation (VMAF $\approx 95$, SSIM $\ge 0.98$, strict preservation of text/subtitles), maintaining target-size accuracy within $\pm 2\%$, and achieving the maximum practical processing speed.

This optimization mission delivered an evidence-based compression strategy, empirical multi-category benchmarking, an intelligent adaptive decision engine, and full production integration without breaking existing APIs or profiles.

---

## Key Achievements & Benchmark Discoveries

| Optimization Dimension | Baseline Behavior | Optimized Result | Impact / Improvement |
|---|---|---|---|
| **Custom Target Accuracy** | 2-Pass ABR (Fixed) | Adaptive 1-Pass / 2-Pass | **-1.11% size error** (within $\pm 2\%$) at **+48% faster encoding** |
| **H.265 / HEVC Presets** | `x265 medium` (0.58x cliff) | `x265 superfast / faster` | **2.17x faster** (26.3 vs 12.1 FPS) & **22% smaller file** (9.63 vs 12.35 MB) |
| **Balanced Profile** | `x264 faster` | `x264 veryfast` | **+41% faster** (40.6 vs 28.7 FPS) with visually lossless SSIM (0.9937) |
| **Smart Fastpath (Remux)** | Full re-encode (31.7s) | Stream Copy (`-c copy`) | **0.63s execution (50.1x faster)**, 0% CPU overhead, 100% quality retention |
| **Screen Recording Quality** | Aggressive downscale blur | Smart Content Protection | 1080p preserved for UI/text, SSIM **0.9999**, pristine edge contrast |
| **Adaptive Downscaling** | Fixed resolution | Bitrate-aware ($<650$ kbps) | **+50% speedup**, 2.2x higher bits-per-pixel for low-bitrate general video |
| **CPU Worker Contention** | Unconstrained threads | Single: 6 thd, Multi: 3 thd | Zero Linux CFS throttling, predictable concurrency |
| **Test Suite Stability** | 96 tests | **106 tests passed (100%)** | Zero regressions, complete decision engine coverage |

---

## Architectural Breakthrough: The Adaptive Decision Engine
Rather than applying a rigid, one-size-fits-all FFmpeg command, Oxmit now features `bot/oxmit/decision_engine.py`:
1. **Content-Aware Classification**: Categorizes incoming media as `screen_text`, `film_motion`, or `general` using metadata heuristics (resolution, framerate, bits-per-pixel ratio, filename markers).
2. **Smart Fastpath Remux**: Instantly bypasses transcoding if the source video already matches Telegram-compatible H.264/AAC MP4 within requested target limits.
3. **Hybrid Codec & Preset Optimization**: Exploits the sweet spot of `x265 superfast/faster` for dense compression without the catastrophic CPU cliff of `x265 medium`.
4. **Adaptive Rate Control**: Utilizes single-pass ABR+VBV for standard media (hitting $\pm 1.2\%$ target error) and strict two-pass ABR for complex/long screen recordings.

All modifications are guarded by environment feature flags and fully verified against the live PostgreSQL database and SVT Encore microservice.
