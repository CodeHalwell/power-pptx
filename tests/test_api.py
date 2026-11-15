"""Unit-test suite for `power_pptx.api` module."""

from __future__ import annotations

import os

import pytest

import power_pptx
from power_pptx.api import Presentation, _is_pptx_package
from power_pptx.opc.constants import CONTENT_TYPE as CT
from power_pptx.parts.presentation import PresentationPart

from .unitutil.mock import class_mock, instance_mock


class DescribePackageSurface:
    """Top-level package re-exports — keep these stable.

    These names are documented entry points; if any of them disappear
    the docs drift silently. The test fails before docs do.
    """

    @pytest.mark.parametrize(
        "name",
        [
            "Presentation",
            "add_plotly_figure",
            "add_matplotlib_figure",
            "add_svg_figure",
            "add_html_figure",
            "FigureBackendUnavailable",
            "add_kpi_card",
            "add_progress_bar",
            "add_gauge",
            "add_status_pill",
            "add_stat_strip",
            "add_article_card",
            "KpiCard",
            "ProgressBar",
            "Gauge",
            "StatusPill",
            "StatStrip",
            "ArticleCard",
        ],
    )
    def it_exposes_each_documented_name_at_package_root(self, name):
        assert hasattr(power_pptx, name), (
            f"power_pptx.{name} is documented as a top-level export but "
            "is not importable from the package root."
        )
        assert name in power_pptx.__all__


class DescribePresentation(object):
    def it_opens_default_template_on_no_path_provided(self, call_fixture):
        Package_, path, prs_ = call_fixture
        prs = Presentation()
        Package_.open.assert_called_once_with(path)
        assert prs is prs_

    # fixtures -------------------------------------------------------

    @pytest.fixture
    def call_fixture(self, Package_, prs_, prs_part_):
        path = os.path.abspath(
            os.path.join(os.path.split(power_pptx.__file__)[0], "templates", "default.pptx")
        )
        Package_.open.return_value.main_document_part = prs_part_
        prs_part_.content_type = CT.PML_PRESENTATION_MAIN
        prs_part_.presentation = prs_
        return Package_, path, prs_

    # fixture components ---------------------------------------------

    @pytest.fixture
    def Package_(self, request):
        return class_mock(request, "power_pptx.api.Package")

    @pytest.fixture
    def prs_(self, request):
        return instance_mock(request, Presentation)

    @pytest.fixture
    def prs_part_(self, request):
        return instance_mock(request, PresentationPart)


class Describe_is_pptx_package(object):
    """A template (.potx) and a slide show (.ppsx) are presentations too."""

    @pytest.mark.parametrize(
        ("content_type", "expected"),
        [
            (CT.PML_PRESENTATION_MAIN, True),
            (CT.PML_PRES_MACRO_MAIN, True),
            (CT.PML_TEMPLATE_MAIN, True),
            (CT.PML_SLIDESHOW_MAIN, True),
            (CT.WML_DOCUMENT_MAIN, False),
            (CT.SML_SHEET_MAIN, False),
            (CT.PML_SLIDE, False),
        ],
    )
    def it_knows_which_main_parts_are_presentations(self, request, content_type, expected):
        prs_part_ = instance_mock(request, PresentationPart, content_type=content_type)

        assert _is_pptx_package(prs_part_) is expected
