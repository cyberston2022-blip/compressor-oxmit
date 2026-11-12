"""Real-ffmpeg smoke test for merge.py (run on the server with
PYTHONPATH=/opt/oxmit/bot). Generates two tiny clips, runs the copy and
re-encode strategies, validates output duration."""
import asyncio
import subprocess
import sys
import uuid

sys.path.insert(0, "/opt/oxmit/bot")

from oxmit import merge as m  # noqa: E402
from oxmit import media as media_mod  # noqa: E402

WORK = "/tmp/oxmit-merge-smoke"


def make_clip(path, color, secs=3):
    subprocess.run([
        "ffmpeg", "-nostdin", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"testsrc2=size=320x240:rate=15:duration={secs}",
        "-f", "lavfi", "-i", f"sine=frequency={color}:duration={secs}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        path,
    ], check=True, capture_output=True)


async def main():
    subprocess.run(["rm", "-rf", WORK], check=False)
    import os
    os.makedirs(WORK, exist_ok=True)
    a, b = f"{WORK}/a.mp4", f"{WORK}/b.mp4"
    make_clip(a, 440)
    make_clip(b, 880)
    pa, pb = await media_mod.probe_video(a), await media_mod.probe_video(b)
    strategy, why = m.decide_strategy([pa, pb])
    print("strategy:", strategy, "|", why)
    assert strategy == "copy", "two identical-config clips must stream-copy"

    out = f"{WORK}/merged_copy.mp4"
    await m.run_copy_merge([a, b], out, WORK)
    dur = await m.validate_output(out, pa["duration_s"] + pb["duration_s"])
    print(f"copy merge OK: duration={dur:.2f}s")

    # re-encode strategy: different resolutions
    c = f"{WORK}/c.mp4"
    subprocess.run([
        "ffmpeg", "-nostdin", "-y", "-v", "error",
        "-f", "lavfi", "-i", "testsrc2=size=640x480:rate=25:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=660:duration=2",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "32000",
        c,
    ], check=True, capture_output=True)
    pc = await media_mod.probe_video(c)
    strategy, why = m.decide_strategy([pa, pc])
    print("strategy:", strategy, "|", why)
    assert strategy == "reencode"
    out2 = f"{WORK}/merged_reencode.mp4"
    await m.run_reencode_merge([a, c], out2, WORK, m.normalize_target([pa, pc]),
                               durations=[pa["duration_s"], pc["duration_s"]])
    dur2 = await m.validate_output(out2, pa["duration_s"] + pc["duration_s"])
    print(f"re-encode merge OK: duration={dur2:.2f}s")

    # validation gate: truncated output must fail
    bad = f"{WORK}/bad.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", a,
                    "-c", "copy", bad], check=True, capture_output=True)
    try:
        await m.validate_output(bad, 9999.0)
        print("FAIL: validation gate did not catch truncated output")
        sys.exit(1)
    except m.MergeError as exc:
        print("validation gate OK:", str(exc)[:60])
    print("MERGE_SMOKE_ALL_OK")


asyncio.run(main())
