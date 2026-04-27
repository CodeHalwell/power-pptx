"""High-level read-only theme API for python-pptx.

Provides access to a presentation's color palette and font scheme as
stored in the theme part (``ppt/theme/theme1.xml``).

Typical usage::

    from pptx.enum.dml import MSO_THEME_COLOR

    theme = prs.theme
    rgb = theme.colors[MSO_THEME_COLOR.ACCENT_1]   # RGBColor
    heading_font = theme.fonts.major                # e.g. "Calibri"
    body_font    = theme.fonts.minor                # e.g. "Calibri"
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_THEME_COLOR
from pptx.oxml.ns import qn

if TYPE_CHECKING:
    from pptx.oxml.theme import CT_OfficeStyleSheet


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------


class Theme:
    """Read-only proxy for an Office theme (``<a:theme>`` element).

    Exposes the color palette via :attr:`colors` and the font pair via
    :attr:`fonts`.  All reads are non-mutating.
    """

    def __init__(self, theme_elm: CT_OfficeStyleSheet):
        self._theme_elm = theme_elm

    @property
    def colors(self) -> ThemeColors:
        """A :class:`ThemeColors` object providing color lookups by theme slot."""
        return ThemeColors(self._theme_elm)

    @property
    def fonts(self) -> ThemeFonts:
        """A :class:`ThemeFonts` object exposing ``major`` and ``minor`` font names."""
        return ThemeFonts(self._theme_elm)

    @property
    def name(self) -> str:
        """The theme name (``<a:theme name="…">``), or an empty string if absent."""
        return self._theme_elm.get("name", "")


# ---------------------------------------------------------------------------
# ThemeColors
# ---------------------------------------------------------------------------

# OOXML defines bg1/bg2/tx1/tx2 as logical aliases that always resolve to
# lt1/lt2/dk1/dk2 respectively in the <a:clrScheme> element.  The scheme
# never stores bg*/tx* child elements, so we must remap before the lookup.
_CLR_SCHEME_ALIAS: dict[str, str] = {
    "bg1": "lt1",
    "bg2": "lt2",
    "tx1": "dk1",
    "tx2": "dk2",
}


class ThemeColors:
    """Dict-like read-only view of a theme's color scheme.

    Keys are :class:`~pptx.enum.dml.MSO_THEME_COLOR` members.
    Values are :class:`~pptx.util.RGBColor` instances.

    Example::

        from pptx.enum.dml import MSO_THEME_COLOR

        rgb = prs.theme.colors[MSO_THEME_COLOR.ACCENT_1]
        print(rgb)   # RGBColor(0x4f, 0x81, 0xbd)
    """

    def __init__(self, theme_elm: CT_OfficeStyleSheet):
        self._theme_elm = theme_elm

    def __getitem__(self, theme_color: MSO_THEME_COLOR) -> RGBColor:
        if not isinstance(theme_color, MSO_THEME_COLOR):
            raise TypeError(
                f"key must be an MSO_THEME_COLOR member, got {type(theme_color).__name__!r}"
            )
        rgb = self._resolve(theme_color)
        if rgb is None:
            raise KeyError(theme_color)
        return rgb

    def get(self, theme_color: MSO_THEME_COLOR, default: RGBColor | None = None) -> RGBColor | None:
        """Return the |RGBColor| for *theme_color*, or *default* if not found."""
        if not isinstance(theme_color, MSO_THEME_COLOR):
            return default
        return self._resolve(theme_color) or default

    def __contains__(self, theme_color: object) -> bool:
        if not isinstance(theme_color, MSO_THEME_COLOR):
            return False
        return self._resolve(theme_color) is not None

    def _resolve(self, theme_color: MSO_THEME_COLOR) -> RGBColor | None:
        """Return the resolved :class:`RGBColor` for *theme_color*, or ``None``."""
        clr_scheme = self._clr_scheme()
        if clr_scheme is None:
            return None

        # bg1/bg2/tx1/tx2 are OOXML aliases; clrScheme only stores lt1/lt2/dk1/dk2.
        slot_name = _CLR_SCHEME_ALIAS.get(theme_color.xml_value, theme_color.xml_value)
        slot_elm = clr_scheme.find(qn(f"a:{slot_name}"))
        if slot_elm is None:
            return None

        return _rgb_from_slot(slot_elm)

    def _clr_scheme(self):
        """Return the ``<a:clrScheme>`` element, or ``None``."""
        # BaseOxmlElement.xpath() pre-loads _nsmap so no namespaces kwarg needed
        results = self._theme_elm.xpath("a:themeElements/a:clrScheme")
        return results[0] if results else None


def _rgb_from_slot(slot_elm) -> RGBColor | None:
    """Extract an RGB value from a ``<a:dk1>``, ``<a:accent1>`` etc. element.

    The slot element contains exactly one color child:
    * ``<a:srgbClr val="RRGGBB">`` → direct hex
    * ``<a:sysClr … lastClr="RRGGBB">`` → use *lastClr* (resolved system color)
    * Other child types are not yet supported and return ``None``.
    """
    srgb = slot_elm.find(qn("a:srgbClr"))
    if srgb is not None:
        val = srgb.get("val")
        if val and len(val) == 6:
            return RGBColor(int(val[0:2], 16), int(val[2:4], 16), int(val[4:6], 16))

    sys_clr = slot_elm.find(qn("a:sysClr"))
    if sys_clr is not None:
        last = sys_clr.get("lastClr")
        if last and len(last) == 6:
            return RGBColor(int(last[0:2], 16), int(last[2:4], 16), int(last[4:6], 16))

    return None


# ---------------------------------------------------------------------------
# ThemeFonts
# ---------------------------------------------------------------------------


class ThemeFonts:
    """Read-only view of a theme's font scheme (major and minor fonts).

    Example::

        print(prs.theme.fonts.major)   # "Calibri"
        print(prs.theme.fonts.minor)   # "Calibri"
    """

    def __init__(self, theme_elm: CT_OfficeStyleSheet):
        self._theme_elm = theme_elm

    @property
    def major(self) -> str | None:
        """The *major* (heading) Latin typeface name, or ``None`` if not set."""
        return self._latin_typeface("majorFont")

    @property
    def minor(self) -> str | None:
        """The *minor* (body) Latin typeface name, or ``None`` if not set."""
        return self._latin_typeface("minorFont")

    def _latin_typeface(self, font_kind: str) -> str | None:
        results = self._theme_elm.xpath(
            f"a:themeElements/a:fontScheme/a:{font_kind}/a:latin/@typeface"
        )
        return results[0] if results else None
