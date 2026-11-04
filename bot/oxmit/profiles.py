"""Compression profiles exposed to users, mapped to Encore profile names."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    key: str
    encore_name: str
    title: str
    title_fa: str
    description: str
    version: int = 1
    # For resolution variants: max short side of the frame (0 = keep source).
    max_short_side: int = 0
    # Fixed output width the corresponding Encore profile scales to
    # (0 = no fixed width). The bot must never request a wider-than-source
    # scale, otherwise portrait/4:3 sources would be upscaled.
    target_width: int = 0


PROFILES: list[Profile] = [
    Profile("level", "level", "Smart compress", "فشرده‌سازی هوشمند",
            "CRF scale 1-20 - content-adaptive size, watchable quality"),
    Profile("level265", "level265", "Smart compress HEVC", "فشرده‌سازی هوشمند HEVC",
            "HEVC escalation pass - auto-triggered when x264 has no size gain"),
    Profile("balanced", "balanced", "Balanced", "متعادل",
            "H.264 CRF22 - balance of quality, size and speed"),
    Profile("highq", "highq", "High quality", "کیفیت بالا",
            "H.264 CRF19 - preserves visual quality"),
    Profile("small", "small", "Smaller file", "حجم کمتر",
            "HEVC/H.265 CRF27 - smaller file, slower encode"),
    Profile("maxcomp", "maxcomp", "Max compression", "حداکثر فشرده‌سازی",
            "HEVC/H.265 CRF30 - smallest size, slowest"),
    Profile("tgcompat", "tgcompat", "Telegram compat", "سازگاری تلگرام",
            "H.264 High + AAC + faststart"),
    Profile("r1080", "r1080", "1080p", "کاهش به ۱۰۸۰p",
            "Scale to 1080p (no upscale)", max_short_side=1080, target_width=1920),
    Profile("r720", "r720", "720p", "کاهش به ۷۲۰p",
            "Scale to 720p (no upscale)", max_short_side=720, target_width=1280),
    Profile("r480", "r480", "480p", "کاهش به ۴۸۰p",
            "Scale to 480p (no upscale)", max_short_side=480, target_width=854),
    Profile("custom", "custom", "Custom target size", "حجم دلخواه",
            "Target bitrate computed from the requested output size"),
    Profile("custom_2pass", "custom_2pass", "Custom 2-pass", "حجم دلخواه ۲-پاس",
            "Target bitrate with strict 2-pass ABR"),
    Profile("remux", "remux", "Fast remux (no re-encode)", "remux سریع",
            "Container shift to MP4+faststart, stream copy - seconds not minutes"),
]

# Estimator inputs per profile (codec, crf, preset, target short side or None).
ESTIMATE_PARAMS = {
    "level": ("h264", 23, "faster", None),
    "level265": ("hevc", 33, "superfast", None),
    "balanced": ("h264", 22, "veryfast", None),
    "highq": ("h264", 19, "faster", None),
    "small": ("hevc", 27, "faster", None),
    "maxcomp": ("hevc", 30, "superfast", None),
    "tgcompat": ("h264", 22, "veryfast", None),
    "r1080": ("h264", 22, "faster", 1080),
    "r720": ("h264", 23, "faster", 720),
    "r480": ("h264", 23, "faster", 480),
    "custom_2pass": ("h264", 23, "faster", None),
}

BY_KEY = {p.key: p for p in PROFILES}
_RES_ORDER = ["r1080", "r720", "r480"]

_LEVEL_CRF_LOW, _LEVEL_CRF_HIGH = 18, 28


def crf_for_level(level: int) -> int:
    """Map the user level 1..20 to x264 CRF 18..28.

    CRF is content-adaptive: the achieved size reduction depends on the video
    (level 20 may cut ~60% on typical content). The range tops out at CRF 28
    so the result stays watchable - visibly compressed but not mushy.
    """
    level = max(1, min(20, int(level)))
    return round(_LEVEL_CRF_LOW + (level - 1) * (_LEVEL_CRF_HIGH - _LEVEL_CRF_LOW) / 19)


def preset_for_level(level: int) -> str:
    """Preset ladder alongside the CRF ladder.

    Kept speed-first: low levels run the fastest preset, everything else runs
    `faster`. Stronger compression for tight sources is the job of the
    automatic HEVC escalation, not of slower x264 presets.
    """
    level = max(1, min(20, int(level)))
    return "veryfast" if level <= 6 else "faster"


def resolve_variant(profile_key: str, src_w: int | None, src_h: int | None) -> str:
    """Pick the encore profile for a request, never upscaling the source.

    The resolution profiles scale to a fixed target WIDTH, so a source whose
    width is narrower than that target (portrait or 4:3 material) would be
    upscaled even when its short side passes the check. A variant is chosen
    only when BOTH the target width and the short side fit; otherwise the
    next smaller variant, or `balanced` when no variant fits.
    """
    prof = BY_KEY[profile_key]
    if prof.max_short_side == 0:
        return prof.encore_name
    if not src_w or not src_h or src_w <= 0 or src_h <= 0:
        return "balanced"
    src_short = min(src_w, src_h)
    for key in _RES_ORDER:
        cand = BY_KEY[key]
        if cand.max_short_side > prof.max_short_side:
            continue
        if (src_w >= cand.target_width
                and src_short >= cand.max_short_side):
            return cand.encore_name
    return "balanced"


def compute_target_params(
    target_mb: int,
    duration_s: float | None,
    source_size: int,
    min_video_kbps: int = 200,
    audio_kbps: int = 96,
    container_overhead_pct: float = 1.5,
) -> tuple[int, str | None]:
    """Estimate video bitrate (kbps) for a requested output size in MB.

    Returns (kbps, status) - status is None on success, "low_bitrate" when the
    requested target would push the video bitrate below the quality floor
    (kbps is then clamped to the floor for a best-effort encode), or
    "bad_target" when the request is not meaningful at all.
    """
    target_bytes = target_mb * 1024 * 1024
    if target_mb <= 0:
        return 0, "bad_target"
    if source_size and target_bytes >= source_size:
        return 0, "bad_target"  # target must be smaller than the source
    if not duration_s or duration_s <= 0:
        return 0, "bad_target"
    usable = target_bytes * (1 - container_overhead_pct / 100)
    audio_bits = audio_kbps * 1000 * duration_s
    video_bits = usable * 8 - audio_bits
    kbps = int(video_bits / duration_s / 1000)
    if kbps < min_video_kbps:
        return min_video_kbps, "low_bitrate"
    return kbps, None
