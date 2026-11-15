"""Opening and saving the kinds of presentation package: .pptx, .potx, .ppsx, .pptm.

A presentation, a template and a slide show share the same `p:presentation`
main part; only that part's content type in `[Content_Types].xml` differs.
PowerPoint insists the content type agrees with the file extension, so the
library has to accept all of them on open and write the one that matches the
target on save.
"""

from __future__ import annotations

import io
import pathlib
import re
import zipfile

import pytest

from power_pptx import Presentation
from power_pptx.compose import apply_template
from power_pptx.opc.constants import CONTENT_TYPE as CT

PRESENTATION = CT.PML_PRESENTATION_MAIN
TEMPLATE = CT.PML_TEMPLATE_MAIN
SLIDESHOW = CT.PML_SLIDESHOW_MAIN
MACRO_ENABLED = CT.PML_PRES_MACRO_MAIN


def _deck_bytes(master_name: str = "Brand master") -> bytes:
    prs = Presentation()
    prs.slide_master.name = master_name
    prs.slides.add_slide(prs.slide_layouts[0]).shapes.title.text = "Hello"
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _retyped(deck: bytes, main_content_type: str) -> bytes:
    """Return `deck` with its main part declared as `main_content_type`.

    This is exactly how PowerPoint's own .potx / .ppsx / .pptm differ from a
    .pptx: one attribute value in `[Content_Types].xml`.
    """
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(deck)) as zin, zipfile.ZipFile(
        out, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for name in zin.namelist():
            data = zin.read(name)
            if name == "[Content_Types].xml":
                assert PRESENTATION.encode() in data
                data = data.replace(PRESENTATION.encode(), main_content_type.encode())
            zout.writestr(name, data)
    return out.getvalue()


def _main_content_type(package: bytes | pathlib.Path) -> str:
    source = io.BytesIO(package) if isinstance(package, bytes) else package
    with zipfile.ZipFile(source) as z:
        content_types = z.read("[Content_Types].xml").decode()
    match = re.search(
        r'<Override PartName="/ppt/presentation.xml" ContentType="([^"]+)"', content_types
    )
    assert match is not None, content_types
    return match.group(1)


@pytest.fixture
def potx_path(tmp_path: pathlib.Path) -> pathlib.Path:
    """A real template: a generated deck whose main part is typed as a template."""
    path = tmp_path / "brand.potx"
    path.write_bytes(_retyped(_deck_bytes(), TEMPLATE))
    assert _main_content_type(path) == TEMPLATE
    return path


@pytest.fixture
def ppsx_path(tmp_path: pathlib.Path) -> pathlib.Path:
    """A real slide show: a generated deck whose main part is typed as a slide show."""
    path = tmp_path / "show.ppsx"
    path.write_bytes(_retyped(_deck_bytes(), SLIDESHOW))
    return path


class DescribeOpeningPresentationPackages:
    def it_opens_a_template(self, potx_path):
        prs = Presentation(str(potx_path))

        assert [s.shapes.title.text for s in prs.slides] == ["Hello"]
        assert prs.slide_master.name == "Brand master"
        assert len(prs.slide_layouts) == 11
        assert prs.part.content_type == TEMPLATE

    def it_opens_a_slide_show(self, ppsx_path):
        prs = Presentation(str(ppsx_path))

        assert [s.shapes.title.text for s in prs.slides] == ["Hello"]
        assert prs.part.content_type == SLIDESHOW

    def it_opens_them_from_a_path_object_or_a_stream_too(self, potx_path, ppsx_path):
        for path in (potx_path, ppsx_path):
            assert len(Presentation(path).slides) == 1
            assert len(Presentation(io.BytesIO(path.read_bytes())).slides) == 1

    def it_still_opens_a_macro_enabled_presentation(self):
        prs = Presentation(io.BytesIO(_retyped(_deck_bytes(), MACRO_ENABLED)))

        assert len(prs.slides) == 1
        assert prs.part.content_type == MACRO_ENABLED

    def but_it_rejects_a_package_that_is_not_a_presentation(self):
        docx_like = _retyped(_deck_bytes(), CT.WML_DOCUMENT_MAIN)

        with pytest.raises(ValueError, match="is not a PowerPoint file, content type is"):
            Presentation(io.BytesIO(docx_like))

    def it_applies_a_template_given_as_a_potx_path(self, potx_path):
        """The documented `apply_template(prs, "brand-template.potx")`."""
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[1])

        apply_template(prs, str(potx_path))

        assert prs.slide_master.name == "Brand master"
        # -- adopting a template's masters does not make the deck a template --
        saved = io.BytesIO()
        prs.save(saved)
        assert _main_content_type(saved.getvalue()) == PRESENTATION

    def it_builds_a_deck_from_a_potx_with_from_spec(self, potx_path):
        from power_pptx.compose import from_spec

        prs = from_spec(
            {
                "template": str(potx_path),
                "slides": [{"layout": "title", "title": "Q4", "subtitle": "Review"}],
            }
        )

        assert prs.slide_master.name == "Brand master"
        saved = io.BytesIO()
        prs.save(saved)
        assert _main_content_type(saved.getvalue()) == PRESENTATION


