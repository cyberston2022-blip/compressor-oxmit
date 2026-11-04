# 02 — CURRENT ARCHITECTURE ANALYSIS

## 1. System Overview

Oxmit is an asynchronous distributed video processing system integrated with the Telegram Bot API. It receives video and audio media from Telegram users, applies compression, aspect-ratio correction, scaling, or repair transformations according to user-selected presets, and delivers the encoded media back to Telegram.

The architecture decouples the front-end user interaction layer from the compute-intensive media processing pipeline through a job queue and an orchestration engine (SVT Encore).

---

## 2. End-to-End Media Pipeline

The complete flow from user message dispatch to final artifact upload is illustrated below:

```mermaid
flowchart TD
    User([Telegram User]) -->|1. Sends Video Message| BotAPI[Telegram Local Bot API\noxmit-botapi]
    BotAPI -->|2. Webhook / Polling| Bot[Oxmit Bot Application\noxmit-bot]
    
    subgraph Ingestion & Pre-validation
        Bot -->|3. Record Metadata| PG[(PostgreSQL\noxmit-postgres)]
        Bot -->|4. Download Video| LocalFS[(Shared Storage\n/media/incoming)]
        Bot -->|5. Inspect Stream| FFprobe[FFprobe Metadata Extraction]
        Bot -->|6. Generate Thumbnail| Thumb[FFmpeg Thumbnail Generator]
    end
    
    subgraph Job Queue & Orchestration
        Bot -->|7. Enqueue Job| RedisQueue[(Redis Queue / Celery)]
        RedisQueue -->|8. Spawn Dispatch| Engine[Oxmit Engine\nbot/oxmit/engine.py]
        Engine -->|9. HTTP POST /api/jobs| EncoreWeb[Encore Coordinator\noxmit-encore-web:8080]
        EncoreWeb -->|10. Store Job State| SQLite[(Encore Internal SQLite)]
    end
    
    subgraph Distributed Transcoding
        Worker1[Encore Worker 1\noxmit-encore-worker-1] -->|11. Poll HTTP GET /api/jobs| EncoreWeb
        Worker2[Encore Worker 2\noxmit-encore-worker-2] -->|11. Poll HTTP GET /api/jobs| EncoreWeb
        Worker1 -->|12. Execute Wrapper| FFmpegWrap[/deploy/wrapper/ffmpeg]
        FFmpegWrap -->|13. Multi-threaded Encode| StaticFFmpeg[FFmpeg 7.0.2 Static]
        StaticFFmpeg -->|14. Write Chunk / Out| OutFS[(Shared Storage\n/media/out)]
    end
    
    subgraph Status & Progress Monitoring
        StaticFFmpeg -->|15. Stdout Progress| Worker1
        Worker1 -->|16. HTTP PUT /api/jobs/{id}/progress| EncoreWeb
        Engine -->|17. Poll Progress (Every 3s)| EncoreWeb
        Engine -->|18. Update Telegram Message| Bot
        Bot -->|19. Edit Message UI| User
    end
    
    subgraph Finalization & Delivery
        EncoreWeb -->|20. Job Status: SUCCESS| Engine
        Engine -->|21. Move to Archive / Verify| Archive[Oxmit Archive Subsystem]
        Archive -->|22. Upload via Local Bot API| BotAPI
        BotAPI -->|23. Fast Local Transfer| User
        Archive -->|24. Background Cleanup| Cleanup[Media Cleanup Task]
    end
```

---

## 3. Component Deep Dive & IPC Protocols

### 3.1 Telegram Bot & Local Bot API
- **Container**: `oxmit-bot` (Python 3.11+, `python-telegram-bot` v20+).
- **Bot API Service**: `oxmit-botapi` running the Telegram Bot API server in `--local` mode.
- **IPC Protocol**: Local HTTP requests over internal Docker bridge (`http://oxmit-botapi:8081`).
- **Advantage**: Downloading media files avoids roundtripping across the public Internet to Telegram servers; files are written directly into mounted local storage paths (`/media/incoming/`).

