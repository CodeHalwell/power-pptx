.. _common_pitfalls:

Common pitfalls
===============

A field guide to the rough edges in |pp| that authors — human and
LLM — most often hit.  Each entry has a short diagnosis and the
canonical workaround.

If you're generating decks dynamically, skim this page once.  Most of
these issues used to land example-deck authors in the source code,
not the docs.

Animations: experimental, broken in PowerPoint slideshow
--------------------------------------------------------

The :doc:`animation API <animation>` round-trips through the OOXML
schema, reads back via the introspection API, and renders correctly
when LibreOffice converts to PDF — but **animations do not currently
play in PowerPoint slideshow mode**.  Animated shapes sit at 10–15%
opacity for several seconds and snap to fully visible all at once.
Slides that combine entrance animations with a Morph transition can
additionally trigger PowerPoint's "Repair?" dialog on open.

**Workaround**: prefer slide :doc:`transitions <transitions>` over
animations.  Transitions round-trip and play correctly.  Track
progress in ``IMPROVEMENT_PLAN.md`` (item 1).

Color values: hex strings, RGBColor, or 3-tuples
------------------------------------------------

Every public color-accepting setter accepts the same "color-like"
inputs:

* :class:`~power_pptx.dml.color.RGBColor`,
* a 6-digit hex string with or without ``"#"`` (``"#06D6FE"`` or
  ``"06D6FE"``), or
* a 3-tuple of ``int`` in ``[0, 255]``.

So this works uniformly::

    shape.fill.fore_color.rgb = "#06D6FE"
    shape.fill.fore_color.rgb = (6, 214, 254)
    shape.fill.fore_color.rgb = RGBColor(6, 214, 254)

Older code may have built ``hex_rgb`` shims.  Those are no longer
needed; reach for :func:`power_pptx._color.coerce_color` if you
need the same coercion in your own helpers.

``RGBColor.from_string`` is deprecated; use ``from_hex``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:meth:`RGBColor.from_string <power_pptx.dml.color.RGBColor.from_string>`
emits a :class:`DeprecationWarning` and will be removed in a future
major release.  :meth:`RGBColor.from_hex
<power_pptx.dml.color.RGBColor.from_hex>` accepts the leading ``"#"``
naturally and is the supported path::

    RGBColor.from_hex("#3C2F80")   # works
    RGBColor.from_hex("3C2F80")    # works
    RGBColor.from_string("3C2F80") # works, but DeprecationWarning

Transitions: ``set_transition`` preserves per-slide overrides
-------------------------------------------------------------

``prs.set_transition(kind=…)`` skips slides that already have an
explicit per-slide transition kind, instead of silently overwriting
them.  The previous behaviour was a footgun — code like::

    slide_2.transition.kind = MSO_TRANSITION_TYPE.MORPH
    prs.set_transition(MSO_TRANSITION_TYPE.FADE)

…used to clobber slide 2's morph.  The new default leaves it alone.
To restore the old "force every slide" behaviour, pass ``force=True``::

    prs.set_transition(MSO_TRANSITION_TYPE.FADE, force=True)

The override-preservation only applies to ``kind``; ``duration``,
``advance_on_click``, and ``advance_after`` are still applied to
every slide regardless.

``apply_quick_layout`` accepts string legend positions
------------------------------------------------------

The ``legend_position`` key in a quick-layout spec accepts both the
:class:`~power_pptx.enum.chart.XL_LEGEND_POSITION` enum *and* its
lowercase string name::

    apply_quick_layout(
        chart,
        {"has_legend": True, "legend_position": "bottom"},
    )

Supported strings: ``"right"``, ``"left"``, ``"top"``, ``"bottom"``,
``"corner"``.  Unknown strings raise :class:`ValueError` listing the
supported names.

``auto_fix()`` now handles TextOverflow
---------------------------------------

When the linter detects :class:`~power_pptx.lint.TextOverflow`, calling
:meth:`SlideLintReport.auto_fix() <power_pptx.lint.SlideLintReport.auto_fix>`
flips the offending text frame's ``auto_size`` to
:attr:`MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
<power_pptx.enum.text.MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE>` so PowerPoint
shrinks the runs at render time.  Frames with an explicit auto-size
(``SHAPE_TO_FIT_TEXT`` or ``TEXT_TO_FIT_SHAPE``) are skipped — the
fixer respects designer choice.

This is a non-destructive fix: text content is preserved verbatim,
only the render-time sizing changes.  When generating decks from
runtime-supplied text, ``auto_fix()`` is the single biggest lever
for "lint-or-die" pipelines.

Recipes use the Blank layout
----------------------------

Slides returned by recipes (``title_slide``, ``kpi_slide``, …) sit on
the Blank layout, so ``slide.shapes.title is None`` and you must
address shapes by index when adding a footer or page number on top of
a recipe-generated slide.

The recipe-anchors API (``slide.title_shape`` / ``body_zone`` /
``footer_zone``) is tracked in ``IMPROVEMENT_PLAN.md`` item 9.

``chart.element`` does not give you the parent shape
----------------------------------------------------

:attr:`chart.shape <power_pptx.chart.chart.Chart.shape>` (added in
2.6) returns the :class:`~power_pptx.shapes.graphfrm.GraphicFrame` that
contains the chart, when the chart was reached via
``slide.shapes.add_chart(...).chart`` or ``slide.shapes[i].chart``.

