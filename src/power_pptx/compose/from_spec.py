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
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Optional

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

# Lowercase transition name → MSO_TRANSITION_TYPE member name.
_TRANSITION_NAMES: dict[str, str] = {
    "none": "NONE",
    "fade": "FADE",
    "push": "PUSH",
    "wipe": "WIPE",
    "split": "SPLIT",
    "random_bar": "RANDOM_BAR",
    "circle": "CIRCLE",
    "dissolve": "DISSOLVE",
    "checker": "CHECKER",
    "diamond": "DIAMOND",
    "plus": "PLUS",
    "wedge": "WEDGE",
    "zoom": "ZOOM",
    "newsflash": "NEWSFLASH",
    "cover": "COVER",
    "strips": "STRIPS",
    "cut": "CUT",
    "blinds": "BLINDS",
    "pull": "PULL",
    "random": "RANDOM",
    "wheel": "WHEEL",
    "morph": "MORPH",
    "fly_through": "FLY_THROUGH",
    "vortex": "VORTEX",
    "switch": "SWITCH",
    "gallery": "GALLERY",
    "conveyor": "CONVEYOR",
}


def from_spec(
    spec: dict[str, Any],
    *,
    vars: Optional[Mapping[str, Any]] = None,
) -> Any:
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

        A slide dict may also carry a ``shapes`` list of extra shapes
        drawn on top of whatever the layout produced — see
        :func:`_add_spec_shapes` for the full shape-entry surface,
        including the ``lint_group`` / ``allow_overlap_with`` /
        ``layer`` / ``layer_above`` fields that declare an overlap as
        intentional at generation time.

    ``tokens`` *(optional)*
        Either a preset name (``{"preset": "modern_light"}``), a path
        to a YAML file (``{"yaml": "brand.yml"}``), an inline token
        dict, a mix of preset + ``overrides`` for per-deck tweaks, or
        an already-built :class:`~power_pptx.design.tokens.DesignTokens`
        instance.

    ``slide_size`` *(optional)*
        Resize the slides to the given dimensions.  Accepts shorthand
        strings (``"16:9"``, ``"widescreen"``, ``"4:3"``, ``"a4"``)
        or an explicit ``(width, height)`` pair / dict
        (``{"width": 13.333, "height": 7.5}``).  Numbers are
        interpreted as inches.  See :func:`_apply_slide_size` for the
        resolver implementation and ``_SLIDE_SIZE_PRESETS`` for the
        full list of named aspect ratios.

    ``vars`` *(optional)*
        Variable bag for ``{{name}}`` interpolation in any string field
        of the spec.  Spec-level ``vars`` are layered under any *vars*
        argument passed to :func:`from_spec` (the kwarg wins).

    ``lint`` *(optional)*
        ``"off"`` (default), ``"warn"``, or ``"raise"``.

    ``template`` *(optional)*
        Path to a ``.pptx`` or ``.potx`` file to use as the base template
        instead of the default blank template.

    Raises:
        :class:`~power_pptx.exc.LintError`  when ``lint == "raise"`` and the linter
        finds errors.
        :class:`ValueError`  for unrecognised keys or invalid values.
    """
    if not isinstance(spec, dict):
        raise TypeError(f"spec must be a dict, got {type(spec).__name__!r}")

    _validate_spec_keys(spec)

    # Resolve interpolation variables: kwarg overrides spec-level.
    merged_vars: dict[str, Any] = {}
    spec_vars = spec.get("vars")
    if spec_vars is not None:
        if not isinstance(spec_vars, Mapping):
            raise ValueError("spec 'vars' must be a mapping")
        merged_vars.update(spec_vars)
    if vars is not None:
        merged_vars.update(vars)

    # Always interpolate — even with no vars, a stray ``{{name}}`` in
    # the spec should raise rather than silently rendering as the
    # literal placeholder.
    spec = _interpolate(spec, merged_vars)

    from power_pptx import Presentation

    template = spec.get("template")
    prs = Presentation(template) if template else Presentation()

    # ``theme`` is treated as a friendly alias for ``tokens`` when
    # ``tokens`` is absent.  Pre-IMPROVEMENTS-#8 the key was in
    # ``_VALID_TOP_KEYS`` and silently ignored, so docs that read
    # ``{"theme": {...}}`` produced an unstyled deck without error.
    token_spec = spec.get("tokens")
    if token_spec is None:
        token_spec = spec.get("theme")
    tokens = _resolve_tokens(token_spec)

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
        )

    lint_mode = spec.get("lint", "off")
    if lint_mode != "off":
        _run_lint(prs, lint_mode)

    return prs


def from_yaml(
    path: str,
    *,
    vars: Optional[Mapping[str, Any]] = None,
) -> Any:
    """Load a deck spec from *path* (YAML file) and run :func:`from_spec`.

    Requires ``pyyaml`` (``pip install pyyaml``).  The YAML file must
    parse to a top-level mapping; the same keys :func:`from_spec`
    accepts are valid here.  Variable interpolation (*vars*) is
    threaded through unchanged so YAML decks parameterise cleanly::

        prs = from_yaml("deck.yml", vars={"company": "ACME", "quarter": "Q4"})
    """
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - import guard
        raise ImportError(
            "from_yaml requires pyyaml; install with `pip install pyyaml`"
        ) from exc
    with open(path, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f) or {}
    if not isinstance(spec, dict):
        raise ValueError(f"YAML at {path!r} did not parse to a mapping")
    return from_spec(spec, vars=vars)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_VALID_TOP_KEYS = frozenset(
    {"slides", "lint", "template", "theme", "tokens", "vars", "slide_size"}
)
_VALID_LINT_VALUES = frozenset({"off", "warn", "raise"})

# Recipe layout name → (recipe callable, mandatory spec keys).  Listed
# inline rather than imported lazily so the dispatcher fails closed if
# a recipe gets renamed.
_RECIPE_LAYOUTS: dict[str, tuple[str, frozenset[str]]] = {
    "title_recipe":     ("title_slide",      frozenset({"title"})),
    "bullets_recipe":   ("bullet_slide",     frozenset({"title", "bullets"})),
    "kpi":              ("kpi_slide",        frozenset({"title", "kpis"})),
    "quote":            ("quote_slide",      frozenset({"quote"})),
    "image_hero":       ("image_hero_slide", frozenset({"title", "image"})),
    "section_divider":  ("section_divider",  frozenset({"title"})),
    "chart":            ("chart_slide",      frozenset({"title", "categories", "series"})),
    "table":            ("table_slide",      frozenset({"title", "columns", "rows"})),
    "code":             ("code_slide",       frozenset({"title", "code"})),
    "timeline":         ("timeline_slide",   frozenset({"title", "milestones"})),
    "comparison":       ("comparison_slide", frozenset({"title", "left_heading", "right_heading", "rows"})),
    "figure":           ("figure_slide",     frozenset({"title", "figure"})),
}


def _did_you_mean(word: str, candidates: Iterable[str]) -> str:
    """Return a ``" (did you mean 'x'?)"`` suffix for the closest candidate.

    Returns an empty string when nothing is close enough. Used to make typo'd
    spec keys / values recoverable in a single follow-up — particularly for an
    LLM authoring a spec, which can act on the suggestion without a round-trip.
    """
    import difflib

    matches = difflib.get_close_matches(word, list(candidates), n=1, cutoff=0.6)
    return f" (did you mean {matches[0]!r}?)" if matches else ""


def _format_unknown(unknown: Iterable[str], candidates: Iterable[str]) -> str:
    """Render unknown keys/values, each annotated with its closest candidate."""
    candidates = list(candidates)
    return "; ".join(f"{u!r}{_did_you_mean(u, candidates)}" for u in sorted(unknown))


def _validate_spec_keys(spec: dict[str, Any]) -> None:
    unknown = set(spec) - _VALID_TOP_KEYS
    if unknown:
        raise ValueError(
            f"Unknown spec keys: {_format_unknown(unknown, _VALID_TOP_KEYS)}. "
            f"Valid keys: {sorted(_VALID_TOP_KEYS)}"
        )
    lint = spec.get("lint", "off")
    if lint not in _VALID_LINT_VALUES:
        raise ValueError(f"lint must be one of {sorted(_VALID_LINT_VALUES)!r}, got {lint!r}")
    if not isinstance(spec.get("slides", []), list):
        raise ValueError("'slides' must be a list")


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
    """
    layout_name = (slide_spec.get("layout") or "blank").lower()

    if tokens is not None:
        upgrade = _LEGACY_TO_RECIPE.get(layout_name)
        if upgrade is not None:
            layout_name = upgrade

    if layout_name in _RECIPE_LAYOUTS:
        slide = _add_recipe_slide(prs, slide_spec, layout_name, tokens)
    else:
        layout = _resolve_layout(prs, layout_name)
        slide = prs.slides.add_slide(layout)

        _set_title(slide, slide_spec.get("title"))
        _set_subtitle_or_body(slide, slide_spec, layout_name)
        _set_transition(slide, slide_spec.get("transition"))

    if "shapes" in slide_spec:
        _add_spec_shapes(
            slide,
            slide_spec["shapes"],
            slide_index=slide_index,
            deck_shape_names=deck_shape_names or {},
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
_RECIPE_NEVER_KWARGS = frozenset({"layout", "shapes"})


def _add_recipe_slide(
    prs: Any, slide_spec: dict[str, Any], layout_name: str, tokens: Any
) -> Any:
    """Dispatch to the recipe matching *layout_name*.

    Validates required keys, then forwards *every other* spec key as a
    keyword argument to the recipe.  The ``tokens`` and ``transition``
    arguments are threaded through automatically: spec-level tokens
    win when a slide-level ``tokens`` field isn't set.

    Unknown kwargs (keys the recipe's signature doesn't accept) raise
    :class:`ValueError` rather than being silently dropped.  This
    prevents subtle typos like ``subtitlz: ...`` from quietly producing
    a slide without the intended subtitle.
    """
    import inspect

    from power_pptx.design import recipes as _recipes

    recipe_name, required = _RECIPE_LAYOUTS[layout_name]
    recipe = getattr(_recipes, recipe_name)

    missing = [k for k in required if k not in slide_spec]
    if missing:
        raise ValueError(
            f"layout {layout_name!r} requires keys "
            f"{sorted(required)}; missing {sorted(missing)}"
        )

    kwargs = {
        k: v for k, v in slide_spec.items()
        if k not in _RECIPE_NEVER_KWARGS
    }
    # Spec-level tokens flow through unless the slide opts out / overrides.
    kwargs.setdefault("tokens", tokens)

    # Fail closed on typos: any kwarg the recipe doesn't accept is an
    # error.  Recipes accept ``tokens`` and ``transition`` consistently,
    # so this catches misspelled content keys (``subtitlz``, ``millestones``)
    # that previously silently no-op'd.
    sig = inspect.signature(recipe)
    accepts_var_kw = any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    if not accepts_var_kw:
        accepted = set(sig.parameters)
        unknown = sorted(set(kwargs) - accepted)
        if unknown:
            accepted_public = sorted(accepted - {"prs"})
            raise ValueError(
                f"layout {layout_name!r}: unknown spec keys "
                f"{_format_unknown(unknown, accepted_public)}. "
                f"Accepted: {accepted_public}."
            )

    return recipe(prs, **kwargs)


def _set_title(slide: Any, title: str | None) -> None:
    if title is None:
        return
    try:
        slide.shapes.title.text = title
    except AttributeError:
        pass  # layout has no title placeholder


def _set_subtitle_or_body(slide: Any, spec: dict[str, Any], layout_name: str) -> None:
    """Populate the secondary placeholder or add shapes based on layout type."""
    if layout_name == "title":
        subtitle = spec.get("subtitle")
        if subtitle:
            _set_placeholder_idx(slide, 1, subtitle)

    elif layout_name == "bullets":
        bullets = spec.get("bullets", [])
        if bullets:
            _set_placeholder_idx(slide, 1, "\n".join(str(b) for b in bullets))

    elif layout_name == "section":
        subtitle = spec.get("subtitle") or spec.get("text")
        if subtitle:
            _set_placeholder_idx(slide, 1, subtitle)

    elif layout_name == "kpi_grid":
        kpis = spec.get("kpis", [])
        if kpis:
            _add_kpi_shapes(slide, kpis)

    elif layout_name in ("two_column", "comparison_layout"):
        # Note: ``comparison`` (bare) routes to the recipe earlier in the
        # dispatcher and never reaches this branch.  ``comparison_layout``
        # is the placeholder-based opt-in that does.
        left = spec.get("left") or spec.get("content_left")
        right = spec.get("right") or spec.get("content_right")
        if left:
            _set_placeholder_idx(slide, 1, left)
        if right:
            _set_placeholder_idx(slide, 2, right)


def _set_placeholder_idx(slide: Any, idx: int, text: str) -> None:
    """Set text on the placeholder with the given idx, if it exists."""
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == idx:
            ph.text = text
            return


def _set_transition(slide: Any, transition: str | None) -> None:
    if not transition:
        return
    key = transition.lower().replace("-", "_")
    member_name = _TRANSITION_NAMES.get(key)
    if member_name is None:
        raise ValueError(
            f"Unknown transition {transition!r}{_did_you_mean(key, _TRANSITION_NAMES)}. "
            f"Valid values: {sorted(_TRANSITION_NAMES)}"
        )
    from power_pptx.enum.presentation import MSO_TRANSITION_TYPE

    slide.transition.kind = getattr(MSO_TRANSITION_TYPE, member_name)


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
        raise ValueError(
            f"{where_slide}: 'shapes' must be a list of shape entries; got "
            f"{type(shape_specs).__name__!r}"
        )

    built: list[tuple[Mapping[str, Any], Any]] = []
    by_name: dict[str, Any] = {}
    for pos, entry in enumerate(shape_specs):
        where = f"{where_slide}.shapes[{pos}]"
        shape = _add_spec_shape(slide, entry, where=where)
        name = entry.get("name")
        if name is not None:
            if name in by_name:
                raise ValueError(
                    f"{where}: duplicate shape name {name!r} on {where_slide}. "
                    "Shape names must be unique within a slide so "
                    "'allow_overlap_with' can resolve them."
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
    if not isinstance(entry, Mapping):
        raise ValueError(
            f"{where}: each 'shapes' entry must be a mapping; got "
            f"{type(entry).__name__!r}"
        )

    unknown = set(entry) - _VALID_SHAPE_KEYS
    if unknown:
        raise ValueError(
            f"{where}: unknown shape keys "
            f"{_format_unknown(unknown, _VALID_SHAPE_KEYS)}. "
            f"Valid keys: {sorted(_VALID_SHAPE_KEYS)}"
        )

    name = entry.get("name")
    if name is not None and (not isinstance(name, str) or not name.strip()):
        raise ValueError(
            f"{where}: shape 'name' must be a non-empty string; got {name!r}"
        )

    missing = [k for k in _REQUIRED_SHAPE_KEYS if k not in entry]
    if missing:
        raise ValueError(
            f"{where}: shape entries require keys "
            f"{list(_REQUIRED_SHAPE_KEYS)}; missing {missing}"
        )
    box = tuple(
        _coerce_length(entry[k], f"{where}: {k!r}") for k in _REQUIRED_SHAPE_KEYS
    )

    kind = entry.get("shape", _TEXTBOX_SHAPE_NAME)
    if not isinstance(kind, str):
        raise ValueError(
            f"{where}: 'shape' must be a string naming an MSO_SHAPE member or "
            f"{_TEXTBOX_SHAPE_NAME!r}; got {type(kind).__name__!r}"
        )
    if kind.strip().lower() == _TEXTBOX_SHAPE_NAME:
        shape = slide.shapes.add_textbox(*box)
    else:
        shape = slide.shapes.add_shape(_resolve_autoshape(kind, where=where), *box)

    if name is not None:
        shape.name = name

    text = entry.get("text")
    if text is not None:
        shape.text_frame.text = str(text)

    # The three lint-intent scalars are plain pass-throughs: the shape
    # properties own their validation, so a bad value fails the same way
    # (and with the same exception type) whether it came from Python or
    # from a spec.  Only the location is added, so a rejected value in a
    # 40-slide spec is findable.
    for field in ("lint_group", "layer", "layer_above"):
        if field not in entry:
            continue
        try:
            setattr(shape, field, entry[field])
        except (TypeError, ValueError) as exc:
            raise type(exc)(f"{where}: {field!r}: {exc}") from exc

    return shape


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
    raise ValueError(
        f"{where}: unknown shape type {kind!r}"
        f"{_did_you_mean(member.lower(), candidates)}. Valid values are "
        f"{_TEXTBOX_SHAPE_NAME!r} or any MSO_SHAPE member name, e.g. "
        "'rectangle', 'rounded_rectangle', 'oval'."
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
    if isinstance(raw, str):
        refs: list[Any] = [raw]
    elif isinstance(raw, (list, tuple)):
        refs = list(raw)
    else:
        raise ValueError(
            f"{where}: 'allow_overlap_with' must be a shape name or a list of "
            f"shape names; got {type(raw).__name__!r}"
        )

    own_name = entry.get("name")
    targets = []
    for ref in refs:
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError(
                f"{where}: 'allow_overlap_with' entries must be non-empty "
                f"shape names; got {ref!r}"
            )
        if ref == own_name:
            raise ValueError(
                f"{where}: 'allow_overlap_with' names this shape itself "
                f"({ref!r}); an allowance always describes a pair of shapes."
            )
        target = by_name.get(ref)
        if target is None:
            elsewhere = sorted(set(deck_shape_names.get(ref, ())) - {slide_index})
            if elsewhere:
                raise ValueError(
                    f"{where}: 'allow_overlap_with' names shape {ref!r}, which "
                    f"is defined on slides {elsewhere} — an overlap allowance "
                    "is keyed on shape id, and shape ids are only unique "
                    "within a slide, so it can only name a shape on "
                    f"slides[{slide_index}]."
                )
            raise ValueError(
                f"{where}: 'allow_overlap_with' names unknown shape {ref!r}"
                f"{_did_you_mean(ref, by_name)} on slides[{slide_index}]. "
                f"Named shapes on that slide: {sorted(by_name)}"
            )
        targets.append(target)

    if targets:
        shape.allow_overlap_with(*targets)


def _add_kpi_shapes(slide: Any, kpis: list[dict[str, Any]]) -> None:
    """Add KPI card shapes to *slide* — label, value, and optional delta."""
    from power_pptx.enum.text import PP_ALIGN
    from power_pptx.util import Inches, Pt
    from power_pptx.dml.color import RGBColor

    prs_part = slide.part.package.presentation_part
    slide_w = prs_part.presentation.slide_width or Inches(10)

    n = len(kpis)
    if n == 0:
        return

    card_w = Inches(2.2)
    card_h = Inches(1.8)
    gap = Inches(0.2)
    total_w = n * card_w + (n - 1) * gap
    start_x = (slide_w - total_w) // 2
    top = Inches(2.5)

    for i, kpi in enumerate(kpis):
        left = start_x + i * (card_w + gap)
        label = str(kpi.get("label", ""))
        value = str(kpi.get("value", ""))
        delta = kpi.get("delta")

        # Value textbox (large, centered)
        tf_value = slide.shapes.add_textbox(left, top, card_w, Inches(1.0))
        tf = tf_value.text_frame
        tf.word_wrap = False
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = value
        run.font.size = Pt(32)
        run.font.bold = True
        p.alignment = PP_ALIGN.CENTER

        # Label textbox
        label_top = top + Inches(1.0)
        tf_label = slide.shapes.add_textbox(left, label_top, card_w, Inches(0.4))
        tf2 = tf_label.text_frame
        p2 = tf2.paragraphs[0]
        run2 = p2.add_run()
        run2.text = label
        run2.font.size = Pt(12)
        run2.font.color.rgb = RGBColor(0x60, 0x60, 0x60)
        p2.alignment = PP_ALIGN.CENTER

        # Delta textbox (optional)
        if delta is not None:
            delta_top = label_top + Inches(0.4)
            sign = "+" if float(delta) >= 0 else ""
            delta_str = f"{sign}{float(delta):.0%}"
            tf_delta = slide.shapes.add_textbox(left, delta_top, card_w, Inches(0.3))
            tf3 = tf_delta.text_frame
            p3 = tf3.paragraphs[0]
            run3 = p3.add_run()
            run3.text = delta_str
            run3.font.size = Pt(11)
            run3.font.color.rgb = (
                RGBColor(0x00, 0x8A, 0x00) if float(delta) >= 0 else RGBColor(0xCC, 0x00, 0x00)
            )
            p3.alignment = PP_ALIGN.CENTER


def _resolve_tokens(spec: Any) -> Any:
    """Build a :class:`DesignTokens` from a token spec, or ``None``.

    Accepts:

    * ``None`` — return ``None``.
    * A :class:`~power_pptx.design.tokens.DesignTokens` instance — returned as-is so
      callers can reuse a built token bag between imperative recipes and
      :func:`from_spec` without round-tripping through ``.to_dict()`` (no such
      method exists today).  See IMPROVEMENTS item 8.
    * ``{"preset": "modern_light", "overrides": {...}}`` — load preset
      and optionally layer overrides.
    * ``{"yaml": "brand.yml"}`` — load from a YAML file.
    * Any other mapping — treated as an inline ``DesignTokens.from_dict``
      payload.
    """
    if spec is None:
        return None
    from power_pptx.design.tokens import DesignTokens

    if isinstance(spec, DesignTokens):
        return spec
    if not isinstance(spec, Mapping):
        raise ValueError(
            f"'tokens' must be a mapping or DesignTokens instance; got "
            f"{type(spec).__name__!r}"
        )
    if "preset" in spec:
        tokens = DesignTokens.from_preset(spec["preset"])
        overrides = spec.get("overrides")
        if overrides:
            tokens = tokens.with_overrides(overrides)
        return tokens
    if "yaml" in spec:
        return DesignTokens.from_yaml(spec["yaml"])
    return DesignTokens.from_dict(spec)


# ---------------------------------------------------------------------------
# Slide size resolver
# ---------------------------------------------------------------------------

# Named aspect-ratio shorthands → (width_in, height_in) in inches.
# Matches PowerPoint's built-in "Page Setup" presets.
_SLIDE_SIZE_PRESETS: dict[str, tuple[float, float]] = {
    "16:9":         (13.333, 7.5),
    "widescreen":   (13.333, 7.5),
    "4:3":          (10.0, 7.5),
    "standard":     (10.0, 7.5),
    "16:10":        (13.333, 8.333),
    "a4":           (11.69, 8.27),
    "letter":       (11.0, 8.5),
}


def _coerce_length(value: Any, what: str) -> Any:
    """Return *value* as a :class:`~power_pptx.util.Length`.

    Bare numbers are inches — the convention the rest of the spec uses
    (``slide_size``, shape geometry) — so a spec never has to name a raw
    EMU integer.  *what* names the offending field in the error message.
    """
    from power_pptx.util import Inches, Length

    if isinstance(value, Length):
        return value
    # ``bool`` is a subclass of ``int``, so the ``isinstance(value,
    # (int, float))`` branch below would silently accept
    # ``slide_size=(True, False)`` as a 1" × 0" canvas.  Reject it
    # explicitly — matches the boolean-rejection rule that
    # ``power_pptx.util._coerce_emu`` applies for shape coordinates.
    if isinstance(value, bool):
        raise ValueError(
            f"{what} must be a number (inches) or Length; got bool: {value!r}"
        )
    if isinstance(value, (int, float)):
        return Inches(float(value))
    raise ValueError(
        f"{what} must be a number (inches) or Length; "
        f"got {type(value).__name__!r}: {value!r}"
    )


def _apply_slide_size(prs: Any, slide_size: Any) -> None:
    """Set ``prs.slide_width`` / ``prs.slide_height`` from a spec value.

    Accepts a named shorthand string, an ``(width, height)`` 2-tuple of
    inches, or a ``{"width": w, "height": h}`` mapping (inches or
    :class:`~power_pptx.util.Length`).  Numbers are interpreted as inches;
    pass an explicit ``Length`` to opt out.  See IMPROVEMENTS item 10.
    """
    from power_pptx.util import Inches

    def _to_emu(value: Any) -> Any:
        return _coerce_length(value, "slide_size dimension")

    if isinstance(slide_size, str):
        key = slide_size.lower()
        preset = _SLIDE_SIZE_PRESETS.get(key)
        if preset is None:
            raise ValueError(
                f"Unknown slide_size {slide_size!r}"
                f"{_did_you_mean(key, _SLIDE_SIZE_PRESETS)}. Valid shorthands: "
                f"{sorted(_SLIDE_SIZE_PRESETS)}, or pass (width, height)."
            )
        width_in, height_in = preset
        prs.slide_width = Inches(width_in)
        prs.slide_height = Inches(height_in)
        return
    if isinstance(slide_size, Mapping):
        if "width" not in slide_size or "height" not in slide_size:
            raise ValueError(
                "slide_size mapping must have 'width' and 'height' keys"
            )
        prs.slide_width = _to_emu(slide_size["width"])
        prs.slide_height = _to_emu(slide_size["height"])
        return
    if isinstance(slide_size, (list, tuple)) and len(slide_size) == 2:
        prs.slide_width = _to_emu(slide_size[0])
        prs.slide_height = _to_emu(slide_size[1])
        return
    raise ValueError(
        f"slide_size must be a string preset, (w, h) pair, or "
        f"{{'width', 'height'}} mapping; got {type(slide_size).__name__!r}"
    )


_INTERP_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")


def _interpolate(value: Any, vars_: Mapping[str, Any]) -> Any:
    """Recursively substitute ``{{name}}`` markers in any string within *value*.

    Walks dicts, lists, tuples, and strings.  ``{{name}}`` resolves to
    ``vars_['name']``; ``{{a.b.c}}`` walks dotted paths through nested
    mappings.  Unknown names raise :class:`KeyError` so a typo doesn't
    silently render as the literal placeholder.
    """
    if isinstance(value, str):
        def _sub(match: "re.Match[str]") -> str:
            key = match.group(1)
            parts = key.split(".")
            cur: Any = vars_
            for p in parts:
                if isinstance(cur, Mapping) and p in cur:
                    cur = cur[p]
                else:
                    raise KeyError(
                        f"interpolation variable {key!r} not found "
                        f"in vars={list(vars_)!r}"
                    )
            return str(cur)
        return _INTERP_RE.sub(_sub, value)
    if isinstance(value, dict):
        return {k: _interpolate(v, vars_) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v, vars_) for v in value]
    if isinstance(value, tuple):
        return tuple(_interpolate(v, vars_) for v in value)
    return value


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
