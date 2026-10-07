"""Deck-level "PowerPoint-strict" checks the OOXML schema doesn't catch.

Microsoft PowerPoint's open-time validator is stricter than the
OOXML schemas. The classic example is the area + doughnut chart
``<a:endParaRPr/>`` bug fixed in this branch — schema-valid (the
``lang`` attribute is optional) but rejected by PowerPoint.

Until a Windows CI runner with real PowerPoint roundtrip exists,
the next-best signal is to scan the saved deck's XML for the
specific strict-validator hooks we know about. The list grows as
we discover more.

Each test builds a deck containing the chart / shape kinds most
likely to trigger the relevant rule, saves it to bytes, and walks
every XML part looking for the stricter-than-spec patterns. A
failure here means a writer regressed.
"""

from __future__ import annotations

import io
import re
import zipfile

import pytest
from lxml import etree

from power_pptx import Presentation
from power_pptx.chart.data import CategoryChartData
from power_pptx.dml.color import RGBColor
from power_pptx.enum.chart import XL_CHART_TYPE
from power_pptx.util import Inches


def _deck_with_every_chart_type():
    prs = Presentation()
    types = [
        XL_CHART_TYPE.AREA,
        XL_CHART_TYPE.AREA_STACKED,
        XL_CHART_TYPE.AREA_STACKED_100,
        XL_CHART_TYPE.BAR_CLUSTERED,
        XL_CHART_TYPE.BAR_STACKED,
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        XL_CHART_TYPE.COLUMN_STACKED,
        XL_CHART_TYPE.LINE,
        XL_CHART_TYPE.PIE,
        XL_CHART_TYPE.DOUGHNUT,
        XL_CHART_TYPE.RADAR,
    ]
    for chart_type in types:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        data = CategoryChartData()
        data.categories = ["A", "B", "C"]
        data.add_series("S1", (1.0, 2.0, 3.0))
        data.add_series("S2", (1.5, 1.8, 2.2))
        slide.shapes.add_chart(chart_type, Inches(1), Inches(1), Inches(6), Inches(4), data)
    return prs


def _save_to_bytes(prs):
    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf.getvalue()


