"""Tiny shared helpers for the stress-test decks.

Importing this module also makes the suite runnable straight from a fresh
source checkout (no install): it puts the repo's ``src/`` directory on
``sys.path`` *before* importing ``power_pptx``. Every deck script imports
``_util`` first, so this covers the standalone form
(``python examples/stress_test/01_effects_torture.py``) too. A checkout's local
source therefore takes precedence over any installed ``power-pptx`` — intended,
since the suite tests the tree it ships with.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "_out"
_SRC = HERE.parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from power_pptx import Presentation  # noqa: E402
from power_pptx.util import Inches  # noqa: E402

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


def deck() -> Presentation:
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    return prs


def blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def save(prs, filename: str) -> Path:
    """Save *prs* into the suite's ``_out/`` dir (created on demand).

    Used by each script's ``__main__`` so a standalone run writes under
    ``examples/stress_test/_out/`` regardless of the caller's working directory.
    """
    OUT.mkdir(exist_ok=True)
    path = OUT / filename
    prs.save(path)
    return path
