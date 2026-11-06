"""Pure HTML -> structured data. No I/O, no async, no external deps.

The SSC response sheet renders every question and option as an image, so the
only machine-readable signal is the fill colour on the option cells:

    green  -> correct option selected   (+ marks)
    red    -> wrong option selected     (- penalty)
    gray   -> left blank                (0)
    yellow -> the correct option, drawn on questions you did not get right
"""

from __future__ import annotations

import re

FORM_RE = re.compile(r"<form[^>]*action=[\"']([^\"']*)[\"']", re.I)
INPUT_RE = re.compile(r"<input\b[^>]*>", re.I)
ATTR_RE = re.compile(r"([A-Za-z_:][\w:.-]*)\s*=\s*[\"']([^\"']*)[\"']")
SUBJECT_RE = re.compile(r'id="lblsubject"[^>]*>(.*?)</span>', re.I | re.S)
QNO_RE = re.compile(r"Q\.No\s*:?\s*(?:&nbsp;|\s)*?(\d+)", re.I)
BGCOLOR_RE = re.compile(r"bgcolor\s*=\s*[\"']?\s*(#?[A-Za-z0-9]+)", re.I)
STYLE_BG_RE = re.compile(r"background(?:-color)?\s*:\s*(#?[A-Za-z0-9]+)", re.I)

COLOUR_WORDS = ("green", "red", "gray", "grey", "yellow", "orange", "blue")

DEFAULT_PART_NAMES = {
    "PART-A": "General Intelligence and Reasoning",
    "PART-B": "General Awareness",
    "PART-C": "Quantitative Aptitude",
    "PART-D": "English Comprehension",
}

STATUSES = ("correct", "wrong", "skipped", "unknown")


def attrs(tag: str) -> dict:
    return {k.lower(): v for k, v in ATTR_RE.findall(tag)}


def hidden_fields(html: str) -> dict:
    """__VIEWSTATE / __EVENTVALIDATION and every other hidden input."""
    out = {}
    for tag in INPUT_RE.findall(html):
        a = attrs(tag)
        if a.get("type", "").lower() == "hidden" and "name" in a:
            out[a["name"]] = a.get("value", "")
    return out


def submit_buttons(html: str) -> dict:
    """{'P2': 'Click Here for PART-B', ...} - only the enabled ones."""
    out = {}
    for tag in INPUT_RE.findall(html):
        if re.search(r"\bdisabled\b", tag, re.I):
            continue
        a = attrs(tag)
        if a.get("type", "").lower() == "submit" and a.get("name") and a.get("value"):
            out[a["name"]] = a["value"]
    return out


def form_action(html: str) -> str:
    m = FORM_RE.search(html)
    return (m.group(1) if m else "").replace("&amp;", "&")


def part_label(html: str) -> str:
    m = SUBJECT_RE.search(html)
    if not m:
        return ""
    txt = re.sub(r"&nbsp;?", " ", m.group(1))
    return re.sub(r"\s+", " ", txt).strip()


def split_label(label: str) -> tuple[str, str]:
    """'PART-A (General Intelligence and Reasoning)' -> ('PART-A', 'General ...')"""
    label = re.sub(r"\s+", " ", label or "").strip()
    m = re.match(r"(PART[\s\-]?[A-Z0-9]+)\s*[(\-:]?\s*(.*?)\)?\s*$", label, re.I)
    if m:
        code = re.sub(r"\s+", "-", m.group(1).upper())
        name = m.group(2).strip() or DEFAULT_PART_NAMES.get(code, code)
        return code, name
    return "", label


def button_part(value: str) -> str:
    """'Click Here for PART-C' -> 'PART-C'."""
    m = re.search(r"PART[\s\-]?([A-Z0-9]+)", value or "", re.I)
    return f"PART-{m.group(1).upper()}" if m else ""


def _colours(block: str) -> set[str]:
    found: set[str] = set()
    for rx in (BGCOLOR_RE, STYLE_BG_RE):
        for val in rx.findall(block):
            v = val.strip().lower().lstrip("#")
            for word in COLOUR_WORDS:
                if v == word or v.endswith(word):
                    found.add("gray" if word == "grey" else word)
    return found


def parse_questions(html: str) -> list[dict]:
    """Split on Q.No markers, classify each question from its colours."""
    marks = [(m.start(), int(m.group(1))) for m in QNO_RE.finditer(html)]
    if not marks:
        return []
    out: list[dict] = []
    seen: set[int] = set()
    for i, (pos, qno) in enumerate(marks):
        if qno in seen:
            continue
        seen.add(qno)
        end = marks[i + 1][0] if i + 1 < len(marks) else len(html)
        colours = _colours(html[pos:end])
        if "green" in colours:
            status = "correct"
        elif "red" in colours:
            status = "wrong"
        elif "gray" in colours:
            status = "skipped"
        else:
            status = "unknown"
        out.append({"qno": qno, "status": status})
    out.sort(key=lambda q: q["qno"])
    return out


def parse_sheet(html: str) -> dict:
    """One page (one PART) -> {'code', 'name', 'questions'}."""
    label = part_label(html)
    code, name = split_label(label)
    questions = parse_questions(html)
    if not name:
        name = DEFAULT_PART_NAMES.get(code, code or "Section")
    return {"code": code, "name": name, "questions": questions, "label": label}


def has_answer_key(questions: list[dict]) -> bool:
    return any(q["status"] in ("correct", "wrong") for q in questions)
