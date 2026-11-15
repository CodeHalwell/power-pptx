.. _render:

Slide thumbnails
================

|pp| can render slide thumbnails by shelling out to LibreOffice.
This is a convenience for review tooling, dashboards, and CI artifacts
— it does not require Microsoft PowerPoint or an Office license, but
``soffice`` must be on ``$PATH`` (or you can point at a custom binary).

Convenience methods
-------------------

::

    paths = prs.render_thumbnails(out_dir="thumbs")
    png   = slide.render_thumbnail(return_bytes=True)

Module-level entry points
-------------------------

::

    from power_pptx.render import (
        render_slide_thumbnails,
        render_slide_thumbnail,
    )

    paths = render_slide_thumbnails(
        prs,
        out_dir="thumbs",
        slide_indexes=[0, 3, 7],
        soffice_bin="/opt/libreoffice/program/soffice",
        timeout=60,
        dpi=150,
    )

``dpi=`` sets the resolution (default 150, so a 10in-wide slide is 1500px
wide) for every deck, one-slide decks included.
``render_slides(scale=...)`` is the same knob in PDF units: ``scale=1.0`` is
72 DPI and ``scale=2`` is 144.  There is no ``width=`` knob; pick the
``dpi=`` that gives the size you need or post-process with Pillow.

Slides are exported to PDF and split into pages with ``pdftoppm`` (Poppler)
or ``pypdfium2``.  LibreOffice's direct PNG filter, which ignores ``dpi=``
and usually writes only the first slide, is used only when neither is
installed or when ``strategy="png"`` asks for it.  Files are named
``_render_input-page-<n>.png``, ``<n>`` counting slides from 1 and
zero-padded to the width of the slide count; ``render_slides`` takes a
``name_template=`` for names of your own.

Set the ``POWER_PPTX_SOFFICE`` environment variable to override the
binary path globally; without it or ``soffice_bin=``, the first ``soffice``
on ``$PATH`` is used, or else the first ``libreoffice``.
``return_bytes=True`` returns each image as raw PNG bytes instead of
writing files.  ``timeout`` (seconds, default 120) applies to each external
process, the LibreOffice export and then the PDF split; one that overruns is
stopped along with every process it started.

LibreOffice draws text with the fonts it can find.  Folders registered with
:func:`power_pptx.text.register_font_dir` (or named in
``POWER_PPTX_FONT_DIRS``) are passed to it automatically, and
``font_dirs=[...]`` adds more for one call, so thumbnails use the faces the
deck was measured with instead of substitutes.

Hidden slides are rendered like any other, so ``slide_indexes=[n]`` always
means ``prs.slides[n]``. This needs LibreOffice 7.4 or later; an older
build renders the visible slides and raises ``ThumbnailRendererError`` for
a hidden one you ask for.

Errors
------

Two exceptions surface failure modes:

* :class:`power_pptx.render.ThumbnailRendererUnavailable` — no LibreOffice
  binary was found (neither ``soffice`` nor ``libreoffice`` on ``$PATH``, or
  the one named does not exist).  The error message includes an install hint.
* :class:`power_pptx.render.ThumbnailRendererError` — conversion failed (the
  underlying ``soffice`` invocation produced no PNG, exited non-zero,
  or timed out).
