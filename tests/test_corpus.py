"""Checks on the real pipeline output for all five acts.

These tests read data/, which git ignores. Generate it first:

  uv run python -m regready.extract
  uv run python -m regready.clean
  uv run python -m regready.parse
  uv run python -m regready.refs
  uv run python -m regready.chunk
"""

import json
import re
import tomllib
from functools import cache
from pathlib import Path

import pytest

from regready.clean import BODY_STAMP
from regready.corpus import ACTS
from regready.parse import LOCATION, SECTION, check, make_cite, parse

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"

if not (DATA / "units").exists():
    pytest.skip("data/units not found: run the pipeline first", allow_module_level=True)

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV"]


def numbers(last, inserted=()):
    return {str(n) for n in range(1, last + 1)} | set(inserted)


# Articles, recitals and annexes each act must contain. The consolidated
# AI Act and GDPR texts have no recitals (see corpus.md).
EXPECTED = {
    "ai_act": (numbers(113, ["4a", "60a", "75a", "75b", "75c", "75d"]), 0, set(ROMAN)),
    "gdpr": (numbers(99), 0, set()),
    "dora": (numbers(64), 106, set()),
    "nis2": (numbers(46), 144, set(ROMAN[:3])),
    "data_act": (numbers(50), 119, set()),
}


def read_jsonl(path):
    return [json.loads(line) for line in open(path)]


@cache
def load_units(act):
    return read_jsonl(DATA / "units" / f"{act}.jsonl")


@cache
def existing_units():
    """Location of every unit at every level, such as Article 5, 5(1) and 5(1)(f)."""
    units = set()
    for act in EXPECTED:
        for b in load_units(act):
            act_, unit, number, part, paragraph, point = (b[k] for k in LOCATION)
            units |= {(act_, unit, number, None, None, None), (act_, unit, number, part, None, None),
                      (act_, unit, number, part, paragraph, None), (act_, unit, number, part, paragraph, point)}
    return units


# --- Units (data/units, written by parse.py) ---


@pytest.mark.parametrize("act", EXPECTED)
def test_structure_counts(act):
    articles, recitals, annexes = EXPECTED[act]

    def found(unit):
        return {r["number"] for r in load_units(act) if r["unit"] == unit}

    assert found("article") == articles
    assert found("recital") == numbers(recitals)
    assert found("annex") == annexes


@pytest.mark.parametrize("act", ACTS, ids=lambda act: act.key)
def test_parser_reports_no_problems(act):
    items = read_jsonl(DATA / "cleaned" / f"{act.stem}.jsonl")
    records, problems = parse(items, act.key, act.version_date, act.consolidated)
    structure_problems, notes = check(records)
    assert problems == []
    assert structure_problems == []
    # AI Act Article 43(1) restarts its points in a second subparagraph.
    # Any other restart needs a look, because the two lists share cites.
    expected_notes = ["ai_act:article:43::1:a (seq 563): points restart after a subparagraph"] if act.key == "ai_act" else []
    assert notes == expected_notes


@pytest.mark.parametrize("act", EXPECTED)
def test_no_leftover_noise(act):
    for r in load_units(act):
        assert not re.search("[▼►\u00ad]", r["text"]), r["cite"]
        assert not BODY_STAMP.match(r["text"]), r["cite"]
        # A section heading inside an article means the parser missed it.
        assert not (r["unit"] == "article" and SECTION.match(r["text"])), r["cite"]


@pytest.mark.parametrize("act", EXPECTED)
def test_every_article_has_a_chapter(act):
    # A consolidated text puts "CHAPTER I" before the first article.
    assert not [r["cite"] for r in load_units(act) if r["unit"] == "article" and not r["chapter"]]


def gold_citations():
    questions = tomllib.load(open(ROOT / "eval" / "questions.toml", "rb"))["questions"]
    return [(q["id"], g) for q in questions for g in q["gold"]]


@pytest.mark.parametrize("qid,gold", gold_citations())
def test_gold_citation_resolves(qid, gold):
    location = tuple(gold.get(k) for k in LOCATION)
    assert location in existing_units(), qid


# --- Cross-references (data/refs, written by refs.py) ---

needs_refs = pytest.mark.skipif(not (DATA / "refs").exists(), reason="data/refs not found: run refs")

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
    [ref] = [r for r in read_jsonl(DATA / "refs" / f"{act}.jsonl") if r["source"] == source and r["text"] == text]
    assert ref["status"] == "resolved"
    assert [make_cite(*(t[k] for k in LOCATION)) for t in ref["targets"]] == expected


@needs_refs
@pytest.mark.parametrize("act", EXPECTED)
def test_resolved_targets_exist(act):
    chapters = {(b["act"], b["chapter"], s) for a in EXPECTED for b in load_units(a) if b["chapter"]
                for s in (None, b["section"])}
    for ref in read_jsonl(DATA / "refs" / f"{act}.jsonl"):
        assert ref["status"] in ("resolved", "outside_corpus", "unresolved", "in_quote")
        assert bool(ref["targets"]) == (ref["status"] == "resolved")
        for t in ref["targets"]:
            if "chapter" in t:
                assert (t["act"], t["chapter"], t["section"]) in chapters, ref
            else:
                assert tuple(t[k] for k in LOCATION) in existing_units(), ref


# --- Chunks (data/chunks, written by chunk.py) ---

CHUNKS = DATA / "chunks" / "blocks.jsonl"
needs_chunks = pytest.mark.skipif(not CHUNKS.exists(), reason="data/chunks not found: run chunk")


@needs_chunks
def test_one_chunk_per_non_title_block():
    chunks = read_jsonl(CHUNKS)
    blocks = {(b["act"], b["seq"]) for a in EXPECTED for b in load_units(a) if b["kind"] != "title"}
    assert sorted((c["act"], c["blocks"][0]) for c in chunks) == sorted(blocks)


@needs_chunks
def test_chunk_parents_exist():
    for chunk in read_jsonl(CHUNKS):
        for level, parent in chunk["parents"].items():
            location = tuple(value or None for value in parent.split(":"))
            assert location in existing_units(), (chunk["id"], level, parent)