def _walk_xml_parts(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        for info in zf.infolist():
            if not info.filename.endswith(".xml"):
                continue
            yield info.filename, zf.read(info.filename)


@pytest.fixture(scope="module")
def deck_blob():
    return _save_to_bytes(_deck_with_every_chart_type())


class DescribeEndParaRPrLang:
    """Issue 0 (post-2.5 review).

    PowerPoint's open-time validator rejects bare ``<a:endParaRPr/>``;
    every emission must carry a ``lang`` attribute even though the
    schema marks it optional.
    """

    def it_finds_no_bare_endParaRPr_anywhere_in_the_deck(self, deck_blob):
        bare = re.compile(rb"<a:endParaRPr\s*/>")
        for filename, body in _walk_xml_parts(deck_blob):
            assert not bare.search(body), (
                f"{filename} emits a bare <a:endParaRPr/>; PowerPoint "
                "will prompt to 'Repair' the file. Add lang=\"en-US\"."
            )

    def it_finds_lang_on_every_endParaRPr(self, deck_blob):
        with_attrs = re.compile(rb"<a:endParaRPr\b[^>]*>")
        for filename, body in _walk_xml_parts(deck_blob):
            for match in with_attrs.finditer(body):
                assert b"lang=" in match.group(0), (
                    f"{filename} emitted <a:endParaRPr> without lang: {match.group(0)!r}"
                )


class DescribeStrictHookList:
    """Reserve a slot for additional strict-validator rules we discover.

    Each of these is a regression-prevention check: if PowerPoint
    rejects something the schema accepts, encode that here so the
    next bug doesn't ship silently.
    """

    def it_runs_against_a_real_chart_deck(self, deck_blob):
        # Smoke check that the deck has the parts we think it does;
        # if zero charts were registered, the more-targeted tests
        # above would pass vacuously.
        chart_parts = [f for f, _ in _walk_xml_parts(deck_blob) if "/charts/chart" in f]
        assert len(chart_parts) >= 11


# ── PowerPoint-strict compliance helper ──────────────────────────────
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
A = f"{{{A_NS}}}"
XFRM_TAGS = ("off", "ext", "chOff", "chExt")


def assert_powerpoint_strict_compliance(pptx_bytes):
    """Assert a saved .pptx passes PowerPoint's stricter-than-spec rules.

    Walks every XML part in the archive and applies three checks:

    1. Every ``<a:p>`` paragraph must end with ``<a:endParaRPr>``
       UNLESS it contains at least one ``<a:r>`` text run. Bare
       ``<a:p><a:pPr/></a:p>`` triggers PowerPoint's "Repair?" dialog.
    2. Every ``<a:endParaRPr>`` must carry a ``lang`` attribute.
    3. Every ``<a:off>`` / ``<a:ext>`` / ``<a:chOff>`` / ``<a:chExt>``
       coordinate (``x``/``y``/``cx``/``cy``) must be an integer-valued
       string. ``CT_Point2D`` is ``xs:long``; floats are schema-invalid
       and PowerPoint rejects them.
    """
    for filename, body in _walk_xml_parts(pptx_bytes):
        try:
            tree = etree.fromstring(body)
        except etree.XMLSyntaxError:
            continue

        # Rule 1 — non-empty <a:p> need either a text run or endParaRPr.
        for p in tree.iter(f"{A}p"):
            has_run = p.find(f"{A}r") is not None
            has_fld = p.find(f"{A}fld") is not None  # field run counts
            has_br = p.find(f"{A}br") is not None  # line break counts
            has_end = p.find(f"{A}endParaRPr") is not None
            if not (has_run or has_fld or has_br or has_end):
                raise AssertionError(
                    f"{filename}: <a:p> has neither a text run nor "
                    f"<a:endParaRPr> — PowerPoint will prompt to Repair "
                    f"the file."
                )

        # Rule 2 — every <a:endParaRPr> must carry lang.
        for endpr in tree.iter(f"{A}endParaRPr"):
            assert endpr.get("lang"), (
                f"{filename}: <a:endParaRPr> missing lang attribute "
                f"(would trigger PowerPoint Repair?)"
            )

        # Rule 3 — xfrm coordinates must be integer-valued strings.
        for tag in XFRM_TAGS:
            for elt in tree.iter(f"{A}{tag}"):
                for attr in ("x", "y", "cx", "cy"):
                    v = elt.get(attr)
                    if v is None:
                        continue
                    msg = (
                        f"{filename}: <a:{tag}> {attr}={v!r} is not "
                        "integer-valued (would trigger PowerPoint "
                        "Repair?). Likely cause: float coordinate "
                        "passed to a shape constructor — check for "
                        "`/` instead of `//` in the calling code."
                    )
                    assert "." not in v, msg
                    assert "e" not in v.lower(), msg


class DescribeIssue0FamilyRegressions:
    """Pin each historical Issue-0-family bug with a strict-compliance test."""

    def it_passes_strict_compliance_for_all_chart_types(self, deck_blob):
        # Original Issue 0 — every chart type, no bare endParaRPr.
        assert_powerpoint_strict_compliance(deck_blob)

    def it_emits_endpararpr_when_chart_text_color_set_after_dlbls(self):
        # Issue 0' — chart dLbls / chart-level txPr <a:p> created
        # lazily by font customisation must include <a:endParaRPr>.
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        data = CategoryChartData()
        data.categories = ["A", "B"]
        data.add_series("S", (1, 2))
        chart = slide.shapes.add_chart(
            XL_CHART_TYPE.BAR_CLUSTERED,
            Inches(1),
            Inches(1),
            Inches(5),
            Inches(4),
            data,
        ).chart
        chart.plots[0].has_data_labels = True
        chart.plots[0].data_labels.show_value = True
        # The sequence that triggered the field bug — assigning
        # text_color after dLbls are enabled materialises the chart's
        # <c:txPr> via CT_TextBody.new_txPr.
        chart.text_color = RGBColor.from_hex("FFFFFF")
        buf = io.BytesIO()
        prs.save(buf)
        assert_powerpoint_strict_compliance(buf.getvalue())

    def it_emits_integer_xfrm_coords_for_float_arithmetic(self):
        # Issue 0'' — float-valued xfrm from `(Inches(N) - g) / 2`.
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        data = CategoryChartData()
        data.categories = ["A", "B"]
        data.add_series("S", (1, 2))
        # Reproduce the exact field-bug arithmetic.
        card_w = (Inches(12.33) - Inches(0.25)) / 2
        assert isinstance(card_w, float), (
            "regression — Python's `/` should still produce a float here"
        )
        slide.shapes.add_chart(
            XL_CHART_TYPE.BAR_CLUSTERED,
            Inches(0.5),
            Inches(1.5),
            card_w,
            Inches(3),
            data,
        )
        buf = io.BytesIO()
        prs.save(buf)
        assert_powerpoint_strict_compliance(buf.getvalue())

    def it_coerces_float_setters_on_shape_geometry(self):
        # Direct property-setter path — `shape.width = float_value`
        # would have written a float-valued `cx` attribute pre-fix.
        from power_pptx.enum.shapes import MSO_SHAPE

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(1),
            Inches(1),
            Inches(2),
            Inches(1),
        )
        shape.left = Inches(0.5) + 0.1  # produces a float
        shape.top = Inches(0.5) + 0.1
        shape.width = Inches(4.0) + 0.5  # produces a float
        shape.height = Inches(2.0) + 0.5
        buf = io.BytesIO()
        prs.save(buf)
        assert_powerpoint_strict_compliance(buf.getvalue())
