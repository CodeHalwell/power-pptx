"""Exceptions used with python-pptx.

The base exception class is PythonPptxError.
"""

from __future__ import annotations


class PythonPptxError(Exception):
    """Generic error class."""


class PackageNotFoundError(PythonPptxError):
    """
    Raised when a package cannot be found at the specified path.
    """


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
