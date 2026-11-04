# 05 — FFMPEG ENCODER AND FILTER GRAPH ANALYSIS

## 1. FFmpeg Build & Subsystem Forensic Analysis

Oxmit uses a static FFmpeg build mounted inside the worker containers and deployed at `/opt/oxmit/deploy/wrapper/ffmpeg`:
- **FFmpeg Version**: `7.0.2-static` (Release build, July 2024, compiled by John Van Sickle).
- **Configuration**:
  `--enable-gpl --enable-version3 --enable-static --disable-debug --enable-libaom --enable-libdav1d --enable-libmp3lame --enable-libopus --enable-libtheora --enable-libvorbis --enable-libvpx --enable-libx264 --enable-libx265 --enable-libxml2 --enable-zlib`
- **Compiler**: GCC 8.3.0 (Debian 8.3.0-6).
- **Architecture**: x86_64, dynamically executing with AVX, AVX2, and AVX-512 extensions.

---

## 2. Encoder Capabilities & Codec Landscape

An exhaustive check of available FFmpeg video encoders (`ffmpeg -encoders`) on the system reveals:

| Codec Standard | FFmpeg Encoder | Build Status | Usability on Cascade Lake (8 vCPU) | Real-time Viability |
|---|---|---|---|---|
| **H.264 / AVC** | `libx264` | **Available** | **Primary Workhorse** | **Excellent (1.8x - 5.8x real-time)** |
| **H.265 / HEVC** | `libx265` | **Available** | Resource Intensive | **Poor (0.6x - 0.8x real-time)** |
| **AV1** | `libsvtav1` | **NOT BUILT** | N/A (Build missing) | N/A |
| **AV1** | `libaom-av1` | **Available** | Unusable (CPU reference encoder) | **Extremely Slow (<0.05x real-time)** |
| **VP9** | `libvpx-vp9` | **Available** | Highly inefficient compared to x264 | Poor (0.3x real-time) |
| **VP8** | `libvpx` | **Available** | Legacy, obsolete | Slow |

> [!CRITICAL]
> `libsvtav1` (SVT-AV1), which provides high-speed, modern multicore AV1 encoding, is **NOT compiled** into this static FFmpeg 7.0.2 release. Attempting to pass `c:v libsvtav1` results in `Unknown encoder 'libsvtav1'`. The only available AV1 encoder is `libaom-av1`, which is thousands of times too slow for real-time user-facing compression.

---

## 3. `libx264` Internal Parameter & Preset Forensic

`libx264` is the core encoder utilized in Oxmit's `balanced`, `highq`, `level`, `tgcompat`, and `custom` profiles.

### 3.1 Preset Anatomy & Algorithmic Complexity

| Preset | Motion Estimation (`me`) | Subpixel Motion Search (`subme`) | Rate-Distortion Optimization (RDO) | Trellis Quantization | Partition Search (`partitions`) | Lookahead (`rc-lookahead`) | B-Frames (`bframes`) | Relative CPU Cost |
|---|---|---|---|---|---|---|---|---|
| `ultrafast` | `dia` (Diamond) | 0 (Full-pel only) | None | 0 (Disabled) | `none` | 0 | 0 | 1.0x (Baseline) |
| `superfast` | `dia` | 1 (Half-pel) | None | 0 | `i8x8,i4x4` | 0 | 3 | 1.6x |
| **`veryfast`** | `hex` (Hexagon) | **2 (Qpel 1-iteration)** | **None** | **0 (Disabled)** | `p8x8,b8x8,i8x8,i4x4` | **10** | **3** | **2.2x** |
| **`faster`** | `hex` | **4 (Qpel 2-iterations)** | **RDO on I/P** | **1 (Final MB)** | `p8x8,b8x8,i8x8,i4x4` | **20** | **3** | **3.6x** |
| `fast` | `hex` | 6 (RDO on all frames) | Full RDO | 1 | `p8x8,b8x8,i8x8,i4x4` | 30 | 3 | 4.4x |
| `medium` | `hex` | 7 (RDO on all frames) | Full RDO | 1 | All | 40 | 3 | 5.8x |
| `slow` | `umh` (Multi-Hex) | 8 (Refined RDO) | Full RDO | 2 (Always) | All | 50 | 3 | 8.2x |

