"""Render a .pptx to one PNG per slide via soffice + pdftoppm.

Standalone helper so individual scripts can call ``render(out_path)``
without depending on ``build_all.py``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

SOFFICE_TIMEOUT = 180
PDFTOPPM_TIMEOUT = 60

_SLIDE_NUM_RE = re.compile(r"slide-(\d+)\.png$")


def _slide_key(path: Path) -> int:
    """Sort key that returns the numeric slide index from ``slide-<n>.png``.

    Plain ``sorted(...)`` would lex-sort, putting ``slide-10`` before
    ``slide-2``; this keeps callers (contact sheets, QA loops) iterating
    in deck order regardless of slide count.
    """
    m = _SLIDE_NUM_RE.search(path.name)
    return int(m.group(1)) if m else -1


def render(deck: Path, thumbs_dir: Path | None = None, dpi: int = 144) -> list[Path]:
    """Render ``deck`` to slide-1.png, slide-2.png, … in ``thumbs_dir``.

    Returns the list of PNG paths in slide order, or [] if rendering
    can't run (missing binaries, soffice failure, or a timeout).
    """
    deck = Path(deck)
    if thumbs_dir is None:
        thumbs_dir = deck.parent / "thumbs" / deck.stem
    thumbs_dir = Path(thumbs_dir)

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    pdftoppm = shutil.which("pdftoppm")
    if not soffice or not pdftoppm:
        print(f"  (rendering {deck.name} skipped — need soffice + pdftoppm)")
        return []

    thumbs_dir.mkdir(parents=True, exist_ok=True)
    for stale in thumbs_dir.glob("slide-*.png"):
        stale.unlink()

    try:
        res = subprocess.run(
            [soffice, "--headless", "--norestore", "--nologo",
             "--nofirststartwizard", "--convert-to", "pdf",
             "--outdir", str(thumbs_dir), str(deck)],
            capture_output=True, timeout=SOFFICE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        print(f"  (pdf conversion timed out after {SOFFICE_TIMEOUT}s — "
              f"check for a stale ~/.config/libreoffice profile lock)")
        return []

    pdf = thumbs_dir / (deck.stem + ".pdf")
    if res.returncode != 0 or not pdf.exists():
        excerpt = (res.stderr or res.stdout or b"").decode("utf-8", "replace")[:300]
        print(f"  (pdf conversion failed: {excerpt})")
        return []

    try:
        res = subprocess.run(
            [pdftoppm, "-r", str(dpi), "-png", str(pdf), str(thumbs_dir / "slide")],
            capture_output=True, timeout=PDFTOPPM_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        pdf.unlink(missing_ok=True)
        print(f"  (pdftoppm timed out after {PDFTOPPM_TIMEOUT}s)")
        return []
    finally:
        pdf.unlink(missing_ok=True)

    if res.returncode != 0:
        excerpt = (res.stderr or res.stdout or b"").decode("utf-8", "replace")[:300]
        print(f"  (pdftoppm failed: {excerpt})")
        return []

    return sorted(thumbs_dir.glob("slide-*.png"), key=_slide_key)
