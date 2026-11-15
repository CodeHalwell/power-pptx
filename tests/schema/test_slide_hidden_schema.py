"""Validate slides hidden with `Slide.hidden` against the ISO-29500 schema."""

from __future__ import annotations

import io
import zipfile

import pytest

from power_pptx import Presentation

from .oxml_schema_validator import (
    assert_schema_valid,
    iter_schema_violations,
    schema_validation_available,
)

pytestmark = pytest.mark.skipif(
    not schema_validation_available(),
    reason="lxml or the bundled ISO-29500 XSD schemas are unavailable",
)


def _saved(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _deck(hidden: list[bool]):
    prs = Presentation()
    for value in hidden:
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        slide.shapes.title.text_frame.text = "hidden" if value else "shown"
        slide.hidden = value
    return prs


class DescribeHiddenSlideSchemaValidity:
    @pytest.mark.parametrize(
        "hidden",
        [[True], [False, True, False], [True, True, True]],
        ids=["only_slide", "middle_slide", "every_slide"],
    )
    def it_validates_against_the_ooxml_schema(self, hidden):
        blob = _saved(_deck(hidden))

        assert_schema_valid(blob)
        # -- guard against passing vacuously: the attribute is really there --
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            for n, value in enumerate(hidden, start=1):
                xml = zf.read("ppt/slides/slide%d.xml" % n)
                assert (b' show="0"' in xml) is value

    def it_validates_a_slide_that_was_hidden_and_then_shown_again(self):
        prs = _deck([True, True])
        for slide in prs.slides:
            slide.hidden = False

        blob = _saved(prs)

        assert_schema_valid(blob)
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            assert b"show=" not in zf.read("ppt/slides/slide1.xml")

    def it_detects_a_show_attribute_that_is_not_a_boolean(self):
        # -- self-test: the validator does check this attribute --
        prs = _deck([False])
        prs.slides[0]._element.set("show", "no")

        violations = list(iter_schema_violations(_saved(prs)))

        assert any("show" in message for _, message in violations), violations
