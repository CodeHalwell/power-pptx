"""Map an explicit HTML annotation contract to native PowerPoint content."""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING, Any, NamedTuple

from power_pptx._color import coerce_color
from power_pptx.chart.data import CategoryChartData
from power_pptx.enum.chart import XL_CHART_TYPE
from power_pptx.enum.text import MSO_AUTO_SIZE
from power_pptx.geometry import BBox
from power_pptx.text.fonts import font_is_installed
from power_pptx.util import Emu, Pt

if TYPE_CHECKING:
    from typing_extensions import TypeGuard

_CHARTS = {
    "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "bar": XL_CHART_TYPE.BAR_CLUSTERED,
    "line": XL_CHART_TYPE.LINE,
    "area": XL_CHART_TYPE.AREA,
    "pie": XL_CHART_TYPE.PIE,
    "doughnut": XL_CHART_TYPE.DOUGHNUT,
}


def css_color(value):
    """Return RGB plus opacity for Chromium's common computed RGB colors."""
    if value == "transparent":
        return coerce_color("#000000"), 0.0
    if value.startswith("#"):
        return coerce_color(value), 1.0
    match = re.fullmatch(r"rgba?\(([^)]+)\)", value)
    if not match:
        raise ValueError(f"Unsupported native CSS color {value!r}; use RGB colors or capture")
    values = [float(n) for n in re.split(r"[,\s/]+", match.group(1)) if n]
    return coerce_color(tuple(round(v) for v in values[:3])), values[3] if len(values) > 3 else 1.0


def _font(style, font_map, strict):
    candidates = [s.strip().strip("\"'") for s in style["font"].split(",")]
    bold, italic = int(style["weight"]) >= 600, style["italic"]
    mapping = {key.casefold(): value for key, value in font_map.items()}
    for candidate in candidates:
        name = mapping.get(candidate.casefold(), candidate)
        if name in {"sans-serif", "system-ui"}:
            name = (
                "Liberation Sans"
                if font_is_installed("Liberation Sans", bold, italic)
                else "DejaVu Sans"
            )
        elif name == "serif":
            name = "DejaVu Serif"
        elif name == "monospace":
            name = "DejaVu Sans Mono"
        if font_is_installed(name, bold, italic):
            return name
    if strict:
        raise ValueError(
            f"HTML native font {style['font']!r} is not installed in its requested style. "
            'Install it, supply font_map, or mark the region data-pptx="capture".'
        )
    return mapping.get(candidates[0].casefold(), candidates[0])


_CHART_OPTIONS = frozenset({"type", "categories", "series", "colors", "title", "legend"})


def _chart_spec(record):
    spec = record["chart"]
    if not isinstance(spec, dict):
        raise ValueError("data-pptx-chart must be a JSON object")
    unknown = set(spec) - _CHART_OPTIONS
    if unknown:
        raise ValueError(f"Unknown chart options: {', '.join(sorted(unknown))}")
    if spec.get("type", "column") not in _CHARTS:
        raise ValueError("Native HTML chart type must be column, bar, line, area, pie, or doughnut")
    categories, series = spec.get("categories"), spec.get("series")
    if not _is_filled_list(categories) or not _is_filled_list(series):
        raise ValueError("Native chart requires non-empty categories and series lists")
    for item in series:
        _check_chart_series(item, len(categories))
    if "colors" in spec:
        _check_chart_colors(spec["colors"])
    return spec


def _is_filled_list(value: Any) -> TypeGuard[list[Any]]:
    return isinstance(value, list) and bool(value)


def _check_chart_series(item, category_count):
    if not isinstance(item, dict) or set(item) - {"name", "values"} or "name" not in item:
        raise ValueError("Each chart series needs name and values")
    values = item.get("values")
    if not isinstance(values, list) or len(values) != category_count:
        raise ValueError("Chart series values must match the category count")
    if not all(_is_chart_value(value) for value in values):
        raise ValueError("Chart values must be finite numbers or null")


def _is_chart_value(value):
    """Return whether *value* is a finite number or ``None`` (a gap in the series)."""
    if value is None:
        return True
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _check_chart_colors(colors):
    if not _is_filled_list(colors):
        raise ValueError("Chart colors must be a non-empty list")
    for color in colors:
        coerce_color(color)


def prepare_layers(capture, *, font_map, strict_fonts):
    """Validate native metadata before creating its slide."""
    if capture.size is None:
        raise ValueError("Hybrid capture has no canvas dimensions")
    for record in capture.elements:
        kind = record["kind"]
        if kind == "capture":
            continue
        _prepare_styled(record, font_map, strict_fonts)
        if kind == "text":
            for run in record["runs"]:
                _prepare_styled(run, font_map, strict_fonts)
        elif kind == "chart":
            _chart_spec(record)
        else:
            _prepare_table(record, font_map, strict_fonts)


def _prepare_styled(item, font_map, strict_fonts):
    """Resolve the native font for *item*'s style and check its text colour."""
    style = item["style"]
    item["native_font"] = _font(style, font_map, strict_fonts)
    css_color(style["color"])


