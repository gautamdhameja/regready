"""Cleanup rules, tested on a minimal docling document."""

from regready.clean import clean


def doc(*texts):
    """A docling JSON document with one body item per (label, text, marker)."""
    items = [{"label": label, "text": text, "marker": marker, "content_layer": "body",
              "prov": [{"page_no": 1}], "children": []} for label, text, marker in texts]
    return {"body": {"children": [{"$ref": f"#/texts/{i}"} for i in range(len(items))]}, "texts": items}


def test_footnote_label_without_marker_is_body_text():
    # Docling labelled DORA Article 31(1), point (a), as a footnote.
    items, _ = clean(doc(("footnote", "(a) designate the ICT third-party service providers", "")))
    assert items[0]["label"] == "list_item"


def test_spaced_marker_is_a_footnote():
    items, _ = clean(doc(("text", "( 1 ) OJ C 233, 16.6.2022, p. 22.", "")))
    assert items[0]["label"] == "footnote"


def test_consolidation_markers_and_soft_hyphens_are_removed():
    items, _ = clean(doc(("text", "▼M1 dispropor­ tionate", "")))
    assert items[0]["text"] == "disproportionate"
