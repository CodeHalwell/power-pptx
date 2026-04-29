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
from typing import Any, Mapping, Optional

# ---------------------------------------------------------------------------
# Built-in layout aliases — map friendly names to the PowerPoint blank
# template's named layouts (from SlideLayouts collection).
# ---------------------------------------------------------------------------

_LAYOUT_ALIASES: dict[str, str] = {
    "title": "Title Slide",
    "bullets": "Title and Content",
    "section": "Section Header",
    "two_column": "Two Content",
    "comparison": "Comparison",
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

    ``tokens`` *(optional)*
        Either a preset name (``{"preset": "modern_light"}``), a path
        to a YAML file (``{"yaml": "brand.yml"}``), an inline token
        dict, or a mix of preset + ``overrides`` for per-deck tweaks.

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

    tokens = _resolve_tokens(spec.get("tokens"))

    for slide_spec in spec.get("slides", []):
        _add_slide(prs, slide_spec, tokens)

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
    {"slides", "lint", "template", "theme", "tokens", "vars"}
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


def _validate_spec_keys(spec: dict[str, Any]) -> None:
    unknown = set(spec) - _VALID_TOP_KEYS
    if unknown:
        raise ValueError(f"Unknown spec keys: {sorted(unknown)}")
    lint = spec.get("lint", "off")
    if lint not in _VALID_LINT_VALUES:
        raise ValueError(f"lint must be one of {sorted(_VALID_LINT_VALUES)!r}, got {lint!r}")
    if not isinstance(spec.get("slides", []), list):
        raise ValueError("'slides' must be a list")


def _resolve_layout(prs: Any, layout_name: str) -> Any:
    """Return the SlideLayout for *layout_name*.

    First tries the built-in alias table, then falls back to an exact
    case-insensitive match against the presentation's own layout names,
    then falls back to the Blank layout.
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

    # Last resort: first available layout (index 0 is always safe)
    blank = prs.slide_layouts.get_by_name("Blank")
    return blank if blank is not None else prs.slide_layouts[0]


def _add_slide(prs: Any, slide_spec: dict[str, Any], tokens: Any = None) -> Any:
    """Add a single slide to *prs* according to *slide_spec*.

    When the layout name matches a styled recipe (``kpi``, ``chart``,
    …), dispatch through :mod:`power_pptx.design.recipes`; otherwise
    fall back to the placeholder-based legacy path so existing decks
    keep working.
    """
    layout_name = (slide_spec.get("layout") or "blank").lower()

    if layout_name in _RECIPE_LAYOUTS:
        return _add_recipe_slide(prs, slide_spec, layout_name, tokens)

    layout = _resolve_layout(prs, layout_name)
    slide = prs.slides.add_slide(layout)

    _set_title(slide, slide_spec.get("title"))
    _set_subtitle_or_body(slide, slide_spec, layout_name)
    _set_transition(slide, slide_spec.get("transition"))

    return slide


_RECIPE_NEVER_KWARGS = frozenset({"layout"})


def _add_recipe_slide(
    prs: Any, slide_spec: dict[str, Any], layout_name: str, tokens: Any
) -> Any:
    """Dispatch to the recipe matching *layout_name*.

    Validates required keys, then forwards *every other* spec key as a
    keyword argument to the recipe.  The ``tokens`` and ``transition``
    arguments are threaded through automatically: spec-level tokens
    win when a slide-level ``tokens`` field isn't set.
    """
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

    elif layout_name in ("two_column", "comparison"):
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
            f"Unknown transition {transition!r}. "
            f"Valid values: {sorted(_TRANSITION_NAMES)}"
        )
    from power_pptx.enum.presentation import MSO_TRANSITION_TYPE

    slide.transition.kind = getattr(MSO_TRANSITION_TYPE, member_name)


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
    * ``{"preset": "modern_light", "overrides": {...}}`` — load preset
      and optionally layer overrides.
    * ``{"yaml": "brand.yml"}`` — load from a YAML file.
    * Any other mapping — treated as an inline ``DesignTokens.from_dict``
      payload.
    """
    if spec is None:
        return None
    from power_pptx.design.tokens import DesignTokens

    if not isinstance(spec, Mapping):
        raise ValueError(
            f"'tokens' must be a mapping; got {type(spec).__name__!r}"
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
