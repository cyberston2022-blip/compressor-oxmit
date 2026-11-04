# System Architecture

## Overview
Oxmit utilizes a decoupled, resilient architecture centered around Docker Compose:

```
[ Telegram Users ]
       │
       ▼
 [ oxmit-bot (Aiogram 3 / Python 3.12) ]
       │                                ├── [ Telegram Local Bot API (tdlib) ]
       ├── PostgreSQL 17 (state store)  ├── [ /media shared volume (2TB space) ]
       ├── Redis 8.6 (queue/cache)      └── [ Private Archive Channel ]
       └── SVT Encore Web (Spring Boot)
              │
              ├── [ Worker 1 (FFmpeg 7.0.2) ]
              └── [ Worker 2 (FFmpeg 7.0.2) ]
```

## Security & Isolation
- All internal communication (PostgreSQL, Redis, Encore, Local Bot API) occurs over an isolated Docker network (`internal`).
- Only port 22 (SSH) and port 8090 (TLS Admin Panel) are accessible from the public internet.
- Storage is managed on host NVMe disk with automated purging and disk-guard thresholds.
