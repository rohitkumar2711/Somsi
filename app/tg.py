"""Telegram front-end.

Two presentation modes, one analyser:

  plain  - Bot API long polling + HTML text card + inline keyboard buttons.
           No extra dependency, works with just TG_TOKEN.
  rich   - if TG_API_ID/TG_API_HASH are set and richpyro is installed, the card
           is a Telegram rich message: heading, striped table, dividers,
           buttons (see app/tg_rich.py).

Both look like a proper result sheet rather than a wall of text.
"""

from __future__ import annotations

import asyncio
import html
import os
import sys
import uuid

import httpx

from . import fetcher as F
from . import scoring as S
from .cache import TTLCache, key_for

TOKEN = os.getenv("TG_TOKEN", "").strip()
TG_API_ID = os.getenv("TG_API_ID", "").strip()
TG_API_HASH = os.getenv("TG_API_HASH", "").strip()
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")

API = f"https://api.telegram.org/bot{TOKEN}"
POLL_TIMEOUT = 30
MAX_TEXT = 3800

cache = TTLCache(maxsize=int(os.getenv("CACHE_SIZE", "5000")))
SESSIONS: dict[str, str] = {}          # short id -> sheet url (for button callbacks)

# ── text ─────────────────────────────────────────────────────────────────────

WELCOME = (
    "<b>SSC Marks Analyser</b>\n"
    "<i>response sheet → section-wise marks</i>\n"
    "\n"
    "<b>Kaise chalega</b>\n"
    "1.  Response sheet ka link copy karo\n"
    "2.  Yahan paste karo\n"
    "3.  Section-wise + total marks, turant\n"
    "\n"
    "<b>Kya milega</b>\n"
    "•  section-wise sahi / galat / chhode\n"
    "•  total marks, accuracy, percentage\n"
    "•  galat question numbers\n"
    "•  doosri marking scheme ka comparison\n"
    "\n"
    "<b>Marking</b>   +2 sahi  ·  −0.5 galat\n"
    "\n"
    "<i>Link aisa dikhta hai:</i>\n"
    "<code>…/ViewCandResponse.aspx?enckey=XXXX</code>"
)

COMMANDS = "/start  /scheme  /help"


W = 34                                   # inner width that fits a phone in Telegram


def bar(frac: float, width: int = 18) -> str:
    frac = max(0.0, min(1.0, frac))
    filled = round(frac * width)
    return "[" + "#" * filled + "." * (width - filled) + "]"


def _esc(text) -> str:
    return html.escape(str(text), quote=False)


def _box(lines: list[str], width: int = W) -> list[str]:
    out = ["╭" + "─" * width + "╮"]
    for line in lines:
        cut = line[:width]
        out.append("│" + cut + " " * (width - len(cut)) + "│")
    out.append("╰" + "─" * width + "╯")
    return out


SHORT = {
    "General Intelligence and Reasoning": "Reasoning",
    "General Awareness": "GA",
    "Quantitative Aptitude": "Quant",
    "English Comprehension": "English",
}


def _short(name: str) -> str:
    for full, short in SHORT.items():
        if name.startswith(full[:12]):
            return short
    return name[:12]


def _table(result: dict) -> list[str]:
    t = result["totals"]
    rows = [f"{'SEC':<12}{'C':>4}{'W':>4}{'S':>4} {'MARKS':>9}", "─" * W]
    for s in result["sections"]:
        mark = f"{s['marks']:.2f}/{s['max']:g}"
        rows.append(f"{_short(s['name']):<12}{s['correct']:>4}{s['wrong']:>4}"
                    f"{s['skipped']:>4} {mark:>9}")
    rows.append("═" * W)
    mark = f"{t['marks']:.2f}/{t['max']:g}"
    rows.append(f"{'TOTAL':<12}{t['correct']:>4}{t['wrong']:>4}"
                f"{t['skipped']:>4} {mark:>9}")
    return _box(rows)


def _score_box(result: dict) -> list[str]:
    t = result["totals"]
    lines = [
        f"SCORE   {t['marks']:.2f} / {t['max']:g}",
        f"PERCENT {t['percentage']:.1f}%    ACCURACY {t['accuracy']:.1f}%",
        bar(t["percentage"] / 100),
    ]
    return _box(lines)


