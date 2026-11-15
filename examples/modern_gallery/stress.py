"""Run the existing broad feature suite, optionally rendering EVERY slide.

These are feature probes, not presentation design references. Use build.py
for the curated modern gallery. Run from a source checkout.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from build import ROOT, contact_sheet

sys.path.insert(0, str(ROOT / "examples" / "stress_test"))

import _harness as harness  # noqa: E402

from power_pptx import Presentation  # noqa: E402
from power_pptx.render import render_slides  # noqa: E402

SHEET_SIZE = 8  # slides per contact sheet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--deck", action="append", help="Optional numeric prefix, e.g. 04")
    args = parser.parse_args()
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    harness.OUT = out
    manifest = out / "manifest.json"
    records = json.loads(manifest.read_text()) if args.deck and manifest.exists() else []
    failures = []
    if not harness._SCHEMA:
        raise SystemExit("The repository's ISO-29500 schema validator is required")
    names = [name for name in harness.discover() if _selected(name, args.deck)]
    for name in names:
        result = harness.check_deck(name)
        record = asdict(result)
        if args.render and result.build_ok:
            _render_every_slide(name, out, result.n_slides, record)
        if not result.clean or record.get("render_error"):
            failures.append(name)
        records = [previous for previous in records if previous["name"] != name]
        records.append(record)
        records.sort(key=lambda item: item["name"])
        manifest.write_text(json.dumps(records, indent=2), encoding="utf-8")
        print(
            f"{name}: {result.n_slides} slides; clean={name not in failures}; "
            f"rendered={record.get('rendered_slides', 0)}",
            flush=True,
        )
    if not names:
        raise SystemExit("No decks matched")
    if failures:
        raise SystemExit("Inspect failures in manifest.json: " + ", ".join(failures))


def _selected(name, prefixes):
    """Every deck when no ``--deck`` prefixes were given, else those matching one."""
    return not prefixes or any(name.startswith(prefix) for prefix in prefixes)


def _render_every_slide(name, out, n_slides, record):
    """Render the saved deck and its contact sheets, noting the outcome in *record*."""
    try:
        prs = Presentation(out / f"{name}.pptx")
        paths = render_slides(
            prs,
            out_dir=out / name,
            name_template="slide-{:02d}.png",
            strategy="pdf",
            dpi=96,
        )
        if len(paths) != n_slides:
            raise RuntimeError("Not every slide rendered")
        record["rendered_slides"] = len(paths)
        for start in range(0, len(paths), SHEET_SIZE):
            contact_sheet(
                paths[start : start + SHEET_SIZE],
                out / f"{name}-contact-{start // SHEET_SIZE + 1}.png",
                f"{name} / slides {start + 1}–{min(start + SHEET_SIZE, len(paths))}",
                start_index=start,
            )
    except Exception as exc:
        record["render_error"] = str(exc)


if __name__ == "__main__":
    main()
