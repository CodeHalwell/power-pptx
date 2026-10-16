"""Exercise the installed component, hybrid, Plotly, and review APIs together."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import plotly.graph_objects as go

from power_pptx import BBox, Presentation, add_plotly_figure
from power_pptx.chart.data import CategoryChartData
from power_pptx.compose import from_html
from power_pptx.design import Badge, Card, Column, MetricTile, NativeContent, Row, TextBlock
from power_pptx.dml.color import RGBColor
from power_pptx.enum.chart import XL_CHART_TYPE
from power_pptx.review import review_presentation
from power_pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
FONT = "DejaVu Sans"
INK, MUTED, PURPLE = "#172334", "#526176", "#6554E8"


def text(value, size=18, **kwargs):
    kwargs.setdefault("min_size_pt", min(12, size))
    return TextBlock(value, size_pt=size, font=FONT, **kwargs)


def deck(title):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(40 / 3), Inches(7.5)
    prs.theme.fonts.major = prs.theme.fonts.minor = FONT
    prs.core_properties.title = title
    return prs


def page(prs, number, title, content, *, dark=False):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = RGBColor.from_hex("101B2D" if dark else "F2F5FA")
    tree = Column(
        [
            text(
                f"NORTHSTAR  /  PRODUCT BRIEF  /  {number:02}",
                11,
                color="#B8C9E5" if dark else MUTED,
                bold=True,
            ),
            text(
                title,
                38,
                min_size_pt=34,
                max_lines=2,
                preserve_breaks=True,
                bold=True,
                color="#FFFFFF" if dark else INK,
            ),
            content,
        ],
        gap=Pt(24),
    )
    tree.render(slide, BBox.from_inches(0.65, 0.45, 12.03, 6.6), strict_fonts=True)
    return slide


def native():
    prs = deck("Northstar — declarative native components")
    page(
        prs,
        1,
        "Less coordination.\nMore momentum.",
        Row(
            [
                Card(
                    [
                        Row([Badge("LIVE WORKSPACE", font=FONT), text("01", 12, align="right")]),
                        text("Everything in its right place.", 24, bold=True, max_lines=2),
                        text(
                            "One shared view of the work, the decisions, and what happens next.",
                            18,
                            color=MUTED,
                        ),
                    ],
                    grow=1.5,
                ),
                Card(
                    [
                        text("THIS WEEK", 12, color=MUTED, bold=True),
                        text("12 hours", 34, color=PURPLE, bold=True, max_lines=1),
                        text("given back to the team", 18, color=MUTED),
                    ]
                ),
            ],
            gap=Pt(18),
            height=Inches(3.25),
        ),
    )
    page(
        prs,
        2,
        "A calmer operating rhythm.",
        Column(
            [
                Row(
                    [
                        MetricTile("94%", "TEAM ADOPTION", detail="Across 18 teams", font=FONT),
                        MetricTile(
                            "2.4×", "FASTER DECISIONS", detail="From signal to action", font=FONT
                        ),
                        MetricTile(
                            "−38%", "MEETING HOURS", detail="More room for deep work", font=FONT
                        ),
                    ],
                    gap=Pt(18),
                    height=Inches(2.5),
                ),
                Row(
                    [
                        Card(
                            [
                                text("01  Align", 20, bold=True),
                                text("Start with the outcome.", color=MUTED),
                            ]
                        ),
                        Card(
                            [
                                text("02  Decide", 20, bold=True),
                                text("Make the next move clear.", color=MUTED),
                            ]
                        ),
                        Card(
                            [
                                text("03  Deliver", 20, bold=True),
                                text("Close the loop together.", color=MUTED),
                            ]
                        ),
                    ],
                    gap=Pt(18),
                ),
            ],
            gap=Pt(18),
            height=Inches(4.75),
        ),
    )

    def chart(slide, box):
        data = CategoryChartData()
        data.categories = ["Week 1", "Week 2", "Week 3", "Week 4"]
        data.add_series("Activation", [42, 58, 73, 94])
        result = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, *box, data)
        result.chart.apply_quick_layout("minimal")
        result.chart.recolour([PURPLE])
        result.chart.font.name = FONT
        result.chart.font.size = Pt(12)
        return result

    page(
        prs,
        3,
        "Adoption that builds on itself.",
        Row(
            [
                Card(
                    [
                        text("Weekly activation", 20, bold=True),
                        NativeContent(chart, height=Inches(2.75)),
                    ],
                    grow=1.8,
                ),
                Column(
                    [
                        text("94%", 58, min_size_pt=50, color="#C9C1FF", bold=True, max_lines=1),
                        text(
                            "of the team is active\nby week four.",
                            22,
                            color="#FFFFFF",
                            preserve_breaks=True,
                        ),
                        text(
                            "The right defaults make\ngood habits feel effortless.",
                            16,
                            color="#B8C9E5",
                            preserve_breaks=True,
                        ),
                    ],
                    width=Inches(3.6),
                    gap=Pt(16),
                ),
            ],
            gap=Pt(28),
            height=Inches(4.55),
        ),
        dark=True,
    )
    return prs


def figures(browser_path):
    prs = deck("Signal — figures through the browser backend")
    specs = [
        (
            "01  /  Flow of funds",
            "Where the momentum goes.",
            go.Sankey(
                node={
                    "label": ["Product", "Services", "Team", "Operations", "Reinvest"],
                    "color": [PURPLE, "#A59AEF", "#263D60", "#589989", "#C7AC74"],
                    "pad": 28,
                    "thickness": 22,
                },
                link={
                    "source": [0, 0, 0, 1, 1],
                    "target": [2, 3, 4, 2, 4],
                    "value": [75, 45, 60, 25, 35],
                    "color": "rgba(101,84,232,.19)",
                },
            ),
            "svg",
        ),
        (
            "02  /  Retention",
            "Good experiences compound.",
            go.Scatter(
                x=["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
                y=[61, 68, 73, 82, 88, 94],
                mode="lines+markers",
                line={"color": PURPLE, "width": 5, "shape": "spline"},
                marker={"size": 12},
                fill="tozeroy",
                fillcolor="rgba(101,84,232,.10)",
            ),
            "png",
        ),
        (
            "03  /  Allocation",
            "A balanced portfolio of bets.",
            go.Treemap(
                labels=["Roadmap", "Core", "Growth", "Explore", "Platform", "Mobile", "Search"],
                parents=["", "Roadmap", "Roadmap", "Roadmap", "Core", "Core", "Growth"],
                values=[100, 55, 30, 15, 35, 20, 30],
                branchvalues="total",
                marker={
                    "colors": [
                        "#FFFFFF",
                        PURPLE,
                        "#589989",
                        "#C7AC74",
                        "#6554E8",
                        "#9688E8",
                        "#589989",
                    ]
                },
            ),
            "svg",
        ),
    ]
    for index, (label, title, trace, fmt) in enumerate(specs, 1):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        Column(
            [
                text(f"SIGNAL  /  {label.upper()}", 11, color=MUTED, bold=True),
                text(title, 34, bold=True, max_lines=1),
            ],
            gap=Pt(18),
        ).render(slide, BBox.from_inches(0.65, 0.45, 12, 1.4), strict_fonts=True)
        fig = go.Figure(trace)
        fig.update_layout(
            width=1120,
            height=400,
            paper_bgcolor="white",
            plot_bgcolor="white",
            margin={"l": 35, "r": 35, "t": 15, "b": 40},
            showlegend=False,
            font={"family": FONT, "size": 20, "color": INK},
        )
        if index == 2:
            fig.update_yaxes(range=[0, 105], ticksuffix="%", gridcolor="#E6EBF2", zeroline=False)
        add_plotly_figure(
            slide,
            fig,
            *BBox.from_inches(0.65, 2.05, 12, 4.3),
            backend="browser",
            format=fmt,
            browser_path=browser_path,
        )
        text(
            "Self-contained Plotly · browser export · SVG with PNG fallback"
            if fmt == "svg"
            else "Self-contained Plotly · browser export · high density PNG",
            11,
            color=MUTED,
        ).render(slide, BBox.from_inches(0.65, 6.85, 12, 0.3), strict_fonts=True)
    return prs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--browser-path")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    references = args.out_dir / "html-source-reference"
    decks = {
        "01-components": native(),
        "02-hybrid": from_html(
            HERE / "hybrid.html",
            mode="hybrid",
            browser_path=args.browser_path,
            reference_dir=references,
        ),
        "03-browser-figures": figures(args.browser_path),
    }
    results = []
    for name, prs in decks.items():
        report = review_presentation(
            prs,
            out_dir=args.out_dir / name,
            dpi=120,
            font_policy="error",
            reference_dir=references if name == "02-hybrid" else None,
        )
        results.append(
            {
                "name": name,
                "passed": not report.has_errors,
                "slides": len(prs.slides),
                "errors": report.manifest["errors"],
            }
        )
        print(name, results[-1], flush=True)
    (args.out_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    links = "".join(
        f'<li><a href="{r["name"]}/index.html">{r["name"]}</a> — {r["slides"]} slides</li>'
        for r in results
    )
    (args.out_dir / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Authoring workflows</title>'
        f"<h1>Authoring workflows</h1><ul>{links}</ul>",
        encoding="utf-8",
    )
    if not all(r["passed"] for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
