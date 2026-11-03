# Third-Party Notices and Attribution

This file records third-party components used by the Oxmit deployment and
open-source projects consulted during development, with their licenses.

## Runtime components

| Component | Version / Commit | License | Provenance | Notes |
|---|---|---|---|---|
| SVT Encore (encore-web, encore-worker) | GHCR image `1.0.0` | EUPL-1.2-or-later | ghcr.io/svt/encore | Used unmodified as the transcoding engine. © Sveriges Television AB. |
| Redis | docker `redis:8.6-alpine` | RSALv2/SSPLv1 (redis) | Docker Hub | Used as job queue/store per Encore requirements. |
| PostgreSQL | docker `postgres:17-alpine` | PostgreSQL License | Docker Hub | Application database. |
| telegram-bot-api (tdlib) | source commit `e3e9dd8e5b3d7ab8537cd5a10dc31d5ffa8f82d1` | BSL-1.0 (Boost) | github.com/tdlib/telegram-bot-api | Built from official source; run locally. |
| FFmpeg (workers) | **7.0.2 static** (johnvansickle build) | **GPL v3** (build includes libx264/libx265) | johnvansickle.com/ffmpeg | Deployed server-side only, not distributed. Replaces the bundled 8.1 (see Issue A). **SHA-256:** `e7e7fb30477f717e6f55f9180a70386c62677ef8a4d4d1a5d948f4098aa3eb99` (79,826,272 bytes; pinned via volume mount `deploy/wrapper/ffmpeg` → `/usr/local/bin/ffmpeg`, read-only). Obtainable from https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz — verify against the recorded hash before replacing. |
| FFmpeg / ffprobe (bot container) | Debian `7.1.5-0+deb13u1` | GPL/LGPL mix (Debian) | debian bookworm repo | Used for probing, thumbnails, splitting. |
| aiogram | `3.x` (pip) | MIT | github.com/aiogram/aiogram | Bot framework. |
| asyncpg / httpx / aiohttp / Pillow | pip | MIT/Apache-2.0/BSD | PyPI | Supporting libraries. |

## Ideas adopted from open-source projects (no code copied unless noted)

| Repository | License (verified) | Idea | Decision |
|---|---|---|---|
| ob22a/file-to-media-bot | MIT | Remux-only fast path (`-c copy -movflags +faststart`), thumbnail at 10% seek | **Adapted** — implemented as the `remux` profile with codec-compatibility gate |
| khadiscon/telegram-video-compressor-bot | MIT | Target-size bitrate formula (duration/size/audio overhead) — independently implemented earlier | **Validated equivalence**, no copy |
| aayushkdev/rendition | MIT | Stale-job reaper concept | **Already implemented** (progress-staleness + STUCK_MINUTES) |
| backblaze-b2-samples/videohash-deduplication | MIT | Audio-identity awareness for perceptual dedup | **Adapted** — similarity reuse now requires matching audio codec/channels |
| aiogram/aiogram docs/source | MIT | TelegramAPIServer override for Local Bot API; TelegramRetryAfter handling | **Adopted** |
| tdlib/telegram-bot-api | BSL-1.0 | `--local` mode semantics, umask/file-permission behavior | **Adopted** (umask 022 entrypoint) |
| shohan-001/ffmpeg-video-bot | MIT | Utility ideas (trim/extract) | **Rejected for now** (P2 scope) |
| Itzmepromgitman/ArgonsEncoder | GPL-3.0 | Queue persistence, disk reservation, deferred jobs, upload retry, bpp size/time estimate card | **Patterns reimplemented independently** (migration 004, estimate.py, _archive_upload) — no GPL code copied; Oxmit remains non-GPL |
| MughalBot/Encoding | AGPL-3.0 | Profile UX | **Study only** (license copyleft) |
| Unmanic/unmanic | GPL-3.0 | Library processing patterns | **Study only** (license copyleft) |
| HaveAGitGat/Tdarr | license unclear (NOASSERTION) | Distributed workers | **Study only, no reuse** |
| Liveserver01/Telegram-Video-Compress-Bot | **no license** | — | **No reuse permitted** |
| FractumSeraph/DistributedEncodes | **no license** | Streaming workers | **No reuse permitted** |
| do0p/deduplicator | license unclear (NOASSERTION) | Hash indexing | **No reuse permitted** |
| BaseMax/telegram-video-compressor | MIT | URL import | **Rejected** (security scope) |
| Aluval/PixelPulseBot | MIT + README deployment restriction | UX ideas | **Design reference only** (README restriction honored) |
