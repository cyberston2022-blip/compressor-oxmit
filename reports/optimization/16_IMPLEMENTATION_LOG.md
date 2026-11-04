# 16 — Implementation Changelog & Modified Components

## Summary of Changes
1. **`bot/oxmit/config.py`**:
   - Added configuration fields to `Settings`: `adaptive_codec_enabled`, `adaptive_resolution_enabled`, `fastpath_copy_enabled`, `audio_copy_enabled`, `custom_encoding_mode`, `ffmpeg_threads_single`, `ffmpeg_threads_multi`, `target_accuracy_tolerance_pct`.
   - Updated `load_settings()` and `validate()` with bounds checking.
2. **`bot/oxmit/decision_engine.py`**:
   - Created the complete decision engine module implementing content detection, fastpath remux, adaptive scaling, audio stream copy, and profile tuning.
3. **`bot/oxmit/profiles.py`**:
   - Added `custom_2pass` to `PROFILES` and `ESTIMATE_PARAMS`.
   - Updated baseline preset for `balanced` to `veryfast` and `maxcomp` to `superfast`.
4. **`bot/oxmit/engine.py`**:
   - Integrated `decision_engine.make_decision()` inside `handle_submission()`.
   - Enabled automatic routing to `remux` (stream copy) when smart fastpath is applicable.
   - Handled dynamic switching to `custom_2pass` for strict target adherence.
5. **Encore Profile YAMLs (`/opt/oxmit/deploy/encore/profiles/`)**:
   - `custom.yml`: Set `twoPass: false` and added SpEL `threads` and `preset`.
   - `custom_2pass.yml`: Created with `twoPass: true`.
   - `balanced.yml`: Upgraded default preset to `veryfast`.
   - `maxcomp.yml`: Upgraded default preset to `superfast`.
   - `small.yml`: Added SpEL `threads` and `preset`.
6. **`tests/test_decision_engine.py`**:
   - Added 10 unit tests verifying content classification, smart bypass, audio copy, adaptive resolution, and decision engine behavior.
