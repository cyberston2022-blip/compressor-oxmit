# 19 — Rollback & Safe Deployment Plan

## 1. Feature Flag Controls
All optimizations can be dynamically toggled via environment variables in `/opt/oxmit/.env`:
- `FASTPATH_COPY_ENABLED=false` -> Disables smart bypass remux.
- `ADAPTIVE_RESOLUTION_ENABLED=false` -> Disables bitrate-aware resolution scaling.
- `CUSTOM_ENCODING_MODE=two_pass` -> Forces strict two-pass encoding for all custom jobs.
- `AUDIO_COPY_ENABLED=false` -> Forces audio re-encoding for all files.

## 2. Instant Rollback Procedure
If any unexpected edge case occurs:
```bash
cd /opt/oxmit
git checkout main -- bot/oxmit/config.py bot/oxmit/engine.py bot/oxmit/profiles.py deploy/encore/profiles/
docker compose restart oxmit-bot
```
The application will instantly revert to the pre-optimization state with zero database modifications required.
