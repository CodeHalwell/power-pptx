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

    paths = prs.render_thumbnails(out_dir="thumbs", width=1280)
    png   = slide.render_thumbnail(return_bytes=True)

Module-level entry points
-------------------------

::

    from pptx.render import (
        render_slide_thumbnails,
        render_slide_thumbnail,
    )

    paths = render_slide_thumbnails(
        prs,
        out_dir="thumbs",
        slide_indexes=[0, 3, 7],
        width=1280,
        soffice_bin="/opt/libreoffice/program/soffice",
        timeout=60,
    )

Set the ``POWER_PPTX_SOFFICE`` environment variable to override the
binary path globally; ``return_bytes=True`` returns each image as raw
PNG bytes instead of writing files.

Errors
------

Two exceptions surface failure modes:

* :class:`pptx.render.ThumbnailRendererUnavailable` — ``soffice`` is not
  on ``$PATH``.  The error message includes an install hint.
* :class:`pptx.render.ThumbnailRendererError` — conversion failed (the
  underlying ``soffice`` invocation produced no PNG, exited non-zero,
  or timed out).
