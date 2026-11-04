# 09 — Content-Aware Compression & Media Classification

## Heuristic Classification Engine
Implemented in `bot/oxmit/decision_engine.py::detect_content_category()`:

```python
def detect_content_category(probe: dict[str, Any]) -> str:
    # 1. Filename heuristic
    screen_keywords = ("screen", "record", "tutorial", "lecture", "slide", "demo", "course", "zoom", "obs", "meet")
    if any(k in filename for k in screen_keywords):
        return "screen_text"

    # 2. Bits-per-pixel ratio heuristic
    if width > 0 and height > 0 and duration_s > 5.0 and bitrate > 0:
        pixels_per_sec = width * height * fps
        bpp = bitrate / pixels_per_sec
        if bpp < 0.04:  # Extremely low temporal variance
            return "screen_text"

    # 3. Cinematic film heuristic
    if 23.0 <= fps <= 24.5 and (width >= 1920 or height >= 1080):
        return "film_motion"

    return "general"
```

This classification allows the decision engine to select custom quantization, rate control, and scaling policies per content type.
