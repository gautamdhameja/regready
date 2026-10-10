"""Clean docling JSON into a flat list of items in reading order.

Each item is a dict with these keys:
  label   docling label, such as "section_header", "list_item", "text",
          "footnote", or "table"
  text    cleaned text
  marker  list marker that docling split off the text, such as "1.", or ""
  page    page number in the PDF

Cleaning steps:
  1. Walk the document tree in reading order. Skip page headers, footers
     and stray page stamps.
  2. Remove consolidation markers (▼B, ▼M1, ►B) and soft hyphens.
  3. Join an item that continues a sentence across a page break onto the
     item before it.

This module reads docling JSON as plain data and does not import docling.

Run: uv run python -m regready.clean
"""

import json
import re
from pathlib import Path

IN_DIR = Path("data/extracted")
OUT_DIR = Path("data/cleaned")

# Consolidated EUR-Lex texts mark the origin of each passage: ▼B for the
# original act, ▼M1 for the first amendment, ▼C1 for the first corrigendum.
MARKER = re.compile(r"[▼►][A-Z]\d*")

# Page stamps that docling correctly moves out of the body. Anything else
# outside the body may be real content, so it is reported.
PAGE_STAMP = re.compile(
    r"^\d{5}[RL]\d{4} - EN - "  # consolidated: 02024R1689 - EN - 27.07.2026 - ...
    r"|Official Journal of the European Union"
    r"|^(EN )?(EN|L \d+/\d+|\d{1,2}\.\d{1,2}\.\d{4}|L series|\d+/\d+)$"  # EN 27.12.2022
    r"|^OJ L, \d{1,2}\.\d{1,2}\.\d{4}$"  # Data Act: OJ L, 22.12.2023
    r"|^ELI: "
)

# Some page stamps stay in the body as separate items, such as "EN" or
# "27.12.2022". Only exact matches are dropped, so real text is never lost.
BODY_STAMP = re.compile(r"^(EN )?(EN|L \d+/\d+|\d{1,2}\.\d{1,2}\.\d{4})$")


def resolve(doc: dict, ref: str) -> dict:
    # A ref looks like "#/texts/12".
    _, kind, index = ref.split("/")
    return doc[kind][int(index)]


def walk(doc: dict, node: dict):
    """Yield text and table nodes under node, in reading order."""
    for child in node.get("children", []):
        item = resolve(doc, child["$ref"])
        if item.get("label") == "table":
            yield item
            continue  # cell text is read from the table grid
        if "text" in item:
            yield item
        yield from walk(doc, item)


def table_text(table: dict) -> str:
    rows = table["data"]["grid"]
    return "\n".join(" | ".join(clean_text(cell["text"]) for cell in row) for row in rows)


def clean_text(text: str) -> str:
    text = MARKER.sub("", text)
    # A soft hyphen marks a word split at a line end: "dispropor\xad tionate".
    text = re.sub(r"­\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def clean(doc: dict) -> tuple[list[dict], list[dict]]:
    """Return the cleaned items and the skipped items that need review."""
    items, review = [], []
    for node in walk(doc, doc["body"]):
        page = node["prov"][0]["page_no"] if node.get("prov") else None

        if node.get("content_layer") != "body":
            if not PAGE_STAMP.search(node.get("text", "")):
                review.append({"label": node["label"], "text": node["text"], "page": page})
            continue

        if node["label"] == "table":
            text = table_text(node)
        else:
            text = clean_text(node["text"])
        if not text or BODY_STAMP.match(text):
            continue  # the item held only a consolidation marker or a page stamp

        item = {"label": node["label"], "text": text, "marker": node.get("marker", ""), "page": page}

        # A body item that starts in lower case on a new page continues the
        # sentence from the previous page. Footnotes sit between the two parts.
        previous = next((i for i in reversed(items) if i["label"] != "footnote"), None)
        if (
            previous
            and text[0].islower()
            and item["label"] in ("text", "list_item")
            and previous["page"] != page
        ):
            previous["text"] += " " + text
            continue

        items.append(item)
    return items, review


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(IN_DIR.glob("*.json")):
        if path.name.endswith(".meta.json"):
            continue
        items, review = clean(json.loads(path.read_text()))
        with open(OUT_DIR / f"{path.stem}.jsonl", "w") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"{path.stem}: {len(items)} items, {len(review)} to review")
        for r in review:
            print(f"  review p.{r['page']} [{r['label']}] {r['text'][:80]}")


if __name__ == "__main__":
    main()
