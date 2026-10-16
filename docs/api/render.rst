.. _render_api:

Slide rendering
===============

.. currentmodule:: power_pptx.render

Each conversion uses an isolated workspace and LibreOffice profile. Reusing
an output directory returns only images from the current render; unrelated
files are preserved, and matching output filenames are replaced. Intermediate
files are removed after the call. Byte-returning calls do not write output
files. Both rendering strategies verify the number of generated slides.


.. autofunction:: render_slide_thumbnails

.. autofunction:: render_slide_thumbnail


Exceptions
----------

.. autoexception:: ThumbnailRendererUnavailable

.. autoexception:: ThumbnailRendererError
