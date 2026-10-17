# Contributing

Thank you for considering a contribution to `power-pptx`.

This document covers the basics: how to propose a change, what your PR
needs to look like, and how the test suite is laid out.

## Where to start

- Browse the [GitHub issues](https://github.com/codehalwell/power-pptx/issues),
  especially anything labelled `good-first-issue`.
- Read the [`ROADMAP.md`](ROADMAP.md). Each phase lists concrete
  user-visible API surface that's planned; if you'd like to take on
  one of those items, please comment on the corresponding tracking
  issue first so we can avoid duplicate work.
- New ideas welcome — open a "feature proposal" issue before writing
  the patch so the design can be sanity-checked against the roadmap.

## Reporting bugs

Please use the bug-report issue template. The most useful bug reports
include:

- A small, self-contained snippet that reproduces the issue.
- The output you got and the output you expected.
- The Python version, `power-pptx` version, and platform.

If the bug touches an existing PowerPoint file, please attach a
minimal redacted `.pptx` that still triggers the issue.

## Development environment

This project uses standard Python tooling — no exotic build steps.

```bash
# clone and create a virtualenv
git clone https://github.com/codehalwell/power-pptx.git
cd power-pptx
python -m venv .venv && source .venv/bin/activate

# install in editable mode plus dev dependencies
pip install -e .
pip install -r requirements-dev.txt
pip install -r requirements-test.txt
```

## Tests

The test suite has three layers:

1. **Unit tests** under `tests/`, organized by source module
   (`tests/dml/test_color.py` covers `power_pptx/dml/color.py`, etc.).
2. **Integration tests** under `tests/integration/` — including the
   round-trip diff harness used by every later roadmap phase to assert
   that `save → open → save` is byte-clean.
3. **Acceptance tests** under `features/`, written in Gherkin and run
   via `behave`.

Running everything:

```bash
pytest --cov=power_pptx tests
behave --stop
```

Running only the round-trip harness while iterating:

```bash
pytest tests/integration -v
```

Type-checking:

```bash
pip install -r requirements-quality.txt
pyright --project pyright-ci.json  # CI scope: audit, compose, rendering and embedding
pyright
```

The repository-wide strict configuration still has inherited typing debt.
CI starts with basic checking of the maintained public entry points in
``pyright-ci.json``; expand that scope as modules are brought into shape.
Ruff correctness rules run over all source and tests, with the complete
configured rule set also enforced on the authoring/validation modules
listed in ``.github/workflows/ci.yml``. Tool versions are pinned in
``requirements-quality.txt``.

Rendering integration tests under ``tests/integration/test_render_libreoffice.py``
use real LibreOffice and Poppler. They skip when those tools are absent;
the dedicated CI job installs both and runs these tests. Release tagging
waits for successful default-branch CI on the exact commit, and publishing
checks that same requirement plus the version tag's target. Manual runs
follow the same checks.

HTML/SVG integration tests use real Chromium and CairoSVG. Install
``pip install -e '.[embedding]'`` and ``python -m playwright install chromium``
or set ``POWER_PPTX_CHROMIUM`` to an existing Chromium binary. The
``html-embedding`` CI job installs the browser and runs the integration tests
and ``examples/html_embedding/build.py``. Browser tests skip locally when the
optional dependencies/browser are absent.

The ``modern-gallery`` job installs the optional embedding/plotting backends,
LibreOffice/Poppler, and DejaVu fonts, then builds and renders all eight decks
in ``examples/modern_gallery/``. Its artifact contains every preview and a
validation manifest for visual review. Run that example's ``build.py --render``
locally to reproduce it, or ``stress.py --render --out-dir /tmp/pptx-stress``
to exercise all pages of the 14 broad feature probes. Read the example README
for prerequisites and the distinction between structural and visual checks.

Formatting and lint:

```bash
ruff check src tests
ruff format src tests
```

## Preparing a release

Merging a feature PR does not itself publish a release. The release workflow
reads `__version__` from `src/power_pptx/__init__.py`; if its `vX.Y.Z` tag
already exists, the workflow succeeds without creating or publishing anything.
Rerunning it with the same version has the same result.

Prepare a release PR against `master`:

1. Set `__version__` to a new version and sync `SITE.version` in
   `site/src/lib/site.ts`.
2. Move the pending `HISTORY.rst` entries into a dated `X.Y.Z (YYYY-MM-DD)`
   section, leaving `Unreleased` ready for future changes. The workflow extracts
   its release notes from that exact version heading.
3. Build the sdist and wheel with `python -m build` and check them with
   `python -m twine check dist/*`. Confirm the distribution metadata uses the
   new version and the matching tag does not already exist.
4. Merge after PR checks pass. The merge starts default-branch CI; the release
   workflow waits for that exact commit's CI before creating its tag/release.
   The resulting publish workflow then builds and uploads that tagged code.

Check the release job's tag decision and the publish job's build/upload steps,
as a successful no-op workflow does not mean a new package was published.

## Pull-request expectations

Per `ROADMAP.md`, PRs should be small. Each public-API surface should
ship as its own PR with:

- **Code** for the change itself.
- **Unit tests** that cover the new behavior.
- **A round-trip test** under `tests/integration/test_round_trip.py`
  if the change emits or reads new XML.
- **A `HISTORY.rst` entry** under the unreleased section.
- **Doc updates** if the change is user-visible.

Round-trip safety is a release blocker: the round-trip harness must
stay green on `master`.

## Commit messages

Follow the existing style. The first line is a short imperative
summary prefixed with one of:

- `fix:` — bug fix.
- `feat:` — new public API.
- `rfctr:` — internal refactor with no behavior change.
- `docs:` — documentation-only change.
- `build:` / `dev:` — build system, dev tooling.
- `test:` — test-only change.

Wrap the body at 72 characters. If the change relates to an issue,
reference it (`refs #123` / `fixes #123`).

## What we say no to

These are listed in `ROADMAP.md` under "Out of scope" and won't be
accepted without a strong new argument:

- Full SmartArt creation.
- A separate pure-Python distribution.
- A pixel-accurate rendering engine.
- Live PowerPoint integration (COM, AppleScript, Office.js).
- `.ppt` (legacy binary format) support.

We also tend to push back on:

- Features that require a non-trivial new dependency.
- Changes that don't round-trip cleanly through PowerPoint.
- Read-time mutation of the underlying XML.

## Code of conduct

Participation in this project is governed by
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). The maintainer enforces
the code of conduct.
