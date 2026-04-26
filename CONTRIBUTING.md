# Contributing

Thank you for considering a contribution to `python-pptx-next`.

This document covers the basics: how to propose a change, what your PR
needs to look like, and how the test suite is laid out.

## Where to start

- Browse the [GitHub issues](https://github.com/codehalwell/python-pptx/issues),
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
- The Python version, `python-pptx-next` version, and platform.

If the bug touches an existing PowerPoint file, please attach a
minimal redacted `.pptx` that still triggers the issue.

## Development environment

This project uses standard Python tooling — no exotic build steps.

```bash
# clone and create a virtualenv
git clone https://github.com/codehalwell/python-pptx.git
cd python-pptx
python -m venv .venv && source .venv/bin/activate

# install in editable mode plus dev dependencies
pip install -e .
pip install -r requirements-dev.txt
pip install -r requirements-test.txt
```

## Tests

The test suite has three layers:

1. **Unit tests** under `tests/`, organized by source module
   (`tests/dml/test_color.py` covers `pptx/dml/color.py`, etc.).
2. **Integration tests** under `tests/integration/` — including the
   round-trip diff harness used by every later roadmap phase to assert
   that `save → open → save` is byte-clean.
3. **Acceptance tests** under `features/`, written in Gherkin and run
   via `behave`.

Running everything:

```bash
pytest --cov=pptx tests
behave --stop
```

Running only the round-trip harness while iterating:

```bash
pytest tests/integration -v
```

Type-checking:

```bash
pyright
```

Formatting and lint:

```bash
ruff check src tests
ruff format src tests
```

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
