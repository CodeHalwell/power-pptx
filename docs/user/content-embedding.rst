.. _content-embedding:

Slides from styled HTML and SVG
===============================

For annotated HTML import with editable text/charts/tables, measured native
components, Plotly browser export, and the installed review command, see
:doc:`authoring-workflows`.

A good HTML design can supply the typography, spacing, palette and layout
for a presentation. Use native PowerPoint objects for content that needs
to remain editable; embed complex diagrams as SVG or browser captures.
For static browser fidelity, capture whole slide-sized HTML sections.

Install optional dependencies::

    pip install 'power-pptx[embedding]'
    python -m playwright install chromium

HTML sections into a deck
-------------------------

Give each slide a visible ``<section data-slide>`` with a fixed-size canvas
such as 1280 by 720 CSS pixels. Then::

    from pathlib import Path
    from power_pptx.compose import from_html

    prs = from_html(
        Path("deck.html"), selector="[data-slide]",
        viewport=(1280, 720), slide_size="16:9", device_scale_factor=2,
    )
    prs.save("deck.pptx")

Matching sections become PNG pictures in DOM order. Visible text is also
stored in speaker notes and picture alt text; the pictures are not editable
PowerPoint text. ``include_notes=False`` omits the notes. Captures wait for
image decoding and web fonts; ``wait_for_function="window.deckReady === true"``
can signal asynchronous application readiness. Container overflow raises by
default, with ``check_overflow=False`` available for intentional overflow.

Local HTML files are served temporarily on localhost. Keep relative styles,
fonts and images under the HTML file's directory. Inline markup should use
data URLs or explicit absolute resource URLs. A system Chromium can be
selected with ``browser_path=`` or ``POWER_PPTX_CHROMIUM``.

Capturing a single element
-------------------------

Use a CSS selector to capture one diagram/card into an existing slide::

    from power_pptx import BBox, add_html_figure

    picture = add_html_figure(
        slide, Path("diagram.html"), *BBox.from_inches(1, 1.5, 8, 4.5),
        selector="#architecture", fit="contain", omit_background=True,
    )
    picture.alt_text = "Clients send requests through the gateway to services."

``contain`` preserves proportions; ``cover`` crops to fill the box;
``stretch`` changes proportions. Capture density controls image resolution,
not physical size. ``full_page=True`` captures a long page as one image,
and cannot be combined with ``selector``. It does not paginate a webpage.
JSON ``figure`` slides and ``design.recipes.figure_slide`` accept the same
capture options through ``html_options``.

SVG and native reconstruction
-----------------------------

``add_svg_figure(slide, svg, ...)`` accepts markup, bytes, paths and binary
streams. The SVG stays vector in modern Office and ships with a PNG fallback
for other renderers. Identical SVG media are reused across occurrences.
Use self-contained SVG with a ``viewBox`` and embedded image resources;
``foreignObject``, scripts and complex web CSS are not portable to Office.
For those visuals capture the HTML in Chromium instead. An explicit
``png_fallback=`` can supply a high-resolution raster companion.

For an editable reconstruction, measure HTML bounds relative to each slide
section and map them to ``BBox`` using the actual deck dimensions. At a
1280px-wide canvas mapped to 13 1/3 inches, a CSS font of 64px maps to 48pt.
Rebuild text, cards, tables and charts with native APIs; preserve complex
artwork through embedded assets. Render and compare the saved deck against
the HTML reference. The linter cannot inspect text inside a captured picture.

See ``examples/html_embedding/`` for a faithful HTML deck and its explicit
native/hybrid companion, and the bundled skill reference
``content-embedding.md`` for the full agent workflow.

Modern design examples
----------------------

``examples/modern_gallery/`` contains eight complete decks / 32 slides across
native, hybrid, and captured workflows. They demonstrate editorial typography,
bento dashboards, dark charts, scientific plots, a Plotly cash-flow diagram,
glass interfaces, commerce layouts, SVG packaging, and procedural canvas art.
The builder checks schema and round-trip fidelity, renders every saved slide,
and creates contact sheets and an HTML preview gallery. Automated validation
supports the visual review; it does not certify appearance.

The bundled ``modern-slide-design.md`` skill reference explains visual direction,
native/browser typography differences, CSS-to-PowerPoint geometry, and the
all-slide review pass.
