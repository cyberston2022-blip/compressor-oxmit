# Compression Profiles

Profiles use the official Encore YAML format
(`encore-settings.profile.location=file:/profiles/profiles.yml`). The index file
maps bot profile keys to YAML files; the bot stores `(profile, version)` per job
and per archive record, so changing a YAML requires bumping `version` in
`bot/oxmit/migrations` (new row in `profiles`) or adding a new key.

| key | encore profile | video | audio | notes |
|---|---|---|---|---|
| balanced | balanced | H.264 (libx264) CRF22 preset faster | AAC 128k | default, good balance |
| highq | highq | H.264 CRF19 preset faster | AAC 160k | near-transparent |
| small | small | HEVC (libx265) CRF27 preset faster, tag hvc1 | AAC 96k | smaller, slower |
| maxcomp | maxcomp | HEVC CRF30 preset medium, tag hvc1 | AAC 96k | smallest, slowest |
| tgcompat | tgcompat | H.264 High, yuv420p, +faststart | AAC 128k | max player compatibility |
| r1080 | r1080 | H.264 CRF22, width 1920 | AAC 128k | never upscales |
| r720 | r720 | H.264 CRF23, width 1280 | AAC 128k | never upscales |
| r480 | r480 | H.264 CRF23, width 854 | AAC 96k | never upscales |

## No-upscale guarantee

Resolution profiles are resolved by the bot (`oxmit/profiles.py`):
`resolve_variant()` compares the source short side against the requested short
side and downgrades to the closest smaller variant (or `balanced` when the
source is smaller than 480). Encore is never asked to enlarge a source.

## Audio handling

All profiles re-encode audio to AAC (the Encore default encoder in the official
images; `libfdk_aac` is intentionally not used — not shipped in the prebuilt
images). First audio track; stereo downmix via Encore defaults. Multi-audio and
subtitle streams are not preserved by Encore 1.0.0 for this job shape —
documented limitation.

## Editing a profile

1. Edit the YAML in `deploy/encore/profiles/`.
2. `docker compose restart encore-web encore-worker` (profiles load at startup).
3. Bump the profile `version` (see above) so dedup does not mix outputs from
   different encoder settings.
