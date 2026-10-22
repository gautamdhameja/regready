"""Chunk rules, tested on small hand-made blocks."""

from regready.chunk import build


def block(seq, text, paragraph=None, point=None, number="5", kind="text", title="Prohibited AI practices"):
    return {"seq": seq, "act": "ai_act", "unit": "article", "number": number, "part": None,
            "paragraph": paragraph, "point": point, "kind": kind, "text": text, "title": title,
            "chapter": "II", "section": None, "version_date": "2026-07-27",
            "cite": f"ai_act:article:{number}::{paragraph or ''}:{point or ''}"}


def texts(blocks):
    return {c["cite"]: c["text"] for c in build(blocks)}


def test_title_blocks_are_not_chunks():
    chunks = build([block(0, "Prohibited AI practices", kind="title"), block(1, "Intro.", paragraph="1")])
    assert [c["cite"] for c in chunks] == ["ai_act:article:5::1:"]


def test_header_names_act_citation_and_title():
    assert texts([block(1, "Intro.", paragraph="1")])["ai_act:article:5::1:"].split("\n")[0] == (
        "AI Act, Article 5(1), Prohibited AI practices")


def test_point_carries_the_lead_in():
    chunks = texts([block(1, "The following shall be prohibited:", paragraph="1"),
                    block(2, "the use of emotion recognition;", paragraph="1", point="f")])
    assert chunks["ai_act:article:5::1:f"].split("\n")[1:] == ["The following shall be prohibited:", "the use of emotion recognition;"]


def test_second_list_uses_its_own_lead_in():
    # Article 43(1): a second lead-in starts a second list of points.
    chunks = build([block(1, "First lead-in:", paragraph="1"), block(2, "first a;", paragraph="1", point="a"),
                    block(3, "Second lead-in:", paragraph="1"), block(4, "second a;", paragraph="1", point="a")])
    assert chunks[-1]["text"].split("\n")[1] == "Second lead-in:"


def test_sub_point_carries_its_point():
    # Article 113, point (c)(i).
    chunks = build([block(1, "However:", number="113"), block(2, "Chapter III shall apply from:", number="113", point="c"),
                    block(3, "(i) 2 December 2027;", number="113", point="c")])
    assert chunks[-1]["text"].split("\n")[1:] == ["However:", "Chapter III shall apply from:", "(i) 2 December 2027;"]


def test_parents_fall_back_to_the_next_larger_unit():
    [chunk] = build([block(1, "Text of an article without paragraphs.")])
    assert chunk["parents"] == {"point": "ai_act:article:5:::", "paragraph": "ai_act:article:5:::", "article": "ai_act:article:5:::"}
