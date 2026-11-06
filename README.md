# SSC Marks Analyser — "link daalo, marks lo"

A deployable service: paste a candidate-response-sheet link, get section-wise +
total marks, correct / wrong / skipped per section, accuracy, wrong question
numbers, and the same answers scored under every SSC marking scheme.

Designed to sit in front of a burst of 500–1000 people at once without falling
over or hammering SSC's server.

```
sscexams.cbexams.com/.../ViewCandResponse.aspx?enckey=XXXX
        ↓
   PART-A  15C   5W   5S   27.50 / 50
   PART-B   8C   8W   9S   12.00 / 50
   PART-C   4C   5W  16S    5.50 / 50
   PART-D  10C  11W   4S   14.50 / 50
   ─────────────────────────────────
   TOTAL   37C  29W  34S   59.50 / 200     (+2 correct, -0.5 wrong)
   accuracy 56.1%   ·   29.8% of max
```

Verified against a live CGL-2026 sheet: 4 sections, 100 questions, every count
matching the colours on the page.

---

## Deploy in one click

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/rohitkumar2711/Somsi)
[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/rohitkumar2711/Somsi)

The buttons point at `rohitkumar2711`. Either edit that in this file, or run

```bash
./publish.sh your-github-username
```

which rewrites every link, creates the repo and pushes it. Then the two buttons
above are live on your own repo page.

What each platform picks up:

| platform | file it reads | notes |
|----------|---------------|-------|
| Render | `render.yaml` | free plan, health check `/api/healthz`. Free instance sleeps after 15 min idle, first hit after that wakes it in ~50 s |
| Heroku | `app.json` + `Procfile` | no free tier any more - `eco` dyno is ~$5/mo |
| Docker / VPS | `Dockerfile`, `docker-compose.yml`, `deploy/nginx.conf` | `docker compose up -d --build` |
| anything else | `requirements.txt` | start with `uvicorn app.api:app --host 0.0.0.0 --port $PORT` |

One instance handles a whole shift's traffic: the only thing all those visitors
share is the sheet, and the cache serves it in ~0.02 s after the first crawl.

## How it reads the sheet

The page shows **one PART at a time**, and every question and option is an
**image** — nothing is readable as text. The only machine-readable signal is the
fill colour the page paints on the option cells:

| colour | page legend | scored as |
|--------|-------------|-----------|
| green  | correct option selected | full marks |
| red    | wrong option selected | negative penalty |
| gray   | not answered | 0 |
| yellow | the correct option (drawn on questions you did not get right) | — |

Two things about the ASP.NET machinery, both verified against the live site:

- the hidden `__VIEWSTATE` / `__EVENTVALIDATION` fields are **required** — post
  without them and the button press is ignored, you get PART-A back;
- the session cookie is **not** required, and postbacks fired in parallel from
  the same page state each return their own correct PART.

So a sheet costs **1 GET + 3 parallel POSTs = 4 requests**, not a chain of hops.
Then each response is parsed into counts, and the counts are scored.

Section names come from the page itself (`lblsubject`), so a Tier-2 layout with
Section-I / Module-I works without code changes.

---

## Why 500–1000 users don't feel lag

Five separate mechanisms:

1. **Two requests per user.** `POST /api/analyze` returns a job id instantly;
   `GET /api/job/{id}?wait=1` long-polls and answers the *moment* the job ends.
   No 700 ms polling loops — 1000 waiting users are 1000 sleeping coroutines,
   not 1400 requests/second.
2. **Live progress.** The crawler reports each step (`PART-B ready`), so a slow
   sheet shows movement instead of a dead spinner.
3. **Cache by `enckey`.** A link forwarded around a group is crawled once.
   Later visitors get the scoreboard in ~0 ms. TTL 30 min, LRU 5000 entries.
4. **Bounded upstream.** One process-wide semaphore (default 64) gates requests
   to cbexams, and a second (default 200) caps sheets in flight. Users above the
   line are *queued*, never dropped — SSC sees a steady stream, not a DDoS.
5. **Nothing blocks.** Everything is async I/O; no thread pool, no `requests`.
   `uvicorn` + `httpx` + `asyncio` only.

