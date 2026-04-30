"""High-level animation API for python-pptx.

Exposes entrance, exit, and emphasis preset animations that map to
PowerPoint's built-in animation library.  All generated XML is valid
OOXML and round-trips through PowerPoint without loss.

Typical usage::

    from power_pptx.animation import Entrance, Exit, Emphasis, MotionPath, Trigger

    # Fade a shape in on the next mouse click (default trigger)
    Entrance.fade(slide, shape)

    # Fly in from the bottom, starting with the previous effect
    Entrance.fly_in(slide, shape, trigger=Trigger.WITH_PREVIOUS)

    # Pulse emphasis
    Emphasis.pulse(slide, shape)

    # Fade exit
    Exit.fade(slide, shape)

    # Move along a straight line, two inches right and one inch down
    from power_pptx.util import Inches
    MotionPath.line(slide, shape, Inches(2), Inches(1))

    # Or pass an SVG-style path with a viewbox.
    MotionPath.svg(slide, shape, "M 0 0 H 100 V 100", viewbox=(0, 0, 100, 100))

    # Fade in each paragraph of a text frame, one after another
    Entrance.fade(slide, text_frame, by_paragraph=True)

    # Sequence multiple effects one after another with a single click
    with slide.animations.sequence():
        Entrance.fade(slide, title)
        Entrance.fly_in(slide, body)
        Emphasis.pulse(slide, badge)

    # Via the slide proxy
    slide.animations.add_entrance("fade", shape)

    # Polymorphic dispatcher — useful when the kind is data-driven
    # (e.g. from a YAML spec).
    slide.animations.add("entrance", "fade", shape)
    slide.animations.add("emphasis", "pulse", shape)
    slide.animations.add("motion", "M 0 0 L 0.5 0 E", shape, duration=1500)
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterator, Optional, cast

from power_pptx.enum.animation import PP_ANIM_TRIGGER
from power_pptx.oxml.ns import nsdecls, qn
from power_pptx.oxml import parse_xml

if TYPE_CHECKING:
    from power_pptx.shapes.base import BaseShape
    from power_pptx.slide import Slide
    from power_pptx.text.text import TextFrame

#: Short alias; application code reads ``Trigger.ON_CLICK`` more naturally.
Trigger = PP_ANIM_TRIGGER


# ---------------------------------------------------------------------------
# Easing curves
# ---------------------------------------------------------------------------

#: Named easings -> ``(accel, decel)`` fractions of the animation duration
#: spent in acceleration / deceleration phases.  Each value is between 0.0
#: and 1.0.  These four cover the common cases; pass an explicit
#: ``(accel, decel)`` tuple for anything else.
_EASING_PRESETS = {
    "linear": (0.0, 0.0),
    "ease_in": (0.5, 0.0),
    "ease_out": (0.0, 0.5),
    "ease_in_out": (0.3, 0.3),
}


def _resolve_easing(easing) -> tuple[float, float]:
    """Resolve an ``easing`` argument to an ``(accel, decel)`` 2-tuple."""
    if isinstance(easing, str):
        try:
            return _EASING_PRESETS[easing]
        except KeyError:
            raise ValueError(
                "unknown easing preset %r; choose from %r or pass an "
                "explicit (accel, decel) tuple"
                % (easing, sorted(_EASING_PRESETS))
            )
    if (
        isinstance(easing, tuple)
        and len(easing) == 2
        and all(isinstance(v, (int, float)) for v in easing)
    ):
        accel, decel = float(easing[0]), float(easing[1])
        if not (0.0 <= accel <= 1.0 and 0.0 <= decel <= 1.0 and accel + decel <= 1.0):
            raise ValueError(
                "easing accel and decel must each be in [0, 1] and sum to ≤ 1"
            )
        return accel, decel
    raise TypeError(
        "easing must be a preset name (e.g. 'ease_in_out') or an "
        "(accel, decel) 2-tuple of floats"
    )


def _apply_easing(group_elm, easing) -> None:
    """Stamp ``accel`` / ``decel`` onto every animation-duration ``<p:cTn>``.

    Operates only on ``<p:cTn>`` elements whose ``dur`` attribute is a
    positive integer greater than 1 — those are the "effect-level" timing
    nodes that drive the actual animation, not the wrapper / 1-frame
    visibility nodes.
    """
    accel, decel = _resolve_easing(easing)
    # ``int(x + 0.5)`` is round-half-up for the always-non-negative
    # ``accel`` / ``decel`` values; behaves identically to ``round()`` here
    # but is unambiguous regardless of banker's-rounding edge cases.
    accel_pct = int(accel * 100000 + 0.5)
    decel_pct = int(decel * 100000 + 0.5)
    for ctn in group_elm.iter(qn("p:cTn")):
        dur = ctn.get("dur")
        try:
            dur_i = int(dur) if dur is not None else 0
        except ValueError:
            continue
        if dur_i <= 1:
            continue
        if accel_pct:
            ctn.set("accel", str(accel_pct))
        if decel_pct:
            ctn.set("decel", str(decel_pct))

# Sentinel for "trigger not specified" — lets `sequence()` distinguish an
# explicit caller-supplied trigger from the default.  Don't use ``None``
# because that's a valid attribute value elsewhere.
_TRIGGER_UNSET = object()

# presetClass attribute → human kind name.  Used by AnimationEntry.kind
# for read-side introspection.
_PRESET_CLASS_TO_KIND: dict[str, str] = {
    "entr": "entrance",
    "exit": "exit",
    "emph": "emphasis",
    "path": "motion",
}

# nodeType attribute on the wrapper cTn → trigger enum.  Used by
# AnimationEntry.trigger.
_NODE_TYPE_TO_TRIGGER: dict[str, "PP_ANIM_TRIGGER"] = {
    "clickEffect": PP_ANIM_TRIGGER.ON_CLICK,
    "withEffect":  PP_ANIM_TRIGGER.WITH_PREVIOUS,
    "afterEffect": PP_ANIM_TRIGGER.AFTER_PREVIOUS,
}

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

# Reverse mappings from (presetID, presetSubtype) → preset name, keyed by
# preset class.  Used by AnimationEntry.preset for read-side introspection.
# Subtype matches are preferred but falling back to a "subtype-agnostic"
# match handles presets like ``fly_in`` where subtype encodes direction.
def _build_reverse_presets() -> dict[str, dict[tuple[int, int], str]]:
    out: dict[str, dict[tuple[int, int], str]] = {
        "entr": {(pid, sub): name for name, (pid, sub) in _ENTRANCE_PRESETS.items()},
        "exit": {(pid, sub): name for name, (pid, sub) in _EXIT_PRESETS.items()},
        "emph": {(pid, sub): name for name, (pid, sub) in _EMPHASIS_PRESETS.items()},
    }
    return out

_REVERSE_PRESETS = _build_reverse_presets()
_REVERSE_PRESET_BY_ID: dict[str, dict[int, str]] = {
    cls: {pid: name for (pid, _sub), name in entries.items()}
    for cls, entries in _REVERSE_PRESETS.items()
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

    Returned by :attr:`power_pptx.slide.Slide.animations`.  Provides methods to
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
        # Group-context state.  When active, the first call uses ``_grp_start``
        # and every subsequent call within the block defaults to
        # WITH_PREVIOUS — i.e. the whole cluster animates as one visual unit.
        self._grp_active: bool = False
        self._grp_start: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.AFTER_PREVIOUS
        self._grp_count: int = 0
        self._grp_delay: int = 0
        self._grp_delay_consumed: bool = False

    # -- introspection ------------------------------------------------------

    def __iter__(self) -> "Iterator[AnimationEntry]":
        """Iterate over the slide's top-level animation entries.

        Yields one :class:`AnimationEntry` per click-group ``<p:par>``,
        in document order.  Effects authored inside PowerPoint as well
        as those added via this API are reported.
        """
        for top_par in self._top_level_pars():
            yield AnimationEntry(top_par, self._slide)

    def __len__(self) -> int:
        return len(self._top_level_pars())

    def __bool__(self) -> bool:  # explicit so __len__ doesn't drive truthiness alone
        return bool(self._top_level_pars())

    def list(self) -> "list[AnimationEntry]":
        """Return a list of :class:`AnimationEntry` views, in document order.

        Convenience for callers that prefer not to iterate.
        """
        return list(self)

    def clear(self) -> int:
        """Remove every animation from the slide.

        Returns the number of top-level click-group entries removed.
        Unlike :meth:`purge_orphans`, this drops **all** entries — useful
        when iterating on animation design and you want to re-run the
        build without the previous run's effects piling up.
        """
        removed = 0
        for top_par in list(self._top_level_pars()):
            parent = top_par.getparent()
            if parent is not None:
                parent.remove(top_par)
                removed += 1
        return removed

    def _top_level_pars(self) -> list[Any]:
        """Return the top-level click-group ``<p:par>`` elements."""
        sld = self._slide._element
        return list(
            sld.xpath("p:timing/p:tnLst/p:par/p:cTn/p:childTnLst/p:par")
        )

    # -- public API ----------------------------------------------------------

    def add(
        self,
        kind: str,
        preset: str,
        shape: "BaseShape | TextFrame",
        **kwargs: Any,
    ) -> None:
        """Polymorphic dispatcher — add an animation of the given *kind*.

        *kind* selects the animation family and routes to the matching
        ``add_*`` method:

        * ``"entrance"`` → :meth:`add_entrance`
        * ``"exit"``     → :meth:`add_exit`
        * ``"emphasis"`` → :meth:`add_emphasis`
        * ``"motion"``   → :meth:`add_motion` (here *preset* is the
          OOXML motion-path string, e.g. ``"M 0 0 L 0.5 0 E"``)

        Convenient when the animation kind is data-driven (e.g. read
        from a YAML spec) rather than known at call sites::

            slide.animations.add("entrance", "fade", title)
            slide.animations.add("emphasis", "pulse", badge)
            slide.animations.add("motion", "M 0 0 L 0.5 0 E", logo,
                                 duration=2000)

        For literal authoring the static
        ``Entrance.fade(slide, shape, ...)`` / ``Exit.fade(...)`` /
        ``Emphasis.pulse(...)`` helpers remain idiomatic and a touch
        more readable.
        """
        if kind == "entrance":
            self.add_entrance(preset, shape, **kwargs)
            return
        if kind == "exit":
            if not hasattr(shape, "shape_id"):
                raise TypeError(
                    f"add(kind='exit') requires a BaseShape; got "
                    f"{type(shape).__name__!r}."
                )
            self.add_exit(preset, cast("BaseShape", shape), **kwargs)
            return
        if kind == "emphasis":
            if not hasattr(shape, "shape_id"):
                raise TypeError(
                    f"add(kind='emphasis') requires a BaseShape; got "
                    f"{type(shape).__name__!r}."
                )
            self.add_emphasis(preset, cast("BaseShape", shape), **kwargs)
            return
        if kind == "motion":
            if not hasattr(shape, "shape_id"):
                raise TypeError(
                    f"add(kind='motion') requires a BaseShape; got "
                    f"{type(shape).__name__!r}."
                )
            # For motion, *preset* carries the raw OOXML path string;
            # validating ``E``-termination here keeps the error site
            # close to the call site rather than deep in the XML
            # builder.
            if not preset or "E" not in preset:
                raise ValueError(
                    "motion path must be a non-empty OOXML path string "
                    "ending in 'E' (e.g. 'M 0 0 L 0.5 0 E')"
                )
            self.add_motion(cast("BaseShape", shape), preset, **kwargs)
            return
        raise ValueError(
            f"Unknown animation kind {kind!r}; choose from "
            "'entrance', 'exit', 'emphasis', 'motion'."
        )

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
        easing: str | tuple[float, float] | None = None,
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
            bshape.shape_id, preset_id, "entr", preset_subtype, trigger, delay,
            behaviors, easing=easing,
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
        if self._grp_active:
            raise RuntimeError("cannot enter sequence() inside group()")
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

    @contextmanager
    def group(
        self,
        *,
        start: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.AFTER_PREVIOUS,
        delay: int = 0,
    ) -> Iterator["SlideAnimations"]:
        """Animate every effect added in the block as a single visual cluster.

        The first effect added inside the ``with`` block uses *start*
        (default :attr:`Trigger.AFTER_PREVIOUS`) and every subsequent
        effect defaults to :attr:`Trigger.WITH_PREVIOUS`, so the whole
        cluster animates as one unit.  Pair this with a per-cluster
        anchor delay to control the rhythm between clusters::

            for i, card in enumerate(cards):
                with slide.animations.group(delay=0 if i == 0 else 200):
                    Entrance.fade(slide, card.body)
                    Entrance.fade(slide, card.title)
                    Entrance.fade(slide, card.blurb)

        ``group()`` is the right primitive when sub-shapes belong to the
        same visual unit (a card, a row, a panel) — emitting a single
        ``WITH_PREVIOUS`` cluster is much cheaper for PowerPoint to
        render than the same number of independent click-groups.

        Effects whose *trigger* is supplied explicitly still honour the
        caller's choice; the group default only applies to unset triggers.

        Cannot be nested or combined with :meth:`sequence` —
        :class:`RuntimeError` is raised on either.
        """
        if self._grp_active:
            raise RuntimeError("animation groups cannot be nested")
        if self._seq_active:
            raise RuntimeError("cannot enter group() inside sequence()")
        self._grp_active = True
        self._grp_start = start
        self._grp_delay = delay
        self._grp_delay_consumed = False
        self._grp_count = 0
        try:
            yield self
        finally:
            self._grp_active = False
            self._grp_count = 0
            self._grp_delay = 0
            self._grp_delay_consumed = False

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

        from power_pptx.text.text import TextFrame as _TextFrame

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

        When called outside a sequence/group, an unset trigger falls back to
        ``Trigger.ON_CLICK``.  Inside a sequence, the first effect uses
        the sequence's ``start`` trigger and subsequent effects default
        to ``Trigger.AFTER_PREVIOUS``.  Inside a group, the first effect
        uses the group's ``start`` trigger and subsequent effects default
        to ``Trigger.WITH_PREVIOUS`` so the whole cluster animates as
        one unit.

        Counters bump on **every** call inside a block, even when the
        caller supplied an explicit trigger.  Otherwise an explicit
        trigger on the first effect would let the *next* unset-trigger
        effect get the "first effect" treatment instead of being
        ``WITH_PREVIOUS`` / ``AFTER_PREVIOUS`` as documented.
        """
        if self._grp_active:
            is_first = self._grp_count == 0
            self._grp_count += 1
            if trigger is not _TRIGGER_UNSET:
                return trigger
            return self._grp_start if is_first else PP_ANIM_TRIGGER.WITH_PREVIOUS
        if self._seq_active:
            is_first = self._seq_count == 0
            self._seq_count += 1
            if trigger is not _TRIGGER_UNSET:
                return trigger
            return self._seq_start if is_first else PP_ANIM_TRIGGER.AFTER_PREVIOUS
        if trigger is not _TRIGGER_UNSET:
            return trigger
        return PP_ANIM_TRIGGER.ON_CLICK

    def _consume_block_delay(self, delay: int) -> int:
        """Add the active sequence/group ``delay`` to the first effect's *delay*.

        ``sequence(delay=N)`` and ``group(delay=N)`` shift the whole
        block by N ms, so the block-level delay is added to the first
        effect's per-call ``delay`` and never applied again within the
        same block.  Returns *delay* unchanged when no block is active.
        """
        if self._grp_active and not self._grp_delay_consumed:
            self._grp_delay_consumed = True
            return delay + self._grp_delay
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
        *,
        easing: str | tuple[float, float] | None = None,
    ) -> None:
        """Build the animation XML and insert it into the slide timing tree."""
        root_ctn = self._get_or_create_root_ctn()

        trigger = self._resolve_default_trigger(trigger)
        delay = self._consume_block_delay(delay)
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
        if easing is not None:
            _apply_easing(group_elm, easing)
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

    # ---- multi-shape sequence helpers --------------------------------------

    def typewriter(
        self,
        shapes,
        *,
        preset: str = "wipe",
        delay_between_ms: int = 200,
        duration: int = 300,
        start: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
        direction: str = "left",
    ) -> None:
        """One-line cascade entrance across an iterable of *shapes*.

        Replaces the manual ``with self.sequence(): for s in shapes: ...``
        boilerplate.  Each shape's entrance fires ``delay_between_ms``
        after the previous one, all under a single click trigger
        (``start``).

        Default uses the ``"wipe"`` preset, which is the closest visual
        analogue to a typewriter reveal; pass any other entrance preset
        (``"fade"``, ``"appear"``, etc.) for the effect of your choice.

        Example::

            slide.animations.typewriter(
                [bullet1, bullet2, bullet3], delay_between_ms=200
            )
        """
        shapes = list(shapes)
        if not shapes:
            return
        with self.sequence(start=start):
            for i, shape in enumerate(shapes):
                self.add_entrance(
                    preset,
                    shape,
                    delay=0 if i == 0 else delay_between_ms,
                    duration=duration,
                    direction=direction,
                )

    # ---- orphan cleanup ----------------------------------------------------

    def purge_orphans(self) -> int:
        """Remove animation entries whose target shape no longer exists.

        Walks the slide's timing tree and removes any top-level click-group
        ``<p:par>`` that contains a ``spid`` reference to a shape that's no
        longer in the slide's shape tree.  Use this after deleting shapes
        to clean up the timing tree (PowerPoint will silently "repair"
        a deck with orphan timing references, but a clean tree avoids
        that prompt).

        Returns the number of orphan ``<p:par>`` entries removed.

        This is also called automatically when a shape is removed via
        :meth:`BaseShape.delete`, but is exposed publicly for callers
        that delete shapes by other means.
        """
        sld = self._slide._element
        # Collect live shape ids from the spTree.
        live_ids: set[int] = set()
        for cNvPr in sld.xpath("p:cSld/p:spTree//p:cNvPr"):
            try:
                live_ids.add(int(cNvPr.get("id")))
            except (TypeError, ValueError):
                continue

        # The click-group <p:par> elements live as children of the root
        # timing's childTnLst: p:timing/p:tnLst/p:par/p:cTn/p:childTnLst/p:par.
        root_pars = sld.xpath("p:timing/p:tnLst/p:par/p:cTn/p:childTnLst/p:par")

        removed = 0
        spTgt_tag = qn("p:spTgt")
        for top_par in list(root_pars):
            spTgts = list(top_par.iter(spTgt_tag))
            for spTgt in spTgts:
                spid_attr = spTgt.get("spid")
                try:
                    spid = int(spid_attr) if spid_attr is not None else None
                except ValueError:
                    continue
                if spid is not None and spid not in live_ids:
                    parent = top_par.getparent()
                    if parent is not None:
                        parent.remove(top_par)
                        removed += 1
                    break  # already removed; no need to check more spTgts
        return removed

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
# Read-side introspection view
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnimationEntry:
    """Read-only view onto a single animation entry on a slide.

    Yielded by iteration over :class:`SlideAnimations`.  Exposes the
    fields most useful for debugging and copying animations between
    slides:

    * :attr:`kind` — one of ``"entrance"``, ``"exit"``, ``"emphasis"``,
      ``"motion"`` (or ``None`` for unknown preset classes)
    * :attr:`preset` — the preset name (``"fade"``, ``"fly_in"``,
      ``"pulse"`` etc.) or ``None`` if the presetID isn't recognised
    * :attr:`trigger` — the :class:`PP_ANIM_TRIGGER` for this entry
    * :attr:`shape_id` — the target shape's id, or ``None`` if the
      entry has no ``<p:spTgt>`` (rare)
    * :attr:`duration` — milliseconds, from the inner cTn ``dur`` attr
    * :attr:`delay` — milliseconds, from the inner cTn's first
      ``<p:cond delay="...">``
    * :attr:`shape` — looked up live from the slide's shape tree by id;
      may be ``None`` if the shape has been deleted (use
      :meth:`SlideAnimations.purge_orphans` to drop orphan entries).
    """

    _par_element: Any  # the wrapping <p:par> click-group element
    _slide: Any

    @property
    def trigger(self) -> Optional[PP_ANIM_TRIGGER]:
        # The nodeType lives on the inner effect cTn (same one carrying
        # presetID).  The outer click-group cTn just wraps timing.
        ctn = self._inner_effect_ctn()
        if ctn is None:
            return None
        return _NODE_TYPE_TO_TRIGGER.get(ctn.get("nodeType"))

    @property
    def kind(self) -> Optional[str]:
        cls = self._effect_attr("presetClass")
        return _PRESET_CLASS_TO_KIND.get(cls) if cls else None

    @property
    def preset(self) -> Optional[str]:
        cls = self._effect_attr("presetClass")
        if cls == "path":
            return "custom"  # MotionPath presets aren't named the same way
        pid = self._effect_attr("presetID")
        sub = self._effect_attr("presetSubtype")
        if cls is None or pid is None:
            return None
        try:
            pid_i = int(pid)
            sub_i = int(sub) if sub is not None else 0
        except ValueError:
            return None
        # Prefer exact (pid, subtype) match — handles fly_in's directional
        # subtypes — then fall back to the subtype-agnostic match for
        # presets like fade where subtype is always 0.
        by_pair = _REVERSE_PRESETS.get(cls, {})
        name = by_pair.get((pid_i, sub_i))
        if name is not None:
            return name
        return _REVERSE_PRESET_BY_ID.get(cls, {}).get(pid_i)

    @property
    def shape_id(self) -> Optional[int]:
        spTgt = self._par_element.find(".//" + qn("p:spTgt"))
        if spTgt is None:
            return None
        spid = spTgt.get("spid")
        try:
            return int(spid) if spid is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def duration(self) -> Optional[int]:
        ctn = self._inner_effect_ctn()
        if ctn is None:
            return None
        # The wrapper cTn has dur="indefinite"; the actual animation
        # duration lives on a nested behaviour cTn.  Find the deepest
        # cTn with a numeric dur attribute.
        best: Optional[int] = None
        for child in self._par_element.iter(qn("p:cTn")):
            dur = child.get("dur")
            if dur is None or dur == "indefinite":
                continue
            try:
                val = int(dur)
            except ValueError:
                continue
            # Skip the wrapper's "0" placeholder; pick the largest concrete
            # duration in the subtree, which corresponds to the visible
            # effect duration.
            if val > 0 and (best is None or val > best):
                best = val
        return best

    @property
    def delay(self) -> int:
        ctn = self._inner_effect_ctn()
        if ctn is None:
            return 0
        cond = ctn.find(".//" + qn("p:stCondLst") + "/" + qn("p:cond"))
        if cond is None:
            return 0
        delay = cond.get("delay")
        try:
            return int(delay) if delay is not None and delay != "indefinite" else 0
        except ValueError:
            return 0

    @property
    def shape(self) -> Any:
        """Look up the live |BaseShape| for this entry on its slide.

        Walks the slide's spTree elements directly to locate the shape
        with a matching id and only then constructs a proxy — so the
        cost is one proxy construction per access, not ``N`` (where
        ``N`` is the number of shapes on the slide).  Returns ``None``
        when the shape has been deleted.  Callers iterating many
        entries on a dense slide can still build their own
        ``shape_id`` → shape map from a single ``slide.shapes`` walk
        if they want to amortise across accesses.
        """
        spid = self.shape_id
        if spid is None:
            return None
        shapes = self._slide.shapes
        for shape_elm in shapes._iter_member_elms():
            elm_id = getattr(shape_elm, "shape_id", None)
            if elm_id == spid:
                return shapes._shape_factory(shape_elm)
        return None

    @property
    def element(self) -> Any:
        """The underlying ``<p:par>`` element.  Treat as read-only."""
        return self._par_element

    def remove(self) -> None:
        """Remove this animation entry from the slide."""
        parent = self._par_element.getparent()
        if parent is not None:
            parent.remove(self._par_element)

    # -- internal helpers --------------------------------------------------

    def _effect_attr(self, name: str) -> Optional[str]:
        ctn = self._inner_effect_ctn()
        return ctn.get(name) if ctn is not None else None

    def _inner_effect_ctn(self) -> Any:
        """Return the inner cTn carrying presetID/presetClass attributes."""
        for ctn in self._par_element.iter(qn("p:cTn")):
            if ctn.get("presetID") is not None:
                return ctn
        return None


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

        from power_pptx.animation import MotionPath, Trigger
        from power_pptx.util import Inches

        # Slide it two inches to the right and one inch down
        MotionPath.line(slide, badge, Inches(2), Inches(1))

        # Or hand-roll a path: a quarter-circle to the right
        MotionPath.custom(
            slide, badge, "M 0 0 C 0 -0.2 0.2 -0.2 0.2 0 E"
        )

        # Built-in path presets:
        MotionPath.arc(slide, badge, Inches(2), 0, height=0.5)
        MotionPath.circle(slide, badge, Inches(1))
        MotionPath.zigzag(slide, badge, Inches(3), 0, segments=4)
        MotionPath.spiral(slide, badge, Inches(2), turns=2)
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
        — typically built with :func:`power_pptx.util.Inches`,
        :func:`power_pptx.util.Pt`, etc.  They are normalized to the slide's
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

        *path* is a PowerPoint motion-path expression — the same syntax
        the ``<p:animMotion>`` element uses internally.  Coordinates are
        slide-normalized: ``(0, 0)`` is the shape's starting position,
        ``(1, 0)`` is one slide-width to the right, ``(0, 1)`` is one
        slide-height down.  The terminating ``E`` (path end) is required,
        e.g. ``"M 0 0 L 0.5 0 E"`` for a horizontal half-slide hop.

        For the more common SVG path syntax — absolute / relative
        commands, no terminator, pixel-style coordinates — use
        :meth:`svg` instead.
        """
        if not path or "E" not in path:
            raise ValueError(
                "motion path must be a non-empty OOXML path string ending in 'E'"
            )
        slide.animations.add_motion(
            shape, path, trigger=trigger, delay=delay, duration=duration
        )

    @classmethod
    def svg(
        cls,
        slide: Slide,
        shape: BaseShape,
        path: str,
        *,
        viewbox: tuple[float, float, float, float] | None = None,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 2000,
    ) -> None:
        """Move *shape* along an SVG-style motion path.

        Accepts the standard SVG path mini-language with the commands
        most commonly seen in design-tool exports:

        * ``M / m`` — moveto (absolute / relative)
        * ``L / l`` — lineto
        * ``H / h`` — horizontal lineto
        * ``V / v`` — vertical lineto
        * ``C / c`` — cubic bezier curveto
        * ``Q / q`` — quadratic bezier curveto
        * ``Z / z`` — closepath (returns to the most-recent moveto)

        Coordinates are interpreted against *viewbox* (a 4-tuple
        ``(min_x, min_y, width, height)``).  When *viewbox* is ``None``
        the path is assumed to live in the unit square ``(0, 0, 1, 1)``,
        which mirrors PowerPoint's slide-normalised coordinate system —
        useful for paths hand-authored in the same coordinate space.

        The first point of the SVG path becomes the shape's starting
        position (``M 0 0`` in OOXML terms) so ``MotionPath.svg(slide,
        shape, "M 0 0 L 100 0", viewbox=(0, 0, 100, 100))`` is
        equivalent to ``MotionPath.line(slide, shape, slide_w, 0)``.

        The ``E`` terminator that OOXML expects is appended automatically;
        callers don't need to include one in *path*.
        """
        normalised = _svg_to_ooxml_motion_path(path, viewbox=viewbox)
        slide.animations.add_motion(
            shape, normalised, trigger=trigger, delay=delay, duration=duration
        )

    @classmethod
    def diagonal(
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
        """Move *shape* diagonally by ``(dx, dy)`` EMU.

        Functionally equivalent to :meth:`line` — exposed as its own
        preset because diagonal motion is a common authoring intent and
        callers reading recipe code shouldn't have to puzzle out which
        direction a "line" travels.
        """
        cls.line(
            slide, shape, dx, dy,
            trigger=trigger, delay=delay, duration=duration,
        )

    @classmethod
    def circle(
        cls,
        slide: Slide,
        shape: BaseShape,
        radius: int,
        *,
        clockwise: bool = True,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 2000,
    ) -> None:
        """Move *shape* in a closed circle of *radius* EMU.

        The shape's starting position sits on the rim at the 9 o'clock
        position; setting *clockwise=False* reverses the direction.  The
        radius is normalized separately against the slide width and
        height, which keeps the path physically circular on widescreen
        and 4:3 slides alike.
        """
        slide_w, slide_h = _slide_dimensions_emu(slide)
        rx = float(radius) / slide_w
        ry = float(radius) / slide_h
        # Build a closed cubic-bezier circle approximation.  The 0.5523
        # constant (4/3 * tan(pi/8)) is the standard control-handle
        # length that yields a near-perfect circle from four cubics.
        k = 0.5522847498
        # Sign flip swaps direction without changing the start point.
        s = 1 if clockwise else -1
        path = (
            f"M 0 0 "
            f"C 0 {-s * k * ry:g} {rx - k * rx:g} {-s * ry:g} {rx:g} {-s * ry:g} "
            f"C {rx + k * rx:g} {-s * ry:g} {2 * rx:g} {-s * (ry - k * ry):g} "
            f"{2 * rx:g} 0 "
            f"C {2 * rx:g} {s * (ry - k * ry):g} {rx + k * rx:g} {s * ry:g} "
            f"{rx:g} {s * ry:g} "
            f"C {rx - k * rx:g} {s * ry:g} 0 {s * (ry - k * ry):g} 0 0 E"
        )
        slide.animations.add_motion(
            shape, path, trigger=trigger, delay=delay, duration=duration
        )

    @classmethod
    def arc(
        cls,
        slide: Slide,
        shape: BaseShape,
        dx: int,
        dy: int,
        *,
        height: float = 0.5,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 2000,
    ) -> None:
        """Move *shape* along a parabolic arc to ``(dx, dy)``.

        *height* controls the arc's peak as a fraction of the chord
        length: ``0.5`` is a gentle hump, ``1.0`` a tall throw.  Negative
        values flip the arc to the opposite side of the chord.

        The peak is placed perpendicular to the chord, so the curve
        keeps its shape for any chord direction including pure vertical
        moves (``dx=0``).
        """
        slide_w, slide_h = _slide_dimensions_emu(slide)
        nx = float(dx) / slide_w
        ny = float(dy) / slide_h
        # Control point offset perpendicular to the chord.  The (ny, -nx)
        # vector has length equal to the chord, so multiplying it by
        # `height` gives a perpendicular offset of `height * chord_length`
        # — non-degenerate for any chord direction, including pure
        # vertical (where the previous `abs(nx) * height` collapsed to 0).
        cx = nx / 2 + height * ny
        cy = ny / 2 - height * nx
        path = f"M 0 0 Q {cx:g} {cy:g} {nx:g} {ny:g} E"
        slide.animations.add_motion(
            shape, path, trigger=trigger, delay=delay, duration=duration
        )

    @classmethod
    def zigzag(
        cls,
        slide: Slide,
        shape: BaseShape,
        dx: int,
        dy: int,
        *,
        segments: int = 4,
        amplitude: float = 0.05,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 2000,
    ) -> None:
        """Move *shape* along a zigzag from origin to ``(dx, dy)``.

        *segments* is the number of zigzag legs (must be ≥ 1).
        *amplitude* is the perpendicular swing as a fraction of the
        slide's smaller dimension.
        """
        if segments < 1:
            raise ValueError("segments must be >= 1")
        slide_w, slide_h = _slide_dimensions_emu(slide)
        nx = float(dx) / slide_w
        ny = float(dy) / slide_h
        length = (nx * nx + ny * ny) ** 0.5 or 1.0
        # Perpendicular unit vector to (nx, ny).
        px, py = -ny / length, nx / length
        parts = ["M 0 0"]
        for i in range(1, segments + 1):
            t = i / segments
            mid_x = nx * t
            mid_y = ny * t
            swing = amplitude if i % 2 == 1 else -amplitude
            if i < segments:
                mid_x += px * swing
                mid_y += py * swing
            parts.append(f"L {mid_x:g} {mid_y:g}")
        parts.append("E")
        path = " ".join(parts)
        slide.animations.add_motion(
            shape, path, trigger=trigger, delay=delay, duration=duration
        )

    @classmethod
    def spiral(
        cls,
        slide: Slide,
        shape: BaseShape,
        radius: int,
        *,
        turns: float = 2.0,
        clockwise: bool = True,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 2500,
    ) -> None:
        """Move *shape* along an Archimedean spiral.

        The spiral begins at the shape's starting position and unwinds
        outward, ending *radius* EMU away (along the +x axis for an
        integer *turns* count).  Use a negative *turns* value to wind
        inward; *clockwise=False* reverses the rotation direction.
        """
        if turns == 0:
            raise ValueError("turns must be non-zero")
        slide_w, slide_h = _slide_dimensions_emu(slide)
        rx = float(radius) / slide_w
        ry = float(radius) / slide_h
        # Sample enough points for a smooth spiral.  16 per turn is
        # visually indistinguishable from a true Archimedean spiral.
        steps = max(16, int(abs(turns) * 16))
        s = 1 if clockwise else -1
        parts = ["M 0 0"]
        for i in range(1, steps + 1):
            t = i / steps
            angle = 2 * math.pi * turns * t
            # Archimedean spiral: radius grows linearly while the angle
            # sweeps `turns` full revolutions.  At t=1 with integer
            # turns this lands at (rx, 0) — one radius from the start.
            x = rx * t * math.cos(angle)
            y = s * ry * t * math.sin(angle)
            parts.append(f"L {x:g} {y:g}")
        parts.append("E")
        path = " ".join(parts)
        slide.animations.add_motion(
            shape, path, trigger=trigger, delay=delay, duration=duration
        )


# Match SVG path command letters (any letter, so unsupported ones can be
# diagnosed) and signed/exponent-form numbers.
_SVG_TOKEN_RE = __import__("re").compile(
    r"[A-Za-z]|-?\d*\.?\d+(?:[eE][+-]?\d+)?"
)


def _svg_to_ooxml_motion_path(
    svg: str,
    *,
    viewbox: tuple[float, float, float, float] | None = None,
) -> str:
    """Convert an SVG path string into an OOXML motion-path expression.

    Supports M/m, L/l, H/h, V/v, C/c, Q/q, Z/z.  The resulting OOXML
    path is rebased so the first moveto becomes ``M 0 0`` (PowerPoint
    motion-paths are relative to the shape's starting position) and
    coordinates are mapped from *viewbox* into the unit square.

    When *viewbox* is ``None`` the path is assumed to already live in
    the unit square ``(0, 0, 1, 1)`` — the OOXML coordinate system —
    which is convenient for hand-authored paths.
    """
    if not svg or not svg.strip():
        raise ValueError("svg path must be a non-empty string")

    if viewbox is None:
        vb_x, vb_y, vb_w, vb_h = 0.0, 0.0, 1.0, 1.0
    else:
        vb_x, vb_y, vb_w, vb_h = (float(v) for v in viewbox)
    if vb_w <= 0 or vb_h <= 0:
        raise ValueError(
            "viewbox width and height must be positive; got "
            f"{viewbox!r}"
        )

    tokens = _SVG_TOKEN_RE.findall(svg)
    if not tokens:
        raise ValueError(f"no recognisable commands in svg path {svg!r}")

    out_parts: list[str] = []
    # Track the SVG-coord cursor (cx, cy), the rebase origin (origin_x,
    # origin_y) — i.e. where the first moveto landed in SVG coords —
    # and the most-recent subpath start for ``Z`` closure.
    cx = cy = 0.0
    origin_x: float | None = None
    origin_y: float | None = None
    subpath_x = subpath_y = 0.0
    started = False

    def _emit(letter: str, *coords: float) -> None:
        # Translate (cx, cy) in SVG coords to OOXML unit-square coords
        # relative to the rebase origin.  ``g`` formatting keeps
        # ``-0`` from sneaking in.
        out_parts.append(letter)
        for c in coords:
            out_parts.append(f"{c:g}")

    def _to_ooxml(x: float, y: float) -> tuple[float, float]:
        # Rebase to origin then map viewbox → unit square.
        assert origin_x is not None and origin_y is not None
        return (x - origin_x) / vb_w, (y - origin_y) / vb_h

    i = 0
    cmd: str = ""
    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            cmd = tok
            i += 1
        # H / V take a single number; Z takes none.
        if cmd in ("Z", "z"):
            # Close current subpath: SVG draws a line back to the
            # subpath origin.
            cx, cy = subpath_x, subpath_y
            ox, oy = _to_ooxml(cx, cy)
            _emit("L", ox, oy)
            continue
        try:
            n = float(tokens[i])
        except (IndexError, ValueError):
            raise ValueError(
                f"expected coordinate after {cmd!r} in svg path {svg!r}"
            )
        i += 1

        if cmd in ("M", "m"):
            # First number is the new cursor; subsequent number-pairs
            # under the same M command are implicit linetos.
            try:
                m = float(tokens[i])
            except (IndexError, ValueError):
                raise ValueError(
                    f"expected y after x in moveto in svg path {svg!r}"
                )
            i += 1
            new_x = n if cmd == "M" else cx + n
            new_y = m if cmd == "M" else cy + m
            if not started:
                origin_x, origin_y = new_x, new_y
                subpath_x, subpath_y = new_x, new_y
                cx, cy = new_x, new_y
                _emit("M", 0.0, 0.0)
                started = True
            else:
                cx, cy = new_x, new_y
                subpath_x, subpath_y = new_x, new_y
                ox, oy = _to_ooxml(cx, cy)
                _emit("M", ox, oy)
            # Implicit lineto continuation: M behaves as L for
            # subsequent coord pairs.
            cmd = "L" if cmd == "M" else "l"
            continue

        if not started:
            # Any non-M command must be preceded by a moveto in valid SVG.
            raise ValueError(
                f"svg path must start with M/m; got {cmd!r} in {svg!r}"
            )

        if cmd in ("L", "l"):
            try:
                m = float(tokens[i])
            except (IndexError, ValueError):
                raise ValueError(
                    f"expected y after x in lineto in svg path {svg!r}"
                )
            i += 1
            cx = n if cmd == "L" else cx + n
            cy = m if cmd == "L" else cy + m
            ox, oy = _to_ooxml(cx, cy)
            _emit("L", ox, oy)
        elif cmd in ("H", "h"):
            cx = n if cmd == "H" else cx + n
            ox, oy = _to_ooxml(cx, cy)
            _emit("L", ox, oy)
        elif cmd in ("V", "v"):
            cy = n if cmd == "V" else cy + n
            ox, oy = _to_ooxml(cx, cy)
            _emit("L", ox, oy)
        elif cmd in ("C", "c"):
            # Cubic: x1 y1 x2 y2 x y
            try:
                pts = [n] + [float(tokens[i + k]) for k in range(5)]
            except (IndexError, ValueError):
                raise ValueError(
                    f"cubic curve needs 6 coords in svg path {svg!r}"
                )
            i += 5
            x1, y1, x2, y2, x, y = pts
            if cmd == "c":
                x1 += cx; y1 += cy
                x2 += cx; y2 += cy
                x += cx; y += cy
            cx, cy = x, y
            o1x, o1y = _to_ooxml(x1, y1)
            o2x, o2y = _to_ooxml(x2, y2)
            ox, oy = _to_ooxml(x, y)
            _emit("C", o1x, o1y, o2x, o2y, ox, oy)
        elif cmd in ("Q", "q"):
            # Quadratic: x1 y1 x y
            try:
                pts = [n] + [float(tokens[i + k]) for k in range(3)]
            except (IndexError, ValueError):
                raise ValueError(
                    f"quadratic curve needs 4 coords in svg path {svg!r}"
                )
            i += 3
            x1, y1, x, y = pts
            if cmd == "q":
                x1 += cx; y1 += cy
                x += cx; y += cy
            cx, cy = x, y
            o1x, o1y = _to_ooxml(x1, y1)
            ox, oy = _to_ooxml(x, y)
            _emit("Q", o1x, o1y, ox, oy)
        else:
            raise ValueError(
                f"unsupported svg path command {cmd!r}; supported: "
                "M/m L/l H/h V/v C/c Q/q Z/z"
            )

    out_parts.append("E")
    return " ".join(out_parts)


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
