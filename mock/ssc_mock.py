"""Local stand-in for the cbexams response sheet.

Used by loadtest.py so we can measure the app at 1000 concurrent users without
hammering SSC's server. It reproduces the parts that matter:

  * GET  -> PART-A page (with __VIEWSTATE, P1..P4 buttons)
  * POST Pn -> that PART's page
  * configurable per-request latency, so timings stay honest

    uvicorn mock.ssc_mock:app --port 9100
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import re

import urllib.parse

from fastapi import FastAPI, Request, Response

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = HERE.parent / "tests" / "fixtures"
LATENCY = float(os.getenv("MOCK_LATENCY_MS", "350")) / 1000

PAGES = {}
for letter in "abcd":
    f = FIXTURES / f"part{letter.upper()}.html"
    if f.exists():
        PAGES[f"P{ord(letter) - 96}"] = f.read_text(encoding="utf-8", errors="replace")

app = FastAPI()


@app.get("/{exam:path}/ViewCandResponse.aspx")
async def sheet(exam: str, enckey: str = ""):
    await asyncio.sleep(LATENCY)
    html = PAGES.get("P1", "")
    return Response(html, media_type="text/html; charset=utf-8")


@app.post("/{exam:path}/ViewCandResponse.aspx")
async def postback(exam: str, request: Request):
    await asyncio.sleep(LATENCY)
    body = (await request.body()).decode("utf-8", "replace")
    form = {k: v[0] for k, v in urllib.parse.parse_qs(body).items()}
    for name in ("P1", "P2", "P3", "P4"):
        if form.get(name):
            return Response(PAGES.get(name, ""), media_type="text/html; charset=utf-8")
    return Response(PAGES.get("P1", ""), media_type="text/html; charset=utf-8")


@app.get("/healthz")
async def healthz():
    return {"ok": True, "parts": sorted(PAGES), "latency_ms": LATENCY * 1000}
