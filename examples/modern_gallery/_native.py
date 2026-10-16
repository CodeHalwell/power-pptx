"""Five editable / hybrid decks, designed on a shared 1280 × 720 CSS-pixel grid."""

from __future__ import annotations

import math
from contextlib import contextmanager
from pathlib import Path

from power_pptx import (
    BBox,
    Presentation,
    add_html_figure,
    add_matplotlib_figure,
    add_plotly_figure,
    add_svg_figure,
)
from power_pptx.chart.data import CategoryChartData
from power_pptx.compose import from_spec
from power_pptx.design.components import add_kpi_card, add_progress_bar, add_status_pill
from power_pptx.design.tokens import DesignTokens
from power_pptx.diagrams import horizontal_pipeline
from power_pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_TICK_MARK
from power_pptx.enum.presentation import MSO_TRANSITION_TYPE
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.util import Emu, Inches, Pt

FONT = "DejaVu Sans"
HERE = Path(__file__).resolve().parent
MONO = "DejaVu Sans Mono"
INK = "#172334"
MUTED = "#526176"
PURPLE = "#6554E8"


def bb(x, y, w, h):
    """96 CSS pixels = one inch on this widescreen canvas."""
    return BBox(*(Emu(round(v * 9525)) for v in (x, y, w, h)))


def deck(title):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(40 / 3), Inches(7.5)
    prs.theme.fonts.major = FONT
    prs.theme.fonts.minor = FONT
    prs.core_properties.title = title
    prs.core_properties.author = "power-pptx modern gallery"
    return prs


def text(s, x, y, w, h, value, size=24, color=INK, bold=False, font=FONT, align="left"):
    shape = s.shapes.add_text(
        bb(x, y, w, h),
        text=value,
        size_pt=size * 0.75,
        font=font,
        color=color,
        bold=bold,
        margin_pt=0,
        anchor="top",
        align=align,
    )
    shape.text_frame.fit_text(font_family=font, max_size=int(size * 0.75), bold=bold, strict=True)
    for p in shape.text_frame.paragraphs:
        p.line_spacing = 1.12 if bold else 1.25
        p.space_before = Pt(0)
        p.space_after = Pt(0)
    return shape


def rect(s, x, y, w, h, fill, border=None, radius=20):
    shape = s.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, *bb(x, y, w, h)
    )
    shape.fill_hex(fill)
    if border:
        shape.line_hex(border, weight_pt=0.75)
    else:
        shape.line.fill.background()
    shape.shadow.clear()
    if radius:
        shape.corner_radius = Pt(radius * 0.75)
    return shape


@contextmanager
def cluster(s):
    """Declare an actual containing card + contents as an intentional overlap."""
    start = len(s.shapes)
    yield
    shapes = list(s.shapes)[start:]
    if shapes:
        s.lint_group_overlaps(*shapes)


def slide(prs, brand, number, *, background="#F6F7FB", color=INK, accent=PURPLE):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = background
    text(s, 64, 42, 980, 30, brand.upper(), 18, accent, True)
    text(s, 64, 670, 1050, 24, "CONCEPT STUDY  /  FICTIONAL DATA", 14, color)
    text(s, 1130, 666, 86, 30, f"{number:02d} / 04", 17, color, align="right")
    s.transition.kind = MSO_TRANSITION_TYPE.FADE
    s.transition.duration = 350
    return s


def heading(s, title, subtitle=None, color=INK):
    text(s, 64, 112, 1152, 94, title, 52, color, True)
    if subtitle:
        text(s, 64, 210, 1152, 40, subtitle, 22, MUTED)


def chart(s, bounds, kind, categories, series, colors, *, dark=False, legend=False):
    data = CategoryChartData()
    data.categories = categories
    for label, values in series:
        data.add_series(label, values)
    c = s.shapes.add_chart(kind, *bb(*bounds), data).chart
    c.apply_quick_layout("minimal")
    c.recolour(colors)
    c.font.name, c.font.size = FONT, Pt(12)
    c.has_legend = legend
    if legend:
        c.legend.position = XL_LEGEND_POSITION.BOTTOM
        c.legend.include_in_layout = False
        c.legend.font.size = Pt(12)
    if kind != XL_CHART_TYPE.DOUGHNUT:
        for axis in (c.category_axis, c.value_axis):
            axis.major_tick_mark = XL_TICK_MARK.NONE
            axis.minor_tick_mark = XL_TICK_MARK.NONE
            axis.tick_labels.font.size = Pt(11)
        c.value_axis.has_major_gridlines = True
        c.value_axis.minimum_scale = 0
    if dark:
        c.apply_dark_theme(text="#C8D5E6", line="#304057")
    else:
        c.text_color = MUTED
        c.line_color = "#DEE4ED"
    return c


