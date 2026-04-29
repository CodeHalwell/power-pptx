"""Build every showcase deck and render thumbnails into ``_out/``.

Usage::

    python examples/showcase/build_all.py

Outputs:
    examples/showcase/_out/<name>.pptx
    examples/showcase/_out/thumbs/<name>/slide-<n>.png

The shipped ``Presentation.render_thumbnails`` shells out to
``soffice --convert-to png``, which only renders slide 1.  To get a
PNG per slide we go through PDF (``soffice --convert-to pdf``) and
then ``pdftoppm``.  Both binaries are typically available wherever
LibreOffice is installed (``apt install libreoffice-impress
poppler-utils``).
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "_out"
THUMBS = OUT / "thumbs"

# Ensure imports like `from _tokens import BRAND` work in each example
# regardless of where build_all is invoked from.
sys.path.insert(0, str(HERE))


SCRIPTS = [
    "01_design_system",
    "02_charts",
    "03_visual_effects",
    "04_animations",
    "05_space_aware",
    "06_tables",
]


def _load(name: str):
    path = HERE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"could not build an import spec for {path}; ensure the file exists "
            f"and is a valid Python module."
        )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SOFFICE_TIMEOUT = 120
PDFTOPPM_TIMEOUT = 60


def _fail(label: str, res: subprocess.CompletedProcess) -> int:
    """Print a one-line failure with a stderr/stdout excerpt."""
    err = (res.stderr or b"").decode("utf-8", "replace").strip()
    out = (res.stdout or b"").decode("utf-8", "replace").strip()
    excerpt = (err or out or "<no output>")[:300]
    print(f"  ({label} failed [exit {res.returncode}]: {excerpt})")
    return 0


def _render_thumbs(deck: Path, sub: Path) -> int:
    """Render one PNG per slide. Returns count rendered (0 on failure)."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    pdftoppm = shutil.which("pdftoppm")
    if not soffice or not pdftoppm:
        print("  (thumbnails skipped — needs soffice + pdftoppm on PATH)")
        return 0

    sub.mkdir(parents=True, exist_ok=True)
    # Stale renders from a prior build can outnumber the current deck's
    # slide count and corrupt the reported count. Clear them first.
    for stale in sub.glob("slide-*.png"):
        stale.unlink()

    # 1) deck.pptx → deck.pdf in `sub`
    try:
        res = subprocess.run(
            [soffice, "--headless", "--norestore", "--nologo",
             "--nofirststartwizard", "--convert-to", "pdf",
             "--outdir", str(sub), str(deck)],
            capture_output=True,
            timeout=SOFFICE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        print(f"  (soffice timed out after {SOFFICE_TIMEOUT}s — check for "
              f"a stale LibreOffice profile lock under ~/.config/libreoffice)")
        return 0

    pdf = sub / (deck.stem + ".pdf")
    if res.returncode != 0 or not pdf.exists():
        return _fail("pdf conversion", res)

    # 2) deck.pdf → slide-<n>.png at 150 dpi
    try:
        res = subprocess.run(
            [pdftoppm, "-r", "150", "-png", str(pdf), str(sub / "slide")],
            capture_output=True,
            timeout=PDFTOPPM_TIMEOUT,
        )
    finally:
        pdf.unlink(missing_ok=True)
    if res.returncode != 0:
        return _fail("pdftoppm", res)

    pngs = sorted(sub.glob("slide-*.png"))
    print(f"  rendered {len(pngs)} slide thumbnail(s)")
    return len(pngs)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    THUMBS.mkdir(exist_ok=True)

    for name in SCRIPTS:
        mod = _load(name)
        out_pptx = OUT / f"{name}.pptx"
        print(f"→ building {name}.pptx")
        mod.build(out_pptx)
        print(f"  saved {out_pptx.relative_to(HERE.parent.parent)}")
        _render_thumbs(out_pptx, THUMBS / name)

    print("\nDone. Decks in:", OUT)


if __name__ == "__main__":
    main()
