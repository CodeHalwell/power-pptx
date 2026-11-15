"""Round-trip tests for `Presentation.set_slide_size`."""

from __future__ import annotations

import io

import pytest

from power_pptx import Presentation
from power_pptx.util import MAX_SLIDE_SIZE, MIN_SLIDE_SIZE, Inches

from .round_trip import assert_round_trip

_SIZES = [
    (Inches(13.333), Inches(7.5), False),
    (MAX_SLIDE_SIZE, MIN_SLIDE_SIZE, False),
    (Inches(40) / 3, Inches(15) / 2, False),
    (Inches(7680 / 96), Inches(1080 / 96), True),
    (Inches(0.25), Inches(3), True),
]
_IDS = ["widescreen", "limits", "float_arithmetic", "fit_video_wall", "fit_too_small"]


def _saved(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


class DescribeSlideSizeRoundTrip:
    @pytest.mark.parametrize(("width", "height", "fit"), _SIZES, ids=_IDS)
    def it_round_trips_a_slide_size(self, width, height, fit):
        prs = Presentation()
        prs.set_slide_size(width, height, fit=fit)
        prs.slides.add_slide(prs.slide_layouts[6])

        assert_round_trip(prs)

    @pytest.mark.parametrize(("width", "height", "fit"), _SIZES, ids=_IDS)
    def it_reads_back_the_size_that_was_reported(self, width, height, fit):
        prs = Presentation()
        size = prs.set_slide_size(width, height, fit=fit)

        twice = Presentation(io.BytesIO(_saved(Presentation(io.BytesIO(_saved(prs))))))

        assert (twice.slide_width, twice.slide_height) == (size.width, size.height)
