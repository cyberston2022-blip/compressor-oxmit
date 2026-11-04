# Static Analysis & Security Scanning Report

- **Tool:** Bandit v1.8.3
- **Target:** `bot/oxmit`
- **Total Scanned Files:** 18 Python modules
- **Total Findings:** 47 automated flags
  - **High Severity:** 0
  - **Medium Severity:** 5 (3 SQL f-strings, 2 0.0.0.0 network binds)
  - **Low Severity:** 42 (assert statements, try-except-pass, subprocess invocations)
- **Review of Medium Findings:**
  - `dedup.py` (B608): Fixed float tolerance formatting, verified no user injection vector.
  - `webpanel.py` (B608): Whitelisted column names (`is_blocked`, `is_vip`), verified safe.
  - `internal_api.py` (B104): 0.0.0.0 binding inside Docker container network, mapped selectively in compose.
