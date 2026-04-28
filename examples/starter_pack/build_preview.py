"""Render one preview deck per starter-pack token set.

Run::

    python examples/starter_pack/build_preview.py

Outputs ``examples/starter_pack/_out/<set>.pptx`` for ``modern``,
``classic``, and ``editorial``.  Each deck is the same content rendered
through :mod:`pptx.design.recipes` so you can compare how the tokens
land.
"""

from __future__ import annotations

import os
import sys

from pptx import Presentation
from pptx.design.recipes import (
    bullet_slide,
    kpi_slide,
    quote_slide,
    title_slide,
)

# Support both invocation styles documented in README.md:
#   python examples/starter_pack/build_preview.py        (no __package__)
#   python -m examples.starter_pack.build_preview        (relative import)
if __package__:
    from . import classic, editorial, modern
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import classic  # type: ignore[import-not-found,no-redef]
    import editorial  # type: ignore[import-not-found,no-redef]
    import modern  # type: ignore[import-not-found,no-redef]


SETS = {
    "modern":    modern.TOKENS,
    "classic":   classic.TOKENS,
    "editorial": editorial.TOKENS,
}


def build_one(name: str, tokens) -> str:
    prs = Presentation()
    title_slide(
        prs,
        title="Q4 Review",
        subtitle="April 2026 — internal",
        tokens=tokens,
    )
    bullet_slide(
        prs,
        title="Highlights",
        bullets=[
            "Two flagship customers shipped this week.",
            "NPS improved 8 points QoQ.",
            "Pipeline coverage at 3.4x the quarter target.",
        ],
        tokens=tokens,
    )
    kpi_slide(
        prs,
        title="Run-rate metrics",
        kpis=[
            {"label": "ARR", "value": "$182M", "delta": +0.27},
            {"label": "NDR", "value": "131%",  "delta": +0.03},
            {"label": "Gross margin", "value": "78%", "delta": -0.02},
        ],
        tokens=tokens,
    )
    quote_slide(
        prs,
        quote="It just works — that's the whole pitch.",
        attribution="Design partner #4",
        tokens=tokens,
    )

    out_dir = os.path.join(os.path.dirname(__file__), "_out")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{name}.pptx")
    prs.save(out_path)
    return out_path


def main() -> None:
    for name, tokens in SETS.items():
        path = build_one(name, tokens)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
