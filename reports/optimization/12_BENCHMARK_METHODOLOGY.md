# 12 — Benchmark Methodology & Synthetic Workload Suite

## 1. Experimental Rigor
All benchmarks were executed on the production AWS Lightsail 8-vCPU instance under realistic operating conditions.

## 2. Synthetic Test Streams
Generated using FFmpeg `lavfi` synthetic filters to ensure 100% reproducible bitstreams:

1. **`stream_film_1080p.mp4`** (Cinematic Film Motion):
   - 1080p30, 30.0 seconds.
   - Dual-frequency oscillating geometric patterns with temporal film grain simulation:
     `testsrc2=size=1920x1080:rate=30,noise=alls=15:allf=t+u`.
   - Audio: Stereo sine wave tone at 440 Hz, AAC 128 kbps.
2. **`stream_screen_1080p.mp4`** (Software Tutorial / Screen Text):
   - 1080p30, 30.0 seconds.
   - Sharp alphanumeric text, vector geometry, moving color bars, timestamp counters:
     `testsrc=size=1920x1080:rate=30`.
   - Audio: Stereo speech-band tone at 1000 Hz, AAC 96 kbps.
3. **`stream_mixed_720p.mp4`** (Mobile / Mixed Video):
   - 720p30, 30.0 seconds.
   - Smooth gradients and motion vectors: `smptebars=size=1280x720:rate=30`.

## 3. Objective Metric Collection
For every encode, the automated test harness measured:
- Output file size in bytes and megabytes.
- Wall-clock execution time (seconds) and throughput (FPS).
- Exact percentage error against requested target size.
- Structural Similarity Index (SSIM) via FFmpeg `libvmaf/ssim` filter against original source.
- Peak Signal-to-Noise Ratio (PSNR) via FFmpeg `psnr` filter.