def svg_art(kind="orbit", ink=PURPLE):
    if kind == "orbit":
        shapes = "".join(
            f'<ellipse cx="260" cy="230" rx="220" ry="{r}" transform="rotate({a} 260 230)" '
            f'fill="none" stroke="{ink}" stroke-width="2" opacity=".6"/>'
            for r, a in [(78, 0), (78, 60), (78, 120)]
        )
        shapes += f'<circle cx="260" cy="230" r="62" fill="{ink}"/>'
        shapes += '<circle cx="260" cy="230" r="17" fill="#FFFFFF"/>'
        for angle in (20, 140, 260):
            x = 260 + 210 * math.cos(math.radians(angle))
            y = 230 + 130 * math.sin(math.radians(angle))
            shapes += f'<circle cx="{x}" cy="{y}" r="11" fill="{ink}"/>'
    else:
        shapes = "".join(
            f'<path d="M 20 {420 - i * 20} C 100 {200 - i * 6}, '
            f'340 {480 - i * 12}, 500 {40 + i * 9}" '
            f'fill="none" stroke="{ink}" stroke-width="{1.5 + i * 0.12}" opacity=".75"/>'
            for i in range(19)
        )
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 460">{shapes}</svg>'


def product():
    prs = deck("Forma — product intelligence")
    s = slide(prs, "FORMA / PRODUCT INTELLIGENCE", 1)
    text(s, 64, 150, 700, 205, "Less busywork.\nMore momentum.", 66, bold=True)
    text(
        s,
        66,
        397,
        620,
        102,
        "A calmer workspace for teams\nturning insight into their next release.",
        27,
        MUTED,
    )
    with cluster(s):
        rect(s, 66, 550, 228, 58, INK, radius=29)
        text(s, 87, 565, 190, 34, "Meet Forma   →", 22, "#FFFFFF", True)
    add_svg_figure(
        s, svg_art(), *bb(760, 145, 470, 416)
    ).alt_text = "Three orbits around one shared product hub."
    s.notes_slide.notes_text_frame.text = (
        "Position the product around a calmer workflow. "
        "All figures in this gallery are illustrative."
    )

    s = slide(prs, "FORMA / THE WORKSPACE", 2)
    heading(
        s,
        "One view. The whole picture.",
        "A bento layout built from editable cards, text, and a native chart.",
    )
    with cluster(s):
        card = rect(s, 64, 285, 690, 340, "#FFFFFF", "#E0E4ED")
        card.shadow.blur_radius, card.shadow.distance = Pt(12), Pt(3)
        card.shadow.color.rgb, card.shadow.color.alpha = "#263554", 0.09
        text(s, 90, 310, 610, 36, "Weekly active teams", 23, bold=True)
        chart(
            s,
            (90, 365, 625, 224),
            XL_CHART_TYPE.COLUMN_CLUSTERED,
            ["Mon", "Tue", "Wed", "Thu", "Fri"],
            [("Teams", [28, 36, 32, 46, 59])],
            [PURPLE],
        )
    tokens = DesignTokens.from_dict(
        {
            "palette": {
                "primary": PURPLE,
                "surface": "#EEEBFF",
                "muted": "#5C538B",
                "positive": "#18745C",
            },
            "typography": {
                "heading": {"family": FONT, "size": 44.0, "bold": True},
                "body": {"family": FONT, "size": 15.0},
            },
            "radii": {"card": 18.0},
        }
    )
    kpi = add_kpi_card(
        s,
        left=bb(790, 285, 0, 0).left,
        top=bb(0, 285, 0, 0).top,
        width=bb(0, 0, 426, 0).width,
        height=bb(0, 0, 0, 210).height,
        value="94%",
        label="Work stays in one place",
        delta={"delta_text": "+18 pts this quarter"},
        tokens=tokens,
    )
    kpi.card.shadow.clear()
    with cluster(s):
        rect(s, 790, 523, 426, 102, INK)
        text(s, 816, 542, 370, 30, "Release 2.4 is ready", 23, "#FFFFFF", True)
        text(s, 816, 580, 370, 26, "All 12 checks passed  ·  Ship it →", 18, "#C9D2DF")

    s = slide(prs, "FORMA / THE FLOW", 3)
    heading(s, "Move from signal to shipped.")
    pipeline = horizontal_pipeline(
        s,
        bb(64, 300, 1152, 156),
        steps=[
            {"label": "01  Capture", "sublabel": "Bring the signals in"},
            {"label": "02  Decide", "sublabel": "Find the next best move"},
            {"label": "03  Release", "sublabel": "Close the feedback loop"},
        ],
        font=FONT,
        size_pt=18,
        fill="#FFFFFF",
        accent=PURPLE,
        text_color=INK,
        card_line="#D9DEEA",
        card_radius=14,
        gap=bb(0, 0, 54, 0).width,
    )
    for card in pipeline.cards:
        card.shadow.clear()
    for x, label, body in [
        (64, "Connect your tools", "Context without another inbox."),
        (466, "Make a small bet", "Clear ownership and a clear finish."),
        (868, "Learn in the open", "Every release feeds the next one."),
    ]:
        text(s, x, 500, 345, 36, label, 23, bold=True)
        text(s, x, 550, 345, 74, body, 21, MUTED)

    s = slide(prs, "FORMA / BUILT FOR TEAMS", 4)
    heading(s, "A small surface. A lot less friction.")
    rows = [
        ("Capability", "Starter", "Team", "Studio"),
        ("Shared projects", "5", "Unlimited", "Unlimited"),
        ("Connected sources", "3", "20", "Unlimited"),
        ("Review workflow", "Basic", "Advanced", "Custom"),
        ("Monthly / editor", "$0", "$18", "$32"),
    ]
    t = s.shapes.add_table(5, 4, *bb(64, 275, 1152, 330), style="clean").table
    t.columns[0].width = bb(0, 0, 450, 0).width
    for col in range(1, 4):
        t.columns[col].width = bb(0, 0, 234, 0).width
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell = t.cell(r, c)
            cell.text = value
            cell.format(
                font=FONT,
                size_pt=17,
                color=INK,
                fill="#FFFFFF" if r % 2 else "#EBEEF6",
                margin=(9, 16, 9, 16),
                anchor="middle",
                bold=r == 0,
                align="left" if c == 0 else "center",
            )
            cell.borders.none()
    t.format_cells(rows=0, fill=INK, color="#FFFFFF", bold=True)
    t.format_cells(rows=slice(1, None), cols=2, fill="#EAE5FF", color="#4836B3")
    return prs


