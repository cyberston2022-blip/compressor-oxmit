# 15 — Optimization Decision Engine Architecture

## Module Architecture: `bot/oxmit/decision_engine.py`

### 1. Structure
```
decision_engine.py
├── EncodingDecision (Dataclass)
├── detect_content_category(probe) -> str
├── can_smart_bypass(probe, profile, target_mb, size_bytes) -> bool
├── can_copy_audio(probe) -> bool
├── select_adaptive_resolution(w, h, kbps, category) -> (w, h, filter)
└── make_decision(probe, profile_key, size_bytes, ...) -> EncodingDecision
```

### 2. Operational Logic
When `JobEngine.handle_submission()` receives a media submission, it calls `decision_engine.make_decision()`:
1. Evaluates fastpath remux eligibility. If eligible, returns `action="remux_only"` (`effective_profile="remux"`).
2. If custom target size: computes exact bitrate budget, checks whether 1-pass or 2-pass is required, applies low-bitrate adaptive resolution (protecting screen text).
3. If standard profile: injects optimal preset (`veryfast` for balanced/tgcompat, `superfast` for maxcomp, dynamic ladder for level).
4. Injects dynamically tuned `-threads` based on current server concurrency.
