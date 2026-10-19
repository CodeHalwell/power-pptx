.. _render_api:

Slide rendering
===============

.. currentmodule:: power_pptx.render

Each conversion uses an isolated workspace and LibreOffice profile. Reusing
an output directory returns only images from the current render; unrelated
files are preserved, and matching output filenames are replaced. Intermediate
files are removed after the call. Byte-returning calls do not write output
files. Both rendering strategies verify the number of generated slides.

``font_dirs=`` points LibreOffice at extra font folders through a temporary
``fonts.conf`` used only by the ``soffice`` subprocess. Folders registered with
:func:`power_pptx.text.register_font_dir` or ``POWER_PPTX_FONT_DIRS`` are always
included.


.. autofunction:: render_slide_thumbnails

.. autofunction:: render_slide_thumbnail

.. autofunction:: render_slides


Exceptions
----------

.. autoexception:: ThumbnailRendererUnavailable

.. autoexception:: ThumbnailRendererError
