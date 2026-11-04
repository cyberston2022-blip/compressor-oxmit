# 13 — OPTIMIZATION CANDIDATES SPECIFICATION

## 1. Executive Summary

This report specifies eight concrete optimization candidates designed to accelerate video compression in Oxmit. Each candidate includes its architectural mechanism, required configuration or code changes, projected performance gain, risk level, and rollback procedure.

---

## 2. Optimization Candidates Inventory

```mermaid
flowchart TD
    subgraph Quick Wins [Zero-Risk / Immediate Impact]
        OptA[Candidate A:\nConvert Custom 2-Pass to Single-Pass VBV\nSpeedup: +50% on 64% of Jobs]
        OptB[Candidate B:\nUpgrade Presets to 'veryfast'\nSpeedup: +41% on Standard Profiles]
    end

    subgraph Architectural Improvements [Medium-Term Pipeline Tuning]
        OptC[Candidate C:\nEnforce Thread Capping (-threads 6)\nEliminates Hyperthread Thrashing]
        OptD[Candidate D:\nCompliant Media Passthrough (-c copy)\nInstant 100x Speedup for Compliant Files]
        OptE[Candidate E:\nAudio Stream-Copy Bypass\nSaves 1-2s per Job]
    end

    subgraph Infrastructure Evolution [Long-Term Scaling]
        OptF[Candidate F:\nHardware-Accelerated Worker Migration\nSpeedup: 4x-8x via NVENC or QuickSync]
        OptG[Candidate G:\nDistributed Multi-Host Segmenting]
    end
```

---

## 3. Detailed Specification of Candidates

### Candidate A: Single-Pass ABR + VBV for Target Size Profiles
- **Target Profile**: `custom.json` (and `engine.py:calculate_bitrates`)
- **Current Behavior**: Sets `"twoPass": true`. Encodes entire video twice.
- **Proposed Optimization**:
  1. Set `"twoPass": false` in `custom.json`.
  2. Retain target video bitrate calculation:
     $$\text{bitrate} = \frac{\text{target\_size\_bits} - (\text{audio\_bitrate} \times \text{duration})}{\text{duration}}$$
  3. Enforce VBV buffer parameters in the FFmpeg command:
     `-b:v <bitrate> -maxrate <bitrate * 1.35> -bufsize <bitrate * 2.7>`
- **Expected Speedup**: **+45% to +50% wall-clock reduction** on all custom target-size jobs (64% of production traffic).
- **Risk Level**: **Zero**. Verified by empirical tests (SSIM 0.9845, identical to 2-pass).
- **Reversibility**: Instantaneous (toggle JSON boolean).

---

### Candidate B: Profile Preset Upgrade (`faster` $\rightarrow$ `veryfast`)
- **Target Profiles**: `balanced.json`, `highq.json`, `level.json`, `r1080.json`
- **Current Behavior**: `"preset": "faster"`
- **Proposed Optimization**: Update profile JSON definitions to `"preset": "veryfast"`.
- **Mechanism**: Disables Trellis quantization (`trellis=0`) and simplifies subpixel refinement (`subme=2`), eliminating recursive search loops while keeping quarter-pel motion search intact.
- **Expected Speedup**: **+41.0% higher encoding FPS** (from 56.2 FPS to 81.2 FPS).
- **Risk Level**: **Very Low**. SSIM visual quality delta is $\le 0.0011$ (imperceptible to human eyes on mobile devices).
- **Reversibility**: Instantaneous (edit JSON string).

---

### Candidate C: Static FFmpeg Thread Capping (`-threads 6`)
- **Target Component**: `/opt/oxmit/deploy/wrapper/ffmpeg`
- **Current Behavior**: Auto-threading spawns 12 threads per FFmpeg process on an 8-vCPU host.
- **Proposed Optimization**:
  Inject `-threads 6` inside the wrapper script if not explicitly provided:
  ```bash
  EXTRA_ARGS="-threads 6"
  ```
- **Mechanism**: Keeps FFmpeg execution within the physical core limit (4 cores / 6 execution pipelines), preventing hyperthreading cache thrashing and context-switch spikes.
- **Expected Speedup**: Stabilizes multi-job concurrency, eliminating the ~48% speed collapse during simultaneous jobs.
- **Risk Level**: **Zero**.
- **Reversibility**: Remove flag from wrapper script.

---

### Candidate D: Compliant Media Remux Passthrough (`-c copy`)
- **Target Component**: `bot/oxmit/media.py` and `bot/oxmit/engine.py`
- **Current Behavior**: Re-encodes every uploaded video even if it is already within Telegram size limits, has `h264` video, `aac` stereo audio, and standard aspect ratio.
- **Proposed Optimization**:
  Inspect source metadata in `media.py`:
  If `codec_name == "h264"` AND `file_size <= target_size` AND `pix_fmt == "yuv420p"`:
  Bypass transcoding entirely and execute remux:
  ```bash
  ffmpeg -i source.mp4 -c copy -movflags +faststart out.mp4
  ```
- **Expected Speedup**: **100x to 200x faster** for compliant videos (completes in 1.5 seconds instead of 15 minutes).
- **Risk Level**: Low (requires strict metadata validation).
- **Reversibility**: Feature flag in `.env` (`FASTPATH_COPY_ENABLED=true/false`).

---

### Candidate E: Audio Stream-Copy Bypass (`-c:a copy`)
- **Target Component**: Encore profile generation in `bot/oxmit/engine.py`
- **Current Behavior**: Decodes and re-encodes audio to AAC 128k on every single file.
- **Proposed Optimization**:
  If input audio stream is already `aac` stereo at $\le 192\text{ kbps}$, pass `-c:a copy` to Encore instead of `-c:a aac -b:a 128k`.
- **Expected Speedup**: Saves 0.5s to 2.5s per job and eliminates generational audio compression artifacts.
- **Risk Level**: Very Low.
- **Reversibility**: Toggled in profile generation logic.

---

### Candidate F: Hardware-Accelerated Worker Node (NVENC / QuickSync)
- **Target Component**: New Docker worker container configured on a GPU/QuickSync host.
- **Mechanism**: Offload encoding to fixed-function silicon (`h264_nvenc` or `h264_qsv`).
- **Expected Speedup**: **4x to 8x faster** (200+ FPS per stream).
- **Risk Level**: Requires infrastructure migration or hybrid worker pool.
- **Reversibility**: Switch Encore worker registration back to CPU worker.
