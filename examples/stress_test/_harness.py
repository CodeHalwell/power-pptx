"""Bug-surfacing harness for the stress-test decks.

Each stress script exposes ``build() -> Presentation``. This harness runs every
deck through five independent checks, catching (never re-raising) failures so a
single run surfaces as many library bugs as possible:

1. **build**       — does ``build()`` run without raising?
2. **lint**        — ``slide.lint()`` / ``auto_fix()`` run cleanly and any
                     residual error-severity issues are reported (these may be
                     genuine layout bugs in the deck *or* false positives in the
                     linter — both are worth surfacing).
3. **round-trip**  — save → reopen → save leaves every XML part byte-identical
                     after c14n canonicalisation (the project's release gate).
4. **reopen**      — the saved ``.pptx`` re-opens cleanly in power-pptx.
5. **schema**      — every part validates against the bundled ISO-29500 XSDs
                     (``tests/schema/oxml_schema_validator``). This is the check
                     that catches the "opens in python-pptx / LibreOffice but
                     Microsoft PowerPoint reports the file as broken" bug class.

Optionally (``--render``) each deck's first slide is rendered to PNG via
LibreOffice to catch "opens in python-pptx but PowerPoint/LibreOffice rejects
it" issues.

Run::

    python examples/stress_test/_harness.py            # build + check all
    python examples/stress_test/_harness.py 01 04      # just those scripts
    python examples/stress_test/_harness.py --render    # also render thumbnails
"""

from __future__ import annotations

import importlib.util
import io
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from power_pptx import Presentation
from power_pptx.lint import LintSeverity

HERE = Path(__file__).parent
OUT = HERE / "_out"
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT))

# The ISO-29500 XSD validator ships with the test suite. It's the harness that
# catches the "opens fine but PowerPoint repairs it" bug class, so we fold it in.
try:
    from tests.schema.oxml_schema_validator import (  # type: ignore
        iter_schema_violations,
        schema_validation_available,
    )
    _SCHEMA = schema_validation_available()
except Exception:  # pragma: no cover - optional dependency / layout
    _SCHEMA = False

    def iter_schema_violations(_):  # type: ignore
        return iter(())


# --------------------------------------------------------------------------- #
# Round-trip diff harness (mirrors tests/integration/round_trip.py)
# --------------------------------------------------------------------------- #
def _parts(pptx_bytes: bytes) -> dict[str, bytes]:
    with ZipFile(io.BytesIO(pptx_bytes)) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def _canon(xml_bytes: bytes) -> bytes:
    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.fromstring(xml_bytes, parser)
    return etree.tostring(root, method="c14n2")