def _prepare_table(record, font_map, strict_fonts):
    if not record["rows"] or not any(record["rows"]):
        raise ValueError("Annotated native table cannot be empty")
    for row in record["rows"]:
        for cell in row:
            _prepare_styled(cell, font_map, strict_fonts)
            css_color(cell["fill"])


def add_layers(slide, capture, *, slide_width, slide_height):
    scale = min(slide_width / capture.size[0], slide_height / capture.size[1])
    x0, y0 = (
        (slide_width - capture.size[0] * scale) / 2,
        (slide_height - capture.size[1] * scale) / 2,
    )

    def box(bounds):
        x, y, w, h = bounds
        return BBox(
            Emu(round(x0 + x * scale)),
            Emu(round(y0 + y * scale)),
            Emu(round(w * scale)),
            Emu(round(h * scale)),
        )

    for record in capture.elements:
        kind = record["kind"]
        bounds = box(record["bounds"])
        if kind == "capture":
            from io import BytesIO

            shape = slide.shapes.add_picture(BytesIO(record["png"]), *bounds)
            shape.alt_text = record["text"] or record["name"]
        elif kind == "text":
            shape = _add_text(slide, record, bounds, scale)
        elif kind == "chart":
            shape = _add_chart(slide, record, bounds, scale)
        else:
            shape = _add_table(slide, record, bounds, scale)
        shape.name = record["name"]


def _apply_font(font, style, family, scale):
    font.name = family
    font.size = Emu(round(style["size"] * scale))
    font.bold, font.italic = int(style["weight"]) >= 600, style["italic"]
    color, alpha = css_color(style["color"])
    font.color.rgb = color
    font.color.alpha = alpha * style["opacity"]
    font.underline = style["underline"]


def _add_text(slide, record, bounds, scale):
    from power_pptx._textstyle import coerce_align

    shape = slide.shapes.add_textbox(*bounds)
    tf = shape.text_frame
    tf.auto_size = MSO_AUTO_SIZE.NONE
    # Browser-measured visual lines are preserved as editable paragraphs.
    tf.word_wrap = False
    padding, border = record["style"]["padding"], record["style"]["border"]
    for attr, p, b in zip(
        ("margin_top", "margin_right", "margin_bottom", "margin_left"), padding, border
    ):
        setattr(tf, attr, Emu(round((p + b) * scale)))
    line = 0
    paragraph = tf.paragraphs[0]

    def format_paragraph(p):
        p.alignment = coerce_align(
            record["style"]["align"]
            if record["style"]["align"] in {"left", "right", "center", "justify"}
            else "left"
        )
        p.line_spacing = Emu(round(record["style"]["lineHeight"] * scale))
        p.space_before = p.space_after = Pt(0)

    format_paragraph(paragraph)
    for item in record["runs"]:
        while line < item["line"]:
            paragraph = tf.add_paragraph()
            format_paragraph(paragraph)
            line += 1
        run = paragraph.add_run()
        run.text = item["text"]
        _apply_font(run.font, item["style"], item["native_font"], scale)
    return shape


def _add_chart(slide, record, bounds, scale):
    spec = record["chart"]
    data = CategoryChartData()
    data.categories = spec["categories"]
    for series in spec["series"]:
        data.add_series(series["name"], series["values"])
    shape = slide.shapes.add_chart(_CHARTS[spec.get("type", "column")], *bounds, data)
    chart = shape.chart
    chart.apply_quick_layout("minimal")
    chart.has_legend = bool(spec.get("legend", False))
    if spec.get("title"):
        chart.has_title = True
        chart.chart_title.text_frame.text = spec["title"]
    if spec.get("colors"):
        chart.recolour(spec["colors"])
    chart.font.name = record["native_font"]
    chart.font.size = Emu(round(record["style"]["size"] * scale))
    chart.text_color = css_color(record["style"]["color"])[0]
    return shape


def _add_table(slide, record, bounds, scale):
    cells, column_count = _place_cells(record["rows"])
    row_count = len(record["rows"])
    if any(placed.row + placed.cell["rowspan"] > row_count for placed in cells):
        raise ValueError("Table rowspan extends beyond its rows")
    shape = slide.shapes.add_table(row_count, column_count, *bounds, style="clean")
    table = shape.table
    table.clear_style()
    column_widths = _column_widths(cells, column_count)
    for i, width in enumerate(_proportional_sizes(bounds.width, column_widths)):
        table.columns[i].width = width
    for i, height in enumerate(_proportional_sizes(bounds.height, record["rowHeights"])):
        table.rows[i].height = height
    shared = _shared_borders(cells)
    for placed in cells:
        _format_cell(table, placed, scale, shared)
    return shape


# CSS alignments a native table cell can show; any other value (``start``,
# ``baseline``, ...) is drawn top left.
_CELL_ALIGNS = frozenset({"left", "right", "center", "justify"})
_CELL_ANCHORS = frozenset({"top", "middle", "bottom"})

