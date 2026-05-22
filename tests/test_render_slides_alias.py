"""Unit tests for ``power_pptx.render.render_slides`` argument validation.

The end-to-end behaviour requires LibreOffice and is covered by
``tests/test_render.py``; this file only exercises the new
``name_template`` validation path that runs *before* soffice is called.
"""

from __future__ import annotations

import pytest

from power_pptx import Presentation
from power_pptx.render import render_slides


@pytest.fixture
def prs():
    p = Presentation()
    p.slides.add_slide(p.slide_layouts[6])
    return p


class DescribeRenderSlidesValidation:
    def it_rejects_name_template_without_a_placeholder(self, prs):
        # ``"slide.png"`` produces the same filename for every slide,
        # which would silently overwrite all but the last PNG.
        with pytest.raises(ValueError, match="same filename"):
            render_slides(prs, name_template="slide.png")

    def it_rejects_name_template_with_bad_format_spec(self, prs):
        # ``"{}{}"`` requires two positional args but we only pass one;
        # we should fail loudly rather than fall back to the literal.
        with pytest.raises(ValueError, match="not a valid str.format"):
            render_slides(prs, name_template="slide-{}-{}.png")
