"""Slide-show settings — what PowerPoint's *Set Up Slide Show* dialog edits.

The settings live in the ``p:showPr`` element of the presentation-properties
part (``ppt/presProps.xml``), not in ``ppt/presentation.xml``. The public entry
point is :attr:`power_pptx.presentation.Presentation.slide_show`, which returns
a :class:`SlideShowSettings` object. A deck that has to run unattended on a
display looks like this::

    from power_pptx.enum.presentation import MSO_TRANSITION

    prs.slide_show.loop = True                 # start over after the last slide
    prs.slide_show.show_type = "kiosk"         # full screen, no click-to-advance
    prs.set_transition(MSO_TRANSITION.FADE, advance_after=5000)   # 5 s a slide

The advance time is a property of each slide's transition, not of the show.
Give the transition a kind as well (``CUT`` for no visible effect):
LibreOffice ignores the advance time of a slide whose transition has none.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from power_pptx.enum.slide_show import PP_SLIDE_SHOW, PP_SLIDE_SHOW_TYPE
from power_pptx.parts.presprops import PresentationPropertiesPart

if TYPE_CHECKING:
    from power_pptx.oxml.presprops import CT_ShowProperties
    from power_pptx.parts.presentation import PresentationPart

__all__ = ["PP_SLIDE_SHOW", "PP_SLIDE_SHOW_TYPE", "SlideShowSettings"]

# -- the words accepted for `show_type`, alongside the enum members. The XML
# -- element names ("present", "browse") are accepted too, so a value read out
# -- of a file by hand can be passed straight back in. --
_SHOW_TYPE_NAMES = {
    "speaker": PP_SLIDE_SHOW_TYPE.SPEAKER,
    "present": PP_SLIDE_SHOW_TYPE.SPEAKER,
    "window": PP_SLIDE_SHOW_TYPE.WINDOW,
    "browse": PP_SLIDE_SHOW_TYPE.WINDOW,
    "kiosk": PP_SLIDE_SHOW_TYPE.KIOSK,
}


def _coerce_show_type(value: object) -> PP_SLIDE_SHOW_TYPE:
    """Return the `PP_SLIDE_SHOW_TYPE` member named by `value`, a member or a string."""
    if isinstance(value, PP_SLIDE_SHOW_TYPE):
        return value
    if isinstance(value, str):
        member = _SHOW_TYPE_NAMES.get(value.strip().lower())
        if member is not None:
            return member
    raise ValueError(
        "show_type must be 'speaker', 'window', 'kiosk' or a PP_SLIDE_SHOW_TYPE member; "
        "got %r" % (value,)
    )


def _require_bool(name: str, value: object) -> bool:
    """Return `value`, raising |TypeError| unless it is exactly `True` or `False`.

    A truthy string such as ``"false"`` turning a setting on is the kind of bug
    that only shows up on the display wall, so nothing is coerced.
    """
    if not isinstance(value, bool):
        raise TypeError("%s must be True or False, got %r" % (name, value))
    return value


class SlideShowSettings:
    """How this presentation runs as a slide show.

    Accessed as :attr:`Presentation.slide_show
    <power_pptx.presentation.Presentation.slide_show>`; not intended to be
    constructed directly.

    Reading a setting never changes the deck: a presentation that has no
    slide-show settings (or no ``ppt/presProps.xml`` at all) reports what
    PowerPoint assumes for it. The XML is created the first time a setting is
    given a value other than the one it already has, and removed again once
    nothing but those assumed values is left. Everything else in
    ``ppt/presProps.xml`` — pen colour, colour history, extension lists — is
    left alone.

    ============================  =========================================
    Setting                       Value when the deck does not say
    ============================  =========================================
    :attr:`loop`                  ``False``
    :attr:`show_type`             ``PP_SLIDE_SHOW_TYPE.SPEAKER``
    :attr:`use_timings`           ``True``
    :attr:`show_narration`        ``True``
    :attr:`show_animation`        ``True``
    ============================  =========================================
    """

    def __init__(self, presentation_part: PresentationPart):
        self._presentation_part = presentation_part

    def __repr__(self) -> str:
        return (
            "<SlideShowSettings loop=%r show_type=%s use_timings=%r "
            "show_narration=%r show_animation=%r>"
            % (
                self.loop,
                self.show_type.name,
                self.use_timings,
                self.show_narration,
                self.show_animation,
            )
        )

    @property
    def loop(self) -> bool:
        """|True| if the show starts over after the last slide until Esc is pressed.

        Read/write. This is the *Loop continuously until 'Esc'* check box. On
        its own it only changes what happens after the final slide; for a show
        nobody is clicking through, also give the slides an advance time::

            prs.slide_show.loop = True
            prs.set_transition(MSO_TRANSITION.FADE, advance_after=5000)
        """
        showPr = self._showPr
        return False if showPr is None else showPr.loop

    @loop.setter
    def loop(self, value: bool) -> None:
        if _require_bool("loop", value) == self.loop:
            return
        self._get_or_add_showPr().loop = value
        self._prune()

    @property
    def show_type(self) -> PP_SLIDE_SHOW_TYPE:
        """How the show is presented, a member of :ref:`PpSlideShowType`. Read/write.

        ``SPEAKER``
            Presented by a speaker, full screen. The default.
        ``WINDOW``
            Browsed by an individual, in a window.
        ``KIOSK``
            Browsed at a kiosk: full screen, and a click does not advance the
            slide, so the slides need advance times or navigation buttons.
            PowerPoint always loops a kiosk show; set :attr:`loop` as well so
            that other viewers do the same.

        Assign a member or one of the strings ``"speaker"``, ``"window"`` and
        ``"kiosk"``; a member is always returned::

            prs.slide_show.show_type = "kiosk"
            prs.slide_show.show_type            # PP_SLIDE_SHOW_TYPE.KIOSK
        """
        showPr = self._showPr
        child = None if showPr is None else showPr.eg_showType
        if child is None:
            return PP_SLIDE_SHOW_TYPE.SPEAKER
        return PP_SLIDE_SHOW_TYPE.from_xml(child.tag.rpartition("}")[2])

    @show_type.setter
    def show_type(self, value: PP_SLIDE_SHOW_TYPE | str) -> None:
        show_type = _coerce_show_type(value)
        if show_type == self.show_type:
            return
        showPr = self._get_or_add_showPr()
        if show_type == PP_SLIDE_SHOW_TYPE.WINDOW:
            showPr.get_or_change_to_browse()
        elif show_type == PP_SLIDE_SHOW_TYPE.KIOSK:
            showPr.get_or_change_to_kiosk()
        else:
            # -- no show-type element means "presented by a speaker", so going
            # -- back to it takes the element away rather than adding one --
            showPr._remove_eg_showType()  # pyright: ignore[reportPrivateUsage]
        self._prune()

    @property
    def use_timings(self) -> bool:
        """|True| if slides advance on their own timings, where they have them.

        Read/write. |False| is the *Advance slides: Manually* option: every
        slide then waits for a click, whatever advance time it carries.
        """
        showPr = self._showPr
        return True if showPr is None else showPr.useTimings

    @use_timings.setter
    def use_timings(self, value: bool) -> None:
        if _require_bool("use_timings", value) == self.use_timings:
            return
        self._get_or_add_showPr().useTimings = value
        self._prune()

    @property
    def show_narration(self) -> bool:
        """|True| if recorded narration is played during the show. Read/write.

        |False| is the *Show without narration* check box.

        A presentation that has no slide-show settings plays its narration,
        so this reads |True| for a new deck. (The file format's own default
        for the attribute is the opposite, which is why PowerPoint always
        writes it out; so does this library, and changing another setting
        never silences a narrated deck.)
        """
        showPr = self._showPr
        if showPr is None:
            return True
        return showPr.showNarration is True

    @show_narration.setter
    def show_narration(self, value: bool) -> None:
        if _require_bool("show_narration", value) == self.show_narration:
            return
        self._get_or_add_showPr().showNarration = value
        self._prune()

    @property
    def show_animation(self) -> bool:
        """|True| if slide animations are played during the show. Read/write.

        |False| is the *Show without animation* check box.
        """
        showPr = self._showPr
        return True if showPr is None else showPr.showAnimation

    @show_animation.setter
    def show_animation(self, value: bool) -> None:
        if _require_bool("show_animation", value) == self.show_animation:
            return
        self._get_or_add_showPr().showAnimation = value
        self._prune()

    @property
    def _showPr(self) -> CT_ShowProperties | None:
        """The `p:showPr` element, or |None| when the deck has none. Never creates it."""
        part = PresentationPropertiesPart.find(self._presentation_part)
        return None if part is None else part.presentationPr.showPr

    def _get_or_add_showPr(self) -> CT_ShowProperties:
        """Return the `p:showPr` element, adding it (and its part) when absent."""
        presentationPr = PresentationPropertiesPart.get_or_add(
            self._presentation_part
        ).presentationPr
        showPr = presentationPr.showPr
        if showPr is None:
            showPr = presentationPr.get_or_add_showPr()
            # -- A bare `<p:showPr loop="1"/>` would switch narration off, the
            # -- schema default for the attribute being false. Start from what
            # -- the deck did before it had this element, as PowerPoint does. --
            showPr.showNarration = True
        return showPr

    def _prune(self) -> None:
        """Remove what a change has left without anything to say.

        A `p:showPr` holding only assumed values goes, and so does a
        presentation-properties part this library added if it is empty again.
        """
        part = PresentationPropertiesPart.find(self._presentation_part)
        if part is None:
            return
        presentationPr = part.presentationPr
        showPr = presentationPr.showPr
        if showPr is not None and showPr.says_nothing:
            presentationPr._remove_showPr()  # pyright: ignore[reportPrivateUsage]
        if part.added_on_demand and len(presentationPr) == 0:
            part.remove_from(self._presentation_part)
