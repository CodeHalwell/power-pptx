.. _theme:

Themes
======

Reading
-------

``Presentation.theme`` returns a :class:`power_pptx.theme.Theme` proxy.  The
six accent slots (and the dk1/dk2/lt1/lt2 background and hyperlink
slots) are addressable by ``MSO_THEME_COLOR``::

    from power_pptx.enum.dml import MSO_THEME_COLOR

    accent1 = prs.theme.colors[MSO_THEME_COLOR.ACCENT_1]    # → RGBColor
    major   = prs.theme.fonts.major                          # → str
    minor   = prs.theme.fonts.minor

Theme-aware color resolution
----------------------------

``power_pptx.inherit.resolve_color`` returns the effective |RGBColor| for any
``ColorFormat`` (or the lazy proxy on ``Font.color`` /
``LineFormat.color``).  Explicit RGB values are returned as-is, scheme
colors resolve through the theme, and unset colors return |None| without
mutating XML::

    from power_pptx.inherit import resolve_color

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

``apply(..., rebind_shape_colors=True, presentation=prs)`` also points every
shape colour that matched a slot of the old palette at that theme slot, so a
re-skinned deck keeps no stray literal colours.

Dark variant
------------

``prs.theme.to_dark_mode()`` swaps the dark and light background/text slots
(``dk1``/``lt1`` and ``dk2``/``lt2``) and then moves any accent whose contrast
against the background (``lt1``) is below 4.5:1 (``min_contrast=``) away from
it, lighter on a dark background, keeping its hue and saturation.  A pair already the dark way round is left alone, so calling
it on a dark theme, or twice, changes nothing more.
