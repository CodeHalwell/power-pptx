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
    matched = 0
    if not harness._SCHEMA:
        raise SystemExit("The repository's ISO-29500 schema validator is required")
    for name in harness.discover():
        if args.deck and not any(name.startswith(prefix) for prefix in args.deck):
            continue
        matched += 1
        result = harness.check_deck(name)
        record = asdict(result)
        if args.render and result.build_ok:
            try:
                prs = Presentation(out / f"{name}.pptx")
                paths = render_slides(
                    prs,
                    out_dir=out / name,
                    name_template="slide-{:02d}.png",
                    strategy="pdf",
                    dpi=96,
                )
                if len(paths) != result.n_slides:
                    raise RuntimeError("Not every slide rendered")
                record["rendered_slides"] = len(paths)
                for start in range(0, len(paths), 8):
                    contact_sheet(
                        paths[start : start + 8],
                        out / f"{name}-contact-{start // 8 + 1}.png",
                        f"{name} / slides {start + 1}–{min(start + 8, len(paths))}",
                        start_index=start,
                    )
            except Exception as exc:
                record["render_error"] = str(exc)
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
    if not matched:
        raise SystemExit("No decks matched")
    if failures:
        raise SystemExit("Inspect failures in manifest.json: " + ", ".join(failures))


if __name__ == "__main__":
    main()
