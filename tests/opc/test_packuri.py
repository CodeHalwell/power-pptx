"""Unit-test suite for the `power_pptx.opc.packuri` module."""

from __future__ import annotations

import pytest

from power_pptx.opc.packuri import PackURI, numbered_partname_pieces


class DescribePackURI(object):
    """Unit-test suite for the `power_pptx.opc.packuri.PackURI` objects."""

    def it_can_construct_from_relative_ref(self):
        pack_uri = PackURI.from_rel_ref("/ppt/slides", "../slideLayouts/slideLayout1.xml")
        assert pack_uri == "/ppt/slideLayouts/slideLayout1.xml"

    def it_should_raise_on_construct_with_bad_pack_uri_str(self):
        with pytest.raises(ValueError):
            PackURI("foobar")

    @pytest.mark.parametrize(
        ("uri", "expected_value"),
        [
            ("/", "/"),
            ("/ppt/presentation.xml", "/ppt"),
            ("/ppt/slides/slide1.xml", "/ppt/slides"),
        ],
    )
    def it_knows_its_base_URI(self, uri: str, expected_value: str):
        assert PackURI(uri).baseURI == expected_value

    @pytest.mark.parametrize(
        ("uri", "expected_value"),
        [
            ("/", ""),
            ("/ppt/presentation.xml", "xml"),
            ("/ppt/media/image.PnG", "PnG"),
        ],
    )
    def it_knows_its_extension(self, uri: str, expected_value: str):
        assert PackURI(uri).ext == expected_value

    @pytest.mark.parametrize(
        ("uri", "expected_value"),
        [
            ("/", ""),
            ("/ppt/presentation.xml", "presentation.xml"),
            ("/ppt/media/image.png", "image.png"),
        ],
    )
    def it_knows_its_filename(self, uri: str, expected_value: str):
        assert PackURI(uri).filename == expected_value

    @pytest.mark.parametrize(
        ("uri", "expected_value"),
        [
            ("/", None),
            ("/ppt/presentation.xml", None),
            ("/ppt/,foo,grob!.xml", None),
            ("/ppt/media/image42.png", 42),
        ],
    )
    def it_knows_the_filename_index(self, uri: str, expected_value: str):
        assert PackURI(uri).idx == expected_value

    @pytest.mark.parametrize(
        ("uri", "base_uri", "expected_value"),
        [
            ("/ppt/presentation.xml", "/", "ppt/presentation.xml"),
            (
                "/ppt/slideMasters/slideMaster1.xml",
                "/ppt",
                "slideMasters/slideMaster1.xml",
            ),
            (
                "/ppt/slideLayouts/slideLayout1.xml",
                "/ppt/slides",
                "../slideLayouts/slideLayout1.xml",
            ),
        ],
    )
    def it_can_compute_its_relative_reference(self, uri: str, base_uri: str, expected_value: str):
        assert PackURI(uri).relative_ref(base_uri) == expected_value

    @pytest.mark.parametrize(
        ("uri", "expected_value"),
        [
            ("/", "/_rels/.rels"),
            ("/ppt/presentation.xml", "/ppt/_rels/presentation.xml.rels"),
            ("/ppt/slides/slide42.xml", "/ppt/slides/_rels/slide42.xml.rels"),
        ],
    )
    def it_knows_the_uri_of_its_rels_part(self, uri: str, expected_value: str):
        assert PackURI(uri).rels_uri == expected_value


class DescribeNumberedPartnamePieces:
    @pytest.mark.parametrize(
        ("partname", "expected"),
        [
            ("/ppt/charts/chart3.xml", ("/ppt/charts/chart", ".xml")),
            ("/ppt/media/logo.png", ("/ppt/media/logo", ".png")),
            ("/ppt/media/my%20logo12.png", ("/ppt/media/my%20logo", ".png")),
            # -- the digits of a percent-escape are not the part's number --
            ("/ppt/media/logo%20.png", ("/ppt/media/logo%20", ".png")),
            ("/ppt/media/logo%2012.png", ("/ppt/media/logo%20", ".png")),
            ("/ppt/media/logo%2A7", ("/ppt/media/logo%2A", "")),
        ],
    )
    def it_splits_a_partname_around_its_trailing_number(self, partname, expected):
        assert numbered_partname_pieces(partname) == expected

    def it_never_leaves_a_bare_percent_sign_in_a_sibling_name(self):
        stem, suffix = numbered_partname_pieces("/ppt/media/logo%20.png")
        assert stem + "1" + suffix == "/ppt/media/logo%201.png"
