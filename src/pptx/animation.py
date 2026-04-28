"""High-level animation API for python-pptx.

Exposes entrance, exit, and emphasis preset animations that map to
PowerPoint's built-in animation library.  All generated XML is valid
OOXML and round-trips through PowerPoint without loss.

Typical usage::

    from pptx.animation import Entrance, Exit, Emphasis, MotionPath, Trigger

    # Fade a shape in on the next mouse click (default trigger)
    Entrance.fade(slide, shape)

    # Fly in from the bottom, starting with the previous effect
    Entrance.fly_in(slide, shape, trigger=Trigger.WITH_PREVIOUS)

    # Pulse emphasis
    Emphasis.pulse(slide, shape)

    # Fade exit
    Exit.fade(slide, shape)

    # Move along a straight line, two inches right and one inch down
    from pptx.util import Inches
    MotionPath.line(slide, shape, Inches(2), Inches(1))

    # Fade in each paragraph of a text frame, one after another
    Entrance.fade(slide, text_frame, by_paragraph=True)

    # Sequence multiple effects one after another with a single click
    with slide.animations.sequence():
        Entrance.fade(slide, title)
        Entrance.fly_in(slide, body)
        Emphasis.pulse(slide, badge)

    # Via the slide proxy
    slide.animations.add_entrance("fade", shape)
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator, cast

from pptx.enum.animation import PP_ANIM_TRIGGER
from pptx.oxml.ns import nsdecls, qn
from pptx.oxml import parse_xml

if TYPE_CHECKING:
    from pptx.shapes.base import BaseShape
    from pptx.slide import Slide
    from pptx.text.text import TextFrame

#: Short alias; application code reads ``Trigger.ON_CLICK`` more naturally.
Trigger = PP_ANIM_TRIGGER

# Sentinel for "trigger not specified" — lets `sequence()` distinguish an
# explicit caller-supplied trigger from the default.  Don't use ``None``
# because that's a valid attribute value elsewhere.
_TRIGGER_UNSET = object()

# ---------------------------------------------------------------------------
# Namespace helpers
# ---------------------------------------------------------------------------

_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_NS = {"p": _P_NS}

# ---------------------------------------------------------------------------
# Preset metadata
# ---------------------------------------------------------------------------

# presetID values match PowerPoint's internal numbering
_ENTRANCE_PRESETS = {
    "appear":       (1,  0),   # (presetID, presetSubtype)
    "fade":         (10, 0),
    "fly_in":       (2,  8),   # default: from bottom (subtype 8)
    "float_in":     (22, 0),
    "wipe":         (8,  2),   # default: left
    "zoom":         (18, 0),
    "wheel":        (20, 1),   # 1 spoke
    "random_bars":  (12, 1),   # horizontal
}

_EXIT_PRESETS = {
    "disappear":    (1,  0),
    "fade":         (10, 0),
    "fly_out":      (2,  8),
    "float_out":    (22, 0),
    "wipe":         (8,  2),
    "zoom":         (18, 0),
    "wheel":        (20, 1),
    "random_bars":  (12, 1),
}

_EMPHASIS_PRESETS = {
    "pulse":  (13, 0),
    "spin":   (5,  0),
    "teeter": (6,  0),
}

# animEffect filter strings for each preset name (entrance direction)
_EFFECT_FILTER = {
    "fade":        "fade",
    "float_in":    "fade",
    "float_out":   "fade",
    "wipe":        "wipe(dir=left)",
    "zoom":        "zoom(dir=in)",
    "wheel":       "wheel(spokes=1)",
    "random_bars": "randomBar(dir=horz)",
}

# FlyIn/FlyOut path templates (M start L end E)
_FLY_PATHS_IN = {
    "bottom": "M 0 1 L 0 0 E",
    "top":    "M 0 -1 L 0 0 E",
    "left":   "M -1 0 L 0 0 E",
    "right":  "M 1 0 L 0 0 E",
}
_FLY_PATHS_OUT = {
    "bottom": "M 0 0 L 0 1 E",
    "top":    "M 0 0 L 0 -1 E",
    "left":   "M 0 0 L -1 0 E",
    "right":  "M 0 0 L 1 0 E",
}

# ---------------------------------------------------------------------------
# Internal XML builders
# ---------------------------------------------------------------------------


def _nsdecls_p() -> str:
    return nsdecls("p")


def _visibility_set_xml(ctn_id: int, spid: int, visible: bool) -> str:
    """Return XML for a `<p:set>` that shows or hides a shape."""
    val = "visible" if visible else "hidden"
    return (
        "<p:set>\n"
        "  <p:cBhvr>\n"
        f'    <p:cTn id="{ctn_id}" dur="1" fill="hold"/>\n'
        f'    <p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>\n'
        "    <p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>\n"
        "  </p:cBhvr>\n"
        f'  <p:to><p:strVal val="{val}"/></p:to>\n'
        "</p:set>\n"
    )


def _anim_effect_xml(ctn_id: int, spid: int, duration: int, filter_str: str, transition: str) -> str:
    return (
        f'<p:animEffect transition="{transition}" filter="{filter_str}">\n'
        "  <p:cBhvr>\n"
        f'    <p:cTn id="{ctn_id}" dur="{duration}"/>\n'
        f'    <p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>\n'
        "  </p:cBhvr>\n"
        "</p:animEffect>\n"
    )


def _anim_motion_xml(ctn_id: int, spid: int, duration: int, path: str) -> str:
    return (
        f'<p:animMotion origin="parent" path="{path}" pathEditMode="relative" rAng="0" ptsTypes="AE">\n'
        "  <p:cBhvr>\n"
        f'    <p:cTn id="{ctn_id}" dur="{duration}" fill="hold"/>\n'
        f'    <p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>\n'
        "  </p:cBhvr>\n"
        "</p:animMotion>\n"
    )


def _visibility_set_xml_for_paragraph(
    ctn_id: int, spid: int, paragraph_idx: int, visible: bool
) -> str:
    """Return XML for a `<p:set>` targeting a single paragraph by index."""
    val = "visible" if visible else "hidden"
    return (
        "<p:set>\n"
        "  <p:cBhvr>\n"
        f'    <p:cTn id="{ctn_id}" dur="1" fill="hold"/>\n'
        f'    <p:tgtEl><p:spTgt spid="{spid}">'
        f'<p:txEl><p:pRg st="{paragraph_idx}" end="{paragraph_idx}"/></p:txEl>'
        "</p:spTgt></p:tgtEl>\n"
        "    <p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>\n"
        "  </p:cBhvr>\n"
        f'  <p:to><p:strVal val="{val}"/></p:to>\n'
        "</p:set>\n"
    )


def _anim_effect_xml_for_paragraph(
    ctn_id: int,
    spid: int,
    paragraph_idx: int,
    duration: int,
    filter_str: str,
    transition: str,
) -> str:
    """Return XML for a `<p:animEffect>` targeting a single paragraph by index."""
    return (
        f'<p:animEffect transition="{transition}" filter="{filter_str}">\n'
        "  <p:cBhvr>\n"
        f'    <p:cTn id="{ctn_id}" dur="{duration}"/>\n'
        f'    <p:tgtEl><p:spTgt spid="{spid}">'
        f'<p:txEl><p:pRg st="{paragraph_idx}" end="{paragraph_idx}"/></p:txEl>'
        "</p:spTgt></p:tgtEl>\n"
        "  </p:cBhvr>\n"
        "</p:animEffect>\n"
    )


def _anim_scale_xml(ctn_id: int, spid: int, duration: int, x: int = 133333, y: int = 133333) -> str:
    """Return XML for a `<p:animScale>` (used by Pulse emphasis)."""
    return (
        "<p:animScale>\n"
        "  <p:cBhvr>\n"
        f'    <p:cTn id="{ctn_id}" dur="{duration}" autoRev="1"/>\n'
        f'    <p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>\n'
        "  </p:cBhvr>\n"
        f'  <p:by x="{x}" y="{y}"/>\n'
        "</p:animScale>\n"
    )


def _anim_rot_xml(ctn_id: int, spid: int, duration: int, angle_deg: float = 360.0) -> str:
    """Return XML for a `<p:animRot>` (used by Spin emphasis)."""
    ang = int(angle_deg * 60000)
    return (
        "<p:animRot>\n"
        "  <p:cBhvr>\n"
        f'    <p:cTn id="{ctn_id}" dur="{duration}" fill="hold"/>\n'
        f'    <p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>\n'
        "  </p:cBhvr>\n"
        f'  <p:by ang="{ang}"/>\n'
        "</p:animRot>\n"
    )


# ---------------------------------------------------------------------------
# SlideAnimations – the object returned by slide.animations
# ---------------------------------------------------------------------------


class SlideAnimations:
    """Manages the animation timeline for a single slide.

    Returned by :attr:`pptx.slide.Slide.animations`.  Provides methods to
    append entrance, exit, and emphasis effects to the slide's timing tree.
    Existing animations (e.g. authored in PowerPoint) are left untouched;
    new effects are appended after them.
    """

    def __init__(self, slide: Slide):
        self._slide = slide
        # Sequence-context state: when active, the first add_* call uses
        # `_seq_start` as its trigger and subsequent calls default to
        # AFTER_PREVIOUS so effects play one after another from a single click.
        # `_seq_delay` is added to the first effect's `delay` so that
        # `sequence(delay=N)` shifts the whole chain forward by N ms.
        self._seq_active: bool = False
        self._seq_start: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK
        self._seq_count: int = 0
        self._seq_delay: int = 0
        self._seq_delay_consumed: bool = False

    # -- public API ----------------------------------------------------------

    def add_entrance(
        self,
        preset: str,
        shape: BaseShape | TextFrame,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 500,
        direction: str = "bottom",
        by_paragraph: bool = False,
    ) -> None:
        """Append an entrance animation for *shape* to the slide timeline.

        *preset* is one of: ``"appear"``, ``"fade"``, ``"fly_in"``,
        ``"float_in"``, ``"wipe"``, ``"zoom"``, ``"wheel"``,
        ``"random_bars"``.

        *direction* is only used for ``"fly_in"``; accepted values are
        ``"bottom"`` (default), ``"top"``, ``"left"``, ``"right"``.

        Pass ``by_paragraph=True`` to animate each paragraph of a text
        frame separately.  *shape* may then be either a |TextFrame| or
        any shape that exposes a ``text_frame`` (e.g. an autoshape or
        placeholder).  The first paragraph fires on the supplied
        *trigger*; subsequent paragraphs fire after the previous one.
        Currently supports the ``"fade"``, ``"appear"``, ``"wipe"``,
        ``"zoom"``, ``"wheel"``, and ``"random_bars"`` presets — others
        raise :class:`ValueError`.
        """
        if preset not in _ENTRANCE_PRESETS:
            raise ValueError(
                f"Unknown entrance preset {preset!r}. "
                f"Choose from: {sorted(_ENTRANCE_PRESETS)}"
            )

        if by_paragraph:
            self._add_entrance_by_paragraph(
                preset, shape, trigger=trigger, delay=delay, duration=duration
            )
            return

        # When by_paragraph=False, *shape* must be a BaseShape (something
        # with a shape_id).  The union type is only widened to support
        # the by_paragraph=True case, so guard explicitly here rather
        # than relying on a duck-typed AttributeError later.
        if not hasattr(shape, "shape_id"):
            raise TypeError(
                f"add_entrance requires a shape with a shape_id; got "
                f"{type(shape).__name__!r}.  Pass by_paragraph=True to "
                "animate a TextFrame's paragraphs individually."
            )
        bshape = cast("BaseShape", shape)
        preset_id, preset_subtype = _ENTRANCE_PRESETS[preset]
        behaviors = self._entrance_behaviors(preset, bshape.shape_id, duration, direction)
        self._append_effect(
            bshape.shape_id, preset_id, "entr", preset_subtype, trigger, delay, behaviors
        )

    def add_exit(
        self,
        preset: str,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 500,
        direction: str = "bottom",
    ) -> None:
        """Append an exit animation for *shape* to the slide timeline.

        *preset* is one of: ``"disappear"``, ``"fade"``, ``"fly_out"``,
        ``"float_out"``, ``"wipe"``, ``"zoom"``, ``"wheel"``,
        ``"random_bars"``.
        """
        if preset not in _EXIT_PRESETS:
            raise ValueError(
                f"Unknown exit preset {preset!r}. "
                f"Choose from: {sorted(_EXIT_PRESETS)}"
            )
        preset_id, preset_subtype = _EXIT_PRESETS[preset]
        behaviors = self._exit_behaviors(preset, shape.shape_id, duration, direction)
        self._append_effect(
            shape.shape_id, preset_id, "exit", preset_subtype, trigger, delay, behaviors
        )

    def add_emphasis(
        self,
        preset: str,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 1000,
        degrees: float = 360.0,
    ) -> None:
        """Append an emphasis animation for *shape* to the slide timeline.

        *preset* is one of: ``"pulse"``, ``"spin"``, ``"teeter"``.

        *degrees* controls the rotation angle for the ``"spin"`` preset
        (default: 360 — one full clockwise revolution).
        """
        if preset not in _EMPHASIS_PRESETS:
            raise ValueError(
                f"Unknown emphasis preset {preset!r}. "
                f"Choose from: {sorted(_EMPHASIS_PRESETS)}"
            )
        preset_id, preset_subtype = _EMPHASIS_PRESETS[preset]
        behaviors = self._emphasis_behaviors(preset, shape.shape_id, duration, degrees)
        self._append_effect(
            shape.shape_id, preset_id, "emph", preset_subtype, trigger, delay, behaviors
        )

    def add_motion(
        self,
        shape: BaseShape,
        path: str,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 2000,
    ) -> None:
        """Append a motion-path animation that moves *shape* along *path*.

        *path* is an OOXML motion-path string (the same syntax PowerPoint
        uses internally): ``"M x y L x y E"`` for a single straight
        segment, ``"M x y C x1 y1 x2 y2 x y E"`` for a cubic bezier, etc.
        Coordinates are normalized to the slide's width and height
        (``0,0`` is the shape's starting position; ``1,0`` is one slide
        width to the right).  The terminating ``E`` is required.

        Use :meth:`MotionPath.line` for a coordinate-aware convenience
        wrapper, or :meth:`MotionPath.custom` to pass an arbitrary path.
        """
        ids = self._reserve_ids(1)
        behaviors = _anim_motion_xml(ids[0], shape.shape_id, duration, path)
        # presetID 64 is PowerPoint's "Custom Path" path animation.
        self._append_effect(
            shape.shape_id, 64, "path", 0, trigger, delay, behaviors
        )

    @contextmanager
    def sequence(
        self,
        *,
        start: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
        delay: int = 0,
    ) -> Iterator[SlideAnimations]:
        """Group the contained animations into a single sequenced run.

        Inside the ``with`` block, the first effect added (whose
        ``trigger`` was not explicitly set) fires on *start* and every
        subsequent effect defaults to :attr:`Trigger.AFTER_PREVIOUS`,
        producing a chain of effects that play one after another from a
        single click.

        Effects whose *trigger* is explicitly supplied still honour the
        caller's choice — sequencing is opt-in per call.

        Example::

            with slide.animations.sequence(delay=200):
                Entrance.fade(slide, title)
                Entrance.fly_in(slide, body)
                Emphasis.pulse(slide, badge)

        Sequences cannot be nested — entering a sequence inside another
        raises :class:`RuntimeError`.
        """
        if self._seq_active:
            raise RuntimeError("animation sequences cannot be nested")
        self._seq_active = True
        self._seq_start = start
        self._seq_delay = delay
        self._seq_delay_consumed = False
        self._seq_count = 0
        try:
            yield self
        finally:
            self._seq_active = False
            self._seq_count = 0
            self._seq_delay = 0
            self._seq_delay_consumed = False

    # -- behavior builders ---------------------------------------------------

    def _entrance_behaviors(
        self, preset: str, spid: int, duration: int, direction: str
    ) -> str:
        ids = self._reserve_ids(3)
        vis_xml = _visibility_set_xml(ids[0], spid, visible=True)

        if preset == "appear":
            return vis_xml

        if preset == "fly_in":
            path = _FLY_PATHS_IN.get(direction, _FLY_PATHS_IN["bottom"])
            return vis_xml + _anim_motion_xml(ids[1], spid, duration, path)

        if preset == "float_in":
            return (
                vis_xml
                + _anim_effect_xml(ids[1], spid, duration, "fade", "in")
                + _anim_motion_xml(ids[2], spid, duration, "M 0 0.25 L 0 0 E")
            )

        filter_str = _EFFECT_FILTER.get(preset, "fade")
        return vis_xml + _anim_effect_xml(ids[1], spid, duration, filter_str, "in")

    def _exit_behaviors(
        self, preset: str, spid: int, duration: int, direction: str
    ) -> str:
        ids = self._reserve_ids(3)

        if preset == "disappear":
            return _visibility_set_xml(ids[0], spid, visible=False)

        if preset == "fly_out":
            path = _FLY_PATHS_OUT.get(direction, _FLY_PATHS_OUT["bottom"])
            vis_xml = _visibility_set_xml(ids[1], spid, visible=False)
            return _anim_motion_xml(ids[0], spid, duration, path) + vis_xml

        if preset == "float_out":
            vis_xml = _visibility_set_xml(ids[2], spid, visible=False)
            return (
                _anim_effect_xml(ids[0], spid, duration, "fade", "out")
                + _anim_motion_xml(ids[1], spid, duration, "M 0 0 L 0 0.25 E")
                + vis_xml
            )

        filter_str = _EFFECT_FILTER.get(preset, "fade")
        vis_xml = _visibility_set_xml(ids[1], spid, visible=False)
        # For exit: animEffect first, then hide
        return _anim_effect_xml(ids[0], spid, duration, filter_str, "out") + vis_xml

    def _emphasis_behaviors(
        self, preset: str, spid: int, duration: int, degrees: float = 360.0
    ) -> str:
        ids = self._reserve_ids(1)
        if preset == "pulse":
            return _anim_scale_xml(ids[0], spid, duration)
        if preset == "spin":
            return _anim_rot_xml(ids[0], spid, duration, angle_deg=degrees)
        if preset == "teeter":
            # Teeter: oscillate rotation ~10 degrees either side
            ang = int(10 * 60000)
            return (
                "<p:animRot>\n"
                "  <p:cBhvr>\n"
                f'    <p:cTn id="{ids[0]}" dur="{duration}" autoRev="1"/>\n'
                f'    <p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>\n'
                "  </p:cBhvr>\n"
                f'  <p:by ang="{ang}"/>\n'
                "</p:animRot>\n"
            )
        return ""

    # -- by-paragraph entrance ---------------------------------------------

    # Subset of entrance presets where targeting an individual paragraph
    # makes sense.  Direction-aware presets (fly_in, float_in) are
    # excluded because PowerPoint's per-paragraph wrappers don't support
    # the motion-path component cleanly.
    _PARAGRAPH_PRESETS = frozenset({
        "appear", "fade", "wipe", "zoom", "wheel", "random_bars",
    })

    def _add_entrance_by_paragraph(
        self,
        preset: str,
        target: BaseShape | TextFrame,
        *,
        trigger: PP_ANIM_TRIGGER,
        delay: int,
        duration: int,
    ) -> None:
        """Append one entrance effect per paragraph of a text frame.

        Resolves *target* to a (shape, text_frame) pair, then emits a
        chain of effects: the first uses *trigger*, the rest use
        AFTER_PREVIOUS so the text reveals one paragraph at a time.
        """
        if preset not in self._PARAGRAPH_PRESETS:
            raise ValueError(
                f"by_paragraph=True is not supported for preset {preset!r}. "
                f"Choose from: {sorted(self._PARAGRAPH_PRESETS)}"
            )

        from pptx.text.text import TextFrame as _TextFrame

        if isinstance(target, _TextFrame):
            text_frame = target
            # Walk up the parent chain until we hit something with a
            # `shape_id` (a |BaseShape|).  TextFrames inside table cells
            # have an intermediate `_Cell` parent that has no shape_id;
            # those cells live inside a `GraphicFrame` further up.  If
            # nothing in the chain has a shape_id, the TextFrame isn't
            # attached to a slide-level shape and we can't target it.
            parent = target._parent  # type: ignore[attr-defined]
            seen: set[int] = set()
            while parent is not None and not hasattr(parent, "shape_id"):
                if id(parent) in seen:
                    parent = None  # cycle guard
                    break
                seen.add(id(parent))
                parent = getattr(parent, "_parent", None)
            if parent is None or not hasattr(parent, "shape_id"):
                raise TypeError(
                    "by_paragraph=True requires a TextFrame whose parent "
                    "chain reaches a shape; "
                    f"{type(target._parent).__name__!r} has no shape_id "  # type: ignore[attr-defined]
                    "ancestor (table-cell text frames are not yet supported)."
                )
            shape = cast("BaseShape", parent)
        else:
            text_frame = getattr(target, "text_frame", None)
            if text_frame is None or not hasattr(target, "shape_id"):
                raise TypeError(
                    "by_paragraph=True requires a TextFrame or a shape with "
                    f"a text_frame and shape_id; got {type(target).__name__!r}"
                )
            shape = cast("BaseShape", target)

        spid: int = shape.shape_id
        preset_id, preset_subtype = _ENTRANCE_PRESETS[preset]
        # Resolve the first trigger now so subsequent effects can chain
        # off it via AFTER_PREVIOUS.  The default trigger inside a
        # `sequence()` context is honoured via _resolve_default_trigger.
        first_trigger = self._resolve_default_trigger(trigger)
        for i, _para in enumerate(text_frame.paragraphs):
            effect_trigger = first_trigger if i == 0 else PP_ANIM_TRIGGER.AFTER_PREVIOUS
            effect_delay = delay if i == 0 else 0
            behaviors = self._paragraph_entrance_behaviors(preset, spid, i, duration)
            self._append_effect(
                spid,
                preset_id,
                "entr",
                preset_subtype,
                effect_trigger,
                effect_delay,
                behaviors,
            )

    def _paragraph_entrance_behaviors(
        self, preset: str, spid: int, paragraph_idx: int, duration: int
    ) -> str:
        """Return the behaviors XML for a paragraph-targeted entrance preset."""
        ids = self._reserve_ids(2)
        vis_xml = _visibility_set_xml_for_paragraph(
            ids[0], spid, paragraph_idx, visible=True
        )
        if preset == "appear":
            return vis_xml
        filter_str = _EFFECT_FILTER.get(preset, "fade")
        return vis_xml + _anim_effect_xml_for_paragraph(
            ids[1], spid, paragraph_idx, duration, filter_str, "in"
        )

    # -- trigger / sequence resolution -------------------------------------

    def _resolve_default_trigger(self, trigger: PP_ANIM_TRIGGER) -> PP_ANIM_TRIGGER:
        """Map the ``_TRIGGER_UNSET`` sentinel to a concrete trigger.

        When called outside a sequence, an unset trigger falls back to
        ``Trigger.ON_CLICK``.  Inside a sequence, the first effect uses
        the sequence's ``start`` trigger and subsequent effects default
        to ``Trigger.AFTER_PREVIOUS``.
        """
        if trigger is not _TRIGGER_UNSET:
            return trigger
        if not self._seq_active:
            return PP_ANIM_TRIGGER.ON_CLICK
        if self._seq_count == 0:
            self._seq_count += 1
            return self._seq_start
        self._seq_count += 1
        return PP_ANIM_TRIGGER.AFTER_PREVIOUS

    def _consume_sequence_delay(self, delay: int) -> int:
        """Add the sequence's ``delay`` to the first effect's *delay*.

        ``sequence(delay=N)`` shifts the whole chain by N ms, so the
        sequence-level delay is added to the first effect's per-call
        ``delay`` and never applied again within the same block.
        Returns *delay* unchanged when no sequence is active.
        """
        if self._seq_active and not self._seq_delay_consumed:
            self._seq_delay_consumed = True
            return delay + self._seq_delay
        return delay

    # -- timing tree management ----------------------------------------------

    def _append_effect(
        self,
        spid: int,
        preset_id: int,
        preset_class: str,
        preset_subtype: int,
        trigger: PP_ANIM_TRIGGER,
        delay: int,
        behaviors_xml: str,
    ) -> None:
        """Build the animation XML and insert it into the slide timing tree."""
        root_ctn = self._get_or_create_root_ctn()

        trigger = self._resolve_default_trigger(trigger)
        delay = self._consume_sequence_delay(delay)
        grp_id, node_type, wrapper_delay = self._resolve_trigger(trigger)

        indent_behaviors = "\n".join(
            "      " + line for line in behaviors_xml.splitlines()
        ) + "\n"

        effect_par = (
            "<p:par>\n"
            f'  <p:cTn id="0" presetID="{preset_id}"'
            f' presetClass="{preset_class}" presetSubtype="{preset_subtype}"'
            f' fill="hold" grpId="{grp_id}" nodeType="{node_type}">\n'
            "    <p:stCondLst>\n"
            f'      <p:cond delay="{delay}"/>\n'
            "    </p:stCondLst>\n"
            "    <p:childTnLst>\n"
            f"{indent_behaviors}"
            "    </p:childTnLst>\n"
            "  </p:cTn>\n"
            "</p:par>\n"
        )

        click_group = (
            "<p:par %s>\n"
            "  <p:cTn fill=\"hold\">\n"
            "    <p:stCondLst>\n"
            f'      <p:cond delay="{wrapper_delay}"/>\n'
            "    </p:stCondLst>\n"
            "    <p:childTnLst>\n"
            + "\n".join("      " + l for l in effect_par.splitlines()) + "\n"
            "    </p:childTnLst>\n"
            "  </p:cTn>\n"
            "</p:par>\n"
        ) % _nsdecls_p()

        group_elm = parse_xml(click_group.encode("utf-8"))
        # Fix IDs: assign proper sequential IDs to all p:cTn elements in our
        # new subtree now that we know which IDs are free.
        self._assign_ids(group_elm)
        root_ctn.append(group_elm)

    def _get_or_create_root_ctn(self):
        """Return the `p:childTnLst` of the root timing container.

        Creates the full `p:timing/p:tnLst/p:par/p:cTn/p:childTnLst` skeleton
        if it doesn't already exist, without disturbing any existing timing.
        """
        sld = self._slide._element
        return sld.get_or_add_childTnLst()

    def _next_ctn_id(self) -> int:
        """Return the next free ``p:cTn/@id`` integer for this slide."""
        sld = self._slide._element
        # BaseOxmlElement.xpath() pre-injects _nsmap; no namespaces kwarg needed
        id_strs = sld.xpath("p:timing//p:cTn/@id")
        if not id_strs:
            return 2  # 1 is reserved for the root cTn
        return max(int(s) for s in id_strs) + 1

    def _reserve_ids(self, count: int) -> list[int]:
        """Return `count` placeholder ints; actual IDs are assigned at insert time."""
        # We use 0-based placeholders; _assign_ids will replace them.
        return list(range(count))

    def _assign_ids(self, group_elm) -> None:
        """Walk `group_elm` and assign monotonically-increasing IDs to every `p:cTn`."""
        next_id = self._next_ctn_id()
        for ctn in group_elm.iter(qn("p:cTn")):
            ctn.set("id", str(next_id))
            next_id += 1

    def _resolve_trigger(
        self, trigger: PP_ANIM_TRIGGER
    ) -> tuple[int, str, str]:
        """Return ``(grp_id, node_type, wrapper_delay)`` for *trigger*."""
        sld = self._slide._element
        click_grp_ids = sld.xpath("p:timing//p:cTn[@nodeType='clickEffect']/@grpId")
        current_max = max((int(g) for g in click_grp_ids), default=-1)

        if trigger is PP_ANIM_TRIGGER.ON_CLICK:
            grp_id = current_max + 1
            return grp_id, "clickEffect", "indefinite"
        elif trigger is PP_ANIM_TRIGGER.WITH_PREVIOUS:
            grp_id = max(current_max, 0)
            return grp_id, "withEffect", "0"
        else:  # AFTER_PREVIOUS
            grp_id = max(current_max, 0)
            return grp_id, "afterEffect", "0"


# ---------------------------------------------------------------------------
# Convenience class API  (Entrance.fade(slide, shape, ...) etc.)
# ---------------------------------------------------------------------------


class Entrance:
    """Convenience class for adding entrance animations.

    All methods are class-methods that delegate to
    :class:`SlideAnimations`.  The slide's ``.animations`` proxy is
    created on demand and discarded; it does not need to be retained.

    Available presets: ``appear``, ``fade``, ``fly_in``, ``float_in``,
    ``wipe``, ``zoom``, ``wheel``, ``random_bars``.
    """

    @classmethod
    def appear(
        cls,
        slide: Slide,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
    ) -> None:
        """Shape pops into view instantly (no duration)."""
        slide.animations.add_entrance("appear", shape, trigger=trigger, delay=delay)

    @classmethod
    def fade(
        cls,
        slide: Slide,
        shape: BaseShape | TextFrame,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 500,
        by_paragraph: bool = False,
    ) -> None:
        """Shape fades in.

        With ``by_paragraph=True``, *shape* may be a |TextFrame| or any
        shape with a ``text_frame``; one fade effect is added per
        paragraph and they reveal sequentially after the first click.
        """
        slide.animations.add_entrance(
            "fade",
            shape,
            trigger=trigger,
            delay=delay,
            duration=duration,
            by_paragraph=by_paragraph,
        )

    @classmethod
    def fly_in(
        cls,
        slide: Slide,
        shape: BaseShape,
        *,
        direction: str = "bottom",
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 500,
    ) -> None:
        """Shape flies in from the given *direction* (bottom/top/left/right)."""
        slide.animations.add_entrance(
            "fly_in",
            shape,
            trigger=trigger,
            delay=delay,
            duration=duration,
            direction=direction,
        )

    @classmethod
    def float_in(
        cls,
        slide: Slide,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 500,
    ) -> None:
        """Shape fades and drifts upward into its final position."""
        slide.animations.add_entrance(
            "float_in", shape, trigger=trigger, delay=delay, duration=duration
        )

    @classmethod
    def wipe(
        cls,
        slide: Slide,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 500,
    ) -> None:
        """Shape is revealed by a wipe from the left."""
        slide.animations.add_entrance(
            "wipe", shape, trigger=trigger, delay=delay, duration=duration
        )

    @classmethod
    def zoom(
        cls,
        slide: Slide,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 500,
    ) -> None:
        """Shape zooms in from the center."""
        slide.animations.add_entrance(
            "zoom", shape, trigger=trigger, delay=delay, duration=duration
        )

    @classmethod
    def wheel(
        cls,
        slide: Slide,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 500,
    ) -> None:
        """Shape spins into view like a wheel."""
        slide.animations.add_entrance(
            "wheel", shape, trigger=trigger, delay=delay, duration=duration
        )

    @classmethod
    def random_bars(
        cls,
        slide: Slide,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 500,
    ) -> None:
        """Shape appears through random horizontal bars."""
        slide.animations.add_entrance(
            "random_bars", shape, trigger=trigger, delay=delay, duration=duration
        )


class Exit:
    """Convenience class for adding exit animations.

    Available presets: ``disappear``, ``fade``, ``fly_out``,
    ``float_out``, ``wipe``, ``zoom``, ``wheel``, ``random_bars``.
    """

    @classmethod
    def disappear(
        cls,
        slide: Slide,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
    ) -> None:
        """Shape vanishes instantly."""
        slide.animations.add_exit("disappear", shape, trigger=trigger, delay=delay)

    @classmethod
    def fade(
        cls,
        slide: Slide,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 500,
    ) -> None:
        """Shape fades out."""
        slide.animations.add_exit(
            "fade", shape, trigger=trigger, delay=delay, duration=duration
        )

    @classmethod
    def fly_out(
        cls,
        slide: Slide,
        shape: BaseShape,
        *,
        direction: str = "bottom",
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 500,
    ) -> None:
        """Shape flies out in the given *direction*."""
        slide.animations.add_exit(
            "fly_out",
            shape,
            trigger=trigger,
            delay=delay,
            duration=duration,
            direction=direction,
        )

    @classmethod
    def float_out(
        cls,
        slide: Slide,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 500,
    ) -> None:
        """Shape fades and drifts upward out of view."""
        slide.animations.add_exit(
            "float_out", shape, trigger=trigger, delay=delay, duration=duration
        )

    @classmethod
    def wipe(
        cls,
        slide: Slide,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 500,
    ) -> None:
        """Shape is wiped away from the left."""
        slide.animations.add_exit(
            "wipe", shape, trigger=trigger, delay=delay, duration=duration
        )

    @classmethod
    def zoom(
        cls,
        slide: Slide,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 500,
    ) -> None:
        """Shape zooms away to the center."""
        slide.animations.add_exit(
            "zoom", shape, trigger=trigger, delay=delay, duration=duration
        )


class Emphasis:
    """Convenience class for adding emphasis animations.

    Available presets: ``pulse``, ``spin``, ``teeter``.
    """

    @classmethod
    def pulse(
        cls,
        slide: Slide,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 300,
    ) -> None:
        """Shape briefly grows and shrinks (pulse)."""
        slide.animations.add_emphasis(
            "pulse", shape, trigger=trigger, delay=delay, duration=duration
        )

    @classmethod
    def spin(
        cls,
        slide: Slide,
        shape: BaseShape,
        *,
        degrees: float = 360.0,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 1000,
    ) -> None:
        """Shape spins by `degrees` (default: full 360-degree rotation)."""
        slide.animations.add_emphasis(
            "spin", shape, trigger=trigger, delay=delay, duration=duration, degrees=degrees
        )

    @classmethod
    def teeter(
        cls,
        slide: Slide,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 800,
    ) -> None:
        """Shape rocks back and forth (teeter)."""
        slide.animations.add_emphasis(
            "teeter", shape, trigger=trigger, delay=delay, duration=duration
        )


class MotionPath:
    """Convenience class for adding motion-path animations.

    A motion path moves a shape along a parametric path while playing.
    Coordinates are normalized to the slide's width and height: ``(0,0)``
    is the shape's starting position, ``(1,0)`` is one slide-width to
    the right, ``(0,1)`` is one slide-height down.

    Example::

        from pptx.animation import MotionPath, Trigger
        from pptx.util import Inches

        # Slide it two inches to the right and one inch down
        MotionPath.line(slide, badge, Inches(2), Inches(1))

        # Or hand-roll a path: a quarter-circle to the right
        MotionPath.custom(
            slide, badge, "M 0 0 C 0 -0.2 0.2 -0.2 0.2 0 E"
        )
    """

    @classmethod
    def line(
        cls,
        slide: Slide,
        shape: BaseShape,
        dx: int,
        dy: int,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 2000,
    ) -> None:
        """Move *shape* in a straight line by ``(dx, dy)`` EMU.

        *dx* and *dy* are absolute deltas in English Metric Units (EMU)
        — typically built with :func:`pptx.util.Inches`,
        :func:`pptx.util.Pt`, etc.  They are normalized to the slide's
        size before being written into the motion-path attribute, so a
        path encoded against a 10-inch-wide slide still moves the right
        absolute distance on a wide-screen slide.
        """
        slide_w, slide_h = _slide_dimensions_emu(slide)
        nx = float(dx) / slide_w
        ny = float(dy) / slide_h
        path = f"M 0 0 L {nx:g} {ny:g} E"
        slide.animations.add_motion(
            shape, path, trigger=trigger, delay=delay, duration=duration
        )

    @classmethod
    def custom(
        cls,
        slide: Slide,
        shape: BaseShape,
        path: str,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 2000,
    ) -> None:
        """Move *shape* along an arbitrary OOXML motion *path* string.

        *path* is a PowerPoint motion-path expression, e.g.
        ``"M 0 0 L 0.5 0 E"`` for a horizontal half-slide hop.  The
        terminating ``E`` (path end) is required.
        """
        if not path or "E" not in path:
            raise ValueError(
                "motion path must be a non-empty OOXML path string ending in 'E'"
            )
        slide.animations.add_motion(
            shape, path, trigger=trigger, delay=delay, duration=duration
        )


def _slide_dimensions_emu(slide: Slide) -> tuple[int, int]:
    """Return the (width, height) of *slide*'s presentation in EMU.

    Falls back to PowerPoint's default 10in × 7.5in if either dimension
    is missing (which should not happen for any well-formed deck).
    """
    prs_part = slide.part.package.presentation_part
    presentation = prs_part.presentation
    width = presentation.slide_width or 9_144_000   # 10 inches
    height = presentation.slide_height or 6_858_000  # 7.5 inches
    return int(width), int(height)
