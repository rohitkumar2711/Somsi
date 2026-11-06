#!/usr/bin/env python3
"""Capacity benchmark that does not depend on the network stack.

The app is driven in-process through the ASGI interface (no TCP), while the
"upstream" is a stand-in that sleeps like SSC's server does and returns the real
saved pages. That isolates what we control: routing, jobs, cache, parsing,
scoring.

    python3 bench_inproc.py --users 1000 --upstream-ms 350 --distinct 1000

Why this exists: on the dev sandbox the OS socket layer itself caps out around
25-30 req/s (proot on a phone), which hides the app behind an infrastructure
limit. This measures the app; loadtest.py measures the whole chain over TCP.
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import statistics
import time

import httpx

from app import fetcher as F
from app import parser as P
from app.api import app

FIXTURES = pathlib.Path(__file__).parent / "tests" / "fixtures"
PAGES = {k: (FIXTURES / f"part{k}.html").read_text(encoding="utf-8", errors="replace")
         for k in "ABCD"}


def make_fake_crawl(upstream_ms: float):
    async def crawl(url: str, on_step=None, client=None):
        if on_step:
            await on_step("fetch", "simulated")
        await asyncio.sleep(upstream_ms / 1000)
        sections = []
        for key in "ABCD":
            await asyncio.sleep(upstream_ms / 1000 / 4)
            sections.append(P.parse_sheet(PAGES[key]))
        return {"sections": sections,
                "meta": {"elapsed_ms": upstream_ms, "requests": 4,
                         "sections": 4, "source_label": ""}}
    return crawl


def pct(vals, p):
    if not vals:
        return 0.0
    vals = sorted(vals)
    k = max(0, min(len(vals) - 1, int(round(p / 100 * (len(vals) - 1)))))
    return vals[k]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=1000)
    ap.add_argument("--distinct", type=int, default=1000)
    ap.add_argument("--upstream-ms", type=float, default=350)
    a = ap.parse_args()

    F.crawl = make_fake_crawl(a.upstream_ms)          # swap the network out

    transport = httpx.ASGITransport(app=app)
    results: list[tuple[bool, float]] = []
    latencies: list[float] = []

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://app",
                                     timeout=httpx.Timeout(120)) as c:
            async def user(i: int):
                url = ("http://cbexams.com/CGLE2026/ViewCandResponse.aspx"
                       f"?enckey=bench{i % a.distinct:05d}")
                t0 = time.perf_counter()
                try:
                    r = await c.post("/api/analyze", json={"url": url},
                                     headers={"X-Forwarded-For":
                                              f"10.{i // 65536 % 250}.{i // 256 % 256}.{i % 256}"})
                    if r.status_code != 200:
                        results.append((False, time.perf_counter() - t0))
                        return
                    job = r.json()["job_id"]
                    while True:                      # long-poll until it ends
                        j = (await c.get(f"/api/job/{job}?wait=1&timeout=25")).json()
                        if j["status"] in ("done", "error"):
                            break
                    dt = time.perf_counter() - t0
                    ok = (j["status"] == "done"
                          and abs(j["result"]["totals"]["marks"] - 59.5) < 0.01)
                    results.append((ok, dt))
                    if ok:
                        latencies.append(dt)
                except Exception:                            # noqa: BLE001
                    results.append((False, time.perf_counter() - t0))

            t0 = time.perf_counter()
            await asyncio.gather(*[user(i) for i in range(a.users)])
            wall = time.perf_counter() - t0

    ok = sum(1 for good, _ in results if good)
    print(f"users           : {a.users}  (distinct links {a.distinct}, "
          f"upstream {a.upstream_ms:.0f}ms per request)")
    print(f"wall clock      : {wall:.2f}s  -> {a.users / wall:.0f} users/s, "
          f"{a.users / wall * 60:.0f} users/min")
    print(f"correct results : {ok}/{a.users}")
    print(f"end-to-end      : p50 {pct(latencies,50):.2f}s  "
          f"p95 {pct(latencies,95):.2f}s  p99 {pct(latencies,99):.2f}s  "
          f"max {max(latencies or [0]):.2f}s  mean "
          f"{statistics.mean(latencies or [0]):.2f}s")


if __name__ == "__main__":
    asyncio.run(main())
