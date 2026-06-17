# Stress-test suite

A deliberately aggressive set of deck generators built to **surface library
bugs** by exercising the whole post-fork API surface — effects, gradients, all
four gradient kinds, line ends/caps/joins, charts (every type + palettes + quick
layouts + per-series gradient/pattern fills), tables (cell borders, merges,
diagonals), native-shape diagrams, 3D (every bevel + material), themes,
transitions (every kind incl. p14), `from_spec`, the design system (tokens,
Grid/Stack, recipes), picture effects + SVG, multilingual/emoji space-aware
text, and cross-deck `import_slide` / `apply_template`.

## Running

```bash
python examples/stress_test/_harness.py          # build + check every deck
python examples/stress_test/_harness.py 02 07     # only matching scripts
python examples/stress_test/_harness.py --render   # also render via LibreOffice
```

Each script also runs standalone (`python examples/stress_test/07_*.py`) and
writes its `.pptx` into `_out/`.

## What the harness checks

Every deck exposes `build() -> Presentation` and is run through five
independent checks (failures are caught, never re-raised, so one run surfaces as
many issues as possible):

1. **build** — `build()` runs without raising.
2. **lint** — `slide.lint()` / `auto_fix()` run cleanly; residual
   error-severity issues are reported.
3. **round-trip** — save → reopen → save leaves every XML part byte-identical
   after c14n canonicalisation (the project's release gate, mirrors
   `tests/integration/round_trip.py`).
4. **reopen** — the saved `.pptx` re-opens in power-pptx.
5. **schema** — every part validates against the bundled ISO-29500 XSDs via
   `tests/schema/oxml_schema_validator`. This is the check that catches the
   "opens in python-pptx / LibreOffice but Microsoft PowerPoint repairs it"
   bug class.

## Findings

See [`BUGS.md`](./BUGS.md). Round-trip and reopen are clean across all decks;
the ISO-29500 schema validator surfaced four distinct bug classes (transition
`p14:dur`, radar `c:smooth`, `softMetal` enum casing, and `washout` recolor's
missing `thresh`).
