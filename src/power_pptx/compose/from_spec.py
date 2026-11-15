"""JSON / YAML-driven presentation authoring — the ``from_spec`` entry point.

This module exposes :func:`from_spec` (dict input) and :func:`from_yaml`
(YAML file input), both returning a fully-populated
:class:`~power_pptx.api.Presentation`.

The spec dispatches to the styled :mod:`power_pptx.design.recipes` library by
default, so layout names like ``"kpi"`` / ``"chart"`` / ``"timeline"``
produce token-driven recipe slides instead of bare placeholder text.
The original placeholder-based aliases (``"title"``, ``"bullets"``,
``"two_column"``, …) are still available — they're useful when the
spec is meant to populate an existing branded template.

Example::

    from power_pptx.compose import from_spec

    prs = from_spec({
        "tokens": {"preset": "modern_light"},
        "vars": {"company": "ACME"},
        "slides": [
            {
                "layout": "title",
                "title": "{{company}} Q4 Review",
                "subtitle": "April 2026",
                "transition": "morph",
            },
            {
                "layout": "kpi",   # routes to recipes.kpi_slide
                "title": "Run-rate metrics",
                "kpis": [
                    {"label": "ARR", "value": "$182M", "delta": 0.27},
                    {"label": "NDR", "value": "131%",  "delta": 0.03},
                ],
            },
            {
                "layout": "chart",
                "title": "Revenue by quarter",
                "chart_type": "line",
                "categories": ["Q1", "Q2", "Q3"],
                "series": [{"name": "ARR", "values": [82, 110, 132]}],
            },
        ],
        "lint": "raise",
    })

YAML usage::

    from power_pptx.compose import from_yaml
    prs = from_yaml("deck.yml", vars={"company": "ACME"})

Errors
------

A spec is usually written by a program, so every problem with its content
is reported as a :class:`SpecError` — a :class:`ValueError` whose message
starts with the location of the offending value (``slides[2].kpis[0]:
expected a mapping ...``).  Wrong value types, unknown keys, content a
layout cannot place, missing files and failures inside a recipe all
surface this way, chained from the original exception.

Untrusted specs
---------------

Pass ``safe=True`` when the spec comes from a model or a user.  Files the
spec names (``template``, a token ``yaml``, ``image``, ``figure``) must
then resolve inside *base_dir*, and HTML / Plotly figures are captured
with network access blocked.  Independently of ``safe``, a spec can never
choose the browser executable.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping, Optional

from power_pptx.enum.presentation import MSO_TRANSITION_TYPE
from power_pptx.exc import PythonPptxError

if TYPE_CHECKING:
    import inspect

    from power_pptx.presentation import Presentation


class SpecError(PythonPptxError, ValueError):
    """A deck spec that :func:`from_spec` cannot build.

    A :class:`ValueError`, so existing ``except ValueError`` handlers keep
    working.  The message starts with the location of the offending value
    in the spec — ``slides[2].kpis[0]: ...`` — and :attr:`path` carries
    that location on its own (an empty string when the problem is not tied
    to one key), which is convenient when feeding the error back to the
    program that wrote the spec.
    """

    def __init__(self, message: str, *, path: str = ""):
        super().__init__(message)
        self.path = path


def _spec_error(path: str, detail: str) -> SpecError:
    """Return a :class:`SpecError` for *detail* at spec location *path*."""
    return SpecError(f"{path}: {detail}" if path else detail, path=path)


@dataclass(frozen=True)
class _Context:
    """Per-call settings the dispatcher threads through to its helpers."""

    safe: bool = False
    base_dir: Optional[Path] = None

    def resolve_file(self, value: Any, where: str, *, hint: str = "") -> str:
        """Return the spec's path *value* as a path to an existing file.

        A relative path is resolved against :attr:`base_dir` when one was
        given.  In safe mode the path — after following symlinks — must lie
        inside the base directory (the current directory when none was
        given).  *where* names the spec key in the error.
        """
        try:
            raw = os.fspath(value)
        except TypeError:
            raise _spec_error(
                where, f"expected a file path; got {_describe(value)}{hint}"
            ) from None
        if not isinstance(raw, str) or not raw or "\x00" in raw:
            raise _spec_error(where, f"expected a file path; got {_describe(value)}{hint}")
        path = Path(raw)
        if self.base_dir is not None and not path.is_absolute():
            path = self.base_dir / path
        if self.safe:
            root = (self.base_dir if self.base_dir is not None else Path.cwd()).resolve()
            try:
                real = path.resolve()
            except (OSError, RuntimeError) as exc:
                raise _spec_error(where, f"cannot resolve path {raw!r}: {exc}") from exc
            if real != root and root not in real.parents:
                raise _spec_error(
                    where,
                    f"path {raw!r} is outside base_dir {str(root)!r}; in safe mode a "
                    "spec may only read files inside it",
                )
            path = real
        if not path.is_file():
            raise _spec_error(where, f"file not found: {raw!r}{hint}")
        return raw if path == Path(raw) else str(path)


# ---------------------------------------------------------------------------
# Built-in layout aliases — map friendly names to the PowerPoint blank
# template's named layouts (from SlideLayouts collection).
# ---------------------------------------------------------------------------

_LAYOUT_ALIASES: dict[str, str] = {
    "title": "Title Slide",
    "bullets": "Title and Content",
    "section": "Section Header",
    "two_column": "Two Content",
    # The bare ``comparison`` alias is intentionally absent here — that
    # name now exclusively routes to the ``comparison_slide`` recipe.
    # Use ``comparison_layout`` to opt in to the placeholder-based
    # layout from the underlying template.
    "comparison_layout": "Comparison",
    "title_only": "Title Only",
    "blank": "Blank",
    "caption": "Content with Caption",
    "picture": "Picture with Caption",
    "kpi_grid": "Title Only",  # rendered via shapes on top of Title Only
}

# Only content fields consumed by each legacy layout are accepted. Shared
# fields also apply to named layouts from custom templates.
_LEGACY_CONTENT_KEYS = {
    "title": {"subtitle"},
    "bullets": {"bullets"},
    "section": {"subtitle", "text"},
    "two_column": {"left", "right", "content_left", "content_right"},
    "comparison_layout": {
        "left",
        "right",
        "content_left",
        "content_right",
        "left_heading",
        "right_heading",
    },
    "kpi_grid": {"kpis"},
}
_COMMON_SLIDE_KEYS = {"layout", "title", "transition", "shapes", "interpolate"}

# Legacy layout → the placeholder ``idx`` each content key fills.  A key
# listed here whose placeholder the layout lacks is an error, never a
# silent drop.
_LEGACY_PLACEHOLDERS: dict[str, dict[str, int]] = {
    "title": {"subtitle": 1},
    "bullets": {"bullets": 1},
    "section": {"subtitle": 1, "text": 1},
    "two_column": {"left": 1, "content_left": 1, "right": 2, "content_right": 2},
    # The Comparison layout pairs a heading (idx 1 / 3) with a content
    # placeholder (idx 2 / 4) on each side.
    "comparison_layout": {
        "left_heading": 1,
        "left": 2,
        "content_left": 2,
        "right_heading": 3,
        "right": 4,
        "content_right": 4,
    },
}

# Content keys that may hold a bullet list as well as a plain string.
_LEGACY_LIST_KEYS = frozenset({"bullets", "left", "right", "content_left", "content_right"})

# Pairs of keys that name the same placeholder; giving both is ambiguous.
_LEGACY_SYNONYMS = (("subtitle", "text"), ("left", "content_left"), ("right", "content_right"))

# Lowercase transition name → MSO_TRANSITION_TYPE member name ("random_bar" →
# "RANDOM_BAR"). Derived from the enum so a new kind needs no edit here.
_TRANSITION_NAMES: dict[str, str] = {
    member.name.lower(): member.name for member in MSO_TRANSITION_TYPE
}


def from_spec(
    spec: dict[str, Any],
    *,
    vars: Optional[Mapping[str, Any]] = None,
    safe: bool = False,
    base_dir: "str | os.PathLike[str] | None" = None,
) -> Presentation:
    """Return a :class:`~power_pptx.api.Presentation` built from the plain-dict *spec*.

    *spec* keys:

    ``slides`` *(required)*
        A list of slide-spec dicts.  Each slide dict must have a
        ``layout`` key.  Recipe layouts (``title_recipe``, ``bullets_recipe``,
        ``kpi``, ``chart``, ``table``, ``code``, ``timeline``,
        ``comparison``, ``quote``, ``image_hero``, ``section_divider``)
        run the matching :mod:`power_pptx.design.recipes` function;
        legacy layouts (``title``, ``bullets``, ``two_column``, …)
        populate the standard placeholder layouts.

        Values are type-checked before anything is built: text fields
        (``title``, ``subtitle``, ``quote``, ``code``, …) must be strings,
        ``bullets`` a list of strings or ``{"text": ..., "level": ...}``
        mappings (nested levels need the placeholder ``bullets`` layout;
        the token-styled recipe renders a flat list), ``kpis`` /
        ``milestones`` / ``series`` lists of mappings, table ``rows``
        lists no longer than ``columns``, and so on.  A key the layout
        cannot place — a ``title`` on a ``blank`` slide, for instance —
        is an error rather than silently dropped content.

        A slide dict may also carry a ``shapes`` list of extra shapes
        drawn on top of whatever the layout produced.  Each entry needs
        ``left`` / ``top`` / ``width`` / ``height`` in inches, and may
        give a ``name``, ``text``, a ``shape`` (an ``MSO_SHAPE`` member
        name; a text box by default), and the ``lint_group`` /
        ``allow_overlap_with`` / ``layer`` / ``layer_above`` fields that
        declare an overlap as intentional at generation time.

        A recipe slide may carry its own ``tokens`` (the same forms as
        the spec-level key).  A ``preset`` or ``yaml`` there replaces
        the deck's tokens for that slide; inline sections and
        ``overrides`` are layered over them.

    ``tokens`` *(optional)*
        Either a preset name (``{"preset": "modern_light"}``), a path
        to a YAML file (``{"yaml": "brand.yml"}``), an inline token
        dict, or an already-built
        :class:`~power_pptx.design.tokens.DesignTokens` instance.  The
        mapping forms combine: ``preset`` is the base, a ``yaml`` file
        is merged over it, inline sections (``palette``,
        ``typography``, ``radii``, ``shadows``, ``spacings``) are
        applied over that, and ``overrides`` (dotted paths or nested
        dicts) last.  Any other key is rejected.  Bare numbers in
        length fields are points.

    ``slide_size`` *(optional)*
        Resize the slides to the given dimensions.  Accepts shorthand
        strings (``"16:9"``, ``"widescreen"``, ``"4:3"``, ``"a4"``)
        or an explicit ``(width, height)`` pair / dict
        (``{"width": 13.333, "height": 7.5}``).  Numbers are
        interpreted as inches.  The template's masters and layouts are
        rescaled to the new size, so placeholder layouts fill the
        slide.  An unknown name raises :class:`SpecError` listing the
        names accepted.

    ``vars`` *(optional)*
        Variable bag for ``{{name}}`` interpolation in any string field
        of the spec.  Spec-level ``vars`` are layered under any *vars*
        argument passed to :func:`from_spec` (the kwarg wins).

        Interpolation only runs when variables are declared — a spec
        with no ``vars`` key and no *vars* argument is left exactly as
        written, so ``{{ ... }}`` in a code sample survives.  When it
        does run, an unknown name raises :class:`SpecError`, and
        ``\\{{`` writes a literal ``{{``.

    ``interpolate`` *(optional)*
        ``False`` turns interpolation off for the whole spec.  The same
        key on a slide turns it off for that slide only — useful for a
        ``code`` slide showing Jinja, Go-template or GitHub Actions
        syntax in a deck that otherwise uses variables.

    ``lint`` *(optional)*
        ``"off"`` (default), ``"warn"``, or ``"raise"``.

    ``template`` *(optional)*
        Path to a ``.pptx`` or ``.potx`` file to use as the base template
        instead of the default blank template.

    *safe* and *base_dir* are for specs you did not write yourself (a
    model's output, a user's upload):

    * ``safe=True`` requires every file the spec names — ``template``,
      a token ``yaml``, ``image``, a ``figure`` path — to resolve,
      after following symlinks, inside *base_dir*, and captures HTML
      and Plotly figures with network access blocked (only ``data:``
      URLs and the capture's own loopback document are loadable).
    * *base_dir* is the directory relative paths in the spec are
      resolved against.  It defaults to the current working directory,
      which is also the boundary safe mode enforces when *base_dir* is
      not given.

    Whatever *safe* is, ``browser_path`` is refused inside a spec's
    ``html_options`` / ``plotly_options``: which executable to launch is
    the caller's decision (``POWER_PPTX_CHROMIUM``, or the Python API).

    Raises:
        :class:`~power_pptx.exc.LintError`  when ``lint == "raise"`` and the linter
        finds errors.
        :class:`SpecError`  (a :class:`ValueError`) for unrecognised keys,
        invalid values, missing files, or a slide that cannot be built.
        The message names the offending spec location, e.g.
        ``slides[2].kpis[0]``.
    """
    if not isinstance(spec, dict):
        raise TypeError(f"spec must be a dict, got {type(spec).__name__!r}")

    ctx = _Context(safe=bool(safe), base_dir=None if base_dir is None else Path(base_dir))
    _validate_spec_keys(spec)

    # Resolve interpolation variables: kwarg overrides spec-level.
    merged_vars: dict[str, Any] = {}
    spec_vars = spec.get("vars")
    if spec_vars is not None:
        merged_vars.update(spec_vars)
    if vars is not None:
        if not isinstance(vars, Mapping):
            raise TypeError(f"vars must be a mapping, got {type(vars).__name__!r}")
        merged_vars.update(vars)

    # Interpolate only when variables were declared.  A spec that never
    # mentions ``vars`` is not a template, so ``{{ ... }}`` in it — a
    # Jinja or GitHub Actions snippet on a code slide, say — is content.
    # Once variables are declared, an unknown name is an error rather
    # than a literal placeholder on the slide.
    if (spec_vars is not None or vars is not None) and spec.get("interpolate", True):
        spec = _interpolate_spec(spec, merged_vars)

    prs = _open_template(spec.get("template"), ctx)

    # ``theme`` is treated as a friendly alias for ``tokens`` when
    # ``tokens`` is absent.  Pre-IMPROVEMENTS-#8 the key was in
    # ``_VALID_TOP_KEYS`` and silently ignored, so docs that read
    # ``{"theme": {...}}`` produced an unstyled deck without error.
    token_spec, token_key = spec.get("tokens"), "tokens"
    if token_spec is None:
        token_spec, token_key = spec.get("theme"), "theme"
    tokens = _resolve_tokens(token_spec, where=token_key, ctx=ctx)

    slide_size = spec.get("slide_size")
    if slide_size is not None:
        _apply_slide_size(prs, slide_size)

    slide_specs = spec.get("slides", [])
    # Shape names are collected up-front so a bad ``allow_overlap_with``
    # reference can say *why* it failed — unknown everywhere vs. defined
    # on a different slide (see ``_apply_overlap_allowances``).
    deck_shape_names = _collect_shape_names(slide_specs)
    for slide_index, slide_spec in enumerate(slide_specs):
        _add_slide(
            prs,
            slide_spec,
            tokens,
            slide_index=slide_index,
            deck_shape_names=deck_shape_names,
            ctx=ctx,
        )

    lint_mode = spec.get("lint", "off")
    if lint_mode != "off":
        _run_lint(prs, lint_mode)

    return prs


def from_yaml(
    path: "str | os.PathLike[str]",
    *,
    vars: Optional[Mapping[str, Any]] = None,
    safe: bool = False,
    base_dir: "str | os.PathLike[str] | None" = None,
) -> Presentation:
    """Load a deck spec from *path* (YAML file) and run :func:`from_spec`.

    Requires ``pyyaml`` (``pip install pyyaml``).  The YAML file must
    parse to a top-level mapping; the same keys :func:`from_spec`
    accepts are valid here.  Variable interpolation (*vars*) is
    threaded through unchanged so YAML decks parameterise cleanly::

        prs = from_yaml("deck.yml", vars={"company": "ACME", "quarter": "Q4"})

    *safe* and *base_dir* are passed to :func:`from_spec`.  *path* itself
    is the caller's choice and is not subject to the safe-mode boundary.
    """
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - import guard
        raise ImportError("from_yaml requires pyyaml; install with `pip install pyyaml`") from exc
    with open(path, encoding="utf-8") as f:
        spec = yaml.safe_load(f) or {}
    if not isinstance(spec, dict):
        raise ValueError(f"YAML at {path!r} did not parse to a mapping")
    return from_spec(spec, vars=vars, safe=safe, base_dir=base_dir)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_VALID_TOP_KEYS = frozenset(
    {"slides", "lint", "template", "theme", "tokens", "vars", "slide_size", "interpolate"}
)
_VALID_LINT_VALUES = frozenset({"off", "warn", "raise"})

# Recipe layout name → (recipe callable, mandatory spec keys).  Listed
# inline rather than imported lazily so the dispatcher fails closed if
# a recipe gets renamed.
_RECIPE_LAYOUTS: dict[str, tuple[str, frozenset[str]]] = {
    "title_recipe": ("title_slide", frozenset({"title"})),
    "bullets_recipe": ("bullet_slide", frozenset({"title", "bullets"})),
    "kpi": ("kpi_slide", frozenset({"title", "kpis"})),
    "quote": ("quote_slide", frozenset({"quote"})),
    "image_hero": ("image_hero_slide", frozenset({"title", "image"})),
    "section_divider": ("section_divider", frozenset({"title"})),
    "chart": ("chart_slide", frozenset({"title", "categories", "series"})),
    "table": ("table_slide", frozenset({"title", "columns", "rows"})),
    "code": ("code_slide", frozenset({"title", "code"})),
    "timeline": ("timeline_slide", frozenset({"title", "milestones"})),
    "comparison": (
        "comparison_slide",
        frozenset({"title", "left_heading", "right_heading", "rows"}),
    ),
    "figure": ("figure_slide", frozenset({"title", "figure"})),
}


def _did_you_mean(word: Any, candidates: Iterable[str]) -> str:
    """Return a ``" (did you mean 'x'?)"`` suffix for the closest candidate.

    Returns an empty string when nothing is close enough. Used to make typo'd
    spec keys / values recoverable in a single follow-up — particularly for an
    LLM authoring a spec, which can act on the suggestion without a round-trip.
    """
    import difflib

    if not isinstance(word, str):
        return ""
    matches = difflib.get_close_matches(word, list(candidates), n=1, cutoff=0.6)
    return f" (did you mean {matches[0]!r}?)" if matches else ""


def _format_unknown(unknown: Iterable[Any], candidates: Iterable[str]) -> str:
    """Render unknown keys/values, each annotated with its closest candidate."""
    candidates = list(candidates)
    return "; ".join(f"{u!r}{_did_you_mean(u, candidates)}" for u in sorted(unknown, key=str))


def _describe(value: Any) -> str:
    """Return a short ``type repr`` description of *value* for an error message."""
    if value is None:
        return "null"
    text = repr(value)
    if len(text) > 60:
        text = text[:57] + "..."
    return f"{type(value).__name__} {text}"


def _validate_spec_keys(spec: dict[str, Any]) -> None:
    unknown = set(spec) - _VALID_TOP_KEYS
    if unknown:
        raise SpecError(
            f"Unknown spec keys: {_format_unknown(unknown, _VALID_TOP_KEYS)}. "
            f"Valid keys: {sorted(_VALID_TOP_KEYS)}"
        )
    lint = spec.get("lint", "off")
    # ``isinstance`` first: an unhashable value (``["raise"]``) cannot be
    # looked up in the frozenset at all.
    if not isinstance(lint, str) or lint not in _VALID_LINT_VALUES:
        raise SpecError(
            f"lint must be one of {sorted(_VALID_LINT_VALUES)!r}, got {lint!r}"
            f"{_did_you_mean(lint, _VALID_LINT_VALUES)}",
            path="lint",
        )
    spec_vars = spec.get("vars")
    if spec_vars is not None and not isinstance(spec_vars, Mapping):
        raise SpecError("spec 'vars' must be a mapping", path="vars")
    if "interpolate" in spec:
        _flag(spec["interpolate"], "interpolate")
    if not isinstance(spec.get("slides", []), list):
        raise SpecError("'slides' must be a list", path="slides")
    for index, slide in enumerate(spec.get("slides", [])):
        _validate_slide_keys(slide, f"slides[{index}]")


def _validate_slide_keys(slide: Any, where: str) -> None:
    """Check the slide-spec keys the dispatcher reads before building anything."""
    if not isinstance(slide, Mapping):
        raise SpecError(f"{where}: each slide must be a mapping", path=where)
    layout = slide.get("layout")
    if layout is not None and not isinstance(layout, str):
        raise SpecError(f"{where}.layout must be a string", path=f"{where}.layout")
    if "interpolate" in slide:
        _flag(slide["interpolate"], f"{where}.interpolate")


def _open_template(template: Any, ctx: _Context) -> Any:
    """Return the presentation the deck is built on (*template*, or the default)."""
    from power_pptx import Presentation

    if template is None or template == "":
        return Presentation()
    if isinstance(template, (str, os.PathLike)):
        source: Any = ctx.resolve_file(template, "template")
    elif hasattr(template, "read"):
        source = template
    else:
        raise _spec_error(
            "template", f"expected a path to a .pptx or .potx file; got {_describe(template)}"
        )
    try:
        return Presentation(source)
    except Exception as exc:
        raise _spec_error("template", f"cannot open {template!r} as a presentation: {exc}") from exc


def _resolve_layout(prs: Any, layout_name: str) -> Any:
    """Return the SlideLayout for *layout_name*.

    First tries the built-in alias table, then an exact case-insensitive
    match against the presentation's own layout names (so custom
    templates work). An unrecognized name raises :class:`ValueError`
    rather than silently substituting the Blank layout — a silent
    fallback reads as "my styled layout just didn't apply" and is the
    same fail-closed-on-typos contract the spec-key validation uses. Use
    ``"blank"`` explicitly for a deliberately blank slide.
    """
    canonical = _LAYOUT_ALIASES.get(layout_name.lower())
    if canonical:
        layout = prs.slide_layouts.get_by_name(canonical)
        if layout is not None:
            return layout

    # Try exact match in the presentation's layouts (supports custom templates)
    for sl in prs.slide_layouts:
        if sl.name.lower() == layout_name.lower():
            return sl

    candidates = sorted(
        set(_LAYOUT_ALIASES)
        | set(_RECIPE_LAYOUTS)
        | set(_LEGACY_TO_RECIPE)
        | {sl.name.lower() for sl in prs.slide_layouts}
    )
    raise ValueError(
        f"Unknown layout {layout_name!r}{_did_you_mean(layout_name.lower(), candidates)}. "
        f"Valid layouts: {candidates}"
    )


def _add_slide(
    prs: Any,
    slide_spec: dict[str, Any],
    tokens: Any = None,
    *,
    slide_index: int = 0,
    deck_shape_names: Optional[Mapping[str, list[int]]] = None,
    ctx: Optional[_Context] = None,
) -> Any:
    """Add a single slide to *prs* according to *slide_spec*.

    When the layout name matches a styled recipe (``kpi``, ``chart``,
    …), dispatch through :mod:`power_pptx.design.recipes`; otherwise
    fall back to the placeholder-based legacy path so existing decks
    keep working.

    When *tokens* is provided, legacy alias names (``"title"`` /
    ``"bullets"``) are silently upgraded to their token-aware recipe
    counterparts (``"title_recipe"`` / ``"bullets_recipe"``).  Before
    this change the placeholder-based legacy path was taken and the
    user's tokens were silently ignored, producing a default-styled
    slide while ``lint`` and ``save`` succeeded.  See IMPROVEMENTS
    item 9.

    A ``shapes`` list on the slide spec is applied last, on top of
    whatever the layout produced — see :func:`_add_spec_shapes`.
    *slide_index* and *deck_shape_names* only feed error messages and
    cross-slide reference detection there.

    Every failure leaves here as a :class:`SpecError` naming
    ``slides[slide_index]`` — and the offending key where one can be
    identified — chained from whatever was raised underneath.  The one
    exception is :class:`ImportError`: a missing optional dependency
    (Playwright, Kaleido, …) is an installation problem, not a problem
    with the spec, and callers already catch it as such.
    """
    where = f"slides[{slide_index}]"
    try:
        return _build_slide(
            prs,
            slide_spec,
            tokens,
            where=where,
            slide_index=slide_index,
            deck_shape_names=deck_shape_names or {},
            ctx=ctx or _Context(),
        )
    except (SpecError, ImportError):
        raise
    except Exception as exc:
        raise _slide_failure(where, slide_spec, exc) from exc


# Recipe layout → the key whose value is a file or document the recipe
# reads.  Every other key of these layouts is checked before the recipe
# runs, so a read, decode or capture failure inside it is about that
# value, and the error can name it.
_SOURCE_KEYS: dict[str, str] = {"image_hero": "image", "figure": "figure"}


def _slide_failure(where: str, slide_spec: Mapping[str, Any], exc: Exception) -> SpecError:
    """Return the :class:`SpecError` for a failure raised while building a slide."""
    layout = slide_spec.get("layout") or "blank"
    key = _SOURCE_KEYS.get(layout.lower()) if isinstance(layout, str) else None
    if key and slide_spec.get(key) is not None:
        if isinstance(exc, OSError):
            return _spec_error(f"{where}.{key}", f"cannot read {_describe(slide_spec[key])}: {exc}")
        if isinstance(exc, (ValueError, RuntimeError)):
            return _spec_error(f"{where}.{key}", str(exc))
    if isinstance(exc, ValueError):
        return _spec_error(where, str(exc))
    return _spec_error(where, f"layout {layout!r} could not be built ({type(exc).__name__}: {exc})")


def _build_slide(
    prs: Any,
    slide_spec: Mapping[str, Any],
    tokens: Any,
    *,
    where: str,
    slide_index: int,
    deck_shape_names: Mapping[str, list[int]],
    ctx: _Context,
) -> Any:
    """Build one slide; raises freely — :func:`_add_slide` locates the errors."""
    declared = slide_spec.get("layout")
    layout_name = (declared or "blank").lower()

    upgrade = _LEGACY_TO_RECIPE.get(layout_name)
    if upgrade is not None and (tokens is not None or slide_spec.get("tokens") is not None):
        layout_name = upgrade

    if layout_name in _RECIPE_LAYOUTS:
        slide = _add_recipe_slide(prs, slide_spec, layout_name, tokens, where=where, ctx=ctx)
    else:
        slide = _add_legacy_slide(
            prs, slide_spec, layout_name, where=where, declared=bool(declared)
        )

    if slide_spec.get("shapes") is not None:
        _add_spec_shapes(
            slide,
            slide_spec["shapes"],
            slide_index=slide_index,
            deck_shape_names=deck_shape_names,
        )

    return slide


# Legacy placeholder-based layout name → recipe layout name.  Only
# applied when ``tokens`` is provided to :func:`from_spec`; without
# tokens the legacy path is what the caller wants.
_LEGACY_TO_RECIPE: dict[str, str] = {
    "title": "title_recipe",
    "bullets": "bullets_recipe",
}


# Slide-spec keys handled by the dispatcher itself and therefore never
# forwarded to a recipe (which would reject them as unknown kwargs).
_RECIPE_NEVER_KWARGS = frozenset({"layout", "shapes", "interpolate"})


# ---------------------------------------------------------------------------
# Value validation — the dispatcher checks the *shape* of every value it
# forwards, so a wrong type is reported against the spec key instead of
# surfacing as an AttributeError three frames inside a recipe (or, worse,
# rendering one character per line).  What goes *inside* a KPI, milestone,
# series or comparison row is the recipe's contract and is checked there.
# ---------------------------------------------------------------------------


def _text(value: Any, path: str) -> str:
    """Return *value* if it is a string; a spec text field takes nothing else."""
    if isinstance(value, str):
        return value
    hint = ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        hint = f' — write it as a string: "{value}"'
    raise _spec_error(path, f"expected a string; got {_describe(value)}{hint}")


def _flag(value: Any, path: str) -> bool:
    if isinstance(value, bool):
        return value
    raise _spec_error(path, f"expected true or false; got {_describe(value)}")


def _items(value: Any, path: str, what: str) -> list[Any]:
    """Return *value* as a list; a string is not a list of its characters."""
    if isinstance(value, (list, tuple)):
        return list(value)
    hint = " — wrap it in a list" if isinstance(value, (str, Mapping)) else ""
    raise _spec_error(path, f"expected {what}; got {_describe(value)}{hint}")


def _mapping_items(example: str) -> Callable[[Any, str], list[Any]]:
    """Return a validator for "a list of mappings" shaped like *example*."""

    def validate(value: Any, path: str) -> list[Any]:
        items = _items(value, path, f"a list of mappings like {example}")
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                raise _spec_error(
                    f"{path}[{index}]",
                    f"expected a mapping like {example}; got {_describe(item)}",
                )
        return items

    return validate


def _label_items(value: Any, path: str) -> list[Any]:
    """Validate a list of labels (chart categories, table column headings)."""
    items = _items(value, path, "a list of labels")
    for index, item in enumerate(items):
        if item is None or isinstance(item, (Mapping, list, tuple, set, bool)):
            raise _spec_error(
                f"{path}[{index}]", f"expected a label (text or a number); got {_describe(item)}"
            )
    return items


def _column_items(value: Any, path: str) -> list[Any]:
    items = _label_items(value, path)
    if not items:
        raise _spec_error(path, "expected at least one column heading; got an empty list")
    return items


def _table_rows(value: Any, path: str) -> list[Any]:
    rows = _items(value, path, "a list of rows, each a list of cell values")
    for index, row in enumerate(rows):
        row_path = f"{path}[{index}]"
        if not isinstance(row, (list, tuple)):
            hint = (
                " — list the cells in column order instead of naming them"
                if isinstance(row, Mapping)
                else ""
            )
            raise _spec_error(
                row_path, f"expected a list of cell values; got {_describe(row)}{hint}"
            )
        for column, cell in enumerate(row):
            if isinstance(cell, (Mapping, list, tuple, set)):
                raise _spec_error(
                    f"{row_path}[{column}]",
                    f"expected a cell value (text or a number); got {_describe(cell)}",
                )
    return [list(row) for row in rows]


def _number_items(value: Any, path: str) -> list[Any]:
    items = _items(value, path, "a list of numbers")
    for index, item in enumerate(items):
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            raise _spec_error(
                f"{path}[{index}]", f"expected a finite number; got {_describe(item)}"
            )
    return items


def _one_of(*choices: str) -> Callable[[Any, str], str]:
    """Return a validator for a string that must be one of *choices*."""

    def validate(value: Any, path: str) -> str:
        text = _text(value, path)
        if text not in choices:
            raise _spec_error(
                path,
                f"expected one of {list(choices)}; got {text!r}"
                f"{_did_you_mean(text.lower(), choices)}",
            )
        return text

    return validate


def _text_items(value: Any, path: str) -> list[Any]:
    items = _items(value, path, "a list of strings")
    for index, item in enumerate(items):
        _text(item, f"{path}[{index}]")
    return items


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    raise _spec_error(path, f"expected a mapping; got {_describe(value)}")


def _progress(value: Any, path: str) -> tuple[int, int]:
    """Validate a section divider's ``[current, total]`` pair."""
    if (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
    ):
        current, total = value
        if 1 <= current <= total:
            return current, total
        raise _spec_error(
            path, f"expected 1 <= current <= total in [current, total]; got {_describe(value)}"
        )
    raise _spec_error(
        path,
        f"expected [current, total] — two whole numbers such as [3, 7]; got {_describe(value)}",
    )


def _chart_palette(value: Any, path: str) -> Any:
    """Validate a chart palette: a built-in name or a list of colours.

    Checked here because a recipe treats a palette that fails to apply as
    cosmetic and carries on with the default colours — which turns a typo
    in the name into a silently unbranded chart.
    """
    from power_pptx.chart.palettes import palette_names, resolve_palette

    if isinstance(value, str):
        names = list(palette_names())
        if value not in names:
            raise _spec_error(
                path,
                f"unknown chart palette {value!r}{_did_you_mean(value.lower(), names)}. "
                f"Valid names: {names}, or give a list of colours",
            )
        return value
    colours = _items(value, path, "a palette name or a list of colours")
    for index, colour in enumerate(colours):
        try:
            resolve_palette([colour])
        except Exception as exc:
            raise _spec_error(
                f"{path}[{index}]", f"not a colour: {_describe(colour)} ({exc})"
            ) from exc
    if not colours:
        raise _spec_error(path, "expected at least one colour; got an empty list")
    return colours


_BULLET_KEYS = ("text", "level")


def _bullet_items(value: Any, path: str) -> list[tuple[str, int]]:
    """Return a ``bullets`` value as ``(text, level)`` pairs.

    Each bullet is a string, or a ``{"text": ..., "level": ...}`` mapping
    where ``level`` is 0 (the default) to 8.
    """
    if not isinstance(value, (list, tuple)):
        hint = " — wrap it in a list, one string per bullet" if isinstance(value, str) else ""
        raise _spec_error(path, f"expected a list of bullets; got {_describe(value)}{hint}")
    return [_bullet_item(item, f"{path}[{index}]") for index, item in enumerate(value)]


def _bullet_item(item: Any, path: str) -> tuple[str, int]:
    """Return one bullet — a string or a ``{"text", "level"}`` mapping — as ``(text, level)``."""
    if isinstance(item, str):
        return item, 0
    if not isinstance(item, Mapping):
        hint = (
            ' — a nested list is not a sub-list; use {"text": ..., "level": 1}'
            if isinstance(item, (list, tuple))
            else ""
        )
        raise _spec_error(
            path,
            'expected a string or a {"text": ..., "level": ...} mapping; '
            f"got {_describe(item)}{hint}",
        )
    unknown = set(item) - set(_BULLET_KEYS)
    if unknown:
        raise _spec_error(
            path,
            f"unknown bullet keys {_format_unknown(unknown, _BULLET_KEYS)}. "
            f"Valid keys: {list(_BULLET_KEYS)}",
        )
    if item.get("text") is None:
        raise _spec_error(path, "a bullet mapping needs a 'text' string")
    level = _bullet_level(item.get("level"), f"{path}.level")
    return _text(item["text"], f"{path}.text"), level


def _bullet_level(level: Any, path: str) -> int:
    """Return a bullet's ``level``: 0 (the default, for ``None``) to 8."""
    level = 0 if level is None else level
    if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= 8:
        raise _spec_error(
            path, f"expected a whole number from 0 (top level) to 8; got {_describe(level)}"
        )
    return level


def _flat_bullets(items: list[tuple[str, int]], path: str) -> list[str]:
    """Return the bullet texts for a recipe that draws a flat list."""
    for index, (_bullet, level) in enumerate(items):
        if level:
            raise _spec_error(
                f"{path}[{index}].level",
                "the token-styled bullets recipe draws a flat list, so a nested level "
                'would be lost. Use level 0, or "layout": "Title and Content" — the '
                "placeholder layout, which indents by level",
            )
    return [text for text, _level in items]


def _transition_name(transition: Any, path: str) -> Optional[str]:
    """Return the canonical key for *transition* (``None`` when there is none)."""
    if transition is None or transition == "":
        return None
    if not isinstance(transition, str):
        raise _spec_error(path, f"expected a transition name; got {_describe(transition)}")
    key = transition.strip().lower().replace("-", "_").replace(" ", "_")
    if key not in _TRANSITION_NAMES:
        raise _spec_error(
            path,
            f"Unknown transition {transition!r}{_did_you_mean(key, _TRANSITION_NAMES)}. "
            f"Valid values: {sorted(_TRANSITION_NAMES)}",
        )
    return key


_FIGURE_HINT = (
    " (a figure string is either SVG / HTML markup starting with '<' or a path to an "
    "image, .svg or .html file)"
)


def _looks_like_markup(value: str) -> bool:
    return value.lstrip("﻿ \t\r\n").startswith("<")


def _image_source(value: Any, path: str, ctx: _Context) -> Any:
    """Validate an ``image`` value: a path to an existing file, or an open file."""
    if isinstance(value, (str, os.PathLike)):
        return ctx.resolve_file(value, path)
    if hasattr(value, "read"):
        return value
    raise _spec_error(path, f"expected a path to an image file; got {_describe(value)}")


def _figure_source(value: Any, path: str, ctx: _Context) -> Any:
    """Validate a ``figure`` value: markup, a path to an existing file, or a figure object."""
    if isinstance(value, os.PathLike) or (isinstance(value, str) and not _looks_like_markup(value)):
        return ctx.resolve_file(value, path, hint=_FIGURE_HINT)
    if (
        isinstance(value, (str, bytes, bytearray))
        or callable(getattr(value, "to_image", None))
        or callable(getattr(value, "savefig", None))
    ):
        return value
    raise _spec_error(
        path,
        "expected SVG or HTML markup, a path to an image / .svg / .html file, or a "
        f"Plotly or Matplotlib figure; got {_describe(value)}",
    )


# Capture options that configure the *process* rather than the picture.
# A spec is data, frequently written by a model: it must never get to
# choose which executable is launched.  The Python functions keep the
# parameter; only the spec route is closed.
_PROCESS_LEVEL_OPTIONS = frozenset({"browser_path"})

# Spec key → the figures-module function its options are forwarded to.
_CAPTURE_TARGETS: dict[str, str] = {
    "html_options": "add_html_figure",
    "plotly_options": "add_plotly_figure",
}

# Parameters of those functions that the recipe supplies itself.
_FIGURE_OWN_ARGS = frozenset(
    {"slide", "html", "figure", "left", "top", "width", "height", "format"}
)


def _capture_options(key: str, value: Any, path: str, ctx: _Context) -> dict[str, Any]:
    """Validate a figure slide's ``html_options`` / ``plotly_options`` mapping."""
    import inspect

    from power_pptx.design import figures as _figures

    if not isinstance(value, Mapping):
        raise _spec_error(path, f"expected a mapping of capture options; got {_describe(value)}")
    target = getattr(_figures, _CAPTURE_TARGETS[key])
    for name in value:
        if name in _PROCESS_LEVEL_OPTIONS:
            raise _spec_error(
                f"{path}.{name}",
                f"{name!r} cannot be set from a spec: it chooses the executable that is "
                "launched. Set the POWER_PPTX_CHROMIUM environment variable, or call "
                f"{target.__name__}(..., {name}=...) from Python",
            )
    parameters = inspect.signature(target).parameters
    accepted = set(parameters) - _FIGURE_OWN_ARGS - _PROCESS_LEVEL_OPTIONS
    unknown = set(value) - accepted
    if unknown and not any(p.kind is p.VAR_KEYWORD for p in parameters.values()):
        hint = " ('format' is the slide's 'figure_format' key)" if "format" in unknown else ""
        raise _spec_error(
            path,
            f"unknown options {_format_unknown(unknown, accepted)}{hint}. "
            f"Accepted: {sorted(accepted)}.",
        )
    options = dict(value)
    if isinstance(options.get("viewport"), list):
        # JSON has no tuples; the capture functions document a pair.
        options["viewport"] = tuple(options["viewport"])
    if ctx.safe:
        if options.get("allow_network"):
            raise _spec_error(
                f"{path}.allow_network",
                "a spec built with safe=True cannot turn network access back on",
            )
        options["allow_network"] = False
    return options


_KPI_EXAMPLE = '{"label": "ARR", "value": "$182M"}'
_MILESTONE_EXAMPLE = '{"date": "Q1", "label": "Alpha"}'
_SERIES_EXAMPLE = '{"name": "ARR", "values": [82, 110]}'
_COMPARISON_ROW_EXAMPLE = '{"left": "Before", "right": "After"}'

# Spec key → validator, for keys that mean the same thing on every recipe.
_KEY_VALIDATORS: dict[str, Callable[[Any, str], Any]] = {
    **dict.fromkeys(
        (
            "title",
            "subtitle",
            "caption",
            "eyebrow",
            "quote",
            "attribution",
            "code",
            "language",
            "left_heading",
            "right_heading",
            "chart_type",
        ),
        _text,
    ),
    **dict.fromkeys(("legend", "smooth", "data_labels", "banded"), _flag),
    "transition": _transition_name,
    "figure_format": _one_of("auto", "svg", "png"),
    "bullets": _bullet_items,
    "kpis": _mapping_items(_KPI_EXAMPLE),
    "milestones": _mapping_items(_MILESTONE_EXAMPLE),
    "series": _mapping_items(_SERIES_EXAMPLE),
    "categories": _label_items,
    "columns": _column_items,
    "widths": _number_items,
    "aligns": _text_items,
    "totals": _mapping,
    "progress": _progress,
    "chart_palette": _chart_palette,
}

# (layout, key) → validator, where one key name means different things.
_LAYOUT_VALIDATORS: dict[tuple[str, str], Callable[[Any, str], Any]] = {
    ("table", "rows"): _table_rows,
    ("comparison", "rows"): _mapping_items(_COMPARISON_ROW_EXAMPLE),
}

# Spec key → validator, for keys that name a file the recipe reads: which
# files a spec may name depends on the call's safe mode and base directory.
_FILE_VALIDATORS: dict[str, Callable[[Any, str, _Context], Any]] = {
    "image": _image_source,
    "figure": _figure_source,
}


def _add_recipe_slide(
    prs: Any,
    slide_spec: Mapping[str, Any],
    layout_name: str,
    tokens: Any,
    *,
    where: str = "slide",
    ctx: Optional[_Context] = None,
) -> Any:
    """Dispatch to the recipe matching *layout_name*.

    Validates required keys and the shape of every value, then forwards
    *every other* spec key as a keyword argument to the recipe.  The
    ``tokens`` and ``transition`` arguments are threaded through
    automatically: spec-level tokens apply unless the slide carries its
    own ``tokens`` field, which is resolved exactly like the spec-level
    one (see :func:`_resolve_tokens`).

    Unknown kwargs (keys the recipe's signature doesn't accept) raise
    :class:`SpecError` rather than being silently dropped.  This
    prevents subtle typos like ``subtitlz: ...`` from quietly producing
    a slide without the intended subtitle.  A key set to ``None`` (JSON
    ``null``) is treated as absent, so the recipe's default applies.
    """
    import inspect

    from power_pptx.design import recipes as _recipes

    ctx = ctx or _Context()
    recipe_name, required = _RECIPE_LAYOUTS[layout_name]
    recipe = getattr(_recipes, recipe_name)

    missing = [k for k in required if slide_spec.get(k) is None]
    if missing:
        raise _spec_error(
            where,
            f"layout {layout_name!r} requires keys {sorted(required)}; missing {sorted(missing)}",
        )

    given = {k: v for k, v in slide_spec.items() if k not in _RECIPE_NEVER_KWARGS}
    parameters = inspect.signature(recipe).parameters
    _check_recipe_keys(given, parameters, layout_name, where)
    kwargs = _recipe_kwargs(given, layout_name, tokens, where=where, ctx=ctx)

    if "bullets" in kwargs:
        kwargs["bullets"] = _flat_bullets(kwargs["bullets"], f"{where}.bullets")
    if layout_name == "table":
        _check_table_row_lengths(kwargs["columns"], kwargs["rows"], where)
    if ctx.safe:
        # Untrusted spec: captures run offline whether or not the slide
        # mentions capture options at all.
        for key in _CAPTURE_TARGETS:
            if key in parameters:
                kwargs.setdefault(key, {"allow_network": False})

    return recipe(prs, **kwargs)


def _check_recipe_keys(
    given: Mapping[str, Any],
    parameters: Mapping[str, inspect.Parameter],
    layout_name: str,
    where: str,
) -> None:
    """Reject a spec key the recipe has no parameter for.

    Fail closed on typos: any kwarg the recipe doesn't accept is an
    error.  Recipes accept ``tokens`` and ``transition`` consistently,
    so this catches misspelled content keys (``subtitlz``, ``millestones``)
    that previously silently no-op'd.
    """
    if any(p.kind is p.VAR_KEYWORD for p in parameters.values()):
        return
    accepted = set(parameters) - {"prs"}
    unknown = set(given) - accepted
    if unknown:
        raise _spec_error(
            where,
            f"layout {layout_name!r}: unknown spec keys "
            f"{_format_unknown(unknown, accepted)}. "
            f"Accepted: {sorted(accepted)}.",
        )


def _recipe_kwargs(
    given: Mapping[str, Any],
    layout_name: str,
    tokens: Any,
    *,
    where: str,
    ctx: _Context,
) -> dict[str, Any]:
    """Return the recipe keyword arguments for a slide's *given* keys, each checked."""
    kwargs: dict[str, Any] = {}
    for key, value in given.items():
        path = f"{where}.{key}"
        if key == "tokens":
            # An explicit ``null`` opts the slide out of the deck's tokens.
            kwargs[key] = (
                None if value is None else _resolve_tokens(value, where=path, ctx=ctx, base=tokens)
            )
        elif value is not None:
            kwargs[key] = _recipe_value(key, value, path, layout_name, ctx)
    # Spec-level tokens flow through unless the slide opts out / overrides.
    kwargs.setdefault("tokens", tokens)
    return kwargs


def _recipe_value(key: str, value: Any, path: str, layout_name: str, ctx: _Context) -> Any:
    """Return the checked recipe argument for one spec *key*.

    A key no validator knows is passed through as written: what goes in it
    is the recipe's contract.
    """
    if key in _CAPTURE_TARGETS:
        return _capture_options(key, value, path, ctx)
    file_validator = _FILE_VALIDATORS.get(key)
    if file_validator is not None:
        return file_validator(value, path, ctx)
    validator = _LAYOUT_VALIDATORS.get((layout_name, key)) or _KEY_VALIDATORS.get(key)
    return value if validator is None else validator(value, path)


def _check_table_row_lengths(columns: list[Any], rows: list[Any], where: str) -> None:
    """Reject a table row with more cells than the table has columns.

    The recipe draws exactly ``len(columns)`` cells per row, so a
    longer row would lose its tail without a word.
    """
    width = len(columns)
    for index, row in enumerate(rows):
        if len(row) > width:
            raise _spec_error(
                f"{where}.rows[{index}]",
                f"has {len(row)} cells but the table has {width} columns "
                f"({columns!r}); the extra cells would be dropped",
            )


def _add_legacy_slide(
    prs: Any,
    slide_spec: Mapping[str, Any],
    layout_name: str,
    *,
    where: str,
    declared: bool,
) -> Any:
    """Add a slide from one of the template's placeholder layouts and fill it."""
    layout = _resolve_layout(prs, layout_name)
    # Named standard layouts accept the same fields as their aliases.
    legacy_name = next(
        (alias for alias, name in _LAYOUT_ALIASES.items() if name.lower() == layout.name.lower()),
        layout_name,
    )
    if layout_name == "kpi_grid":
        legacy_name = layout_name
    accepted = _COMMON_SLIDE_KEYS | _LEGACY_CONTENT_KEYS.get(legacy_name, set())
    unknown = set(slide_spec) - accepted
    if unknown:
        hint = (
            " ('tokens' only styles recipe layouts; a placeholder layout takes its "
            "look from the template)"
            if "tokens" in unknown
            else ""
        )
        raise _spec_error(
            where,
            f"layout {layout_name!r}: unknown spec keys "
            f"{_format_unknown(unknown, accepted)}{hint}. Accepted: {sorted(accepted)}.",
        )
    label = (
        f"layout {layout_name!r}"
        if declared
        else "the default 'blank' layout (this slide has no 'layout' key)"
    )
    slide = prs.slides.add_slide(layout)

    _set_title(slide, slide_spec.get("title"), where=where, label=label)
    _set_subtitle_or_body(slide, slide_spec, legacy_name, where=where, label=label)
    _set_transition(slide, slide_spec.get("transition"), f"{where}.transition")
    return slide


def _set_title(slide: Any, title: Any, *, where: str = "slide", label: str = "this layout") -> None:
    """Put *title* in the slide's title placeholder; never drop it silently."""
    if title is None:
        return
    text = _text(title, f"{where}.title")
    placeholder = slide.shapes.title
    if placeholder is None:
        raise _spec_error(
            f"{where}.title",
            f"{label} has no title placeholder, so the title would be dropped. Use a "
            "layout that has one ('title_only', 'title', 'bullets', ...), a recipe "
            "layout, or a 'shapes' entry",
        )
    placeholder.text_frame.text = text


def _legacy_placeholder_map(slide: Any, layout_name: str) -> dict[str, int]:
    """Return the content-key → placeholder-idx map for a legacy layout."""
    mapping = _LEGACY_PLACEHOLDERS.get(layout_name, {})
    if layout_name == "comparison_layout":
        present = {ph.placeholder_format.idx for ph in slide.placeholders}
        if not {3, 4} <= present:
            # A custom template whose "Comparison" layout is just two
            # content placeholders: fill those, as ``two_column`` does.
            mapping = _LEGACY_PLACEHOLDERS["two_column"]
    return mapping


def _set_subtitle_or_body(
    slide: Any,
    spec: Mapping[str, Any],
    layout_name: str,
    *,
    where: str = "slide",
    label: str = "this layout",
) -> None:
    """Populate the secondary placeholders or add shapes based on layout type.

    Note: ``comparison`` (bare) routes to the recipe earlier in the
    dispatcher and never reaches this function.  ``comparison_layout``
    is the placeholder-based opt-in that does.
    """
    if layout_name == "kpi_grid":
        if spec.get("kpis") is not None:
            _add_kpi_shapes(slide, spec["kpis"], where=f"{where}.kpis")
        return

    mapping = _legacy_placeholder_map(slide, layout_name)
    for first, second in _LEGACY_SYNONYMS:
        if first in mapping and spec.get(first) is not None and spec.get(second) is not None:
            raise _spec_error(
                f"{where}.{second}",
                f"{first!r} and {second!r} fill the same placeholder; give only one",
            )
    placeholders = {ph.placeholder_format.idx: ph for ph in slide.placeholders}
    for key in sorted(_LEGACY_CONTENT_KEYS.get(layout_name, set())):
        value = spec.get(key)
        if value is None or value == "" or value == []:
            continue
        path = f"{where}.{key}"
        placeholder = placeholders.get(mapping.get(key, -1))
        if placeholder is None or not placeholder.has_text_frame:
            raise _spec_error(
                path, f"{label} has no text placeholder for {key!r}, so it would be dropped"
            )
        _fill_text_frame(placeholder.text_frame, value, path, key)


def _fill_text_frame(text_frame: Any, value: Any, path: str, key: str) -> None:
    """Write a legacy content value — a string or a bullet list — into *text_frame*."""
    if key not in _LEGACY_LIST_KEYS or (isinstance(value, str) and key != "bullets"):
        text_frame.text = _text(value, path)
        return
    text_frame.text = ""
    for index, (text, level) in enumerate(_bullet_items(value, path)):
        paragraph = text_frame.paragraphs[0] if index == 0 else text_frame.add_paragraph()
        paragraph.text = text
        if level:
            paragraph.level = level


def _set_transition(slide: Any, transition: Any, where: str = "transition") -> None:
    key = _transition_name(transition, where)
    if key is None:
        return
    slide.transition.kind = getattr(MSO_TRANSITION_TYPE, _TRANSITION_NAMES[key])


# ---------------------------------------------------------------------------
# Per-slide ``shapes`` entries — extra shapes plus lint-intent declarations
# ---------------------------------------------------------------------------

# Keys accepted on a single ``shapes`` entry.  Fail-closed like every
# other key set in this module: an unrecognised key raises rather than
# being silently dropped, so ``lint_groupp`` doesn't quietly leave the
# overlap undeclared.
_VALID_SHAPE_KEYS = frozenset(
    {
        "name",
        "shape",
        "text",
        "left",
        "top",
        "width",
        "height",
        "lint_group",
        "layer",
        "layer_above",
        "allow_overlap_with",
    }
)

# Geometry is mandatory — a shape entry with no box has nothing to draw.
_REQUIRED_SHAPE_KEYS = ("left", "top", "width", "height")

# Value of the ``shape`` key that means "plain text box" rather than an
# ``MSO_SHAPE`` autoshape.  Also the default when ``shape`` is omitted.
_TEXTBOX_SHAPE_NAME = "textbox"


def _collect_shape_names(slide_specs: Any) -> dict[str, list[int]]:
    """Map every ``shapes`` entry name in the deck to the slides defining it.

    Collected before any slide is built so an ``allow_overlap_with``
    reference to a shape on a *different* slide can be reported as
    exactly that, rather than as a plain "unknown shape" — including
    when the other slide comes later in the spec.
    """
    names: dict[str, list[int]] = {}
    if not isinstance(slide_specs, list):
        return names
    for slide_index, slide_spec in enumerate(slide_specs):
        if not isinstance(slide_spec, Mapping):
            continue
        entries = slide_spec.get("shapes")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            name = entry.get("name")
            if isinstance(name, str) and name.strip():
                names.setdefault(name, []).append(slide_index)
    return names


def _add_spec_shapes(
    slide: Any,
    shape_specs: Any,
    *,
    slide_index: int,
    deck_shape_names: Mapping[str, list[int]],
) -> None:
    """Add the slide spec's ``shapes`` entries to *slide*.

    A shape entry is a mapping with a geometry box and, optionally, a
    name, a shape type, text, and the linter's three intent
    declarations::

        {
            "layout": "blank",
            "shapes": [
                {"name": "card",  "shape": "rounded_rectangle",
                 "left": 1, "top": 1, "width": 4, "height": 2,
                 "layer": "card"},
                {"name": "badge", "shape": "oval",
                 "left": 4.4, "top": 0.7, "width": 1.2, "height": 0.8,
                 "layer_above": "card",
                 "allow_overlap_with": "card"},
            ],
        }

    Entry keys:

    ``left`` / ``top`` / ``width`` / ``height`` *(required)*
        Numbers are inches (matching ``slide_size``); pass a
        :class:`~power_pptx.util.Length` to opt out.

    ``name`` *(optional)*
        The shape's name, which doubles as the spec-level handle
        ``allow_overlap_with`` resolves against.  Names must be unique
        within a slide.

    ``shape`` *(optional)*
        An ``MSO_SHAPE`` member name, case- and separator-insensitive
        (``"rounded_rectangle"``, ``"Rounded Rectangle"``).  Defaults to
        ``"textbox"``.

    ``text`` *(optional)*
        Text for the shape's text frame.

    ``lint_group`` / ``layer`` / ``layer_above`` *(optional)*
        Passed straight through to the matching
        :class:`~power_pptx.shapes.base.BaseShape` property, which
        validates them.

    ``allow_overlap_with`` *(optional)*
        A shape name, or a list of them, naming other shapes **on the
        same slide**.  Resolved to real shape ids after every shape on
        the slide exists, so forward references work.
    """
    where_slide = f"slides[{slide_index}]"
    if not isinstance(shape_specs, list):
        raise SpecError(
            f"{where_slide}: 'shapes' must be a list of shape entries; got "
            f"{type(shape_specs).__name__!r}",
            path=f"{where_slide}.shapes",
        )

    built: list[tuple[Mapping[str, Any], Any]] = []
    by_name: dict[str, Any] = {}
    for pos, entry in enumerate(shape_specs):
        where = f"{where_slide}.shapes[{pos}]"
        shape = _add_spec_shape(slide, entry, where=where)
        name = entry.get("name")
        if name is not None:
            if name in by_name:
                raise SpecError(
                    f"{where}: duplicate shape name {name!r} on {where_slide}. "
                    "Shape names must be unique within a slide so "
                    "'allow_overlap_with' can resolve them.",
                    path=f"{where}.name",
                )
            by_name[name] = shape
        built.append((entry, shape))

    # Second pass: every shape on the slide now exists (and has an id),
    # so a reference may point forward as well as back.
    for pos, (entry, shape) in enumerate(built):
        _apply_overlap_allowances(
            shape,
            entry,
            by_name,
            where=f"{where_slide}.shapes[{pos}]",
            slide_index=slide_index,
            deck_shape_names=deck_shape_names,
        )


def _add_spec_shape(slide: Any, entry: Any, *, where: str) -> Any:
    """Create one shape from a ``shapes`` entry and return it."""
    _check_shape_keys(entry, where)
    name = _shape_name(entry, where)
    box = _shape_box(entry, name, where)
    shape = _new_shape(slide, entry.get("shape", _TEXTBOX_SHAPE_NAME), box, where)

    if name is not None:
        shape.name = name

    text = entry.get("text")
    if text is not None:
        shape.text_frame.text = str(text)

    _apply_lint_intent(shape, entry, where)
    return shape


def _check_shape_keys(entry: Any, where: str) -> None:
    """Reject a ``shapes`` entry that is not a mapping, or that has an unknown key."""
    if not isinstance(entry, Mapping):
        raise SpecError(
            f"{where}: each 'shapes' entry must be a mapping; got {type(entry).__name__!r}",
            path=where,
        )

    unknown = set(entry) - _VALID_SHAPE_KEYS
    if unknown:
        raise SpecError(
            f"{where}: unknown shape keys "
            f"{_format_unknown(unknown, _VALID_SHAPE_KEYS)}. "
            f"Valid keys: {sorted(_VALID_SHAPE_KEYS)}",
            path=where,
        )


def _shape_name(entry: Mapping[str, Any], where: str) -> Optional[str]:
    """Return a ``shapes`` entry's checked ``name``, or ``None`` when it has none."""
    name = entry.get("name")
    if name is None:
        return None
    if not isinstance(name, str) or not name.strip():
        raise SpecError(
            f"{where}: shape 'name' must be a non-empty string; got {name!r}",
            path=f"{where}.name",
        )
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise SpecError(
            f"{where}: shape 'name' must not contain control characters; got {name!r}",
            path=f"{where}.name",
        )
    return name


def _shape_box(entry: Mapping[str, Any], name: Optional[str], where: str) -> tuple[Any, ...]:
    """Return a ``shapes`` entry's ``(left, top, width, height)`` as lengths."""
    missing = [k for k in _REQUIRED_SHAPE_KEYS if k not in entry]
    if missing:
        raise SpecError(
            f"{where}: shape entries require keys {list(_REQUIRED_SHAPE_KEYS)}; missing {missing}",
            path=where,
        )
    # Sizes cannot be negative and nothing can be larger, or further
    # away, than the largest slide PowerPoint allows: outside that range
    # the value is a mistake, and writing it would produce a file that
    # fails schema validation (a negative ``cx``) or cannot be opened.
    of_shape = f" of shape {name!r}" if name is not None else ""
    return tuple(
        _coerce_length(
            entry[k],
            f"{where}: {k!r}{of_shape}",
            minimum=0.0 if k in ("width", "height") else -_MAX_INCHES,
            maximum=_MAX_INCHES,
            path=f"{where}.{k}",
        )
        for k in _REQUIRED_SHAPE_KEYS
    )


def _new_shape(slide: Any, kind: Any, box: tuple[Any, ...], where: str) -> Any:
    """Add the text box or ``MSO_SHAPE`` autoshape *kind* names, at *box*."""
    if not isinstance(kind, str):
        raise SpecError(
            f"{where}: 'shape' must be a string naming an MSO_SHAPE member or "
            f"{_TEXTBOX_SHAPE_NAME!r}; got {type(kind).__name__!r}",
            path=f"{where}.shape",
        )
    if kind.strip().lower() == _TEXTBOX_SHAPE_NAME:
        return slide.shapes.add_textbox(*box)
    return slide.shapes.add_shape(_resolve_autoshape(kind, where=where), *box)


def _apply_lint_intent(shape: Any, entry: Mapping[str, Any], where: str) -> None:
    """Set the entry's ``lint_group`` / ``layer`` / ``layer_above`` on *shape*.

    The three lint-intent scalars are plain pass-throughs: the shape
    properties own their validation, so a bad value is rejected for the
    same reason whether it came from Python or from a spec.  The spec
    layer adds the location, so a rejected value in a 40-slide spec is
    findable, and reports it as a ``SpecError`` like every other
    problem with a spec's content.
    """
    for field in ("lint_group", "layer", "layer_above"):
        if field not in entry:
            continue
        try:
            setattr(shape, field, entry[field])
        except (TypeError, ValueError) as exc:
            raise SpecError(f"{where}: {field!r}: {exc}", path=f"{where}.{field}") from exc


def _resolve_autoshape(kind: str, *, where: str) -> Any:
    """Return the ``MSO_SHAPE`` member named by *kind*.

    Accepts the member name in any case and with spaces or hyphens
    standing in for underscores, so ``"rounded rectangle"`` and
    ``"ROUNDED_RECTANGLE"`` both land on the same member.
    """
    from power_pptx.enum.shapes import MSO_SHAPE

    member = kind.strip().upper().replace(" ", "_").replace("-", "_")
    try:
        return getattr(MSO_SHAPE, member)
    except AttributeError:
        pass
    candidates = [m.name.lower() for m in MSO_SHAPE] + [_TEXTBOX_SHAPE_NAME]
    raise SpecError(
        f"{where}: unknown shape type {kind!r}"
        f"{_did_you_mean(member.lower(), candidates)}. Valid values are "
        f"{_TEXTBOX_SHAPE_NAME!r} or any MSO_SHAPE member name, e.g. "
        "'rectangle', 'rounded_rectangle', 'oval'.",
        path=f"{where}.shape",
    )


def _apply_overlap_allowances(
    shape: Any,
    entry: Mapping[str, Any],
    by_name: Mapping[str, Any],
    *,
    where: str,
    slide_index: int,
    deck_shape_names: Mapping[str, list[int]],
) -> None:
    """Resolve an entry's ``allow_overlap_with`` names and apply them.

    Shape ids are assigned by the library at creation time, so a spec
    names its peers instead; resolution happens here, once every shape
    on the slide exists.  Ids are only unique within a slide, so a
    reference to a shape on another slide is rejected rather than
    silently ignored.
    """
    raw = entry.get("allow_overlap_with")
    if raw is None:
        return

    own_name = entry.get("name")
    targets = []
    for ref in _overlap_refs(raw, where):
        _check_overlap_ref(ref, own_name, where)
        target = by_name.get(ref)
        if target is None:
            raise _unresolved_overlap_ref(
                ref,
                by_name,
                where=where,
                slide_index=slide_index,
                deck_shape_names=deck_shape_names,
            )
        targets.append(target)

    if targets:
        shape.allow_overlap_with(*targets)


def _overlap_refs(raw: Any, where: str) -> list[Any]:
    """Return an ``allow_overlap_with`` value as a list of references."""
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (list, tuple)):
        return list(raw)
    raise SpecError(
        f"{where}: 'allow_overlap_with' must be a shape name or a list of "
        f"shape names; got {type(raw).__name__!r}",
        path=f"{where}.allow_overlap_with",
    )


def _check_overlap_ref(ref: Any, own_name: Any, where: str) -> None:
    """Reject a reference that is not a shape name, or that names its own shape."""
    if not isinstance(ref, str) or not ref.strip():
        raise SpecError(
            f"{where}: 'allow_overlap_with' entries must be non-empty shape names; got {ref!r}",
            path=f"{where}.allow_overlap_with",
        )
    if ref == own_name:
        raise SpecError(
            f"{where}: 'allow_overlap_with' names this shape itself "
            f"({ref!r}); an allowance always describes a pair of shapes.",
            path=f"{where}.allow_overlap_with",
        )


def _unresolved_overlap_ref(
    ref: str,
    by_name: Mapping[str, Any],
    *,
    where: str,
    slide_index: int,
    deck_shape_names: Mapping[str, list[int]],
) -> SpecError:
    """Return the error for a reference to no shape on this slide.

    It says so when the name belongs to a shape on another slide, which
    an allowance can never name.
    """
    elsewhere = sorted(set(deck_shape_names.get(ref, ())) - {slide_index})
    if elsewhere:
        return SpecError(
            f"{where}: 'allow_overlap_with' names shape {ref!r}, which "
            f"is defined on slides {elsewhere} — an overlap allowance "
            "is keyed on shape id, and shape ids are only unique "
            "within a slide, so it can only name a shape on "
            f"slides[{slide_index}].",
            path=f"{where}.allow_overlap_with",
        )
    return SpecError(
        f"{where}: 'allow_overlap_with' names unknown shape {ref!r}"
        f"{_did_you_mean(ref, by_name)} on slides[{slide_index}]. "
        f"Named shapes on that slide: {sorted(by_name)}",
        path=f"{where}.allow_overlap_with",
    )


_LEGACY_KPI_KEYS = ("label", "value", "delta")


def _add_kpi_shapes(slide: Any, kpis: Any, *, where: str = "kpis") -> None:
    """Add KPI card shapes to *slide* — label, value, and optional delta.

    The cards sit in centred rows inside the slide margins.  A card is
    2.2" wide when there is room and narrows — its value font shrinking in
    proportion — as the row fills, wrapping to another row before it would
    become too narrow to read.  A grid that cannot fit above the bottom
    margin is an error rather than a set of shapes hanging off the slide.
    """
    from power_pptx.util import Inches

    kpis = _legacy_kpis(kpis, where)
    if not kpis:
        return
    presentation = slide.part.package.presentation_part.presentation
    grid = _KpiGrid.fit(
        len(kpis),
        presentation.slide_width or Inches(10),
        presentation.slide_height or Inches(7.5),
        where=where,
    )
    for index, kpi in enumerate(kpis):
        _add_kpi_card(slide, kpi, grid, index, where=f"{where}[{index}]")


def _legacy_kpis(kpis: Any, where: str) -> list[Any]:
    """Return a legacy ``kpis`` value as a list of checked KPI mappings."""
    kpis = _mapping_items(_KPI_EXAMPLE)(kpis, where)
    for index, kpi in enumerate(kpis):
        unknown = set(kpi) - set(_LEGACY_KPI_KEYS)
        if unknown:
            raise _spec_error(
                f"{where}[{index}]",
                f"unknown KPI keys {_format_unknown(unknown, _LEGACY_KPI_KEYS)}. "
                f"Valid keys: {list(_LEGACY_KPI_KEYS)}",
            )
        for key in ("label", "value"):
            if isinstance(kpi.get(key), (Mapping, list, tuple, set)):
                raise _spec_error(
                    f"{where}[{index}].{key}",
                    f"expected text or a number; got {_describe(kpi[key])}",
                )
    return kpis


@dataclass(frozen=True)
class _KpiGrid:
    """Where the legacy ``kpi_grid`` layout puts its cards; lengths are EMU.

    A card is a value box over a label box over an optional delta box.
    """

    count: int
    per_row: int
    slide_width: int
    card_width: int
    value_size: int
    gap: int
    top: int
    value_height: int
    label_height: int
    delta_height: int

    @classmethod
    def fit(cls, count: int, slide_width: int, slide_height: int, *, where: str) -> "_KpiGrid":
        """Return the grid for *count* cards, or raise when it cannot fit on the slide."""
        from power_pptx.util import Emu, Inches, Pt

        margin = Inches(0.5)
        gap = Inches(0.2)
        max_card_w, min_card_w = Inches(2.2), Inches(1.1)
        value_h, label_h, delta_h = Inches(1.0), Inches(0.4), Inches(0.3)
        row_h = value_h + label_h + delta_h
        top = Inches(2.5)

        available = slide_width - 2 * margin
        max_per_row = max(1, int((available + gap) // (min_card_w + gap)))
        max_rows = max(0, int((slide_height - margin - top + gap) // (row_h + gap)))
        rows = -(-count // max_per_row)
        if rows > max_rows:
            raise _spec_error(
                where,
                f"{count} KPIs do not fit on this slide (room for {max_per_row * max_rows}); "
                "split them across slides",
            )
        # Balance the rows (8 cards → 4 + 4, not 7 + 1) and size every card
        # for the fullest row so the grid stays aligned.
        per_row = -(-count // rows)
        card_w = Emu(min(int(max_card_w), int((available - (per_row - 1) * gap) // per_row)))
        return cls(
            count=count,
            per_row=per_row,
            slide_width=slide_width,
            card_width=card_w,
            value_size=Pt(max(14.0, 32.0 * card_w / max_card_w)),
            gap=gap,
            top=top,
            value_height=value_h,
            label_height=label_h,
            delta_height=delta_h,
        )

    @property
    def row_height(self) -> int:
        return self.value_height + self.label_height + self.delta_height

    def card_origin(self, index: int) -> tuple[int, int]:
        """Return the top-left corner of card *index*; each row is centred."""
        from power_pptx.util import Emu

        row, column = divmod(index, self.per_row)
        in_row = min(self.per_row, self.count - row * self.per_row)
        row_w = in_row * self.card_width + (in_row - 1) * self.gap
        left = Emu(int((self.slide_width - row_w) // 2 + column * (self.card_width + self.gap)))
        top = Emu(int(self.top + row * (self.row_height + self.gap)))
        return left, top


def _add_kpi_card(
    slide: Any, kpi: Mapping[str, Any], grid: _KpiGrid, index: int, *, where: str
) -> None:
    """Draw KPI card *index*: its value, its label and, when it has one, its delta."""
    from power_pptx.dml.color import RGBColor
    from power_pptx.util import Pt

    left, top = grid.card_origin(index)
    width = grid.card_width
    label = "" if kpi.get("label") is None else str(kpi["label"])
    value = "" if kpi.get("value") is None else str(kpi["value"])
    delta = kpi.get("delta")

    _add_kpi_text(
        slide,
        (left, top, width, grid.value_height),
        value,
        grid.value_size,
        bold=True,
        wrap=False,
    )
    label_top = top + grid.value_height
    _add_kpi_text(
        slide,
        (left, label_top, width, grid.label_height),
        label,
        Pt(12),
        color=RGBColor(0x60, 0x60, 0x60),
    )
    if delta is None:
        return
    text, negative = _kpi_delta(delta, f"{where}.delta")
    _add_kpi_text(
        slide,
        (left, label_top + grid.label_height, width, grid.delta_height),
        text,
        Pt(11),
        color=RGBColor(0xCC, 0x00, 0x00) if negative else RGBColor(0x00, 0x8A, 0x00),
    )


def _kpi_delta(delta: Any, path: str) -> tuple[str, bool]:
    """Return a KPI delta's text and whether it is negative.

    A number is a fraction rendered as a signed percentage; a string is
    shown as written.
    """
    if isinstance(delta, str):
        return delta, delta.strip().startswith(("-", "−", "–"))
    if isinstance(delta, bool) or not isinstance(delta, (int, float)) or not math.isfinite(delta):
        raise _spec_error(
            path,
            "expected a number such as 0.27 (shown as +27%) or a string to show "
            f"as written; got {_describe(delta)}",
        )
    sign = "+" if delta >= 0 else ""
    return f"{sign}{float(delta):.0%}", delta < 0


def _add_kpi_text(
    slide: Any,
    box: tuple[int, int, int, int],
    text: str,
    size: int,
    *,
    bold: bool = False,
    color: Any = None,
    wrap: bool = True,
) -> None:
    """Add one centred single-run text box of a KPI card."""
    from power_pptx.enum.text import PP_ALIGN

    text_frame = slide.shapes.add_textbox(*box).text_frame
    if not wrap:
        text_frame.word_wrap = False
    paragraph = text_frame.paragraphs[0]
    run = paragraph.add_run()
    run.text = text
    run.font.size = size
    if bold:
        run.font.bold = True
    if color is not None:
        run.font.color.rgb = color
    paragraph.alignment = PP_ALIGN.CENTER


# Keys of a ``tokens`` mapping that say where the tokens come from; the
# rest of its keys are the token sections themselves.
_TOKEN_SOURCE_KEYS = ("preset", "yaml", "overrides")


def _resolve_tokens(
    spec: Any,
    *,
    where: str = "tokens",
    ctx: Optional[_Context] = None,
    base: Any = None,
) -> Any:
    """Build a :class:`DesignTokens` from a token spec, or ``None``.

    Accepts:

    * ``None`` — return ``None``.
    * A :class:`~power_pptx.design.tokens.DesignTokens` instance — returned as-is so
      callers can reuse a built token bag between imperative recipes and
      :func:`from_spec` without round-tripping through ``.to_dict()`` (no such
      method exists today).  See IMPROVEMENTS item 8.
    * A mapping whose keys are any of ``preset``, ``yaml``, ``overrides``
      and the token sections (``palette``, ``typography``, ``radii``,
      ``shadows``, ``spacings``).  They are applied in that order, each
      over the last: the preset is the base, the YAML brand file is merged
      over it, inline sections override individual slots (and individual
      fields of a typography or shadow token), and ``overrides`` — dotted
      paths or nested dicts — go on last.  With neither ``preset`` nor
      ``yaml`` the sections are a complete inline
      ``DesignTokens.from_dict`` payload.

    Nothing is ignored: an unknown key raises with a did-you-mean hint, so
    ``{"palete": ...}`` cannot quietly produce an unstyled deck and a
    ``palette`` next to a ``preset`` really does change the colour.

    *where* names the spec key in errors.  *base* is the token set to
    layer onto when the mapping names no ``preset`` / ``yaml`` of its own:
    the deck's tokens, when resolving a slide-level ``tokens`` key.
    """
    if spec is None:
        return None
    from power_pptx.design.tokens import DesignTokens

    if isinstance(spec, DesignTokens):
        return spec
    sections = _token_sections(spec, where)
    ctx = ctx or _Context()
    try:
        return _build_tokens(spec, sections, ctx, where=where, base=base)
    except (SpecError, ImportError):
        raise
    except Exception as exc:
        raise _token_error(where, exc) from exc


def _token_sections(spec: Any, where: str) -> dict[str, Mapping[str, Any]]:
    """Check a ``tokens`` mapping's keys and return its inline token sections."""
    from power_pptx.design.tokens import _SECTIONS

    if not isinstance(spec, Mapping):
        hint = (
            f' — for a preset write {{"preset": {spec!r}}}, for a brand file {{"yaml": {spec!r}}}'
            if isinstance(spec, str)
            else ""
        )
        raise SpecError(
            f"'{where}' must be a mapping or DesignTokens instance; got "
            f"{type(spec).__name__!r}{hint}",
            path=where,
        )
    known = (*_TOKEN_SOURCE_KEYS, *_SECTIONS)
    unknown = set(spec) - set(known)
    if unknown:
        raise _spec_error(
            where,
            f"unknown token keys {_format_unknown(unknown, known)}. Valid keys: {list(known)}",
        )
    sections = {name: spec[name] for name in _SECTIONS if spec.get(name) is not None}
    for name, section in sections.items():
        if not isinstance(section, Mapping):
            raise _spec_error(
                f"{where}.{name}",
                f"expected a mapping of token names to values; got {_describe(section)}",
            )
    return sections


def _build_tokens(
    spec: Mapping[str, Any],
    sections: Mapping[str, Mapping[str, Any]],
    ctx: _Context,
    *,
    where: str,
    base: Any,
) -> Any:
    """Return the token set a checked ``tokens`` mapping describes.

    The preset is the base, a YAML brand file is merged over it (both
    fall back to *base*), then the inline *sections*, then ``overrides``.
    """
    from power_pptx.design.tokens import DesignTokens

    tokens = None
    if spec.get("preset") is not None:
        tokens = DesignTokens.from_preset(spec["preset"])
    if spec.get("yaml") is not None:
        loaded = DesignTokens.from_yaml(ctx.resolve_file(spec["yaml"], f"{where}.yaml"))
        tokens = loaded if tokens is None else tokens.merge(loaded)
    if tokens is None:
        tokens = base
    if tokens is None:
        tokens = DesignTokens.from_dict(sections)
    elif sections:
        tokens = tokens.with_overrides(sections)
    if spec.get("overrides") is not None:
        tokens = tokens.with_overrides(spec["overrides"])
    return tokens


def _token_error(where: str, exc: Exception) -> SpecError:
    """Return the :class:`SpecError` for a failure building the tokens at *where*."""
    from power_pptx.design.tokens import _SECTIONS

    detail = str(exc)
    # A token error already starts with its own path (``palette.primary:
    # ...``); join it on so the whole location reads as one.
    joined = any(detail.startswith((f"{name}.", f"{name}:")) for name in _SECTIONS)
    return SpecError(f"{where}{'.' if joined else ': '}{detail}", path=where)


# ---------------------------------------------------------------------------
# Slide size resolver
# ---------------------------------------------------------------------------

# Named aspect-ratio shorthands → (width_in, height_in) in inches.
# Matches PowerPoint's built-in "Page Setup" presets.
_SLIDE_SIZE_PRESETS: dict[str, tuple[float, float]] = {
    "16:9": (13.333, 7.5),
    "widescreen": (13.333, 7.5),
    "4:3": (10.0, 7.5),
    "standard": (10.0, 7.5),
    "16:10": (13.333, 8.333),
    "a4": (11.69, 8.27),
    "letter": (11.0, 8.5),
}

# PowerPoint's own slide-size limits, in inches.  Nothing on a slide can
# sensibly be larger than the largest slide, so the upper limit also
# bounds shape geometry — which keeps a stray ``1e9`` from being written
# as a coordinate no consumer can open.
_MIN_SLIDE_INCHES = 1.0
_MAX_INCHES = 56.0


def _coerce_length(
    value: Any,
    what: str,
    *,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
    path: str = "",
) -> Any:
    """Return *value* as a :class:`~power_pptx.util.Length`.

    Bare numbers are inches — the convention the rest of the spec uses
    (``slide_size``, shape geometry) — so a spec never has to name a raw
    EMU integer.  *what* names the offending field in the error message.
    *minimum* and *maximum* are inclusive bounds in inches; a value
    outside them, or one that is not finite, is rejected.
    """
    length = _as_length(value, what, path)
    inches = length / 914400
    if (minimum is not None and inches < minimum) or (maximum is not None and inches > maximum):
        allowed = _describe_bounds(minimum, maximum)
        raise SpecError(f"{what} must be {allowed} inches; got {value!r}", path=path)
    return length


def _as_length(value: Any, what: str, path: str) -> Any:
    """Return *value* — a Length, or a finite number of inches — as a Length."""
    from power_pptx.util import Inches, Length

    if isinstance(value, Length):
        return value
    # ``bool`` is a subclass of ``int``, so the ``isinstance(value,
    # (int, float))`` branch below would silently accept
    # ``slide_size=(True, False)`` as a 1" × 0" canvas.  Reject it
    # explicitly — matches the boolean-rejection rule that
    # ``power_pptx.util._coerce_emu`` applies for shape coordinates.
    if isinstance(value, bool):
        raise SpecError(
            f"{what} must be a number (inches) or Length; got bool: {value!r}", path=path
        )
    if not isinstance(value, (int, float)):
        raise SpecError(
            f"{what} must be a number (inches) or Length; got {type(value).__name__!r}: {value!r}",
            path=path,
        )
    if not math.isfinite(value):
        raise SpecError(
            f"{what} must be a finite number (inches) or Length; got {value!r}", path=path
        )
    return Inches(float(value))


def _describe_bounds(minimum: Optional[float], maximum: Optional[float]) -> str:
    """Return the allowed range for an error: ``between 0 and 56`` and so on."""
    if minimum is not None and maximum is not None:
        return f"between {minimum:g} and {maximum:g}"
    return f"at least {minimum:g}" if maximum is None else f"at most {maximum:g}"


def _resolve_slide_size(slide_size: Any) -> tuple[Any, Any]:
    """Return the ``(width, height)`` lengths a ``slide_size`` value names."""

    def _dimension(value: Any, name: str) -> Any:
        return _coerce_length(
            value,
            f"slide_size {name}",
            minimum=_MIN_SLIDE_INCHES,
            maximum=_MAX_INCHES,
            path="slide_size",
        )

    if isinstance(slide_size, str):
        key = slide_size.strip().lower()
        preset = _SLIDE_SIZE_PRESETS.get(key)
        if preset is None:
            raise SpecError(
                f"Unknown slide_size {slide_size!r}"
                f"{_did_you_mean(key, _SLIDE_SIZE_PRESETS)}. Valid shorthands: "
                f"{sorted(_SLIDE_SIZE_PRESETS)}, or pass (width, height).",
                path="slide_size",
            )
        return _dimension(preset[0], "width"), _dimension(preset[1], "height")
    if isinstance(slide_size, Mapping):
        if "width" not in slide_size or "height" not in slide_size:
            raise SpecError(
                "slide_size mapping must have 'width' and 'height' keys", path="slide_size"
            )
        return _dimension(slide_size["width"], "width"), _dimension(slide_size["height"], "height")
    if isinstance(slide_size, (list, tuple)) and len(slide_size) == 2:
        return _dimension(slide_size[0], "width"), _dimension(slide_size[1], "height")
    raise SpecError(
        f"slide_size must be a string preset, (w, h) pair, or "
        f"{{'width', 'height'}} mapping; got {type(slide_size).__name__!r}",
        path="slide_size",
    )


def _apply_slide_size(prs: Any, slide_size: Any) -> None:
    """Set ``prs.slide_width`` / ``prs.slide_height`` from a spec value.

    Accepts a named shorthand string, an ``(width, height)`` 2-tuple of
    inches, or a ``{"width": w, "height": h}`` mapping (inches or
    :class:`~power_pptx.util.Length`).  Numbers are interpreted as inches;
    pass an explicit ``Length`` to opt out.  See IMPROVEMENTS item 10.

    Each dimension must lie within PowerPoint's 1–56 inch range.  When the
    size changes, the geometry of the masters, the layouts and any slides
    already in the deck is rescaled to match — see
    :func:`_rescale_template_geometry`.
    """
    width, height = _resolve_slide_size(slide_size)
    old_width, old_height = prs.slide_width, prs.slide_height
    prs.slide_width = width
    prs.slide_height = height
    _rescale_template_geometry(prs, old_width, old_height)


def _rescale_template_geometry(prs: Any, old_width: Any, old_height: Any) -> None:
    """Scale master, layout and existing-slide geometry to the new slide size.

    Changing the slide size on its own leaves every placeholder where the
    template put it, so a 4:3 template resized to 16:9 keeps all its
    content in the left three quarters of the slide.  PowerPoint rescales
    the masters and layouts when the size changes; this does the same, so
    placeholder layouts keep filling the slide.  Shapes stretch with the
    slide; a picture keeps its aspect ratio and stays centred on the spot
    it occupied.  Shapes that inherit their position are left alone — they
    follow the placeholder they inherit from.
    """
    new_width, new_height = prs.slide_width, prs.slide_height
    if not old_width or not old_height or not new_width or not new_height:
        return
    if (old_width, old_height) == (new_width, new_height):
        return
    scale_x, scale_y = new_width / old_width, new_height / old_height
    trees = []
    for master in prs.slide_masters:
        trees.append(master.shapes._spTree)
        trees.extend(layout.shapes._spTree for layout in master.slide_layouts)
    trees.extend(slide.shapes._spTree for slide in prs.slides)
    for tree in trees:
        for element in tree.iterchildren():
            _rescale_element(element, scale_x, scale_y)


def _rescale_element(element: Any, scale_x: float, scale_y: float) -> None:
    """Scale one shape-tree child's own ``a:off`` / ``a:ext``, if it has them."""
    from power_pptx.oxml.ns import qn

    xfrm = None
    for holder in ("p:spPr", "p:grpSpPr"):
        properties = element.find(qn(holder))
        if properties is not None:
            xfrm = properties.find(qn("a:xfrm"))
            break
    else:
        xfrm = element.find(qn("p:xfrm"))
    if xfrm is None:
        return
    off, ext = xfrm.find(qn("a:off")), xfrm.find(qn("a:ext"))
    if off is None or ext is None:
        return
    try:
        x, y = int(off.get("x")), int(off.get("y"))
        cx, cy = int(ext.get("cx")), int(ext.get("cy"))
    except (TypeError, ValueError):
        return
    if element.tag == qn("p:pic"):
        scale = min(scale_x, scale_y)
        new_cx, new_cy = round(cx * scale), round(cy * scale)
        new_x = round((x + cx / 2) * scale_x - new_cx / 2)
        new_y = round((y + cy / 2) * scale_y - new_cy / 2)
    else:
        new_x, new_y = round(x * scale_x), round(y * scale_y)
        new_cx, new_cy = round(cx * scale_x), round(cy * scale_y)
    off.set("x", str(new_x))
    off.set("y", str(new_y))
    ext.set("cx", str(new_cx))
    ext.set("cy", str(new_cy))


# ``\{{`` (group 1 unset) is the escape for a literal ``{{``; otherwise
# group 1 is the variable name, optionally a dotted path.
_INTERP_RE = re.compile(r"\\\{\{|\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")


def _interpolate_spec(spec: dict[str, Any], vars_: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of *spec* with ``{{name}}`` markers substituted.

    ``vars`` itself is not interpolated, and a slide carrying
    ``"interpolate": false`` is passed through exactly as written.
    """
    result: dict[str, Any] = {}
    for key, value in spec.items():
        if key in ("vars", "interpolate"):
            result[key] = value
        elif key == "slides" and isinstance(value, list):
            result[key] = [
                slide
                if isinstance(slide, Mapping) and slide.get("interpolate") is False
                else _interpolate(slide, vars_, f"slides[{index}]")
                for index, slide in enumerate(value)
            ]
        else:
            result[key] = _interpolate(value, vars_, str(key))
    return result


def _interpolate(value: Any, vars_: Mapping[str, Any], path: str = "") -> Any:
    """Recursively substitute ``{{name}}`` markers in any string within *value*.

    Walks dicts, lists, tuples, and strings.  ``{{name}}`` resolves to
    ``vars_['name']``; ``{{a.b.c}}`` walks dotted paths through nested
    mappings.  ``\\{{`` is the escape: it yields a literal ``{{`` and
    whatever follows is left alone.  Unknown names raise
    :class:`SpecError` naming *path* — the location of the string in the
    spec — so a typo doesn't silently render as the literal placeholder.
    """
    if isinstance(value, str):
        return _interpolate_text(value, vars_, path)
    if isinstance(value, dict):
        return {
            k: _interpolate(v, vars_, f"{path}.{k}" if path else str(k)) for k, v in value.items()
        }
    if isinstance(value, list):
        return [_interpolate(v, vars_, f"{path}[{i}]") for i, v in enumerate(value)]
    if isinstance(value, tuple):
        return tuple(_interpolate(v, vars_, f"{path}[{i}]") for i, v in enumerate(value))
    return value


def _interpolate_text(text: str, vars_: Mapping[str, Any], path: str) -> str:
    """Return *text* with its ``{{name}}`` markers substituted (see :func:`_interpolate`)."""
    if "{{" not in text:
        return text

    def _sub(match: "re.Match[str]") -> str:
        key = match.group(1)
        if key is None:
            return "{{"
        return str(_lookup_var(vars_, key, path))

    return _INTERP_RE.sub(_sub, text)


def _lookup_var(vars_: Mapping[str, Any], key: str, path: str) -> Any:
    """Return the variable *key* names, walking a dotted name through nested mappings."""
    cur: Any = vars_
    for p in key.split("."):
        if not (isinstance(cur, Mapping) and p in cur):
            names = sorted(str(name) for name in vars_)
            raise _spec_error(
                path,
                f"interpolation variable {key!r} not found in vars={names!r}"
                f"{_did_you_mean(key, names)}. Write \\{{{{ for a literal "
                "'{{', or set \"interpolate\": false on the slide (or the "
                "whole spec) to switch substitution off",
            )
        cur = cur[p]
    return cur


def _run_lint(prs: Any, mode: str) -> None:
    """Run the deck-level linter according to *mode* (``"warn"`` or ``"raise"``)."""
    import logging

    from power_pptx.exc import LintError

    logger = logging.getLogger(__name__)
    all_issues = []
    for slide in prs.slides:
        report = slide.lint()
        all_issues.extend(report.issues)

    errors = [i for i in all_issues if getattr(i, "severity", "warning") == "error"]

    if mode == "warn":
        for issue in all_issues:
            logger.warning("pptx lint: %s", issue)
    elif mode == "raise" and errors:
        msgs = "; ".join(str(i) for i in errors)
        raise LintError(f"Lint errors in generated presentation: {msgs}")
