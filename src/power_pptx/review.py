"""Build inspectable slide review artifacts from the installed library.

Use ``power-pptx review deck.pptx --out-dir review`` or import
``review_presentation``. Automated success always leaves visual review pending.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import shutil
import sys
import tempfile
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFont, ImageStat

from power_pptx.validation import presentation_bytes, validate_presentation


@dataclass(frozen=True)
class ReviewReport:
    directory: Path
    manifest: dict[str, Any]

    @property
    def has_errors(self):
        return not self.manifest["passed"]

    @property
    def images(self):
        return [self.directory / path for path in self.manifest["slides"]]


def _render(prs, directory, *, dpi, soffice_bin, timeout, font_dirs=None):
    from power_pptx.render import _pdf_to_pngs, _resolve_binary, _run_soffice_pdf, _soffice_env

    # One PDF conversion provides both the deliverable PDF and every PNG.
    with tempfile.TemporaryDirectory(prefix="pptx-review-render-") as tmp:
        work = Path(tmp)
        deck = work / "presentation.pptx"
        prs.save(deck)
        env = _soffice_env(work, font_dirs)
        result = _run_soffice_pdf(_resolve_binary(soffice_bin), deck, work, timeout, env=env)
        pdf = work / "presentation.pdf"
        if result.returncode or not pdf.is_file():
            raise RuntimeError(
                "LibreOffice PDF export failed: " + result.stderr.decode("utf-8", "replace")[:2000]
            )
        pages = _pdf_to_pngs(pdf, work, dpi=dpi)
        if len(pages) != len(prs.slides):
            raise RuntimeError(f"Expected {len(prs.slides)} rendered pages; received {len(pages)}")
        shutil.copy2(pdf, directory / "presentation.pdf")
        target = directory / "slides"
        target.mkdir()
        outputs = []
        for index, path in enumerate(pages):
            dest = target / f"slide-{index:02d}.png"
            shutil.copy2(path, dest)
            outputs.append(dest)
        return outputs


def _contact_sheets(images, directory):
    sheets = []
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    resampling: Any = getattr(getattr(Image, "Resampling", Image), "LANCZOS", 1)
    for start in range(0, len(images), 8):
        pages = images[start : start + 8]
        with Image.open(pages[0]) as first:
            ratio = first.height / first.width
        width, height = 640, round(640 * ratio)
        canvas = Image.new(
            "RGB", (width * 2 + 60, ((len(pages) + 1) // 2) * (height + 55) + 20), "#E3E9F2"
        )
        draw = ImageDraw.Draw(canvas)
        for offset, path in enumerate(pages):
            x = 20 + (offset % 2) * (width + 20)
            y = 20 + (offset // 2) * (height + 55)
            with Image.open(path) as source:
                preview = source.convert("RGB")
                preview.thumbnail((width, height), resampling)
                canvas.paste(preview, (x, y))
            draw.text(
                (x, y + height + 8), f"Slide {start + offset + 1:02d}", font=font, fill="#172334"
            )
        target = directory / f"contact-{start // 8 + 1:02d}.png"
        canvas.save(target)
        sheets.append(target.name)
    return sheets


def _compare(images, references, directory, max_mean_error):
    from power_pptx.render import _natural_sort_key

    paths = sorted(Path(references).glob("*.png"), key=_natural_sort_key)
    if len(paths) != len(images):
        raise ValueError(
            f"Reference count {len(paths)} does not match rendered slide count {len(images)}"
        )
    target = directory / "references"
    target.mkdir()
    diff_dir = directory / "differences"
    diff_dir.mkdir()
    metrics = []
    resampling: Any = getattr(getattr(Image, "Resampling", Image), "LANCZOS", 1)
    for index, (actual, reference) in enumerate(zip(images, paths)):
        with Image.open(actual) as actual_image, Image.open(reference) as reference_image:
            a = actual_image.convert("RGB")
            b = reference_image.convert("RGB")
            if abs((a.width / a.height) / (b.width / b.height) - 1) > 0.01:
                raise ValueError(f"Reference slide {index + 1} has a different aspect ratio")
            b = b.resize(a.size, resampling)
            difference = ImageChops.difference(a, b)
            error = sum(ImageStat.Stat(difference).mean) / (3 * 255)
            ImageEnhance.Brightness(difference).enhance(4).save(diff_dir / f"slide-{index:02d}.png")
            b.save(target / f"slide-{index:02d}.png")
            metrics.append(
                {
                    "slide": index + 1,
                    "mean_error": round(error, 6),
                    "within_tolerance": None if max_mean_error is None else error <= max_mean_error,
                }
            )
    return metrics


def _index(directory, manifest):
    cards = []
    for index, path in enumerate(manifest["slides"]):
        extra = ""
        if manifest["comparisons"]:
            metric = manifest["comparisons"][index]
            extra = (
                f"<p>Mean pixel error: {metric['mean_error']:.2%} · "
                f'<a href="references/slide-{index:02d}.png">Reference</a> · '
                f'<a href="differences/slide-{index:02d}.png">Difference ×4</a></p>'
            )
        cards.append(
            f'<article><h2>Slide {index + 1:02d}</h2><a href="{path}">'
            f'<img src="{path}" alt="Rendered slide {index + 1}" loading="lazy">'
            f"</a>{extra}</article>"
        )
    status = "Automated checks passed" if manifest["passed"] else "Automated checks need attention"
    errors = "".join(f"<li>{escape(message)}</li>" for message in manifest["errors"])
    links = [
        ("presentation.pptx", "PowerPoint"),
        ("presentation.pdf", "PDF"),
        ("manifest.json", "Validation results"),
        ("REVIEW.md", "Review notes"),
    ]
    navigation = " · ".join(
        f'<a href="{path}">{label}</a>' for path, label in links if (directory / path).is_file()
    )
    fonts = manifest["validation"].get("missing_fonts", [])
    warning = f"<p>Missing native fonts: {escape(', '.join(fonts))}</p>" if fonts else ""
    html = f"""<!doctype html><html lang="en"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>Slide review</title>
    <style>
    body{{font:17px/1.6 system-ui,sans-serif;background:#111827;color:#edf3ff;
    margin:40px auto;padding:0 24px;max-width:1500px}}
    h1{{font-size:42px}}a{{color:#b8ccff}}
    .grid{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}
    img{{width:100%;display:block;border:1px solid #40506a;border-radius:8px}}
    h2{{font-size:21px}}@media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}
    </style>
    <h1>{escape(manifest["title"])}</h1><p>{status}. Visual review: <strong>pending</strong>.</p>
    <p>Inspect every saved-PPTX render for typography, wrapping, clipping, contrast,
    and composition. Structural checks and image differences do not certify
    appearance or PowerPoint playback.</p>
    <p>{navigation}</p>{warning}<ul>{errors}</ul><div class="grid">{"".join(cards)}</div></html>"""
    (directory / "index.html").write_text(html, encoding="utf-8")


def review_presentation(
    source,
    *,
    out_dir,
    reference_dir=None,
    reference_html=None,
    selector: str = "[data-slide]",
    viewport: tuple[int, int] = (1280, 720),
    wait_for_function: str | None = None,
    browser_path=None,
    dpi: int = 120,
    soffice_bin=None,
    timeout: int = 120,
    max_mean_error: float | None = None,
    font_policy: str = "warn",
    fail_on_warnings: bool = False,
    check_schema: bool = True,
    font_dirs=None,
) -> ReviewReport:
    """Validate and render every slide, producing PPTX, PDF, PNGs, and a gallery.

    ``source`` is a Presentation, PPTX path, or bytes. References can be a
    directory of naturally sorted PNGs or an HTML slide document. Comparison
    is advisory unless ``max_mean_error`` supplies a normalized 0..1 limit.
    ``font_policy`` controls missing explicit native fonts: warn/error/ignore.
    Validation and rendering failures are recorded so batch callers can keep
    their review artifacts. Invalid options and missing input files raise.
    Input files are never overwritten. Only files from this run appear in the
    manifest/gallery; pre-existing output PNGs cannot count as rendered pages.
    ``font_dirs`` are registered for font checks and handed to LibreOffice, as
    are folders already registered with ``register_font_dir``.
    """
    from power_pptx import Presentation

    if reference_dir is not None and reference_html is not None:
        raise ValueError("Choose reference_dir or reference_html")
    if font_policy not in {"warn", "error", "ignore"}:
        raise ValueError("font_policy must be warn, error, or ignore")
    if isinstance(dpi, bool) or not isinstance(dpi, int) or dpi <= 0 or timeout <= 0:
        raise ValueError("dpi and timeout must be positive")
    if max_mean_error is not None and (
        not math.isfinite(max_mean_error) or not 0 <= max_mean_error <= 1
    ):
        raise ValueError("max_mean_error must be between 0 and 1")
    if font_dirs:
        from power_pptx.text.fonts import register_font_dir

        for directory in font_dirs:
            register_font_dir(directory)
    out = Path(out_dir).resolve()
    if (
        isinstance(source, (str, Path))
        and Path(source).resolve() == (out / "presentation.pptx").resolve()
    ):
        raise ValueError("Review output cannot overwrite its input presentation")
    if reference_dir is not None and not Path(reference_dir).is_dir():
        raise ValueError("reference_dir must be an existing directory")
    data = presentation_bytes(source)
    validation = validate_presentation(
        data, check_schema=check_schema, check_fonts=font_policy != "ignore"
    )
    errors = list(validation.errors)
    if validation.schema_violations:
        errors.append("OOXML schema/package validation failed")
    if validation.roundtrip_changed_parts:
        errors.append("Save/reopen round-trip changed package parts")
    if validation.audit.get("has_errors"):
        errors.append("Deck audit found errors")
    if validation.audit.get("empty_slides"):
        errors.append("Deck contains empty slides")
    if font_policy == "error" and validation.missing_fonts:
        errors.append("Missing native fonts: " + ", ".join(validation.missing_fonts))
    if fail_on_warnings and (
        validation.missing_fonts
        or any(i["severity"] != "error" for i in validation.audit.get("lint_issues", []))
    ):
        errors.append("Warnings are configured to fail this review")
    manifest = {
        "title": "Slide review",
        "slide_count": validation.slide_count,
        "validation": validation.to_dict(),
        "slides": [],
        "contact_sheets": [],
        "comparisons": [],
        "errors": errors,
        "passed": False,
        "visual_review": "pending",
        "renderer": "LibreOffice PDF + Poppler or PDFium",
        "dpi": dpi,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pptx-review-stage-", dir=out.parent) as tmp:
        stage = Path(tmp)
        (stage / "presentation.pptx").write_bytes(data)
        try:
            prs = Presentation(io.BytesIO(data))
            manifest["title"] = prs.core_properties.title or "Slide review"
            if not len(prs.slides):
                raise ValueError("Presentation has no slides")
            images = _render(
                prs,
                stage,
                dpi=dpi,
                soffice_bin=soffice_bin,
                timeout=timeout,
                font_dirs=font_dirs,
            )
            manifest["slides"] = [p.relative_to(stage).as_posix() for p in images]
            manifest["contact_sheets"] = _contact_sheets(images, stage)
            if reference_html is not None:
                from power_pptx.design._html import capture_html

                refs = stage / "browser-reference"
                refs.mkdir()
                captures = capture_html(
                    reference_html,
                    selector=selector,
                    multiple=True,
                    viewport=viewport,
                    browser_path=browser_path,
                    wait_for_function=wait_for_function,
                )
                for i, capture in enumerate(captures):
                    (refs / f"slide-{i:02d}.png").write_bytes(capture.png)
                reference_dir = refs
            if reference_dir is not None:
                manifest["comparisons"] = _compare(images, reference_dir, stage, max_mean_error)
                if any(item["within_tolerance"] is False for item in manifest["comparisons"]):
                    errors.append("Rendered slides exceed the requested reference difference limit")
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        manifest["passed"] = not errors
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (stage / "REVIEW.md").write_text(
            "# Visual review pending\n\nInspect every rendered slide and record findings here.\n"
            "Automated checks and pixel comparisons are supporting evidence.\n",
            encoding="utf-8",
        )
        _index(stage, manifest)
        out.mkdir(parents=True, exist_ok=True)
        # Copy only this run's staging files. The manifest never discovers
        # images by globbing an output directory from a previous run.
        shutil.copytree(stage, out, dirs_exist_ok=True)
    return ReviewReport(out, manifest)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="power-pptx review", description=__doc__)
    parser.add_argument(
        "inputs", nargs="+", type=Path, help="PPTX, HTML, JSON, or YAML slide sources"
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--reference-html", type=Path)
    parser.add_argument("--reference-dir", type=Path)
    parser.add_argument("--mode", choices=["capture", "hybrid"], default="capture")
    parser.add_argument("--browser-path")
    parser.add_argument("--ready", help="JavaScript expression indicating application readiness")
    parser.add_argument("--selector", default="[data-slide]")
    parser.add_argument("--dpi", type=int, default=120)
    parser.add_argument("--soffice-bin")
    parser.add_argument("--max-error", type=float)
    parser.add_argument("--font-policy", choices=["warn", "error", "ignore"], default="warn")
    parser.add_argument("--fail-on-warnings", action="store_true")
    parser.add_argument(
        "--font-dir",
        action="append",
        type=Path,
        default=[],
        help="Extra font folder for measurement and rendering (repeatable)",
    )
    args = parser.parse_args(argv)
    if args.font_dir:
        from power_pptx.text.fonts import register_font_dir

        for directory in args.font_dir:
            if not directory.is_dir():
                parser.error(f"--font-dir {directory} is not a directory")
            register_font_dir(directory)
    if len(args.inputs) > 1 and (args.reference_html or args.reference_dir):
        parser.error("Explicit references apply to a single input")
    names = [p.stem for p in args.inputs]
    if len(set(names)) != len(names):
        parser.error("Batch inputs must have distinct basenames")
    results = []
    for path in args.inputs:
        target = args.out_dir / path.stem if len(args.inputs) > 1 else args.out_dir
        try:
            with tempfile.TemporaryDirectory(prefix="pptx-review-source-") as tmp:
                reference = args.reference_dir
                source = path
                suffix = path.suffix.lower()
                if suffix in {".html", ".htm"}:
                    from power_pptx.compose import from_html

                    capture_reference = None
                    if reference is None and args.reference_html is None:
                        reference = Path(tmp) / "reference"
                        capture_reference = reference
                    source = from_html(
                        path,
                        mode=args.mode,
                        browser_path=args.browser_path,
                        selector=args.selector,
                        wait_for_function=args.ready,
                        reference_dir=capture_reference,
                    )
                elif suffix in {".json", ".yaml", ".yml"}:
                    from power_pptx.compose import from_spec, from_yaml

                    source = (
                        from_spec(json.loads(path.read_text(encoding="utf-8")))
                        if suffix == ".json"
                        else from_yaml(path)
                    )
                elif suffix != ".pptx":
                    raise ValueError("Input must be PPTX, HTML, JSON, or YAML")
                report = review_presentation(
                    source,
                    out_dir=target,
                    reference_dir=reference,
                    reference_html=args.reference_html,
                    browser_path=args.browser_path,
                    wait_for_function=args.ready,
                    selector=args.selector,
                    dpi=args.dpi,
                    soffice_bin=args.soffice_bin,
                    max_mean_error=args.max_error,
                    font_policy=args.font_policy,
                    fail_on_warnings=args.fail_on_warnings,
                )
                results.append(
                    {"input": str(path), "passed": not report.has_errors, "directory": str(target)}
                )
                print(
                    f"{path.name}: {'PASS' if not report.has_errors else 'FAIL'} — "
                    f"{target / 'index.html'}",
                    flush=True,
                )
        except Exception as exc:
            failure = {"input": str(path), "passed": False, "error": str(exc)}
            results.append(failure)
            target.mkdir(parents=True, exist_ok=True)
            (target / "manifest.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")
            (target / "index.html").write_text(
                '<!doctype html><meta charset="utf-8"><title>Review failed</title>'
                f"<h1>{escape(path.name)}</h1><p>{escape(str(exc))}</p>"
                '<a href="manifest.json">Failure details</a>',
                encoding="utf-8",
            )
            print(f"{path.name}: FAIL — {exc}", file=sys.stderr, flush=True)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if len(args.inputs) > 1:
        (args.out_dir / "batch.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        cards = "".join(
            f'<li><a href="{escape(path.stem)}/index.html">{escape(path.name)}</a>: '
            f"{'PASS' if result['passed'] else 'FAIL'}</li>"
            for path, result in zip(args.inputs, results)
        )
        (args.out_dir / "index.html").write_text(
            '<!doctype html><meta charset="utf-8"><title>Deck reviews</title>'
            f'<h1>Deck reviews</h1><ul>{cards}</ul><a href="batch.json">Batch results</a>',
            encoding="utf-8",
        )
    return 1 if any(not record["passed"] for record in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
