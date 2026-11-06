"""Marking schemes and score math.

The server sends raw counts (correct / wrong / skipped per section); the client
does the arithmetic, so switching schemes costs zero extra requests.
"""

from __future__ import annotations

from fractions import Fraction

# code -> (label, marks per correct, marks cut per wrong)
PRESETS: dict[str, tuple[str, Fraction, Fraction]] = {
    "cgl-t1": ("CGL Tier-1 (+2, -1/2)", Fraction(2), Fraction(1, 2)),
    "ssc-1/3": ("+2, -1/3 (older SSC papers)", Fraction(2), Fraction(1, 3)),
    "cgl-t2": ("CGL Tier-2 (+3, -1)", Fraction(3), Fraction(1)),
    "chsl-t1": ("CHSL Tier-1 (+2, -1/2)", Fraction(2), Fraction(1, 2)),
    "mts": ("MTS (+1, no negative)", Fraction(1), Fraction(0)),
}
DEFAULT_SCHEME = "cgl-t1"


def parse_number(txt) -> Fraction:
    if txt is None:
        raise ValueError("empty number")
    if isinstance(txt, Fraction):
        return txt
    if isinstance(txt, (int, float)):
        return Fraction(str(txt))
    s = str(txt).strip().replace("\u2212", "-").replace(",", ".")
    if "/" in s:
        a, b = s.split("/", 1)
        return Fraction(a.strip()) / Fraction(b.strip())
    return Fraction(s)


def resolve(correct=None, wrong=None, scheme: str | None = None):
    """Return (label, per_correct, per_wrong) from a scheme code or numbers."""
    if correct is None and wrong is None:
        label, pc, pw = PRESETS.get(scheme or DEFAULT_SCHEME,
                                    PRESETS[DEFAULT_SCHEME])
        return label, pc, pw
    pc = parse_number(correct if correct is not None else 2)
    pw = parse_number(wrong if wrong is not None else Fraction(1, 2))
    return f"custom (+{float(pc):g}, -{float(pw):g})", pc, pw


def section_score(correct: int, wrong: int, pc: Fraction, pw: Fraction) -> Fraction:
    return Fraction(correct) * pc - Fraction(wrong) * pw


def counts(section: dict) -> tuple[int, int, int, int, list[dict]]:
    """Accepts either a raw parsed section (questions list) or a counted one."""
    if "correct" in section:
        return (section["correct"], section["wrong"], section["skipped"],
                section.get("unknown", 0), section.get("questions", []))
    questions = section.get("questions", [])
    c = sum(1 for q in questions if q["status"] == "correct")
    w = sum(1 for q in questions if q["status"] == "wrong")
    sk = sum(1 for q in questions if q["status"] == "skipped")
    u = sum(1 for q in questions if q["status"] == "unknown")
    return c, w, sk, u, questions


def summarize(sections: list[dict], pc: Fraction, pw: Fraction) -> dict:
    """Add marks per section + totals. Works on raw or counted sections."""
    out_sections = []
    tc = tw = ts = tu = 0
    total = Fraction(0)
    total_max = Fraction(0)
    for s in sections:
        c, w, sk, u, questions = counts(s)
        marks = section_score(c, w, pc, pw)
        sec_max = pc * (c + w + sk + u)
        tc += c
        tw += w
        ts += sk
        tu += u
        total += marks
        total_max += sec_max
        out_sections.append({
            "code": s.get("code", ""),
            "name": s.get("name", ""),
            "correct": c,
            "wrong": w,
            "skipped": sk,
            "unknown": u,
            "questions_wrong": [q["qno"] for q in questions if q["status"] == "wrong"],
            "questions_skipped": [q["qno"] for q in questions if q["status"] == "skipped"],
            "marks": round(float(marks), 4),
            "max": float(sec_max),
            "attempted": c + w,
            "accuracy": round(c / (c + w) * 100, 2) if (c + w) else 0.0,
            "share": round(float(marks) / float(sec_max) * 100, 1) if sec_max else 0.0,
        })
    asked = tc + tw + ts + tu
    return {
        "sections": out_sections,
        "totals": {
            "questions": asked,
            "correct": tc,
            "wrong": tw,
            "skipped": ts,
            "unknown": tu,
            "attempted": tc + tw,
            "marks": round(float(total), 4),
            "max": float(total_max),
            "percentage": round(float(total) / float(total_max) * 100, 2)
            if total_max else 0.0,
            "accuracy": round(tc / (tc + tw) * 100, 2) if (tc + tw) else 0.0,
        },
        "scheme": {"per_correct": float(pc), "per_wrong": float(pw)},
    }
