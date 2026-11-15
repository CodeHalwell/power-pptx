"""Round-trip tests for `Slide.hidden`."""

from __future__ import annotations

import io

from power_pptx import Presentation

from .round_trip import assert_round_trip, round_trip_diff


def _deck(slides: int = 3):
    prs = Presentation()
    for _ in range(slides):
        prs.slides.add_slide(prs.slide_layouts[6])
    return prs


def _saved(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


class DescribeHiddenSlideRoundTrip:
    def it_round_trips_a_hidden_slide(self):
        prs = _deck()
        prs.slides[1].hidden = True

        assert_round_trip(prs)

    def it_keeps_slides_hidden_through_the_round_trip(self):
        prs = _deck()
        prs.slides[0].hidden = True
        prs.slides[2].hidden = True

        twice = Presentation(io.BytesIO(_saved(Presentation(io.BytesIO(_saved(prs))))))

        assert [slide.hidden for slide in twice.slides] == [True, False, True]

    def it_round_trips_a_slide_that_was_hidden_and_then_shown_again(self):
        prs = _deck()
        untouched = _saved(prs)
        prs.slides[1].hidden = True
        prs.slides[1].hidden = False

        assert _saved(prs) == untouched
        assert_round_trip(prs)

    def it_does_not_alter_a_deck_after_hidden_is_read(self):
        prs = _deck()
        prs.slides[1].hidden = True
        before = _saved(prs)

        assert [slide.hidden for slide in prs.slides] == [False, True, False]

        assert _saved(prs) == before
        assert round_trip_diff(prs) == {}
