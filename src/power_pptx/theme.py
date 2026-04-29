"""High-level theme API for power-pptx.

Provides read/write access to a presentation's color palette and font
scheme as stored in the theme part (``ppt/theme/theme1.xml``).

Typical read usage::

    from power_pptx.enum.dml import MSO_THEME_COLOR

    theme = prs.theme
    rgb = theme.colors[MSO_THEME_COLOR.ACCENT_1]   # RGBColor
    heading_font = theme.fonts.major                # e.g. "Calibri"
    body_font    = theme.fonts.minor                # e.g. "Calibri"

Theme writes (Phase 7)::

    theme.colors[MSO_THEME_COLOR.ACCENT_1] = RGBColor(0xFF, 0x66, 0x00)
    theme.fonts.major = "Inter"
    theme.fonts.minor = "Inter"

    # Bulk-apply the palette + fonts of another presentation's theme
    theme.apply(other_prs.theme)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from power_pptx.dml.color import RGBColor
from power_pptx.enum.dml import MSO_THEME_COLOR
from power_pptx.oxml.ns import qn
from power_pptx.oxml.xmlchemy import OxmlElement

if TYPE_CHECKING:
    from power_pptx.oxml.theme import CT_OfficeStyleSheet


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------


class Theme:
    """Read/write proxy for an Office theme (``<a:theme>`` element).

    Exposes the color palette via :attr:`colors` and the font pair via
    :attr:`fonts`.  All reads are non-mutating; assignments to
    :attr:`colors` slots and :attr:`fonts.major`/`.minor` modify the
    underlying ``<a:clrScheme>``/``<a:fontScheme>`` so the changes
    persist on save.
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

    @name.setter
    def name(self, value: str) -> None:
        self._theme_elm.set("name", value)

    def apply(
        self,
        other: Theme,
        *,
        rebind_shape_colors: bool = False,
        presentation=None,
    ) -> int:
        """Copy *other*'s color palette and font pair into this theme.

        Iterates every :class:`MSO_THEME_COLOR` slot present on *other*
        and writes the resolved RGB into the corresponding slot here,
        then mirrors the major/minor font typefaces.  Slots that *other*
        cannot resolve (e.g. unsupported color types) are left
        untouched on this theme.

        When ``rebind_shape_colors=True``, every shape in *presentation*
        whose hardcoded RGB matches a slot in the **old** (pre-swap)
        palette is rewritten to point at that theme slot instead — so
        re-skinning a deck no longer leaves orphan literal colors.
        Requires *presentation* to be supplied.

        Returns the number of shape-color rebinds applied (0 when
        ``rebind_shape_colors=False``).
        """
        if not isinstance(other, Theme):
            raise TypeError(f"apply() requires a Theme, got {type(other).__name__!r}")

        # Snapshot the pre-swap palette so we can rebind matching shapes
        # afterwards (rebinding by RGB only makes sense relative to the
        # palette that was active when those RGBs were authored).
        before_palette: dict[tuple[int, int, int], MSO_THEME_COLOR] = {}
        if rebind_shape_colors:
            if presentation is None:
                raise ValueError(
                    "rebind_shape_colors=True requires presentation= to be supplied"
                )
            for slot in MSO_THEME_COLOR:
                if not slot.xml_value:
                    continue
                rgb = self.colors.get(slot)
                if rgb is not None:
                    # First-write wins so aliases (BACKGROUND_1 vs LIGHT_1)
                    # don't shadow the canonical slot.
                    before_palette.setdefault(tuple(int(c) for c in rgb), slot)

        src_colors = other.colors
        dst_colors = self.colors
        for slot in MSO_THEME_COLOR:
            if not slot.xml_value:
                continue
            rgb = src_colors.get(slot)
            if rgb is not None:
                dst_colors[slot] = rgb

        if other.fonts.major:
            self.fonts.major = other.fonts.major
        if other.fonts.minor:
            self.fonts.minor = other.fonts.minor

        if not rebind_shape_colors:
            return 0
        return _rebind_shape_colors(presentation, before_palette)


