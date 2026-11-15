"""Exceptions used with python-pptx.

The base exception class is PythonPptxError.
"""

from __future__ import annotations

import zipfile


class PythonPptxError(Exception):
    """Generic error class."""


class PackageNotFoundError(PythonPptxError):
    """
    Raised when a package cannot be found at the specified path.
    """


class InvalidPackageError(PackageNotFoundError, zipfile.BadZipFile, KeyError):
    """Raised when a file is found but is not a package this library can read.

    That covers input that is not a zip archive at all (plain text, a legacy
    ``.ppt``, a password-protected file) and an archive that lacks something
    every package must have (``[Content_Types].xml``, ``_rels/.rels``, a main
    presentation part, a content type for one of its parts) or contains
    something none may (a DTD in an XML part).

    These faults used to surface as :class:`PackageNotFoundError`,
    :class:`zipfile.BadZipFile` or :class:`KeyError`, depending on the fault
    and on whether the package was given as a path or as a stream.  This
    class derives from all three, so existing ``except`` clauses keep
    working; new code can catch this one.
    """

    def __str__(self) -> str:
        # -- KeyError.__str__ would show the repr() of the message --
        return Exception.__str__(self)


class InvalidXmlError(PythonPptxError):
    """
    Raised when a value is encountered in the XML that is not valid according
    to the schema.
    """


class LintError(PythonPptxError):
    """Raised by :func:`~power_pptx.compose.from_spec` when ``lint="raise"`` and the
    linter detects errors in the generated presentation."""


class FontMetricsWarning(UserWarning):
    """Warned when text is measured against a font that isn't the requested one.

    :meth:`~power_pptx.text.text.TextFrame.fit_text` measures with real font
    metrics, so its "text will not overflow" guarantee only holds when the
    requested family is actually installed.  When it isn't, measurement falls
    back to Pillow's bundled default font and the chosen size becomes a best
    guess — usually close, but not something to trust for a display face.

    Pass ``strict=True`` to raise instead, or install the font (see
    :func:`power_pptx.text.fonts.font_is_installed`).
    """
