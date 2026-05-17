"""Build every playground deck and render thumbnails into ``_out/``.

Usage::

    python examples/playground/build_all.py

Outputs:
    examples/playground/_out/<name>.pptx
    examples/playground/_out/thumbs/<name>/slide-<n>.png

Renders one PNG per slide via ``soffice --convert-to pdf`` followed by
``pdftoppm``. Requires LibreOffice with the Impress component and
``pdftoppm`` from ``poppler-utils``; both binaries should be on PATH.
If either is missing, deck generation still succeeds and thumbnail
rendering is skipped with a warning.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "_out"
THUMBS = OUT / "thumbs"

# Make `_brand`, `_common`, `_render` importable from the example scripts
# regardless of where build_all.py is invoked from.
sys.path.insert(0, str(HERE))

from _render import render  # noqa: E402

SCRIPTS = [
    "01_editorial_data_story",
    "02_research_findings",
    "03_product_launch",
    "04_sales_playbook",
    "05_from_spec_declarative",
]


def _load(name: str):
    path = HERE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load module {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    OUT.mkdir(exist_ok=True)
    # `_render.render()` creates its own per-deck thumbs directory, so
    # we don't pre-create the parent here.

    for name in SCRIPTS:
        print(f"→ building {name}.pptx")
        mod = _load(name)
        out_pptx = OUT / f"{name}.pptx"
        mod.build(out_pptx)
        rel = out_pptx.relative_to(HERE.parent.parent)
        print(f"  saved {rel}")
        thumbs = render(out_pptx, THUMBS / name)
        if thumbs:
            print(f"  rendered {len(thumbs)} slide thumbnail(s)")

    print("\nDone. Decks in:", OUT)


if __name__ == "__main__":
    main()
