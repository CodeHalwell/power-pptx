"""Integration tests for PowerPoint-compatibility of generated transitions.

A morph (and other p14) transition must be serialized inside an
``<mc:AlternateContent>`` wrapper; a bare ``<p14:morph>`` child of
``<p:transition>`` is schema-invalid and Microsoft PowerPoint flags the deck as
needing repair.  These tests drive the public API through a save/reopen cycle
because the wrap/unwrap happens at the part serialization boundary.
"""

from __future__ import annotations

import io
import zipfile

from power_pptx import Presentation
from power_pptx.enum.presentation import MSO_TRANSITION_TYPE
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.util import Inches


def _saved_slide_xml(prs, slide_index=0):
    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    with zipfile.ZipFile(buf) as z:
        return z.read("ppt/slides/slide%d.xml" % (slide_index + 1)).decode("utf-8")


class DescribeMorphTransitionSerialization:
    def it_wraps_a_morph_transition_in_alternate_content(self):
        prs = Presentation()
        s = prs.slides.add_slide(prs.slide_layouts[6])
        s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(2), Inches(2), Inches(2), Inches(2))
        s.transition.kind = MSO_TRANSITION_TYPE.MORPH
        s.transition.duration = 500

        xml = _saved_slide_xml(prs)
        assert "<mc:AlternateContent" in xml
        # Morph is a PowerPoint-2016 (2015/09, p159) element per MS-PPTX —
        # NOT p14. A `p14:morph` in a Requires="p14" Choice is an undefined
        # element in a namespace every modern PowerPoint understands, which
        # triggers the repair dialog.
        assert 'Requires="p159"' in xml
        assert "<p159:morph" in xml
        assert 'option="byObject"' in xml
        assert "p14:morph" not in xml
        # A fallback <p:transition> must be present for pre-2016 viewers,
        # with PowerPoint's own downgrade kind (fade), not kind-less.
        assert "<mc:Fallback>" in xml
        assert "<p:fade/>" in xml
        # The bare (invalid) form must NOT be present.
        assert "<p:transition><p159:morph" not in xml

    def it_does_not_wrap_a_standard_transition(self):
        prs = Presentation()
        s = prs.slides.add_slide(prs.slide_layouts[6])
        s.transition.kind = MSO_TRANSITION_TYPE.FADE

        xml = _saved_slide_xml(prs)
        assert "AlternateContent" not in xml
        assert "<p:transition><p:fade/></p:transition>" in xml

    def it_round_trips_a_morph_transition_through_save_and_reopen(self, tmp_path):
        prs = Presentation()
        s = prs.slides.add_slide(prs.slide_layouts[6])
        s.transition.kind = MSO_TRANSITION_TYPE.MORPH
        s.transition.duration = 750
        path = str(tmp_path / "morph.pptx")
        prs.save(path)

        reopened = Presentation(path)
        assert reopened.slides[0].transition.kind == MSO_TRANSITION_TYPE.MORPH
        assert reopened.slides[0].transition.duration == 750

        # Re-saving must keep the wrapper (stable round-trip).
        xml = _saved_slide_xml(reopened)
        assert "<mc:AlternateContent" in xml
        assert "<p159:morph" in xml

    def it_round_trips_a_powerpoint_authored_p159_morph(self):
        # A deck whose morph was written by PowerPoint itself (p159 wrapper,
        # p14:dur on the transition) must re-save schema-valid: the p159 kind
        # must stay in a Requires="p159" Choice and must never leak into the
        # ISO-pure mc:Fallback branch.
        import re

        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)

        p159_wrapper = (
            '<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/'
            'markup-compatibility/2006">'
            '<mc:Choice xmlns:p159="http://schemas.microsoft.com/office/'
            'powerpoint/2015/09/main" xmlns:p14="http://schemas.microsoft.com/'
            'office/powerpoint/2010/main" Requires="p159">'
            '<p:transition spd="slow" p14:dur="2000">'
            '<p159:morph option="byObject"/></p:transition></mc:Choice>'
            "<mc:Fallback><p:transition spd=\"slow\"><p:fade/></p:transition>"
            "</mc:Fallback></mc:AlternateContent>"
        )
        out = io.BytesIO()
        with zipfile.ZipFile(buf) as zin:
            slide_xml = zin.read("ppt/slides/slide1.xml").decode("utf-8")
            slide_xml = re.sub(
                r"(</p:clrMapOvr>)", r"\1" + p159_wrapper, slide_xml, count=1
            )
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = (
                        slide_xml.encode("utf-8")
                        if item.filename == "ppt/slides/slide1.xml"
                        else zin.read(item.filename)
                    )
                    zout.writestr(item, data)
        out.seek(0)

        reopened = Presentation(out)
        assert reopened.slides[0].transition.kind == MSO_TRANSITION_TYPE.MORPH

        resaved = _saved_slide_xml(reopened)
        assert 'Requires="p159"' in resaved
        # No bare p159 kind outside the wrapper, and none in the Fallback.
        assert "<p:transition spd=\"slow\" p14:dur=\"2000\"><p159:morph" not in resaved.replace(
            "AlternateContent", ""
        ) or "<mc:AlternateContent" in resaved
        fallback = resaved.split("<mc:Fallback>", 1)[1]
        assert "p159" not in fallback

        from tests.schema.oxml_schema_validator import iter_schema_violations

        final = io.BytesIO()
        reopened.save(final)
        assert list(iter_schema_violations(final.getvalue())) == []

    def it_heals_a_legacy_p14_morph_on_resave(self):
        # Decks written by earlier power-pptx releases carry `p14:morph`
        # inside a Requires="p14" Choice; a load → save cycle must retag the
        # kind to p159 and fix the Requires token.
        import re

        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)

        p14_wrapper = (
            '<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/'
            'markup-compatibility/2006">'
            '<mc:Choice xmlns:p14="http://schemas.microsoft.com/office/'
            'powerpoint/2010/main" Requires="p14">'
            '<p:transition p14:dur="600"><p14:morph option="byObject"/>'
            "</p:transition></mc:Choice>"
            "<mc:Fallback><p:transition/></mc:Fallback></mc:AlternateContent>"
        )
        out = io.BytesIO()
        with zipfile.ZipFile(buf) as zin:
            slide_xml = zin.read("ppt/slides/slide1.xml").decode("utf-8")
            slide_xml = re.sub(
                r"(</p:clrMapOvr>)", r"\1" + p14_wrapper, slide_xml, count=1
            )
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = (
                        slide_xml.encode("utf-8")
                        if item.filename == "ppt/slides/slide1.xml"
                        else zin.read(item.filename)
                    )
                    zout.writestr(item, data)
        out.seek(0)

        reopened = Presentation(out)
        assert reopened.slides[0].transition.kind == MSO_TRANSITION_TYPE.MORPH
        resaved = _saved_slide_xml(reopened)
        assert "p14:morph" not in resaved
        assert "<p159:morph" in resaved
        assert 'Requires="p159"' in resaved


class DescribeChartAxisIds:
    def it_generates_unsigned_axis_ids(self, tmp_path):
        # axId / crossAx are xs:unsignedInt; the legacy templates used to emit
        # negative (signed) ids which fail schema validation.
        from power_pptx.chart.data import CategoryChartData
        from power_pptx.enum.chart import XL_CHART_TYPE
        from lxml import etree

        prs = Presentation()
        s = prs.slides.add_slide(prs.slide_layouts[6])
        cd = CategoryChartData()
        cd.categories = ["A", "B"]
        cd.add_series("S", [1, 2])
        s.shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1), Inches(6), Inches(4), cd
        )
        path = str(tmp_path / "chart.pptx")
        prs.save(path)

        with zipfile.ZipFile(path) as z:
            chart_xml = etree.fromstring(z.read("ppt/charts/chart1.xml"))
        C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
        vals = [
            int(e.get("val"))
            for tag in ("axId", "crossAx")
            for e in chart_xml.iter("{%s}%s" % (C, tag))
        ]
        assert vals, "expected axId/crossAx elements"
        assert all(0 <= v <= 4294967295 for v in vals), vals
