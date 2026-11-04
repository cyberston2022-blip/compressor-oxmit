# Risk Register & Mitigations

| Risk | Severity | Probability | Mitigation Implemented |
|---|---|---|---|
| Disk exhaustion during high concurrency | High | Low | Admission floor, need factor calculation, disk-defer queue |
| Telegram FloodWait during peak uploads | Medium | Medium | flood_safe wrapper with exponential backoff & single-retry |
| Worker OOMKilled during SpEL heavy jobs | Medium | Low | Docker memory limit set to 4.5GB with dynamic CPU tuner |
| Database connection pool exhaustion | Low | Low | Pool configured with min_size=2, max_size=10 |
