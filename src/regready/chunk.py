"""Build small chunks, one per text block, for retrieval.

Input:  data/units/<act>.jsonl for all acts (see parse.py).
Output: data/chunks/blocks.jsonl, one chunk per line.

Each chunk is one block, but the text that gets searched carries context:
a header naming the act, the citation and the title, and for a point the
lead-in that the point completes. Without this, a block such as
"importers and distributors of AI systems;" says nothing about where it
belongs.

  AI Act, Article 5(1)(f), Prohibited AI practices
  The following AI practices shall be prohibited:
  the placing on the market ... to infer emotions of a natural person ...

Record format
-------------
  id            act and block seq, such as "ai_act:563"
  cite          cite of the block (see parse.py)
  blocks        seq numbers of the blocks the chunk contains; the scorer
                uses these
  parents       cite of the unit to expand to at each level: "point",
                "paragraph" and "article". The retriever picks the level.
  text          the searched text: header, lead-in and block text
  words         word count of text
  act, title, chapter, section, version_date   copied from the block

Title blocks do not become chunks. Their text is in every header.

Run: uv run python -m regready.chunk
"""

import json
from pathlib import Path

from regready.parse import ACTS

UNITS_DIR = Path("data/units")
OUT_DIR = Path("data/chunks")

ACT_NAMES = {"ai_act": "AI Act", "gdpr": "GDPR", "dora": "DORA", "nis2": "NIS2", "data_act": "Data Act"}

LOCATION = ("act", "unit", "number", "part", "paragraph", "point")


def make_cite(*values) -> str:
    return ":".join(value or "" for value in values)


def label(block: dict) -> str:
    """Human-readable citation: "Article 5(1)(f)", "Annex VIII, Section A,
    point 1", "Article 113, point (c)" or "Recital 34"."""
    unit, number, part, paragraph, point = (block[k] for k in LOCATION[1:])
    if unit == "recital":
        return f"Recital {number}"
    if unit == "annex":
        text = f"Annex {number}" + (f", Section {part}" if part else "")
        if paragraph:
            text += f", point {paragraph}" + (f"({point})" if point else "")
        elif point:
            text += f", point ({point})"
        return text
    text = f"Article {number}" + (f"({paragraph})" if paragraph else "")
    if point:
        text += f"({point})" if paragraph else f", point ({point})"
    return text


def parents(block: dict) -> dict[str, str]:
    """The unit a block expands to at each level.

    A level the block does not have falls back to the next larger unit: a
    block that is not in a point expands to its paragraph at point level.
    """
    act, unit, number, part, paragraph, point = (block[k] for k in LOCATION)
    return {
        "point": make_cite(act, unit, number, part, paragraph, point),
        "paragraph": make_cite(act, unit, number, part, paragraph, None),
        "article": make_cite(act, unit, number, None, None, None),
    }


def lead_ins(blocks: list[dict]) -> dict[int, list[str]]:
    """Text each point block completes, by block seq.

    A point's lead-in is the nearest paragraph-level block before the point
    starts. It is not always the paragraph's first block: Article 113 has
    unnumbered paragraphs, and the points follow "However:"; Article 43(1)
    has a second list of points after a second lead-in. A sub-point block,
    such as Article 113, point (c)(i), also gets the first block of its
    point: "Chapter III, Sections 1, 2, and 3 ... shall apply from:".
    """
    last_paragraph_block: dict[tuple, str] = {}  # paragraph key -> text
    point_lead: dict[tuple, str | None] = {}  # point key -> lead-in when the point started
    point_first: dict[tuple, dict] = {}  # point key -> first block of the point
    result = {}
    for b in blocks:
        if b["kind"] == "title":
            continue
        key = tuple(b[k] for k in LOCATION)
        if b["point"] is None:
            # Paragraph-level text ends the current list of points. A point
            # seen after it, such as the second (a) in Article 43(1), starts
            # a new list with this text as its lead-in.
            last_paragraph_block[key[:5]] = b["text"]
            for point_key in [k for k in point_first if k[:5] == key[:5]]:
                del point_first[point_key]
            continue
        if key not in point_first:
            point_first[key] = b
            point_lead[key] = last_paragraph_block.get(key[:5])
        texts = [point_lead[key]] if point_lead[key] else []
        if point_first[key] is not b:
            texts.append(point_first[key]["text"])
        result[b["seq"]] = texts
    return result


def build(blocks: list[dict]) -> list[dict]:
    """Chunks for the blocks of one act."""
    leads = lead_ins(blocks)
    chunks = []
    for b in blocks:
        if b["kind"] == "title":
            continue
        header = ", ".join(part for part in (ACT_NAMES[b["act"]], label(b), b["title"]) if part)
        text = "\n".join([header, *leads.get(b["seq"], []), b["text"]])
        chunks.append({
            "id": f"{b['act']}:{b['seq']}",
            "cite": b["cite"],
            "blocks": [b["seq"]],
            "parents": parents(b),
            "text": text,
            "words": len(text.split()),
            "act": b["act"],
            "title": b["title"],
            "chapter": b["chapter"],
            "section": b["section"],
            "version_date": b["version_date"],
        })
    return chunks


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    with open(OUT_DIR / "blocks.jsonl", "w") as f:
        for act, _, _ in ACTS.values():
            blocks = [json.loads(line) for line in open(UNITS_DIR / f"{act}.jsonl")]
            chunks = build(blocks)
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            words = sorted(c["words"] for c in chunks)
            print(f"{act}: {len(chunks)} chunks, words median {words[len(words) // 2]}, max {words[-1]}")
            total += len(chunks)
    print(f"total: {total} chunks")


if __name__ == "__main__":
    main()