### 3.2 Database & Queue Layer
- **PostgreSQL (`oxmit-postgres`)**: Stores persistent state:
  - User accounts, subscription tiers, usage limits.
  - Historical jobs (`jobs` table with UUIDs, status, durations, input/output file sizes, profiles).
  - Admin audit trails.
- **Redis (`oxmit-redis`)**: High-speed broker for asynchronous task distribution and distributed locks.

### 3.3 Orchestration Engine: SVT Encore
- **Container**: `oxmit-encore-web` (Java Spring Boot, port 8080).
- **Repository**: Open-source SVT Encore transcoding orchestrator.
- **Role**:
  - Translates profile JSON configurations into parameterized FFmpeg command lines.
  - Manages worker heartbeats and distributed lock allocation.
  - Coordinates segment splitting and concatenation when segmented encoding is enabled.
- **API Protocol**: RESTful JSON over HTTP (`/api/jobs`, `/api/profiles`).

### 3.4 Transcoding Workers
- **Containers**: `oxmit-encore-worker-1` and `oxmit-encore-worker-2`.
- **Worker Execution Loop**:
  1. Worker continuously polls `oxmit-encore-web:8080` for queued jobs (`status=QUEUED`).
  2. Claims job and transitions state to `RUNNING`.
  3. Invokes `/opt/oxmit/deploy/wrapper/ffmpeg` as a subprocess.
  4. Parses FFmpeg stdout progress messages (`frame=`, `fps=`, `out_time_ms=`) and streams progress back to Encore via HTTP PUT.
  5. Upon exit code 0, verifies output file presence and marks job `SUCCESSFUL`.

---

## 4. File Handoffs and Storage Lifecycle

The application relies on shared volume mounts between host and containers:
- `/media/incoming/`: Ingest directory where downloaded Telegram source videos reside.
- `/media/out/`: Transcoding destination where FFmpeg writes intermediate and final MP4 files.
- `/media/work/`: Dedicated scratch directory for Encore segmented chunks and concatenation lists.
- `/media/archive/`: Staging directory for post-processed artifacts awaiting upload or permanent retention.

### Storage Lifecycle Flow
1. **Creation**: `bot/oxmit/media.py` creates a dedicated UUID directory: `/media/incoming/{job_id}/source.mp4`.
2. **Processing**: Encore Worker writes directly to `/media/out/{job_id}/out.mp4`.
3. **Verification**: `bot/oxmit/engine.py` validates `out.mp4` with `ffprobe`.
4. **Delivery**: Artifact is transferred to Telegram Bot API.
5. **Purge**: Background cleanup task deletes `/media/incoming/{job_id}` and `/media/out/{job_id}` after delivery confirmation.

---

## 5. Concurrency Model & Contention Analysis

The concurrency hierarchy operates across four distinct tiers:

| Tier | Component | Concurrency Mechanism | Current Setting | Contention Risk |
|---|---|---|---|---|
| **Tier 1** | Bot Webhook / Polling | Asyncio event loop | Async event loop (coroutine based) | Very low; I/O bound |
| **Tier 2** | Redis Queue Dispatch | Celery / Async Worker | Dynamic pool (1 - 4 tasks) | Low |
| **Tier 3** | Encore Transcoding Workers | Independent Docker containers | Worker-1 (active), Worker-2 (scale=1/restart) | **High**: Multiple workers compete for 8 vCPUs |
| **Tier 4** | FFmpeg Internal Threads | Frame & Slice Threading | `-threads 0` (libx264/x265 auto) | **Critical**: FFmpeg spawns 1.5x vCPUs = 12 threads |

### The Oversubscription Multiplier
When two Encore workers are active simultaneously:
- Worker 1 runs FFmpeg with `auto` threads -> spawns 12 threads.
- Worker 2 runs FFmpeg with `auto` threads -> spawns 12 threads.
- **Total active encoding threads: 24 threads competing for 8 vCPUs**.
- Result: Severe context switching overhead, L1/L2 cache thrashing, and elevated CPU run-queue latency (`load average > 16.0`).