def _wrong_box(result: dict) -> list[str]:
    rows: list[str] = []
    for s in result["sections"]:
        qs = s.get("questions_wrong") or []
        if not qs:
            continue
        tag = s["code"].replace("PART-", "")
        line = tag + "  "
        for q in qs:
            piece = str(q)
            candidate = line + piece + ", "
            if len(candidate.rstrip(", ")) > W:
                rows.append(line.rstrip(", "))
                line = "   " + piece + ", "
            else:
                line = candidate
        if line.strip():
            rows.append(line.rstrip(", "))
    if not rows:
        return []
    return _box(["GALAT Q.NO."] + rows)


def welcome_markup() -> dict:
    rows = []
    if PUBLIC_URL:
        rows.append([{"text": "Open web version", "url": PUBLIC_URL}])
    rows.append([{"text": "How to use", "callback_data": "help"},
                 {"text": "Marking schemes", "callback_data": "schemes"}])
    return {"inline_keyboard": rows}


def result_markup(result: dict, sid: str) -> dict:
    rows = [[{"text": "+2 / −0.5", "callback_data": f"sch:cgl-t1:{sid}"},
             {"text": "+2 / −1/3", "callback_data": f"sch:ssc-1/3:{sid}"}],
            [{"text": "Recalculate", "callback_data": f"ref:{sid}"},
             {"text": "All schemes", "callback_data": f"alt:{sid}"}]]
    if PUBLIC_URL:
        rows.append([{"text": "Open web version", "url": PUBLIC_URL}])
    return {"inline_keyboard": rows}


def card(result: dict, scheme_label: str) -> str:
    """Full boxed result sheet - monospace frame inside <pre>."""
    lines = ["SSC MARKS ANALYSER", scheme_label]
    lines += _table(result)
    lines += _score_box(result)
    wrong = _wrong_box(result)
    if wrong:
        lines += wrong
    for note in result.get("notes", []):
        lines += _box([note])
    body = "\n".join(_esc(line) for line in lines)
    out = f"<pre>{body}</pre>"
    if result.get("alternates"):
        alt = " · ".join(f"{a['label'].split(' (')[0]} {a['marks']:g}"
                         for a in result["alternates"][:3])
        out += f"\n<i>{_esc(alt)}</i>"
    return out[:MAX_TEXT]


def alt_text(result: dict) -> str:
    rows = ["SAME ANSWERS, OTHER SCHEMES", "─" * W]
    for a in result.get("alternates", []):
        name = a["label"].split(" (")[0]
        rows.append(f"{name[:24]:<24}{a['marks']:>9.2f}")
    rows.append("─" * W)
    rows.append(f"{'current':<24}{result['totals']['marks']:>9.2f}")
    body = "\n".join(_esc(line) for line in _box(rows))
    return f"<pre>{body}</pre>"


# ── analyse ──────────────────────────────────────────────────────────────────

async def analyze(url: str, scheme: str | None = None):
    label, pc, pw = S.resolve(scheme=scheme)
    cached = cache.get(key_for(url))
    if cached:
        out = S.summarize(cached["sections"], pc, pw)
        return {**out, "alternates": _alternates(cached["sections"], pc, pw),
                "notes": _notes(cached["sections"]), "cached": True}, label

    raw = await F.crawl(url)
    cache.set(key_for(url), {"sections": raw["sections"], "meta": raw["meta"]})
    out = S.summarize(raw["sections"], pc, pw)
    return {**out, "alternates": _alternates(raw["sections"], pc, pw),
            "notes": _notes(raw["sections"]), "cached": False}, label


def _alternates(sections: list[dict], pc, pw) -> list[dict]:
    counted = [(S.counts(s)[0], S.counts(s)[1]) for s in sections]
    alts = []
    for code, (lbl, apc, apw) in S.PRESETS.items():
        if (apc, apw) == (pc, pw):
            continue
        marks = sum(float(S.section_score(c, w, apc, apw)) for c, w in counted)
        alts.append({"code": code, "label": lbl, "marks": round(marks, 2)})
    return sorted(alts, key=lambda a: -a["marks"])