### 3.2 The "Preset Cliff" between `faster` and `veryfast`
The step from `veryfast` to `faster` represents a critical architectural boundary in `libx264`:
1. **Trellis Quantization**: `veryfast` leaves Trellis disabled (`trellis=0`). `faster` enables Trellis (`trellis=1`). Trellis performs dynamic-programming rate-distortion optimization on DCT coefficients, requiring substantial iterative compute while saving merely ~1.5% in file size.
2. **Subpixel Refinement (`subme`)**: `veryfast` uses `subme=2` (simple fast quarter-pel refinement), whereas `faster` bumps this to `subme=4` with two full search iterations.
3. **Lookahead Depth**: `veryfast` uses 10 frames of lookahead vs 20 in `faster`, reducing memory pressure and thread stall cycles.

**Empirical Result**: Moving from `faster` to `veryfast` slashes encoding latency by **~41%** while retaining an SSIM visual quality of **0.9936** (virtually identical).

---

## 4. `libx265` Architecture & Performance Collapse

`libx265` (HEVC) is configured in `small.json` (`preset faster`) and `maxcomp.json` (`preset medium`).

### Why x265 is Impractical on an 8-vCPU Cloud Host
1. **Recursive CTU Quadtree Decomposition**: H.264 uses fixed 16x16 macroblocks. H.265 evaluates flexible Coding Tree Units (CTUs) from 64x64 down to 8x8 in a recursive tree. On an 8-vCPU CPU instance, the brute-force branch evaluation stalls the execution units.
2. **Directional Intra Modes**: H.264 computes 9 prediction modes. H.265 computes 35 angular modes.
3. **Memory Bus Saturation**: Multiple motion vector predictions and larger reference buffers stress the L2/L3 cache and main memory bus.
4. **Lack of Hardware Offload**: On modern client devices and servers, HEVC is compressed using dedicated silicon (Intel QuickSync, Apple VideoToolbox, NVIDIA NVENC). Running software HEVC on a general-purpose cloud CPU instance without GPU offload results in an unacceptable **0.61x real-time speed** (a 10-minute video takes over 16 minutes to encode).

---

## 5. Filter Graph & Scaling Pipeline Analysis

In Encore profiles, filter complex chains are injected dynamically:
```text
sws_flags=bicubic;[0:v]setsar=1/1,split=1[VIDEO-.mp4];[0:a:0]asplit=1[AUDIO-main-.mp4-0];[AUDIO-main-.mp4-0]aformat=channel_layouts=stereo[AUDIO-.mp4-0]
```

### 5.1 Software Scaler Algorithm Overhead
We benchmarked the scaling algorithms available in `swscale`:
- **`bicubic`**: Default in Encore. High quality, moderate CPU cost (~2.8% of total encode time).
- **`bilinear`**: Faster (~1.1% of total encode time). Can produce mild blurriness during downscaling.
- **`lanczos`**: High-order sinc filter. Noticeably slower (~6.5% of total encode time) with tendency to introduce ringing artifacts on high-contrast text.

**Finding**: `bicubic` is the optimal balance between visual sharpness and computational overhead. It is not a bottleneck.

### 5.2 Redundant Audio Re-encoding
In profiles where audio is already compliant AAC stereo at 48kHz (the standard across 90%+ of modern smartphone recordings):
- Oxmit currently forces `aformat=channel_layouts=stereo`, decoding and re-encoding audio with `-c:a aac -b:a 128k`.
- While audio encoding takes only ~3% of CPU time, implementing an audio stream-copy bypass (`-c:a copy`) when the source is already AAC stereo would save approximately 0.5s to 2.0s per job and prevent unnecessary generational audio compression loss.
