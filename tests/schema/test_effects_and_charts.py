"""Schema-validity guards for effects, 3-D, fills, picture recolour and charts.

Each builder returns a saved deck exercising one area whose XML changed; the
test asserts that every part validates against the ISO-29500 schemas *and*
that it survives save -> open -> save unchanged.  Kept apart from
`test_schema_validity.py` so the two can grow independently.
"""

from __future__ import annotations

import io

import pytest

from power_pptx import Presentation
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.util import Inches, Pt

from ..integration.round_trip import assert_round_trip
from .oxml_schema_validator import assert_schema_valid, schema_validation_available

pytestmark = pytest.mark.skipif(
    not schema_validation_available(),
    reason="lxml or the bundled ISO-29500 XSD schemas are unavailable",
)


def _blank_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def _rect(slide, col=0, row=0):
    return slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0.5 + 3 * col),
        Inches(0.5 + 2 * row),
        Inches(2.5),
        Inches(1.5),
    )


# ---------------------------------------------------------------------------
# Deck builders — each returns an unsaved |Presentation|.
# ---------------------------------------------------------------------------


def _deck_float_effect_lengths():
    """Every effect, 3-D and line length arrives as a float (`Pt(n) / 2`)."""
    prs = Presentation()
    sh = _rect(_blank_slide(prs))
    sh.shadow.blur_radius = Pt(8) / 2
    sh.shadow.distance = Pt(8) * 0.5
    sh.inner_shadow.blur_radius = Pt(6) / 2
    sh.glow.radius = Pt(6) / 2
    sh.soft_edges.radius = Pt(6) / 2
    sh.blur.radius = Pt(6) / 2
    sh.reflection.distance = Pt(6) / 2
    sh.reflection.blur_radius = Pt(1) / 3
    sh.line.width = Pt(3) / 2
    sh.three_d.bevel_top.width = Pt(6) / 2
    sh.three_d.bevel_top.height = Pt(5) / 3
    sh.three_d.extrusion_height = Pt(6) / 2
    sh.three_d.contour_width = Pt(1) / 2
    return prs


def _deck_rejected_effect_assignments():
    """Assignments that raise must not leave a half-built element behind."""
    prs = Presentation()
    slide = _blank_slide(prs)
    sh = _rect(slide)
    attempts = (
        (sh.soft_edges, "radius", -1),  # <a:softEdge/> lacks its required `rad`
        (sh.soft_edges, "radius", "3pt"),
        (sh.reflection, "start_alpha", 1.2),
        (sh.glow, "radius", object()),
        (sh.shadow, "direction", float("nan")),
        (sh.shadow.color, "rgb", "#FFF"),
        (sh.preset_shadow, "preset", 99),
        (sh.three_d.bevel_top, "width", -1),
        (sh.three_d.bevel_top, "preset", "circle"),
        (sh.three_d.extrusion_color, "rgb", "nope"),  # <a:extrusionClr/> needs a colour
        (sh.three_d, "preset_material", "metal"),
        (sh.line, "width", -1),
    )
    for proxy, name, value in attempts:
        with pytest.raises((TypeError, ValueError)):
            setattr(proxy, name, value)
    return prs


def _deck_cleared_effects():
    """Everything is set and then cleared again with `None`."""
    from power_pptx.enum.dml import BevelPreset

    prs = Presentation()
    sh = _rect(_blank_slide(prs))
    sh.shadow.blur_radius = Pt(4)
    sh.shadow.direction = -360  # a full turn must normalise to 0, not 21600000
    sh.glow.radius = Pt(4)
    sh.inner_shadow.distance = Pt(4)
    sh.soft_edges.radius = Pt(4)
    sh.blur.radius = Pt(4)
    sh.reflection.distance = Pt(4)
    sh.preset_shadow.distance = Pt(4)
    sh.three_d.bevel_top.preset = BevelPreset.CIRCLE

    sh.shadow.blur_radius = None
    sh.shadow.direction = None
    sh.glow.radius = None
    sh.inner_shadow.distance = None
    sh.soft_edges.radius = None
    sh.blur.radius = None
    sh.reflection.distance = None
    sh.preset_shadow.preset = None
    sh.three_d.bevel_top.preset = None
    return prs