Use this for animating, measuring, or styling the parent shape::

    chart = slide.shapes.add_chart(...).chart   # or `slide.shapes[i].chart`
    chart.shape.left  = Inches(0.5)
    chart.shape.width = Inches(9)

Don't reach for ``chart.element.getparent().getparent()`` — the
parent chain bottoms out earlier than you expect.

Card body text: use ``set_paragraph_defaults`` for branded fonts
----------------------------------------------------------------

Setting per-run ``font.name``, ``font.size``, ``font.color.rgb`` on
every paragraph in a card is the single most tedious thing about
generating styled content.  Use
:meth:`TextFrame.set_paragraph_defaults
<power_pptx.text.text.TextFrame.set_paragraph_defaults>` instead::

    tf.text = "first line\nsecond line"
    tf.set_paragraph_defaults(
        font_name="Inter",
        size=Pt(14),
        color="#222222",
    )

Properties already set on a run (e.g. an explicit ``bold=True``) are
preserved verbatim; only unset properties are filled in.

Pricing-card / badge text in shapes ≤ 0.5" tall
-----------------------------------------------

Short single-line strings (≤ 20 chars) get a tighter character-width
heuristic than longer text in the linter — but if you're targeting
a < 0.5"-tall pill or badge, set ``auto_size = TEXT_TO_FIT_SHAPE``
right after writing the text to avoid the :class:`TextOverflow` lint
entirely.

Designed-overlap groups
-----------------------

Cards-with-color-bands, badges-over-cards, and eyebrow-over-rectangle
headers used to surface as :class:`ShapeCollision` issues.  Two
mitigations now ship by default:

1. **Auto-suppression** of "small shape strictly contained inside a
   larger shape, drawn on top" — the canonical layered-design pattern
   no longer fires a collision.
2. **Batch tagging** via :meth:`Slide.lint_group_overlaps
   <power_pptx.slide.Slide.lint_group_overlaps>`::

       slide.lint_group_overlaps(card, accent_bar, label, value)

   Generates a unique-on-the-slide group name and tags every shape
   with it.  Returns the chosen name so you can reuse it later.

OffGridDrift tolerance is 0.05"
-------------------------------

The default off-grid drift tolerance was relaxed from 0.01" to 0.05"
(IMPROVEMENT_PLAN item 10).  An ``Inches(0.6)`` divider next to an
``Inches(0.62)`` eyebrow no longer lights up a warning on section
headers.  Genuine drift between 0.05" and 0.10" is still flagged.

Phantom shadows on auto shapes
------------------------------

A shape from ``shapes.add_shape()`` is born with a ``<p:style>``
containing ``<a:effectRef idx="2"/>`` — a reference into the theme's
effect-style list, which in most themes is a soft drop shadow.  Nothing
in the shape's own ``<a:spPr>`` mentions a shadow, so code that clears
``shadow.blur_radius`` / ``distance`` / ``color`` (or sets the
deprecated ``shadow.inherit = False``, which only writes an empty
``<a:effectLst/>``) looks like it turned the shadow off — and the
rendered card still has one.

**Workaround**: call :meth:`ShadowFormat.clear
<power_pptx.dml.effect.ShadowFormat.clear>`.  It drops the explicit
shadow elements *and* re-points the effect reference at the theme's
empty slot, leaving other effects (glow, soft edges, blur, reflection)
intact::

    card.shadow.clear()

Corner radius is a fraction, not a length
-----------------------------------------

``adjustments[0]`` on a rounded rectangle is a fraction of the shorter
side, so ``0.045`` is a different physical radius on every
differently-sized card — which is why hand-tuned values never quite
match across a deck.  Use :attr:`Shape.corner_radius
<power_pptx.shapes.autoshape.Shape.corner_radius>`, which converts to
and from a real length::

    card.corner_radius = Pt(6)

``fit_text`` needs the font to be installed
-------------------------------------------

:meth:`TextFrame.fit_text <power_pptx.text.text.TextFrame.fit_text>`
measures with real font metrics read from the machine running the
build.  When the requested family isn't installed — the normal case for
a brand display face inside a container or CI runner — measurement
falls back to Pillow's bundled default font, and the "text will not
overflow" guarantee degrades to a best guess.

Naming a family that isn't installed now emits a
:class:`~power_pptx.exc.FontMetricsWarning`.  Omitting ``font_family``
does not — no particular face was requested — while passing
``"Calibri"`` explicitly does.  Three ways to keep the guarantee, best
first::

    # 1. ship the metrics with the build
    tf.fit_text("Instrument Serif", max_size=44,
                font_file="fonts/InstrumentSerif-Regular.ttf")

    # 2. fail the build rather than ship an estimate
    tf.fit_text("Inter", max_size=24, strict=True)

    # 3. degrade deliberately to a family you know is present
    from power_pptx.text.fonts import font_is_installed
    family = "Inter" if font_is_installed("Inter") else "DejaVu Sans"
    tf.fit_text(family, max_size=24)

:func:`power_pptx.text.fonts.installed_font_families` lists what the
build machine can actually measure.  ``slide.lint()`` is unaffected —
its overflow check uses a font-agnostic character-width heuristic — so
the lint pass remains worth running when the metrics are approximate.
