# Project governance

`python-pptx-next` is an actively-maintained fork of `python-pptx`. This
document describes how decisions get made and how new contributors can
gain commit rights.

## Roles

### Maintainer

The current maintainer is **Daniel Halwell** (@codehalwell). The
maintainer is responsible for:

- Reviewing and merging pull requests.
- Tagging and publishing releases on PyPI.
- Resolving disputes about scope and direction.
- Approving changes to this `GOVERNANCE.md` file and to `ROADMAP.md`.

### Committer

A committer has write access to the repository (merge rights) but does
not single-handedly set roadmap direction. Committers are nominated by
the maintainer based on a sustained track record of high-quality PRs
and reviews. There is currently no formal cap on the number of
committers.

### Contributor

Anyone who opens an issue, submits a pull request, reviews someone
else's pull request, or improves the documentation. We aim to make the
contribution path low-friction; see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Decision-making

Day-to-day decisions (bug fixes, internal refactors, additive feature
work that fits the published roadmap) are made by lazy consensus on the
relevant pull request: a PR with at least one approving review and no
sustained objection from the maintainer or another committer can be
merged.

Decisions that change the **public API**, **roadmap direction**, or
**project governance** require an explicit `+1` from the maintainer.

When consensus cannot be reached, the maintainer makes the call. The
maintainer commits to writing down the rationale on the relevant issue
or PR so that the reasoning survives the decision.

## Roadmap

The published roadmap lives in [`ROADMAP.md`](ROADMAP.md). New phases
are added (and existing phases revised) by PR; the maintainer's `+1` is
required before a phase is considered committed.

Concrete features within an in-flight phase do not require a roadmap
PR; an issue with the `phase-N` label is enough to record intent.

## Releases

`python-pptx-next` follows semantic versioning as described in the
roadmap's [Versioning](ROADMAP.md#versioning) section:

- `1.x.y` — additive changes only; no removals.
- `2.0.0` — breaking changes batched together; no new features.

Pre-release builds use the `.devN` / `.aN` / `.bN` suffixes and publish
to PyPI under the same distribution name (`python-pptx-next`).

## Code of conduct

See [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). The maintainer enforces
the code of conduct and may take any of the actions described there
(including temporary or permanent bans) when warranted.

## Changing this document

`GOVERNANCE.md` itself is updated by PR. The maintainer's `+1` is
required.
