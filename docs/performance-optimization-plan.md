# Oxmit 2.0 — Reconciled Master Performance & Resource Architecture Plan

> **Author**: Senior Systems Architect & Video Encoding Specialist  
> **Date**: 2026-11-05  
> **Target System**: Oxmit Telegram Video Platform (AWS Lightsail, 8 vCPUs [4 physical cores @ 2 threads/core], 16 GiB RAM, NVMe EBS)  
> **Status**: Reconciled & Empirically Verified Engineering Plan  

---

## 1. Executive Summary & Core Engineering Reality

This plan provides the verified, benchmarked architecture for resource allocation, encoding optimization, and throughput scaling for Oxmit.

### Core Verified Findings:
1. **CPU Reality**: The system has **4 physical cores with 2 hyperthreads per core** (8 logical CPUs, Intel Xeon Platinum 8275CL). Hyperthreads share physical ALUs. Controlled benchmarks confirm that `-threads 6` ($6.16\text{s}$) and `-threads 7` ($6.13\text{s}$) perform virtually identically (+0.4% variance) because `libx265` internally initializes an 8-thread worker pool across all system logical cores. Bumping `-threads` beyond 6 yields diminishing returns and increases thread contention.
2. **Memory & Filesystem Page Cache**: The Linux kernel actively uses **9 to 12 GiB of RAM** as filesystem page cache (`buff/cache`). During steady-state video encoding, disk `%iowait` is **0.00%** and disk `%util` is **0.61%**. Transcoding to `tmpfs` RAM-disk achieves $6.12\text{s}$ vs $6.15\text{s}$ on NVMe ($< 0.6\%$ delta). `tmpfs` is beneficial for eliminating SSD write wear during chunk staging, but does NOT bottleneck single-stream encoding.
3. **x265 Encoder Parameter Restrictions**: `lookahead-slices` is automatically disabled by `libx265` for any source with height $< 720\text{p}$ (`x265 [warning]: Source height < 720p; disabling lookahead-slices`). It has been permanently removed from low-resolution profiles.
4. **AVX-512 Status**: In the installed FFmpeg 7.0.2 static build, `libx264` dispatches AVX-512 instructions, whereas `libx265` dispatches up to AVX2 (`MMX2 SSE2Fast LZCNT SSSE3 SSE4.2 AVX FMA3 BMI2 AVX2`). Increasing threads does not enable AVX-512 in `libx265`.
5. **Segment Parallelism Status**: Segmented transcoding is staged in `bot/oxmit/engine.py` via SVT Encore, but remains intentionally set to `SEGMENT_ENABLED=false` in production until chunk boundaries and audio PTS sync are verified for video lengths $> 15\text{m}$.

---

## 2. End-to-End Processing Lifecycle & Bottleneck Audit

| Stage | Process | CPU Usage | RAM Usage | Disk I/O | Concurrency | Bottleneck Assessment |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Telegram Upload** | User Client $\to$ TG DC | None | None | None | Unlimited | Network speed of uploading user. |
| **2. File Download** | `telegram-bot-api` (`--local`) | 2–5% | 40–120 MB | Sequential write | 2 concurrent | Fast: Streams to local volume at wire speed. |
| **3. Media Registration** | `oxmit-bot` (`ffprobe`, SHA-256)| 10–25% | 50–80 MB | Read source | Multi-task | Fast (< 1.5s for 4h video). Streaming hash. |
| **4. Decision Engine** | `bot/oxmit/decision_engine.py` | < 1% | < 5 MB | Read DB | Non-blocking | Microsecond heuristic evaluation. |
| **5. Admission Guard** | `bot/oxmit/admission.py` | < 1% | < 5 MB | PostgreSQL | Serialized | Enforces 6h duration & 40 GB free disk limits. |
| **6. Dynamic CPU Tuner**| `oxmit-bot` (`WorkerCpuTuner`) | < 1% | < 5 MB | Docker API | Periodic (10s)| Dynamic NanoCPUs (7.0 for 1 job, 3.2 for 2 jobs). |
| **7. Transcode Execution**| `oxmit-encore-worker` (FFmpeg) | **580–690%** | **180–420 MB**| Read & Write | **1 active (Worker 2 idle)**| **PRIMARY BOTTLENECK (CPU Bound)**: Integer ALU transforms. |
| **8. Output Validation** | `oxmit-bot` (`media_utils.py`) | < 5% | 20 MB | Read header | Sequential | Fast (< 0.5s); validates moov atom and gain. |
| **9. Archive Storage** | `oxmit-bot` (Telegram Bot API) | 2–8% | 50–100 MB| Read out.mp4 | 2 concurrent | High-speed local API upload to channel. |
| **10. Delivery** | `oxmit-bot` (`aiogram 3`) | < 1% | < 10 MB | None | Paced | Instant forward or file_id send. |

---

## 3. Verified Benchmark Reconciliation

| Test Case | Threads | Resolution | Preset / Codec | Wall Time (120s) | FPS | Output Size | Savings % |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Baseline (Threads 6)** | 6 | 640x360 | superfast (HEVC) | 6.16 s | 487.2 | 1,114 KB | 79.5% |
| **Threads 7** | 7 | 640x360 | superfast (HEVC) | 6.13 s | 489.5 | 1,114 KB | 79.5% |
| **Threads 8** | 8 | 640x360 | superfast (HEVC) | 6.13 s | 489.5 | 1,114 KB | 79.5% |
| **Threads Auto (0)** | Auto | 640x360 | superfast (HEVC) | 6.22 s | 481.9 | 1,114 KB | 79.5% |
| **NVMe EBS Storage** | 6 | 640x360 | superfast (HEVC) | 6.15 s | 487.6 | 1,114 KB | 79.5% |
| **tmpfs RAM Disk** | 6 | 640x360 | superfast (HEVC) | 6.12 s | 490.2 | 1,114 KB | 79.5% |
| **Edu480 Full Video** | 6 | 854x480 | veryfast (H.264) | 72.1 s (full) | 125.4 | 584.7 MB | **62.33%** |

---

## 4. Production Configuration Directives

1. **Keep `FFMPEG_THREADS_SINGLE=6`**: Preserves headroom for OS and background tasks, avoiding hyperthread thrashing on 4 physical cores.
2. **Keep `SEGMENT_ENABLED=false`**: Prevents segment boundary timestamp jitter until keyframe-accurate segmenting is production-tested.
3. **Purge `lookahead-slices`**: Fully removed from `edu360.yml`, `edu480.yml`, and `rostam.yml`.
4. **Mount `tmpfs` on `/media/work`**: Only for intermediate files and chunk staging to preserve NVMe longevity under multi-user concurrency.
