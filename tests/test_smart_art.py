"""Unit-test suite for `power_pptx.smart_art` module."""

from __future__ import annotations

import io
import os

import pytest

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "test_files", "smart_art_org_chart.pptx")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prs():
    """Return a fresh Presentation loaded from the SmartArt fixture."""
    from power_pptx import Presentation

    return Presentation(FIXTURE_PATH)


# ---------------------------------------------------------------------------
# SmartArtCollection
# ---------------------------------------------------------------------------


class DescribeSmartArtCollection:
    def it_has_length_1_for_the_org_chart_fixture(self):
        prs = _make_prs()
        assert len(prs.slides[0].smart_art) == 1

    def it_is_empty_on_a_blank_slide(self):
        from power_pptx import Presentation

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        assert len(slide.smart_art) == 0

    def it_supports_iteration(self):
        prs = _make_prs()
        items = list(prs.slides[0].smart_art)
        assert len(items) == 1

    def it_raises_on_out_of_range_index(self):
        prs = _make_prs()
        with pytest.raises(IndexError):
            _ = prs.slides[0].smart_art[99]

    def it_returns_the_correct_repr(self):
        prs = _make_prs()
        r = repr(prs.slides[0].smart_art)
        assert "SmartArtCollection" in r
        assert "1" in r


# ---------------------------------------------------------------------------
# SmartArtShape.texts
# ---------------------------------------------------------------------------


class DescribeSmartArtShape_texts:
    def it_returns_the_initial_node_texts(self):
        prs = _make_prs()
        sa = prs.slides[0].smart_art[0]
        assert sa.texts == ["CEO", "CTO", "CFO"]

    def it_has_the_correct_shape_name(self):
        prs = _make_prs()
        sa = prs.slides[0].smart_art[0]
        assert sa.name == "SmartArt 1"


# ---------------------------------------------------------------------------
# SmartArtShape.set_text
# ---------------------------------------------------------------------------


