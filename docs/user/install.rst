.. _install:

Installing
==========

|pp| is hosted on PyPI under the distribution name ``power-pptx``::

    pip install power-pptx

The importable package is ``power_pptx``::

    from power_pptx import Presentation

The package name differs from upstream ``python-pptx`` (which installs
``pptx``) on purpose, so the two can be installed side by side. When moving
code across, replace ``pptx`` with ``power_pptx`` in imports.

Requirements
------------

* Python 3.9 or later.
* ``lxml``, ``Pillow``, ``XlsxWriter`` and ``typing_extensions``, which ``pip``
  installs for you. The minimum versions declared in ``pyproject.toml`` are
  the oldest the test suite passes on, and continuous integration runs the
  suite against exactly those.

Optional features
-----------------

Some features need extra packages or programs. Each raises a clear error
naming what is missing if you use it without them.

``pip install "power-pptx[html]"``
    HTML capture (``from_html``, HTML figures) through Playwright. A Chromium
    build is also needed: ``python -m playwright install chromium``.

``pip install "power-pptx[svg]"``
    Rasterising SVG pictures through CairoSVG, for the PNG fallback that older
    viewers display.

``pip install "power-pptx[embedding]"``
    Both of the above.

``pip install "power-pptx[review]"``
    PDF page rendering for ``power-pptx review`` through ``pypdfium2``.

Slide thumbnails and the review bundle run LibreOffice (``soffice``) and, for
multi-slide decks, Poppler (``pdftoppm``). Install those with your system's
package manager; see :ref:`render` for details.

Claude skill
------------

The package ships a Claude skill describing its public API. Install it into
your Claude skills directory with::

    python -m power_pptx.skill install
