# Project Map

## Directory Layout
```
/opt/oxmit/
├── bot/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── oxmit/
│       ├── __init__.py
│       ├── __main__.py
│       ├── archive.py       # Telegram delivery & channel archive logic
│       ├── audit.py         # Persistent audit logging for admin actions
│       ├── bot.py           # Aiogram dispatcher, polling, and lifecycle
│       ├── config.py        # Typed settings and environment parsing
│       ├── db.py            # asyncpg connection pool & migrations
│       ├── dedup.py         # SHA-256 and fuzzy video deduplication
│       ├── encore_client.py # REST client for SVT Encore API
│       ├── engine.py        # Core JobEngine: transcoding pipeline coordinator
│       ├── estimate.py      # Video size and duration estimator
│       ├── forcesub.py      # Channel forced-subscription checking
│       ├── handlers/        # Aiogram route handlers (intake, menu, admin, settings)
│       ├── internal_api.py  # Aiohttp HTTP servers (callbacks & webpanel)
│       ├── log.py           # Structured JSON logger
│       ├── media.py         # FFprobe/FFmpeg metadata extraction & utilities
│       ├── migrations/      # 10 SQL migration scripts
│       ├── profiles.py      # Transcoding profiles and CRF calculation ladders
│       ├── resources.py     # Worker CPU tuner via Docker socket
│       ├── texts.py         # Bilingual text strings (Fa/En)
│       └── webpanel.py      # HTTPS Admin Management Web Panel
├── deploy/
│   ├── certs/               # TLS self-signed certificates
│   ├── encore/profiles/     # 12 SVT Encore transcoding profiles
│   ├── telegram-bot-api/    # Local Bot API tdlib Dockerfile
│   └── wrapper/ffmpeg       # Static FFmpeg 7.0.2 binary override
├── docker-compose.yml       # Multi-container orchestration
├── docs/                    # Architecture and ops documentation
├── scripts/                 # Backup, load testing, and counter reconciliation
├── tests/                   # Pytest test suite (96 tests)
└── reports/stabilization/   # Audit documentation and findings ledger
```