class DescribeSmartArtShape_set_text:
    def it_replaces_all_node_texts(self):
        prs = _make_prs()
        sa = prs.slides[0].smart_art[0]
        sa.set_text(["Alice", "Bob", "Carol"])
        assert sa.texts == ["Alice", "Bob", "Carol"]

    def it_round_trips_through_save_and_reopen(self):
        from power_pptx import Presentation

        prs = _make_prs()
        prs.slides[0].smart_art[0].set_text(["Alice", "Bob", "Carol"])

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        prs2 = Presentation(buf)

        assert prs2.slides[0].smart_art[0].texts == ["Alice", "Bob", "Carol"]

    def it_raises_on_wrong_length_in_strict_mode(self):
        prs = _make_prs()
        sa = prs.slides[0].smart_art[0]
        with pytest.raises(ValueError, match="3 content node"):
            sa.set_text(["Only", "Two"])

    def it_silently_accepts_extra_values_when_strict_is_False(self):
        prs = _make_prs()
        sa = prs.slides[0].smart_art[0]
        # 5 values for 3 nodes — excess should be ignored
        sa.set_text(["A", "B", "C", "D", "E"], strict=False)
        assert sa.texts == ["A", "B", "C"]

    def it_accepts_fewer_values_when_strict_is_False(self):
        prs = _make_prs()
        sa = prs.slides[0].smart_art[0]
        sa.set_text(["X"], strict=False)
        # only first node changed; rest remain
        texts = sa.texts
        assert texts[0] == "X"
        assert texts[1] == "CTO"
        assert texts[2] == "CFO"

    def it_leaves_layout_colors_and_style_parts_unchanged(self):
        """The three non-data parts should be byte-for-byte identical after set_text."""

        prs = _make_prs()

        # Capture original sibling part bytes
        slide_part = prs.slides[0].part
        lo_part = slide_part.related_part("rId2")
        qs_part = slide_part.related_part("rId3")
        cs_part = slide_part.related_part("rId4")
        orig_lo = lo_part.blob
        orig_qs = qs_part.blob
        orig_cs = cs_part.blob

        # Mutate the data part
        prs.slides[0].smart_art[0].set_text(["X", "Y", "Z"])

        # Re-fetch the parts — should be unchanged
        assert slide_part.related_part("rId2").blob == orig_lo
        assert slide_part.related_part("rId3").blob == orig_qs
        assert slide_part.related_part("rId4").blob == orig_cs

    def it_fills_the_paragraph_of_a_node_still_showing_its_prompt(self):
        # A node nobody typed into has one empty paragraph and is flagged as a
        # placeholder. Its text belongs in that paragraph, ahead of the
        # end-of-paragraph properties, not in a second paragraph after it.
        from power_pptx.oxml.ns import qn

        prs = _make_prs()
        sa = prs.slides[0].smart_art[0]
        pt = _content_nodes(sa)[1]
        _make_prompt_node(pt)

        sa.set_text(["Alice", "Bob", "Carol"])

        paragraphs = pt.find(qn("dgm:t")).findall(qn("a:p"))
        assert len(paragraphs) == 1
        assert [child.tag for child in paragraphs[0]] == [qn("a:r"), qn("a:endParaRPr")]
        assert sa.texts == ["Alice", "Bob", "Carol"]
        # -- with text of its own the node is no longer a placeholder --
        assert pt.find(qn("dgm:prSet")).get("phldr") is None
        assert pt.find(qn("dgm:prSet")).get("phldrT") == "[Text]"

    def but_it_leaves_a_prompt_node_a_placeholder_when_given_no_text(self):
        from power_pptx.oxml.ns import qn

        prs = _make_prs()
        sa = prs.slides[0].smart_art[0]
        pt = _content_nodes(sa)[1]
        _make_prompt_node(pt)

        sa.set_text(["Alice", "", "Carol"])

        assert sa.texts == ["Alice", "", "Carol"]
        assert pt.find(qn("dgm:prSet")).get("phldr") == "1"

    def it_adds_the_text_body_of_a_node_without_one_ahead_of_its_extension_list(self):
        from lxml import etree

        from power_pptx.oxml.ns import qn

        prs = _make_prs()
        sa = prs.slides[0].smart_art[0]
        pt = _content_nodes(sa)[1]
        pt.remove(pt.find(qn("dgm:t")))
        etree.SubElement(pt, qn("dgm:extLst"))

        sa.set_text(["Alice", "Bob", "Carol"])

        assert [child.tag for child in pt] == [qn("dgm:t"), qn("dgm:extLst")]
        assert sa.texts == ["Alice", "Bob", "Carol"]

    def and_it_adds_it_last_in_a_node_without_an_extension_list(self):
        from power_pptx.oxml.ns import qn

        prs = _make_prs()
        sa = prs.slides[0].smart_art[0]
        pt = _content_nodes(sa)[1]
        pt.remove(pt.find(qn("dgm:t")))
        assert pt.find(qn("dgm:extLst")) is None
        tags_before = [child.tag for child in pt]

        sa.set_text(["Alice", "Bob", "Carol"])

        assert [child.tag for child in pt] == tags_before + [qn("dgm:t")]
        t_body = pt.find(qn("dgm:t"))
        assert [child.tag for child in t_body] == [qn("a:bodyPr"), qn("a:lstStyle"), qn("a:p")]
        assert sa.texts == ["Alice", "Bob", "Carol"]


# ---------------------------------------------------------------------------
# SmartArt as PowerPoint writes it
# ---------------------------------------------------------------------------


