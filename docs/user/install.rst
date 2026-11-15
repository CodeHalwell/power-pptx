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

* Python 3.9 to 3.14.
* ``lxml`` (4.6.2 or later), ``Pillow`` (10.1 or later), ``XlsxWriter`` (1.3.7
  or later) and ``typing_extensions``, which ``pip`` installs for you. These
  minimum versions are the oldest the test suite passes on, and continuous
  integration runs the suite against exactly those.

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

Slide thumbnails and the review bundle run LibreOffice (``soffice``, or
``libreoffice``) to export the deck to PDF, and Poppler (``pdftoppm``) or
``pypdfium2`` to turn its pages into PNGs. Install LibreOffice and Poppler with
your system's package manager; see :ref:`render` for details.

Command-line tools
------------------

Installing the package also installs a ``power-pptx`` command:

``power-pptx lint DECK [DECK ...]``
    Runs the layout linter over saved decks, for CI. See :ref:`lint-cli`.

``power-pptx review INPUT [INPUT ...] --out-dir DIRECTORY``
    Renders and validates a deck (or HTML, JSON or YAML source) into a review
    bundle. See :doc:`authoring-workflows`.

``power-pptx --help`` lists them, and ``power-pptx lint --help`` and
``power-pptx review --help`` give each one's options.

Claude skill
------------

The package ships a Claude skill describing its public API. Install it into
your Claude skills directory with::

    python -m power_pptx.skill install

This copies ``SKILL.md`` and its ``references/`` folder to
``~/.claude/skills/power-pptx/``. ``power-pptx-skill install`` is the same
command. To install somewhere else, name the skill's own folder (the one that
will hold ``SKILL.md``, not the ``skills/`` folder around it)::

    python -m power_pptx.skill install --target /path/to/skills/power-pptx
    python -m power_pptx.skill install /path/to/skills/power-pptx    # the same

Running it again replaces a previous install of the skill. A target that is a
file, a symbolic link, or a folder holding anything other than this skill is
left alone and the command fails with exit status 1; ``--no-overwrite`` fails
the same way whenever the target exists. ``python -m power_pptx.skill path``
prints where the skill's files are inside the installed package.
