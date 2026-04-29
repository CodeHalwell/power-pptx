"""Showcase 04 — Animations & transitions.

Animations don't render in static thumbnails, so this deck's review
artefact is the .pptx itself — open it in PowerPoint to see the
sequence. The script still proves the API exercises:

* Sequenced ``Entrance`` / ``Emphasis`` calls
* Per-paragraph reveal on a bullet body
* A motion path on a callout shape
* Per-slide transitions plus a deck-wide fade
"""

from __future__ import annotations

from pathlib import Path

from power_pptx import Presentation
from power_pptx.animation import Emphasis, Entrance, MotionPath, Trigger
from power_pptx.design.recipes import bullet_slide, kpi_slide, title_slide
from power_pptx.dml.color import RGBColor
from power_pptx.enum.presentation import MSO_TRANSITION_TYPE
from power_pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
from power_pptx.enum.text import PP_ALIGN
from power_pptx.util import Inches, Pt

from _lint import lint_or_die
from _tokens import BRAND

HERE = Path(__file__).parent


def build(out_path: Path) -> Presentation:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # 1. Title — full-slide entrance sequence
    s1 = title_slide(
        prs,
        title="Animations in power-pptx",
        subtitle="Click to advance — every effect is preset-driven",
        tokens=BRAND,
    )
    with s1.animations.sequence():
        Entrance.fade(s1, s1.shapes[0])           # title
        Entrance.fly_in(s1, s1.shapes[1], direction="bottom")  # subtitle

    # 2. Bullet — per-paragraph reveal
    s2 = bullet_slide(
        prs,
        title="Per-paragraph reveal",
        bullets=[
            "Each bullet enters on its own click",
            "Backed by Trigger.AFTER_PREVIOUS chaining",
            "Works for fade, wipe, zoom, wheel, random-bars",
            "Single API call — no manual timing tree edits",
        ],
        tokens=BRAND,
    )
    body_tf = s2.shapes[1].text_frame
    Entrance.fade(s2, body_tf, by_paragraph=True)

    # 3. KPI — emphasis pulse on every card
    s3 = kpi_slide(
        prs,
        title="Emphasis pulse",
        kpis=[
            {"label": "Latency",    "value": "42 ms",  "delta": -0.18},
            {"label": "Throughput", "value": "12k/s",  "delta": +0.22},
            {"label": "Errors",     "value": "0.04%",  "delta": -0.30},
        ],
        tokens=BRAND,
    )
    # Pulse each KPI card on its own click. ``shape_type`` reports
    # ``AUTO_SHAPE`` for every auto-shape; the actual subtype lives on
    # ``auto_shape_type`` (which raises on non-auto-shapes, so the
    # ``shape_type`` test has to come first).
    with s3.animations.sequence():
        for shape in s3.shapes:
            if (shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
                    and shape.auto_shape_type == MSO_SHAPE.ROUNDED_RECTANGLE):
                Emphasis.pulse(s3, shape)

    # 4. Motion path
    s4 = prs.slides.add_slide(prs.slide_layouts[6])
    title_box = s4.shapes.add_textbox(
        Inches(0.6), Inches(0.4), Inches(12), Inches(1.0),
    )
    title_box.text_frame.text = "Motion path"
    title_box.text_frame.fit_text(font_family="Inter", max_size=36, bold=True)
    title_box.text_frame.paragraphs[0].font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)

    badge = s4.shapes.add_shape(
        MSO_SHAPE.OVAL,
        Inches(1.5), Inches(4.5), Inches(1.5), Inches(1.5),
    )
    badge.fill.solid()
    badge.fill.fore_color.rgb = RGBColor(0x4F, 0x46, 0xE5)
    badge.line.fill.background()
    badge.text_frame.text = "Go"
    p = badge.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.runs[0]
    run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    run.font.bold = True
    run.font.size = Pt(28)

    Entrance.fade(s4, badge)
    MotionPath.arc(
        s4, badge,
        dx=Inches(8), dy=Inches(0), height=0.4,
        trigger=Trigger.AFTER_PREVIOUS,
    )
    Emphasis.spin(s4, badge, trigger=Trigger.AFTER_PREVIOUS)

    # Transitions: deck-wide fade, then upgrade slide 1 to Morph.
    prs.set_transition(kind=MSO_TRANSITION_TYPE.FADE, duration=400)
    prs.slides[0].transition.kind = MSO_TRANSITION_TYPE.MORPH
    prs.slides[0].transition.duration = 1200
    prs.slides[3].transition.kind = MSO_TRANSITION_TYPE.PUSH
    prs.slides[3].transition.duration = 600

    lint_or_die(prs)
    prs.save(out_path)
    return prs


if __name__ == "__main__":
    out = HERE / "_out" / "04_animations.pptx"
    out.parent.mkdir(exist_ok=True)
    build(out)
    print(f"wrote {out}")
