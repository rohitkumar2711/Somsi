"""Async crawler for SSC candidate response sheets.

Why it is written this way
--------------------------
The sheet is one ASP.NET page that only ever renders *one* PART at a time. The
other parts sit behind postback buttons (P1..P4). Two facts we verified against
the live site:

  * the hidden __VIEWSTATE / __EVENTVALIDATION fields are required - without
    them the button press is ignored and you get PART-A back;
  * the session cookie is *not* required, and parallel postbacks fired from the
    same page state each return their own correct PART.

So: one GET, then P2/P3/P4 fired concurrently from that same state. A sheet is
4 round trips deep, not 4 round trips long. Everything outbound is gated by a
global semaphore so a burst of users cannot turn into a burst of 4000 requests
against cbexams.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
import urllib.parse

import httpx

from . import parser as P

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

OUTBOUND_CONCURRENCY = int(os.getenv("OUTBOUND_CONCURRENCY", "64"))
TIMEOUT = httpx.Timeout(connect=8.0, read=30.0, write=10.0, pool=10.0)
ALLOWED_HOSTS = [
    h.strip().lower()
    for h in os.getenv("ALLOWED_HOSTS", "cbexams.com").split(",")
    if h.strip()
]
MAX_PARTS = int(os.getenv("MAX_PARTS", "8"))
HTTP2 = os.getenv("HTTP2", "1") not in ("0", "false", "False")
try:                                    # http/2 needs the h2 package
    import h2  # noqa: F401
except ImportError:                     # pragma: no cover
    HTTP2 = False

_sem: asyncio.Semaphore | None = None


def semaphore() -> asyncio.Semaphore:
    """One process-wide gate for outbound requests."""
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(OUTBOUND_CONCURRENCY)
    return _sem


class SheetError(Exception):
    """A failure we can explain to the user."""

    def __init__(self, code: str, message: str, hint: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


def check_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise SheetError("bad_url", "link hi nahi mila.",
                         "response sheet ka poora link paste karo.")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise SheetError("bad_url", "ye link theek nahi lag raha.",
                         "https:// se shuru hone wala poora link do.")
    host = (parts.hostname or "").lower()
    netloc = parts.netloc.lower()
    if not any(host == h or host.endswith("." + h) or netloc == h
               for h in ALLOWED_HOSTS):
        raise SheetError(
            "bad_url", "ye SSC ka link nahi hai.",
            f"allowed: {', '.join(ALLOWED_HOSTS)}")
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, parts.query, ""))


def new_client() -> httpx.AsyncClient:
    """Connection-pooled client. Cookies are irrelevant for this site."""
    return httpx.AsyncClient(
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Upgrade-Insecure-Requests": "1",
        },
        timeout=TIMEOUT,
        follow_redirects=True,
        http2=HTTP2,
        limits=httpx.Limits(max_connections=256, max_keepalive_connections=64,
                            keepalive_expiry=45.0),
    )


async def _request(client: httpx.AsyncClient, method: str, url: str,
                   data: dict | None = None, retries: int = 2) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            async with semaphore():
                r = await client.request(method, url, data=data)
            if r.status_code >= 500:
                raise httpx.HTTPStatusError(f"upstream {r.status_code}",
                                            request=r.request, response=r)
            return r
        except (httpx.TimeoutException, httpx.TransportError,
                httpx.HTTPStatusError) as exc:
            last = exc
            if attempt < retries:
                await asyncio.sleep(0.6 * (2 ** attempt) + random.random() * 0.4)
    raise SheetError(
        "upstream",
        f"SSC ka server jawab nahi de raha ({type(last).__name__}).",
        "thodi der baad try karo, ya link dobara khol ke check karo.")


async def _post_part(client: httpx.AsyncClient, url: str, action: str,
                     hidden: dict, name: str, value: str) -> str:
    data = dict(hidden)
    data[name] = value
    target = urllib.parse.urljoin(url, action) if action else url
    r = await _request(client, "POST", target, data=data)
    return r.text


async def crawl(url: str, on_step=None, client: httpx.AsyncClient | None = None) -> dict:
    """Fetch every PART of one response sheet and classify every question.

    on_step: optional async callable(step:str, detail:str) for live progress.
    """
    url = check_url(url)
    started = time.perf_counter()
    own_client = client is None
    client = client or new_client()

    async def step(a: str, b: str = ""):
        if on_step:
            try:
                await on_step(a, b)
            except Exception:                                # noqa: BLE001
                pass

    try:
        await step("fetch", "link khol rahe hain")
        r = await _request(client, "GET", url)
        base = r.text
        first = P.parse_sheet(base)
        if not first["questions"]:
            raise SheetError(
                "expired",
                "is link pe koi question nahi mila.",
                "enckey purani ho gayi hogi ya exam window band hai. "
                "Browser me khol ke dekho - agar wahan bhi khaali hai to link "
                "dead hai.")

        collected: dict[str, dict] = {}
        if first["code"]:
            collected[first["code"]] = first
        await step("part", f"{first['code'] or 'PART'} ready "
                           f"({len(first['questions'])} questions)")

        hidden = P.hidden_fields(base)
        action = P.form_action(base)
        buttons = [
            (n, v, P.button_part(v))
            for n, v in P.submit_buttons(base).items()
            if n.upper().startswith("P") and n[1:].isdigit()
        ]
        pending = [(n, v, c) for n, v, c in buttons
                   if (c or n) not in collected]

        # fire the remaining parts in parallel from the same page state
        if pending:
            await step("parts", f"{len(pending)} section(s) parallel me")
            tasks = [_post_part(client, url, action, hidden, n, v)
                     for n, v, _ in pending]
            pages = await asyncio.gather(*tasks, return_exceptions=True)
            for (n, v, code), page in zip(pending, pages):
                if isinstance(page, Exception):
                    continue
                sheet = P.parse_sheet(page)
                key = sheet["code"] or code or n
                if not sheet["questions"] or key in collected:
                    continue
                collected[key] = sheet
                await step("part", f"{key} ready ({len(sheet['questions'])} questions)")

        # anything still missing: walk it sequentially from the base page
        missing = [(n, v) for n, v, c in buttons if (c or n) not in collected]
        for n, v in missing[:MAX_PARTS]:
            try:
                page = await _post_part(client, url, action, hidden, n, v)
            except SheetError:
                continue
            sheet = P.parse_sheet(page)
            key = sheet["code"] or n
            if sheet["questions"] and key not in collected:
                collected[key] = sheet
                await step("part", f"{key} ready ({len(sheet['questions'])} questions)")

        if not collected:
            raise SheetError("no_questions", "koi bhi section parse nahi hua.",
                             "link dobara check karo.")

        sections = sorted(collected.values(), key=lambda s: s["code"] or "Z")
        elapsed = time.perf_counter() - started
        await step("done", f"{len(sections)} sections, {elapsed:.1f}s")
        return {
            "sections": sections,
            "meta": {
                "elapsed_ms": int(elapsed * 1000),
                "requests": 1 + len(buttons),
                "sections": len(sections),
                "source_label": first.get("label", ""),
            },
        }
    finally:
        if own_client:
            await client.aclose()
