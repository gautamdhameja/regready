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
