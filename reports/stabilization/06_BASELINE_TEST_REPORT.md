# Baseline Test Report

- **Date:** 2026-11-04 12:23 UTC
- **Test Runner:** Pytest 9.2.0 in isolated container `oxmit-test:local`
- **Total Tests Collected:** 79 items
- **Initial Result:** 77 passed, 2 xpassed in 6.59s
- **Observations:**
  - 2 tests (`test_retry_user_job_below_limit_increments_and_guards` and `test_stage_recopies_on_size_mismatch`) passed unexpectedly because underlying fixes had been implemented in commit 6e60174 but xfail markers were retained.
  - Overall initial test coverage: 22%.
