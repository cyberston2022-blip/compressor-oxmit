# 20 — Remaining Technical Debt & Future Architectural Roadmap

## 1. SVT-AV1 Exploration
- While AV1 achieves an additional $15	ext{--}25\%$ compression gain over HEVC, decoding support in older Telegram mobile clients is inconsistent.
- As hardware AV1 decoding reaches ubiquity, introducing an `av1` profile using SVT-AV1 (`preset 6` or `7`) will provide further size reductions.

## 2. Dynamic VBV Window Tuning
- For ultra-long videos ($>2$ hours), VBV buffer sizes could be modulated based on scene change frequency (`sc_threshold`).

## 3. Dedicated Perceptual VMAF Worker
- For VIP users or archival jobs, an asynchronous background VMAF verification task could validate encoded assets before delivery.
