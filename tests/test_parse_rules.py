"""Parser rules, tested on small hand-made inputs.

Each test feeds a few cleaned items through parse() and checks where the
text ends up. No corpus data is needed.
"""

from regready.parse import parse


def item(text, marker="", label="list_item", page=1):
    return {"label": label, "text": text, "marker": marker, "page": page}


def consolidated(*body):
    """Parse items as the body of a consolidated text, which has no
    drafting formulas."""
    records, problems = parse([item("Article 1", label="section_header"), *body], "gdpr", "2016-05-04", True)
    assert problems == []
    return records


def cites(records):
    return [(r["paragraph"], r["point"], r["text"]) for r in records if r["kind"] == "text"]


def test_first_unmarked_line_after_heading_is_the_title():
    records = consolidated(item("Subject matter", label="section_header"), item("This Regulation applies.", label="text"))
    assert records[0]["kind"] == "title"
    assert records[1]["title"] == "Subject matter"


def test_paragraphs_and_points():
    records = consolidated(
        item("Title", label="section_header"),
        item("The following shall be prohibited:", marker="1."),
        item("(a) first practice;"),
        item("(ba) inserted practice;"),
    )
    assert cites(records) == [
        ("1", None, "The following shall be prohibited:"),
        ("1", "a", "first practice;"),
        ("1", "ba", "inserted practice;"),
    ]


def test_numbered_items_are_paragraphs():
    # Numbered definitions, such as GDPR Article 4(11).
    records = consolidated(item("Title", label="section_header"), item("'consent' means ...", marker="(11)"))
    assert cites(records) == [("11", None, "'consent' means ...")]


def test_text_after_points_returns_to_the_paragraph():
    # GDPR Article 6(1): "Point (f) of the first subparagraph shall not apply ..."
    records = consolidated(
        item("Title", label="section_header"),
        item("Processing shall be lawful only if:", marker="1."),
        item("(a) consent;"),
        item("Point (a) shall not apply to ...", label="text"),
    )
    assert cites(records)[-1] == ("1", None, "Point (a) shall not apply to ...")


def test_i_after_h_is_a_letter():
    records = consolidated(item("Title", label="section_header"), item("Measures:", marker="2."), item("(h) cryptography;"), item("(i) access control;"))
    assert cites(records)[-1] == ("2", "i", "access control;")


def test_i_followed_by_ii_is_a_sub_point():
    records = consolidated(
        item("Title", label="section_header"),
        item("Measures:", marker="2."),
        item("(h) the following:"),
        item("(i) first sub-point;"),
        item("(ii) second sub-point;"),
    )
    # Both sub-points stay with point (h) and keep their marker in the text.
    assert cites(records)[-2:] == [("2", "h", "(i) first sub-point;"), ("2", "h", "(ii) second sub-point;")]


def test_quoted_text_is_not_structure():
    # Amending articles quote replacement text with its own markers.
    records = consolidated(
        item("Amendments", label="section_header"),
        item("Article 26 is amended as follows:", marker="(1)"),
        item("(a) paragraph 3 is replaced by the following:"),
        item("'3. A CCP shall ...", label="text"),
        item("(a) inside the quote;"),
        item("(b) also inside the quote.';"),
        item("(b) paragraph 6 is deleted;"),
    )
    assert [(p, pt) for p, pt, _ in cites(records)] == [("1", None), ("1", "a"), ("1", "a"), ("1", "a"), ("1", "a"), ("1", "b")]


def test_quote_can_close_on_a_footnote():
    records = consolidated(
        item("Amendments", label="section_header"),
        item("paragraph 1 is replaced by the following:", marker="(1)"),
        item("'1. A CSD shall ... (*).", label="text"),
        item("(*) Regulation (EU) 2022/2554 (OJ L 333, 27.12.2022, p. 1).';", label="footnote"),
        item("paragraph 2 is deleted;", marker="(2)"),
    )
    assert cites(records)[-1] == ("2", None, "paragraph 2 is deleted;")


def test_original_act_regions():
    items = [
        item("Having regard to the Treaty ...", label="text"),
        item("Whereas:", label="text"),
        item("First recital.", marker="(1)"),
        item("HAVE ADOPTED THIS REGULATION:", label="text"),
        item("Article 1", label="section_header"),
        item("Subject matter", label="section_header"),
        item("This Regulation applies.", label="text"),
        item("Done at Strasbourg, 14 December 2022.", label="text"),
        item("For the European Parliament", label="text"),
    ]
    records, problems = parse(items, "dora", "2022-12-27", False)
    assert problems == []
    assert [(r["unit"], r["number"], r["text"]) for r in records] == [
        ("recital", "1", "First recital."),
        ("article", "1", "Subject matter"),
        ("article", "1", "This Regulation applies."),
    ]


def test_missing_formula_is_a_problem():
    items = [
        item("Whereas:", label="text"),
        item("First recital.", marker="(1)"),
        item("HAVE ADOPTED THIS REGULATION:", label="text"),
        item("Article 1", label="section_header"),
        item("This Regulation applies.", label="text"),
    ]
    _, problems = parse(items, "dora", "2022-12-27", False)
    assert problems == ["dora: drafting formulas found ['whereas', 'enacting'], expected ['whereas', 'enacting', 'done_at']"]


def test_point_gap_is_a_problem():
    # Docling once dropped DORA Article 31(1), point (a). A list that starts
    # at (b) must be reported.
    from regready.parse import check
    records = consolidated(item("Title", label="section_header"), item("Intro:", marker="1."), item("(b) second point;"))
    problems, _ = check(records)
    assert problems == ["gdpr seq 2: point 'b' where 'a' was expected in ('article', '1', None, '1')"]


def test_chapter_before_first_article_in_consolidated_text():
    items = [item("CHAPTER I", label="section_header"), item("GENERAL PROVISIONS", label="section_header"),
             item("Article 1", label="section_header"), item("Subject matter", label="section_header")]
    records, problems = parse(items, "gdpr", "2016-05-04", True)
    assert problems == [] and records[0]["chapter"] == "I"
