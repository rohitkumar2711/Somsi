"""Unit tests on saved real pages. Run: python3 -m pytest -q (or python3 tests/test_parser.py)"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from app import parser as P          # noqa: E402
from app import scoring as S         # noqa: E402

FIX = HERE / "fixtures"
PAGE_A = (FIX / "partA.html").read_text(encoding="utf-8", errors="replace")
PAGE_B = (FIX / "partB.html").read_text(encoding="utf-8", errors="replace")


def test_label_and_code():
    assert P.part_label(PAGE_A) == "PART-A (General Intelligence and Reasoning)"
    code, name = P.split_label(P.part_label(PAGE_A))
    assert code == "PART-A"
    assert name == "General Intelligence and Reasoning"


def test_hidden_fields_present():
    hf = P.hidden_fields(PAGE_A)
    assert "__VIEWSTATE" in hf and len(hf["__VIEWSTATE"]) > 100
    assert "__EVENTVALIDATION" in hf


def test_buttons():
    buttons = P.submit_buttons(PAGE_A)
    assert P.button_part(buttons["P2"]) == "PART-B"
    assert P.button_part(buttons["P4"]) == "PART-D"


def test_question_counts_match_colours():
    qa = P.parse_questions(PAGE_A)
    assert len(qa) == 25
    counts = {s: sum(1 for q in qa if q["status"] == s) for s in P.STATUSES}
    assert counts == {"correct": 15, "wrong": 5, "skipped": 5, "unknown": 0}
    # numbering is absolute across parts
    assert [q["qno"] for q in qa][:3] == [1, 2, 3]


def test_second_part():
    qb = P.parse_questions(PAGE_B)
    counts = {s: sum(1 for q in qb if q["status"] == s) for s in P.STATUSES}
    assert counts == {"correct": 8, "wrong": 8, "skipped": 9, "unknown": 0}
    assert qb[0]["qno"] == 26 and qb[-1]["qno"] == 50


def test_default_scheme_is_half():
    label, pc, pw = S.resolve()
    assert pw == S.Fraction(1, 2) and pc == 2
    out = S.summarize([P.parse_sheet(PAGE_A)], pc, pw)
    assert abs(out["totals"]["marks"] - 27.5) < 0.01


def test_scoring_third_penalty():
    sections = [P.parse_sheet(PAGE_A)]
    out = S.summarize(sections, *S.resolve(scheme="ssc-1/3")[1:])
    assert out["totals"]["correct"] == 15
    assert abs(out["totals"]["marks"] - 28.3333) < 0.01
    assert out["totals"]["max"] == 50.0


def test_scoring_half_penalty():
    sections = [P.parse_sheet(PAGE_A)]
    _, pc, pw = S.resolve(scheme="cgl-t1")
    out = S.summarize(sections, pc, pw)
    assert abs(out["totals"]["marks"] - 27.5) < 0.01


def test_question_number_lists():
    out = S.summarize([P.parse_sheet(PAGE_A)], *S.resolve()[1:])
    sec = out["sections"][0]
    assert sec["questions_wrong"] == [13, 16, 20, 22, 25]
    assert sec["questions_skipped"] == [2, 6, 7, 15, 18]


def test_number_parsing():
    assert S.parse_number("1/3") == S.Fraction(1, 3)
    assert S.parse_number("0.5") == S.Fraction(1, 2)
    assert S.parse_number(2) == S.Fraction(2)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except AssertionError as exc:
                fails += 1
                print(f"FAIL {name}: {exc}")
    print("\nall good" if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
