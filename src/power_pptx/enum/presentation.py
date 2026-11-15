"""Enumerations used by presentation- and slide-level objects."""

from __future__ import annotations

from power_pptx.enum.base import BaseXmlEnum


class MSO_TRANSITION_TYPE(BaseXmlEnum):
    """Specifies the kind of transition between two slides.

    Alias: ``MSO_TRANSITION``

    Example::

        from power_pptx.enum.presentation import MSO_TRANSITION

        slide.transition.kind = MSO_TRANSITION.FADE

    Each member maps to a single child element of ``<p:transition>``. Most
    are the transitions of the ISO/IEC 29500 standard, in the ``p``
    namespace. Members drawn from a PowerPoint extension namespace are
    annotated as such: ``p14`` (PowerPoint 2010) and ``p159`` (PowerPoint
    2016, for Morph). Their XML is written inside ``mc:AlternateContent``
    with an ISO-pure fallback for applications that cannot render them.

    A transition of a kind with no member here (the ``p15`` kinds of
    PowerPoint 2013 such as Airplane, for instance) reads as |None| from
    :attr:`SlideTransition.kind` and is saved back exactly as it was read.

    The ``xml_value`` of each member is the local-name of the corresponding
    transition element (``"fade"`` for ``<p:fade/>``, ``"morph"`` for
    ``<p159:morph/>``, etc.). Consumers should not rely on the integer values
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

    MORPH = (21, "morph", "Morph transition (PowerPoint 2016+; p159 namespace).")
    """Morph transition (PowerPoint 2016+; p159 namespace)."""

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

    COMB = (27, "comb", "Comb transition.")
    """Comb transition."""


MSO_TRANSITION = MSO_TRANSITION_TYPE


# -- members whose XML element lives in the `p14:` (PowerPoint 2010+) namespace --
P14_TRANSITION_NAMES = frozenset(
    {
        "flythrough",
        "vortex",
        "switch",
        "gallery",
        "conveyor",
    }
)

# -- members whose XML element lives in the `p159:` (PowerPoint 2016+,
# -- http://schemas.microsoft.com/office/powerpoint/2015/09/main) namespace.
# -- Morph is NOT a p14 element: MS-PPTX defines it in the 2015/09 schema, and
# -- a `p14:morph` inside an `mc:Choice Requires="p14"` is an undefined element
# -- in a namespace every modern PowerPoint understands — the repair-dialog
# -- class of failure. --
P159_TRANSITION_NAMES = frozenset({"morph"})
