"""Find cross-references in the legal units and resolve them to citations.

Input:  data/units/<act>.jsonl for all acts (see parse.py).
Output: data/refs/<act>.jsonl, one reference per line.

Record format
-------------
  seq      seq of the block that contains the reference
  source   cite of that block
  text     the reference as written, such as
           "Article 9(1) of Regulation (EU) 2016/679"
  status   resolved        every target exists in the corpus
           outside_corpus  the reference names an act outside the corpus
           unresolved      the act or a target could not be found
           in_quote        the block is quoted text in an amending article,
                           so the reference points into the amended act
  targets  citations, empty unless status is resolved. A unit target has
           act, unit, number, part, paragraph and point, as gold citations
           do. A chapter target has act, chapter and section.

Resolution rules
----------------
- The act comes from the suffix: "of this Regulation" is the same act,
  "of Regulation (EU) 2016/679" is the GDPR. "of that Directive" is the
  last directive named earlier in the same block. With no suffix, the act
  is the block's own act, the amended act in an article titled
  "Amendment(s) to <act>", or in a correlation table the act named at the
  top of the column.
- Relative references use the block's position: "paragraph 1" is in the
  same article, "point (a)" in the same paragraph.
- Points follow the gold citation rules: a numbered point "(4)" or "1" is
  a paragraph, a lettered point "(a)" is a point. Subparagraphs are ignored.
- Lists and ranges expand to separate targets. A range expands to the units
  that exist, so "points (b) to (c)" includes an inserted "(ba)".
- A target that does not exist makes the whole reference unresolved.
- "this Article" or "this Regulation" on their own name no other unit and
  make no record.

Run: uv run python -m regready.refs
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

from regready.parse import ACTS

UNITS_DIR = Path("data/units")
OUT_DIR = Path("data/refs")

# Official numbers of the corpus acts, as other acts cite them.
CORPUS_NUMBERS = {
    "2024/1689": "ai_act",
    "2016/679": "gdpr",
    "2022/2554": "dora",
    "2022/2555": "nis2",
    "2023/2854": "data_act",
}

# --- Grammar of a reference -------------------------------------------------
#
# A reference is a chain of segments joined by "," or "of", with an optional
# suffix naming the act:
#
#   points (f) and (g)  ,  Article 10(2)  ,  of this Regulation
#   Section A  of  Annex VIII
#   point (b)  of the  first subparagraph  of  Article 6(1)

ORDINAL = r"(?:first|second|third|fourth|fifth|sixth|last)"
SINGULAR = r"(?:Article|Annex|[Pp]aragraph|[Pp]oint|[Ss]ubparagraph|Chapter|Section|[Rr]ecital)\b"
PLURAL = r"(?:Articles|Annexes|[Pp]aragraphs|[Pp]oints|[Ss]ubparagraphs|Chapters|Sections|[Rr]ecitals)\b"
# An identifier: 6, 4a, 6(1), 6(1)(a), 4(a), III, A, (a), (4), (ba)
IDENT = r"(?:\d+[a-z]?(?:\(\d+[a-z]?\)|\([a-z]{1,3}\))*|[IVXL]+\b|[A-Z]\b|\((?:\d+[a-z]?|[a-z]{1,3})\)(?:\([a-z]{1,3}\))?)"
SEP = r"(?:\s*,\s*(?:and\s+|or\s+)?|\s+(?:and|or|to)\s+)"
# A singular word takes one identifier, plus bare paragraphs as in
# "Article 6(1) and (2)". Only a plural word takes a list, so the "15" in
# "Article 6, 15 days later" is not read as an article.
SINGULAR_IDS = rf"{IDENT}(?:{SEP}\((?:\d+[a-z]?|[a-z]{{1,3}})\))*"
PLURAL_IDS = rf"{IDENT}(?:{SEP}{IDENT})*"
SEGMENT = (
    rf"(?:{ORDINAL}\s+)?(?:{SINGULAR}\s+{SINGULAR_IDS}|{PLURAL}\s+{PLURAL_IDS})"
    rf"|{ORDINAL}\s+(?:{SINGULAR}|{PLURAL})"
    r"|this\s+(?:Article|paragraph|subparagraph|point|Annex)\b"
)
# Segments join with "," or "of". ", and" joins only before another article
# or annex, as in "Article 2, point (10), and Article 22 of Directive ...",
# so the act suffix applies to both.
LINK = r"(?:\s*,\s*of\s+(?:the\s+)?|\s*,?\s+and\s+(?=Articles?\b|Annex)|\s*,\s*|\s+of\s+(?:the\s+)?)"
CHAIN = rf"\b(?:{SEGMENT})(?:{LINK}(?:{SEGMENT}))*"

ACT_REF = (
    r"(?P<kind>Regulation|Directive|Decision)\s+"
    r"(?:\((?:EU|EC|EEC|EU,\s*Euratom)\)\s+)?(?:No\s+)?"
    r"(?P<number>\d{2,4}/\d+(?:/[A-Z]{2,4})?)"
)
SUFFIX = (
    r",?\s+(?:of\s+(?:"
    r"(?P<self>this)\s+(?:Regulation|Directive)\b"
    r"|(?P<anaphor>that|those)\s+(?P<anaphor_kind>Regulation|Directive|Decision|Article)s?\b"
    r"|(?:the\s+)?(?P<treaty>TFEU|TEU|Charter|Treaty)\b"
    rf"|(?:Commission\s+|Council\s+)?(?:Delegated\s+|Implementing\s+)?{ACT_REF})"
    r"|(?P<treaty_short>TFEU|TEU)\b"
    r"|(?P<thereof>thereof)\b)"
)
REFERENCE = re.compile(rf"(?P<chain>{CHAIN})(?:{SUFFIX})?")
SEGMENT_PARTS = re.compile(
    rf"(?:{ORDINAL}\s+)?(?P<word>{SINGULAR}|{PLURAL})(?:\s+(?P<ids>{PLURAL_IDS}))?"
    r"|this\s+(?P<this>Article|paragraph|subparagraph|point|Annex)\b"
)
ACT_MENTION = re.compile(ACT_REF)
AMENDS = re.compile(rf"^(?:Amendments?|Amendment)\s+(?:to|of)\s+{ACT_REF}")

WORDS = {
    "article": "article", "annex": "annex", "annexe": "annex", "paragraph": "paragraph",
    "point": "point", "subparagraph": "subparagraph", "chapter": "chapter",
    "section": "section", "recital": "recital",
}


def word_kind(word: str) -> str:
    word = word.lower()
    return WORDS.get(word, WORDS.get(word[:-1], WORDS.get(word[:-2], word)))


def split_ident(ident: str) -> tuple[str | None, list[str]]:
    """Split "6(1)(a)" into ("6", ["1", "a"]) and "(2)" into (None, ["2"])."""
    m = re.match(r"^(\d+[a-z]?|[IVXL]+|[A-Z])?(.*)$", ident)
    return m.group(1), re.findall(r"\(([^)]+)\)", m.group(2))


def parse_ids(ids: str) -> list[tuple]:
    """Turn "5, 6 and 8 to 10" into [("one", "5"), ("one", "6"), ("range", "8", "10")]."""
    items: list[tuple] = []
    tokens = re.findall(rf"{IDENT}|\bto\b", ids)
    for i, token in enumerate(tokens):
        if token == "to" or (i and tokens[i - 1] == "to"):
            continue
        if i + 2 < len(tokens) and tokens[i + 1] == "to":
            items.append(("range", token, tokens[i + 2]))
        else:
            items.append(("one", token))
    return items


def address(token: str) -> tuple[str | None, str | None]:
    """Paragraph and point named by a point identifier.

    "(a)" is point a, "(4)" and "1" are paragraphs (numbered points), and
    "4(a)" is paragraph 4, point a.
    """
    head, parens = split_ident(token)
    parts = ([head] if head else []) + parens
    paragraph = next((p for p in parts if p[0].isdigit()), None)
    point = next((p for p in parts if not p[0].isdigit()), None)
    return paragraph, point


# --- Index of existing units ------------------------------------------------


class Index:
    """Which units exist, and the order of units at each level."""

    def __init__(self, blocks: list[dict]):
        self.units: set[tuple] = set()
        self.children: dict[tuple, list] = {}
        self.chapters: set[tuple] = set()
        for b in blocks:
            act, unit, number, part, paragraph, point = (b[k] for k in ("act", "unit", "number", "part", "paragraph", "point"))
            self.add((act, unit), number)
            self.add((act, unit, number), part)
            self.add((act, unit, number, part), paragraph)
            self.add((act, unit, number, part, paragraph), point)
            for key in [(act, unit, number, None, None, None), (act, unit, number, part, None, None),
                        (act, unit, number, part, paragraph, None), (act, unit, number, part, paragraph, point)]:
                self.units.add(key)
            if unit == "article" and b["chapter"]:
                self.chapters.update({(act, b["chapter"], None), (act, b["chapter"], b["section"])})

    def add(self, parent: tuple, child) -> None:
        if child is None:
            return
        siblings = self.children.setdefault(parent, [])
        if child not in siblings:
            siblings.append(child)

    def expand(self, parent: tuple, item: tuple) -> list | None:
        """Values for one list item, or None if it names a unit that does not exist."""
        siblings = self.children.get(parent, [])
        if item[0] == "one":
            return [item[1]] if item[1] in siblings else None
        _, first, last = item
        if first not in siblings or last not in siblings or siblings.index(first) > siblings.index(last):
            return None
        return siblings[siblings.index(first): siblings.index(last) + 1]


# --- Resolution -------------------------------------------------------------


UNIT_KINDS = ("article", "annex", "recital", "chapter")
PART_KINDS = ("section", "paragraph", "point")


def new_group(parts: list[tuple] = ()) -> dict[str, list]:
    group: dict[str, list] = {k: [] for k in UNIT_KINDS + PART_KINDS}
    for kind, ids in parts:
        group[kind].extend(ids)
    return group


def read_chain(chain: str) -> list[dict]:
    """Split a chain into groups, one per article, annex, recital or chapter.

    Order matters. A paragraph or point after a unit, joined by a comma,
    belongs to that unit: "Article 23, point (d), Article 29". One before a
    unit, joined by "of", belongs to the unit that follows: "points 1 to 3
    of Section C of Annex VIII". Parts that belong to no unit are relative
    to the block: "paragraph 1, point (a)" or "paragraph 3 of this Article".
    """
    groups: list[dict] = []
    pending: list[tuple] = []  # parts waiting for the unit they belong to
    current = None  # the last unit, which parts after a comma attach to
    end = 0
    for m in SEGMENT_PARTS.finditer(chain):
        joined_by_of = bool(re.search(r"\bof\b", chain[end:m.start()]))
        end = m.end()
        if m.group("this"):
            if pending:
                groups.append(new_group(pending))
            pending, current = [], None
            continue
        if not m.group("ids"):
            continue  # "the first subparagraph"
        kind = word_kind(m.group("word"))
        ids = parse_ids(m.group("ids"))
        if kind in UNIT_KINDS:
            group = new_group([(kind, ids)] + (pending if joined_by_of else []))
            if pending and not joined_by_of:
                groups.append(new_group(pending))
            pending = []
            groups.append(group)
            current = group
        elif kind in PART_KINDS:
            if current is not None and not joined_by_of:
                current[kind].extend(ids)
            else:
                pending.append((kind, ids))
    if pending:
        groups.append(new_group(pending))
    return groups


def find_act(m: re.Match, block: dict, mentions: list[tuple], default: str) -> str:
    """The act a reference points into: a corpus act key, "outside" or "unknown"."""
    if m.group("self"):
        return block["act"]
    if m.group("number"):
        return CORPUS_NUMBERS.get(m.group("number").split("/EU")[0], "outside")
    if m.group("treaty") or m.group("treaty_short"):
        return "outside"
    if m.group("anaphor"):
        kind = m.group("anaphor_kind")
        earlier = [number for start, k, number in mentions if k == kind and start < m.start()]
        return CORPUS_NUMBERS.get(earlier[-1], "outside") if earlier else "unknown"
    if m.group("thereof"):
        return "unknown"
    return default


def resolve(query: dict, act: str, block: dict, index: Index) -> list[dict] | None:
    """Targets of a reference, or None if a target does not exist."""
    same_act = act == block["act"]

    # Chapters and sections of the enacting terms.
    if query["chapter"] or (query["section"] and not query["annex"] and block["unit"] != "annex"):
        chapters = [c[1] for c in query["chapter"] if c[0] == "one"] or ([block["chapter"]] if same_act else [])
        sections = [s[1] for s in query["section"] if s[0] == "one"] or [None]
        targets = [{"act": act, "chapter": c, "section": s} for c in chapters for s in sections]
        if not targets or any((t["act"], t["chapter"], t["section"]) not in index.chapters for t in targets):
            return None
        return targets

    # Which unit numbers, and any paragraph or point written inline: "6(1)(a)".
    part = None
    if query["article"]:
        unit, items = "article", query["article"]
    elif query["annex"]:
        unit, items = "annex", query["annex"]
        part = query["section"][0][1] if query["section"] else None
    elif query["recital"]:
        unit, items = "recital", query["recital"]
    elif (query["paragraph"] or query["point"] or query["section"]) and same_act:
        unit, items = block["unit"], [("one", block["number"])]
        part = query["section"][0][1] if query["section"] else block["part"]
    else:
        return None

    entries = []  # (number item, inline paragraph item, inline point item)
    for item in items:
        if item[0] == "range":
            first_head, first_parens = split_ident(item[1])
            last_head, last_parens = split_ident(item[2])
            if last_head is None and first_parens and last_parens:  # "Article 99(3) to (7)"
                entries.append((("one", first_head), ("range", first_parens[0], last_parens[0]), None))
            else:  # "Articles 102 to 110"
                entries.append((item, None, None))
            continue
        head, parens = split_ident(item[1])
        if head is None and entries:  # "(2)" in "Article 6(1) and (2)"
            head = entries[-1][0][1]
        paragraph, point = address("(" + ")(".join(parens) + ")") if parens else (None, None)
        entries.append((("one", head), ("one", paragraph) if paragraph else None, ("one", point) if point else None))

    # Paragraphs and points named in their own segments. A paragraph number
    # is sometimes bracketed: "paragraphs (3) to (9)".
    point_items = []
    paragraph_items = [tuple(v.strip("()") if i else v for i, v in enumerate(item)) for item in query["paragraph"]]
    for item in query["point"]:
        if item[0] == "range":
            numbered = item[1][0].isdigit() or item[1].startswith("(") and item[1][1].isdigit()
            target = paragraph_items if numbered else point_items
            target.append(("range", *(address(v)[0] or address(v)[1] for v in item[1:])))
            continue
        paragraph, point = address(item[1])
        if paragraph and not point:
            paragraph_items.append(("one", paragraph))
        else:
            if paragraph:
                paragraph_items.append(("one", paragraph))
            point_items.append(("one", point))

    # A bare "point (a)" is in the block's own paragraph.
    relative = not (query["article"] or query["annex"] or query["recital"])
    if relative and point_items and not paragraph_items and block["paragraph"]:
        paragraph_items = [("one", block["paragraph"])]

    targets = []
    for number_item, inline_paragraph, inline_point in entries:
        numbers = index.expand((act, unit), number_item)
        if numbers is None:
            return None
        for number in numbers:
            paragraphs = [inline_paragraph] if inline_paragraph else paragraph_items or [None]
            points = [inline_point] if inline_point else point_items or [None]
            for p_item in paragraphs:
                p_values = [None] if p_item is None else index.expand((act, unit, number, part), p_item)
                if p_values is None:
                    return None
                for paragraph in p_values:
                    for pt_item in points:
                        pt_values = [None] if pt_item is None else index.expand((act, unit, number, part, paragraph), pt_item)
                        if pt_values is None:
                            return None
                        for point in pt_values:
                            key = (act, unit, number, part, paragraph, point)
                            if key not in index.units:
                                return None
                            targets.append(dict(zip(("act", "unit", "number", "part", "paragraph", "point"), key)))
    return targets


def column_acts(block: dict) -> list[str] | None:
    """The act of each column of a correlation table, from its header row.

    NIS2 Annex III maps "Directive (EU) 2016/1148 | This Directive". A
    reference in the left column points into the old directive.
    """
    header = block["text"].split("\n")[0].split(" | ")
    acts = []
    for cell in header:
        if m := ACT_MENTION.search(cell):
            acts.append(CORPUS_NUMBERS.get(m.group("number"), "outside"))
        elif re.match(r"^This (Regulation|Directive)$", cell.strip()):
            acts.append(block["act"])
        else:
            return None
    return acts


def find_refs(block: dict, index: Index) -> list[dict]:
    """All references in one block, resolved."""
    # The act a reference points into when it names none: the block's own
    # act, the amended act in an amending article, or the act of the table
    # column it sits in.
    default = block["act"]
    if block["unit"] == "article" and (m := AMENDS.match(block["title"] or "")):
        default = CORPUS_NUMBERS.get(m.group("number"), "outside")
    pieces = [(block["text"], default)]
    if block["kind"] == "table" and (acts := column_acts(block)):
        rows = [row.split(" | ") for row in block["text"].split("\n")[1:]]
        pieces = [(cell, act) for row in rows for cell, act in zip(row, acts)]

    records = []
    for text, default in pieces:
        records += find_refs_in(text, default, block, index)
    return records


def find_refs_in(text: str, default: str, block: dict, index: Index) -> list[dict]:
    mentions = [(m.start(), m.group("kind"), m.group("number")) for m in ACT_MENTION.finditer(text)]
    records = []
    for m in REFERENCE.finditer(text):
        groups = [g for g in read_chain(m.group("chain")) if any(g.values())]
        if not groups:
            continue  # "this Article" or "the first subparagraph" alone
        record = {"seq": block["seq"], "source": block["cite"], "text": m.group().strip(" ,"), "status": "", "targets": []}
        act = find_act(m, block, mentions, default)
        if block["quoted"]:
            record["status"] = "in_quote"
        elif act == "outside":
            record["status"] = "outside_corpus"
        elif act == "unknown":
            record["status"] = "unresolved"
        else:
            # Every group must resolve, or the reference as a whole does not.
            resolved = [resolve(group, act, block, index) for group in groups]
            if all(resolved):
                record["status"] = "resolved"
                record["targets"] = [t for targets in resolved for t in targets]
            else:
                record["status"] = "unresolved"
        records.append(record)
    return records


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    acts = [act for act, _, _ in ACTS.values()]
    blocks = {act: [json.loads(line) for line in open(UNITS_DIR / f"{act}.jsonl")] for act in acts}
    index = Index([b for act in acts for b in blocks[act]])

    problems = []
    for act in acts:
        refs = [r for b in blocks[act] for r in find_refs(b, index)]
        with open(OUT_DIR / f"{act}.jsonl", "w") as f:
            for r in refs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{act}: {len(refs)} references, {dict(Counter(r['status'] for r in refs))}")
        # Every resolved target must exist. resolve() only builds existing
        # targets, so a failure here is a bug in this module.
        for r in refs:
            for t in r["targets"]:
                key = (t["act"], t["chapter"], t["section"]) if "chapter" in t else tuple(t.values())
                if key not in (index.chapters if "chapter" in t else index.units):
                    problems.append(f"{r['source']}: target {t} does not exist")

    for problem in problems:
        print("PROBLEM", problem)
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