def developer():
    prs = deck("Relay — developer platform")
    bg, panel, fg, muted, mint = "#0A111C", "#111E2E", "#EAF2FF", "#A6B7CC", "#75F3CE"

    def page(n):
        return slide(prs, "RELAY_ / DEVELOPER PLATFORM", n, background=bg, color=muted, accent=mint)

    s = page(1)
    text(s, 64, 145, 750, 200, "Ship at the speed\nof a good idea.", 72, fg, True)
    text(
        s,
        64,
        390,
        660,
        105,
        "One API for the events, jobs, and tools\nthat keep your product moving.",
        26,
        muted,
    )
    with cluster(s):
        card = rect(s, 820, 146, 380, 432, panel, "#2B4157")
        card.fill.linear_gradient("#163849", "#121B2C", angle=70)
        text(s, 850, 184, 320, 32, "SYSTEM STATUS", 18, mint, True, MONO)
        text(s, 850, 261, 320, 100, "99.98%", 60, fg, True)
        text(s, 850, 365, 320, 60, "Uptime over the last 90 days", 23, muted)
        add_status_pill(
            s,
            left=bb(850, 485, 0, 0).left,
            top=bb(0, 485, 0, 0).top,
            width=bb(0, 0, 310, 0).width,
            height=bb(0, 0, 0, 50).height,
            text="●  All systems operational",
            accent="#173C35",
            text_color=mint,
        )

    s = page(2)
    heading(s, "Readable code. Predictable results.", color=fg)
    with cluster(s):
        rect(s, 64, 272, 748, 340, panel, "#2B4157")
        text(s, 92, 294, 660, 30, "quickstart.ts", 18, muted, font=MONO)
        for y, line, col in [
            (354, 'import { Relay } from "relay";', mint),
            (400, "const relay = new Relay({ key });", fg),
            (446, "await relay.events.publish({", fg),
            (492, '  topic: "order.created",', "#FFCF8A"),
            (538, '  data: { id: "ord_42" }', "#FFCF8A"),
            (577, "});", fg),
        ]:
            text(s, 94, y, 695, 34, line, 21, col, font=MONO)
    text(s, 865, 295, 335, 100, "Less glue.\nMore product.", 40, fg, True)
    text(
        s,
        865,
        430,
        335,
        145,
        "Typed payloads.\nAutomatic retries.\nBuilt-in observability.",
        24,
        muted,
    )

    s = page(3)
    heading(s, "One path from event to action.", color=fg)
    horizontal_pipeline(
        s,
        bb(64, 290, 1152, 155),
        ["Events", "Queue", "Workers", "Your product"],
        accent=mint,
        fill=panel,
        text_color=fg,
        font=FONT,
        size_pt=18,
        card_line="#2B4157",
        card_radius=12,
        gap=bb(0, 0, 50, 0).width,
    )
    text(
        s,
        64,
        506,
        700,
        92,
        "Trace the whole journey.\nFind the slow hop before your users do.",
        27,
        muted,
    )
    add_progress_bar(
        s,
        left=bb(64, 617, 0, 0).left,
        top=bb(0, 617, 0, 0).top,
        width=bb(0, 0, 655, 0).width,
        height=bb(0, 0, 0, 5).height,
        fraction=0.82,
        fill_color=mint,
        track_color="#304057",
    )
    text(s, 910, 492, 300, 80, "142 ms", 54, mint, True, align="right")
    text(s, 910, 575, 300, 32, "p95 end-to-end latency", 19, muted, align="right")

    s = page(4)
    heading(s, "Faster at every scale.", color=fg)
    with cluster(s):
        rect(s, 64, 270, 810, 352, panel, "#2B4157")
        chart(
            s,
            (87, 294, 760, 300),
            XL_CHART_TYPE.LINE,
            ["1k", "5k", "10k", "25k", "50k"],
            [("Relay", [25, 30, 35, 39, 44]), ("Previous stack", [35, 54, 85, 127, 188])],
            [mint, "#6D87FE"],
            dark=True,
            legend=True,
        )
        for series in s.shapes[-1].chart.series:
            series.format.line.width = Pt(3)
    text(s, 926, 292, 280, 100, "4.3×", 72, mint, True)
    text(s, 926, 415, 280, 130, "Lower latency at\n50k events / second", 26, fg)
    text(s, 926, 562, 280, 54, "Illustrative load test\nLatency in milliseconds", 16, muted)
    return prs


