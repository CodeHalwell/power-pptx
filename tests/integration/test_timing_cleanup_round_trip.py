"""Timing trees cleaned by shape deletion must survive a save -> open -> save cycle unchanged."""

from __future__ import annotations

import io

from power_pptx import Presentation
from power_pptx.animation import Entrance
from power_pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from power_pptx.util import Inches

from ..unitutil.timing import install_timing, powerpoint_timing_xml
from .round_trip import assert_round_trip


def _slide_with_shapes(count):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    shapes = [
        slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0.5 + i), Inches(1), Inches(0.5), Inches(0.5)
        )
        for i in range(count)
    ]
    return prs, slide, shapes


class DescribeTimingCleanupRoundTrip:
    def it_round_trips_a_main_sequence_deck_after_deleting_shapes(self):
        prs, slide, (a, b, c, d, e) = _slide_with_shapes(5)
        install_timing(
            slide,
            powerpoint_timing_xml(
                [
                    (a.shape_id, "clickEffect"),
                    (b.shape_id, "withEffect"),
                    (c.shape_id, "afterEffect"),
                    (d.shape_id, "clickEffect"),
                ],
                media=[("video", e.shape_id)],
                bld=[a.shape_id, b.shape_id, c.shape_id, d.shape_id],
            ),
        )
        a.delete()
        c.delete()
        d.delete()

        assert_round_trip(prs)

    def it_round_trips_an_emptied_main_sequence_beside_play_controls(self):
        prs, slide, (a, b, media_shape) = _slide_with_shapes(3)
        install_timing(
            slide,
            powerpoint_timing_xml(
                [(a.shape_id, "clickEffect"), (b.shape_id, "withEffect")],
                media=[("video", media_shape.shape_id)],
            ),
        )
        slide.animations.clear()

        assert_round_trip(prs)

    def it_round_trips_a_deck_after_deleting_a_movie(self):
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
        movie.delete()

        assert_round_trip(prs)

    def it_round_trips_a_deck_after_ungrouping_an_animated_group(self):
        prs, slide, (a, b) = _slide_with_shapes(2)
        connector = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Inches(1), Inches(4), Inches(6), Inches(4)
        )
        group = slide.shapes.add_group_shape([a, b])
        connector.begin_connect(group, 2)
        connector.end_connect(a, 0)
        Entrance.fade(slide, group)
        Entrance.fade(slide, a)
        group.ungroup()

        assert_round_trip(prs)
