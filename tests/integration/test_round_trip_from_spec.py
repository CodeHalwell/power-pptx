"""Round-trip guards for what ``from_spec`` writes from spec values.

``slide_size`` rewrites the geometry of the template's masters and layouts,
and the placeholder layouts and legacy KPI grid write text and shapes from
spec content; a deck built that way must survive save → open → save intact.
"""

from __future__ import annotations

import io

import pytest

from power_pptx import Presentation
from power_pptx.compose import from_spec

from .round_trip import assert_round_trip

_SLIDES = [
    {"layout": "title", "title": "Deck", "subtitle": "Subtitle"},
    {
        "layout": "bullets",
        "title": "Agenda",
        "bullets": ["One", {"text": "Nested", "level": 1}],
    },
    {
        "layout": "comparison_layout",
        "title": "A vs B",
        "left_heading": "Before",
        "left": "Slow",
        "right_heading": "After",
        "right": ["Fast", "Cheap"],
    },
    {
        "layout": "kpi_grid",
        "title": "Metrics",
        "kpis": [{"label": f"KPI {n}", "value": str(n), "delta": "+1 pt"} for n in range(6)],
    },
    {
        "layout": "blank",
        "shapes": [
            {"name": "card", "shape": "rounded_rectangle",
             "left": -0.25, "top": 1, "width": 4, "height": 2, "text": "Card"},
        ],
    },
]


class DescribeFromSpecRoundTrip:
    @pytest.mark.parametrize("slide_size", [None, "16:9", (8, 10)])
    def it_round_trips_a_deck_of_placeholder_layouts(self, slide_size):
        spec = {"slides": _SLIDES}
        if slide_size is not None:
            spec["slide_size"] = slide_size
        assert_round_trip(from_spec(spec))

    def it_keeps_the_rescaled_layout_geometry_after_reopening(self):
        prs = from_spec({"slide_size": "16:9", "slides": _SLIDES[:2]})
        buf = io.BytesIO()
        prs.save(buf)
        reopened = Presentation(io.BytesIO(buf.getvalue()))
        title, again = prs.slides[1].shapes.title, reopened.slides[1].shapes.title
        assert (again.left, again.top, again.width, again.height) == (
            title.left, title.top, title.width, title.height,
        )
        # The placeholder inherits from the rescaled layout: it now spans the wide slide.
        assert again.left + again.width > reopened.slide_width * 0.9
        body = next(p for p in reopened.slides[1].placeholders if p.placeholder_format.idx == 1)
        assert [(p.text, p.level) for p in body.text_frame.paragraphs] == [
            ("One", 0), ("Nested", 1),
        ]