class DescribeSavingPresentationPackages:
    @pytest.mark.parametrize(
        ("opened_as", "filename", "expected"),
        [
            # -- the common case: start from a template, hand over a deck --
            (TEMPLATE, "deck.pptx", PRESENTATION),
            (TEMPLATE, "copy.potx", TEMPLATE),
            (TEMPLATE, "show.ppsx", SLIDESHOW),
            (SLIDESHOW, "deck.pptx", PRESENTATION),
            (SLIDESHOW, "show.ppsx", SLIDESHOW),
            (SLIDESHOW, "brand.potx", TEMPLATE),
            (PRESENTATION, "deck.pptx", PRESENTATION),
            (PRESENTATION, "brand.potx", TEMPLATE),
            (PRESENTATION, "show.ppsx", SLIDESHOW),
            # -- the extension is matched without regard to case --
            (TEMPLATE, "DECK.PPTX", PRESENTATION),
            (PRESENTATION, "Brand.PotX", TEMPLATE),
            # -- an extension that names no kind of presentation: a presentation --
            (TEMPLATE, "deck.bin", PRESENTATION),
            (TEMPLATE, "deck", PRESENTATION),
        ],
    )
    def it_writes_the_kind_of_package_the_filename_asks_for(
        self, tmp_path, opened_as, filename, expected
    ):
        prs = Presentation(io.BytesIO(_retyped(_deck_bytes(), opened_as)))
        path = tmp_path / filename

        prs.save(str(path))

        assert _main_content_type(path) == expected
        reopened = Presentation(str(path))
        assert [s.shapes.title.text for s in reopened.slides] == ["Hello"]

    def it_accepts_a_path_object(self, tmp_path):
        prs = Presentation(io.BytesIO(_retyped(_deck_bytes(), TEMPLATE)))

        prs.save(tmp_path / "deck.pptx")
        prs.save(tmp_path / "brand.potx")

        assert _main_content_type(tmp_path / "deck.pptx") == PRESENTATION
        assert _main_content_type(tmp_path / "brand.potx") == TEMPLATE

    @pytest.mark.parametrize("opened_as", [TEMPLATE, SLIDESHOW, PRESENTATION])
    def it_writes_a_presentation_to_a_stream(self, opened_as):
        prs = Presentation(io.BytesIO(_retyped(_deck_bytes(), opened_as)))
        stream = io.BytesIO()

        prs.save(stream)

        assert _main_content_type(stream.getvalue()) == PRESENTATION

    def it_decides_afresh_on_every_save(self, tmp_path):
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[0])

        prs.save(str(tmp_path / "brand.potx"))
        prs.save(str(tmp_path / "deck.pptx"))
        stream = io.BytesIO()
        prs.save(stream)

        assert _main_content_type(tmp_path / "brand.potx") == TEMPLATE
        assert _main_content_type(tmp_path / "deck.pptx") == PRESENTATION
        assert _main_content_type(stream.getvalue()) == PRESENTATION

    @pytest.mark.parametrize("filename", ["deck.pptm", "deck.pptx", "brand.potx", None])
    def it_leaves_a_macro_enabled_presentation_macro_enabled(self, tmp_path, filename):
        # Its content type says the package carries a VBA project; a new file
        # name does not remove the macros, so it must not claim otherwise.
        prs = Presentation(io.BytesIO(_retyped(_deck_bytes(), MACRO_ENABLED)))

        if filename is None:
            target = io.BytesIO()
            prs.save(target)
            saved = target.getvalue()
        else:
            prs.save(str(tmp_path / filename))
            saved = (tmp_path / filename).read_bytes()

        assert _main_content_type(saved) == MACRO_ENABLED

    def it_changes_nothing_but_the_main_content_type(self, potx_path):
        from .round_trip import _canonicalize_xml, _parts

        original = _parts(potx_path.read_bytes())
        stream = io.BytesIO()
        Presentation(str(potx_path)).save(stream)
        saved = _parts(stream.getvalue())

        assert sorted(saved) == sorted(original)
        changed = [
            name
            for name in original
            if name.endswith((".xml", ".rels"))
            and _canonicalize_xml(original[name]) != _canonicalize_xml(saved[name])
        ]
        assert changed == ["[Content_Types].xml"]
        assert saved["[Content_Types].xml"].count(PRESENTATION.encode()) == 1
        assert TEMPLATE.encode() not in saved["[Content_Types].xml"]


class DescribePresentationPackageSchemaValidity:
    def it_saves_schema_valid_packages_of_each_kind(self, tmp_path, potx_path):
        from power_pptx.validation import iter_schema_violations

        prs = Presentation(str(potx_path))
        prs.slides.add_slide(prs.slide_layouts[1]).shapes.title.text = "More"

        for filename in ("deck.pptx", "brand.potx", "show.ppsx"):
            path = tmp_path / ("out-" + filename)
            prs.save(str(path))
            assert list(iter_schema_violations(path.read_bytes())) == [], filename
