#!/usr/bin/env python3
"""Load test / functional test driver hitting the bot's internal test API.

Run on the VPS:  python3 scripts/loadtest.py --token <INTERNAL_TEST_TOKEN>

Modes:
  pipeline   - one end-to-end encode through a generated file (default)
  dedup      - same file twice sequentially (2nd must reuse) + 6 concurrent
               duplicates (must coalesce into one encode)
  burst      - N distinct files submitted concurrently (bounded by design)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8090"


def post(path: str, token: str, body: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Test-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def get(path: str, token: str) -> dict:
    req = urllib.request.Request(BASE + path, headers={"X-Test-Token": token})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


async def wait_job(token: str, job_id: str, timeout: int = 1800) -> dict:
    start = time.time()
    last = None
    while time.time() - start < timeout:
        try:
            job = get(f"/internal/test/job/{job_id}", token)
        except Exception as exc:  # noqa: BLE001
            print(f"  poll error: {exc}")
            await asyncio.sleep(5)
            continue
        status = job.get("status")
        progress = job.get("progress", 0)
        if (status, progress) != last:
            print(f"  [{int(time.time() - start)}s] {status} {progress}%")
            last = (status, progress)
        if status in ("completed", "failed", "cancelled"):
            return job
        await asyncio.sleep(5)
    raise TimeoutError(f"job {job_id} did not finish in {timeout}s")


async def pipeline(token: str, secs: int, profile: str, big: bool) -> None:
    print(f"== pipeline: gen {secs}s ({'1080p' if big else '720p'}) profile={profile}")
    gen = post("/internal/test/gen", token, {"secs": secs, "big": big})
    print(f"  generated: {gen['size'] / 1e6:.1f}MB {gen['path']}")
    t0 = time.time()
    sub = post("/internal/test/submit", token,
               {"path": gen["path"], "profile": profile, "allow_no_archive": True})
    print(f"  submitted: {sub}")
    if sub.get("outcome") != "queued":
        return
    job = await wait_job(token, sub["job_id"])
    dt = time.time() - t0
    print(
        f"  RESULT: status={job['status']} src={job['source_size']} out={job['output_size']} "
        f"wall={dt:.0f}s no_gain={job['is_no_gain']} err={job.get('error_message')}"
    )


async def dedup_test(token: str) -> None:
    print("== dedup: generate one file")
    gen = post("/internal/test/gen", token, {"secs": 20})
    path = gen["path"]

    print("== first submission (should encode)")
    sub1 = post("/internal/test/submit", token,
                {"path": path, "profile": "balanced", "allow_no_archive": True})
    print(f"  {sub1}")

    print("== second submission AFTER completion (should reuse archive)")
    await wait_job(token, sub1["job_id"])
    sub2 = post("/internal/test/submit", token,
                {"path": path, "profile": "balanced", "allow_no_archive": True})
    print(f"  {sub2}")
    assert sub2["outcome"] in ("reused",), f"expected reuse, got {sub2}"

    print("== 6 concurrent duplicates while encoding (should coalesce)")
    gen2 = post("/internal/test/gen", token, {"secs": 40})
    outs = await asyncio.gather(
        *[
            asyncio.to_thread(
                post, "/internal/test/submit", token,
                {"path": gen2["path"], "profile": "balanced", "allow_no_archive": True},
            )
            for _ in range(6)
        ]
    )
    outcomes = [o.get("outcome") for o in outs]
    print(f"  outcomes: {outcomes}")
    queued = [o for o in outcomes if o == "queued"]
    assert len(queued) <= 1, f"more than one encode started: {outcomes}"
    job_id = next(o["job_id"] for o in outs if o["outcome"] == "queued")
    await wait_job(token, job_id)
    stats = get("/internal/stats", token)
    print(f"  counters: {json.dumps(stats['counters'])}")


async def burst(token: str, n: int) -> None:
    print(f"== burst: {n} distinct files concurrently")
    gens = [post("/internal/test/gen", token, {"secs": 30}) for _ in range(n)]
    t0 = time.time()
    subs = await asyncio.gather(
        *[
            asyncio.to_thread(
                post, "/internal/test/submit", token,
                {"path": g["path"], "profile": "balanced", "allow_no_archive": True},
            )
            for g in gens
        ]
    )
    print(f"  submit latency: {time.time() - t0:.1f}s outcomes={[s.get('outcome') for s in subs]}")
    job_ids = [s["job_id"] for s in subs if s.get("outcome") == "queued"]
    await asyncio.gather(*[wait_job(token, j) for j in job_ids])
    stats = get("/internal/stats", token)
    print(f"  counters: {json.dumps(stats['counters'])}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--mode", default="pipeline",
                    choices=["pipeline", "dedup", "burst"])
    ap.add_argument("--secs", type=int, default=30)
    ap.add_argument("--profile", default="balanced")
    ap.add_argument("--big", action="store_true")
    ap.add_argument("--n", type=int, default=4)
    args = ap.parse_args()
    if args.mode == "pipeline":
        asyncio.run(pipeline(args.token, args.secs, args.profile, args.big))
    elif args.mode == "dedup":
        asyncio.run(dedup_test(args.token))
    else:
        asyncio.run(burst(args.token, args.n))


if __name__ == "__main__":
    main()
