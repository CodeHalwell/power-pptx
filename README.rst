power-pptx
==========

*power-pptx* is an actively-maintained fork of the excellent
`python-pptx`_ library by `Steve Canny`_, picking up where the upstream's
1.0.2 release left off. It is a Python library for creating, reading, and
updating PowerPoint (.pptx) files.

Install from PyPI and import as ``power_pptx``::

    pip install power-pptx

    # then in Python
    from power_pptx import Presentation

The 2.0 release renamed the importable package from ``pptx`` to
``power_pptx`` so that ``power-pptx`` and the upstream ``python-pptx``
distribution can be installed side-by-side without colliding on the
top-level ``pptx`` module. To migrate code from ``power-pptx`` 1.x or
``python-pptx`` 1.0.2, replace ``pptx`` with ``power_pptx`` in your
imports.

A typical use is generating a PowerPoint presentation from dynamic content
such as a database query, analytics output, or a JSON payload — perhaps in
response to an HTTP request — and downloading the generated PPTX file. It
runs on any Python-capable platform, including macOS and Linux, and does
not require Microsoft PowerPoint to be installed or licensed.

It can also be used to analyze PowerPoint files from a corpus, perhaps to
extract search-indexing text and images, or simply to automate the
production of a slide or two that would be tedious to get right by hand.

What's new in the fork
----------------------

The fork extends the 1.0.2 surface with features the upstream roadmap did
not cover.  All additions are drop-in compatible — existing scripts keep
working — and every new feature ships with a round-trip regression test.

* **Visual effects** — outer shadow, glow, soft edges, blur, and reflection
  exposed as non-mutating proxies on every shape; alpha-tinted colors
  (``RGBColor.alpha``); gradient fills with ``linear`` / ``radial`` /
  ``rectangular`` / ``shape`` kinds and mutable stops; line ends, caps,
  joins, and compound lines.
* **Animations and transitions** — preset entrance, exit, and emphasis
  effects; motion-path presets (line, diagonal, circle, arc, zigzag,
  spiral); per-paragraph reveal; sequencing context manager;
  per-slide and deck-wide transitions including Morph and the other
  ``p14:`` extension transitions.
* **Layout linter** — ``slide.lint()`` reports text overflow, off-slide
  shapes, and undeclared collisions, with optional ``auto_fix()`` and
  save-time hooks.
* **JSON authoring** — ``power_pptx.compose.from_spec(...)`` builds a deck from
  a JSON-shaped spec; ``import_slide`` and ``apply_template`` cover
  cross-presentation operations.
* **Theme reader and writer** — read theme colors and fonts; write fresh
  ``<a:srgbClr>`` values into the clrScheme; apply a theme imported from
  a ``.potx``.
* **Picture effects** — transparency, brightness, contrast, recolor
  (grayscale, sepia, washout, duotone); native SVG embedding with PNG
  fallback.
* **Design-system layer** — ``DesignTokens`` (palette, typography,
  shadows, radii, spacings) loadable from a dict, YAML, or a ``.pptx``;
  a token-resolving ``shape.style`` facade; ``Grid`` / ``Stack`` layout
  primitives; opinionated slide recipes (``title``, ``bullet``, ``kpi``,
  ``quote``, ``image_hero``); a starter pack of three example token sets.
* **Charting** — chart palette presets independent of ``chart_style``;
  ten quick-layout presets; full per-series gradient and pattern fills.
* **3D primitives and SmartArt text substitution** — bevel and extrusion
  via ``shape.three_d``; ``slide.smart_art[i].set_text([...])``.
* **Slide thumbnails** — ``Presentation.render_thumbnails()`` shells out
  to LibreOffice for PNG previews.

See ``HISTORY.rst`` for the full changelog and ``ROADMAP.md`` for the
broader plan.

Attribution
-----------

This project is a fork of `scanny/python-pptx`_, originally created and
maintained by Steve Canny under the MIT License. The original copyright
notice is preserved in ``LICENSE``. Sincere thanks to Steve and to all the
upstream contributors whose work this project builds on.

The fork was created to continue development of features the upstream
roadmap did not cover (notably effects, transitions, animations, theme
customization, and a higher-level design layer). See ``HISTORY.rst`` for
the divergence point and changelog from there forward.

This project is **not** affiliated with or endorsed by Microsoft.
"PowerPoint" is a trademark of Microsoft Corporation; it is used here only
descriptively to identify the file format the library reads and writes.

Documentation
-------------

The Sphinx documentation lives under ``docs/`` and covers both the
inherited 1.0.2 API and every feature added by the fork.  Browse
`examples with screenshots`_ to get a quick idea what you can do.

.. _`python-pptx`:
   https://github.com/scanny/python-pptx
.. _`scanny/python-pptx`:
   https://github.com/scanny/python-pptx
.. _`Steve Canny`:
   https://github.com/scanny
.. _`examples with screenshots`:
   https://python-pptx.readthedocs.org/en/latest/user/quickstart.html
