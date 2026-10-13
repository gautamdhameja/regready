"""Parse cleaned items into legal units.

Input:  data/cleaned/<file>.jsonl, one cleaned item per line (see clean.py).
Output: data/units/<act>.jsonl, one text block per line.

Record format
-------------
Each record is one text block. A legal unit, such as a paragraph, can have
several blocks: for example, the lead-in of a paragraph and a subparagraph
that follows its points. Rebuild a unit by collecting its blocks in `seq`
order.

  seq           unique position of the block in the act; the record key
  cite          act:unit:number:part:paragraph:point, with empty slots kept,
                such as "ai_act:article:5::1:f" or "ai_act:annex:VIII:A:1:".
                All blocks of the same unit share it.
  act           ai_act, gdpr, dora, nis2 or data_act
  unit          article, recital or annex
  number        unit number as a string, such as "5", "4a" or "XIV"
  part          annex section, such as "A", or None
  paragraph     paragraph number as a string, or None
  point         point letter or number as a string, or None
  kind          "title" for an article or annex title, "table" for a table,
                "text" otherwise
  text          block text, without its marker
  title         article or annex title, copied to every block in the unit
  chapter       chapter number, such as "II", or None
  section       section number within the chapter, or None
  pages         PDF pages the block comes from
  version_date  version date of the act text, from the corpus record

The location fields follow the gold citation rules in eval/README.md.
Find a unit's blocks by comparing these fields, not by matching the start
of `cite`: "ai_act:article:5::1" is a prefix of "ai_act:article:5::1a".

Mapping rules
-------------
- Numbered paragraphs "1." and numbered items "(1)" are paragraphs. This
  covers numbered definitions, such as GDPR Article 4(11).
- Lettered items "(a)" and "(ba)" are points.
- In annexes, a numbered point "4." is the paragraph and "(a)" the point.
  A section that restarts the numbering, such as "Section A", is the part.
- Text without a marker belongs to the unit it follows. This covers
  unnumbered paragraphs, subparagraphs, sub-points "(i)" and dash items.
- Text that starts with a quote mark never starts a new unit. Amending
  articles quote replacement text such as "'3. A CCP shall ...'".
- Annex tables are one block of the annex.
- Footnotes, the title, citations ("Having regard to ...") and closing
  formulas ("Done at Brussels ...") are dropped. Only recitals, articles
  and annexes become units.

Region boundaries come from the drafting formulas that EU drafting rules
require in every act: "Whereas:", "HAVE ADOPTED THIS REGULATION:" and
"Done at ...". See FORMULAS below.

The parser checks its own output and exits with an error if a drafting
formula is missing or out of order, a quote never closes, or article or
annex numbers, paragraphs or points are out of order. A wrong structure
then fails loudly instead of producing wrong citations.

Run: uv run python -m regready.parse
"""

import json
import re
import sys
from pathlib import Path

IN_DIR = Path("data/cleaned")
OUT_DIR = Path("data/units")

# Corpus record from corpus.md:
# cleaned file stem -> (act, version date, consolidated text or not).
ACTS = {
    "CELEX_02024R1689-20260727_EN_TXT": ("ai_act", "2026-07-27", True),
    "CELEX_02016R0679-20160504_EN_TXT": ("gdpr", "2016-05-04", True),
    "CELEX_32022R2554_EN_TXT": ("dora", "2022-12-27", False),
    "CELEX_32022L2555_EN_TXT": ("nis2", "2022-12-27", False),
    "OJ_L_202302854_EN_TXT": ("data_act", "2023-12-22", False),
}

# Drafting formulas that every act must contain, in this order. They mark
# the boundaries between the parts of an act. Source: Joint Handbook for
# acts under the ordinary legislative procedure, Annex II and points Q,
# S.1, S.2 and U. Consolidated texts leave all three out.
#
#   name -> (pattern, region that starts after it)
FORMULAS = {
    "whereas": (re.compile(r"^Whereas:$"), "recitals"),  # point Q
    "enacting": (re.compile(r"^HAVE ADOPTED THIS (REGULATION|DIRECTIVE):$"), "articles"),  # S.1, S.2
    "done_at": (re.compile(r"^Done at [A-Z][a-z]+, \d{1,2} [A-Z][a-z]+ \d{4}\.$"), "end"),  # point U
}