# A cell's sides, in the order CSS lists border widths and colours.
_CELL_EDGES = ("top", "right", "bottom", "left")


class _GridCell(NamedTuple):
    """An HTML table cell placed at its native table grid position."""

    row: int
    column: int
    cell: dict[str, Any]

    @property
    def last_row(self) -> int:
        """The grid row just below this cell."""
        return self.row + self.cell["rowspan"]

    @property
    def last_column(self) -> int:
        """The grid column just right of this cell."""
        return self.column + self.cell["colspan"]

    def edge_keys(self):
        """Return the grid-edge keys along this cell's top, right, bottom and left sides.

        ``("h", row, column)`` is the horizontal edge above a grid cell and
        ``("v", column, row)`` the vertical edge to its left, so two cells
        that share a side share its keys.
        """
        rows, columns = range(self.row, self.last_row), range(self.column, self.last_column)
        return (
            [("h", self.row, x) for x in columns],
            [("v", self.last_column, y) for y in rows],
            [("h", self.last_row, x) for x in columns],
            [("v", self.column, y) for y in rows],
        )


def _place_cells(rows):
    """Return each cell at its grid position, and the grid's column count.

    As in an HTML table, a cell starts at the first column of its row that
    no row-spanning cell from a row above already covers.
    """
    cells = []
    occupied = set()
    column_count = 0
    for r, row in enumerate(rows):
        c = 0
        for cell in row:
            while (r, c) in occupied:
                c += 1
            placed = _GridCell(r, c, cell)
            occupied.update(
                (rr, cc) for rr in range(r, placed.last_row) for cc in range(c, placed.last_column)
            )
            cells.append(placed)
            column_count = max(column_count, placed.last_column)
            c = placed.last_column
    return cells, column_count


def _column_widths(cells, column_count):
    """Return the browser width of each grid column.

    A column takes the width of a cell that spans it alone; a column only
    spanning cells cover takes an even share of the first such cell.
    """
    widths = [0.0] * column_count
    for placed in cells:
        if placed.cell["colspan"] == 1:
            widths[placed.column] = placed.cell["bounds"][2]
    for placed in cells:
        for i in range(placed.column, placed.last_column):
            if not widths[i]:
                widths[i] = placed.cell["bounds"][2] / placed.cell["colspan"]
    return widths


def _proportional_sizes(length, weights):
    """Split *length* EMU in proportion to *weights*.

    Each running edge is rounded, so the sizes always add up to *length*.
    """
    total = sum(weights)
    sizes = []
    used = 0
    for i in range(len(weights)):
        edge = round(length * sum(weights[: i + 1]) / total)
        sizes.append(Emu(edge - used))
        used = edge
    return sizes


def _shared_borders(cells):
    """Return the strongest ``(width, colour)`` border along each grid edge.

    Office resolves shared cell edges differently from CSS collapse. Give
    both neighbors the same strongest border so an explicit noFill cannot
    erase the other cell's visible bottom/right edge in LibreOffice.
    """
    shared = {}
    for placed in cells:
        style = placed.cell["style"]
        for keys, width, color in zip(placed.edge_keys(), style["border"], style["borderColors"]):
            for key in keys:
                if width >= shared.get(key, (0, "transparent"))[0]:
                    shared[key] = (width, color)
    return shared


def _format_cell(table, placed, scale, shared):
    """Merge, fill, write and outline the native cell for *placed*."""
    cell, style = placed.cell, placed.cell["style"]
    target = table.cell(placed.row, placed.column)
    if cell["rowspan"] > 1 or cell["colspan"] > 1:
        target.merge(table.cell(placed.last_row - 1, placed.last_column - 1))
    target.text = cell["text"]
    fill, opacity = css_color(cell["fill"])
    target.format(
        font=cell["native_font"],
        size_pt=style["size"] * scale / 12700,
        bold=int(style["weight"]) >= 600,
        italic=style["italic"],
        color=css_color(style["color"])[0],
        fill=fill if opacity else "none",
        align=_supported(style["align"], _CELL_ALIGNS, "left"),
        anchor=_supported(style["verticalAlign"], _CELL_ANCHORS, "top"),
        margin=tuple(p * scale / 12700 for p in style["padding"]),
    )
    target.borders.none()
    if opacity:
        target.fill.fore_color.alpha = opacity
    for paragraph in target.text_frame.paragraphs:
        for run in paragraph.runs:
            _apply_font(run.font, style, cell["native_font"], scale)
    for edge, keys in zip(_CELL_EDGES, placed.edge_keys()):
        width, color = max((shared[key] for key in keys), key=lambda item: item[0])
        _set_border(getattr(target.borders, edge), width, color, scale)


def _supported(value, choices, fallback):
    """Return *value* when it is one of *choices*, otherwise *fallback*."""
    return value if value in choices else fallback


def _set_border(line, width, color, scale):
    """Draw *line* at the CSS *width* and *color*, or hide it when *width* is 0."""
    if width > 0:
        line.width = Emu(round(width * scale))
        line.color.rgb, line.color.alpha = css_color(color)
    else:
        line.fill.background()
