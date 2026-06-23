# CLAUDE.md

Guidance for AI assistants (Claude Code and compatible harnesses) working in
this repository.

## What this project is

**power-pptx** is the actively-maintained fork of
[`python-pptx`](https://github.com/scanny/python-pptx) by Steve Canny, picking
up where upstream's 1.0.2 release left off. It is a pure-Python library for
creating, reading, and updating PowerPoint 2007+ (`.pptx`) files without
needing Microsoft PowerPoint installed.

- Distributed on PyPI as **`power-pptx`** but imported as **`import power_pptx`**
  (the 2.0 release renamed the top-level package from `pptx` to `power_pptx` so
  it can be installed side-by-side with upstream `python-pptx`). When migrating
  code, replace `pptx` with `power_pptx` in imports.
- Current version is defined in `src/power_pptx/__init__.py` (`__version__`).
- Python 3.9–3.13 supported. Runtime deps: `Pillow`, `XlsxWriter`, `lxml`,
  `typing_extensions`.

### Why the fork exists: space-aware authoring

The headline feature is making programmatically-generated decks **physically
correct** — text that doesn't overflow its box, shapes that don't slide off the
edges. Three layered tools catch nearly all real-world layout issues:

1. `TextFrame.fit_text(...)` — measures with Pillow font metrics and bakes a
   fitting size into the XML *before* save.
2. `text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE` — lets PowerPoint
   shrink at render time as a fallback.
3. `slide.lint()` / `slide.tidy()` — catches and auto-fixes what slipped
   through (e.g. nudges off-slide shapes back inside).

## ⭐ Using the library: read the bundled skill first

This repo ships its own **Claude skill** which is the canonical, up-to-date
guide for *using* the library's public API. When a task involves generating,
mutating, theming, linting, or rendering decks, consult it before writing code:

- `src/power_pptx/skill/SKILL.md` — cheat sheet, common operations,
  anti-patterns, and pitfalls.
- `src/power_pptx/skill/references/*.md` — deep dives per topic
  (`space-aware-authoring.md`, `geometry-and-arrows.md`, `charts.md`,
  `design.md`, `theme.md`, `animations.md`, `transitions.md`, `effects.md`,
  `tables.md`, `compose.md`, `render.md`, `lint.md`, `smart-art.md`,
  `three-d.md`, `end-to-end-deck.md`, `basics.md`, `picture-effects.md`).

A mirrored copy lives under `.claude/skills/power-pptx/` so the skill is active
in this repo's Claude Code sessions. **These two copies must be kept in sync** —
the one under `src/` is what gets packaged and shipped to downstream installs
(`python -m power_pptx.skill install` copies it into `~/.claude/skills/`).

Note: the SKILL.md "Where to look in the project" section still references the
old `src/pptx/...` paths; the actual source lives under `src/power_pptx/...`.

## Repository layout

```
src/power_pptx/        # the library (importable package)
  __init__.py          # public exports + __version__ + content-type → Part map
  api.py               # Presentation() factory entry point
  presentation.py      # Presentation object
  slide.py             # Slide, Slides, shape-collection helpers, lint()/tidy()
  shapes/              # autoshape, picture, connector, freeform, group, table frame, placeholder, shapetree
  text/                # text.py, layout.py (TextFitter / fit_text), fonts.py
  chart/               # chart model, plots, series, palettes, quick_layouts, xlsx writer
  dml/                 # DrawingML: fill, line, color, effect, picture filters, 3-D
  oxml/                # lxml-backed OOXML element classes (the XML layer)
  opc/                 # Open Packaging Conventions (zip/part/relationship plumbing)
  parts/               # package parts (slide, chart, image, media, diagram, ...)
  enum/                # MSO_* / PP_* enumerations
  design/              # post-fork design system: tokens, style, layout (Grid/Stack), recipes, components, figures
  compose/             # from_spec (dict/JSON → deck), import_slide, apply_template
  diagrams.py          # native-shape diagram recipes (pipeline, hub_and_spoke, cycle, ...)
  animation.py         # Entrance/Exit/Emphasis/MotionPath, SlideAnimations
  theme.py             # theme reader/writer (palette + fonts)
  inherit.py           # color/style inheritance resolution
  lint.py              # SlideLintReport, TextOverflow, OffSlide, ShapeCollision, LintSeverity
  render.py            # slide-thumbnail renderer (needs soffice/LibreOffice)
  audit.py             # one-call whole-deck audit() → AuditReport.markdown()
  geometry.py          # BBox value object (splattable into add_*)
  smart_art.py, _svg.py, media.py, table.py, util.py, formats.py, ...
  skill/               # the shipped Claude skill (SKILL.md + references/)
  templates/           # default.pptx and bundled theme/notes XML

tests/                 # pytest unit tests, mirroring src module layout; plus schema/ and integration/
features/              # Gherkin acceptance tests (run via behave)
examples/              # real_world/, showcase/, starter_pack/, playground/, stress_test/
spec/                  # ISO/IEC 29500 OOXML spec material + XSD schemas
docs/                  # Sphinx documentation (user/, dev/, api/)
typings/               # type stubs (used by pyright strict mode)
lab/                   # experimental, undisciplined code (excluded from lint)
```

## Development workflows

Standard Python tooling — no exotic build steps.

```bash
# setup (editable install + dev/test deps)
pip install -e .
pip install -r requirements-dev.txt
pip install -r requirements-test.txt
```

### Tests — three layers

```bash
pytest --cov=power_pptx tests        # unit tests, organized by source module
pytest tests/integration -v          # round-trip harness (save → open → save byte-clean)
pytest tests/schema -v               # validate generated decks against ISO 29500 XSDs
behave --stop                        # Gherkin acceptance tests under features/
```

- **Round-trip safety is a release blocker** — `tests/integration` must stay
  green on `master`.
- **Schema validation** is the gate for the "reopens fine but PowerPoint reports
  the file as broken / offers to repair it" class of bug. Add a schema test
  whenever you emit new XML.
- pytest discovers test classes named `Test`/`Describe` and functions prefixed
  `test_`/`it_`/`they_`/`but_`/`and_` (see `[tool.pytest.ini_options]` in
  `pyproject.toml`). `filterwarnings = ["error"]` — warnings fail the suite.

### Lint, format, type-check

```bash
ruff check src tests                 # lint (line-length 100; rules in pyproject.toml)
ruff format src tests                # format
pyright                              # strict type-checking on src/power_pptx + tests
```

`docs/`, `lab/`, `spec/`, and `ref/` are excluded from ruff. `lab/` is
deliberately undisciplined experimental code.

### Building / docs

```bash
python -m build                      # sdist + wheel (or: make build)
make docs                            # Sphinx HTML into docs/.build/html
```

## CI gates (`.github/workflows/ci.yml`)

A PR must keep all of these green:

1. **build** — `pytest` (with coverage) + `behave` across Python 3.9–3.13.
2. **examples-lint** — `pyflakes examples/` (no unused imports / undefined names).
3. **examples-build** — `python examples/real_world/build_all.py` smoke-builds
   all ten real-world decks end-to-end (proves the public surface didn't regress).
4. **schema-validation** — `pytest tests/schema` against bundled OOXML XSDs.

Other workflows: `publish.yml` (PyPI), `release-on-version-bump.yml`,
`qodana_code_quality.yml`.

## Conventions

- **Line length 100** (ruff + black config).
- **`known-first-party = ["power_pptx"]`** for isort import ordering.
- **No raw EMU integers in API usage** — use `BBox.from_inches(...)`,
  `Inches(...)`, `Pt(...)`. Float arithmetic on lengths is coerced at the
  setter, so expressions like `(Inches(N) - gutter) / 2` are fine.
- **Hex strings / tuples / `RGBColor` all work** anywhere a colour is accepted;
  prefer hex-string + short-name kwargs over importing enum constants.
- **Commit message prefixes** (imperative summary, body wrapped at 72 chars):
  `fix:`, `feat:`, `rfctr:`, `docs:`, `build:`/`dev:`, `test:`. Reference issues
  with `refs #123` / `fixes #123`.
- **PRs should be small** — one public-API surface per PR, with: code, unit
  tests, a round-trip test if new XML is emitted, a `HISTORY.rst` entry under
  the unreleased section, and doc updates if user-visible.

## When making changes

- Public API additions: add unit tests mirroring the source module layout, a
  round-trip test if XML changes, and a schema test if new XML is emitted.
- Update `HISTORY.rst` (unreleased section) for any user-visible change.
- If you change the library's public usage surface, update **both** the skill
  copy under `src/power_pptx/skill/` and the mirror under `.claude/skills/`.
- The version is the `__version__` string in `src/power_pptx/__init__.py`
  (setuptools reads it dynamically); a version bump can trigger the release
  workflow.

## Useful references in-tree

- `README.rst` — overview, install, skill-install instructions.
- `CONTRIBUTING.md` — dev environment, test layout, PR expectations, commit style.
- `ROADMAP.md` — planned API surface and explicit "out of scope" items.
- `HISTORY.rst` — changelog.
- `IMPROVEMENT_PLAN.md` / `IMPROVEMENT_PLAN_v2.md` — internal planning notes.