def editorial():
    prs = deck("Fieldwork — editorial strategy")
    bg, green, muted, orange = "#F2EFE5", "#183F35", "#51685D", "#B8491D"

    def page(n):
        return slide(prs, "FIELDWORK / STUDIO JOURNAL", n, background=bg, color=muted, accent=green)

    s = page(1)
    text(s, 64, 140, 700, 246, "A little less.\nA lot better.", 86, green, font="DejaVu Serif")
    text(
        s,
        64,
        442,
        650,
        110,
        "Make room for the work that matters.\nA study in focus, craft, and useful restraint.",
        25,
        muted,
    )
    add_svg_figure(
        s, svg_art("flow", orange), *bb(762, 130, 455, 420)
    ).alt_text = "Nineteen orange curves form an abstract flowing field."
    s = page(2)
    heading(s, "Start with the space between.", color=green)
    for x, num, label, body in [
        (64, "01", "Remove the noise", "Give every element a reason to be here."),
        (466, "02", "Keep the rhythm", "Repeat a few decisions. Vary the scale."),
        (868, "03", "Leave some air", "Whitespace is part of the message."),
    ]:
        with cluster(s):
            rect(s, x, 290, 348, 320, "#FCFAF4", "#CBD1C5", radius=0)
            text(s, x + 26, 315, 285, 90, num, 68, orange, font="DejaVu Serif")
            text(s, x + 26, 430, 292, 40, label, 25, green, True)
            text(s, x + 26, 492, 284, 95, body, 23, muted)
    s = page(3)
    text(
        s,
        64,
        138,
        1140,
        330,
        "“The best interface\nis the one that makes\nthe work feel lighter.”",
        62,
        green,
        font="DejaVu Serif",
    )
    rect(s, 66, 528, 76, 4, orange, radius=0)
    text(s, 170, 516, 1000, 40, "A FIELDWORK DESIGN PRINCIPLE", 20, muted, True)
    text(
        s,
        170,
        574,
        1000,
        40,
        "A fictional studio, with a very real preference for clarity.",
        23,
        muted,
    )
    s = page(4)
    heading(s, "A season of small, deliberate moves.", color=green)
    for i, (season, title, body) in enumerate(
        [
            ("SPRING", "Listen closely", "Interview six teams.\nMap the daily friction."),
            ("SUMMER", "Make it tangible", "Prototype three moments.\nTest them in real work."),
            ("AUTUMN", "Keep what works", "Launch one useful change.\nMeasure the difference."),
        ]
    ):
        x = 64 + i * 402
        rect(s, x, 284, 348, 6, orange if i == 0 else "#A7B9AA", radius=0)
        text(s, x, 328, 348, 32, season, 19, muted, True)
        text(s, x, 398, 348, 80, title, 32, green, True)
        text(s, x, 500, 348, 100, body, 24, muted)
    return prs