def _notes(sections: list[dict]) -> list[str]:
    if not any(S.counts(s)[0] or S.counts(s)[1] for s in sections):
        return ["Is sheet pe answer key nahi dikh rahi — key release ke baad "
                "dobara bhejna."]
    return []


def session_token(url: str) -> str:
    for sid, known in SESSIONS.items():
        if known == url:
            return sid
    sid = uuid.uuid4().hex[:10]
    SESSIONS[sid] = url
    if len(SESSIONS) > 5000:
        for k in list(SESSIONS)[:1000]:
            SESSIONS.pop(k, None)
    return sid


# ── plain Bot API ────────────────────────────────────────────────────────────

async def call(client: httpx.AsyncClient, method: str, **payload):
    r = await client.post(f"{API}/{method}", json=payload, timeout=60)
    try:
        return r.json()
    except Exception:                                        # noqa: BLE001
        return {"ok": False, "description": r.text[:200]}


async def on_message(client: httpx.AsyncClient, msg: dict) -> None:
    chat = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    if not text:
        return

    if text.startswith("/start") or text.startswith("/help"):
        await call(client, "sendMessage", chat_id=chat, text=WELCOME,
                   parse_mode="HTML", reply_markup=welcome_markup(),
                   disable_web_page_preview=True)
        return
    if text.startswith("/scheme"):
        await call(client, "sendMessage", chat_id=chat,
                   text="available: " + ", ".join(S.PRESETS)
                        + f"\ncurrent default: {S.DEFAULT_SCHEME}")
        return
    if "http" not in text:
        await call(client, "sendMessage", chat_id=chat,
                   text="Link bhejo bhai. /help me example hai.",
                   reply_markup=welcome_markup())
        return

    url = next((tok for tok in text.split() if tok.startswith("http")), "")
    if not url:
        return

    ph = await call(client, "sendMessage", chat_id=chat,
                    text="sheet padh raha hoon…")
    msg_id = (ph.get("result") or {}).get("message_id")
    try:
        result, label = await analyze(url)
    except F.SheetError as exc:
        body = f"{exc.message}" + (f"\n{exc.hint}" if exc.hint else "")
        await _edit_or_send(client, chat, msg_id, body)
        return
    except Exception as exc:                                 # noqa: BLE001
        await _edit_or_send(client, chat, msg_id, f"kuch toot gaya: {type(exc).__name__}")
        return

    sid = session_token(url)
    await _edit_or_send(client, chat, msg_id, card(result, label),
                        markup=result_markup(result, sid))


async def _edit_or_send(client, chat, msg_id, text, markup=None):
    payload = dict(chat_id=chat, text=text, parse_mode="HTML",
                   disable_web_page_preview=True)
    if markup:
        payload["reply_markup"] = markup
    if msg_id:
        payload["message_id"] = msg_id
        r = await call(client, "editMessageText", **payload)
        if r.get("ok"):
            return r
    return await call(client, "sendMessage", **payload)


async def on_callback(client: httpx.AsyncClient, cq: dict) -> None:
    data = cq.get("data") or ""
    msg = cq.get("message") or {}
    chat = (msg.get("chat") or {}).get("id")
    msg_id = msg.get("message_id")
    await call(client, "answerCallbackQuery", callback_query_id=cq["id"])

    if data == "help":
        await call(client, "sendMessage", chat_id=chat, text=WELCOME,
                   parse_mode="HTML", reply_markup=welcome_markup(),
                   disable_web_page_preview=True)
        return
    if data == "schemes":
        lines = ["<b>Marking schemes</b>", ""]
        for code, (lbl, pc, pw) in S.PRESETS.items():
            star = " ← default" if code == S.DEFAULT_SCHEME else ""
            lines.append(f"<code>{code:<8}</code> {lbl}{star}")
        await call(client, "sendMessage", chat_id=chat, text="\n".join(lines),
                   parse_mode="HTML")
        return

    kind, _, rest = data.partition(":")
    scheme = rest.split(":")[0] if kind == "sch" else None
    sid = rest.split(":")[-1]
    url = SESSIONS.get(sid)
    if not url:
        await call(client, "sendMessage", chat_id=chat,
                   text="Ye button purana ho gaya. Link dobara bhej do.")
        return

    try:
        result, label = await analyze(url, scheme=scheme)
    except Exception as exc:                                 # noqa: BLE001
        await call(client, "sendMessage", chat_id=chat,
                   text=f"recalculate fail: {type(exc).__name__}")
        return

    if kind == "alt":
        body = alt_text(result)
        markup = {"inline_keyboard": [[
            {"text": "back to card", "callback_data": f"ref:{sid}"}]]}
    else:
        body = card(result, label)
        markup = result_markup(result, sid)
    await _edit_or_send(client, chat, msg_id, body, markup=markup)


