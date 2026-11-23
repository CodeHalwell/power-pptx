"""Regression tests for input that is hostile rather than merely wrong.

Each test here holds a boundary `SECURITY.md` promises: opening or rendering a
deck from an untrusted source reads nothing else from the host, text supplied
by a caller cannot become markup, and a spec built with ``safe=True`` cannot
ask for unbounded work.
"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import pytest

from power_pptx import Presentation
from power_pptx._svg import (
    MAX_RASTER_PIXELS,
    _capped_size,  # pyright: ignore[reportPrivateUsage]
    neutralise_external_references,
)
from power_pptx.chart.data import CategoryChartData, XyChartData
from power_pptx.compose import from_spec
from power_pptx.compose.from_spec import SpecError, from_yaml
from power_pptx.enum.chart import XL_CHART_TYPE
from power_pptx.exc import InvalidPackageError
from power_pptx.opc import serialized
from power_pptx.opc.packuri import PackURI
from power_pptx.opc.serialized import _DirPkgReader  # pyright: ignore[reportPrivateUsage]
from power_pptx.util import Inches

HERE = Path(__file__).parent
TEST_FILES = HERE / "test_files"
SMART_ART_DECK = TEST_FILES / "shp-shapes.pptx"

# -- markup a hostile string tries to smuggle in; it must come out as text --
INJECTED = '<evil:x xmlns:evil="urn:evil"/>'
HOSTILE = 'a"/>' + INJECTED + "<!-- & ' <b"

SVG_NS = 'xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'


def _rewritten(source: Path, change) -> io.BytesIO:
    """A copy of the package at `source` with `change(name, data)` applied to each member."""
    out = io.BytesIO()
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in zin.namelist():
            zout.writestr(name, change(name, zin.read(name)))
    out.seek(0)
    return out


def _saved_members(prs) -> dict[str, bytes]:
    buf = io.BytesIO()
    prs.save(buf)
    with zipfile.ZipFile(buf) as package:
        return {name: package.read(name) for name in package.namelist()}


def _assert_nothing_injected(prs) -> None:
    members = _saved_members(prs)
    assert [name for name, data in members.items() if b"<evil:x" in data] == []


class DescribeSmartArtCachedDrawing:
    """The cached drawing is the one package XML the loader does not parse itself."""

    def it_refuses_a_drawing_part_that_declares_an_external_entity(self, tmp_path):
        secret = tmp_path / "secret.txt"
        secret.write_text("TOP-SECRET")

        def plant(name: str, data: bytes) -> bytes:
            if "diagrams/drawing" not in name:
                return data
            body = data[data.index(b"<dsp:drawing") :]
            doctype = '<!DOCTYPE d [<!ENTITY x SYSTEM "%s">]>' % secret.as_uri()
            return doctype.encode() + body.replace(
                b"</dsp:drawing>", b"<dsp:leak>&x;</dsp:leak></dsp:drawing>"
            )

        prs = Presentation(_rewritten(SMART_ART_DECK, plant))
        smart_art = prs.slides[0].smart_art[0]

        with pytest.raises(InvalidPackageError, match="contains a DTD"):
            smart_art.set_text(["a", "b", "c"])
        assert all(b"TOP-SECRET" not in data for data in _saved_members(prs).values())


class DescribeZipPackageReader:
    def it_refuses_a_package_that_inflates_out_of_all_proportion(self, monkeypatch):
        monkeypatch.setattr(serialized, "MAX_INFLATED_SIZE_UNCHECKED", 1024 * 1024)

        def bloat(name: str, data: bytes) -> bytes:
            if name != "ppt/slides/slide1.xml":
                return data
            return data.replace(b"</p:sld>", b"<!--" + b" " * (8 * 1024 * 1024) + b"--></p:sld>")

        bomb = _rewritten(TEST_FILES / "test.pptx", bloat)

        with pytest.raises(InvalidPackageError, match="expand to more than 100 times"):
            Presentation(bomb)

    def it_still_opens_an_ordinary_package_under_the_same_limit(self, monkeypatch):
        monkeypatch.setattr(serialized, "MAX_INFLATED_SIZE_UNCHECKED", 0)

        assert len(Presentation(str(TEST_FILES / "test.pptx")).slides) > 0

    def it_lets_a_caller_raise_the_ratio_for_a_file_it_trusts(self, monkeypatch):
        monkeypatch.setattr(serialized, "MAX_INFLATED_SIZE_UNCHECKED", 1024)
        monkeypatch.setattr(serialized, "MAX_INFLATION_RATIO", 10_000)

        def bloat(name: str, data: bytes) -> bytes:
            if name != "ppt/slides/slide1.xml":
                return data
            return data.replace(b"</p:sld>", b"<!--" + b" " * (1024 * 1024) + b"--></p:sld>")

        assert Presentation(_rewritten(TEST_FILES / "test.pptx", bloat)) is not None


class DescribeDirectoryPackageReader:
    def it_reads_members_inside_the_directory(self):
        reader = _DirPkgReader(str(TEST_FILES / "expanded_pptx"))

        assert PackURI("/[Content_Types].xml") in reader
        assert reader[PackURI("/[Content_Types].xml")].startswith(b"<?xml")

    def it_has_no_member_outside_the_directory(self, tmp_path):
        package_dir = tmp_path / "pkg"
        package_dir.mkdir()
        (tmp_path / "secret.txt").write_text("secret")
        reader = _DirPkgReader(str(package_dir))
        # -- |PackURI| folds `..` away when it is made from a relationship, which is why
        # -- this takes one made directly; on Windows a backslash gets through as it is --
        escaping = PackURI("/../secret.txt")

        assert escaping not in reader
        with pytest.raises(KeyError):
            reader[escaping]


class DescribeCallerTextInGeneratedXml:
    """Text from a caller is data wherever it ends up in the XML."""

    @pytest.fixture
    def slide(self):
        prs = Presentation()
        return prs.slides.add_slide(prs.slide_layouts[6])

    def it_escapes_chart_values_and_number_formats(self, slide):
        data = CategoryChartData(number_format=HOSTILE)
        data.categories = ["a", "b"]
        data.add_series("s", ("1</c:v></c:pt>" + INJECTED + '<c:pt idx="9"><c:v>2', 2))
        slide.shapes.add_chart(XL_CHART_TYPE.LINE, 0, 0, Inches(3), Inches(3), data)
        xy = XyChartData(number_format=HOSTILE)
        xy.add_series("s", number_format=HOSTILE).add_data_point(1, 2)
        slide.shapes.add_chart(XL_CHART_TYPE.XY_SCATTER, 0, 0, Inches(3), Inches(3), xy)

        _assert_nothing_injected(slide.part.package.presentation_part.presentation)

    def it_keeps_a_number_format_with_markup_characters_intact(self, slide):
        data = CategoryChartData(number_format='0.0 "<kg>" & more')
        data.categories = ["a"]
        data.add_series("s", (1,))

        chart = slide.shapes.add_chart(
            XL_CHART_TYPE.BAR_CLUSTERED, 0, 0, Inches(3), Inches(3), data
        ).chart

        codes = chart._chartSpace.xpath("//c:formatCode/text()")
        assert set(codes) == {'0.0 "<kg>" & more'}

    def it_escapes_a_picture_file_name(self, slide, tmp_path):
        if os.name == "nt":
            pytest.skip('Windows file names cannot contain "')
        image = tmp_path / 'R&D "final" <v2>.png'
        image.write_bytes((TEST_FILES / "python-powered.png").read_bytes())

        picture = slide.shapes.add_picture(str(image), 0, 0)

        assert picture._element.nvPicPr.cNvPr.get("descr") == image.name

    def it_escapes_a_movie_file_name(self, slide, tmp_path):
        movie = tmp_path / "R&D demo.mp4"
        movie.write_bytes((TEST_FILES / "dummy.mp4").read_bytes())

        shape = slide.shapes.add_movie(str(movie), 0, 0, Inches(1), Inches(1))

        assert shape.name == "R&D demo.mp4"

    def it_escapes_an_ole_object_prog_id(self, slide):
        frame = slide.shapes.add_ole_object(
            str(TEST_FILES / "python-powered.png"), HOSTILE, 0, 0, Inches(1), Inches(1)
        )

        assert frame.ole_format.prog_id == HOSTILE
        _assert_nothing_injected(slide.part.package.presentation_part.presentation)


def _styled_svg(style: str) -> bytes:
    """An SVG carrying `style` both in a `<style>` element and in a `style` attribute."""
    attribute = style.replace('"', "&quot;")
    return f'<svg {SVG_NS}><style>a{{{style}}}</style><rect style="{attribute}"/></svg>'.encode()


class DescribeNeutraliseExternalReferences:
    def it_returns_a_self_contained_svg_unchanged(self):
        svg = (
            f'<svg {SVG_NS}><defs><g id="a"/></defs><use href="#a"/>'
            '<image href="data:image/png;base64,AAAA"/><rect fill="url(#g)"/></svg>'
        ).encode()

        assert neutralise_external_references(svg) is svg

    @pytest.mark.parametrize(
        "style",
        [
            "fill:url('#gradient')",
            'clip-path:url("#clip")',
            "fill:url( #gradient )",
            "fill:url( '#gradient' )",
            "background:url('data:image/png;base64,AAAA')",
            "FILL:URL(#gradient)",
        ],
    )
    def it_keeps_internal_css_references_however_they_are_quoted(self, style):
        svg = _styled_svg(style)

        assert neutralise_external_references(svg) is svg

    @pytest.mark.parametrize(
        "style",
        [
            "fill:url('file:///etc/passwd')",
            'fill:url( "ftp://h/x" )',
            "fill:url( other.svg#a )",
            "fill:url('  //h/x')",
        ],
    )
    def it_removes_external_css_references_however_they_are_quoted(self, style):
        svg = _styled_svg(style)

        cleaned = neutralise_external_references(svg).decode()

        assert cleaned.count("fill:none") == 2
        assert "url(" not in cleaned

    def it_removes_everything_that_names_another_resource(self):
        svg = (
            '<?xml version="1.0"?><?xml-stylesheet href="file:///etc/x.css"?>'
            '<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            f"<svg {SVG_NS}>"
            "<style>@import url('ftp://h/x.css'); a{fill:url(#ok);b:url( 'file:///etc/hosts' )}"
            "</style><text>a&x;b</text>"
            '<image xlink:href="file:///etc/passwd" href="FILE:///x" x="1"/>'
            '<use href="other.svg#a"/><rect style="fill:url(ftp://h/p)" fill="url(#g)"/>'
            '<a href=" #frag">kept</a></svg>'
        ).encode()

        cleaned = neutralise_external_references(svg).decode()

        for gone in ("file:", "FILE:", "ftp:", "other.svg", "DOCTYPE", "&x;", "stylesheet"):
            assert gone not in cleaned
        for kept in ("url(#ok)", 'fill="url(#g)"', 'href=" #frag"', "<text>ab</text>", 'x="1"'):
            assert kept in cleaned

    def it_replaces_a_document_it_cannot_parse_with_an_empty_one(self):
        cleaned = neutralise_external_references(b'<svg><image href="file:///x">')

        assert b"file:" not in cleaned
        assert cleaned.startswith(b"<svg")


class DescribeSvgRasterSize:
    def it_leaves_an_ordinary_size_to_the_rasteriser(self):
        assert (
            _capped_size(b'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"/>')
            is None
        )

    @pytest.mark.parametrize(
        "attrs",
        [
            'width="30000" height="30000"',
            'width="800cm" height="800cm"',
            'viewBox="0 0 30000 30000"',
        ],
    )
    def it_scales_an_oversize_svg_down_to_the_pixel_budget(self, attrs):
        size = _capped_size(f'<svg xmlns="http://www.w3.org/2000/svg" {attrs}/>'.encode())

        assert size is not None
        width, height = size
        assert width == height
        assert 0.9 * MAX_RASTER_PIXELS < width * height <= MAX_RASTER_PIXELS


class DescribeRenderingAnUntrustedDeck:
    def it_starts_libreoffice_with_links_and_macros_blocked(self, tmp_path):
        from power_pptx.render import _seed_profile  # pyright: ignore[reportPrivateUsage]

        _seed_profile(tmp_path / "profile")

        settings = (tmp_path / "profile" / "user" / "registrymodifications.xcu").read_text()
        assert 'oor:name="BlockUntrustedRefererLinks" oor:op="fuse"><value>true' in settings
        assert 'oor:name="DisableMacrosExecution" oor:op="fuse"><value>true' in settings

    def it_takes_external_references_out_of_the_svgs_in_the_copy_it_renders(self, tmp_path):
        from power_pptx.render import _neutralise_deck  # pyright: ignore[reportPrivateUsage]

        hostile = f'<svg {SVG_NS}><image href="file:///etc/passwd"/></svg>'.encode()
        deck = tmp_path / "deck.pptx"
        with zipfile.ZipFile(deck, "w") as package:
            package.writestr("ppt/media/image1.svg", hostile)
            package.writestr("ppt/media/image2.png", hostile)  # -- an SVG by content only --
            package.writestr("ppt/slides/slide1.xml", b"<p:sld/>")

        _neutralise_deck(deck)

        with zipfile.ZipFile(deck) as package:
            assert b"file:" not in package.read("ppt/media/image1.svg")
            assert b"file:" not in package.read("ppt/media/image2.png")
            assert package.read("ppt/slides/slide1.xml") == b"<p:sld/>"

    def it_leaves_a_deck_without_svg_as_it_is(self, tmp_path):
        from power_pptx.render import _neutralise_deck  # pyright: ignore[reportPrivateUsage]

        deck = tmp_path / "deck.pptx"
        deck.write_bytes((TEST_FILES / "test.pptx").read_bytes())

        _neutralise_deck(deck)

        assert deck.read_bytes() == (TEST_FILES / "test.pptx").read_bytes()


def _figure_spec(figure="<p>hello</p>", **keys):
    return {"slides": [{"layout": "figure", "title": "Chart", "figure": figure, **keys}]}


@pytest.fixture
def figures_added(monkeypatch):
    """Record the figure value each figure slide hands to its recipe."""
    from power_pptx.design import figures

    added: list = []
    monkeypatch.setattr(
        figures, "add_html_figure", lambda slide, html, *a, **options: added.append(html)
    )
    monkeypatch.setattr(
        "power_pptx.shapes.shapetree._BaseGroupShapes.add_svg_picture",
        lambda self, svg, *a, **k: added.append(svg),
    )
    return added


class DescribeSafeModeLimits:
    @pytest.mark.parametrize(
        ("options", "where"),
        [
            ({"timeout_ms": 600_000}, "timeout_ms"),
            ({"device_scale_factor": 50}, "device_scale_factor"),
            ({"viewport": [100_000, 720]}, "viewport"),
        ],
    )
    def it_refuses_a_capture_larger_than_a_figure_needs(self, options, where):
        with pytest.raises(SpecError, match=where + ".*safe=True may ask for"):
            from_spec(_figure_spec(html_options=options), safe=True)

    def it_leaves_those_options_to_a_trusted_spec(self, figures_added):
        from_spec(_figure_spec(html_options={"timeout_ms": 600_000}))

        assert figures_added == ["<p>hello</p>"]

    def it_checks_a_string_the_recipe_would_open_as_a_file(self, tmp_path):
        # -- starts with `<` but is not markup to the recipe, which would open it --
        with pytest.raises(SpecError, match="outside base_dir"):
            from_spec(_figure_spec("<1/../../outside.png"), safe=True, base_dir=tmp_path)

    def it_refuses_yaml_aliases(self, tmp_path):
        pytest.importorskip("yaml")
        spec = tmp_path / "deck.yml"
        spec.write_text(
            "vars:\n  a: &a [x, x, x]\n  b: &b [*a, *a, *a]\nslides:\n  - layout: title\n"
            "    title: t\n"
        )

        with pytest.raises(ValueError, match="uses an alias"):
            from_yaml(str(spec), safe=True)
        assert from_yaml(str(spec)) is not None
