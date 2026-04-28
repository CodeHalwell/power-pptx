power-pptx
==========

Release v\ |version| (:ref:`Installation <install>`)

.. include:: ../README.rst


Philosophy
----------

|pp| aims to broadly support the PowerPoint format (PPTX, PowerPoint 2007 and
later), but its primary commitment is to be *industrial-grade*, that is,
suitable for use in a commercial setting. Maintaining this robustness requires
a high engineering standard which includes a comprehensive two-level (e2e +
unit) testing regimen and a round-trip regression harness that locks in every
new feature.


Feature support
---------------

|pp| has the following capabilities:

* Round-trip any Open XML presentation (.pptx file) including all its elements
* Add slides, populate text placeholders, add images, textboxes, tables, auto
  shapes (polygons, flowchart shapes, etc.), and column / bar / line / pie
  charts at arbitrary positions and sizes
* Access and change core document properties such as title and subject
* Apply visual effects (shadows, glow, soft edges, blur, reflection) and
  alpha-tinted colors via non-mutating proxies on every shape
* Author entrance, exit, emphasis, and motion-path animations using a small
  preset library; apply per-slide and deck-wide transitions including Morph
* Read and write the active theme's color scheme and major/minor fonts;
  apply a theme imported from a ``.potx``
* Compose presentations from a JSON spec, import slides between decks, and
  apply a template to existing slides
* Run a layout linter on each slide to detect text overflow, off-slide
  shapes, and shape collisions; auto-fix nudges off-slide shapes back
  inside the slide bounds (text-overflow auto-fix is on the roadmap)
* Build with a design-token system, opinionated slide recipes, and ``Grid`` /
  ``Stack`` layout primitives
* Recolor charts from named palettes and toggle title / legend / axis-label
  / gridline visibility through quick-layout presets
* Render slide thumbnails through LibreOffice when one is on ``$PATH``

Even with all that, the PowerPoint document format is very rich and there are
still features |pp| does not support — see ``ROADMAP.md`` for what is
planned and what is intentionally out of scope.


User Guide
----------

.. toctree::
   :maxdepth: 1

   user/intro
   user/install
   user/quickstart
   user/presentations
   user/slides
   user/understanding-shapes
   user/autoshapes
   user/placeholders-understanding
   user/placeholders-using
   user/text
   user/charts
   user/table
   user/notes
   user/use-cases
   user/concepts
   user/effects
   user/animation
   user/transitions
   user/lint
   user/compose
   user/theme
   user/design
   user/charts-advanced
   user/render


Community Guide
---------------

.. toctree::
   :maxdepth: 1

   community/faq
   community/support
   community/updates


.. _api:

API Documentation
-----------------

.. toctree::
   :maxdepth: 2

   api/presentation
   api/slides
   api/shapes
   api/placeholders
   api/table
   api/chart-data
   api/chart
   api/text
   api/action
   api/dml
   api/image
   api/exc
   api/util
   api/animation
   api/lint
   api/compose
   api/theme
   api/design
   api/render
   api/smart_art
   api/enum/index


Contributor Guide
-----------------

.. toctree::
   :maxdepth: 1

   dev/runtests
   dev/xmlchemy
   dev/development_practices
   dev/philosophy
   dev/analysis/index
   dev/resources/index
