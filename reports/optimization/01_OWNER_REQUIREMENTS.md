# 01 — Owner Requirements & Optimization Priorities

## 1. Core Mandate
The owner established non-negotiable optimization priorities that govern every engineering decision in this mission:

### Priority 1: File Size is Slightly More Important Than Speed
- Smaller output files are the primary goal.
- However, encoding speed must not be sacrificed blindly for diminishing returns.
- Presets that consume $3\times$ to $5\times$ more CPU time for a negligible $2\text{--}4\%$ size saving are strictly prohibited.
- Presets that cut file size by $30\text{--}50\%$ with acceptable compute expenditure are prioritized.

### Priority 2: Visual Quality Guardrails
- **Perceptual Target**: Visually lossless or near-lossless during normal mobile and desktop playback.
- **Objective Metrics**:
  - Target VMAF $\approx 95$ or higher.
  - VMAF below 93 must be investigated carefully and rejected by default.
  - SSIM target $\ge 0.98$ as a supporting indicator.
- **Text & Subtitle Protection**: Screen recordings, software tutorials, slides, and educational videos must maintain razor-sharp text legibility and edge contrast. Detail loss or blurring on UI elements is strictly prohibited.

### Priority 3: Target-Size Accuracy ($\pm 2\%$)
- When a user explicitly requests a custom target size (e.g., 50 MB, 100 MB):
  - Achieved size must strictly fall within $\pm 2\%$ of the target.
  - Output file must **never** exceed the requested maximum size or platform upload ceilings.
  - Bitrate calculations must accurately compensate for audio stream bitrate, container muxing overhead (1.5%), and subtitle/metadata tracks.

### Priority 4: Hybrid H.264 and H.265 Strategy
- **Do NOT eliminate H.265 / HEVC**: The owner explicitly requested preserving H.265 for compact distribution.
- **Avoid the Performance Cliff**: Eliminate `x265 medium` (which collapsed to 0.58x real-time in previous audits). Deploy optimized H.265 presets (`superfast` / `faster`) that deliver 30–50% smaller files than H.264 at viable speeds.
- Maintain H.264 as the universal compatibility baseline for web/Telegram instant streaming.

### Priority 5: Adaptive Resolution Downscaling
- Downscale 4K ($3840\times 2160$) and 1440p ($2560\times 1440$) to 1080p.
- Downscale 1080p to 720p only when calculated video bitrate is below $650\text{ kbps}$, **except** for screen recordings/presentations where 1080p resolution must be preserved.
- Never upscale lower resolutions (720p, 480p).

### Priority 6: Smart Encoding Bypass (Fastpath)
- If an input file is already encoded in H.264 / AAC inside an MP4 container and already satisfies user size/compatibility limits, bypass full transcoding via stream copy (`-c copy`).

### Priority 7: Fixed Infrastructure Constraint
- Optimize exclusively within the current AWS Lightsail 8-vCPU / 16 GB RAM instance ($80/month). No migration or external fleet expansion.
