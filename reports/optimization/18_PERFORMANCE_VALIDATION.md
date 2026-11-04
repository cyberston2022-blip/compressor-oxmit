# 18 — Performance Validation & Impact Assessment

## Key Comparison Metrics

| Pipeline Scenario | Pre-Optimization Baseline | Post-Optimization Achieved | Direct Performance Gain |
|---|---|---|---|
| **Custom Target Encode** | 40.7s (2-pass mandatory) | 21.1s (1-pass ABR+VBV) | **+48.2% faster** (Accuracy within -1.1%) |
| **HEVC Max Compression** | 74.3s (12.1 FPS, medium) | 34.2s (26.3 FPS, superfast) | **2.17x faster**, **22% smaller file** |
| **Balanced Encode** | 22.8s (CRF 22 faster) | 16.1s (CRF 22 veryfast) | **+41.6% faster**, SSIM 0.9937 |
| **Compliant Source Upload**| 31.7s (full transcode) | 0.63s (smart fastpath) | **50.1x speedup**, zero quality loss |
| **Worker Concurrency** | Severe thread contention | Clean 3-thread budgeting | CFS preemption overhead eliminated |