class DescribePowerPointAuthoredSmartArt:
    """SmartArt saved by PowerPoint itself, rather than the hand-built fixture above.

    PowerPoint leaves `type` off its content nodes (the schema default is
    "node") and keeps a drawing part caching the shapes the diagram was last
    laid out as, which is what a viewer displays.
    """

    def it_reads_the_texts_of_nodes_that_carry_no_type_attribute(self):
        sa = _powerpoint_smart_art()

        assert all(pt.get("type") is None for pt in _content_nodes(sa))
        assert sa.texts == ["shapes[5]", " ", " Smart Art"]

    def it_replaces_the_node_texts(self):
        sa = _powerpoint_smart_art()

        sa.set_text(["Plan", "Build", "Ship"])

        assert sa.texts == ["Plan", "Build", "Ship"]

    def it_still_checks_the_number_of_values_in_strict_mode(self):
        sa = _powerpoint_smart_art()

        with pytest.raises(ValueError, match="3 content node"):
            sa.set_text(["Only", "Two"])

    def it_replaces_the_text_in_the_cached_drawing_too(self):
        from power_pptx import Presentation

        prs = Presentation(POWERPOINT_FIXTURE_PATH)
        prs.slides[0].smart_art[0].set_text(["Plan", "Build", "Ship"])
        buf = io.BytesIO()
        prs.save(buf)

        reopened = Presentation(io.BytesIO(buf.getvalue())).slides[0].smart_art[0]

        assert reopened.texts == ["Plan", "Build", "Ship"]
        assert _cached_texts(reopened) == ["Plan", "Build", "Ship"]

    def it_keeps_the_formatting_of_the_cached_text(self):
        from power_pptx.oxml.ns import qn

        sa = _powerpoint_smart_art()
        before = [rPr.attrib for rPr in sa._cached_drawing.iter(qn("a:rPr"))]

        sa.set_text(["Plan", "Build", "Ship"])

        assert [rPr.attrib for rPr in sa._cached_drawing.iter(qn("a:rPr"))] == before

    def it_only_touches_the_cached_shapes_of_the_nodes_it_was_given(self):
        sa = _powerpoint_smart_art()

        sa.set_text(["Plan"], strict=False)

        assert sa.texts == ["Plan", " ", " Smart Art"]
        assert _cached_texts(sa) == ["Plan", " ", " Smart Art"]

    def it_gives_a_cached_shape_that_showed_no_text_a_run_of_its_own(self):
        # The cached shape of an empty node has a paragraph but no run. The
        # run it gets goes ahead of the end-of-paragraph properties and takes
        # over their settings, the font size the shape was laid out with.
        from power_pptx.oxml.ns import qn

        sa = _powerpoint_smart_art()
        drawing = sa._cached_drawing
        run = [t for t in drawing.iter(qn("a:t")) if t.text == " "][0].getparent()
        paragraph = run.getparent()
        paragraph.remove(run)
        sa._save_cached_drawing(drawing)
        assert _cached_texts(sa) == ["shapes[5]", " Smart Art"]

        sa.set_text(["Plan", "Build", "Ship"])

        assert _cached_texts(sa) == ["Plan", "Build", "Ship"]
        texts = [t for t in sa._cached_drawing.iter(qn("a:t")) if t.text == "Build"]
        new_run = texts[0].getparent()
        end = new_run.getnext()
        assert end.tag == qn("a:endParaRPr")
        assert new_run.find(qn("a:rPr")).attrib == end.attrib
        assert end.get("sz") is not None


POWERPOINT_FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "features", "steps", "test_files", "shp-shapes.pptx"
)


def _powerpoint_smart_art():
    from power_pptx import Presentation

    return Presentation(POWERPOINT_FIXTURE_PATH).slides[0].smart_art[0]


def _content_nodes(sa):
    """The `dgm:pt` elements of `sa` that hold its text, found without the code under test."""
    from power_pptx.oxml.ns import qn

    pt_lst = sa._data_element.find(qn("dgm:ptLst"))
    return [pt for pt in pt_lst.findall(qn("dgm:pt")) if pt.get("type") in (None, "node", "asst")]


def _make_prompt_node(pt) -> None:
    """Turn `pt` into a node nobody has typed into yet, as PowerPoint writes one."""
    from lxml import etree

    from power_pptx.oxml.ns import qn

    prSet = etree.Element(qn("dgm:prSet"), phldrT="[Text]", phldr="1")
    pt.insert(0, prSet)
    t = pt.find(qn("dgm:t"))
    for p in t.findall(qn("a:p")):
        t.remove(p)
    p = etree.SubElement(t, qn("a:p"))
    etree.SubElement(p, qn("a:endParaRPr"), lang="en-US")


def _cached_texts(sa) -> list[str]:
    """Text of each shape in the cached drawing of `sa` that displays any."""
    from power_pptx.oxml.ns import qn

    dsp = "{http://schemas.microsoft.com/office/drawing/2008/diagram}"
    texts = []
    for sp in sa._cached_drawing.iter(dsp + "sp"):
        runs = [t.text or "" for t in sp.iter(qn("a:t"))]
        if runs:
            texts.append("".join(runs))
    return texts
