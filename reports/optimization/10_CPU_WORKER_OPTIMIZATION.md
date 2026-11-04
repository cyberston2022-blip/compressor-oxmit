# 10 — CPU Worker & Thread Allocation Optimization

## Linux CFS Thread Throttling Elimination
On an 8-vCPU host running two concurrent workers alongside PostgreSQL, Redis, and Telegram Bot API:
- When FFmpeg runs unconstrained (`-threads 0`), it spawns 12–16 worker threads per process ($24	ext{--}32$ active threads total).
- The Linux Completely Fair Scheduler (CFS) rapidly preempts threads across CPU cores, inducing severe L1/L2 cache evictions, context switching latency, and thread lock contention.

## Dynamic Thread Capping
We introduced explicit thread allocation via SpEL bindings in profile YAMLs:
- **Single Job Mode**: `threads: 6` (Leaves 2 full vCPUs for database, bot API, and OS).
- **Concurrent Job Mode**: `threads: 3` (3 threads per worker = 6 threads total, perfectly saturating encoding capacity without CFS thrashing).

Tuned through `FFMPEG_THREADS_SINGLE` and `FFMPEG_THREADS_MULTI` in `config.py`.