def embed_font(
    presentation,
    font_path: str,
    *,
    typeface: str | None = None,
    weight: str = "regular",
) -> str:
    """Embed a TrueType/OpenType font into *presentation*.

    Bundles the font binary as a package part under ``/ppt/fonts/`` and
    registers it in the presentation's ``<p:embeddedFontLst>`` so it
    travels with the deck and is used by readers that respect embedded
    fonts (PowerPoint 2007+).

    Parameters
    ----------
    presentation
        The :class:`~power_pptx.presentation.Presentation` to embed into.
    font_path
        Filesystem path to a ``.ttf`` or ``.otf`` font file.
    typeface
        Family name to register. If omitted, the file's stem is used
        (e.g. ``Inter-Regular.ttf`` → ``"Inter-Regular"``).
    weight
        One of ``"regular"`` / ``"bold"`` / ``"italic"`` / ``"boldItalic"``.

    Returns the typeface that was registered.

    Notes
    -----
    The font is embedded *unobfuscated* using content type
    ``application/x-fontdata``. PowerPoint 2007+ accepts this form.
    The fully-obfuscated form (per ECMA-376 §15.2.13) is on the roadmap.
    Once an obfuscated path lands, calls written against this API will
    not need to change.
    """
    import os

    from power_pptx.opc.constants import CONTENT_TYPE as CT
    from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT
    from power_pptx.opc.package import Part

    valid_weights = ("regular", "bold", "italic", "boldItalic")
    if weight not in valid_weights:
        raise ValueError(
            f"weight must be one of {valid_weights}, got {weight!r}"
        )
    if not os.path.isfile(font_path):
        raise FileNotFoundError(f"font file not found: {font_path}")
    with open(font_path, "rb") as f:
        blob = f.read()
    if typeface is None:
        typeface = os.path.splitext(os.path.basename(font_path))[0]

    package = presentation.part.package
    # Existing fontdata files in /ppt/fonts/font<N>.fntdata; allocate next.
    partname = package.next_partname("/ppt/fonts/font%d.fntdata")
    font_part = Part(partname, CT.X_FONTDATA, package, blob)

    prs_part = package.presentation_part
    rId = prs_part.relate_to(font_part, RT.FONT)

    # Inject <p:embeddedFontLst> entry into presentation.xml.
    _add_embedded_font_entry(prs_part.presentation, typeface, weight, rId)
    return typeface


def _add_embedded_font_entry(presentation, typeface: str, weight: str, rId: str) -> None:
    """Add or extend a ``<p:embeddedFont>`` entry in presentation.xml.

    If an entry already exists for *typeface*, the *weight* slot
    (regular / bold / italic / boldItalic) is added to it.  Otherwise a
    new ``<p:embeddedFont>`` is appended to ``<p:embeddedFontLst>``,
    creating the list if needed.
    """
    pres_elm = presentation._element  # type: ignore[attr-defined]
    r_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

    embedded_lst = pres_elm.find(qn("p:embeddedFontLst"))
    if embedded_lst is None:
        embedded_lst = OxmlElement("p:embeddedFontLst")
        # Insert in CT_Presentation's schema-permitted position; appending
        # at the end is acceptable per the schema (only handlerLst, custDataLst
        # and extLst follow it; we don't generate those).
        pres_elm.append(embedded_lst)

    # Find existing entry for this typeface.
    existing = None
    for ef in embedded_lst.findall(qn("p:embeddedFont")):
        font = ef.find(qn("p:font"))
        if font is not None and font.get("typeface") == typeface:
            existing = ef
            break

    if existing is None:
        ef = OxmlElement("p:embeddedFont")
        font = OxmlElement("p:font")
        font.set("typeface", typeface)
        ef.append(font)
        embedded_lst.append(ef)
        existing = ef

    # Add weight slot if absent (PowerPoint disallows duplicates).
    slot_elm = existing.find(qn(f"p:{weight}"))
    if slot_elm is not None:
        slot_elm.set(f"{{{r_ns}}}id", rId)
    else:
        slot_elm = OxmlElement(f"p:{weight}")
        slot_elm.set(f"{{{r_ns}}}id", rId)
        # Per the schema the order is regular, bold, italic, boldItalic
        # *after* the <p:font> child. We append; PowerPoint accepts any
        # of these in any order in practice, but most readers also do.
        existing.append(slot_elm)


# Method on Theme for the user-facing API.
def _theme_embed_font(self, presentation, font_path, *, typeface=None, weight="regular"):
    """Embed *font_path* into *presentation* and register it.

    Convenience method on :class:`Theme`.  See :func:`embed_font` for
    the full description.
    """
    return embed_font(
        presentation, font_path, typeface=typeface, weight=weight
    )


