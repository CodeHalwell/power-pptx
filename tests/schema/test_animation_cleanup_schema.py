"""Schema validity of the timing tree once shapes are deleted from it.

Taking effects out of a timing tree is where it goes wrong: ``p:childTnLst`` and ``p:bldLst`` must
each hold at least one entry, so a removal that leaves either empty produces a deck PowerPoint
offers to repair. These tests build timing the way PowerPoint writes it (everything nested under a
main sequence), delete shapes in the ways that empty the various wrappers, and validate every
intermediate deck against the ISO-29500 schemas.
"""

from __future__ import annotations

import io

import pytest

from power_pptx import Presentation
from power_pptx.animation import Entrance
from power_pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from power_pptx.util import Inches

from ..unitutil.timing import install_timing, powerpoint_timing_xml
from .oxml_schema_validator import assert_schema_valid, schema_validation_available

pytestmark = pytest.mark.skipif(
    not schema_validation_available(),
    reason="lxml or the bundled ISO-29500 XSD schemas are unavailable",
)


def _saved(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _animated_deck():
    """A slide with a PowerPoint-style timing tree touching eight shapes.

    Main sequence: A (click) with B, then C after previous; D (click). Interactive sequence:
    clicking F plays G. E carries media play controls. A, B, C and D are in the build list.
    """
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    a, b, c, d, e, f, g, h = (
        slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0.5 + i), Inches(1), Inches(0.5), Inches(0.5)
        )
        for i in range(8)
    )
    install_timing(
        slide,
        powerpoint_timing_xml(
            [
                (a.shape_id, "clickEffect"),
                (b.shape_id, "withEffect"),
                (c.shape_id, "afterEffect"),
                (d.shape_id, "clickEffect"),
            ],
            interactive=[(f.shape_id, [(g.shape_id, "clickEffect")])],
            media=[("video", e.shape_id)],
            bld=[a.shape_id, b.shape_id, c.shape_id, d.shape_id],
        ),
    )
    return prs, slide, {"abcdefgh"[i]: s for i, s in enumerate((a, b, c, d, e, f, g, h))}


class DescribeTimingSchemaValidityAfterDeletion:
    def it_starts_from_a_valid_deck(self):
        prs, _, _ = _animated_deck()

        assert_schema_valid(_saved(prs))

    @pytest.mark.parametrize(
        "order",
        [
            "abcdefgh",  # in play order
            "hgfedcba",  # backwards
            "bdfhaceg",  # scattered
            "fgabcdeh",  # the interactive sequence first
            "ecbadfgh",  # the media node first
        ],
    )
    def it_stays_valid_after_every_deletion(self, order):
        prs, _, shapes = _animated_deck()

        for key in order:
            shapes[key].delete()
            assert_schema_valid(_saved(prs))

    def it_stays_valid_when_the_trigger_of_an_interactive_sequence_is_deleted(self):
        prs, _, shapes = _animated_deck()

        shapes["f"].delete()

        assert_schema_valid(_saved(prs))

    def it_stays_valid_when_every_effect_is_cleared(self):
        prs, slide, _ = _animated_deck()

        slide.animations.clear()

        assert_schema_valid(_saved(prs))

    def it_stays_valid_when_effects_are_removed_one_by_one(self):
        prs, slide, _ = _animated_deck()

        while len(slide.animations):
            list(slide.animations)[0].remove()
            assert_schema_valid(_saved(prs))

    def it_stays_valid_when_the_library_appends_effects_to_the_cleaned_tree(self):
        prs, slide, shapes = _animated_deck()
        shapes["a"].delete()
        shapes["c"].delete()

        Entrance.fade(slide, shapes["h"])

        assert_schema_valid(_saved(prs))

    def it_stays_valid_after_deleting_a_group_of_animated_shapes(self):
        prs, slide, shapes = _animated_deck()
        group = slide.shapes.add_group_shape([shapes["a"], shapes["b"]])

        group.delete()

        assert_schema_valid(_saved(prs))


class DescribeMoviesAndGroupsSchemaValidity:
    def it_stays_valid_after_a_movie_is_deleted(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        movie = slide.shapes.add_movie(
            io.BytesIO(b"\x00" * 16),
            Inches(1),
            Inches(1),
            Inches(2),
            Inches(2),
            mime_type="video/mp4",
        )
        assert_schema_valid(_saved(prs))

        movie.delete()

        assert_schema_valid(_saved(prs))

    def it_stays_valid_after_a_group_with_animation_and_glue_is_ungrouped(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(1), Inches(1))
        b = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(3), Inches(1), Inches(1), Inches(1))
        connector = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Inches(1), Inches(4), Inches(6), Inches(4)
        )
        group = slide.shapes.add_group_shape([a, b])
        connector.begin_connect(group, 2)
        connector.end_connect(a, 0)
        Entrance.fade(slide, group)
        Entrance.fade(slide, a)
        assert_schema_valid(_saved(prs))

        group.ungroup()

        assert_schema_valid(_saved(prs))
