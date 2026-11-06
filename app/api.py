"""FastAPI service: link in, score card out.

Concurrency model
-----------------
Everything is async I/O, so one process holds thousands of waiting requests
without breaking a sweat. Two gates protect the upstream site:

    OUTBOUND_CONCURRENCY  - max simultaneous requests to cbexams (default 64)
    SHEET_CONCURRENCY     - max sheets being crawled at once (default 200)

Anyone above the line waits in "queued" and the UI says so. That is the whole
trick behind "1000 log ek saath, lag na kare": nobody blocks a thread, and the
slow part (SSC's server) is rate-shaped instead of flattened.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import fetcher as F
from . import scoring as S
from .cache import TTLCache, key_for
from .jobs import JobStore
from .ui import PAGE

SHEET_CONCURRENCY = int(os.getenv("SHEET_CONCURRENCY", "200"))
RATE_PER_MIN = int(os.getenv("RATE_PER_MIN", "30"))
MAX_ACTIVE_PER_IP = int(os.getenv("MAX_ACTIVE_PER_IP", "4"))

state: dict = {}
_hits: dict[str, deque] = defaultdict(deque)


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["client"] = F.new_client()
    state["cache"] = TTLCache()
    state["jobs"] = JobStore()
    state["sheets"] = asyncio.Semaphore(SHEET_CONCURRENCY)
    F.semaphore()                      # bind the outbound gate to this loop
    state["inflight"] = 0
    state["served"] = 0
    try:
        yield
    finally:
        await state["client"].aclose()


app = FastAPI(title="SSC Marks Analyser", docs_url="/api/docs",
              openapi_url="/api/openapi.json", lifespan=lifespan)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "-"


def rate_ok(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_PER_MIN:
        return False
    q.append(now)
    if len(_hits) > 50000:                    # keep the map from growing forever
        for k in list(_hits)[:10000]:
            if not _hits[k]:
                _hits.pop(k, None)
    return True


def score_payload(sections: list[dict], pc, pw, url: str, meta: dict,
                  cached: bool) -> dict:
    summary = S.summarize(sections, pc, pw)
    counted = [(S.counts(s)[0], S.counts(s)[1]) for s in sections]
    alts = []
    for code, (label, apc, apw) in S.PRESETS.items():
        if (apc, apw) == (pc, pw):
            continue
        marks = sum(float(S.section_score(c, w, apc, apw)) for c, w in counted)
        alts.append({"code": code, "label": label,
                     "per_correct": float(apc), "per_wrong": float(apw),
                     "marks": round(marks, 2)})
    alts.sort(key=lambda a: -a["marks"])
    flags = {
        "answer_key_visible": any(c or w for c, w in counted),
        "cached": cached,
    }
    notes = []
    if not flags["answer_key_visible"]:
        notes.append("Is sheet pe answer key nahi dikh rahi - saare questions "
                     "unattempted lag rahe hain. Key release hone ke baad "
                     "dobara chalao.")
    if summary["totals"]["unknown"]:
        notes.append(f"{summary['totals']['unknown']} question(s) pe koi colour "
                     f"marker nahi mila.")
    return {
        **summary,
        "alternates": alts,
        "flags": flags,
        "notes": notes,
        "meta": {**meta, "url": url, "scored_at": int(time.time())},
    }


async def run_sheet(job, url: str, pc, pw) -> None:
    """Crawl one sheet, cache it, score it. Never raises."""
    job.status = "running"
    job.started = time.time()
    cache: TTLCache = state["cache"]
    key = key_for(url)
    try:
        cached = cache.get(key)
        if cached:
            job.step("cache", "pehle se calculate hai, seedha result")
            job.result = score_payload(cached["sections"], pc, pw, url,
                                       {**cached["meta"], "elapsed_ms": 0}, True)
            job.status = "done"
            return

        async def on_step(name: str, detail: str = ""):
            job.step(name, detail)

        async with state["sheets"]:
            raw = await F.crawl(url, on_step=on_step, client=state["client"])

        cache.set(key, {"sections": raw["sections"], "meta": raw["meta"]})
        job.result = score_payload(raw["sections"], pc, pw, url, raw["meta"], False)
        job.status = "done"
        state["served"] += 1
    except F.SheetError as exc:
        job.status = "error"
        job.error = {"code": exc.code, "message": exc.message, "hint": exc.hint}
    except Exception as exc:                                # noqa: BLE001
        job.status = "error"
        job.error = {"code": "crash", "message": f"{type(exc).__name__}: {exc}",
                     "hint": "ek baar dobara try karo."}
    finally:
        if job.status != "done" and job.error:
            job.step("failed", job.error.get("code", "error"))
        job.finish()


@app.post("/api/analyze")
async def analyze(request: Request):
    try:
        body = await request.json()
    except Exception:                                        # noqa: BLE001
        return JSONResponse({"error": "bad json"}, status_code=400)

    url = (body.get("url") or "").strip()
    ip = client_ip(request)
    if not rate_ok(ip):
        return JSONResponse({"error": "Bahut zyada requests. 1 minute ruk ke "
                                      "try karo."}, status_code=429)

    try:
        scheme = body.get("scheme")
        label, pc, pw = S.resolve(body.get("correct"), body.get("wrong"), scheme)
    except Exception:                                        # noqa: BLE001
        label, pc, pw = S.resolve()

    try:
        url = F.check_url(url)
    except F.SheetError as exc:
        return JSONResponse({"error": exc.message, "hint": exc.hint},
                            status_code=400)

    jobs: JobStore = state["jobs"]
    if jobs.active_for(ip) > MAX_ACTIVE_PER_IP:
        return JSONResponse({"error": "Aapke 4 sheets already chal rahe hain, "
                                      "thoda intezaar karo."}, status_code=429)

    job = jobs.create(url, ip)
    job.step("start", "job ban gaya")
    asyncio.create_task(run_sheet(job, url, pc, pw))
    return {"job_id": job.id, "scheme": label,
            "per_correct": float(pc), "per_wrong": float(pw)}


@app.get("/api/job/{job_id}")
async def job_status(job_id: str, wait: int = 0, timeout: float = 20.0):
    """wait=1 long-polls: reply the moment the job ends, or after `timeout`.

    This is what keeps 1000 users cheap - one held connection each instead of
    a poll every few hundred milliseconds.
    """
    job = state["jobs"].get(job_id)
    if not job:
        return JSONResponse({"error": "job nahi mila"}, status_code=404)
    if wait and job.status in ("queued", "running"):
        try:
            await asyncio.wait_for(job.done_event.wait(), timeout=min(timeout, 30))
        except asyncio.TimeoutError:
            pass
    return job.to_dict()


@app.get("/api/schemes")
async def schemes():
    return {"default": S.DEFAULT_SCHEME,
            "presets": [{"code": c, "label": l, "per_correct": float(a),
                         "per_wrong": float(b)}
                        for c, (l, a, b) in S.PRESETS.items()]}


@app.get("/api/healthz")
async def healthz():
    return {
        "ok": True,
        "cache": state["cache"].stats(),
        "jobs": state["jobs"].stats(),
        "inflight": state["inflight"],
        "served": state["served"],
        "outbound_concurrency": F.OUTBOUND_CONCURRENCY,
        "sheet_concurrency": SHEET_CONCURRENCY,
    }


@app.get("/", response_class=HTMLResponse)
async def index():
    return PAGE