# Headings. Docling sometimes merges an article title into its heading:
# "Article 15 Accuracy, robustness and cybersecurity". The title must start
# with a capital, so running text such as "Article 6 shall apply" is not a
# heading.
ARTICLE = re.compile(r"^Article (\d+[a-z]?)(?: ([A-Z‘'].*))?$")
ANNEX = re.compile(r"^ANNEX ([IVXL]+)(?: (.+))?$")
CHAPTER = re.compile(r"^CHAPTER ([IVXL]+)\b")
# Section headings vary: "SECTION 1" (AI Act), letter-spaced "S e c t i o n 1"
# (GDPR) and "Sect ion I I" (DORA). Spaces inside the number are removed.
# A heading is the number alone or followed by a capitalised title, so text
# such as "Section II is amended as follows:" is not a heading.
SECTION = re.compile(r"^(?i:S\s*E\s*C\s*T\s*I\s*O\s*N)\s+(\d+|(?:[IVXL]\s?)+)(?:\s+[A-Z][^:;]*)?$")
ANNEX_PART = re.compile(r"^(?:Section|SECTION|Part|PART) ([A-Z0-9]+)\b")

# Markers. Docling puts some markers in the item's `marker` field and leaves
# others at the start of the text.
TEXT_MARKER = re.compile(r"^(\d+[a-z]?\.|\(\d+[a-z]?\)|\([a-z]{1,4}\))\s+")
PARAGRAPH = re.compile(r"^(\d+[a-z]?)\.$")  # 1.  1a.
NUMBERED = re.compile(r"^\((\d+[a-z]?)\)$")  # (1)  (14a)
LETTERED = re.compile(r"^\(([a-z]{1,3})\)$")  # (a)  (ba)
ROMAN = re.compile(r"^[ivx]+$")

QUOTES = "'‘’\"“"
QUOTE_END = re.compile(r"['’\"”]\s*[;.,]?\s*$")


def split_marker(item: dict) -> tuple[str, str]:
    """Return the item's marker, such as "1." or "(a)", and its text."""
    marker = item["marker"].strip()
    if marker:
        return marker, item["text"]
    m = TEXT_MARKER.match(item["text"])
    if m:
        return m.group(1), item["text"][m.end():]
    return "", item["text"]


def number_key(number: str) -> tuple[int, str]:
    """Sort key for "4", "4a" and roman numerals such as "XIV"."""
    if number.isdigit() or number[:-1].isdigit():
        digits = number.rstrip("abcdefghijklmnopqrstuvwxyz")
        return int(digits), number[len(digits):]
    values = {"I": 1, "V": 5, "X": 10, "L": 50}
    total = 0
    for char, following in zip(number, number[1:] + " "):
        value = values[char]
        total += -value if values.get(following, 0) > value else value
    return total, ""