def _deck_shadow_directions():
    """Directions at and around a full turn stay inside `[0, 21600000)`."""
    prs = Presentation()
    slide = _blank_slide(prs)
    for i, degrees in enumerate((360, -360, 359.9999999, -1e-6, 720.5, -90)):
        sh = _rect(slide, col=i % 3, row=i // 3)
        sh.shadow.direction = degrees
        sh.inner_shadow.direction = degrees
        sh.reflection.direction = degrees
    return prs


def _deck_gradients():
    """Gradients at every angle, plus calls that are rejected part-way."""
    prs = Presentation()
    slide = _blank_slide(prs)
    for i, angle in enumerate((0, 90, 180, 270, -90, 360, 359.9999999)):
        _rect(slide, col=i % 3, row=i // 3).fill.linear_gradient("#FF0000", "#0000FF", angle=angle)

    # -- a rejected stop or angle must leave a valid fill behind, not an
    # -- `<a:gs/>` with neither position nor colour
    sh = _rect(slide, col=1, row=2)
    sh.fill.gradient()
    with pytest.raises(ValueError):
        sh.fill.gradient_stops.replace([(0.0, "#FF0000"), (1.5, "#00FF00")])
    with pytest.raises(ValueError):
        sh.fill.gradient_stops.append(-0.5, "#00FF00")
    with pytest.raises(ValueError):
        sh.fill.linear_gradient([("#FF0000", -0.2), ("#00FF00", 1.0)])
    with pytest.raises(ValueError):
        sh.fill.linear_gradient("#FF0000", "#00F")
    return prs


def _add_chart(slide, chart_type, series_names, row=0, col=0):
    from power_pptx.chart.data import CategoryChartData

    data = CategoryChartData()
    data.categories = ["Q1", "Q2", "Q3"]
    for i, name in enumerate(series_names):
        data.add_series(name, (10.0 * (i + 1), 20.0 * (i + 1), 30.0 * (i + 1)))
    return slide.shapes.add_chart(
        chart_type, Inches(0.3 + 4.8 * col), Inches(0.3 + 3.6 * row), Inches(4.6), Inches(3.4), data
    ).chart


def _deck_series_on_secondary_axis():
    """One series of several moved onto a secondary axis, in each plot kind."""
    from power_pptx.chart.data import XyChartData
    from power_pptx.enum.chart import XL_CHART_TYPE

    prs = Presentation()
    slide = _blank_slide(prs)

    # -- a series split off into its own plot
    column = _add_chart(slide, XL_CHART_TYPE.COLUMN_CLUSTERED, ("Revenue", "Margin %"))
    column.series[1].axis_group = "secondary"
    column.value_axis.maximum_scale = 100
    column.secondary_value_axis.maximum_scale = 1

    # -- two like series gathered into one secondary plot
    a, b, c = _add_chart(slide, XL_CHART_TYPE.LINE_MARKERS, ("A", "B", "C"), col=1).series
    c.axis_group = "secondary"
    b.axis_group = "secondary"

    # -- the documented two-liner, on a horizontal bar chart
    bar = _add_chart(slide, XL_CHART_TYPE.BAR_STACKED, ("Won", "Lost", "Open"), row=1)
    bar.secondary_value_axis
    bar.series[0].axis_group = "secondary"

    # -- XY chart: both axes of each group are value axes
    data = XyChartData()
    for name in ("S1", "S2"):
        series = data.add_series(name)
        for x, y in ((1, 2), (2, 3), (3, 5)):
            series.add_data_point(x, y)
    xy = slide.shapes.add_chart(
        XL_CHART_TYPE.XY_SCATTER, Inches(5.1), Inches(3.9), Inches(4.6), Inches(3.4), data
    ).chart
    xy.series[1].axis_group = "secondary"
    return prs


_DECK_BUILDERS = {
    "cleared_effects": _deck_cleared_effects,
    "float_effect_lengths": _deck_float_effect_lengths,
    "gradients": _deck_gradients,
    "rejected_effect_assignments": _deck_rejected_effect_assignments,
    "series_on_secondary_axis": _deck_series_on_secondary_axis,
    "shadow_directions": _deck_shadow_directions,
}


def _saved(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


class DescribeEffectsAndChartsSchemaValidity:
    @pytest.mark.parametrize("name", sorted(_DECK_BUILDERS))
    def it_validates_against_the_ooxml_schema(self, name):
        assert_schema_valid(_saved(_DECK_BUILDERS[name]()))

    @pytest.mark.parametrize("name", sorted(_DECK_BUILDERS))
    def it_round_trips(self, name):
        assert_round_trip(_DECK_BUILDERS[name]())

    def it_leaves_nothing_behind_once_effects_are_cleared_or_rejected(self):
        for build in (_deck_cleared_effects, _deck_rejected_effect_assignments):
            spPr = build().slides[0].shapes[0]._element.spPr
            assert spPr.effectLst is None, build.__name__
            assert spPr.ln is None, build.__name__

    def it_keeps_every_chart_axis_reference_resolvable_after_a_series_moves(self):
        # The schema cannot express "each plot's axId names an axis that
        # exists, and each axis is used", which is what PowerPoint needs.
        prs = Presentation(io.BytesIO(_saved(_deck_series_on_secondary_axis())))
        charts = [shape.chart for shape in prs.slides[0].shapes]
        assert len(charts) == 4
        for chart in charts:
            plotArea = chart._chartSpace.plotArea
            defined = plotArea.xpath("(c:catAx | c:valAx | c:dateAx)/c:axId/@val")
            used = {v for xChart in plotArea.xCharts for v in xChart.xpath("c:axId/@val")}
            assert len(defined) == len(set(defined)) == 4
            assert used == set(defined)
            # -- each axis crosses the other axis of its own group
            for axis in plotArea.xpath("c:catAx | c:valAx | c:dateAx"):
                assert axis.xpath("c:crossAx/@val")[0] in defined
            assert {series.axis_group for series in chart.series} == {"primary", "secondary"}
