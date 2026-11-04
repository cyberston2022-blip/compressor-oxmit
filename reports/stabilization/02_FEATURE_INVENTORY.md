# Feature Inventory & Verification Matrix

| Feature | Implementation | Tests | Status | Notes |
|---|---|---|---|---|
| Video Intake & Compression | `handlers/intake.py`, `engine.py` | Verified (96 tests) | Fully Verified | Accepts videos up to 2GB via local Bot API |
| Dedup (SHA-256) | `dedup.py`, `archive.py` | Verified | Fully Verified | Instant delivery without re-encoding |
| Fuzzy Dedup (Perceptual) | `dedup.py`, `media.py` | Verified | Fully Verified | Size ±2%, name_norm, duration window |
| SVT Encore Transcoding | `encore_client.py`, `engine.py` | Verified | Fully Verified | Multi-profile bounded worker queue |
| Automatic Split Upload | `engine.py`, `media.py` | Verified | Fully Verified | Oversized videos split into playable parts |
| Channel Archival | `archive.py`, `engine.py` | Verified | Fully Verified | Private archive channel acts as canonical store |
| Delivery Fallback Chain | `archive.py` | Verified (new) | Fully Verified | forward -> copy -> file_id -> local upload |
| Dynamic CPU Tuning | `resources.py`, `bot.py` | Verified | Fully Verified | Throttles worker cores based on active jobs |
| Web Admin Panel v2 | `webpanel.py`, `internal_api.py`| Verified | Fully Verified | HTTPS on port 8090, CSRF & token auth |
| Daily Backup & Alerts | `scripts/backup.sh`, cron | Verified | Fully Verified | 03:00 UTC daily, 14-day retention, TG alerts |
