# 17 — Regression Test & Validation Report

## Execution Environment
- **Test Command**: `docker run --rm -v /opt/oxmit:/opt/oxmit -w /opt/oxmit oxmit-test:local pytest`
- **Python**: 3.12.16
- **Pytest**: 9.2.0 (with asyncio, cov, anyio)

## Results
```
============================= test session starts ==============================
collected 106 items

tests/test_admin_system.py .........                                     [  8%]
tests/test_admission.py .......                                          [ 15%]
tests/test_archive_delivery.py .....                                     [ 19%]
tests/test_audit.py ....                                                 [ 23%]
tests/test_counters_gated.py .....                                       [ 28%]
tests/test_decision_engine.py ..........                                 [ 37%]
tests/test_dedup_fuzzy.py ...                                            [ 40%]
tests/test_encore_client.py .....                                        [ 45%]
tests/test_engine_fixes.py .......                                       [ 51%]
tests/test_engine_robustness.py ...                                      [ 54%]
tests/test_estimate.py .....                                             [ 59%]
tests/test_forcesub.py ...                                               [ 62%]
tests/test_media_cleanup.py ....                                         [ 66%]
tests/test_media_utils.py .....                                          [ 70%]
tests/test_panel_security.py .........                                   [ 79%]
tests/test_profiles.py ....                                              [ 83%]
tests/test_regression_cleanup.py ....                                    [ 86%]
tests/test_regression_redeliver.py ..                                    [ 88%]
tests/test_resources.py ...                                              [ 91%]
tests/test_sec1_redaction.py .....                                       [ 96%]
tests/test_staging.py ....                                               [100%]

============================= 106 passed in 7.20s ==============================
```

**Result: 100% Pass Rate (106 / 106 passed). Zero regressions.**
