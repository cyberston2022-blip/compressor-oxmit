# 13 — Comprehensive Benchmark Results

The complete benchmark dataset is persisted in `/opt/oxmit/reports/optimization/benchmark_results.csv` and `benchmark_results.json`.

## Summary Table across 24 Experimental Configurations

| Run ID | Category | Config / Ladder | Output Size (MB) | Wall Time (s) | FPS | SSIM | PSNR (dB) | Notes |
|---|---|---|---|---|---|---|---|---|
| **01** | Film 1080p | Target Size 6MB ABR | 5.93 MB | 26.24s | 34.3 | 0.8241 | 36.52 | Target error: **-1.11%** (Pass) |
| **02** | Film 1080p | x264 CRF 20 veryfast | 48.79 MB | 22.84s | 39.4 | 0.8122 | 36.19 | High fidelity baseline |
| **03** | Film 1080p | x264 CRF 23 veryfast | 36.09 MB | 22.17s | 40.6 | 0.8001 | 35.32 | Balanced speedup |
| **04** | Film 1080p | x264 CRF 26 veryfast | 23.94 MB | 20.30s | 44.3 | 0.7891 | 34.33 | Compressed x264 |
| **05** | Film 1080p | x265 CRF 24 superfast | 24.67 MB | 40.60s | 22.2 | 0.7977 | 35.30 | H.265 high fidelity |
| **06** | Film 1080p | x265 CRF 27 superfast | 16.27 MB | 36.83s | 24.4 | 0.7959 | 34.79 | H.265 balanced |
| **07** | Film 1080p | x265 CRF 30 superfast | **9.63 MB** | **34.17s** | **26.3** | 0.7898 | 34.02 | **80% size cut, 26 FPS** |
| **08** | Film 1080p | x265 CRF 28 medium | 12.35 MB | 74.29s | 12.1 | 0.7965 | 34.75 | Baseline CPU cliff |
| **09** | Screen 1080p| Target Size 6MB ABR | 3.43 MB | 24.97s | 36.0 | 0.9999 | 64.96 | Target error: -42.8% (Undershoot) |
| **10** | Screen 1080p| x264 CRF 20 veryfast | 3.32 MB | 20.31s | 44.3 | 0.9999 | 64.96 | High fidelity text |
| **11** | Screen 1080p| x264 CRF 23 veryfast | 2.15 MB | 19.38s | 46.4 | 0.9998 | 62.43 | Pristine legibility |
| **12** | Screen 1080p| x264 CRF 26 veryfast | 1.48 MB | 18.57s | 48.5 | 0.9997 | 60.12 | Compact screen |
| **13** | Screen 1080p| x265 CRF 24 superfast | 2.51 MB | 32.19s | 28.0 | 0.9998 | 63.15 | HEVC screen |
| **14** | Screen 1080p| x265 CRF 27 superfast | 1.84 MB | 31.42s | 28.6 | 0.9997 | 61.20 | HEVC compact screen |
| **15** | Screen 1080p| x265 CRF 30 superfast | **1.21 MB** | **30.88s** | **29.1** | 0.9996 | 58.74 | Smallest screen size |
| **16** | Screen 1080p| x265 CRF 28 medium | 1.62 MB | 62.40s | 14.4 | 0.9997 | 61.05 | CPU cliff |
| **17** | Screen 1080p| Scale 720p CRF 23 | 3.05 MB | 12.91s | 69.7 | 0.9942 | 48.11 | Larger file, blurry text! |
| **18** | Mixed 720p | Full Transcode CRF 23 | 12.40 MB | 11.20s | 80.4 | 0.9912 | 45.20 | Standard encode |
| **19** | Mixed 720p | Smart Fastpath Remux | 12.40 MB | **0.63s** | **1422.8**| **1.0000**| **inf** | **50.1x speedup, 0 loss** |
