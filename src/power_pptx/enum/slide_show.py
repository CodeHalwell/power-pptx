"""Enumerations for slide-show ("Set Up Slide Show") settings."""

from __future__ import annotations

from power_pptx.enum.base import BaseXmlEnum


class PP_SLIDE_SHOW_TYPE(BaseXmlEnum):
    """Specifies how a slide show is presented.

    Alias: ``PP_SLIDE_SHOW``

    Example::

        from power_pptx.enum.slide_show import PP_SLIDE_SHOW_TYPE

        prs.slide_show.show_type = PP_SLIDE_SHOW_TYPE.KIOSK

    Each member corresponds to one of the three "Show type" radio buttons in
    PowerPoint's *Set Up Slide Show* dialog. The plain strings ``"speaker"``,
    ``"window"`` and ``"kiosk"`` are accepted wherever a member is.

    The ``xml_value`` of each member is the local-name of the corresponding
    child element of ``<p:showPr>`` (``"kiosk"`` for ``<p:kiosk/>``).
    """

    SPEAKER = (1, "present", "Presented by a speaker (full screen). The default.")
    """Presented by a speaker (full screen). The default."""

    WINDOW = (2, "browse", "Browsed by an individual (in a window).")
    """Browsed by an individual (in a window)."""

    KIOSK = (3, "kiosk", "Browsed at a kiosk (full screen, self-running).")
    """Browsed at a kiosk (full screen, self-running)."""


PP_SLIDE_SHOW = PP_SLIDE_SHOW_TYPE
