.. _theme:

Themes
======

Reading
-------

``Presentation.theme`` returns a :class:`pptx.theme.Theme` proxy.  The
six accent slots (and the dk1/dk2/lt1/lt2 background and hyperlink
slots) are addressable by ``MSO_THEME_COLOR``::

    from pptx.enum.dml import MSO_THEME_COLOR

    accent1 = prs.theme.colors[MSO_THEME_COLOR.ACCENT_1]    # → RGBColor
    major   = prs.theme.fonts.major                          # → str
    minor   = prs.theme.fonts.minor

Theme-aware color resolution
----------------------------

``pptx.inherit.resolve_color`` returns the effective |RGBColor| for any
``ColorFormat`` (or the lazy proxy on ``Font.color`` /
``LineFormat.color``).  Explicit RGB values are returned as-is, scheme
colors resolve through the theme, and unset colors return |None| without
mutating XML::

    from pptx.inherit import resolve_color

    rgb = resolve_color(run.font.color, theme=prs.theme)

``brightness`` is applied by blending toward white or black, mirroring
PowerPoint's ``lumMod`` / ``lumOff`` model.

Writing
-------

Assignment through the same proxy writes a fresh ``<a:srgbClr>`` into
the requested slot (alias slots like ``BACKGROUND_1`` resolve to their
canonical ``lt1`` / ``lt2`` / ``dk1`` / ``dk2`` target)::

    prs.theme.colors[MSO_THEME_COLOR.ACCENT_1] = RGBColor(0x4F, 0x9D, 0xFF)
    prs.theme.fonts.major = "Inter"
    prs.theme.fonts.minor = "Inter"

    # Bulk-copy the palette and font pair from another deck's theme.
    prs.theme.apply(other_prs.theme)