async def run_http() -> None:
    offset = 0
    async with httpx.AsyncClient() as client:
        me = await call(client, "getMe")
        print("bot (plain card):", (me.get("result") or {}).get("username"),
              flush=True)
        tasks: set[asyncio.Task] = set()
        while True:
            try:
                upd = await client.get(f"{API}/getUpdates",
                                       params={"offset": offset,
                                               "timeout": POLL_TIMEOUT},
                                       timeout=POLL_TIMEOUT + 15)
                data = upd.json()
            except Exception as exc:                          # noqa: BLE001
                print("poll error:", exc, flush=True)
                await asyncio.sleep(3)
                continue
            for item in data.get("result", []):
                offset = item["update_id"] + 1
                if item.get("callback_query"):
                    task = asyncio.create_task(
                        on_callback(client, item["callback_query"]))
                else:
                    msg = item.get("message") or item.get("edited_message")
                    if not msg:
                        continue
                    task = asyncio.create_task(on_message(client, msg))
                tasks.add(task)
                task.add_done_callback(tasks.discard)


# ── rich (richpyro) ──────────────────────────────────────────────────────────

async def handle_rich(pclient, message, is_callback: bool = False) -> None:
    from . import tg_rich

    chat = message.chat.id
    text = (message.text or "").strip()
    if is_callback and getattr(message, "data", None):
        text = message.data or ""

    if text.startswith(("/start", "/help")) or text == "help":
        await pclient.send_message(chat, WELCOME, parse_mode="enums.ParseMode.HTML",
                                   reply_markup=welcome_markup())
        return
    if "http" not in text:
        await pclient.send_message(chat, "Link bhejo bhai. /help me example hai.")
        return

    url = next((tok for tok in text.split() if tok.startswith("http")), "")
    placeholder = await pclient.send_message(chat, "sheet padh raha hoon…")
    try:
        result, label = await analyze(url)
        await tg_rich.send_card(pclient, chat, result, label)
    except F.SheetError as exc:
        await pclient.send_message(chat, f"{exc.message}"
                                   + (f"\n{exc.hint}" if exc.hint else ""))
    except Exception as exc:                                 # noqa: BLE001
        await pclient.send_message(chat, f"[x] {type(exc).__name__}")
    finally:
        try:
            await placeholder.delete()
        except Exception:                                    # noqa: BLE001
            pass


async def run_rich() -> None:
    from pyrogram import Client, filters

    app = Client("ssc-marks-bot", api_id=int(TG_API_ID), api_hash=TG_API_HASH,
                 bot_token=TOKEN, in_memory=True)

    @app.on_message(filters.text)
    async def _on_message(client, message):                  # noqa: ANN001
        asyncio.create_task(handle_rich(client, message))

    await app.start()
    me = await app.get_me()
    print(f"bot (rich cards): @{me.username}", flush=True)
    await asyncio.Event().wait()


async def main() -> None:
    if not TOKEN:
        print("TG_TOKEN missing", file=sys.stderr)
        raise SystemExit(2)
    from . import tg_rich
    if TG_API_ID and TG_API_HASH and tg_rich.available():
        await run_rich()
    else:
        if TG_API_ID or TG_API_HASH:
            print("TG_API_ID/TG_API_HASH adhoore hain — plain card pe gir raha hoon",
                  file=sys.stderr)
        await run_http()


if __name__ == "__main__":
    asyncio.run(main())
