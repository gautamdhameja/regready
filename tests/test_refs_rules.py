"""Cross-reference rules, tested on small hand-made blocks.

A tiny index stands in for the corpus, so no data is needed.
"""

from regready.refs import Index, find_refs, read_chain


def block(text, act="dora", unit="article", number="5", paragraph=None, point=None, **extra):
    fields = {"act": act, "unit": unit, "number": number, "part": None, "paragraph": paragraph,
              "point": point, "chapter": "II", "section": None, "title": "Title", "kind": "text", "quoted": False}
    fields.update(extra)
    location = (fields["act"], unit, number, "", paragraph or "", point or "")
    return {"seq": 0, "cite": ":".join(location), "text": text, **fields}


# DORA articles 5 to 7 with paragraphs and points; NIS2 article 4.
INDEX = Index([
    block("", number="5", paragraph="1"),
    block("", number="5", paragraph="2", point="a"),
    block("", number="5", paragraph="2", point="b"),
    block("", number="5", paragraph="2", point="ba"),
    block("", number="5", paragraph="2", point="c"),
    block("", number="6", paragraph="1"),
    block("", number="7", paragraph="1"),
    block("", act="nis2", number="4", paragraph="1"),
])


def targets(text, **context):
    [ref] = find_refs(block(text, **context), INDEX)
    return ref["status"], [(t["act"], t["number"], t["paragraph"], t["point"]) for t in ref["targets"]]


def test_article_with_inline_paragraph():
    assert targets("in accordance with Article 6(1)") == ("resolved", [("dora", "6", "1", None)])


def test_range_includes_inserted_point():
    assert targets("Article 5(2), points (b) to (c)") == (
        "resolved", [("dora", "5", "2", "b"), ("dora", "5", "2", "ba"), ("dora", "5", "2", "c")])


def test_relative_paragraph_and_point():
    # "paragraph 2, point (a)" in Article 5 means Article 5(2)(a).
    assert targets("referred to in paragraph 2, point (a)", number="5") == ("resolved", [("dora", "5", "2", "a")])


def test_bare_point_is_in_the_same_paragraph():
    assert targets("the condition in point (b)", number="5", paragraph="2") == ("resolved", [("dora", "5", "2", "b")])


def test_parts_after_a_comma_belong_to_the_unit_before():
    # Point (a) belongs to Article 5(2) only, not to Article 6.
    assert targets("Article 5(2), point (a), Article 6") == (
        "resolved", [("dora", "5", "2", "a"), ("dora", "6", None, None)])


def test_parts_before_of_belong_to_the_unit_after():
    groups = read_chain("points 1 to 3 of Section C of Annex VIII")
    assert len(groups) == 1 and groups[0]["annex"] and groups[0]["section"] and groups[0]["point"]


def test_other_corpus_act_by_number():
    assert targets("Article 4 of Directive (EU) 2022/2555") == ("resolved", [("nis2", "4", None, None)])


def test_that_directive_is_the_last_one_named():
    [first, second] = find_refs(block("Article 4 of Directive (EU) 2022/2555 and Article 4 of that Directive"), INDEX)
    assert second["status"] == "resolved" and second["targets"][0]["act"] == "nis2"


def test_act_outside_the_corpus():
    assert targets("Article 2 of Directive 2013/34/EU") == ("outside_corpus", [])


def test_missing_target_is_unresolved():
    assert targets("Article 99") == ("unresolved", [])


def test_this_article_alone_makes_no_record():
    assert find_refs(block("as provided for in this Article"), INDEX) == []


def test_amending_article_points_into_the_amended_act():
    assert targets("Article 26 is amended as follows:", title="Amendments to Regulation (EU) No 648/2012") == ("outside_corpus", [])


def test_quoted_text_is_in_quote():
    assert targets("'3. As referred to in Article 6(1) ...", quoted=True) == ("in_quote", [])


def test_correlation_table_columns():
    table = "Directive (EU) 2016/1148 | This Directive\nArticle 7(1) | Article 6(1)"
    refs = find_refs(block(table, kind="table"), INDEX)
    assert [r["status"] for r in refs] == ["outside_corpus", "resolved"]
