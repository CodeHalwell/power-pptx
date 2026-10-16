"""Build, validate, and optionally render the modern design gallery.

The schema validator is provided by the installed library.
Rendering every slide is required before an output is ready for visual review.
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
import traceback
from html import escape
from pathlib import Path
from zipfile import ZipFile

from lxml import etree
from lxml.html import fromstring as parse_html
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT), str(HERE)]

from _native import BUILDERS  # noqa: E402

from power_pptx import Presentation, audit  # noqa: E402
from power_pptx.compose import from_html  # noqa: E402
from power_pptx.render import render_slides  # noqa: E402
from power_pptx.validation import (  # noqa: E402
    iter_schema_violations,
    schema_validation_available,
)

DESCRIPTIONS = {
    "01-forma": (
        "Forma",
        "Editable product UI",
        "Native text, cards, shadows, chart, KPI component, pipeline, comparison table",
    ),
    "02-relay": (
        "Relay",
        "Editable developer platform",
        "Dark theme, gradient card, status pill, code, routed arrows, line chart",
    ),
    "03-fieldwork": (
        "Fieldwork",
        "Editable editorial",
        "Serif display type, whitespace, inline SVG, quote, seasonal timeline",
    ),
    "04-lumen": (
        "Lumen",
        "Hybrid research",
        "Matplotlib SVG with uncertainty, HTML network panel, native labels, slide import",
    ),
    "05-current": (
        "Current",
        "Hybrid finance",
        "Gradient card, Plotly Sankey via HTML, native doughnut, merged and styled native table",
    ),
    "06-aster": (
        "Aster",
        "Captured HTML",
        "CSS gradients, glass panels, backdrop filters, SVG network, layered interface",
    ),
    "07-daily": (
        "Daily",
        "Captured HTML",
        "SVG packaging, rotation, drop shadows, CSS grid, asymmetric commerce layout",
    ),
    "08-offgrid": (
        "Offgrid",
        "Captured HTML",
        "Oversized typography, clip paths, SVG poster, programmatic canvas, CSS schedule",
    ),
}
DOCUMENTS = {
    name: HERE / "html" / f"{name}.html" for name in DESCRIPTIONS if name[:2] in {"06", "07", "08"}
}


def parts(blob):
    with ZipFile(io.BytesIO(blob)) as z:
        return {name: z.read(name) for name in z.namelist()}


def save_bytes(prs):
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def canonical(blob):
    root = etree.fromstring(blob, etree.XMLParser(remove_blank_text=True))
    return etree.tostring(root, method="c14n2")


def validate(prs, path):
    """Structural gates supplement visual review; they do not certify appearance."""
    if not schema_validation_available():
        raise RuntimeError("The installed ISO-29500 schemas are required for this gallery")
    first = save_bytes(prs)
    path.write_bytes(first)
    second = save_bytes(Presentation(io.BytesIO(first)))
    before, after = parts(first), parts(second)
    changed = []
    for name in before.keys() | after.keys():
        a, b = before.get(name), after.get(name)
        if a is not None and b is not None and name.endswith((".xml", ".rels")):
            a, b = canonical(a), canonical(b)
        if a != b:
            changed.append(name)
    violations = list(iter_schema_violations(path))
    report = audit(prs)
    lint_errors = [
        f"slide {idx}: {issue}"
        for idx, issue in report.lint_issues
        if issue.severity.value == "error"
    ]
    result = {
        "slides": len(prs.slides),
        "schema_violations": violations,
        "roundtrip_changed_parts": changed,
        "lint_errors": lint_errors,
        "lint_warnings": [
            f"slide {idx}: {issue}"
            for idx, issue in report.lint_issues
            if issue.severity.value != "error"
        ],
        "broken_pictures": len(report.broken_pictures),
        "empty_slides": report.empty_slides,
        "font_warnings": report.font_warnings,
        "native_charts": sum(sh.has_chart for s in prs.slides for sh in s.shapes),
        "native_tables": sum(sh.has_table for s in prs.slides for sh in s.shapes),
        "text_shapes": sum(
            sh.has_text_frame and bool(sh.text.strip()) for s in prs.slides for sh in s.shapes
        ),
        "svg_parts": sum(n.endswith(".svg") for n in before),
        "structural_pass": not (
            violations
            or changed
            or report.lint_issues
            or report.broken_pictures
            or report.empty_slides
        ),
    }
    return result, report.markdown()


def contact_sheet(paths, target, title, *, start_index=0):
    """Large enough for manual type / spacing review, with one row per two slides."""
    thumb_w, thumb_h, gutter, label = 768, 432, 20, 36
    rows = (len(paths) + 1) // 2
    canvas = Image.new(
        "RGB", (thumb_w * 2 + gutter * 3, rows * (thumb_h + label + gutter) + 70), "#E2E7F0"
    )
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype("DejaVuSans.ttf", 21)
    draw.text((gutter, 22), title, font=font, fill="#172334")
    for i, path in enumerate(paths):
        x, y = gutter + (i % 2) * (thumb_w + gutter), 70 + (i // 2) * (thumb_h + label + gutter)
        with Image.open(path) as im:
            canvas.paste(
                im.convert("RGB").resize((thumb_w, thumb_h), Image.Resampling.LANCZOS), (x, y)
            )
        draw.text(
            (x, y + thumb_h + 7), f"Slide {start_index + i + 1:02d}", font=font, fill="#172334"
        )
    canvas.save(target)


def browser_render_error(prs, paths):
    """Mean per-channel absolute error, normalized to 0..1 after resizing."""
    errors = []
    for slide, path in zip(prs.slides, paths):
        with (
            Image.open(io.BytesIO(slide.shapes[0].image.blob)) as ref,
            Image.open(path) as rendered,
        ):
            ref = ref.convert("RGB").resize(rendered.size, Image.Resampling.LANCZOS)
            stat = ImageStat.Stat(ImageChops.difference(ref, rendered.convert("RGB")))
            errors.append(round(sum(stat.mean) / (3 * 255), 5))
    return errors


def gallery(out, records):
    cards = []
    for name, record in records.items():
        title, mode, features = DESCRIPTIONS[name]
        previews = (
            "".join(
                f'<a href="{name}/slide-{i:02d}.png"><img loading="lazy" '
                f'src="{name}/slide-{i:02d}.png" alt="{escape(title)} slide {i + 1}"></a>'
                for i in range(record.get("slides", 0))
            )
            if record.get("rendered")
            else ""
        )
        cards.append(
            f'<article><div class="bar"><h2>{title}</h2><span>{mode}</span>'
            f'<a href="{name}.pptx" download>Download PPTX</a></div>'
            f'<p>{features}</p><div class="slides">{previews}</div></article>'
        )
    template = (HERE / "gallery.html").read_text(encoding="utf-8")
    html = template.replace("{{CARDS}}", "".join(cards))
    html = html.replace(
        "{{COUNTS}}",
        f"{len(records)} directions. {sum(r.get('slides', 0) for r in records.values())} slides.",
    )
    expected = sum(r.get("slides", 0) for r in records.values() if r.get("rendered"))
    if len(parse_html(html).xpath("//div[@class='slides']//img")) != expected:
        raise RuntimeError("Gallery template must display every rendered slide")
    (out / "index.html").write_text(html, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=HERE / "_out")
    parser.add_argument("--browser-path")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--deck", action="append", choices=list(DESCRIPTIONS))
    args = parser.parse_args()
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "html").mkdir(exist_ok=True)
    (out / "source").mkdir(exist_ok=True)
    for path in HERE.glob("*.py"):
        shutil.copy2(path, out / "source" / path.name)
    shutil.copy2(HERE / "gallery.html", out / "source" / "gallery.html")
    shutil.copytree(HERE / "html", out / "source" / "html", dirs_exist_ok=True)
    if (HERE / "README.md").exists():
        shutil.copy2(HERE / "README.md", out / "source" / "README.md")
    # Keep existing entries when refining one deck; stale files never count as a render pass.
    records = (
        json.loads((out / "manifest.json").read_text()) if (out / "manifest.json").exists() else {}
    )
    failures = []
    for name in args.deck or list(DESCRIPTIONS):
        try:
            if name in DOCUMENTS:
                source = out / "html" / f"{name}.html"
                shutil.copy2(DOCUMENTS[name], source)
                prs = from_html(
                    source,
                    browser_path=args.browser_path,
                    wait_for_function="window.deckReady === true",
                )
            else:
                builder = BUILDERS[name]
                prs = (
                    builder(browser_path=args.browser_path)
                    if name in {"04-lumen", "05-current"}
                    else builder()
                )
                for s in prs.slides:
                    if not s.has_notes_slide:
                        s.notes_slide.notes_text_frame.text = "\n".join(
                            sh.text for sh in s.shapes if sh.has_text_frame and sh.text.strip()
                        )
            record, audit_md = validate(prs, out / f"{name}.pptx")
            record["rendered"] = False
            (out / f"{name}-audit.md").write_text(audit_md, encoding="utf-8")
            records[name] = record
            if args.render:
                paths = render_slides(
                    prs,
                    out_dir=out / name,
                    name_template="slide-{:02d}.png",
                    strategy="pdf",
                    dpi=96,
                )
                if len(paths) != len(prs.slides):
                    raise RuntimeError("Every slide must render")
                record["rendered"] = True
                contact_sheet(paths, out / f"{name}-contact.png", DESCRIPTIONS[name][0])
                if name in DOCUMENTS:
                    record["browser_render_mean_error"] = browser_render_error(prs, paths)
                    if any(error > 0.015 for error in record["browser_render_mean_error"]):
                        raise RuntimeError(
                            "HTML render differs materially from its browser reference"
                        )
            print(
                f"{name}: {record['slides']} slides; "
                f"structure={'PASS' if record['structural_pass'] else 'FAIL'}; "
                f"rendered={record['rendered']}",
                flush=True,
            )
            if not record["structural_pass"]:
                failures.append(name)
        except Exception:
            failures.append(name)
            records[name] = {
                "error": traceback.format_exc(),
                "structural_pass": False,
                "rendered": False,
            }
            print(f"{name}: FAILED\n{records[name]['error']}", flush=True)
        (out / "manifest.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    gallery(out, records)
    (out / "REVIEW.md").write_text(
        "# Visual review pending\n\nThe manifest records automated checks only. "
        "Inspect every rendered slide and record findings here before approving appearance.\n",
        encoding="utf-8",
    )
    if failures:
        raise SystemExit(f"Fix failures before review: {', '.join(failures)}")


if __name__ == "__main__":
    main()
