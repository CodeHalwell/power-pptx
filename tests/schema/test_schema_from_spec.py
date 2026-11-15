"""Decks built by ``from_spec`` validate against the ISO-29500 schemas.

``from_spec`` is fed by programs, so the shapes it writes from spec values —
free-standing ``shapes`` entries, the legacy KPI grid, structured bullets,
and the masters and layouts it rescales for ``slide_size`` — are checked here
rather than trusted to "reopens fine".
"""

from __future__ import annotations

import io

import pytest

from power_pptx.compose import SpecError, from_spec

from .oxml_schema_validator import assert_schema_valid, schema_validation_available

pytestmark = pytest.mark.skipif(
    not schema_validation_available(),
    reason="lxml or the bundled ISO-29500 XSD schemas are unavailable",
)


def _saved(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


_PLACEHOLDER_SLIDES = [
    {"layout": "title", "title": "Deck", "subtitle": "Subtitle"},
    {
        "layout": "bullets",
        "title": "Agenda",
        "bullets": ["One", {"text": "Nested", "level": 1}, {"text": "Deeper", "level": 2}],
    },
    {"layout": "section", "title": "Part two", "text": "Details"},
    {"layout": "two_column", "title": "Two", "left": ["a", "b"], "right": "plain"},
    {
        "layout": "comparison_layout",
        "title": "A vs B",
        "left_heading": "Before",
        "left": "Slow",
        "right_heading": "After",
        "right": ["Fast", {"text": "Cheap", "level": 1}],
    },
    {
        "layout": "kpi_grid",
        "title": "Metrics",
        "kpis": [{"label": f"KPI {n}", "value": str(n), "delta": (n - 4) / 10} for n in range(9)],
    },
]


class DescribeFromSpecSchemaValidity:
    @pytest.mark.parametrize("slide_size", [None, "16:9", "a4", (20, 5)])
    def it_validates_placeholder_layouts_at_any_slide_size(self, slide_size):
        spec = {"slides": _PLACEHOLDER_SLIDES, "lint": "off"}
        if slide_size is not None:
            spec["slide_size"] = slide_size
        assert_schema_valid(_saved(from_spec(spec)))

    def it_validates_recipe_slides_built_from_json_style_tokens(self):
        prs = from_spec(
            {
                "slide_size": "16:9",
                "tokens": {
                    "preset": "modern_light",
                    "palette": {"primary": [200, 30, 30]},
                    "typography": {"heading": {"size": 30}},
                    "shadows": {"card": {"blur": 10, "distance": 3, "alpha": 0.2}},
                    "radii": {"md": 6},
                },
                "slides": [
                    {"layout": "title", "title": "Deck", "subtitle": "Subtitle"},
                    {"layout": "bullets", "title": "Agenda", "bullets": ["One", {"text": "Two"}]},
                    {
                        "layout": "kpi",
                        "title": "Run-rate",
                        "kpis": [{"label": "ARR", "value": "$182M", "delta": 0.27}],
                        "tokens": {"preset": "modern_dark"},
                    },
                    {"layout": "table", "title": "T", "columns": ["a", "b"], "rows": [[1, 2], [3]]},
                    {"layout": "section_divider", "title": "Next", "progress": [2, 5]},
                ],
            }
        )
        assert_schema_valid(_saved(prs))

    def it_validates_free_standing_shapes_at_the_edges_of_the_allowed_geometry(self):
        prs = from_spec(
            {
                "slides": [
                    {
                        "layout": "blank",
                        "shapes": [
                            {
                                "name": "bleed",
                                "shape": "rectangle",
                                "left": -0.5,
                                "top": -0.5,
                                "width": 11,
                                "height": 8.5,
                            },
                            {"name": "rule", "left": 1, "top": 3, "width": 8, "height": 0},
                            {
                                "name": "far",
                                "shape": "oval",
                                "left": 56,
                                "top": 56,
                                "width": 56,
                                "height": 56,
                            },
                        ],
                    }
                ],
            }
        )
        assert_schema_valid(_saved(prs))

    def it_refuses_to_write_the_geometry_that_used_to_break_the_schema(self):
        # ``"width": -2`` was written as cx="-1828800", which ST_PositiveCoordinate
        # rejects; it must now be stopped before a file exists.
        with pytest.raises(SpecError, match="'width' must be between 0 and 56 inches"):
            from_spec(
                {
                    "slides": [
                        {
                            "layout": "blank",
                            "shapes": [{"left": 1, "top": 1, "width": -2, "height": 1}],
                        }
                    ],
                }
            )