class Parser:
    """Walks the cleaned items of one act and emits text blocks.

    The parser keeps the current position in the law (unit, number, part,
    paragraph, point) and updates it as headings and markers appear. Every
    text item becomes a block that cites the current position.
    """

    def __init__(self, act: str, version_date: str):
        self.act = act
        self.version_date = version_date
        self.records: list[dict] = []
        self.problems: list[str] = []
        self.formulas_found: list[str] = []
        # Original act:      front -> recitals -> articles -> end -> annexes
        # Consolidated text: front -> articles -> annexes
        self.region = "front"
        self.chapter = self.section = None
        self.unit = self.number = self.part = self.paragraph = self.point = None
        self.title = None
        self.expect_title = False
        self.in_quote = False

    def emit(self, text: str, page: int, kind: str = "text") -> None:
        location = (self.act, self.unit, self.number, self.part, self.paragraph, self.point)
        self.records.append({
            "seq": len(self.records),
            "cite": ":".join(value or "" for value in location),
            "act": self.act,
            "unit": self.unit,
            "number": self.number,
            "part": self.part,
            "paragraph": self.paragraph,
            "point": self.point,
            "kind": kind,
            "text": text,
            "title": self.title,
            "chapter": self.chapter,
            "section": self.section,
            "pages": [page],
            "version_date": self.version_date,
        })

    def start_unit(self, unit: str, number: str, title: str | None, page: int) -> None:
        self.unit, self.number = unit, number
        self.part = self.paragraph = self.point = None
        self.title = title
        self.expect_title = title is None
        if title:
            self.emit(title, page, "title")

    def is_next_article(self, number: str) -> bool:
        """True if number follows the current article, such as 61 after 60."""
        if self.unit != "article":
            return False
        current, _ = number_key(self.number)
        new, _ = number_key(number)
        return new in (current, current + 1) and number_key(number) > number_key(self.number)

    def feed(self, item: dict, next_marker: str) -> None:
        text, page = item["text"], item["page"]
        if item["label"] == "footnote":
            # Quoted text can end with a footnote, so the closing quote mark
            # sits on the footnote: "... (OJ L 333, 27.12.2022, p. 1).';"
            if self.in_quote and QUOTE_END.search(text):
                self.in_quote = False
            return

        # Quoted text in amending articles can span several items and hold
        # its own headings and markers. It all belongs to the current unit.
        if self.in_quote:
            m = ARTICLE.match(text)
            if not (m and self.is_next_article(m.group(1))):
                self.emit(text, page)
                if QUOTE_END.search(text):
                    self.in_quote = False
                return
            # The quote never closed, so everything since it opened may be
            # filed under the wrong unit. Recover, but report it.
            self.problems.append(f"{self.act} article {self.number}: quote not closed before Article {m.group(1)}")
            self.in_quote = False

        # Region boundaries. A drafting formula moves to the next region.
        # Whether each one was found, in order, is checked in parse().
        for name, (pattern, region) in FORMULAS.items():
            if pattern.match(text):
                self.formulas_found.append(name)
                self.region, self.unit = region, None
                return
        # A consolidated text has no formulas, so its first article heading
        # ends the front matter.
        if self.region in ("front", "articles") and (m := ARTICLE.match(text)):
            self.region = "articles"
            self.start_unit("article", m.group(1), m.group(2), page)
            return
        if self.region in ("articles", "end", "annexes") and (m := ANNEX.match(text)):
            self.region = "annexes"
            self.chapter = self.section = None
            self.start_unit("annex", m.group(1), m.group(2), page)
            return
        if self.region in ("front", "end"):
            return

        if self.region == "recitals":
            self.feed_recital(item)
            return

        # Chapter and section headings close the current article. Their
        # titles, which follow, are dropped until the next article heading.
        if self.region == "articles" and (m := CHAPTER.match(text)):
            self.chapter, self.section, self.unit = m.group(1), None, None
            return
        # The length limit keeps running text such as "Section 2 shall apply"
        # from being read as a heading.
        if self.region == "articles" and len(text) < 100 and (m := SECTION.match(text)):
            self.section, self.unit = m.group(1).replace(" ", "").upper(), None
            return
        if self.unit is None:
            return

        self.feed_body(item, next_marker)

    def feed_recital(self, item: dict) -> None:
        """A recital is a numbered "(n)" item between "Whereas:" and the
        enacting formula. Unnumbered text continues the current recital."""
        marker, text = split_marker(item)
        if m := NUMBERED.match(marker):
            self.unit, self.number = "recital", m.group(1)
            self.part = self.paragraph = self.point = self.title = None
            self.emit(text, item["page"])
        elif self.unit == "recital":
            self.emit(item["text"], item["page"])

    def feed_body(self, item: dict, next_marker: str) -> None:
        """Handle one item inside an article or annex."""
        text, page = item["text"], item["page"]

        if item["label"] == "table":
            self.emit(text, page, "table")
            return

        marker, body = split_marker(item)

        # The first unmarked item after a heading is the title.
        if self.expect_title:
            self.expect_title = False
            if not marker and text[:1] not in QUOTES and len(text) < 250:
                self.title = text
                self.emit(text, page, "title")
                return

        if self.unit == "annex" and (m := ANNEX_PART.match(text)):
            self.part, self.paragraph, self.point = m.group(1), None, None
            self.emit(text, page)
            return

        # An item that opens with a quote mark is quoted replacement text.
        if not item["marker"].strip() and text[:1] in QUOTES:
            self.emit(text, page)
            self.in_quote = not QUOTE_END.search(text)
            return

        if (m := PARAGRAPH.match(marker)) or (m := NUMBERED.match(marker)):
            self.paragraph, self.point = m.group(1), None
            self.emit(body, page)
            return

        if (m := LETTERED.match(marker)) and not self.is_sub_point(m.group(1), next_marker):
            self.point = m.group(1)
            self.emit(body, page)
            return

        # No structural marker: a continuation block of the current unit.
        # Unmarked running text after a list of points returns to the
        # paragraph, such as "Point (f) of the first subparagraph shall not
        # apply ...". Sub-points (i) and dash items stay with their point.
        if item["label"] == "text" and not marker:
            self.point = None
        self.emit(f"{marker} {body}".strip(), page)

    def is_sub_point(self, letter: str, next_marker: str) -> bool:
        """Tell a roman sub-point "(i)" from the ninth lettered point "(i)".

        A roman-looking marker is a lettered point only if it follows the
        current point in the alphabet, as "(i)" follows "(h)", and the next
        marker is not "(ii)".
        """
        if not ROMAN.match(letter):
            return False
        follows = (
            self.point is not None
            and len(self.point) == 1
            and len(letter) == 1
            and ord(letter) == ord(self.point) + 1
        )
        return not follows or next_marker == "(ii)"