Theme.embed_font = _theme_embed_font  # type: ignore[attr-defined]


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

    Keys are :class:`~power_pptx.enum.dml.MSO_THEME_COLOR` members.
    Values are :class:`~power_pptx.util.RGBColor` instances.

    Example::

        from power_pptx.enum.dml import MSO_THEME_COLOR

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

    def __setitem__(self, theme_color: MSO_THEME_COLOR, rgb: RGBColor) -> None:
        """Replace the *theme_color* slot's content with a single ``<a:srgbClr>`` *rgb*.

        Only slots that map directly into ``<a:clrScheme>`` (everything
        except ``HYPERLINK``/``FOLLOWED_HYPERLINK`` is fair game; those
        also have first-class slots and are supported as well) can be
        written.  Aliased slots (``BACKGROUND_1``, ``BACKGROUND_2``,
        ``TEXT_1``, ``TEXT_2``) write to their canonical
        ``lt1``/``lt2``/``dk1``/``dk2`` slot.

        Replaces any existing color child of the slot (``srgbClr``,
        ``sysClr``, ``schemeClr``, …) with a single ``<a:srgbClr>``,
        which is the simplest form PowerPoint understands and what we
        emit elsewhere in the library.
        """
        if not isinstance(theme_color, MSO_THEME_COLOR):
            raise TypeError(
                f"key must be an MSO_THEME_COLOR member, got {type(theme_color).__name__!r}"
            )
        if not isinstance(rgb, RGBColor):
            raise TypeError(
                f"value must be an RGBColor, got {type(rgb).__name__!r}"
            )
        if not theme_color.xml_value:
            raise ValueError(
                f"{theme_color!r} has no <a:clrScheme> slot and cannot be assigned"
            )

        slot_name = _CLR_SCHEME_ALIAS.get(theme_color.xml_value, theme_color.xml_value)
        clr_scheme = self._clr_scheme()
        if clr_scheme is None:
            raise ValueError(
                "theme has no <a:clrScheme>; cannot write to color slot"
            )

        slot_elm = clr_scheme.find(qn(f"a:{slot_name}"))
        if slot_elm is None:
            # Slot wasn't previously declared (rare but possible); add
            # it at the schema-defined position.  CT_ColorScheme
            # requires its children in a fixed sequence; appending at
            # the tail would invalidate the file when later slots
            # (e.g. hlink/folHlink) are already present.
            slot_elm = OxmlElement(f"a:{slot_name}")
            _insert_clr_scheme_slot(clr_scheme, slot_elm, slot_name)

        # Replace the slot's color child with a fresh <a:srgbClr val="...">
        for child in list(slot_elm):
            slot_elm.remove(child)
        srgb = OxmlElement("a:srgbClr")
        srgb.set("val", "{:02X}{:02X}{:02X}".format(*rgb))
        slot_elm.append(srgb)

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
        # Pseudo-slots like NOT_THEME_COLOR / MIXED carry an empty xml_value
        # and have no <a:clrScheme> child — they always resolve to None.
        if not theme_color.xml_value:
            return None

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
    """Read/write view of a theme's font scheme (major and minor fonts).

    Example::

        print(prs.theme.fonts.major)        # "Calibri"
        prs.theme.fonts.major = "Inter"     # heading font
        prs.theme.fonts.minor = "Inter"     # body font
    """

    def __init__(self, theme_elm: CT_OfficeStyleSheet):
        self._theme_elm = theme_elm

    @property
    def major(self) -> str | None:
        """The *major* (heading) Latin typeface name, or ``None`` if not set."""
        return self._latin_typeface("majorFont")

    @major.setter
    def major(self, typeface: str) -> None:
        self._set_latin_typeface("majorFont", typeface)

    @property
    def minor(self) -> str | None:
        """The *minor* (body) Latin typeface name, or ``None`` if not set."""
        return self._latin_typeface("minorFont")

    @minor.setter
    def minor(self, typeface: str) -> None:
        self._set_latin_typeface("minorFont", typeface)

    def _latin_typeface(self, font_kind: str) -> str | None:
        results = self._theme_elm.xpath(
            f"a:themeElements/a:fontScheme/a:{font_kind}/a:latin/@typeface"
        )
        return results[0] if results else None

    def _set_latin_typeface(self, font_kind: str, typeface: str) -> None:
        if not isinstance(typeface, str) or not typeface:
            raise TypeError("typeface must be a non-empty string")

        font_scheme = self._theme_elm.find(
            f"{qn('a:themeElements')}/{qn('a:fontScheme')}"
        )
        if font_scheme is None:
            raise ValueError(
                "theme has no <a:fontScheme>; cannot set typeface"
            )

        kind_elm = font_scheme.find(qn(f"a:{font_kind}"))
        if kind_elm is None:
            kind_elm = OxmlElement(f"a:{font_kind}")
            font_scheme.append(kind_elm)

        latin = kind_elm.find(qn("a:latin"))
        if latin is None:
            # <a:latin> must be the first child of <a:majorFont>/<a:minorFont>
            latin = OxmlElement("a:latin")
            kind_elm.insert(0, latin)
        latin.set("typeface", typeface)


