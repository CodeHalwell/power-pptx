"""Main presentation object."""

from __future__ import annotations

import logging
import os
from typing import IO, TYPE_CHECKING, Literal, cast

from power_pptx.section import Sections
from power_pptx.shared import PartElementProxy
from power_pptx.slide import SlideMasters, Slides
from power_pptx.util import lazyproperty

if TYPE_CHECKING:
    from power_pptx.enum.presentation import MSO_TRANSITION_TYPE
    from power_pptx.lint import LintIssue
    from power_pptx.oxml.presentation import CT_Presentation, CT_SlideId
    from power_pptx.parts.presentation import PresentationPart
    from power_pptx.slide import NotesMaster, Slide, SlideLayouts
    from power_pptx.util import Length

logger = logging.getLogger(__name__)

# Sentinel used by `set_transition` so callers can distinguish "leave the
# existing value alone" from "explicitly clear it" (which is `None`).
_UNSET = object()

LintOnSaveMode = Literal["off", "warn", "raise"]

#: Accepted values for :attr:`Presentation.lint_on_save`.
_LINT_ON_SAVE_MODES: tuple[LintOnSaveMode, ...] = ("off", "warn", "raise")


class Presentation(PartElementProxy):
    """PresentationML (PML) presentation.

    Not intended to be constructed directly. Use :func:`power_pptx.Presentation` to open or
    create a presentation.
    """

    _element: CT_Presentation
    part: PresentationPart  # pyright: ignore[reportIncompatibleMethodOverride]

    # ---- `lint_on_save` is a plain instance attribute, not part of the XML.
    # ---- `PresentationPart.presentation` is a `lazyproperty`, so a package
    # ---- hands back this same proxy object every time and the setting sticks
    # ---- for the life of the package. It is deliberately *not* persisted.
    _lint_on_save: LintOnSaveMode = "off"

    @property
    def core_properties(self):
        """|CoreProperties| instance for this presentation.

        Provides read/write access to the Dublin Core document properties for the presentation.
        """
        return self.part.core_properties

    @property
    def notes_master(self) -> NotesMaster:
        """Instance of |NotesMaster| for this presentation.

        If the presentation does not have a notes master, one is created from a default template
        and returned. The same single instance is returned on each call.
        """
        return self.part.notes_master

    @property
    def lint_on_save(self) -> LintOnSaveMode:
        """What :meth:`save` does about error-severity lint issues. Read/write.

        One of:

        ``"off"`` *(default)*
            No checks are run at save time; :meth:`save` does no lint work at
            all.  This is the default so that existing code keeps working
            unchanged.

        ``"warn"``
            Every slide is linted before the file is written and each
            error-severity issue is logged (stdlib :mod:`logging`, logger
            ``"power_pptx.presentation"``).  The file is still written.

        ``"raise"``
            Every slide is linted *before* the file is written and
            :class:`~power_pptx.exc.LintError` is raised if any slide has an
            error-severity issue, so a failing deck never reaches disk.

        Example::

            prs.lint_on_save = "raise"
            prs.save("deck.pptx")   # raises LintError if a shape is off-slide

        This is a setting on the in-memory |Presentation| object; it is not
        stored in the ``.pptx`` file, so a deck re-opened from disk starts
        out at ``"off"`` again.

        Raises:
            ValueError: if assigned anything other than ``"off"``, ``"warn"``,
                or ``"raise"``.
        """
        return self._lint_on_save

    @lint_on_save.setter
    def lint_on_save(self, value: LintOnSaveMode) -> None:
        if value not in _LINT_ON_SAVE_MODES:
            raise ValueError(
                f"lint_on_save must be one of 'off', 'warn', or 'raise', got {value!r}"
            )
        # ---- the `not in` check above narrows `value` to `LintOnSaveMode` ----
        self._lint_on_save = value

    def save(self, file: str | os.PathLike[str] | IO[bytes]):
        """Writes this presentation to `file`.

        `file` can be either a file-path or a file-like object open for writing bytes.

        The extension of a file-path decides what kind of file is written: ``.potx`` saves a
        template, ``.ppsx`` a slide show, and anything else an ordinary presentation. A
        file-like object always receives an ordinary presentation. This holds whatever the
        deck was opened from, so ``Presentation("brand.potx")`` saved as ``"deck.pptx"`` is a
        presentation, not a template with the wrong extension.

        Saving to a file-path is all-or-nothing. The package is written to a temporary file in
        the same directory and moved into place once it is complete, so if anything fails
        along the way an existing file at that path is left exactly as it was.

        When :attr:`lint_on_save` is ``"warn"`` or ``"raise"``, every slide is
        linted before anything is written; in ``"raise"`` mode a
        :class:`~power_pptx.exc.LintError` propagates and no file is written.
        """
        # ---- the default ("off") does no lint work whatsoever ----
        if self._lint_on_save != "off":
            _lint_before_save(self, self._lint_on_save)
        self.part.save(file)

    def render_thumbnails(self, **kwargs):
        """Render PNG thumbnails for every slide via headless LibreOffice.

        Thin wrapper around :func:`power_pptx.render.render_slide_thumbnails` that
        forwards `out_dir`, `slide_indexes`, `soffice_bin`, `timeout`, and
        `return_bytes` keyword arguments.  Requires ``soffice`` (LibreOffice)
        on PATH; raises ``ThumbnailRendererUnavailable`` otherwise.
        """
        from power_pptx.render import render_slide_thumbnails

        return render_slide_thumbnails(self, **kwargs)

    @property
    def slide_height(self) -> Length | None:
        """Height of slides in this presentation, in English Metric Units (EMU).

        Returns |None| if no slide width is defined. Read/write.
        """
        sldSz = self._element.sldSz
        if sldSz is None:
            return None
        return sldSz.cy

    @slide_height.setter
    def slide_height(self, height: Length):
        sldSz = self._element.get_or_add_sldSz()
        sldSz.cy = height

    @property
    def slide_layouts(self) -> SlideLayouts:
        """|SlideLayouts| collection belonging to the first |SlideMaster| of this presentation.

        A presentation can have more than one slide master and each master will have its own set
        of layouts. This property is a convenience for the common case where the presentation has
        only a single slide master.
        """
        return self.slide_masters[0].slide_layouts

    @property
    def slide_master(self):
        """
        First |SlideMaster| object belonging to this presentation. Typically,
        presentations have only a single slide master. This property provides
        simpler access in that common case.
        """
        return self.slide_masters[0]

    @lazyproperty
    def slide_masters(self) -> SlideMasters:
        """|SlideMasters| collection of slide-masters belonging to this presentation."""
        return SlideMasters(self._element.get_or_add_sldMasterIdLst(), self)

    @property
    def slide_width(self):
        """
        Width of slides in this presentation, in English Metric Units (EMU).
        Returns |None| if no slide width is defined. Read/write.
        """
        sldSz = self._element.sldSz
        if sldSz is None:
            return None
        return sldSz.cx

    @slide_width.setter
    def slide_width(self, width: Length):
        sldSz = self._element.get_or_add_sldSz()
        sldSz.cx = width

    @property
    def theme(self):
        """Return a |Theme| object providing read-only access to the color palette and fonts.

        Navigates to the theme part of the first slide master, which is where
        Office applications store the active theme.  Returns ``None`` if no
        slide master (and therefore no theme) is present.

        Example::

            from power_pptx.enum.dml import MSO_THEME_COLOR

            rgb   = prs.theme.colors[MSO_THEME_COLOR.ACCENT_1]
            major = prs.theme.fonts.major   # e.g. "Calibri"
        """
        return self.slide_master.part.theme

    @lazyproperty
    def slides(self):
        """|Slides| object containing the slides in this presentation."""
        sldIdLst = self._element.get_or_add_sldIdLst()
        self.part.rename_slide_parts([cast("CT_SlideId", sldId).rId for sldId in sldIdLst])
        return Slides(sldIdLst, self)

    @property
    def sections(self) -> Sections:
        """|Sections| collection of named slide groupings in this presentation.

        Sections appear in PowerPoint's outline / slide-sorter pane and are
        stored as a PowerPoint-2010 extension on the presentation part. The
        returned collection supports ``len()``, indexed access, iteration,
        ``.add(name, start_slide_index=None)``, and ``.remove(section)``.

        Reading this property never modifies the deck; the extension
        container is created only when the first section is added.
        """
        return Sections(self._element, self)

    @property
    def slide_show(self):
        """:class:`~power_pptx.slide_show.SlideShowSettings` for this presentation.

        The settings in PowerPoint's *Set Up Slide Show* dialog: whether the
        show loops, how it is presented, and whether timings, narration and
        animation are used. A deck that has to run by itself on a display::

            from power_pptx.enum.presentation import MSO_TRANSITION

            prs.slide_show.loop = True                # start over after the last slide
            prs.slide_show.show_type = "kiosk"        # full screen, self-running
            prs.set_transition(MSO_TRANSITION.FADE, advance_after=5000)   # 5 s a slide

        The settings are stored in ``ppt/presProps.xml`` rather than
        ``ppt/presentation.xml``. Reading them never modifies the deck; the
        ``<p:showPr>`` element (and the part, for a deck written by a tool
        that leaves it out) is created only when a setting is changed, and is
        removed again when every setting is back at its default.
        """
        from power_pptx.slide_show import SlideShowSettings

        return SlideShowSettings(self.part)

    def set_slide_size(self, width: float, height: float, *, fit: bool = False):
        """Set the slide width and height together; return the size that was set.

        `width` and `height` are lengths, as for :attr:`slide_width` and
        :attr:`slide_height`, and may be the float result of arithmetic on
        lengths. Both are checked before either is written, so a size that is
        refused leaves the presentation as it was.

        A slide can be no smaller than 1 inch and no larger than 56 inches in
        either direction (:data:`power_pptx.util.MIN_SLIDE_SIZE` and
        :data:`~power_pptx.util.MAX_SLIDE_SIZE`). A size outside those limits
        raises |ValueError| unless `fit` is |True|, in which case it is scaled
        to the nearest size in the same proportions that is inside them (see
        :func:`power_pptx.util.fit_slide_size`).

        The return value is a :class:`~power_pptx.util.SlideSize`, a
        ``(width, height, scale)`` named tuple. ``scale`` is what the
        requested size was multiplied by — ``1.0`` unless `fit` changed it —
        and is the factor to apply to coordinates worked out for the size
        asked for::

            from power_pptx.util import Inches

            # a 7680 x 1080 px video wall, at 96 px to the inch: 80" x 11.25"
            size = prs.set_slide_size(Inches(7680 / 96), Inches(1080 / 96), fit=True)
            size.width.inches, size.height.inches, size.scale    # (56.0, 7.875, 0.7)

            px = size.scale * Inches(1) / 96          # one wall pixel, on the slide
            slide.shapes.add_textbox(1920 * px, 120 * px, 3840 * px, 400 * px)

        Shapes, layouts and masters already in the presentation are not moved
        or resized.
        """
        from power_pptx.oxml.simpletypes import ST_SlideSizeCoordinate
        from power_pptx.util import Emu, SlideSize, _coerce_emu, fit_slide_size

        if fit:
            size = fit_slide_size(width, height)
        else:
            dimensions: list[Emu] = []
            for what, value in (("slide width", width), ("slide height", height)):
                emu = _coerce_emu(value)
                if emu is None:
                    raise TypeError("%s is required, got None" % what)
                try:
                    ST_SlideSizeCoordinate.validate(emu, what)
                except ValueError as exc:
                    raise ValueError(
                        "%s; pass fit=True to scale the size to fit, keeping its proportions" % exc
                    ) from None
                dimensions.append(Emu(emu))
            size = SlideSize(dimensions[0], dimensions[1], 1.0)

        sldSz = self._element.get_or_add_sldSz()
        sldSz.cx, sldSz.cy = size.width, size.height
        return size

    def import_slide(
        self,
        source_slide: Slide,
        merge_master: Literal["dedupe", "clone"] = "dedupe",
    ) -> Slide:
        """Copy *source_slide* into this presentation and return the new |Slide|.

        The imported slide is appended after any existing slides.

        Parameters
        ----------
        source_slide:
            A |Slide| object from any |Presentation| instance, including this one.
        merge_master:
            Controls how the slide master is handled:

            ``'dedupe'`` *(default)*
                Reuse an existing master in this presentation if its XML is
                identical to the source master's XML (normalised byte-for-byte
                compare).  Clone the master otherwise.

            ``'clone'``
                Always clone the source master, even if an identical one
                already exists.

            Any other value raises :class:`ValueError`.

        Only *source_slide* is imported.  Pictures and media the
        presentation already holds are reused rather than copied again.  A
        "jump to slide" link on the slide (``click_action.target_slide``) is
        kept when its target is already in this presentation — a same-deck
        import, or a slide imported earlier into this object — and removed
        otherwise; the linked slide itself is never brought along.

        Returns
        -------
        Slide
            The newly imported slide.

        Example::

            src = power_pptx.Presentation("source.pptx")
            dst = power_pptx.Presentation("dest.pptx")
            new_slide = dst.import_slide(src.slides[0])
            dst.save("merged.pptx")
        """
        from power_pptx._slide_importer import import_slide as _import_slide

        return _import_slide(self, source_slide, merge_master=merge_master)

    def apply_template(
        self,
        template_path_or_stream: str | os.PathLike[str] | IO[bytes] | Presentation,
    ) -> None:
        """Re-point every slide in this presentation at masters from *template_path_or_stream*.

        After this call every slide inherits theme, fonts, and colours from
        the template.  Slide content (shapes, text, animations) is preserved.

        The template can be a ``.potx`` or any ``.pptx``/``.pptm`` file — the
        master(s) inside are used regardless of the extension.  The masters,
        their layouts and themes, and the pictures those use are copied into
        this presentation and replace its own.  |SlideMaster| and
        |SlideLayout| objects obtained before the call belong to the replaced
        masters; read :attr:`slide_masters` / :attr:`slide_layouts` again
        afterwards.

        Layout matching (in priority order):

        1. Same ``<p:cSld name="…">`` name.
        2. Same layout ``type`` attribute (e.g. ``"title"``, ``"obj"``).
        3. Fall back to the template's first layout.

        Parameters
        ----------
        template_path_or_stream:
            Path to a ``.potx``/``.pptx`` file, a file-like object, or an
            open |Presentation|.

        Raises
        ------
        ValueError
            If the template has no slide master, or this presentation has
            slides and the template has no slide layout to put them on.
            Nothing is changed in that case.

        Example::

            prs = power_pptx.Presentation("deck.pptx")
            prs.apply_template("brand.potx")
            prs.save("branded_deck.pptx")
        """
        from power_pptx._template_applier import apply_template as _apply_template

        _apply_template(self, template_path_or_stream)

    def set_transition(
        self,
        kind: "MSO_TRANSITION_TYPE | None" = cast("MSO_TRANSITION_TYPE", _UNSET),
        *,
        duration: int | None = cast(int, _UNSET),
        advance_on_click: bool | None = cast(bool, _UNSET),
        advance_after: int | None = cast(int, _UNSET),
        force: bool = False,
    ) -> None:
        """Apply a transition to every slide in this presentation.

        Convenience for the common "give the whole deck the same transition"
        case; equivalent to looping over :attr:`slides` and assigning to each
        slide's :attr:`~power_pptx.slide.Slide.transition` properties.

        Any argument left unspecified is left untouched on each slide, so
        partial updates (e.g. only changing ``duration``) are safe::

            from power_pptx.enum.presentation import MSO_TRANSITION

            prs.set_transition(MSO_TRANSITION.MORPH, duration=750)

            # later, just bump the duration without disturbing the kind
            prs.set_transition(duration=500)

        Passing ``kind=None`` clears the transition element on every slide
        (restoring inheritance/defaults).  Passing ``duration=None``,
        ``advance_on_click=None``, or ``advance_after=None`` clears that
        individual attribute on every slide.

        Per-slide overrides are preserved by default
        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

        When ``kind`` is supplied, slides that already have an explicit
        transition kind are **left untouched** — the deck-wide call no
        longer silently clobbers an earlier ``slide.transition.kind = …``.
        This is the historical footgun that prompted item 2 in
        ``IMPROVEMENT_PLAN.md``.  To restore the old "force every slide to
        match" behaviour, pass ``force=True``::

            slide_2.transition.kind = MSO_TRANSITION_TYPE.MORPH
            prs.set_transition(MSO_TRANSITION_TYPE.FADE)              # slide 2 keeps MORPH
            prs.set_transition(MSO_TRANSITION_TYPE.FADE, force=True)  # slide 2 → FADE

        ``duration``, ``advance_on_click``, and ``advance_after`` are
        always applied to every slide regardless of ``force``; only
        ``kind`` participates in the override-preservation behaviour.

        A slide whose transition only carries timing settings — say after an
        earlier ``prs.set_transition(advance_after=8000)`` — has no kind of
        its own yet, so a later ``prs.set_transition(kind=…)`` applies to
        it.  An explicit ``slide.transition.kind = MSO_TRANSITION_TYPE.NONE``
        on a slide with no timing settings does count as that slide's
        choice and is preserved.
        """
        for slide in self.slides:
            transition = slide.transition
            if kind is not _UNSET:
                # Skip slides that already state a kind unless the caller
                # has opted in to force-overwrite.  A slide states a kind
                # when its transition has a kind element — including one
                # of a kind this library has no enum member for, which
                # reads back as ``None`` but is still the author's choice
                # — or when it is a bare ``<p:transition/>``, the explicit
                # "no transition" that reads back as
                # ``MSO_TRANSITION_TYPE.NONE``.  A kind-less transition
                # that only carries timing attributes (what an earlier
                # ``set_transition(advance_after=…)`` leaves behind) states
                # none, so the kind still applies to it.
                #
                # ``kind=None`` on the caller side means "clear" — apply
                # unconditionally so callers can still wipe the
                # transition off every slide in one call without an
                # explicit ``force=True``.
                if kind is None or force or not transition._states_a_kind:
                    transition.kind = kind
            if duration is not _UNSET:
                transition.duration = duration
            if advance_on_click is not _UNSET:
                transition.advance_on_click = advance_on_click
            if advance_after is not _UNSET:
                transition.advance_after = advance_after


def _lint_before_save(prs: Presentation, mode: LintOnSaveMode) -> None:
    """Lint every slide of `prs` and warn or raise per `mode`.

    Mirrors the ``lint`` option of :func:`power_pptx.compose.from_spec`: only
    ERROR-severity issues are acted on, and ``"raise"`` reports every offending
    issue in a single :class:`~power_pptx.exc.LintError`.
    """
    from power_pptx.exc import LintError
    from power_pptx.lint import LintSeverity

    errors: list[tuple[int, LintIssue]] = [
        (idx, issue)
        for idx, slide in enumerate(prs.slides)
        for issue in slide.lint().issues
        if issue.severity == LintSeverity.ERROR
    ]

    if not errors:
        return

    if mode == "warn":
        for idx, issue in errors:
            logger.warning("pptx lint: slide %d: %s", idx, issue)
        return

    msgs = "; ".join(f"slide {idx}: {issue}" for idx, issue in errors)
    raise LintError(f"Lint errors in presentation: {msgs}")
