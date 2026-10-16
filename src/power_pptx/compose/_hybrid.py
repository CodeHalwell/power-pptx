"""Map an explicit HTML annotation contract to native PowerPoint content."""

from __future__ import annotations

import math
import re

from power_pptx._color import coerce_color
from power_pptx.chart.data import CategoryChartData
from power_pptx.enum.chart import XL_CHART_TYPE
from power_pptx.enum.text import MSO_AUTO_SIZE
from power_pptx.geometry import BBox
from power_pptx.text.fonts import font_is_installed
from power_pptx.util import Emu, Pt

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


def _chart_spec(record):
    spec = record["chart"]
    if not isinstance(spec, dict):
        raise ValueError("data-pptx-chart must be a JSON object")
    unknown = set(spec) - {"type", "categories", "series", "colors", "title", "legend"}
    if unknown:
        raise ValueError(f"Unknown chart options: {', '.join(sorted(unknown))}")
    if spec.get("type", "column") not in _CHARTS:
        raise ValueError("Native HTML chart type must be column, bar, line, area, pie, or doughnut")
    categories, series = spec.get("categories"), spec.get("series")
    if (
        not isinstance(categories, list)
        or not categories
        or not isinstance(series, list)
        or not series
    ):
        raise ValueError("Native chart requires non-empty categories and series lists")
    for item in series:
        if not isinstance(item, dict) or set(item) - {"name", "values"} or "name" not in item:
            raise ValueError("Each chart series needs name and values")
        values = item.get("values")
        if not isinstance(values, list) or len(values) != len(categories):
            raise ValueError("Chart series values must match the category count")
        if any(
            v is not None
            and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v))
            for v in values
        ):
            raise ValueError("Chart values must be finite numbers or null")
    if "colors" in spec:
        if not isinstance(spec["colors"], list) or not spec["colors"]:
            raise ValueError("Chart colors must be a non-empty list")
        for color in spec["colors"]:
            coerce_color(color)
    return spec


def prepare_layers(capture, *, font_map, strict_fonts):
    """Validate native metadata before creating its slide."""
    if capture.size is None:
        raise ValueError("Hybrid capture has no canvas dimensions")
    for record in capture.elements:
        if record["kind"] == "capture":
            continue
        style = record["style"]
        record["native_font"] = _font(style, font_map, strict_fonts)
        css_color(style["color"])
        if record["kind"] == "text":
            for run in record["runs"]:
                run["native_font"] = _font(run["style"], font_map, strict_fonts)
                css_color(run["style"]["color"])
        elif record["kind"] == "chart":
            _chart_spec(record)
        else:
            if not record["rows"] or not any(record["rows"]):
                raise ValueError("Annotated native table cannot be empty")
            for row in record["rows"]:
                for cell in row:
                    cell["native_font"] = _font(cell["style"], font_map, strict_fonts)
                    css_color(cell["style"]["color"])
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
    cells = []
    occupied = set()
    count = 0
    for r, row in enumerate(record["rows"]):
        c = 0
        for cell in row:
            while (r, c) in occupied:
                c += 1
            for rr in range(r, r + cell["rowspan"]):
                for cc in range(c, c + cell["colspan"]):
                    occupied.add((rr, cc))
            cells.append((r, c, cell))
            count = max(count, c + cell["colspan"])
            c += cell["colspan"]
    row_count = len(record["rows"])
    if any(r + cell["rowspan"] > row_count for r, c, cell in cells):
        raise ValueError("Table rowspan extends beyond its rows")
    shape = slide.shapes.add_table(row_count, count, *bounds, style="clean")
    table = shape.table
    table.clear_style()
    widths = [0.0] * count
    for r, c, cell in cells:
        if cell["colspan"] == 1:
            widths[c] = cell["bounds"][2]
    for r, c, cell in cells:
        for i in range(c, c + cell["colspan"]):
            if not widths[i]:
                widths[i] = cell["bounds"][2] / cell["colspan"]
    total = sum(widths)
    used = 0
    for i, w in enumerate(widths):
        edge = round(bounds.width * sum(widths[: i + 1]) / total)
        table.columns[i].width = Emu(edge - used)
        used = edge
    total = sum(record["rowHeights"])
    used = 0
    for i, h in enumerate(record["rowHeights"]):
        edge = round(bounds.height * sum(record["rowHeights"][: i + 1]) / total)
        table.rows[i].height = Emu(edge - used)
        used = edge
    # Office resolves shared cell edges differently from CSS collapse. Give
    # both neighbors the same strongest border so an explicit noFill cannot
    # erase the other cell's visible bottom/right edge in LibreOffice.
    shared = {}

    def edge_keys(r, c, cell):
        bottom, right = r + cell["rowspan"], c + cell["colspan"]
        return (
            [("h", r, x) for x in range(c, right)],
            [("v", right, y) for y in range(r, bottom)],
            [("h", bottom, x) for x in range(c, right)],
            [("v", c, y) for y in range(r, bottom)],
        )

    for r, c, cell in cells:
        for keys, width, color in zip(
            edge_keys(r, c, cell), cell["style"]["border"], cell["style"]["borderColors"]
        ):
            for key in keys:
                if width >= shared.get(key, (0, "transparent"))[0]:
                    shared[key] = (width, color)
    for r, c, cell in cells:
        target = table.cell(r, c)
        style = cell["style"]
        if cell["rowspan"] > 1 or cell["colspan"] > 1:
            target.merge(table.cell(r + cell["rowspan"] - 1, c + cell["colspan"] - 1))
        target.text = cell["text"]
        fill, opacity = css_color(cell["fill"])
        target.format(
            font=cell["native_font"],
            size_pt=style["size"] * scale / 12700,
            bold=int(style["weight"]) >= 600,
            italic=style["italic"],
            color=css_color(style["color"])[0],
            fill=fill if opacity else "none",
            align=style["align"]
            if style["align"] in {"left", "right", "center", "justify"}
            else "left",
            anchor=style["verticalAlign"]
            if style["verticalAlign"] in {"top", "middle", "bottom"}
            else "top",
            margin=tuple(p * scale / 12700 for p in style["padding"]),
        )
        target.borders.none()
        if opacity:
            target.fill.fore_color.alpha = opacity
        for paragraph in target.text_frame.paragraphs:
            for run in paragraph.runs:
                _apply_font(run.font, style, cell["native_font"], scale)
        for edge, keys in zip(("top", "right", "bottom", "left"), edge_keys(r, c, cell)):
            width, color = max((shared[key] for key in keys), key=lambda item: item[0])
            line = getattr(target.borders, edge)
            if width > 0:
                line.width = Emu(round(width * scale))
                line.color.rgb = css_color(color)[0]
                line.color.alpha = css_color(color)[1]
            else:
                line.fill.background()
    return shape
