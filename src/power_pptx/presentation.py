"""Main presentation object."""

from __future__ import annotations

import logging
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
    from power_pptx.parts.slide import SlidePart
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
    def lint_on_save(self, value: str) -> None:
        if value not in _LINT_ON_SAVE_MODES:
            raise ValueError(
                f"lint_on_save must be one of 'off', 'warn', or 'raise', got {value!r}"
            )
        # ---- the `not in` check above narrows `value` to `LintOnSaveMode` ----
        self._lint_on_save = value

    def save(self, file: str | IO[bytes]):
        """Writes this presentation to `file`.

        `file` can be either a file-path or a file-like object open for writing bytes.

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

        return _import_slide(source_slide.part, self.part, merge_master=merge_master)

    def apply_template(
        self,
        template_path_or_stream: str | IO[bytes],
    ) -> None:
        """Re-point every slide in this presentation at masters from *template_path_or_stream*.

        After this call every slide inherits theme, fonts, and colours from
        the template.  Slide content (shapes, text, animations) is preserved.

        The template can be a ``.potx`` or any ``.pptx``/``.pptm`` file — the
        master(s) inside are used regardless of the extension.

        Layout matching (in priority order):

        1. Same ``<p:cSld name="…">`` name.
        2. Same layout ``type`` attribute (e.g. ``"title"``, ``"obj"``).
        3. Fall back to the template's first layout.

        Parameters
        ----------
        template_path_or_stream:
            Path to a ``.potx``/``.pptx`` file, or a file-like object.

        Example::

            prs = power_pptx.Presentation("deck.pptx")
            prs.apply_template("brand.potx")
            prs.save("branded_deck.pptx")
        """
        from power_pptx._template_applier import apply_template as _apply_template
        from power_pptx.api import Presentation as _Presentation

        tpl = _Presentation(template_path_or_stream)
        _apply_template(self.part, tpl.part)

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
        """
        for slide in self.slides:
            transition = slide.transition
            if kind is not _UNSET:
                # Skip slides that already have an explicit kind unless
                # the caller has opted in to force-overwrite.  The
                # ``transition.kind`` getter returns ``None`` only when
                # no ``<p:transition>`` element is present.  An explicit
                # ``<p:transition/>`` reads back as
                # ``MSO_TRANSITION_TYPE.NONE`` and counts as an existing
                # explicit choice (the slide author asked for "no
                # transition"), so it is preserved unless ``force=True``.
                #
                # ``kind=None`` on the caller side means "clear" — apply
                # unconditionally so callers can still wipe the
                # transition off every slide in one call without an
                # explicit ``force=True``.
                if kind is None or transition.kind is None or force:
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