def science(browser_path=None):
    import matplotlib

    matplotlib.use("Agg")
    import numpy as np
    from matplotlib import pyplot as plt

    prs = deck("Lumen — research briefing")
    s = slide(prs, "LUMEN / RESEARCH BRIEFING", 1, background="#F3F7FA", accent="#146F85")
    text(s, 64, 142, 740, 205, "Complex ideas.\nMade clear.", 68, bold=True)
    text(
        s,
        64,
        395,
        680,
        110,
        "A research story told through vector plots,\neditable annotations, and a browser visual.",
        25,
        MUTED,
    )
    add_svg_figure(
        s, svg_art(ink="#146F85"), *bb(800, 152, 410, 365)
    ).alt_text = "An orbital model represents connected research disciplines."

    s = slide(prs, "LUMEN / SIGNAL & UNCERTAINTY", 2, background="#F3F7FA", accent="#146F85")
    heading(s, "Keep the uncertainty visible.")
    x = np.linspace(0, 12, 70)
    mean = 14 + 2.6 * x + 2 * np.sin(x / 2)
    band = 3 + 0.15 * x
    fig, ax = plt.subplots(figsize=(8.7, 3.6), dpi=150)
    fig.patch.set_facecolor("#F3F7FA")
    ax.set_facecolor("#F3F7FA")
    ax.fill_between(x, mean - band, mean + band, color="#B5DBE5", alpha=0.8, label="95% interval")
    ax.plot(x, mean, color="#146F85", lw=3, label="Estimated response")
    ax.scatter(x[::6], mean[::6] + np.sin(x[::6]) * 1.2, s=23, color="#24374A", zorder=4)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color("#B9C9D7")
    ax.tick_params(colors=MUTED, labelsize=12, length=0, pad=10)
    ax.grid(axis="y", color="#D9E3EB", lw=0.6)
    ax.set_axisbelow(True)
    ax.set_xlabel("Observation window / weeks", fontsize=13, color=MUTED, labelpad=12)
    ax.set_ylabel("Response index", fontsize=13, color=MUTED, labelpad=12)
    fig.tight_layout(pad=1.4)
    add_matplotlib_figure(
        s, fig, *bb(60, 267, 850, 352), format="svg"
    ).alt_text = "Response rises from 14 to 45 over twelve weeks with a widening confidence band."
    plt.close(fig)
    text(s, 954, 300, 256, 80, "+31", 68, "#146F85", True)
    text(s, 954, 411, 256, 115, "Index points over\ntwelve weeks", 25)
    text(s, 954, 551, 256, 60, "Simulated observations.\nNo causal claim implied.", 17, MUTED)

    s = slide(prs, "LUMEN / MODEL LANDSCAPE", 3, background="#F3F7FA", accent="#146F85")
    heading(s, "A connected body of evidence.")
    with cluster(s):
        rect(s, 64, 269, 700, 354, "#10283B", radius=20)
        panel = HERE / "html" / "lumen-network.html"
        network = add_html_figure(
            s,
            panel,
            *bb(64, 269, 700, 354),
            viewport=(700, 354),
            selector=".map",
            omit_background=True,
            browser_path=browser_path,
        )
        network.alt_text = "Data, theory, methods, and review connect to a shared body of evidence."
    text(s, 816, 292, 390, 90, "A connected\nbody of evidence.", 35, bold=True)
    text(
        s,
        816,
        427,
        390,
        150,
        "HTML owns the network visual. PowerPoint owns this explanation, "
        "the heading, and the story.",
        24,
        MUTED,
    )

    # Declarative recipe + cross-deck import exercises composition with editable text.
    source = from_spec(
        {
            "slide_size": "16:9",
            "tokens": {"preset": "modern_light"},
            "slides": [{"layout": "blank", "shapes": []}],
        }
    )
    prs.import_slide(source.slides[0], merge_master="dedupe")
    s = prs.slides[-1]
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = "#F3F7FA"
    text(s, 64, 42, 1000, 30, "LUMEN / NEXT EXPERIMENT", 18, "#146F85", True)
    heading(s, "Three questions for the next experiment.")
    for i, (title, body) in enumerate(
        [
            ("Does it generalize?", "Replicate the effect across three new environments."),
            ("What changes it?", "Vary one assumption and observe the response."),
            ("What would disprove it?", "Pre-register the failure criteria before the next run."),
        ]
    ):
        x = 64 + i * 402
        text(s, x, 300, 348, 60, f"0{i + 1}", 38, "#146F85", True)
        text(s, x, 390, 348, 75, title, 30, bold=True)
        text(s, x, 495, 348, 125, body, 24, MUTED)
    text(s, 64, 670, 1000, 24, "SIMULATED RESEARCH / EDITABLE ANNOTATIONS", 14, MUTED)
    text(s, 1130, 666, 86, 30, "04 / 04", 17, MUTED, align="right")
    return prs