def _save_bytes(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def round_trip_diff(prs) -> dict[str, tuple]:
    first = _save_bytes(prs)
    reopened = Presentation(io.BytesIO(first))
    second = _save_bytes(reopened)
    parts1, parts2 = _parts(first), _parts(second)
    diff: dict[str, tuple] = {}
    for name in set(parts1) | set(parts2):
        p1, p2 = parts1.get(name), parts2.get(name)
        if p1 is None or p2 is None:
            diff[name] = (p1, p2)
            continue
        if name.endswith((".xml", ".rels")):
            try:
                if _canon(p1) != _canon(p2):
                    diff[name] = (p1, p2)
            except etree.XMLSyntaxError:
                if p1 != p2:
                    diff[name] = (p1, p2)
        elif p1 != p2:
            diff[name] = (p1, p2)
    return diff


# --------------------------------------------------------------------------- #
# Result accounting
# --------------------------------------------------------------------------- #
@dataclass
class DeckResult:
    name: str
    build_ok: bool = False
    n_slides: int = 0
    lint_errors: list[str] = field(default_factory=list)
    lint_crash: str | None = None
    roundtrip_parts: list[str] = field(default_factory=list)
    roundtrip_crash: str | None = None
    reopen_crash: str | None = None
    render_crash: str | None = None
    build_crash: str | None = None
    schema_violations: list[str] = field(default_factory=list)
    schema_crash: str | None = None

    @property
    def clean(self) -> bool:
        return (
            self.build_ok
            and not self.lint_errors
            and not self.lint_crash
            and not self.roundtrip_parts
            and not self.roundtrip_crash
            and not self.reopen_crash
            and not self.render_crash
            and not self.schema_violations
            and not self.schema_crash
        )


def _short_tb() -> str:
    return "".join(traceback.format_exc().strip().splitlines(keepends=True)[-4:])


def check_deck(name: str, render: bool = False) -> DeckResult:
    res = DeckResult(name=name)
    path = HERE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        prs = module.build()
        res.build_ok = True
        res.n_slides = len(prs.slides)
    except Exception:
        res.build_crash = _short_tb()
        return res

    # 2. lint
    try:
        for i, slide in enumerate(prs.slides):
            report = slide.lint()
            report.auto_fix()
            for issue in slide.lint().issues:
                if issue.severity is LintSeverity.ERROR:
                    res.lint_errors.append(f"slide {i + 1}: {issue}")
    except Exception:
        res.lint_crash = _short_tb()

    # 3. round-trip
    try:
        diff = round_trip_diff(prs)
        res.roundtrip_parts = sorted(diff)
    except Exception:
        res.roundtrip_crash = _short_tb()

    # save (always, so artifacts exist + reopen check is meaningful)
    OUT.mkdir(exist_ok=True)
    out_path = OUT / f"{name}.pptx"
    try:
        prs.save(out_path)
    except Exception:
        res.reopen_crash = "save failed:\n" + _short_tb()
        return res

    # 4. reopen
    try:
        Presentation(out_path)
    except Exception:
        res.reopen_crash = _short_tb()

    # 5. ISO-29500 schema validation (deduplicated, part :: message)
    if _SCHEMA:
        try:
            seen = set()
            for part, msg in iter_schema_violations(out_path):
                short = msg.strip().splitlines()[0][:160]
                key = (part.rsplit("/", 1)[-1], short)
                if key in seen:
                    continue
                seen.add(key)
                res.schema_violations.append(f"{key[0]} :: {short}")
        except Exception:
            res.schema_crash = _short_tb()

    # 6. optional render
    if render:
        import shutil
        import subprocess

        if shutil.which("soffice"):
            try:
                subprocess.run(
                    ["soffice", "--headless", "--convert-to", "pdf",
                     "--outdir", str(OUT), str(out_path)],
                    capture_output=True, timeout=120, check=True,
                )
            except Exception:
                res.render_crash = _short_tb()
    return res


def discover() -> list[str]:
    names = []
    for p in sorted(HERE.glob("[0-9][0-9]_*.py")):
        names.append(p.stem)
    return names


def main(argv: list[str]) -> int:
    render = "--render" in argv
    filters = [a for a in argv if not a.startswith("--")]
    names = discover()
    if filters:
        names = [n for n in names if any(n.startswith(f) or f in n for f in filters)]

    results = [check_deck(n, render=render) for n in names]

    print("\n" + "=" * 72)
    print("STRESS-TEST HARNESS REPORT")
    print("=" * 72)
    bugs = 0
    for r in results:
        status = "CLEAN" if r.clean else "ISSUES"
        print(f"\n[{status}] {r.name}  ({r.n_slides} slides)")
        if r.build_crash:
            bugs += 1
            print("  ✗ BUILD CRASHED:")
            print("    " + r.build_crash.replace("\n", "\n    "))
            continue
        if r.lint_crash:
            bugs += 1
            print("  ✗ LINT CRASHED:")
            print("    " + r.lint_crash.replace("\n", "\n    "))
        if r.lint_errors:
            print(f"  ⚠ {len(r.lint_errors)} lint error-issue(s):")
            for e in r.lint_errors[:8]:
                print(f"      - {e}")
            if len(r.lint_errors) > 8:
                print(f"      ... +{len(r.lint_errors) - 8} more")
        if r.roundtrip_crash:
            bugs += 1
            print("  ✗ ROUND-TRIP CRASHED:")
            print("    " + r.roundtrip_crash.replace("\n", "\n    "))
        if r.roundtrip_parts:
            bugs += 1
            print(f"  ✗ ROUND-TRIP CHANGED {len(r.roundtrip_parts)} part(s):")
            for p in r.roundtrip_parts:
                print(f"      - {p}")
        if r.reopen_crash:
            bugs += 1
            print("  ✗ REOPEN/SAVE CRASHED:")
            print("    " + r.reopen_crash.replace("\n", "\n    "))
        if r.schema_crash:
            bugs += 1
            print("  ✗ SCHEMA VALIDATION CRASHED:")
            print("    " + r.schema_crash.replace("\n", "\n    "))
        if r.schema_violations:
            bugs += 1
            print(f"  ✗ ISO-29500 SCHEMA: {len(r.schema_violations)} distinct violation(s):")
            for v in r.schema_violations[:8]:
                print(f"      - {v}")
            if len(r.schema_violations) > 8:
                print(f"      ... +{len(r.schema_violations) - 8} more")
        if r.render_crash:
            print("  ⚠ RENDER FAILED:")
            print("    " + r.render_crash.replace("\n", "\n    "))

    clean = sum(1 for r in results if r.clean)
    print("\n" + "=" * 72)
    print(f"{clean}/{len(results)} decks fully clean; "
          f"{bugs} hard bug signal(s) across the suite.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