def parse(items: list[dict], act: str, version_date: str, consolidated: bool) -> tuple[list[dict], list[str]]:
    """Return the text blocks of one act and any problems found on the way."""
    parser = Parser(act, version_date)
    markers = [split_marker(item)[0] for item in items]
    for i, item in enumerate(items):
        next_marker = next((m for m in markers[i + 1:] if m), "")
        parser.feed(item, next_marker)
    if parser.in_quote:
        parser.problems.append(f"{act}: quote still open at the end of the document")

    # An original act must contain every drafting formula once, in order.
    # A consolidated text must contain none. Anything else means a region
    # boundary was missed and the units cannot be trusted.
    expected = [] if consolidated else list(FORMULAS)
    if parser.formulas_found != expected:
        parser.problems.append(f"{act}: drafting formulas found {parser.formulas_found}, expected {expected}")
    return parser.records, parser.problems


def check(records: list[dict]) -> tuple[list[str], list[str]]:
    """Return structure problems and notes.

    A problem is a number that repeats or goes backwards. A note is a point
    list that restarts after an unmarked subparagraph, as in AI Act
    Article 43(1). The law does this, but the two lists then share cites.
    """
    problems, notes = [], []
    seen_units: dict[str, list] = {}
    seen_paragraphs: dict[tuple, list] = {}
    seen_points: dict[tuple, list] = {}
    last_point: dict[tuple, str | None] = {}
    for r in records:
        unit_key, paragraph_key = (r["unit"], r["number"], r["part"]), (r["unit"], r["number"], r["part"], r["paragraph"])
        if r["paragraph"] is not None:
            if r["point"] == "a" and last_point.get(paragraph_key, "a") is None and seen_points.get(paragraph_key):
                notes.append(f"{r['cite']} (seq {r['seq']}): points restart after a subparagraph")
                seen_points[paragraph_key] = []
            last_point[paragraph_key] = r["point"]
        steps = [
            (seen_units, r["unit"], r["number"], number_key),
            (seen_paragraphs, unit_key, r["paragraph"], number_key),
            (seen_points, paragraph_key, r["point"], lambda p: p),
        ]
        for seen, scope, value, key in steps:
            if value is None:
                continue
            values = seen.setdefault(scope, [])
            if values and values[-1] == value:
                continue
            if value in values or (values and key(value) < key(values[-1])):
                problems.append(f"{r['act']} seq {r['seq']}: {value!r} after {values[-1]!r} in {scope}")
            values.append(value)
    return problems, notes


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    problems = []
    for stem, (act, version_date, consolidated) in ACTS.items():
        items = [json.loads(line) for line in open(IN_DIR / f"{stem}.jsonl")]
        records, parse_problems = parse(items, act, version_date, consolidated)
        problems += parse_problems
        with open(OUT_DIR / f"{act}.jsonl", "w") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        counts = {u: len({r["number"] for r in records if r["unit"] == u}) for u in ("recital", "article", "annex")}
        print(f"{act}: {len(records)} blocks, {counts}")
        act_problems, act_notes = check(records)
        problems += act_problems
        for note in act_notes:
            print("  NOTE", note)

    for problem in problems:
        print("PROBLEM", problem)
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
