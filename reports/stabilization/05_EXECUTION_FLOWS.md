# Execution Flows

## 1. Video Intake Flow
1. User sends a video or document message.
2. `handlers/intake.py` validates file size, user quotas, and channel subscription.
3. Media asset registered; SHA-256 and fuzzy deduplication queried.
4. If cached in archive: direct delivery via `copyMessage` or `forwardMessage`.
5. If new: staged to `/media` volume, job enqueued in PostgreSQL.

## 2. Transcoding Flow
1. `JobEngine.run_job` verifies disk headroom and reserves quota.
2. Submits job to SVT Encore Web API with selected profile parameters.
3. Workers pick up task from Redis queue, transcode via FFmpeg 7.0.2.
4. Progress updates received via callback and periodic polling.
5. On completion: output duration validated, thumbnail extracted, uploaded to archive channel, delivered to user.
6. Temporary staging files immediately cleaned up.