# ---------------------------------------------------------------------------
# OOXML schema helpers
# ---------------------------------------------------------------------------

# CT_ColorScheme defines its children in this exact sequence; later slots
# (e.g. hlink) must follow earlier ones, and <a:extLst> is allowed last.
_CLR_SCHEME_SLOT_ORDER: tuple[str, ...] = (
    "dk1", "lt1", "dk2", "lt2",
    "accent1", "accent2", "accent3", "accent4", "accent5", "accent6",
    "hlink", "folHlink",
)


def _rebind_shape_colors(presentation, palette_map) -> int:
    """Walk every shape in *presentation* and rebind hardcoded literal RGB
    fills/lines/text colors to a theme slot when the literal matches.

    *palette_map* maps ``(r, g, b)`` ints to ``MSO_THEME_COLOR`` enum
    members — typically a snapshot of the old palette taken just before
    a :meth:`Theme.apply` swap.

    Implemented as a direct XML rewrite: any ``<a:srgbClr val="RRGGBB">``
    whose value matches a key in *palette_map* is replaced in-place with
    a ``<a:schemeClr val="<slot>"/>`` referencing the theme. The shape's
    other children (alpha, lumMod, etc.) are preserved.

    Returns the number of color references rebound.
    """
    if not palette_map:
        return 0

    # Build a hex-string lookup keyed by uppercase 6-char strings.
    hex_map: dict[str, str] = {}
    for (r, g, b), slot in palette_map.items():
        hex_str = "{:02X}{:02X}{:02X}".format(r, g, b)
        hex_map[hex_str] = slot.xml_value

    a_srgbClr = qn("a:srgbClr")
    a_schemeClr = qn("a:schemeClr")

    rebound = 0
    for slide in presentation.slides:
        for srgb in slide._element.iter(a_srgbClr):  # type: ignore[attr-defined]
            val = (srgb.get("val") or "").upper()
            if val not in hex_map:
                continue
            scheme = OxmlElement("a:schemeClr")
            scheme.set("val", hex_map[val])
            # Preserve alpha/lumMod/etc. modifier children.
            for child in list(srgb):
                scheme.append(child)
            srgb.tag = a_schemeClr
            srgb.attrib.clear()
            srgb.set("val", hex_map[val])
            for child in list(srgb):
                srgb.remove(child)
            for child in list(scheme):
                srgb.append(child)
            rebound += 1
    return rebound


def _insert_clr_scheme_slot(clr_scheme, slot_elm, slot_name: str) -> None:
    """Insert *slot_elm* into *clr_scheme* at the schema-defined position.

    Finds the first existing child whose schema position is *after*
    *slot_name* and inserts before it; otherwise appends at the tail
    (but before any trailing ``<a:extLst>`` if present).
    """
    try:
        target_idx = _CLR_SCHEME_SLOT_ORDER.index(slot_name)
    except ValueError:
        # Unknown slot name (shouldn't happen): append at end.
        clr_scheme.append(slot_elm)
        return

    for child in clr_scheme:
        local = child.tag.rsplit("}", 1)[-1]
        if local == "extLst":
            clr_scheme.insert(list(clr_scheme).index(child), slot_elm)
            return
        if local in _CLR_SCHEME_SLOT_ORDER:
            child_idx = _CLR_SCHEME_SLOT_ORDER.index(local)
            if child_idx > target_idx:
                clr_scheme.insert(list(clr_scheme).index(child), slot_elm)
                return
    clr_scheme.append(slot_elm)