Rate limits are per IP (30/min, 4 active jobs) so one person cannot eat the box.

---

## Speed, measured

| step | cost |
|------|------|
| 4 pages parsed | **~16 ms** |
| scoring + JSON | < 1 ms |
| 1 GET + 3 parallel POSTs to SSC | **whatever SSC feels like** (0.7 s → 11 s per request, by the hour) |
| second visitor of the same link | **~0.02 s** (cache, zero network) |

HTTP/2 is on by default: on a cold connect it took the first page fetch from
6.5 s to 2.0 s in testing. After that the wall clock is SSC's server, not this
app. Every link form of the same sheet (`ViewCandResponse.aspx?enckey=` and
`ViewCandResponse4.aspx?EncKey=`) hits the same cache entry.

## Benchmarks (honest version)

Two different things get measured, because they have different bottlenecks.

**App-side capacity** — `bench_inproc.py` drives the real ASGI app in-process
(no TCP) with a stand-in upstream that sleeps like SSC:

```
$ python3 bench_inproc.py --users 1000 --distinct 20 --upstream-ms 350
users           : 1000  (distinct links 20, upstream 350ms per request)
wall clock      : 8.9s   -> 112 users/s, 6700 users/min
correct results : 1000/1000
end-to-end      : p50 1.4s  p95 2.6s  p99 3.1s
```

```
$ python3 bench_inproc.py --users 1000 --distinct 1000 --upstream-ms 350
users 1000, 1000 distinct links (worst case, no cache reuse)
correct results : 1000/1000
```

**Full chain over TCP** — `loadtest.py` spawns 1000 virtual users with their own
`X-Forwarded-For`, mixed shared/unique links, and checks every result equals
59.50.

> Caveat you should know: the box this was developed on is a proot sandbox on a
> phone. **A hello-world FastAPI endpoint there tops out at ~30 req/s**, so
> absolute socket timings from it say nothing about a real VPS; they measure the
> sandbox, not the app. That is exactly why the in-process benchmark exists.
> On a normal 1–2 vCPU VPS, uvicorn does hundreds of these requests per second
> and the only real ceiling left is SSC's own latency.

Sizing rule of thumb: parsing a page costs ~5 ms here, ~1–2 ms on a normal
CPU → a sheet (4 pages) is ~20 ms of CPU here, ~6 ms there. One worker saturates
around **40–60 sheets/s here**, **150–250/s on a real vCPU**. Scale with
`WEB_CONCURRENCY` + `ip_hash` (see below).

---

## Run it

### Docker (recommended)

```bash
docker compose up -d --build          # app + nginx on :80
curl -s localhost/api/healthz | jq
```

### Bare metal / VPS

```bash
./run.sh                              # venv + uvicorn on :8000
PORT=9000 WEB_CONCURRENCY=2 ./run.sh
```

### Managed hosts (Render / Railway / Fly / Koyeb)

Build from the Dockerfile, health check `/api/healthz`, one instance is enough
to start. No database, no disk, no cron.

### Local dev with fake upstream

```bash
uvicorn mock.ssc_mock:app --port 9100 &
ALLOWED_HOSTS="cbexams.com,127.0.0.1:9100" uvicorn app.api:app --port 8000
python3 loadtest.py --base http://127.0.0.1:8000 --users 500 --distinct 20
```

---

## API

| method | path | notes |
|--------|------|-------|
| `GET` | `/` | the page (link box, live progress, scoreboard) |
| `POST` | `/api/analyze` | `{"url": "...", "scheme": "ssc-1/3"}` or `{"correct": 2, "wrong": "1/3"}` → `{job_id}` |
| `GET` | `/api/job/{id}` | current steps + result; add `?wait=1&timeout=25` to long-poll |
| `GET` | `/api/schemes` | available marking schemes |
| `GET` | `/api/healthz` | cache + job stats, in-flight counters |
| `GET` | `/api/docs` | OpenAPI UI |

Schemes: `cgl-t1` (**default**, +2 / −1/2), `ssc-1/3` (+2 / −1/3), `cgl-t2`
(+3 / −1), `chsl-t1`, `mts`, or any custom pair. The server returns counts only;
**the browser does the arithmetic**, so switching schemes re-scores instantly.

---

