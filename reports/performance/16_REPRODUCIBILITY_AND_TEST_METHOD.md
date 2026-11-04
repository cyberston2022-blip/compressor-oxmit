# 16 — REPRODUCIBILITY AND TEST METHODOLOGY

## 1. Executive Summary

This document provides complete, step-by-step instructions, exact FFmpeg command invocations, test harness code, and JSON/CSV data schemas required to reproduce every benchmark and metric reported in this performance audit.

Future engineers can execute these procedures to validate optimizations or detect performance regressions in continuous integration (CI/CD) pipelines.

---

## 2. Benchmark Environment & Prerequisites

To execute the benchmark suite on any Linux host or container:
- Python 3.8+ (`python3`)
- Production FFmpeg wrapper: `/opt/oxmit/deploy/wrapper/ffmpeg` (or any FFmpeg 7.0+ static binary)
- Standard Linux utilities: `bc`, `awk`, `grep`, `coreutils`

---

## 3. Synthetic Media Generation

Reproducible test media is generated deterministically without network dependencies using FFmpeg's synthetic pattern generator:

### 3.1 1080p 30fps Synthetic Stream (30 seconds, 900 frames)
```bash
/opt/oxmit/deploy/wrapper/ffmpeg -y \
  -f lavfi -i "testsrc2=size=1920x1080:rate=30:duration=30" \
  -f lavfi -i "sine=frequency=1000:sample_rate=48000:duration=30" \
  -c:v libx264 -preset ultrafast -crf 18 \
  -c:a aac -b:a 128k \
  -pix_fmt yuv420p \
  /tmp/bench/synth_1080p30.mp4
```

### 3.2 720p 30fps Synthetic Stream (30 seconds, 900 frames)
```bash
/opt/oxmit/deploy/wrapper/ffmpeg -y \
  -f lavfi -i "testsrc2=size=1280x720:rate=30:duration=30" \
  -f lavfi -i "sine=frequency=1000:sample_rate=48000:duration=30" \
  -c:v libx264 -preset ultrafast -crf 18 \
  -c:a aac -b:a 128k \
  -pix_fmt yuv420p \
  /tmp/bench/synth_720p30.mp4
```

---

## 4. Exact Benchmark FFmpeg Invocations

### 4.1 Production Baseline Profiles

#### `balanced` Profile
```bash
/opt/oxmit/deploy/wrapper/ffmpeg -hide_banner -y \
  -i /tmp/bench/synth_1080p30.mp4 \
  -filter_complex "sws_flags=bicubic;[0:v]setsar=1/1,split=1[VIDEO-.mp4];[0:a:0]asplit=1[AUDIO-main-.mp4-0];[AUDIO-main-.mp4-0]aformat=channel_layouts=stereo[AUDIO-.mp4-0]" \
  -map "[VIDEO-.mp4]" -map "[AUDIO-.mp4-0]" \
  -c:v libx264 -preset faster -crf 22 -pix_fmt yuv420p -movflags +faststart \
  -c:a aac -b:a 128k -ar 48000 \
  /tmp/bench/out_balanced.mp4
```

#### `tgcompat` Profile
```bash
/opt/oxmit/deploy/wrapper/ffmpeg -hide_banner -y \
  -i /tmp/bench/synth_1080p30.mp4 \
  -filter_complex "sws_flags=bicubic;[0:v]setsar=1/1,split=1[VIDEO-.mp4];[0:a:0]asplit=1[AUDIO-main-.mp4-0];[AUDIO-main-.mp4-0]aformat=channel_layouts=stereo[AUDIO-.mp4-0]" \
  -map "[VIDEO-.mp4]" -map "[AUDIO-.mp4-0]" \
  -c:v libx264 -preset veryfast -crf 22 -pix_fmt yuv420p -movflags +faststart \
  -c:a aac -b:a 128k -ar 48000 \
  /tmp/bench/out_tgcompat.mp4
```

