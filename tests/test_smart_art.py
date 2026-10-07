"""Unit-test suite for `power_pptx.smart_art` module."""

from __future__ import annotations

import io
import os
import zipfile

import pytest
from lxml import etree

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "test_files", "smart_art_org_chart.pptx")

# -- Decks authored in PowerPoint itself. Their SmartArt data model omits `type` on ordinary
# -- content nodes (the schema default is "node") and carries a `dsp:drawing` cache part.
FEATURE_FILES = os.path.join(os.path.dirname(__file__), "..", "features", "steps", "test_files")
SHAPES_DECK = os.path.join(FEATURE_FILES, "shp-shapes.pptx")
PLACEHOLDERS_DECK = os.path.join(FEATURE_FILES, "ph-populated-placeholders.pptx")

_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_DGM = "{http://schemas.openxmlformats.org/drawingml/2006/diagram}"
_DSP = "{http://schemas.microsoft.com/office/drawing/2008/diagram}"
_NSDECLS = (
    'xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:dsp="http://schemas.microsoft.com/office/drawing/2008/diagram"'
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prs():
    """Return a fresh Presentation loaded from the SmartArt fixture."""
    from power_pptx import Presentation

    return Presentation(FIXTURE_PATH)


def _open_variant(data_xml, drawing_xml=None):
    """Open the hand-built fixture with its diagram data (and optionally a drawing cache) swapped.

    `data_xml` replaces `ppt/diagrams/data1.xml`. When `drawing_xml` is given it is added as
    `ppt/diagrams/drawing1.xml`, related from the slide as `rId6` (which is what the
    `dsp:dataModelExt/@relId` in `_data_xml()` points at), like PowerPoint does.
    """
    from power_pptx import Presentation

    drawing_rel = (
        '<Relationship Id="rId6" '
        'Type="http://schemas.microsoft.com/office/2007/relationships/diagramDrawing" '
        'Target="../diagrams/drawing1.xml"/>'
    )
    drawing_override = (
        '<Override PartName="/ppt/diagrams/drawing1.xml" '
        'ContentType="application/vnd.ms-office.drawingml.diagramDrawing+xml"/>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(FIXTURE_PATH) as src, zipfile.ZipFile(buf, "w") as dst:
        for item in src.infolist():
            blob = src.read(item.filename)
            if item.filename == "ppt/diagrams/data1.xml":
                blob = data_xml.encode("utf-8")
            elif drawing_xml is not None and item.filename == "ppt/slides/_rels/slide1.xml.rels":
                blob = blob.decode("utf-8").replace(
                    "</Relationships>", drawing_rel + "</Relationships>"
                )
                blob = blob.encode("utf-8")
            elif drawing_xml is not None and item.filename == "[Content_Types].xml":
                blob = blob.decode("utf-8").replace("</Types>", drawing_override + "</Types>")
                blob = blob.encode("utf-8")
            dst.writestr(item, blob)
        if drawing_xml is not None:
            dst.writestr("ppt/diagrams/drawing1.xml", drawing_xml)
    buf.seek(0)
    return Presentation(buf)


def _para(text=None, *, rpr='lang="en-US"'):
    """A PowerPoint-style `a:p`; without `text` it is the empty "[Text]" placeholder paragraph."""
    run = f"<a:r><a:rPr {rpr}/><a:t>{text}</a:t></a:r>" if text else ""
    return f"<a:p>{run}<a:endParaRPr {rpr}/></a:p>"


def _pt(model_id, paragraphs="", *, type_=None, prset="", with_t=True):
    """A `dgm:pt` point; `type_=None` omits the (optional) `type` attribute like PowerPoint."""
    type_attr = "" if type_ is None else f' type="{type_}"'
    t = f"<dgm:t><a:bodyPr/><a:lstStyle/>{paragraphs}</dgm:t>" if with_t else ""
    return f'<dgm:pt modelId="{model_id}"{type_attr}>{prset}{t}</dgm:pt>'


def _data_xml(points, connections="", *, drawing_rel_id=None):
    """A complete `dgm:dataModel`, optionally pointing at a cached drawing part."""
    ext = ""
    if drawing_rel_id is not None:
        ext = (
            "<dgm:extLst>"
            '<a:ext uri="http://schemas.microsoft.com/office/drawing/2008/diagram">'
            f'<dsp:dataModelExt relId="{drawing_rel_id}" '
            'minVer="http://schemas.openxmlformats.org/drawingml/2006/diagram"/>'
            "</a:ext></dgm:extLst>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<dgm:dataModel {_NSDECLS}><dgm:ptLst>{points}</dgm:ptLst>"
        f"<dgm:cxnLst>{connections}</dgm:cxnLst><dgm:bg/><dgm:whole/>{ext}</dgm:dataModel>"
    )


def _sp(model_id, texts, *, rpr='lang="en-US" sz="1600" kern="1200"'):
    """A cached `dsp:sp` whose `dsp:txBody` holds one paragraph per entry of `texts`."""
    paragraphs = "".join(
        '<a:p><a:pPr lvl="0" algn="ctr"/>'
        + (f"<a:r><a:rPr {rpr}/><a:t>{text}</a:t></a:r>" if text else "")
        + f"<a:endParaRPr {rpr}/></a:p>"
        for text in texts
    )
    return (
        f'<dsp:sp modelId="{model_id}"><dsp:nvSpPr><dsp:cNvPr id="0" name=""/><dsp:cNvSpPr/>'
        "</dsp:nvSpPr><dsp:spPr/><dsp:txBody><a:bodyPr/><a:lstStyle/>"
        f"{paragraphs}</dsp:txBody></dsp:sp>"
    )


def _drawing_xml(*shapes):
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<dsp:drawing {_NSDECLS}><dsp:spTree><dsp:nvGrpSpPr><dsp:cNvPr id="0" name=""/>'
        "<dsp:cNvGrpSpPr/></dsp:nvGrpSpPr><dsp:grpSpPr/>"
        + "".join(shapes)
        + "</dsp:spTree></dsp:drawing>"
    )


def _pres_of(model_id, src, dest, dest_ord=0):
    return (
        f'<dgm:cxn modelId="{model_id}" type="presOf" srcId="{src}" destId="{dest}" '
        f'srcOrd="0" destOrd="{dest_ord}"/>'
    )


def _cached_org_chart(*, texts=("CEO", "CTO", "CFO"), paragraphs=None, drawing_rel_id="rId6"):
    """A hand-built, PowerPoint-shaped diagram: untyped node B, nodes C and D, plus cache.

    Node B owns its own cached shape ({PB}); C and D share one cached shape ({PCD}) the way
    child bullets do, so their paragraphs are told apart only by `destOrd`.
    """
    paragraphs = paragraphs or [_para(t) if t else _para() for t in texts]
    points = (
        _pt("{A}", type_="doc", with_t=False)
        + _pt("{B}", paragraphs[0])
        + _pt("{C}", paragraphs[1], type_="node")
        + _pt("{D}", paragraphs[2], type_="node")
        + _pt("{PB}", type_="pres", with_t=False)
        + _pt("{PCD}", type_="pres", with_t=False)
    )
    connections = (
        _pres_of("{X1}", "{B}", "{PB}")
        + _pres_of("{X2}", "{C}", "{PCD}", 0)
        + _pres_of("{X3}", "{D}", "{PCD}", 1)
    )
    drawing = _drawing_xml(_sp("{PB}", [texts[0]]), _sp("{PCD}", [texts[1], texts[2]]))
    return _data_xml(points, connections, drawing_rel_id=drawing_rel_id), drawing


def _drawing_part(slide):
    """The cached `diagramDrawing` part related from `slide`."""
    (part,) = [
        rel.target_part
        for rel in slide.part.rels.values()
        if rel.reltype.endswith("/diagramDrawing")
    ]
    return part


def _cached_text(slide):
    """Map each cached shape's `modelId` to the list of its paragraphs' text."""
    root = etree.fromstring(_drawing_part(slide).blob)
    return {
        sp.get("modelId"): [
            "".join(t.text or "" for t in p.iter(_A + "t")) for p in sp.iter(_A + "p")
        ]
        for sp in root.iter(_DSP + "sp")
    }


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

    # -- `dgm:pt/@type` is optional and defaults to "node" (ST_PtType); PowerPoint omits it
    # -- on ordinary content nodes, so a node must not be required to say `type="node"`.

    def it_reads_the_nodes_of_a_PowerPoint_authored_diagram(self):
        from power_pptx import Presentation

        sa = Presentation(SHAPES_DECK).slides[0].smart_art[0]
        assert sa.texts == ["shapes[5]", " ", " Smart Art"]

    def it_reads_the_placeholder_nodes_of_a_PowerPoint_authored_diagram(self):
        from power_pptx import Presentation

        sa = Presentation(PLACEHOLDERS_DECK).slides[7].smart_art[0]
        assert sa.texts == ["", "", "", "", "", ""]

    def it_reads_nodes_that_omit_the_type_attribute_in_a_hand_built_diagram(self):
        points = (
            _pt("{A}", type_="doc", with_t=False)
            + _pt("{B}", _para("CEO"))
            + _pt("{C}", _para("CTO"))
            + _pt("{D}", _para("CFO"))
        )
        sa = _open_variant(_data_xml(points)).slides[0].smart_art[0]
        assert sa.texts == ["CEO", "CTO", "CFO"]

    def it_counts_explicit_node_and_assistant_points_alongside_untyped_ones(self):
        points = (
            _pt("{B}", _para("untyped"))
            + _pt("{C}", _para("node"), type_="node")
            + _pt("{D}", _para("assistant"), type_="asst")
        )
        sa = _open_variant(_data_xml(points)).slides[0].smart_art[0]
        assert sa.texts == ["untyped", "node", "assistant"]

    def it_ignores_the_structural_points_even_when_they_carry_text(self):
        points = (
            _pt("{A}", _para("doc text"), type_="doc")
            + _pt("{B}", _para("CEO"))
            + _pt("{P}", _para("par"), type_="parTrans")
            + _pt("{S}", _para("sib"), type_="sibTrans")
            + _pt("{R}", _para("pres"), type_="pres")
            + _pt("{C}", _para("CTO"), type_="node")
        )
        sa = _open_variant(_data_xml(points)).slides[0].smart_art[0]
        assert sa.texts == ["CEO", "CTO"]


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

    # -- nodes that omit `type` (what PowerPoint writes for ordinary content nodes) --

    def it_replaces_the_text_of_a_PowerPoint_authored_diagram(self):
        from power_pptx import Presentation

        sa = Presentation(SHAPES_DECK).slides[0].smart_art[0]
        sa.set_text(["ALPHA", "BETA", "GAMMA"])
        assert sa.texts == ["ALPHA", "BETA", "GAMMA"]

    def it_fills_the_placeholder_nodes_of_a_PowerPoint_authored_diagram(self):
        from power_pptx import Presentation

        sa = Presentation(PLACEHOLDERS_DECK).slides[7].smart_art[0]
        sa.set_text(["one", "two", "three", "four", "five", "six"])
        assert sa.texts == ["one", "two", "three", "four", "five", "six"]

    def it_round_trips_a_PowerPoint_authored_diagram_through_save_and_reopen(self):
        from power_pptx import Presentation

        prs = Presentation(SHAPES_DECK)
        prs.slides[0].smart_art[0].set_text(["ALPHA", "BETA", "GAMMA"])
        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        assert Presentation(buf).slides[0].smart_art[0].texts == ["ALPHA", "BETA", "GAMMA"]

    def it_replaces_the_text_of_untyped_nodes_in_a_hand_built_diagram(self):
        points = (
            _pt("{A}", type_="doc", with_t=False)
            + _pt("{B}", _para("CEO"))
            + _pt("{C}", _para("CTO"))
        )
        sa = _open_variant(_data_xml(points)).slides[0].smart_art[0]
        sa.set_text(["Alice", "Bob"])
        assert sa.texts == ["Alice", "Bob"]

    # -- a node whose `dgm:t` already holds a paragraph (PowerPoint's "[Text]" placeholder
    # -- nodes hold an empty one) must be written into, not given a second paragraph.

    def it_writes_into_the_existing_empty_paragraph_of_a_placeholder_node(self):
        points = _pt("{B}", _para(), type_="node") + _pt("{C}", _para(), type_="node")
        sa = _open_variant(_data_xml(points)).slides[0].smart_art[0]

        sa.set_text(["First", "Second"])

        assert sa.texts == ["First", "Second"]
        for pt in sa._data_element.iter(_DGM + "pt"):
            paragraphs = pt.findall(f"{_DGM}t/{_A}p")
            assert len(paragraphs) == 1
            # -- the run goes before the paragraph's end-of-paragraph properties --
            assert [child.tag for child in paragraphs[0]] == [_A + "r", _A + "endParaRPr"]

    def it_keeps_a_single_paragraph_for_every_placeholder_node_of_a_PowerPoint_deck(self):
        from power_pptx import Presentation

        sa = Presentation(PLACEHOLDERS_DECK).slides[7].smart_art[0]
        sa.set_text(["one", "two", "three", "four", "five", "six"])
        nodes = sa._data_element.xpath(
            "dgm:ptLst/dgm:pt[not(@type)]", namespaces={"dgm": _DGM[1:-1]}
        )
        assert len(nodes) == 6
        for pt in nodes:
            assert len(pt.findall(f"{_DGM}t/{_A}p")) == 1

    def it_carries_the_end_of_paragraph_run_properties_over_to_the_new_run(self):
        points = _pt("{B}", _para(rpr='lang="de-DE"'), type_="node")
        sa = _open_variant(_data_xml(points)).slides[0].smart_art[0]

        sa.set_text(["Hallo"])

        (run,) = sa._data_element.iter(_A + "r")
        assert run.find(_A + "rPr").get("lang") == "de-DE"

    def it_adds_a_paragraph_only_when_the_node_has_none(self):
        points = _pt("{B}", "", type_="node") + _pt("{C}", type_="node", with_t=False)
        sa = _open_variant(_data_xml(points)).slides[0].smart_art[0]

        sa.set_text(["First", "Second"])

        assert sa.texts == ["First", "Second"]
        for pt in sa._data_element.iter(_DGM + "pt"):
            assert len(pt.findall(f"{_DGM}t/{_A}p")) == 1

    def it_writes_into_the_first_paragraph_when_a_node_has_several_empty_ones(self):
        points = _pt("{B}", _para() + _para(), type_="node")
        sa = _open_variant(_data_xml(points)).slides[0].smart_art[0]

        sa.set_text(["Only"])

        (pt,) = sa._data_element.iter(_DGM + "pt")
        paragraphs = pt.findall(f"{_DGM}t/{_A}p")
        assert len(paragraphs) == 2
        assert paragraphs[0].find(_A + "r") is not None
        assert paragraphs[1].find(_A + "r") is None

    # -- placeholder flag: PowerPoint drops `phldr` once a node holds real text --

    def it_clears_the_placeholder_flag_of_a_node_that_receives_text(self):
        prset = '<dgm:prSet phldrT="[Text]" phldr="1"/>'
        points = _pt("{B}", _para(), type_="node", prset=prset) + _pt(
            "{C}", _para(), type_="node", prset=prset
        )
        sa = _open_variant(_data_xml(points)).slides[0].smart_art[0]

        sa.set_text(["Filled", ""])

        first, second = sa._data_element.iter(_DGM + "prSet")
        assert first.get("phldr") is None
        assert first.get("phldrT") == "[Text]"
        # -- a node set to the empty string is still a placeholder --
        assert second.get("phldr") == "1"


# ---------------------------------------------------------------------------
# SmartArtShape.set_text keeps the cached drawing in step
# ---------------------------------------------------------------------------


class DescribeSmartArtShape_set_text_drawing_cache:
    """`ppt/diagrams/drawing#.xml` is what LibreOffice, Keynote and Google Slides draw from.

    Only PowerPoint re-lays a diagram out from the data model, so `set_text` has to refresh
    the cached text as well or every other renderer keeps showing the old strings.
    """

    def it_refreshes_the_text_cached_for_a_PowerPoint_authored_diagram(self):
        from power_pptx import Presentation

        slide = Presentation(SHAPES_DECK).slides[0]
        assert list(_cached_text(slide).values()) == [
            ["shapes[5]"],
            [""],
            [" "],
            [""],
            [" Smart Art"],
        ]

        slide.smart_art[0].set_text(["ALPHA", "BETA", "GAMMA"])

        # -- the cached shapes are keyed by *presentation* point, reached via `presOf` --
        assert _cached_text(slide) == {
            "{5A183679-F237-8E4A-BA44-AAD532C514F1}": ["ALPHA"],
            "{76DBFE1B-4144-9848-BF42-89AD15BEB370}": [""],
            "{A998EA2A-9166-EA4D-AD00-C84E18DA4D0C}": ["BETA"],
            "{D7E6BFD9-07A3-C64B-9399-EE30EC59A042}": [""],
            "{A7CEAFEB-AFA1-0349-AD09-A062A478B8A0}": ["GAMMA"],
        }

    def it_keeps_the_cached_text_through_save_and_reopen(self):
        from power_pptx import Presentation

        prs = Presentation(SHAPES_DECK)
        prs.slides[0].smart_art[0].set_text(["ALPHA", "BETA", "GAMMA"])
        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)

        cached = _cached_text(Presentation(buf).slides[0])

        assert [text for texts in cached.values() for text in texts if text] == [
            "ALPHA",
            "BETA",
            "GAMMA",
        ]

    def it_writes_text_into_the_empty_cached_paragraphs_of_placeholder_nodes(self):
        from power_pptx import Presentation

        slide = Presentation(PLACEHOLDERS_DECK).slides[7]
        slide.smart_art[0].set_text(["one", "two", "three", "four", "five", "six"])

        root = etree.fromstring(_drawing_part(slide).blob)
        filled = []
        for sp in root.iter(_DSP + "sp"):
            for p in sp.iter(_A + "p"):
                assert len(p.findall(_A + "r")) <= 1
                for r in p.findall(_A + "r"):
                    filled.append(r.find(_A + "t").text)
                    # -- the cached size (from `a:endParaRPr`) is what keeps it legible --
                    assert r.find(_A + "rPr").get("sz") == p.find(_A + "endParaRPr").get("sz")
                    assert list(p)[-1].tag == _A + "endParaRPr"
        assert sorted(filled) == ["five", "four", "one", "six", "three", "two"]

    def it_matches_the_paragraphs_of_a_shared_shape_by_destination_order(self):
        data, drawing = _cached_org_chart()
        slide = _open_variant(data, drawing).slides[0]

        slide.smart_art[0].set_text(["Alice", "Bob", "Carol"])

        assert _cached_text(slide) == {"{PB}": ["Alice"], "{PCD}": ["Bob", "Carol"]}

    def it_only_touches_the_shapes_of_nodes_whose_text_changed(self):
        data, drawing = _cached_org_chart()
        slide = _open_variant(data, drawing).slides[0]
        before = etree.fromstring(_drawing_part(slide).blob).find(
            f".//{_DSP}sp[@modelId='{{PCD}}']"
        )
        before_xml = etree.tostring(before)

        slide.smart_art[0].set_text(["Alice"], strict=False)

        assert _cached_text(slide) == {"{PB}": ["Alice"], "{PCD}": ["CTO", "CFO"]}
        after = etree.fromstring(_drawing_part(slide).blob).find(f".//{_DSP}sp[@modelId='{{PCD}}']")
        assert etree.tostring(after) == before_xml

    def it_matches_cached_shapes_that_carry_the_node_id_itself(self):
        # -- some generators key the cached shape by the data node rather than a pres point --
        points = _pt("{B}", _para("CEO"), type_="node")
        drawing = _drawing_xml(_sp("{B}", ["CEO"]))
        slide = _open_variant(_data_xml(points, drawing_rel_id="rId6"), drawing).slides[0]

        slide.smart_art[0].set_text(["Alice"])

        assert _cached_text(slide) == {"{B}": ["Alice"]}

    def it_leaves_a_cached_shape_alone_when_its_text_is_not_that_of_the_node(self):
        # -- the cache has drifted from the data model; guessing would corrupt another shape --
        data, drawing = _cached_org_chart()
        drawing = drawing.replace("<a:t>CEO</a:t>", "<a:t>Chief Exec</a:t>")
        slide = _open_variant(data, drawing).slides[0]

        slide.smart_art[0].set_text(["Alice", "Bob", "Carol"])

        assert _cached_text(slide) == {"{PB}": ["Chief Exec"], "{PCD}": ["Bob", "Carol"]}

    def it_leaves_a_shared_shape_alone_when_its_paragraphs_do_not_match_its_nodes(self):
        data, _ = _cached_org_chart()
        drawing = _drawing_xml(_sp("{PB}", ["CEO"]), _sp("{PCD}", ["CTO", "CFO", "extra"]))
        slide = _open_variant(data, drawing).slides[0]

        slide.smart_art[0].set_text(["Alice", "Bob", "Carol"])

        assert _cached_text(slide) == {"{PB}": ["Alice"], "{PCD}": ["CTO", "CFO", "extra"]}

    def it_does_not_need_a_drawing_part(self):
        sa = _make_prs().slides[0].smart_art[0]

        sa.set_text(["Alice", "Bob", "Carol"])

        assert sa.texts == ["Alice", "Bob", "Carol"]

    def it_ignores_a_data_model_extension_that_points_at_a_missing_relationship(self):
        points = _pt("{B}", _para("CEO"), type_="node")
        sa = _open_variant(_data_xml(points, drawing_rel_id="rId99")).slides[0].smart_art[0]

        sa.set_text(["Alice"])

        assert sa.texts == ["Alice"]

    def it_ignores_a_data_model_extension_that_points_at_another_kind_of_part(self):
        # -- rId2 is the layout part, not a drawing cache: it must not be rewritten --
        points = _pt("{B}", _para("CEO"), type_="node")
        prs = _open_variant(_data_xml(points, drawing_rel_id="rId2"))
        layout_part = prs.slides[0].part.related_part("rId2")
        layout_blob = layout_part.blob

        prs.slides[0].smart_art[0].set_text(["Alice"])

        assert layout_part.blob == layout_blob
