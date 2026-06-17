"""Tiny shared helpers for the stress-test decks."""

from __future__ import annotations

from power_pptx import Presentation
from power_pptx.util import Inches

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


def deck() -> Presentation:
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    return prs


def blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])
