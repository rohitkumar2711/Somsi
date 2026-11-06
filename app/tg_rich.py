"""Premium Telegram card using richpyro (Telegram "Rich Messages").

richpyro is a Pyrogram/Kurigram wrapper for Bot API 10.1 rich blocks - headings,
tables, dividers, styled text, buttons. It makes the *Telegram* card look like a
printed result sheet instead of a monospace wall.

It is NOT a web UI library and it cannot style the website; the page upgrade is
pure CSS/JS in app/ui.py.

Enable it by setting TG_API_ID + TG_API_HASH (my.telegram.org). Without those,
app/tg.py falls back to the plain Bot API HTML card - no dependency required.
"""

from __future__ import annotations

import os

PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")

try:                                        # optional dependency
    import richpyro as R
    HAVE_RICH = True
except Exception:                           # noqa: BLE001  (missing lib / bad env)
    R = None
    HAVE_RICH = False


def available() -> bool:
    return HAVE_RICH


def _bar(frac: float, width: int = 12) -> str:
    frac = max(0.0, min(1.0, frac))
    filled = round(frac * width)
    return "#" * filled + "." * (width - filled)


def build_card(result: dict, scheme_label: str):
    """Score dict -> InputRichMessage. Raises if richpyro is missing."""
    if not HAVE_RICH:
        raise RuntimeError("richpyro not installed")

    t = result["totals"]
    pct = t["percentage"] / 100

    blocks = [
        R.heading("SSC Response Sheet", 2),
        R.para(R.bold(f"{t['marks']:.2f}"), R.code(f" / {t['max']:g}"),
               "   ", R.bold(f"{t['percentage']:.1f}%")),
        R.para(R.code(_bar(pct)), "  accuracy ", R.bold(f"{t['accuracy']:.1f}%")),
        R.divider(),
    ]

    head = [R.table_cell(h, is_header=True, align="left") for h in
            ("Section", "C", "W", "S", "Marks")]
    rows = [head]
    for s in result["sections"]:
        rows.append([
            R.table_cell(f"{s['code'].replace('PART-', '')}  {s['name'][:18]}", align="left"),
            R.table_cell(str(s["correct"]), align="right"),
            R.table_cell(str(s["wrong"]), align="right"),
            R.table_cell(str(s["skipped"]), align="right"),
            R.table_cell(f"{s['marks']:.2f}/{s['max']:g}", align="right"),
        ])
    rows.append([
        R.table_cell("TOTAL", align="left"),
        R.table_cell(str(t["correct"]), align="right"),
        R.table_cell(str(t["wrong"]), align="right"),
        R.table_cell(str(t["skipped"]), align="right"),
        R.table_cell(f"{t['marks']:.2f}/{t['max']:g}", align="right"),
    ])
    blocks.append(R.table(rows, bordered=True, striped=True, compact=True,
                          cap=f"scheme: {scheme_label}"))

    wrong = [(s["code"].replace("PART-", ""), s.get("questions_wrong") or [])
             for s in result["sections"] if s.get("questions_wrong")]
    if wrong:
        blocks.append(R.divider())
        blocks.append(R.para(R.bold("galat:"), " " + " · ".join(
            f"{code} {', '.join(str(q) for q in qs[:12])}" for code, qs in wrong)))

    if result.get("alternates"):
        blocks.append(R.para(R.bold("other schemes:"), " " + " · ".join(
            f"{a['label'].split(' (')[0]} {a['marks']:g}"
            for a in result["alternates"][:3])))

    for note in result.get("notes", []):
        blocks.append(R.para(note))

    if PUBLIC_URL:
        blocks.append(R.buttons(R.url_btn("open the web version", PUBLIC_URL)))

    blocks.append(R.footer("+2 sahi · -0.5 galat · ssc marks analyser"))
    return R.message(*blocks)


async def send_card(client, chat_id: int, result: dict, scheme_label: str):
    """Send through a started Pyrogram/Kurigram client."""
    card = build_card(result, scheme_label)
    return await client.send_rich_message(chat_id, rich_message=card)