## Config

| env | default | meaning |
|-----|---------|---------|
| `OUTBOUND_CONCURRENCY` | `64` | max simultaneous requests to cbexams |
| `SHEET_CONCURRENCY` | `200` | max sheets being crawled at once |
| `CACHE_TTL` / `CACHE_SIZE` | `1800` / `5000` | result cache |
| `RATE_PER_MIN` | `30` | per-IP requests per minute |
| `MAX_ACTIVE_PER_IP` | `4` | per-IP concurrent sheets |
| `HTTP2` | `1` | talk HTTP/2 to cbexams (measured 6.5s → 2.0s on a cold connect) |
| `ALLOWED_HOSTS` | `cbexams.com` | SSRF guard: only these hosts are fetchable |
| `WEB_CONCURRENCY` | `1` | uvicorn workers (needs `ip_hash` if > 1) |
| `TG_TOKEN` | — | enables the Telegram front-end |

Jobs live in memory, so a job must be read back from the worker that created it.
With `WEB_CONCURRENCY > 1` put nginx in front with `ip_hash` (included in
`deploy/nginx.conf`) and every user stays pinned to their worker. Cache hit rate
rises with traffic, so a second worker mostly buys headroom, not correctness.

---

## Telegram bot

```bash
TG_TOKEN=123456:ABC... python3 -m app.tg        # plain card + buttons, no extra deps
```

What a user sees:

- `/start` -> formatted welcome (headings, bullets, marking scheme) + buttons
  `[How to use] [Marking schemes]` and `[Open web version]` when `PUBLIC_URL` is set
- paste a link -> placeholder message turns into the result card, with buttons
  `[+2 / −0.5] [+2 / −1/3]`, `[Recalculate] [Other schemes]`, `[Open web version]`
- pressing a scheme button re-renders the same card instantly (counts are cached,
  no crawl), `[Other schemes]` shows the full comparison, stale buttons answer
  politely instead of breaking

Every button is a callback query, handled in-process; `SESSIONS` maps a short id
to the sheet url so `callback_data` stays under Telegram's 64-byte limit.

## Premium Telegram card (optional)

The web page needs no UI library - it is plain CSS/JS. The *Telegram* card can
look like a printed result sheet using [richpyro](https://pypi.org/project/richpyro/),
which wraps Telegram's Bot API 10.1 rich blocks (headings, striped tables,
dividers, buttons):

```bash
pip install -r requirements-rich.txt     # richpyro + Kurigram
export TG_TOKEN=...          # bot token from @BotFather
export TG_API_ID=...         # my.telegram.org
export TG_API_HASH=...
python3 -m app.tg            # rich cards; without the api pair it falls back to HTML
```

`app/tg_rich.py` builds the card (heading, score, table, wrong question numbers,
alternate schemes, footer button); `app/tg.py` picks the rich path only when
richpyro **and** the api credentials are present, so the plain deploy stays
dependency-light.

## Failure modes it handles

| situation | what the user sees |
|-----------|--------------------|
| expired `enckey` / window closed | "is link pe koi question nahi mila" + hint to re-open the sheet |
| answer key not released yet | explicit warning, counts shown as unattempted instead of a fake score |
| SSC slow / 5xx | two retries with backoff, then "server jawab nahi de raha" |
| too many requests from one IP | 429 with a plain-language message |
| link from another site | rejected before any request leaves the box (SSRF guard) |
| sheet with unknown layout | falls back to raw counts, never guesses marks |

---

## Files

```
app/parser.py    colours -> counts (pure, unit-tested)
app/fetcher.py   async crawl: 1 GET + parallel postbacks, retries, semaphores
app/scoring.py   schemes, per-section and total marks
app/cache.py     TTL + LRU
app/jobs.py      job state + long-poll event
app/api.py       FastAPI routes
app/ui.py        the page (no build step, no CDN)
app/tg.py        Telegram bot
tests/           9 unit tests on saved real pages
mock/            fake cbexams for load testing
bench_inproc.py  capacity benchmark (app only)
loadtest.py      1000 virtual users over TCP
Dockerfile · docker-compose.yml · deploy/nginx.conf · run.sh
```

Tests: `python3 tests/test_parser.py`
