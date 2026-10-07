"""Schema and hierarchy validity of decks built by ``apply_template`` / ``import_slide``.

Both operations copy slide masters, layouts and themes between packages.  Getting a
``p:sldLayoutIdLst`` wrong (an r:id that resolves to the theme, an unlisted layout, a repeated
id) or losing a picture's relationship yields a deck that reopens in python-pptx but that
PowerPoint "repairs", so each deck below must pass the ISO-29500 schema checks *and* the
master/layout hierarchy checks.
"""

from __future__ import annotations

import io
import warnings
from typing import Callable

import pytest

from power_pptx import Presentation
from power_pptx.util import Inches

from .hierarchy_decks import (
    BLUE,
    RED,
    add_logo,
    add_theme_image_fill,
    needs_schema_validator,
    saved_bytes,
    solid_png,
)
from .hierarchy_validator import iter_hierarchy_violations
from .oxml_schema_validator import assert_schema_valid


def _branded_template() -> Presentation:
    """A template whose master, a layout and whose theme all carry pictures."""
    template = Presentation()
    add_logo(template, template.slide_master.part, solid_png(RED), shape_id=900)
    add_logo(template, template.slide_layouts[0].part, solid_png(BLUE), shape_id=901)
    add_theme_image_fill(template, solid_png(RED))
    template.slides.add_slide(template.slide_layouts[0])
    return template


def _two_master_template() -> Presentation:
    template = Presentation()
    donor = Presentation()
    donor.slides.add_slide(donor.slide_layouts[0])
    template.import_slide(donor.slides[0], merge_master="clone")
    return template


def _deck_with_slides() -> Presentation:
    deck = Presentation()
    deck.slides.add_slide(deck.slide_layouts[0]).shapes.title.text = "Title"
    deck.slides.add_slide(deck.slide_layouts[1]).shapes.title.text = "Content"
    deck.slides.add_slide(deck.slide_layouts[6])
    return deck


def _deck_apply_default_template() -> bytes:
    deck = _deck_with_slides()
    deck.apply_template(io.BytesIO(saved_bytes(Presentation())))
    return saved_bytes(deck)


def _deck_apply_branded_template() -> bytes:
    deck = _deck_with_slides()
    deck.apply_template(io.BytesIO(saved_bytes(_branded_template())))
    return saved_bytes(deck)


def _deck_apply_two_master_template() -> bytes:
    deck = _deck_with_slides()
    deck.apply_template(io.BytesIO(saved_bytes(_two_master_template())))
    return saved_bytes(deck)


def _deck_apply_template_twice() -> bytes:
    deck = _deck_with_slides()
    deck.apply_template(io.BytesIO(saved_bytes(_branded_template())))
    deck.apply_template(io.BytesIO(saved_bytes(_two_master_template())))
    return saved_bytes(deck)


def _deck_import_slides_cloning_a_branded_master() -> bytes:
    src = _branded_template()
    src.slides.add_slide(src.slide_layouts[6]).shapes.add_picture(
        io.BytesIO(solid_png(RED)), Inches(1), Inches(1), Inches(1), Inches(1)
    )
    dst = Presentation()
    dst.import_slide(src.slides[0])
    dst.import_slide(src.slides[1], merge_master="clone")
    dst.import_slide(src.slides[0])
    return saved_bytes(dst)


def _deck_import_slide_with_slide_jumps() -> bytes:
    src = Presentation()
    jumper = src.slides.add_slide(src.slide_layouts[6])
    target = src.slides.add_slide(src.slide_layouts[6])
    target.shapes.add_picture(
        io.BytesIO(solid_png(RED)), Inches(1), Inches(1), Inches(1), Inches(1)
    )
    box = jumper.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
    box.text_frame.text = "shape jump"
    box.click_action.target_slide = target
    run = jumper.shapes.add_textbox(Inches(1), Inches(3), Inches(3), Inches(1))
    run.text_frame.paragraphs[0].add_run().text = "run jump"
    run.text_frame.paragraphs[0].runs[0].hyperlink.target_slide = target
    selfjump = jumper.shapes.add_textbox(Inches(1), Inches(5), Inches(3), Inches(1))
    selfjump.text_frame.text = "self jump"
    selfjump.click_action.target_slide = jumper
    dst = Presentation()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        dst.import_slide(jumper)
    return saved_bytes(dst)


def _deck_duplicate_slides_within_one_deck() -> bytes:
    prs = Presentation()
    first = prs.slides.add_slide(prs.slide_layouts[6])
    second = prs.slides.add_slide(prs.slide_layouts[6])
    second.shapes.add_picture(
        io.BytesIO(solid_png(BLUE)), Inches(1), Inches(1), Inches(1), Inches(1)
    )
    box = first.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
    box.text_frame.text = "to second"
    box.click_action.target_slide = second
    first.notes_slide.notes_text_frame.text = "notes"
    prs.import_slide(first)
    prs.import_slide(second)
    return saved_bytes(prs)


def _deck_import_after_apply_template() -> bytes:
    template = _branded_template()
    deck = _deck_with_slides()
    deck.apply_template(io.BytesIO(saved_bytes(template)))
    deck.import_slide(Presentation(io.BytesIO(saved_bytes(template))).slides[0])
    return saved_bytes(deck)


_DECK_BUILDERS: dict[str, Callable[[], bytes]] = {
    "apply_default_template": _deck_apply_default_template,
    "apply_branded_template": _deck_apply_branded_template,
    "apply_two_master_template": _deck_apply_two_master_template,
    "apply_template_twice": _deck_apply_template_twice,
    "import_cloning_a_branded_master": _deck_import_slides_cloning_a_branded_master,
    "import_slide_with_slide_jumps": _deck_import_slide_with_slide_jumps,
    "duplicate_slides_within_one_deck": _deck_duplicate_slides_within_one_deck,
    "import_after_apply_template": _deck_import_after_apply_template,
}


@needs_schema_validator
class DescribeCopiedHierarchySchemaValidity:
    @pytest.mark.parametrize("name", sorted(_DECK_BUILDERS))
    def it_validates_against_the_ooxml_schema(self, name):
        assert_schema_valid(_DECK_BUILDERS[name]())

    @pytest.mark.parametrize("name", sorted(_DECK_BUILDERS))
    def it_keeps_the_master_and_layout_lists_consistent(self, name):
        assert list(iter_hierarchy_violations(_DECK_BUILDERS[name]())) == []
