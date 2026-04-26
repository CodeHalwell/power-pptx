python-pptx-next
================

*python-pptx-next* is an actively-maintained fork of the excellent
`python-pptx`_ library by `Steve Canny`_, picking up where the upstream's
1.0.2 release left off. It is a Python library for creating, reading, and
updating PowerPoint (.pptx) files.

The import path is unchanged (``import pptx``) so it is a drop-in
replacement; only the distribution name on PyPI differs::

    pip install python-pptx-next

A typical use is generating a PowerPoint presentation from dynamic content
such as a database query, analytics output, or a JSON payload — perhaps in
response to an HTTP request — and downloading the generated PPTX file. It
runs on any Python-capable platform, including macOS and Linux, and does
not require Microsoft PowerPoint to be installed or licensed.

It can also be used to analyze PowerPoint files from a corpus, perhaps to
extract search-indexing text and images, or simply to automate the
production of a slide or two that would be tedious to get right by hand.

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

More information is available in the `python-pptx documentation`_ (note:
the hosted docs currently still reflect the upstream 1.0 API; new APIs
introduced in this fork are documented in their respective release notes
in ``HISTORY.rst`` until the docs site is rebuilt).

Browse `examples with screenshots`_ to get a quick idea what you can do.

.. _`python-pptx`:
   https://github.com/scanny/python-pptx
.. _`scanny/python-pptx`:
   https://github.com/scanny/python-pptx
.. _`Steve Canny`:
   https://github.com/scanny
.. _`python-pptx documentation`:
   https://python-pptx.readthedocs.org/en/latest/
.. _`examples with screenshots`:
   https://python-pptx.readthedocs.org/en/latest/user/quickstart.html
