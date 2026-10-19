"""Checks on the real pipeline output for all five acts.

These tests read data/cleaned and data/units, which git ignores. Generate
them first:

  uv run python -m regready.extract
  uv run python -m regready.clean
  uv run python -m regready.parse
"""

import json
import re
import tomllib
from pathlib import Path

import pytest

from regready.parse import ACTS, SECTION, check, parse

ROOT = Path(__file__).parent.parent
CLEANED = ROOT / "data" / "cleaned"
UNITS = ROOT / "data" / "units"

if not UNITS.exists():
    pytest.skip("data/units not found: run extract, clean and parse first", allow_module_level=True)

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV"]


def numbers(last, inserted=()):
    return {str(n) for n in range(1, last + 1)} | set(inserted)


# What each act must contain. Recitals are missing from the consolidated
# AI Act and GDPR texts (see corpus.md).
EXPECTED = {
    "ai_act": (numbers(113, ["4a", "60a", "75a", "75b", "75c", "75d"]), 0, set(ROMAN)),
    "gdpr": (numbers(99), 0, set()),
    "dora": (numbers(64), 106, set()),
    "nis2": (numbers(46), 144, set(ROMAN[:3])),
    "data_act": (numbers(50), 119, set()),
}


def load_units(act):
    return [json.loads(line) for line in open(UNITS / f"{act}.jsonl")]


def load_cleaned(stem):
    return [json.loads(line) for line in open(CLEANED / f"{stem}.jsonl")]


@pytest.mark.parametrize("act", EXPECTED)
def test_structure_counts(act):
    articles, recitals, annexes = EXPECTED[act]
    records = load_units(act)

    def found(unit):
        return {r["number"] for r in records if r["unit"] == unit}

    assert found("article") == articles
    assert found("recital") == numbers(recitals)
    assert found("annex") == annexes


@pytest.mark.parametrize("stem", ACTS)
def test_parser_reports_no_problems(stem):
    act, version_date, consolidated = ACTS[stem]
    records, problems = parse(load_cleaned(stem), act, version_date, consolidated)
    structure_problems, notes = check(records)
    assert problems == []
    assert structure_problems == []
    # AI Act Article 43(1) restarts its points in a second subparagraph.
    # Any other restart needs a look, because the two lists share cites.
    expected_notes = ["ai_act:article:43::1:a (seq 563): points restart after a subparagraph"] if act == "ai_act" else []
    assert notes == expected_notes


@pytest.mark.parametrize("act", EXPECTED)
def test_no_leftover_noise(act):
    for r in load_units(act):
        assert not re.search(r"[▼►­]", r["text"]), r["cite"]
        assert not re.match(r"^(EN|L \d+/\d+|\d{1,2}\.\d{1,2}\.\d{4})$", r["text"]), r["cite"]
        # A section heading inside an article means the parser missed it.
        assert not (r["unit"] == "article" and SECTION.match(r["text"])), r["cite"]


def gold_citations():
    questions = tomllib.load(open(ROOT / "eval" / "questions.toml", "rb"))["questions"]
    return [(q["id"], g) for q in questions for g in q["gold"]]


@pytest.mark.parametrize("qid,gold", gold_citations())
def test_gold_citation_resolves(qid, gold):
    blocks = [
        r for r in load_units(gold["act"])
        if r["unit"] == gold["unit"]
        and r["number"] == gold["number"]
        and all(r[k] == gold[k] for k in ("part", "paragraph", "point") if k in gold)
    ]
    assert blocks, f"{qid}: no blocks for {gold}"


@pytest.mark.parametrize("act", EXPECTED)
def test_every_article_has_a_chapter(act):
    # A consolidated text puts "CHAPTER I" before the first article.
    assert not [r["cite"] for r in load_units(act) if r["unit"] == "article" and not r["chapter"]]


# --- Cross-references (data/refs, written by refs.py) ---

REFS = ROOT / "data" / "refs"
needs_refs = pytest.mark.skipif(not REFS.exists(), reason="data/refs not found: run refs")


def load_refs(act):
    return [json.loads(line) for line in open(REFS / f"{act}.jsonl")]


def short(target):
    return ":".join(target[k] or "" for k in ("act", "unit", "number", "part", "paragraph", "point"))


# Checked by hand against the act text.
HAND_CHECKED = [
    ("ai_act", "ai_act:article:6::2:", "Annex III", ["ai_act:annex:III:::"]),
    ("dora", "dora:article:1::2:", "Article 4 of that Directive", ["nis2:article:4:::"]),
    ("ai_act", "ai_act:article:4a::1:", "Article 10(2), points (f) and (g), of this Regulation",
     ["ai_act:article:10::2:f", "ai_act:article:10::2:g"]),
    ("data_act", "data_act:article:1::5:", "Articles 15 and 20 of Regulation (EU) 2016/679",
     ["gdpr:article:15:::", "gdpr:article:20:::"]),
]


@needs_refs
@pytest.mark.parametrize("act,source,text,expected", HAND_CHECKED)
def test_hand_checked_reference(act, source, text, expected):
    [ref] = [r for r in load_refs(act) if r["source"] == source and r["text"] == text]
    assert ref["status"] == "resolved"
    assert [short(t) for t in ref["targets"]] == expected


@needs_refs
@pytest.mark.parametrize("act", EXPECTED)
def test_resolved_targets_exist(act):
    cites = {r["cite"] for a in EXPECTED for r in load_units(a)}
    prefixes = {c.rsplit(":", n)[0] for c in cites for n in range(4)}
    chapters = {(r["act"], r["chapter"], r["section"]) for a in EXPECTED for r in load_units(a) if r["chapter"]}
    chapters |= {(a, c, None) for a, c, _ in chapters}
    for ref in load_refs(act):
        assert ref["status"] in ("resolved", "outside_corpus", "unresolved", "in_quote")
        assert bool(ref["targets"]) == (ref["status"] == "resolved")
        for t in ref["targets"]:
            if "chapter" in t:
                assert (t["act"], t["chapter"], t["section"]) in chapters, ref
            else:
                assert short(t).rstrip(":") in {p.rstrip(":") for p in prefixes}, ref
