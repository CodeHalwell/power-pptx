"""Enumerations used by presentation- and slide-level objects."""

from __future__ import annotations

from pptx.enum.base import BaseXmlEnum


class MSO_TRANSITION_TYPE(BaseXmlEnum):
    """Specifies the kind of transition between two slides.

    Alias: ``MSO_TRANSITION``

    Example::

        from pptx.enum.presentation import MSO_TRANSITION

        slide.transition.kind = MSO_TRANSITION.FADE

    Each member maps to a single child element of ``<p:transition>``. Members
    drawn from the PowerPoint 2010+ extension namespace (``p14``) are
    annotated as such; their XML lives in the ``p14`` namespace and is
    silently preserved on round-trip even when the consuming application
    cannot render them.

    The ``xml_value`` of each member is the local-name of the corresponding
    transition element (``"fade"`` for ``<p:fade/>``, ``"morph"`` for
    ``<p14:morph/>``, etc.). Consumers should not rely on the integer values
    for anything other than enum-membership comparisons.
    """

    NONE = (0, "", "Empty transition (no animation between slides).")
    """Empty transition (no animation between slides)."""

    FADE = (1, "fade", "Fade transition.")
    """Fade transition."""

    PUSH = (2, "push", "Push transition.")
    """Push transition."""

    WIPE = (3, "wipe", "Wipe transition.")
    """Wipe transition."""

    SPLIT = (4, "split", "Split transition.")
    """Split transition."""

    RANDOM_BAR = (5, "randomBar", "Random Bar transition.")
    """Random Bar transition."""

    CIRCLE = (6, "circle", "Circle transition.")
    """Circle transition."""

    DISSOLVE = (7, "dissolve", "Dissolve transition.")
    """Dissolve transition."""

    CHECKER = (8, "checker", "Checkerboard transition.")
    """Checkerboard transition."""

    DIAMOND = (9, "diamond", "Diamond transition.")
    """Diamond transition."""

    PLUS = (10, "plus", "Plus transition.")
    """Plus transition."""

    WEDGE = (11, "wedge", "Wedge transition.")
    """Wedge transition."""

    ZOOM = (12, "zoom", "Zoom transition.")
    """Zoom transition."""

    NEWSFLASH = (13, "newsflash", "Newsflash transition.")
    """Newsflash transition."""

    COVER = (14, "cover", "Cover transition.")
    """Cover transition."""

    STRIPS = (15, "strips", "Strips transition.")
    """Strips transition."""

    CUT = (16, "cut", "Cut transition.")
    """Cut transition."""

    BLINDS = (17, "blinds", "Blinds transition.")
    """Blinds transition."""

    PULL = (18, "pull", "Pull transition.")
    """Pull transition."""

    RANDOM = (19, "random", "Random transition.")
    """Random transition."""

    WHEEL = (20, "wheel", "Wheel transition.")
    """Wheel transition."""

    MORPH = (21, "morph", "Morph transition (PowerPoint 2016+; p14 namespace).")
    """Morph transition (PowerPoint 2016+; p14 namespace)."""

    FLY_THROUGH = (22, "flythrough", "Fly Through transition (p14 namespace).")
    """Fly Through transition (p14 namespace)."""

    VORTEX = (23, "vortex", "Vortex transition (p14 namespace).")
    """Vortex transition (p14 namespace)."""

    SWITCH = (24, "switch", "Switch transition (p14 namespace).")
    """Switch transition (p14 namespace)."""

    GALLERY = (25, "gallery", "Gallery transition (p14 namespace).")
    """Gallery transition (p14 namespace)."""

    CONVEYOR = (26, "conveyor", "Conveyor transition (p14 namespace).")
    """Conveyor transition (p14 namespace)."""


MSO_TRANSITION = MSO_TRANSITION_TYPE


# -- members whose XML element lives in the `p14:` (PowerPoint 2010+) namespace --
P14_TRANSITION_NAMES = frozenset(
    {
        "morph",
        "flythrough",
        "vortex",
        "switch",
        "gallery",
        "conveyor",
    }
)
