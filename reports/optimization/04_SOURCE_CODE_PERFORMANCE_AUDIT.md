# 04 — Source Code Performance & Pipeline Audit

## Key Architectural Findings
1. **`bot/oxmit/engine.py`**:
   - `handle_submission()` orchestrated admission, dedup, and job creation.
   - Profile params were statically loaded from profiles or minimal formulas.
   - No dynamic preset or thread capping injection was performed.
   - Stream bypass was only invoked if `profile_key == "remux"`.
2. **`bot/oxmit/profiles.py`**:
   - Resolution profiles (`r1080`, `r720`, `r480`) strictly guarded against upscaling via `resolve_variant()`.
   - Bitrate calculation clamped to 200 kbps minimum floor.
3. **`bot/oxmit/encore_client.py`**:
   - Uses `httpx.AsyncClient` with Spring Boot REST API (`/encoreJobs`).
   - Cleanly forwards `profileParams` and `inputParams`.
4. **`deploy/encore/profiles/*.yml`**:
   - Profiles evaluate SpEL expressions for dynamic properties (e.g. `#{profileParams['bv'] ?: '2000k'}`).
   - Missing SpEL dynamic bindings for `preset`, `crf`, and `threads` in several profiles.