def finance(browser_path=None):
    import plotly.graph_objects as go

    prs = deck("Current — finance workspace")
    bg, blue, muted = "#F5F7FC", "#2556CD", MUTED
    s = slide(prs, "CURRENT / MONEY IN MOTION", 1, background=bg, accent=blue)
    text(s, 64, 145, 730, 218, "Your numbers.\nA clearer picture.", 66, bold=True)
    text(
        s,
        64,
        402,
        640,
        110,
        "A finance workspace built around decisions,\nwith the detail always one step away.",
        25,
        muted,
    )
    with cluster(s):
        card = rect(s, 830, 156, 368, 390, blue)
        card.fill.linear_gradient("#2859D2", "#133680", angle=70)
        text(s, 862, 195, 300, 35, "AVAILABLE BALANCE", 17, "#CCD9FF", True)
        text(s, 862, 280, 310, 90, "$248.6k", 51, "#FFFFFF", True)
        text(s, 862, 390, 300, 50, "↑ 12.8% this month", 24, "#B8F2D8", True)
        text(s, 862, 486, 300, 30, "CURRENT  ••••  0428", 19, "#CCD9FF", font=MONO)
    s = slide(prs, "CURRENT / CASH FLOW", 2, background=bg, accent=blue)
    heading(s, "See the flow behind the balance.")
    fig = go.Figure(
        go.Sankey(
            arrangement="fixed",
            node={
                "pad": 30,
                "thickness": 20,
                "line": {"width": 0},
                "label": [
                    "Product · 180",
                    "Services · 60",
                    "Cash in · 240",
                    "People · 120",
                    "Operations · 50",
                    "Retained · 70",
                ],
                "color": ["#2556CD", "#6A92EC", "#17364D", "#82B7A6", "#A3C7DD", "#B5A3F1"],
                "x": [0.02, 0.02, 0.40, 0.98, 0.98, 0.98],
                "y": [0.20, 0.80, 0.50, 0.10, 0.50, 0.90],
            },
            link={
                "source": [0, 1, 2, 2, 2],
                "target": [2, 2, 3, 4, 5],
                "value": [180, 60, 120, 50, 70],
                "color": ["#2556CD40", "#6A92EC40", "#82B7A670", "#A3C7DD70", "#B5A3F170"],
            },
        )
    )
    fig.update_layout(
        width=1100,
        height=350,
        margin={"l": 8, "r": 8, "t": 10, "b": 10},
        font={"family": FONT, "size": 18, "color": INK},
        paper_bgcolor=bg,
    )
    add_plotly_figure(
        s,
        fig,
        *bb(74, 285, 1120, 345),
        backend="browser",
        format="svg",
        browser_path=browser_path,
    ).alt_text = (
        "240 thousand cash in: 180 product and 60 services; 120 people, 50 operations, 70 retained."
    )
    s = slide(prs, "CURRENT / REVENUE MIX", 3, background=bg, accent=blue)
    heading(s, "Growth from more than one source.")
    with cluster(s):
        rect(s, 64, 271, 710, 350, "#FFFFFF", "#DFE5F0")
        c = chart(
            s,
            (90, 292, 365, 306),
            XL_CHART_TYPE.DOUGHNUT,
            ["Subscriptions", "Services", "Marketplace"],
            [("Revenue", [68, 22, 10])],
            [blue, "#80B9AC", "#B6A5E8"],
        )
        c.plots[0].hole_size = 74
        for y, label, val, col in [
            (335, "Subscriptions", "68%", blue),
            (417, "Services", "22%", "#377563"),
            (499, "Marketplace", "10%", "#76539F"),
        ]:
            rect(s, 470, y + 8, 12, 12, col, radius=0)
            text(s, 500, y, 230, 35, label, 21)
            text(s, 500, y + 33, 230, 40, val, 25, col, True)
    text(s, 834, 295, 365, 105, "$1.24m", 64, blue, True)
    text(s, 834, 416, 365, 90, "Annualized revenue\nacross three sources", 25)
    text(s, 834, 544, 365, 60, "+26% year over year\nIllustrative financials", 18, muted)
    s = slide(prs, "CURRENT / THE OPERATING PLAN", 4, background=bg, accent=blue)
    heading(s, "A plan that fits on one screen.")
    # Merged table heading; all cells retain native editing.
    t = s.shapes.add_table(6, 4, *bb(64, 272, 1152, 350), style="clean").table
    t.cell(0, 0).merge(t.cell(0, 3))
    t.cell(0, 0).text = "Q3 OPERATING PLAN / USD THOUSANDS"
    rows = [
        ("Initiative", "Budget", "Used", "Status"),
        ("Product platform", "240", "162", "On track"),
        ("Customer growth", "180", "126", "On track"),
        ("Data foundations", "120", "54", "Ahead"),
        ("Team & operations", "160", "112", "On track"),
    ]
    for r, row in enumerate(rows, 1):
        for c, value in enumerate(row):
            t.cell(r, c).text = value
    t.format_cells(
        font=FONT, size_pt=16, color=INK, fill="#FFFFFF", margin=(8, 16, 8, 16), anchor="middle"
    )
    t.format_cells(rows=0, fill=INK, color="#FFFFFF", bold=True, size_pt=14)
    t.format_cells(rows=1, fill="#E5EBF7", bold=True)
    t.columns[0].width = bb(0, 0, 480, 0).width
    for c in range(1, 4):
        t.columns[c].width = bb(0, 0, 224, 0).width
    t.format_cells(rows=slice(2, None), cols=3, color="#176C56", bold=True)
    for cell in t.iter_cells():
        cell.borders.none()
        cell.borders.bottom.width = Pt(0.5)
        cell.borders.bottom.color.rgb = "#DFE5F0"
    return prs


BUILDERS = {
    "01-forma": product,
    "02-relay": developer,
    "03-fieldwork": editorial,
    "04-lumen": science,
    "05-current": finance,
}