#### `custom` 2-Pass Profile (Target Size ~7 MB)
```bash
# Pass 1
/opt/oxmit/deploy/wrapper/ffmpeg -hide_banner -y \
  -i /tmp/bench/synth_1080p30.mp4 \
  -filter_complex "sws_flags=bicubic;[0:v]setsar=1/1,split=1[VIDEO-.mp4];[0:a:0]asplit=1[AUDIO-main-.mp4-0];[AUDIO-main-.mp4-0]aformat=channel_layouts=stereo[AUDIO-.mp4-0]" \
  -map "[VIDEO-.mp4]" -an \
  -b:v 1800k -maxrate 2430k -bufsize 4860k -preset faster -pix_fmt yuv420p \
  -c:v libx264 -x264-params "pass=1:stats=/tmp/bench/passlog" \
  -f null -

# Pass 2
/opt/oxmit/deploy/wrapper/ffmpeg -hide_banner -y \
  -i /tmp/bench/synth_1080p30.mp4 \
  -filter_complex "sws_flags=bicubic;[0:v]setsar=1/1,split=1[VIDEO-.mp4];[0:a:0]asplit=1[AUDIO-main-.mp4-0];[AUDIO-main-.mp4-0]aformat=channel_layouts=stereo[AUDIO-.mp4-0]" \
  -map "[VIDEO-.mp4]" -map "[AUDIO-.mp4-0]" \
  -b:v 1800k -maxrate 2430k -bufsize 4860k -preset faster -pix_fmt yuv420p -movflags +faststart \
  -c:v libx264 -x264-params "pass=2:stats=/tmp/bench/passlog" \
  -c:a aac -b:a 96k -ar 48000 \
  /tmp/bench/out_custom_2pass.mp4
```

#### Candidate A: 1-Pass ABR + VBV
```bash
/opt/oxmit/deploy/wrapper/ffmpeg -hide_banner -y \
  -i /tmp/bench/synth_1080p30.mp4 \
  -filter_complex "sws_flags=bicubic;[0:v]setsar=1/1,split=1[VIDEO-.mp4];[0:a:0]asplit=1[AUDIO-main-.mp4-0];[AUDIO-main-.mp4-0]aformat=channel_layouts=stereo[AUDIO-.mp4-0]" \
  -map "[VIDEO-.mp4]" -map "[AUDIO-.mp4-0]" \
  -b:v 1800k -maxrate 2430k -bufsize 4860k -preset veryfast -pix_fmt yuv420p -movflags +faststart \
  -c:v libx264 \
  -c:a aac -b:a 96k -ar 48000 \
  /tmp/bench/out_custom_1pass.mp4
```

---

## 5. Objective Quality Metric Calculation (SSIM & PSNR)

Calculate exact per-frame and mean SSIM/PSNR against the uncompressed source:
```bash
/opt/oxmit/deploy/wrapper/ffmpeg -hide_banner \
  -i /tmp/bench/out.mp4 \
  -i /tmp/bench/synth_1080p30.mp4 \
  -lavfi "ssim;[0:v][1:v]psnr" \
  -f null - 2>&1 | grep -E "(SSIM|PSNR)"
```

---

## 6. Data Deliverable Schemas

### 6.1 `benchmark_results.json` Schema
```json
{
  "timestamp": "2026-11-04T13:30:00Z",
  "system": {
    "cpu": "Intel(R) Xeon(R) Platinum 8275CL CPU @ 3.00GHz",
    "vcpus": 8,
    "ram_total_kb": 15984388,
    "os": "Ubuntu 22.04.4 LTS (Linux 6.8.0-1017-aws x86_64)"
  },
  "benchmarks": [
    {
      "test_name": "Profile Baseline: balanced",
      "codec": "libx264",
      "preset": "faster",
      "rate_control": "CRF 22",
      "wall_time_sec": 16.01,
      "effective_speed": 1.87,
      "fps": 56.2,
      "cpu_percent": 383.0,
      "output_size_bytes": 23970816,
      "ssim": 0.99567,
      "psnr_db": 45.21
    }
  ]
}
```

### 6.2 `benchmark_results.csv` Schema
```csv
test_category,profile_or_preset,codec,wall_time_sec,speed_x,fps,cpu_percent,size_mb,ssim,psnr_db
Profile Baseline,balanced,libx264,16.01,1.87,56.2,383.0,22.86,0.99567,45.21
Profile Baseline,highq,libx264,16.50,1.82,54.6,384.0,29.86,0.99738,47.80
Profile Baseline,level,libx264,17.40,1.72,51.7,368.0,28.71,0.99708,47.12
Profile Baseline,tgcompat,libx264,11.25,2.67,80.0,354.0,20.14,0.99461,43.82
Profile Baseline,small,libx265,37.35,0.80,24.1,363.0,18.38,0.99020,42.14
Profile Baseline,maxcomp,libx265,48.94,0.61,18.4,366.0,11.55,0.98920,41.40
```
