"""Integration tests for the ``power_pptx.compose`` package.

These guard the public surface that Phase 7 promises:
``from_spec`` / ``import_slide`` / ``apply_template`` are all importable
from the same module path.  The implementations themselves are exercised
by their own dedicated test suites; this file just locks in re-exports.
"""

from __future__ import annotations

import io

import pytest

import power_pptx.compose as compose
from power_pptx import Presentation


class Describe_compose_package:
    def it_reexports_from_spec(self):
        from power_pptx.compose.from_spec import from_spec

        assert compose.from_spec is from_spec

    def it_reexports_import_slide(self):
        from power_pptx._slide_importer import import_slide

        assert compose.import_slide is import_slide

    def it_reexports_apply_template(self):
        from power_pptx._template_applier import apply_template

        assert compose.apply_template is apply_template

    def it_advertises_all_composition_entry_points(self):
        assert set(compose.__all__) == {
            "from_spec", "from_yaml", "from_html", "import_slide", "apply_template"
        }

    def it_can_drive_from_spec_end_to_end(self):
        prs = compose.from_spec(
            {
                "slides": [
                    {"layout": "title", "title": "Hello", "subtitle": "World"},
                    {"layout": "bullets", "title": "Bullets", "bullets": ["a", "b"]},
                ]
            }
        )
        assert len(prs.slides) == 2


def _deck(*texts: str) -> Presentation:
    prs = Presentation()
    for text in texts:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = text
    return prs


def _titles(prs: Presentation) -> list[str]:
    return [slide.shapes.title.text for slide in prs.slides]


def _saved(prs: Presentation) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


class Describe_compose_import_slide:
    """The calls shown in compose.md / docs/user/compose.rst must work as written."""

    def it_accepts_the_documented_presentation_and_slide_objects(self):
        src = _deck("one", "two", "three", "four")
        dst = _deck("cover")

        new_slide = compose.import_slide(dst, src.slides[3], merge_master="dedupe")

        assert _titles(dst) == ["cover", "four"]
        assert new_slide == dst.slides[1]
        assert len(dst.slide_masters) == 1
        assert _titles(Presentation(io.BytesIO(_saved(dst)))) == ["cover", "four"]

    def it_defaults_merge_master_to_dedupe(self):
        src = _deck("one")
        dst = _deck("cover")

        compose.import_slide(dst, src.slides[0])
        assert len(dst.slide_masters) == 1

        compose.import_slide(dst, src.slides[0], "clone")
        assert len(dst.slide_masters) == 2

    def it_still_accepts_the_part_based_call(self):
        src = _deck("one")
        dst = _deck("cover")

        positional = compose.import_slide(src.slides[0].part, dst.part)
        keywords = compose.import_slide(
            src_slide_part=src.slides[0].part, dst_prs_part=dst.part, merge_master="clone"
        )

        assert _titles(dst) == ["cover", "one", "one"]
        assert positional == dst.slides[1]
        assert keywords == dst.slides[2]
        assert len(dst.slide_masters) == 2

    def it_validates_merge_master(self):
        src = _deck("one")
        dst = _deck("cover")

        with pytest.raises(ValueError, match="merge_master must be 'dedupe' or 'clone'"):
            compose.import_slide(dst, src.slides[0], merge_master="dedup")

        assert _titles(dst) == ["cover"]

    @pytest.mark.parametrize(
        ("make_args", "message"),
        [
            (lambda src, dst: (dst, src), "more than one destination"),
            (lambda src, dst: (src.slides[0], src.slides[0]), "more than one slide"),
            (lambda src, dst: (dst,), "needs the Slide to import"),
            (lambda src, dst: (src.slides[0],), "needs the destination Presentation"),
            (lambda src, dst: (dst, src.slide_layouts[0]), "got SlideLayout"),
            (lambda src, dst: (dst, "deck.pptx"), "got str"),
        ],
    )
    def it_explains_wrong_arguments(self, make_args, message):
        src = _deck("one")
        dst = _deck("cover")

        with pytest.raises(TypeError, match=message):
            compose.import_slide(*make_args(src, dst))

        assert _titles(dst) == ["cover"]


class Describe_compose_apply_template:
    def it_accepts_the_documented_presentation_and_path(self, tmp_path):
        template_path = tmp_path / "brand-template.potx"
        template = Presentation()
        template.slide_master.name = "Brand master"
        template.save(str(template_path))
        dst = _deck("one", "two")

        compose.apply_template(dst, str(template_path))

        assert dst.slide_master.name == "Brand master"
        assert _titles(dst) == ["one", "two"]
        reopened = Presentation(io.BytesIO(_saved(dst)))
        assert reopened.slide_master.name == "Brand master"
        assert len(reopened.slide_layouts) == 11

    def it_accepts_a_pathlib_path_a_stream_or_an_open_presentation(self, tmp_path):
        template = Presentation()
        template.slide_master.name = "Brand master"
        template_path = tmp_path / "brand.pptx"
        template.save(str(template_path))

        for source in (template_path, io.BytesIO(_saved(template)), template):
            dst = _deck("one")
            compose.apply_template(dst, source)
            assert dst.slide_master.name == "Brand master"

    def it_still_accepts_the_part_based_call(self):
        template = Presentation()
        template.slide_master.name = "Brand master"

        positional = _deck("one")
        compose.apply_template(positional.part, template.part)
        assert positional.slide_master.name == "Brand master"

        keywords = _deck("one")
        compose.apply_template(dst_prs_part=keywords.part, template_prs_part=template.part)
        assert keywords.slide_master.name == "Brand master"

    @pytest.mark.parametrize(
        ("make_args", "message"),
        [
            (lambda dst: (dst,), "needs a template"),
            (lambda dst: (), "needs the Presentation to modify"),
            (lambda dst: ("deck.pptx", "brand.potx"), "takes a Presentation to modify, got str"),
            (lambda dst: (dst, 42), "got int"),
            (lambda dst: (dst, dst.slides[0]), "got Slide"),
        ],
    )
    def it_explains_wrong_arguments(self, make_args, message):
        dst = _deck("one")

        with pytest.raises(TypeError, match=message):
            compose.apply_template(*make_args(dst))

        assert len(dst.slide_masters) == 1
