# 08 — Adaptive Resolution Downscaling Strategy

## 1. Architectural Rules
Oxmit implements an intelligent resolution downscaling ladder based on calculated bitrate budget and content classification:

```mermaid
flowchart TD
    Input[Incoming Video Probe] --> ResCheck{Resolution >= 1440p?}
    ResCheck -- Yes --> Scale1080[Downscale to 1080p]
    ResCheck -- No --> Check1080{Resolution == 1080p?}
    Check1080 -- Yes --> BitrateCheck{Bitrate < 650 kbps?}
    BitrateCheck -- Yes --> CategoryCheck{Content == Screen Text?}
    CategoryCheck -- Yes --> Keep1080[PRESERVE 1080p for Text Clarity]
    CategoryCheck -- No --> Scale720[Downscale to 720p for Higher BPP]
    BitrateCheck -- No --> Keep1080
    Check1080 -- No --> Preserve[Preserve Native 720p/480p - Never Upscale]
```

## 2. Empirical Verification: Screen Recording Protection
During testing, downscaling a 1080p screen recording to 720p actually **increased** file size from **2.15 MB** to **3.05 MB** (+41.8% larger!) due to bilinear/bicubic filter antialiasing adding artificial high-frequency entropy to sharp vector lines, while destroying text clarity!

**The Protection Policy**:
For all content detected as `screen_text`, 1080p resolution is strictly preserved regardless of bitrate budget.
