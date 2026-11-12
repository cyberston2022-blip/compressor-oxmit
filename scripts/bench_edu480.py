#!/usr/bin/env python3
"""EDU480 benchmark: encode representative samples with candidate settings
and report speed, size and quality (SSIM vs. the source scaled to the same
geometry). Run it on the production server against REAL educational samples
(whiteboard, slides, classroom, screen recording) before changing
EDU480_CRF / EDU480_PRESET / EDU480_MAX_FPS.

    python3 scripts/bench_edu480.py sample1.mp4 sample2.mkv --threads 3 \
        --variants "veryfast:25:30" "faster:25:30" "superfast:25:30" "veryfast:27:30"

Each variant is preset:crf:max_fps. Uses the same filter chain the bot sends
to Encore (bot/oxmit/edu480.py). Writes a CSV next to stdout output.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bot"))
from oxmit import edu480  # noqa: E402


def probe(path: str) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json",
                          "-show_format", "-show_streams", path],
                         capture_output=True, check=True).stdout
    d = json.loads(out)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    num, den = (v.get("avg_frame_rate") or "0/1").split("/")
    return {"width": v["width"], "height": v["height"],
            "fps": float(num) / float(den) if float(den) else 0,
            "duration_s": float(d["format"].get("duration") or 0),
            "size": int(d["format"].get("size") or 0)}


def run_variant(src: str, p: dict, preset: str, crf: int, max_fps: float,
                threads: int, tmp: str) -> dict:
    vf, fpsf = edu480.video_filters(p, max_fps)
    chain = ",".join(x for x in (vf, fpsf) if x != "null") or "null"
    out = os.path.join(tmp, f"o_{preset}_{crf}_{int(max_fps)}.mp4")
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", chain, "-c:v", "libx264",
           "-preset", preset, "-crf", str(crf), "-aq-mode", "3", "-rc-lookahead", "40",
           "-threads", str(threads), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k",
           "-movflags", "+faststart", out]
    t0 = time.perf_counter()
    r0 = os.times()
    subprocess.run(cmd, check=True)
    r1 = os.times()
    wall = time.perf_counter() - t0
    cpu = (r1.children_user - r0.children_user) + (r1.children_system - r0.children_system)
    # SSIM of the output vs. the source brought to the same geometry/fps.
    ref = f"[1:v]{chain}[ref];[0:v][ref]ssim" if chain != "null" else "[0:v][1:v]ssim"
    s = subprocess.run(["ffmpeg", "-v", "info", "-i", out, "-i", src, "-lavfi", ref,
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    ssim = None
    for line in s.splitlines():
        if "SSIM" in line and "All:" in line:
            ssim = float(line.split("All:")[1].split()[0])
    size = os.path.getsize(out)
    dur = p["duration_s"] or 1
    return {"preset": preset, "crf": crf, "max_fps": max_fps, "filters": chain,
            "wall_s": round(wall, 2), "realtime_x": round(dur / wall, 2),
            "cpu_s_per_media_min": round(cpu / dur * 60, 2),
            "out_mb": round(size / 1048576, 2),
            "ratio_pct": round(100 * size / max(1, p["size"]), 1),
            "ssim": ssim}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("samples", nargs="+")
    ap.add_argument("--threads", type=int, default=3)
    ap.add_argument("--variants", nargs="+",
                    default=["veryfast:25:30", "faster:25:30", "superfast:25:30",
                             "veryfast:27:30", "veryfast:25:60"])
    ap.add_argument("--csv", default="bench_edu480.csv")
    a = ap.parse_args()
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for src in a.samples:
            p = probe(src)
            for v in a.variants:
                preset, crf, fps = v.split(":")
                r = run_variant(src, p, preset, int(crf), float(fps), a.threads, tmp)
                r["sample"] = os.path.basename(src)
                r["source"] = f"{p['width']}x{p['height']}@{p['fps']:.2f} {p['duration_s']:.0f}s"
                rows.append(r)
                print(json.dumps(r, ensure_ascii=False))
    with open(a.csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {a.csv}")


if __name__ == "__main__":
    main()
