"""JSON-driven presentation authoring — the ``from_spec`` entry point.

This module exposes a single public function, :func:`from_spec`, that accepts a
plain Python dict (or anything that round-trips through ``json.loads``/
``json.dumps``) and returns a fully-populated :class:`~pptx.api.Presentation`.

The spec format is intentionally minimal for 1.2.0: it maps a handful of named
layouts to the standard layouts shipped with the default blank template, and
supports the most common per-slide fields (title, subtitle, bullets, kpis,
transition).  A full design-recipe library is deferred to Phase 9.

Example::

    from pptx.compose import from_spec

    prs = from_spec({
        "slides": [
            {
                "layout": "title",
                "title": "Q4 Review",
                "subtitle": "April 2026",
                "transition": "morph",
            },
            {
                "layout": "bullets",
                "title": "Customer impact",
                "bullets": [
                    "Two flagship customers shipped this week.",
                    "NPS improved 8 points QoQ.",
                ],
            },
            {
                "layout": "kpi_grid",
                "title": "Run-rate metrics",
                "kpis": [
                    {"label": "ARR", "value": "$182M", "delta": +0.27},
                    {"label": "NDR", "value": "131%", "delta": +0.03},
                ],
            },
        ],
        "lint": "raise",
    })
"""

from __future__ import annotations

from typing import Any

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


def from_spec(spec: dict[str, Any]) -> Any:
    """Return a :class:`~pptx.api.Presentation` built from the plain-dict *spec*.

    *spec* keys:

    ``slides`` *(required)*
        A list of slide-spec dicts.  Each slide dict must have at least a
        ``layout`` key.  Supported fields per layout:

        - **title** (all layouts): the slide title.
        - **subtitle** (*title* layout): the subtitle text.
        - **bullets** (*bullets* layout): list of bullet strings.
        - **kpis** (*kpi_grid* layout): list of dicts with ``label``,
          ``value``, and optional ``delta`` (float) keys.
        - **transition**: string name, e.g. ``"morph"`` or ``"fade"``.

    ``lint`` *(optional)*
        ``"off"`` (default), ``"warn"``, or ``"raise"``.  Controls whether the
        linter runs after construction and what happens when issues are found.

    ``template`` *(optional)*
        Path to a ``.pptx`` or ``.potx`` file to use as the base template
        instead of the default blank template.

    Raises:
        :class:`~pptx.exc.LintError`  when ``lint == "raise"`` and the linter
        finds errors.
        :class:`ValueError`  for unrecognised keys or invalid values.
    """
    if not isinstance(spec, dict):
        raise TypeError(f"spec must be a dict, got {type(spec).__name__!r}")

    _validate_spec_keys(spec)

    from pptx import Presentation

    template = spec.get("template")
    prs = Presentation(template) if template else Presentation()

    for slide_spec in spec.get("slides", []):
        _add_slide(prs, slide_spec)

    lint_mode = spec.get("lint", "off")
    if lint_mode != "off":
        _run_lint(prs, lint_mode)

    return prs


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_VALID_TOP_KEYS = frozenset({"slides", "lint", "template", "theme"})
_VALID_LINT_VALUES = frozenset({"off", "warn", "raise"})


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


def _add_slide(prs: Any, slide_spec: dict[str, Any]) -> Any:
    """Add a single slide to *prs* according to *slide_spec*."""
    layout_name = slide_spec.get("layout", "blank")
    layout = _resolve_layout(prs, layout_name)
    slide = prs.slides.add_slide(layout)

    _set_title(slide, slide_spec.get("title"))
    _set_subtitle_or_body(slide, slide_spec, layout_name.lower())
    _set_transition(slide, slide_spec.get("transition"))

    return slide


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
    from pptx.enum.presentation import MSO_TRANSITION_TYPE

    slide.transition.kind = getattr(MSO_TRANSITION_TYPE, member_name)


def _add_kpi_shapes(slide: Any, kpis: list[dict[str, Any]]) -> None:
    """Add KPI card shapes to *slide* — label, value, and optional delta."""
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor

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


def _run_lint(prs: Any, mode: str) -> None:
    """Run the deck-level linter according to *mode* (``"warn"`` or ``"raise"``)."""
    import logging

    from pptx.exc import LintError

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
