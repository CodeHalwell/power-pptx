"""Tracking, weights, case, ragged columns, and measured tables in native components."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from power_pptx import BBox, Presentation
from power_pptx.design import (
    Card,
    Column,
    DataTable,
    LayoutOverflowError,
    LayoutWarning,
    Row,
    TextBlock,
)
from power_pptx.text import clear_registered_fonts, register_font_dir
from power_pptx.text.fonts import FONT_DIRS_ENV
from power_pptx.util import Inches, Pt
from power_pptx.validation import validate_presentation

FONTS = Path(__file__).parents[1] / "fonts"


@pytest.fixture(autouse=True)
def bundled_fonts(monkeypatch):
    monkeypatch.delenv(FONT_DIRS_ENV, raising=False)
    clear_registered_fonts()
    register_font_dir(FONTS)
    yield
    clear_registered_fonts()


@pytest.fixture
def slide():
    prs = Presentation()
    return prs.slides.add_slide(prs.slide_layouts[6])


def _rpr(shape):
    return shape.text_frame.paragraphs[0].runs[0].font


class DescribeBundledFonts:
    def it_measures_bold_with_the_bold_face_from_a_registered_folder(self, slide):
        block = TextBlock("Revenue", font="Outfit", bold=True, size_pt=20)

        result = block.render(slide, BBox.from_inches(1, 1, 4, 1), strict_fonts=True)

        assert result.estimated_fonts == []
        assert _rpr(result.shapes[0]).bold is True

    def it_still_raises_in_strict_mode_for_unknown_fonts(self, slide):
        with pytest.raises(ValueError, match="register_font_dir"):
            TextBlock("x", font="No Such Font").render(
                slide, BBox.from_inches(1, 1, 4, 1), strict_fonts=True
            )


class DescribeLetterSpacing:
    def it_overflows_when_tracking_no_longer_fits(self, slide):
        narrow = BBox(Inches(1), Inches(1), Pt(95), Pt(30))
        untracked = TextBlock(
            "ACTIVE CUSTOMERS", font="Outfit", size_pt=9, min_size_pt=9, max_lines=1
        )
        untracked.render(slide, narrow, strict_fonts=True)

        tracked = TextBlock(
            "ACTIVE CUSTOMERS",
            font="Outfit",
            size_pt=9,
            min_size_pt=9,
            max_lines=1,
            letter_spacing=Pt(1.4),
        )
        with pytest.raises(LayoutOverflowError):
            tracked.render(slide, narrow, strict_fonts=True)

    def it_writes_the_spacing_on_every_run(self, slide):
        block = TextBlock(
            "Eyebrow", font="Outfit", size_pt=9, min_size_pt=9, letter_spacing=Pt(1.4)
        )

        result = block.render(slide, BBox.from_inches(1, 1, 4, 1), strict_fonts=True)

        runs = [r for p in result.shapes[0].text_frame.paragraphs for r in p.runs]
        assert runs
        assert all(r.font.letter_spacing == Pt(1.4) for r in runs)

    def it_rejects_non_finite_spacing(self, slide):
        with pytest.raises(ValueError, match="letter_spacing"):
            TextBlock("x", letter_spacing=float("inf")).render(slide, BBox.from_inches(1, 1, 4, 1))


class DescribeCase:
    @pytest.mark.parametrize(("case", "expected"), [("upper", "ACTIVE"), ("lower", "active")])
    def it_measures_and_draws_the_transformed_text(self, slide, case, expected):
        block = TextBlock("Active", font="Outfit", case=case)

        result = block.render(slide, BBox.from_inches(1, 1, 4, 1), strict_fonts=True)

        assert result.shapes[0].text_frame.text == expected

    def it_rejects_unknown_cases(self, slide):
        with pytest.raises(ValueError, match="case"):
            TextBlock("x", case="title").render(slide, BBox.from_inches(1, 1, 4, 1))


class DescribeWeight:
    def it_draws_a_medium_face_by_its_legacy_family_name(self, slide):
        block = TextBlock("Revenue", font="Tektur", weight="medium")

        result = block.render(slide, BBox.from_inches(1, 1, 4, 1), strict_fonts=True)

        font = _rpr(result.shapes[0])
        assert font.name == "Tektur Medium"
        assert font.bold is False
        assert result.estimated_fonts == []

    def it_treats_bold_weight_as_the_bold_flag(self, slide):
        result = TextBlock("Revenue", font="Outfit", weight=700).render(
            slide, BBox.from_inches(1, 1, 4, 1), strict_fonts=True
        )

        assert _rpr(result.shapes[0]).bold is True
        assert _rpr(result.shapes[0]).name == "Outfit"

    def it_raises_for_a_missing_weight_in_strict_mode(self, slide):
        with pytest.raises(ValueError, match="SemiBold"):
            TextBlock("Revenue", font="Outfit", weight="semibold").render(
                slide, BBox.from_inches(1, 1, 4, 1), strict_fonts=True
            )

    def it_falls_back_to_the_nearest_face_and_says_so(self, slide):
        result = TextBlock("Revenue", font="Outfit", weight="semibold", name="kpi").render(
            slide, BBox.from_inches(1, 1, 4, 1)
        )

        assert _rpr(result.shapes[0]).bold is True
        assert result.estimated_fonts == ["kpi"]

    def it_rejects_bold_with_a_different_weight(self, slide):
        with pytest.raises(ValueError, match="conflicts"):
            TextBlock("x", bold=True, weight="medium").render(slide, BBox.from_inches(1, 1, 4, 1))


def _two_column_row(last_options=None, **column_options):
    return Row(
        [
            Card([TextBlock("Left " * 60, font="Outfit", size_pt=14)], name="left"),
            Column(
                [
                    Card([TextBlock("a", font="Outfit")]),
                    Card([TextBlock("b", font="Outfit")], name="last", **(last_options or {})),
                ],
                **column_options,
            ),
        ]
    )


def _bottom_gap(result):
    left, last = result["left"], result["last"]
    return (left.top + left.height) - (last.top + last.height)


class DescribeRaggedColumns:
    def it_warns_when_a_stretched_column_ends_short(self, slide):
        with pytest.warns(LayoutWarning, match="fill_last=True"):
            result = _two_column_row().render(slide, BBox.from_inches(0.5, 0.5, 9, 5))

        assert len(result.warnings) == 1
        assert _bottom_gap(result) > Pt(100)

    @pytest.mark.parametrize("variant", ["fill_last", "grow"])
    def it_aligns_bottom_edges_when_the_last_child_takes_the_space(self, slide, variant):
        if variant == "fill_last":
            tree = _two_column_row(fill_last=True)
        else:
            tree = _two_column_row(last_options={"grow": 1})
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            result = tree.render(slide, BBox.from_inches(0.5, 0.5, 9, 5))

        assert result.warnings == []
        assert _bottom_gap(result) == 0
        assert not [i for i in slide.lint().issues if i.code == "RaggedEdge"]

    def it_does_not_warn_for_unstretched_or_unfilled_columns(self, slide):
        tree = Column([Card([TextBlock("a", font="Outfit")])])
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert tree.render(slide, BBox.from_inches(0.5, 0.5, 9, 5)).warnings == []

    def it_validates_fill_last(self, slide):
        with pytest.raises(ValueError, match="vertical"):
            Row([TextBlock("x")], fill_last=True).render(slide, BBox.from_inches(1, 1, 4, 1))
        with pytest.raises(ValueError, match="fixed height"):
            Column([TextBlock("x", height=Pt(20))], fill_last=True).render(
                slide, BBox.from_inches(1, 1, 4, 1)
            )


ROWS = [
    ["Region", "Revenue", "Note"],
    ["EMEA", "£4.2m", "Strong renewals across every major account in the quarter"],
    ["APAC", "£3.1m", "Flat"],
]


class DescribeDataTable:
    def it_measures_row_heights_and_truncates_cells(self, slide):
        table = DataTable(
            ROWS, font="Outfit", columns=[1, 1, 2], max_lines=1, truncate=True, name="revenue"
        )

        result = Column([table]).render(slide, BBox.from_inches(0.5, 0.5, 6, 4), strict_fonts=True)

        frame = result["revenue"]
        cells = [c.text for c in frame.table.iter_cells()]
        assert cells[5].endswith("…")
        assert ROWS[1][2].startswith(cells[5][:-1])
        assert len({row.height for row in frame.table.rows}) == 1
        assert frame.height == sum(row.height for row in frame.table.rows)
        assert frame.table.cell(0, 0).text_frame.paragraphs[0].runs[0].font.bold is True

    def it_wraps_cells_and_grows_rows_without_a_line_budget(self, slide):
        result = DataTable(ROWS, font="Outfit", columns=[1, 1, 2]).render(
            slide, BBox.from_inches(0.5, 0.5, 6, 4), strict_fonts=True
        )

        heights = [row.height for row in result.shapes[0].table.rows]
        assert heights[1] > heights[2]

    def it_raises_when_a_cell_exceeds_its_line_budget(self, slide):
        with pytest.raises(LayoutOverflowError, match="max_lines"):
            DataTable(ROWS, font="Outfit", max_lines=1).render(
                slide, BBox.from_inches(0.5, 0.5, 4, 4), strict_fonts=True
            )

    def it_raises_when_the_table_is_taller_than_its_region(self, slide):
        with pytest.raises(LayoutOverflowError, match="DataTable"):
            DataTable(ROWS * 10, font="Outfit").render(
                slide, BBox.from_inches(0.5, 0.5, 6, 1), strict_fonts=True
            )

    @pytest.mark.parametrize(
        "options",
        [
            {"rows": []},
            {"rows": [["a", "b"], ["c"]]},
            {"columns": [1, 2]},
            {"align": "middle"},
            {"truncate": True},
            {"max_lines": 0},
        ],
    )
    def it_validates_its_options(self, slide, options):
        kwargs = {"rows": ROWS, **options}
        with pytest.raises(ValueError):
            DataTable(**kwargs).render(slide, BBox.from_inches(0.5, 0.5, 6, 4))

    def it_produces_a_valid_package(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        DataTable(ROWS, font="Outfit", max_lines=1, truncate=True).render(
            slide, BBox.from_inches(0.5, 0.5, 6, 4)
        )
        TextBlock("Eyebrow", font="Tektur", weight="medium", letter_spacing=Pt(1.4)).render(
            slide, BBox.from_inches(0.5, 4.5, 4, 1)
        )

        report = validate_presentation(prs)

        assert not report.schema_violations
        assert not report.roundtrip_changed_parts
