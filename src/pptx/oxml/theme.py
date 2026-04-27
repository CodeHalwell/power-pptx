"""lxml custom element classes for theme-related XML elements."""

from __future__ import annotations

from pptx.oxml.xmlchemy import BaseOxmlElement, OptionalAttribute
from pptx.oxml.simpletypes import XsdString

from . import parse_from_template


class CT_OfficeStyleSheet(BaseOxmlElement):
    """``<a:theme>`` element, root of a theme part."""

    name: str = OptionalAttribute(  # pyright: ignore[reportAssignmentType]
        "name", XsdString, default=""
    )

    @classmethod
    def new_default(cls):
        """Return a new ``<a:theme>`` element containing default settings
        suitable for use with a notes master.
        """
        return parse_from_template("theme")

    @property
    def clrScheme(self):
        """The ``<a:clrScheme>`` element, or ``None`` if not present."""
        # BaseOxmlElement.xpath() pre-injects _nsmap so no namespaces kwarg needed
        results = self.xpath("a:themeElements/a:clrScheme")
        return results[0] if results else None

    @property
    def fontScheme(self):
        """The ``<a:fontScheme>`` element, or ``None`` if not present."""
        results = self.xpath("a:themeElements/a:fontScheme")
        return results[0] if results else None
