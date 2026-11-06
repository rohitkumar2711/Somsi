#!/usr/bin/env python3
"""Load test: N concurrent users, each pasting a response-sheet link.

    python3 loadtest.py --base http://127.0.0.1:8104 --users 1000 --distinct 20

Each virtual user gets its own X-Forwarded-For (so per-IP rate limits behave
like production) and either its own link or one of `--distinct` shared links -
because in real life a shift's link gets forwarded around a lot, which is what
the cache is for.

Reports: submit latency, end-to-end time (link -> score card), p50/p95/p99,
throughput, error count and a correctness check on every result.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import time

import httpx

URL_TPL = ("{base}/CGLE2026jsdgheQchallengemshetsOct13/ViewCandResponse.aspx"
           "?enckey={key}")


async def one_user(client: httpx.AsyncClient, base: str, sheet_base: str,
                   idx: int, distinct: int, expect: float | None, poll: float,
                   results: list):
    ip = f"10.{idx // 65536 % 250}.{idx // 256 % 256}.{idx % 256}"
    headers = {"X-Forwarded-For": ip}
    key = f"load{idx % distinct:04d}"
    url = URL_TPL.format(base=sheet_base, key=key)
    t0 = time.perf_counter()
    try:
        r = await client.post(f"{base}/api/analyze", json={"url": url},
                              headers=headers)
        submit = time.perf_counter() - t0
        if r.status_code != 200:
            results.append({"ok": False, "stage": "submit",
                            "code": r.status_code, "submit": submit})
            return
        job = r.json()["job_id"]
        deadline = time.perf_counter() + 180
        while True:
            if time.perf_counter() > deadline:
                results.append({"ok": False, "stage": "timeout",
                                "submit": submit,
                                "total": time.perf_counter() - t0})
                return
            # long-poll: the server answers the moment the job ends
            jr = await client.get(f"{base}/api/job/{job}?wait=1&timeout=25",
                                  headers=headers)
            j = jr.json()
            if j["status"] in ("done", "error"):
                break
            await asyncio.sleep(poll)
        total = time.perf_counter() - t0
        if j["status"] == "error":
            results.append({"ok": False, "stage": "job", "err": j["error"],
                            "submit": submit, "total": total})
            return
        marks = j["result"]["totals"]["marks"]
        good = (expect is None or abs(marks - expect) < 0.01)
        results.append({"ok": good, "marks": marks, "submit": submit,
                        "total": total, "cached": j["result"]["flags"]["cached"]})
    except Exception as exc:                                 # noqa: BLE001
        results.append({"ok": False, "stage": "exception", "err": str(exc),
                        "submit": 0, "total": time.perf_counter() - t0})


def pct(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    vals = sorted(vals)
    k = max(0, min(len(vals) - 1, int(round(p / 100 * (len(vals) - 1)))))
    return vals[k]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8100")
    ap.add_argument("--users", type=int, default=1000)
    ap.add_argument("--sheet-base", default="http://127.0.0.1:9100",
                    help="where the response sheets live (mock or cbexams)")
    ap.add_argument("--distinct", type=int, default=20,
                    help="how many different sheet links are in circulation")
    ap.add_argument("--poll", type=float, default=0.2)
    ap.add_argument("--expect", type=float, default=59.5,
                    help="expected total marks; -1 disables the check")
    ap.add_argument("--ramp", type=float, default=0.0,
                    help="seconds spread over which users arrive")
    a = ap.parse_args()

    limits = httpx.Limits(max_connections=a.users + 50,
                          max_keepalive_connections=a.users)
    timeout = httpx.Timeout(connect=10, read=60, write=10, pool=60)
    results: list[dict] = []
    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        t0 = time.perf_counter()
        tasks = []
        for i in range(a.users):
            tasks.append(asyncio.create_task(
                one_user(client, a.base, a.sheet_base, i, a.distinct,
                         None if a.expect < 0 else a.expect, a.poll, results)))
            if a.ramp:
                await asyncio.sleep(a.ramp / max(1, a.users))
        await asyncio.gather(*tasks)
        wall = time.perf_counter() - t0

    ok = [r for r in results if r["ok"]]
    bad = [r for r in results if not r["ok"]]
    totals = [r["total"] for r in ok]
    submits = [r["submit"] for r in ok]
    cached = sum(1 for r in ok if r.get("cached"))

    print(f"users          : {a.users}   (distinct links: {a.distinct})")
    print(f"wall clock     : {wall:.2f}s   → {a.users / wall:.1f} users/s")
    print(f"success        : {len(ok)}/{a.users}"
          + (f"   failures: {len(bad)}" if bad else ""))
    if totals:
        print(f"end-to-end     : p50 {pct(totals,50):.2f}s   "
              f"p95 {pct(totals,95):.2f}s   p99 {pct(totals,99):.2f}s   "
              f"max {max(totals):.2f}s   mean {statistics.mean(totals):.2f}s")
        print(f"submit ack     : p50 {pct(submits,50)*1000:.0f}ms   "
              f"p95 {pct(submits,95)*1000:.0f}ms")
        print(f"served from cache: {cached}/{len(ok)}")
    if bad:
        print("first failures :")
        for r in bad[:5]:
            print("  ", {k: v for k, v in r.items() if k != 'submit'})


if __name__ == "__main__":
    asyncio.run(main())
