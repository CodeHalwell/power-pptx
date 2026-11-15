"""High-level animation API for python-pptx.

.. warning::

   **Experimental — playback is currently broken in PowerPoint.**
   Animation timing XML produced by this module round-trips through
   the OOXML schema, reads back correctly via the introspection API,
   and converts cleanly to PDF via LibreOffice.  But in PowerPoint
   slideshow mode, animated shapes sit at 10–15% opacity for several
   seconds and then snap to fully visible all at once, instead of
   playing the requested animation.  Decks containing entrance
   animations on the same slide as a Morph transition can additionally
   trigger PowerPoint's "Repair?" dialog on open.

   Until this is resolved, prefer slide :class:`transitions
   <power_pptx.slide.SlideTransition>` (which round-trip and play
   correctly) and treat the animation API as a code-shape preview
   only.  See ``IMPROVEMENT_PLAN.md`` (item 1) for the diagnostic plan.

Exposes entrance, exit, and emphasis preset animations that map to
PowerPoint's built-in animation library.  Generated XML is valid
OOXML and persists/reads back correctly at the XML level via the
introspection API — but that is a *schema-validity* guarantee, not a
guarantee of PowerPoint open/save round-tripping or slideshow
playback (see the warning above).

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
import numbers
import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterator, Optional, cast
from xml.sax.saxutils import quoteattr

from power_pptx.enum.animation import PP_ANIM_TRIGGER
from power_pptx.oxml import parse_xml
from power_pptx.oxml.ns import nsdecls, qn

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
                "explicit (accel, decel) tuple" % (easing, sorted(_EASING_PRESETS))
            )
    if (
        isinstance(easing, tuple)
        and len(easing) == 2
        and all(isinstance(v, (int, float)) for v in easing)
    ):
        accel, decel = float(easing[0]), float(easing[1])
        if not (0.0 <= accel <= 1.0 and 0.0 <= decel <= 1.0 and accel + decel <= 1.0):
            raise ValueError("easing accel and decel must each be in [0, 1] and sum to ≤ 1")
        return accel, decel
    raise TypeError(
        "easing must be a preset name (e.g. 'ease_in_out') or an (accel, decel) 2-tuple of floats"
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
    "withEffect": PP_ANIM_TRIGGER.WITH_PREVIOUS,
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

# (presetID, presetSubtype) of each preset.  These numbers are what tells
# PowerPoint (and LibreOffice) which effect of its gallery an effect is: they
# name it in the animation pane and decide what its effect options edit.  The
# values below are the ones LibreOffice's PPTX import and export tables give
# for the effect each preset builds, checked by converting decks with
# LibreOffice in both directions.  `presetSubtype` names the direction of a
# directional preset (see _DIRECTION_SUBTYPES), the number of spokes of a
# wheel, and "in" (16) or "out" (32) for a zoom.
_ENTRANCE_PRESETS = {
    "appear": (1, 0),
    "fade": (10, 0),
    "fly_in": (2, 4),  # Fly In, from the bottom unless directed otherwise
    "float_in": (42, 0),  # fade in while rising into place ("Ascend")
    "wipe": (22, 8),  # Wipe, from the left
    "zoom": (23, 16),  # Zoom, in
    "wheel": (21, 1),  # Wheel, 1 spoke
    "random_bars": (14, 5),  # Random Bars, horizontal
}

_EXIT_PRESETS = {
    "disappear": (1, 0),
    "fade": (10, 0),
    "fly_out": (2, 4),  # Fly Out, to the bottom unless directed otherwise
    "float_out": (42, 0),  # fade out while sinking away ("Descend")
    "wipe": (22, 8),  # Wipe, from the left
    "zoom": (23, 32),  # Zoom, out
    "wheel": (21, 1),  # Wheel, 1 spoke
    "random_bars": (14, 5),  # Random Bars, horizontal
}

_EMPHASIS_PRESETS = {
    "pulse": (26, 0),  # an auto-reversing scale ("Flash Bulb" to LibreOffice)
    "spin": (8, 0),
    "teeter": (32, 0),
}

# presetSubtype of a direction: the edge an entrance comes in from, or the one
# an exit leaves by.
_DIRECTION_SUBTYPES = {"top": 1, "right": 2, "bottom": 4, "left": 8}

# Presets whose `direction` chooses that edge, with the one they take when no
# direction is given.  Every other preset ignores `direction`.
_DIRECTIONAL_PRESETS = {"fly_in": "bottom", "fly_out": "bottom", "wipe": "left"}

# animEffect filter of a wipe from each edge.  The filter names the edge the
# wipe starts from, "up" and "down" standing for the top and the bottom: that
# is how LibreOffice reads them and writes its own wipes.
_WIPE_FILTERS = {
    "left": "wipe(left)",
    "right": "wipe(right)",
    "top": "wipe(up)",
    "bottom": "wipe(down)",
}


def _resolve_direction(preset: str, direction: str | None) -> str | None:
    """The direction *preset* is to take: *direction*, or the preset's own default.

    |None| for a preset that has no direction, which ignores the argument.
    Raises |ValueError| for a direction a directional preset cannot take,
    rather than quietly using its default.
    """
    default = _DIRECTIONAL_PRESETS.get(preset)
    if default is None:
        return None
    if direction is None:
        return default
    if direction not in _DIRECTION_SUBTYPES:
        raise ValueError(
            f"direction for {preset!r} must be one of {sorted(_DIRECTION_SUBTYPES)}; "
            f"got {direction!r}"
        )
    return direction


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

# animEffect filter for each preset drawn by one.  The value is a
# "type(subtype)" name a consumer looks up in its table of reserved filters
# (ISO/IEC 29500-1 §19.5.3); a name it does not know plays as no effect at
# all.  LibreOffice spells random bars "randombar", not the "randomBars" of
# the standard's table, and draws horizontal bars with the "vertical" bar
# wipe.  A zoom is not a filter: it animates the width and height.
_EFFECT_FILTER = {
    "fade": "fade",
    "float_in": "fade",
    "float_out": "fade",
    "wipe": "wipe(left)",
    "wheel": "wheel(1)",
    "random_bars": "randombar(vertical)",
}


def _effect_filter(preset: str, direction: str | None = None) -> str:
    """The animEffect filter of *preset*, taking *direction* for a wipe."""
    if preset == "wipe":
        return _WIPE_FILTERS[direction or "left"]
    return _EFFECT_FILTER.get(preset, "fade")


# FlyIn/FlyOut path templates (M start L end E)
_FLY_PATHS_IN = {
    "bottom": "M 0 1 L 0 0 E",
    "top": "M 0 -1 L 0 0 E",
    "left": "M -1 0 L 0 0 E",
    "right": "M 1 0 L 0 0 E",
}
_FLY_PATHS_OUT = {
    "bottom": "M 0 0 L 0 1 E",
    "top": "M 0 0 L 0 -1 E",
    "left": "M 0 0 L -1 0 E",
    "right": "M 0 0 L 1 0 E",
}

# ---------------------------------------------------------------------------
# Value checks
# ---------------------------------------------------------------------------

#: Largest time, in milliseconds, a timing attribute can hold: ``ST_TLTime``
#: is an ``xsd:unsignedInt`` (or the keyword ``indefinite``).
_MAX_TIME_MS = 2**32 - 1

#: Largest magnitude of an ``ST_Angle``, an ``xsd:int`` counting 60000ths of
#: a degree — just under a hundred full turns.
_MAX_ANGLE = 2**31 - 1


def _milliseconds(value: Any, name: str) -> int:
    """Return *value* as the whole number of milliseconds a timing attribute takes.

    A `dur` or `delay` must be a non-negative integer, so a float is rounded:
    ordinary arithmetic like ``1500 / 3`` or ``0.2 * 1000`` yields one, and
    written out as ``"500.0"`` it would make the slide schema-invalid.
    Raises |TypeError| for a non-number and |ValueError| for a number that is
    negative, too large for the attribute, or not finite.
    """
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise TypeError(f"{name} must be a number of milliseconds, got {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number of milliseconds, got {value!r}")
    ms = int(round(value))
    if not 0 <= ms <= _MAX_TIME_MS:
        raise ValueError(f"{name} must be between 0 and {_MAX_TIME_MS} milliseconds, got {value!r}")
    return ms


def _angle_units(degrees: Any, name: str = "degrees") -> int:
    """Return *degrees* in the 60000ths of a degree a rotation attribute takes.

    Raises |TypeError| for a non-number and |ValueError| for an angle that is
    not finite or does not fit the attribute.
    """
    if isinstance(degrees, bool) or not isinstance(degrees, numbers.Real):
        raise TypeError(f"{name} must be a number of degrees, got {degrees!r}")
    if not math.isfinite(degrees):
        raise ValueError(f"{name} must be a finite number of degrees, got {degrees!r}")
    units = int(round(degrees * 60000))
    if abs(units) > _MAX_ANGLE:
        limit = _MAX_ANGLE // 60000
        raise ValueError(f"{name} must be between -{limit} and {limit} degrees, got {degrees!r}")
    return units


def _paragraph_target(target: BaseShape | TextFrame) -> tuple[BaseShape, TextFrame]:
    """The shape to animate, and the text frame whose paragraphs to reveal, for *target*.

    *target* is a text frame, or a shape that has one.  Raises |TypeError|
    for anything else.
    """
    from power_pptx.text.text import TextFrame as _TextFrame

    if isinstance(target, _TextFrame):
        return _shape_of_text_frame(target), target
    text_frame = getattr(target, "text_frame", None)
    if text_frame is None or not hasattr(target, "shape_id"):
        raise TypeError(
            "by_paragraph=True requires a TextFrame or a shape with "
            f"a text_frame and shape_id; got {type(target).__name__!r}"
        )
    return cast("BaseShape", target), text_frame


def _shape_of_text_frame(text_frame: TextFrame) -> BaseShape:
    """The slide-level shape *text_frame* belongs to.

    That is the first thing with a `shape_id` (a |BaseShape|) up its parent
    chain, which may pass through parents that have none (a table cell's
    text frame has a `_Cell` parent).  Raises |TypeError| when nothing in the
    chain has one, so the text frame is not attached to a slide-level shape
    (table-cell text frames are not yet supported), or the chain loops.
    """
    parent = text_frame._parent  # type: ignore[attr-defined]
    seen: set[int] = set()
    while parent is not None and id(parent) not in seen:
        if hasattr(parent, "shape_id"):
            return cast("BaseShape", parent)
        seen.add(id(parent))
        parent = getattr(parent, "_parent", None)
    raise TypeError(
        "by_paragraph=True requires a TextFrame whose parent "
        "chain reaches a shape; "
        f"{type(text_frame._parent).__name__!r} has no shape_id "  # type: ignore[attr-defined]
        "ancestor (table-cell text frames are not yet supported)."
    )


# ---------------------------------------------------------------------------
# Internal XML builders
# ---------------------------------------------------------------------------


def _nsdecls_p() -> str:
    return nsdecls("p")


def _visibility_set_xml(ctn_id: int, spid: int, visible: bool, delay: int = 0) -> str:
    """Return XML for a `<p:set>` that shows or hides a shape *delay* ms into its effect."""
    val = "visible" if visible else "hidden"
    ctn = f'<p:cTn id="{ctn_id}" dur="1" fill="hold"/>'
    if delay:
        ctn = (
            f'<p:cTn id="{ctn_id}" dur="1" fill="hold">'
            f'<p:stCondLst><p:cond delay="{delay}"/></p:stCondLst></p:cTn>'
        )
    return (
        "<p:set>\n"
        "  <p:cBhvr>\n"
        f"    {ctn}\n"
        f'    <p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>\n'
        "    <p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>\n"
        "  </p:cBhvr>\n"
        f'  <p:to><p:strVal val="{val}"/></p:to>\n'
        "</p:set>\n"
    )


def _anim_effect_xml(
    ctn_id: int, spid: int, duration: int, filter_str: str, transition: str
) -> str:
    return (
        f'<p:animEffect transition="{transition}" filter="{filter_str}">\n'
        "  <p:cBhvr>\n"
        f'    <p:cTn id="{ctn_id}" dur="{duration}"/>\n'
        f'    <p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>\n'
        "  </p:cBhvr>\n"
        "</p:animEffect>\n"
    )


def _anim_motion_xml(ctn_id: int, spid: int, duration: int, path: str) -> str:
    # `ptsTypes` is left out: it is optional, and its letters (one point type
    # per path point, from {A, F, T, S}) are an editing hint this module has no
    # use for.  The "AE" formerly written here was not even in that set.
    path_attr = quoteattr(path)
    return (
        f'<p:animMotion origin="parent" path={path_attr} pathEditMode="relative" rAng="0">\n'
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


def _sp_tgt_xml(spid: int, paragraph_idx: int | None = None) -> str:
    """Return a `<p:spTgt>` naming shape *spid*, or one paragraph of its text."""
    if paragraph_idx is None:
        return f'<p:spTgt spid="{spid}"/>'
    return (
        f'<p:spTgt spid="{spid}">'
        f'<p:txEl><p:pRg st="{paragraph_idx}" end="{paragraph_idx}"/></p:txEl>'
        "</p:spTgt>"
    )


def _anim_size_xml(
    ctn_id: int,
    spid: int,
    duration: int,
    attr: str,
    start: str,
    end: str,
    paragraph_idx: int | None = None,
) -> str:
    """Return XML for a `<p:anim>` taking the width or height of a shape from *start* to *end*.

    *attr* is ``"ppt_w"`` or ``"ppt_h"``, and *start* and *end* are values such
    as ``"0"`` or ``"#ppt_w"`` (the size the shape has on the slide).  A Zoom
    is two of these, one per dimension.
    """
    return (
        '<p:anim calcmode="lin" valueType="num">\n'
        '  <p:cBhvr additive="repl">\n'
        f'    <p:cTn id="{ctn_id}" dur="{duration}" fill="hold"/>\n'
        f"    <p:tgtEl>{_sp_tgt_xml(spid, paragraph_idx)}</p:tgtEl>\n"
        f"    <p:attrNameLst><p:attrName>{attr}</p:attrName></p:attrNameLst>\n"
        "  </p:cBhvr>\n"
        "  <p:tavLst>\n"
        f'    <p:tav tm="0"><p:val><p:strVal val="{start}"/></p:val></p:tav>\n'
        f'    <p:tav tm="100000"><p:val><p:strVal val="{end}"/></p:val></p:tav>\n'
        "  </p:tavLst>\n"
        "</p:anim>\n"
    )


def _zoom_xml(
    ids: list[int], spid: int, duration: int, entering: bool, paragraph_idx: int | None = None
) -> str:
    """Return the two `<p:anim>` of a Zoom: grow from nothing, or shrink to nothing."""
    out = ""
    for ctn_id, attr in zip(ids, ("ppt_w", "ppt_h")):
        start, end = ("0", "#" + attr) if entering else ("#" + attr, "0")
        out += _anim_size_xml(ctn_id, spid, duration, attr, start, end, paragraph_idx)
    return out


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
    ang = _angle_units(angle_deg)
    # `by` is an ST_Angle *attribute* of <p:animRot> (CT_TLAnimateRotationBehavior
    # allows only a <p:cBhvr> child).  Emitting it as a <p:by> child — as
    # <p:animScale> legitimately does — produces XML that PowerPoint rejects.
    return (
        f'<p:animRot by="{ang}">\n'
        "  <p:cBhvr>\n"
        f'    <p:cTn id="{ctn_id}" dur="{duration}" fill="hold"/>\n'
        f'    <p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>\n'
        "  </p:cBhvr>\n"
        "</p:animRot>\n"
    )


# ---------------------------------------------------------------------------
# Timing-tree helpers
# ---------------------------------------------------------------------------
#
# PowerPoint nests every effect of a slide under its main sequence:
#
#     p:timing/p:tnLst/p:par (tmRoot)/p:cTn/p:childTnLst
#       p:seq (mainSeq)/p:cTn/p:childTnLst
#         p:par              one per click
#           p:par            one per batch of effects that start together
#             p:par          the effect: its p:cTn carries presetID/presetClass
#               p:set, p:animEffect, …   its behaviours, each naming its target
#       p:seq (interactiveSeq)   effects triggered by clicking a shape
#       p:video, p:audio         media nodes
#
# whereas an effect this module adds to a slide that has no main sequence sits
# one wrapper below the root.  Nothing below assumes a depth: an effect is any
# `p:par` whose `p:cTn` carries a preset, wherever in the tree it is.

_PAR = qn("p:par")
_CTN = qn("p:cTn")
_TIMING = qn("p:timing")
_TN_LST = qn("p:tnLst")
_CHILD_TN_LST = qn("p:childTnLst")
_SUB_TN_LST = qn("p:subTnLst")
_BLD_LST = qn("p:bldLst")
_CONTAINERS = frozenset({_PAR, qn("p:seq"), qn("p:excl")})
_TIME_NODE_LISTS = frozenset({_TN_LST, _CHILD_TN_LST, _SUB_TN_LST})
# -- the elements that name a shape by id: the target of a behaviour, a media
# -- node or a trigger condition (`p:spTgt`), an ink target, a sub-shape --
_SHAPE_REFERENCES = (qn("p:spTgt"), qn("p:inkTgt"), qn("p:subSp"))
_EFFECT_NODE_TYPES = frozenset(_NODE_TYPE_TO_TRIGGER)
_MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"


def _shape_id(element: Any) -> Optional[int]:
    """The shape id in the ``spid`` attribute of *element*, or |None| if it has no usable one."""
    try:
        return int(element.get("spid"))
    except (TypeError, ValueError):
        return None


def _is_effect(node: Any) -> bool:
    """True when time node *node* is an animation effect, not a wrapper around some."""
    if node.tag != _PAR:
        return False
    ctn = node.find(_CTN)
    if ctn is None:
        return False
    return (
        ctn.get("presetClass") is not None
        or ctn.get("presetID") is not None
        or ctn.get("nodeType") in _EFFECT_NODE_TYPES
    )


def _effects(timing: Any) -> list[Any]:
    """The effect nodes of *timing* in document order, whatever their depth."""
    if timing is None:
        return []
    return [par for tnLst in timing.findall(_TN_LST) for par in tnLst.iter(_PAR) if _is_effect(par)]


def _child_pars(par: Any) -> list[Any]:
    """The ``<p:par>`` nodes directly inside the container *par*."""
    return par.findall("%s/%s/%s" % (_CTN, _CHILD_TN_LST, _PAR))


def _entry_root(effect: Any) -> Any:
    """The largest subtree holding *effect* and no other time node.

    That is *effect* itself, or the outermost of the plain wrappers around it
    (a click step, a batch) that have nothing else in them.
    """
    node = effect
    while True:
        lst = node.getparent()
        if lst is None or lst.tag != _CHILD_TN_LST or len(lst) != 1:
            return node
        ctn = lst.getparent()
        owner = None if ctn is None else ctn.getparent()
        # -- a wrapper is a `p:par` with no role of its own; the root and the
        # -- sequences have a `nodeType` (or are no `p:par` at all) --
        if owner is None or owner.tag != _PAR or ctn.get("nodeType") is not None:
            return node
        node = owner


def _remove_time_node(node: Any) -> None:
    """Detach *node* from its timing tree, with every container this leaves childless.

    A ``<p:childTnLst>`` must hold at least one time node, so a wrapper (or a
    sequence) emptied by the removal goes too, and so on upward.  The root
    node stays; :func:`_prune_empty_timing` deals with a tree left empty.
    """
    while True:
        lst = node.getparent()
        if lst is None:
            return
        lst.remove(node)
        if len(lst) or lst.tag == _TN_LST:
            return
        ctn = lst.getparent()
        if ctn is None:
            return
        owner = ctn.getparent()
        if lst.tag == _SUB_TN_LST or owner is None or owner.tag not in _CONTAINERS:
            # -- here the list is optional: its owner stands without one --
            ctn.remove(lst)
            return
        holder = owner.getparent()
        if holder is None or holder.tag == _TN_LST:
            return  # -- `owner` is the root node --
        node = owner


def _owning_time_node(reference: Any) -> Any:
    """The time node that cannot outlive the shape *reference* names, or |None|.

    Within an effect that is the effect, all its behaviours included.  Outside
    one it is the innermost time node holding the reference: a media node
    (``<p:video>``, ``<p:audio>``), a lone behaviour, or the sequence or
    container whose trigger condition names the shape.
    """
    node = None
    for ancestor in reference.iterancestors():
        parent = ancestor.getparent()
        if parent is not None and parent.tag in _TIME_NODE_LISTS:
            node = ancestor
            break
    if node is None:
        return None
    candidate = node
    while candidate is not None and candidate.tag != _TIMING:
        if _is_effect(candidate):
            return candidate
        candidate = candidate.getparent()
    return node


def _purge_dead_targets(timing: Any, live_ids: set[int]) -> int:
    """Remove every time node of *timing* naming a shape not in *live_ids*; return how many."""
    removed = 0
    for tag in _SHAPE_REFERENCES:
        for reference in list(timing.iter(tag)):
            spid = _shape_id(reference)
            if spid is None or spid in live_ids:
                continue
            if not any(ancestor is timing for ancestor in reference.iterancestors()):
                continue  # -- went with a node removed earlier in this loop --
            node = _owning_time_node(reference)
            if node is not None:
                _remove_time_node(node)
                removed += 1
    return removed


def _prune_build_list(timing: Any, live_ids: Optional[set[int]] = None) -> int:
    """Drop stale entries from the build list of *timing*; return how many.

    With *live_ids*, an entry is stale when its shape is not among them.
    Without, it is stale when no time node of *timing* targets its shape any
    more.  A build list left empty is removed: it must hold an entry.
    """
    bldLst = timing.find(_BLD_LST)
    if bldLst is None:
        return 0
    if live_ids is None:
        live_ids = {
            spid
            for tnLst in timing.findall(_TN_LST)
            for tag in _SHAPE_REFERENCES
            for spid in (_shape_id(ref) for ref in tnLst.iter(tag))
            if spid is not None
        }
    removed = 0
    for build in list(bldLst):
        if not isinstance(build.tag, str):
            continue
        spid = _shape_id(build)
        if spid is not None and spid not in live_ids:
            bldLst.remove(build)
            removed += 1
    if len(bldLst) == 0:
        timing.remove(bldLst)
    return removed


def _prune_empty_timing(sld: Any) -> None:
    """Drop the slide's timing content once it holds no time nodes.

    An empty `<p:childTnLst>` violates the schema (CT_TimeNodeList requires
    at least one time-node child), so whichever removal takes out the last
    animation entry must remove the `p:tnLst` subtree with it.  A `p:bldLst`
    goes too — its build entries reference the effects just removed.  An
    extension list (`p:extLst`) is preserved: CT_SlideTiming allows a timing
    element holding only extensions, and its content is not ours to drop.
    Timing trees that still carry time nodes (remaining effects, or a
    `p:video` node for a movie's play controls) are left untouched.

    Every `p:timing` of the slide is looked at, including the copies
    PowerPoint keeps in the branches of an `mc:AlternateContent` when its
    effects use a newer feature; a wrapper left with nothing in any branch is
    removed along with them.
    """
    for timing in list(sld.iter(_TIMING)):
        if timing.xpath("p:tnLst/p:par/p:cTn/p:childTnLst/*"):
            continue  # -- it still has time nodes --
        _keep_only_extensions(timing)
        if len(timing) == 0:
            _remove_empty_timing(timing)


def _keep_only_extensions(timing: Any) -> None:
    """Remove every child of *timing* but its extension list."""
    ext_lst_tag = qn("p:extLst")
    for child in list(timing):
        if child.tag != ext_lst_tag:
            timing.remove(child)


def _remove_empty_timing(timing: Any) -> None:
    """Remove *timing*, and the ``mc:AlternateContent`` it was in if no branch has content."""
    branch = timing.getparent()
    if branch is None:
        return
    branch.remove(timing)
    wrapper = branch.getparent()
    if wrapper is None or wrapper.tag != "{%s}AlternateContent" % _MC_NS:
        return
    if any(len(alternative) for alternative in wrapper):
        return  # -- another branch still has its copy --
    holder = wrapper.getparent()
    if holder is not None:
        holder.remove(wrapper)


def _first_delay(ctn: Any) -> int:
    """Milliseconds the first start condition of *ctn* waits, or 0 when it states none."""
    cond = ctn.find("%s/%s" % (qn("p:stCondLst"), qn("p:cond")))
    try:
        return int(cond.get("delay"))
    except (AttributeError, TypeError, ValueError):  # no condition, no delay, "indefinite"
        return 0


def _effect_span(effect: Any) -> int:
    """Milliseconds from the start of its batch to the end of *effect*."""
    ctn = effect.find(_CTN)
    longest = 0
    for inner in ctn.iter(_CTN):
        try:
            dur = int(inner.get("dur"))
        except (TypeError, ValueError):  # absent or "indefinite"
            continue
        if dur <= 1:
            continue  # -- the 1 ms of a visibility switch counts as instantaneous --
        longest = max(longest, dur if inner is ctn else _first_delay(inner) + dur)
    return _first_delay(ctn) + longest


def _batch_end(batch: Any) -> int:
    """Milliseconds from its click to the moment every effect of *batch* is over."""
    return _first_delay(batch.find(_CTN)) + max(
        (_effect_span(effect) for effect in _child_pars(batch)), default=0
    )


def _batch_par_xml(delay: int) -> str:
    """XML for an empty batch `<p:par>` starting *delay* ms into its click step."""
    return (
        f"<p:par {_nsdecls_p()}>"
        '<p:cTn id="0" fill="hold">'
        f'<p:stCondLst><p:cond delay="{delay}"/></p:stCondLst>'
        "<p:childTnLst/>"
        "</p:cTn>"
        "</p:par>"
    )


def _click_par_xml(auto_start_after: Optional[str]) -> str:
    """XML for an empty click-step `<p:par>` of the main sequence.

    It waits for a click, unless *auto_start_after* names the time node (the
    main sequence itself) whose beginning sets it off unprompted: that is how
    PowerPoint starts a leading "with previous" or "after previous" effect.
    """
    auto = ""
    if auto_start_after is not None:
        auto = f'<p:cond evt="onBegin" delay="0"><p:tn val="{auto_start_after}"/></p:cond>'
    return (
        f"<p:par {_nsdecls_p()}>"
        '<p:cTn id="0" fill="hold">'
        f'<p:stCondLst><p:cond delay="indefinite"/>{auto}</p:stCondLst>'
        "<p:childTnLst/>"
        "</p:cTn>"
        "</p:par>"
    )


def _step_list(main_seq: Any) -> Any:
    """The ``<p:childTnLst>`` holding the click steps of *main_seq*, added if it has none.

    A new one goes ahead of a ``<p:subTnLst>``, which comes last in a time node.
    """
    steps = main_seq.find(_CHILD_TN_LST)
    if steps is not None:
        return steps
    steps = parse_xml("<p:childTnLst %s/>" % _nsdecls_p())
    sub_lst = main_seq.find(_SUB_TN_LST)
    if sub_lst is None:
        main_seq.append(steps)
    else:
        sub_lst.addprevious(steps)
    return steps


def _batch_list(click: Any) -> Any:
    """The ``<p:childTnLst>`` holding the batches of click step *click*, added if it has none."""
    click_ctn = click.find(_CTN)
    batches = click_ctn.find(_CHILD_TN_LST)
    if batches is None:
        batches = parse_xml("<p:childTnLst %s/>" % _nsdecls_p())
        click_ctn.append(batches)
    return batches


def _effect_list(batch: Any) -> Any:
    """The ``<p:childTnLst>`` holding the effects of *batch*."""
    return batch.find(_CTN).find(_CHILD_TN_LST)


def _new_batch(delay: int, effect: Any) -> Any:
    """A batch holding *effect* that starts *delay* ms into its click step."""
    batch = parse_xml(_batch_par_xml(delay))
    _effect_list(batch).append(effect)
    return batch


def _new_click_step(main_seq: Any, effect: Any, trigger: PP_ANIM_TRIGGER) -> Any:
    """A click step of *main_seq* holding *effect*, in a batch of its own.

    The step waits for a click.  When *effect* does not, the step is also set
    off by the main sequence beginning, if the sequence has an id to name.
    """
    auto_start = None
    if trigger is not PP_ANIM_TRIGGER.ON_CLICK and (main_seq.get("id") or "").isdigit():
        auto_start = main_seq.get("id")
    click = parse_xml(_click_par_xml(auto_start))
    batch = parse_xml(_batch_par_xml(0))
    click.find(_CTN).find(_CHILD_TN_LST).append(batch)
    _effect_list(batch).append(effect)
    return click


def _place_in_click_step(click: Any, effect: Any, trigger: PP_ANIM_TRIGGER) -> tuple[Any, Any]:
    """Where *effect* goes in click step *click*: the node to add, and the list to add it to.

    A with-previous effect joins the last batch.  Any other opens a new batch
    that starts when the last one is over, or at once in a step that,
    unusually, has no batch yet.
    """
    batches = _child_pars(click)
    if trigger is PP_ANIM_TRIGGER.WITH_PREVIOUS and batches:
        return effect, _effect_list(batches[-1])
    batch = _new_batch(_batch_end(batches[-1]) if batches else 0, effect)
    return batch, _batch_list(click)


# ---------------------------------------------------------------------------
# SlideAnimations – the object returned by slide.animations
# ---------------------------------------------------------------------------


class SlideAnimations:
    """Manages the animation timeline for a single slide.

    Returned by :attr:`power_pptx.slide.Slide.animations`.  Provides methods to
    append entrance, exit, and emphasis effects to the slide's timing tree.
    Existing animations (e.g. authored in PowerPoint) are left untouched;
    new effects are appended after them.

    Effects authored in PowerPoint are listed alongside those added here:
    iteration, ``len()``, :meth:`clear` and :meth:`purge_orphans` all work on
    the whole timing tree, down through its main sequence.  On a slide that
    has a main sequence a new effect is appended to it, in the click-step
    structure PowerPoint uses there, so it takes its place after the existing
    ones.
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
        """Iterate over the slide's animation effects.

        Yields one :class:`AnimationEntry` per effect, in document order.
        Effects authored inside PowerPoint as well as those added via this
        API are reported, wherever they sit in the timing tree.
        """
        for effect in self._effects():
            yield AnimationEntry(effect, self._slide)

    def __len__(self) -> int:
        return len(self._effects())

    def __bool__(self) -> bool:  # explicit so __len__ doesn't drive truthiness alone
        return bool(self._effects())

    def list(self) -> "list[AnimationEntry]":
        """Return a list of :class:`AnimationEntry` views, in document order.

        Convenience for callers that prefer not to iterate.
        """
        return list(self)

    def clear(self) -> int:
        """Remove every animation effect from the slide.

        Returns the number of effects removed.
        Unlike :meth:`purge_orphans`, this drops **all** entries — useful
        when iterating on animation design and you want to re-run the
        build without the previous run's effects piling up.

        The wrappers and sequences the effects sat in go with them, as do
        the build-list entries of the shapes that are no longer animated.
        Media nodes (the play controls of a movie) are not effects and stay.
        """
        timing = self._timing
        effects = _effects(timing)
        for effect in effects:
            _remove_time_node(effect)
        if effects:
            _prune_build_list(timing)
            _prune_empty_timing(self._slide._element)
        return len(effects)

    @property
    def _timing(self) -> Any:
        """The slide's ``<p:timing>`` element, or |None| if it has none."""
        return self._slide._element.find(_TIMING)

    def _effects(self) -> list[Any]:
        """Return the effect ``<p:par>`` elements of the slide, in document order."""
        return _effects(self._timing)

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
                    f"add(kind='exit') requires a BaseShape; got {type(shape).__name__!r}."
                )
            self.add_exit(preset, cast("BaseShape", shape), **kwargs)
            return
        if kind == "emphasis":
            if not hasattr(shape, "shape_id"):
                raise TypeError(
                    f"add(kind='emphasis') requires a BaseShape; got {type(shape).__name__!r}."
                )
            self.add_emphasis(preset, cast("BaseShape", shape), **kwargs)
            return
        if kind == "motion":
            if not hasattr(shape, "shape_id"):
                raise TypeError(
                    f"add(kind='motion') requires a BaseShape; got {type(shape).__name__!r}."
                )
            # For motion, *preset* carries the raw OOXML path string, which
            # `add_motion` checks.
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
        direction: str | None = None,
        by_paragraph: bool = False,
        easing: str | tuple[float, float] | None = None,
    ) -> None:
        """Append an entrance animation for *shape* to the slide timeline.

        *preset* is one of: ``"appear"``, ``"fade"``, ``"fly_in"``,
        ``"float_in"``, ``"wipe"``, ``"zoom"``, ``"wheel"``,
        ``"random_bars"``.

        *direction* is the edge the shape comes in from, ``"bottom"``,
        ``"top"``, ``"left"`` or ``"right"``.  It is used by ``"fly_in"``
        (from the bottom by default) and ``"wipe"`` (from the left by
        default); any other value raises :class:`ValueError`.  Other
        presets have no direction and ignore it.

        Pass ``by_paragraph=True`` to animate each paragraph of a text
        frame separately.  *shape* may then be either a |TextFrame| or
        any shape that exposes a ``text_frame`` (e.g. an autoshape or
        placeholder).  The first paragraph fires on the supplied
        *trigger*; subsequent paragraphs fire after the previous one.
        Currently supports the ``"fade"``, ``"appear"``, ``"wipe"``,
        ``"zoom"``, ``"wheel"``, and ``"random_bars"`` presets — others
        raise :class:`ValueError`.  *direction* and *easing* apply to
        every paragraph.

        *delay* and *duration* are in milliseconds.  A float is rounded to
        the nearest whole millisecond; a negative value raises
        :class:`ValueError`.
        """
        if preset not in _ENTRANCE_PRESETS:
            raise ValueError(
                f"Unknown entrance preset {preset!r}. Choose from: {sorted(_ENTRANCE_PRESETS)}"
            )
        delay = _milliseconds(delay, "delay")
        duration = _milliseconds(duration, "duration")
        direction = _resolve_direction(preset, direction)

        if by_paragraph:
            self._add_entrance_by_paragraph(
                preset,
                shape,
                trigger=trigger,
                delay=delay,
                duration=duration,
                direction=direction,
                easing=easing,
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
        if direction is not None:
            preset_subtype = _DIRECTION_SUBTYPES[direction]
        behaviors = self._entrance_behaviors(preset, bshape.shape_id, duration, direction)
        self._append_effect(
            bshape.shape_id,
            preset_id,
            "entr",
            preset_subtype,
            trigger,
            delay,
            behaviors,
            easing=easing,
        )

    def add_exit(
        self,
        preset: str,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = _TRIGGER_UNSET,  # pyright: ignore[reportArgumentType]
        delay: int = 0,
        duration: int = 500,
        direction: str | None = None,
    ) -> None:
        """Append an exit animation for *shape* to the slide timeline.

        *preset* is one of: ``"disappear"``, ``"fade"``, ``"fly_out"``,
        ``"float_out"``, ``"wipe"``, ``"zoom"``, ``"wheel"``,
        ``"random_bars"``.

        *direction* is used by ``"fly_out"`` (the edge the shape leaves by,
        the bottom by default) and ``"wipe"`` (the edge the wipe starts
        from, the left by default), and checked as for :meth:`add_entrance`.

        *delay* and *duration* are in milliseconds, checked as for
        :meth:`add_entrance`.
        """
        if preset not in _EXIT_PRESETS:
            raise ValueError(
                f"Unknown exit preset {preset!r}. Choose from: {sorted(_EXIT_PRESETS)}"
            )
        delay = _milliseconds(delay, "delay")
        duration = _milliseconds(duration, "duration")
        direction = _resolve_direction(preset, direction)
        preset_id, preset_subtype = _EXIT_PRESETS[preset]
        if direction is not None:
            preset_subtype = _DIRECTION_SUBTYPES[direction]
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
        (default: 360 — one full clockwise revolution).  It may be negative
        (counter-clockwise) and is limited to just under a hundred turns
        either way, the range of the attribute that holds it.

        *delay* and *duration* are in milliseconds, checked as for
        :meth:`add_entrance`.
        """
        if preset not in _EMPHASIS_PRESETS:
            raise ValueError(
                f"Unknown emphasis preset {preset!r}. Choose from: {sorted(_EMPHASIS_PRESETS)}"
            )
        delay = _milliseconds(delay, "delay")
        duration = _milliseconds(duration, "duration")
        _angle_units(degrees)  # -- reject an unusable angle before anything is built --
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
        width to the right).  The path ends with ``E``; one is added if
        *path* has none.

        Only the commands ``M``, ``L``, ``C``, ``Z`` and ``E`` (and their
        lower-case, relative forms) exist in a motion path.  Anything else
        in *path* raises :class:`ValueError`; for SVG path syntax, with its
        wider set of commands, use :meth:`MotionPath.svg`.

        Use :meth:`MotionPath.line` for a coordinate-aware convenience
        wrapper, or :meth:`MotionPath.custom` to pass an arbitrary path.
        """
        path = _normalise_motion_path(path)
        delay = _milliseconds(delay, "delay")
        duration = _milliseconds(duration, "duration")
        ids = self._reserve_ids(1)
        behaviors = _anim_motion_xml(ids[0], shape.shape_id, duration, path)
        # presetID 64 is PowerPoint's "Custom Path" path animation.
        self._append_effect(shape.shape_id, 64, "path", 0, trigger, delay, behaviors)

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
        delay = _milliseconds(delay, "delay")
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
        delay = _milliseconds(delay, "delay")
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
        self, preset: str, spid: int, duration: int, direction: str | None
    ) -> str:
        ids = self._reserve_ids(3)
        vis_xml = _visibility_set_xml(ids[0], spid, visible=True)

        if preset == "appear":
            return vis_xml

        if preset == "fly_in":
            path = _FLY_PATHS_IN[direction or "bottom"]
            return vis_xml + _anim_motion_xml(ids[1], spid, duration, path)

        if preset == "float_in":
            return (
                vis_xml
                + _anim_effect_xml(ids[1], spid, duration, "fade", "in")
                + _anim_motion_xml(ids[2], spid, duration, "M 0 0.25 L 0 0 E")
            )

        if preset == "zoom":
            return vis_xml + _zoom_xml(ids[1:], spid, duration, entering=True)

        filter_str = _effect_filter(preset, direction)
        return vis_xml + _anim_effect_xml(ids[1], spid, duration, filter_str, "in")

    def _exit_behaviors(self, preset: str, spid: int, duration: int, direction: str | None) -> str:
        ids = self._reserve_ids(3)

        if preset == "disappear":
            return _visibility_set_xml(ids[0], spid, visible=False)

        # The shape is hidden once its exit has played, in the last millisecond
        # of it: hidden from the start, there would be nothing to see fade,
        # wipe or fly away.
        hide_at = max(duration - 1, 0)

        if preset == "fly_out":
            path = _FLY_PATHS_OUT[direction or "bottom"]
            vis_xml = _visibility_set_xml(ids[1], spid, visible=False, delay=hide_at)
            return _anim_motion_xml(ids[0], spid, duration, path) + vis_xml

        if preset == "float_out":
            vis_xml = _visibility_set_xml(ids[2], spid, visible=False, delay=hide_at)
            return (
                _anim_effect_xml(ids[0], spid, duration, "fade", "out")
                + _anim_motion_xml(ids[1], spid, duration, "M 0 0 L 0 0.25 E")
                + vis_xml
            )

        if preset == "zoom":
            vis_xml = _visibility_set_xml(ids[2], spid, visible=False, delay=hide_at)
            return _zoom_xml(ids[:2], spid, duration, entering=False) + vis_xml

        filter_str = _effect_filter(preset, direction)
        vis_xml = _visibility_set_xml(ids[1], spid, visible=False, delay=hide_at)
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
            # Teeter: oscillate rotation ~10 degrees either side.  `by` is an
            # attribute of <p:animRot>, not a child element (see _anim_rot_xml).
            ang = int(10 * 60000)
            return (
                f'<p:animRot by="{ang}">\n'
                "  <p:cBhvr>\n"
                f'    <p:cTn id="{ids[0]}" dur="{duration}" autoRev="1"/>\n'
                f'    <p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>\n'
                "  </p:cBhvr>\n"
                "</p:animRot>\n"
            )
        return ""

    # -- by-paragraph entrance ---------------------------------------------

    # Subset of entrance presets where targeting an individual paragraph
    # makes sense.  Direction-aware presets (fly_in, float_in) are
    # excluded because PowerPoint's per-paragraph wrappers don't support
    # the motion-path component cleanly.
    _PARAGRAPH_PRESETS = frozenset(
        {
            "appear",
            "fade",
            "wipe",
            "zoom",
            "wheel",
            "random_bars",
        }
    )

    def _add_entrance_by_paragraph(
        self,
        preset: str,
        target: BaseShape | TextFrame,
        *,
        trigger: PP_ANIM_TRIGGER,
        delay: int,
        duration: int,
        direction: str | None = None,
        easing: str | tuple[float, float] | None = None,
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
        shape, text_frame = _paragraph_target(target)

        spid: int = shape.shape_id
        preset_id, preset_subtype = _ENTRANCE_PRESETS[preset]
        if direction is not None:
            preset_subtype = _DIRECTION_SUBTYPES[direction]
        # Resolve the first trigger now so subsequent effects can chain
        # off it via AFTER_PREVIOUS.  The default trigger inside a
        # `sequence()` context is honoured via _resolve_default_trigger.
        first_trigger = self._resolve_default_trigger(trigger)
        for i, _para in enumerate(text_frame.paragraphs):
            effect_trigger = first_trigger if i == 0 else PP_ANIM_TRIGGER.AFTER_PREVIOUS
            effect_delay = delay if i == 0 else 0
            behaviors = self._paragraph_entrance_behaviors(preset, spid, i, duration, direction)
            self._append_effect(
                spid,
                preset_id,
                "entr",
                preset_subtype,
                effect_trigger,
                effect_delay,
                behaviors,
                easing=easing,
            )

    def _paragraph_entrance_behaviors(
        self,
        preset: str,
        spid: int,
        paragraph_idx: int,
        duration: int,
        direction: str | None = None,
    ) -> str:
        """Return the behaviors XML for a paragraph-targeted entrance preset."""
        ids = self._reserve_ids(3)
        vis_xml = _visibility_set_xml_for_paragraph(ids[0], spid, paragraph_idx, visible=True)
        if preset == "appear":
            return vis_xml
        if preset == "zoom":
            return vis_xml + _zoom_xml(ids[1:], spid, duration, True, paragraph_idx)
        filter_str = _effect_filter(preset, direction)
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
        # -- everything that can be refused is checked before the timing tree is
        # -- touched: a skeleton created for an effect that then fails to
        # -- materialise would be left behind empty, which is schema-invalid --
        if easing is not None:
            _resolve_easing(easing)
        trigger = self._resolve_default_trigger(trigger)
        # -- the delay of an enclosing sequence()/group() is added on top, so the
        # -- sum is what has to fit the attribute --
        delay = _milliseconds(self._consume_block_delay(delay), "delay")

        root_ctn = self._get_or_create_root_ctn()
        grp_id, node_type, wrapper_delay = self._resolve_trigger(trigger)

        indent_behaviors = "\n".join("      " + line for line in behaviors_xml.splitlines()) + "\n"

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
            '  <p:cTn fill="hold">\n'
            "    <p:stCondLst>\n"
            f'      <p:cond delay="{wrapper_delay}"/>\n'
            "    </p:stCondLst>\n"
            "    <p:childTnLst>\n" + "\n".join("      " + l for l in effect_par.splitlines()) + "\n"
            "    </p:childTnLst>\n"
            "  </p:cTn>\n"
            "</p:par>\n"
        ) % _nsdecls_p()

        main_seq = self._main_sequence()
        if main_seq is not None:
            effect_elm = parse_xml(
                effect_par.replace("<p:par>", "<p:par %s>" % _nsdecls_p(), 1).encode("utf-8")
            )
            if easing is not None:
                _apply_easing(effect_elm, easing)
            self._append_to_main_sequence(main_seq, effect_elm, trigger)
            return

        group_elm = parse_xml(click_group.encode("utf-8"))
        # Fix IDs: assign proper sequential IDs to all p:cTn elements in our
        # new subtree now that we know which IDs are free.
        self._assign_ids(group_elm)
        if easing is not None:
            _apply_easing(group_elm, easing)
        root_ctn.append(group_elm)

    def _main_sequence(self) -> Any:
        """The ``<p:cTn>`` of the slide's main sequence, or |None| if it has none.

        PowerPoint keeps the effects of a slide in a ``<p:seq>`` directly
        under the root time node, marked ``nodeType="mainSeq"``.
        """
        found = self._slide._element.xpath(
            "p:timing/p:tnLst/p:par/p:cTn/p:childTnLst/p:seq/p:cTn[@nodeType='mainSeq']"
        )
        return found[0] if found else None

    def _append_to_main_sequence(
        self, main_seq: Any, effect_elm: Any, trigger: PP_ANIM_TRIGGER
    ) -> None:
        """Add *effect_elm* at the end of the main sequence, the way PowerPoint files it.

        The main sequence holds one ``<p:par>`` per click; each of those holds
        one ``<p:par>`` per batch of effects that start together, placed on the
        click's timeline by its start delay.  So an on-click effect opens a new
        click step, a with-previous effect joins the last batch, and an
        after-previous effect opens a new batch that starts when the last one
        is over.  With nothing before it, an effect that does not wait for a
        click goes in a step set off by the sequence itself beginning.
        """
        steps = _step_list(main_seq)
        clicks = steps.findall(_PAR)
        if trigger is PP_ANIM_TRIGGER.ON_CLICK or not clicks:
            node, parent = _new_click_step(main_seq, effect_elm, trigger), steps
        else:
            node, parent = _place_in_click_step(clicks[-1], effect_elm, trigger)
        # -- ids are numbered from those already in the tree, so before adding --
        self._assign_ids(node)
        parent.append(node)

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
        *direction* is the edge each shape comes in from for the presets
        that have one (``"wipe"``, ``"fly_in"``), checked as for
        :meth:`add_entrance`; the others ignore it.

        Example::

            slide.animations.typewriter(
                [bullet1, bullet2, bullet3], delay_between_ms=200
            )
        """
        delay_between_ms = _milliseconds(delay_between_ms, "delay_between_ms")
        duration = _milliseconds(duration, "duration")
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
        """Remove every timing node whose target shape no longer exists.

        Walks the whole timing tree, looking at each reference to a shape:
        the target of an effect's behaviours, of a media node (the
        ``<p:video>`` behind a movie's play controls), and of a trigger
        condition.  An effect naming a missing shape is removed whole; so is
        a media node, or a sequence that was triggered by clicking the shape.
        Wrappers left empty go with them, and so do the build-list entries
        (``<p:bldP>`` and friends) of missing shapes.  Use this after
        deleting shapes to clean up the timing tree (PowerPoint will silently
        "repair" a deck with orphan timing references, but a clean tree
        avoids that prompt).

        Returns the number of timing nodes removed.

        This is also called automatically when a shape is removed via
        :meth:`BaseShape.delete` or a group is dissolved via
        :meth:`GroupShape.ungroup`, but is exposed publicly for callers
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

        # PowerPoint keeps a second copy of the timing tree in the branches of
        # an mc:AlternateContent when an effect uses a newer feature, so every
        # `p:timing` under the slide is purged, not only its direct child.
        removed = 0
        changed = False
        for timing in list(sld.iter(_TIMING)):
            purged = _purge_dead_targets(timing, live_ids)
            stale_builds = _prune_build_list(timing, live_ids)
            removed += purged
            if purged or stale_builds:
                changed = True
        if changed:
            _prune_empty_timing(sld)
        return removed

    def _resolve_trigger(self, trigger: PP_ANIM_TRIGGER) -> tuple[int, str, str]:
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

    An entry stands for one effect, whether this library added it or
    PowerPoint did: the ``<p:par>`` whose ``<p:cTn>`` carries the preset.
    """

    _par_element: Any  # the effect <p:par>, whose <p:cTn> carries the preset
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
        return _first_delay(ctn)

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
        """The ``<p:par>`` element holding this effect and nothing else.

        That is the effect together with the wrappers around it that it has
        to itself (its click step, say), which is what :meth:`remove` takes
        out.  Treat as read-only.
        """
        return _entry_root(self._par_element)

    def remove(self) -> None:
        """Remove this animation entry from the slide.

        Wrappers the effect leaves empty are removed with it, and so is the
        build-list entry of its shape once nothing animates that shape.
        """
        timing = None
        for ancestor in self._par_element.iterancestors(_TIMING):
            timing = ancestor
        if timing is None:
            return  # -- already removed --
        _remove_time_node(self._par_element)
        _prune_build_list(timing)
        _prune_empty_timing(self._slide._element)

    # -- internal helpers --------------------------------------------------

    def _effect_attr(self, name: str) -> Optional[str]:
        ctn = self._inner_effect_ctn()
        return ctn.get(name) if ctn is not None else None

    def _inner_effect_ctn(self) -> Any:
        """Return the effect's own cTn, which carries presetID/presetClass."""
        return self._par_element.find(_CTN)


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
        direction: str = "left",
    ) -> None:
        """Shape is revealed by a wipe from *direction* (left/right/top/bottom)."""
        slide.animations.add_entrance(
            "wipe",
            shape,
            trigger=trigger,
            delay=delay,
            duration=duration,
            direction=direction,
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
        """Shape is revealed by a single spoke sweeping round like a clock hand."""
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
        slide.animations.add_exit("fade", shape, trigger=trigger, delay=delay, duration=duration)

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
        """Shape fades out while sinking a little below its position."""
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
        direction: str = "left",
    ) -> None:
        """Shape is wiped away, starting from *direction* (left/right/top/bottom)."""
        slide.animations.add_exit(
            "wipe",
            shape,
            trigger=trigger,
            delay=delay,
            duration=duration,
            direction=direction,
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
        slide.animations.add_exit("zoom", shape, trigger=trigger, delay=delay, duration=duration)

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
        """Shape is hidden by a single spoke sweeping round like a clock hand."""
        slide.animations.add_exit("wheel", shape, trigger=trigger, delay=delay, duration=duration)

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
        """Shape disappears through random horizontal bars."""
        slide.animations.add_exit(
            "random_bars", shape, trigger=trigger, delay=delay, duration=duration
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
        path = f"M 0 0 L {_fmt(nx)} {_fmt(ny)} E"
        slide.animations.add_motion(shape, path, trigger=trigger, delay=delay, duration=duration)

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
        slide-height down.  A path ends with ``E``, e.g.
        ``"M 0 0 L 0.5 0 E"`` for a horizontal half-slide hop; the ``E``
        is added if *path* leaves it out.

        The commands are ``M`` (move to), ``L`` (line to), ``C`` (cubic
        curve to), ``Z`` (close the loop) and ``E`` (end), lower case for
        coordinates relative to the current point.  Anything else raises
        :class:`ValueError`.

        For the more common SVG path syntax — horizontal / vertical /
        quadratic commands, a viewbox, pixel-style coordinates — use
        :meth:`svg` instead.
        """
        slide.animations.add_motion(shape, path, trigger=trigger, delay=delay, duration=duration)

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
        * ``Q / q`` — quadratic bezier curveto (written as the equivalent
          cubic: a motion path has no quadratic command)
        * ``Z / z`` — closepath (returns to the most-recent moveto)

        Anything else — an arc (``A``), a smooth curve (``S``, ``T``), a
        stray character, a command short of coordinates — raises
        :class:`ValueError`.

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
            slide,
            shape,
            dx,
            dy,
            trigger=trigger,
            delay=delay,
            duration=duration,
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
            f"C 0 {_fmt(-s * k * ry)} {_fmt(rx - k * rx)} {_fmt(-s * ry)} "
            f"{_fmt(rx)} {_fmt(-s * ry)} "
            f"C {_fmt(rx + k * rx)} {_fmt(-s * ry)} {_fmt(2 * rx)} "
            f"{_fmt(-s * (ry - k * ry))} {_fmt(2 * rx)} 0 "
            f"C {_fmt(2 * rx)} {_fmt(s * (ry - k * ry))} {_fmt(rx + k * rx)} "
            f"{_fmt(s * ry)} {_fmt(rx)} {_fmt(s * ry)} "
            f"C {_fmt(rx - k * rx)} {_fmt(s * ry)} 0 {_fmt(s * (ry - k * ry))} 0 0 E"
        )
        slide.animations.add_motion(shape, path, trigger=trigger, delay=delay, duration=duration)

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
        # A parabola is a quadratic bezier, which the motion-path grammar
        # does not have (only M, L, C, Z, E), so it is written as the cubic
        # tracing the same curve.
        c1x, c1y, c2x, c2y = _cubic_from_quadratic((0.0, 0.0), (cx, cy), (nx, ny))
        path = f"M 0 0 C {_fmt(c1x)} {_fmt(c1y)} {_fmt(c2x)} {_fmt(c2y)} {_fmt(nx)} {_fmt(ny)} E"
        slide.animations.add_motion(shape, path, trigger=trigger, delay=delay, duration=duration)

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
            parts.append(f"L {_fmt(mid_x)} {_fmt(mid_y)}")
        parts.append("E")
        path = " ".join(parts)
        slide.animations.add_motion(shape, path, trigger=trigger, delay=delay, duration=duration)

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
            parts.append(f"L {_fmt(x)} {_fmt(y)}")
        parts.append("E")
        path = " ".join(parts)
        slide.animations.add_motion(shape, path, trigger=trigger, delay=delay, duration=duration)


# One token of a path: a command letter (any letter, so unsupported ones can
# be diagnosed) or a number in SVG's grammar — optional sign, digits with an
# optional fraction or a bare fraction, optional exponent.  Tokens may be
# separated by whitespace and commas, or by nothing at all ("M10-5L.5.5").
_PATH_TOKEN_RE = re.compile(r"[\s,]*(?:([A-Za-z])|([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?))")


@dataclass(frozen=True)
class _PathDialect:
    """The commands one kind of path string knows, and its name in messages."""

    name: str
    """What the path is called in error messages, e.g. ``"svg path"``."""

    arg_counts: dict[str, int]
    """Number of coordinates each (upper-case) command takes per repetition."""

    unsupported: str
    """Message for a command not in `arg_counts`, formatted with `cmd` and `path`."""


# The commands of an SVG path that can be converted to a motion path.
_SVG_PATH = _PathDialect(
    "svg path",
    {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "Q": 4, "Z": 0},
    "unsupported svg path command {cmd!r}; supported: M/m L/l H/h V/v C/c Q/q Z/z",
)

# The commands of an OOXML motion path, which are all there are: ISO/IEC
# 29500-1 §19.5.4 gives the allowed set as {M, L, C, Z, E} and their
# lower-case (relative) forms.
_MOTION_PATH = _PathDialect(
    "motion path",
    {"M": 2, "L": 2, "C": 6, "Z": 0, "E": 0},
    "unsupported motion path command {cmd!r} in {path!r}: a motion path knows only M, L, C, "
    "Z and E (lower case for relative coordinates). For SVG path syntax use MotionPath.svg().",
)


def _path_tokens(path: str, what: str) -> list[str | float]:
    """Split *path* into command letters (`str`) and numbers (`float`).

    Raises |ValueError| on anything else in the string, rather than skip it:
    a character dropped in silence (a typographic minus sign, say) would
    change where the path goes.  *what* names the kind of path in the message.
    """
    tokens: list[str | float] = []
    pos = 0
    end = len(path.rstrip(" \t\r\n,"))
    while pos < end:
        match = _PATH_TOKEN_RE.match(path, pos)
        if match is None:
            bad = path[pos:].lstrip(" \t\r\n,")[:1]
            raise ValueError(f"unexpected character {bad!r} in {what} {path!r}")
        command, number = match.groups()
        tokens.append(command if command is not None else float(number))
        pos = match.end()
    return tokens


class _PathCommands:
    """The commands of a *dialect* path string, each with its coordinates.

    Iterating yields a ``(command, coordinates)`` pair for every repetition of
    a command: a command repeats for as long as coordinates follow it, so
    ``"L 1 2 3 4"`` yields ``("L", [1.0, 2.0])`` and then ``("L", [3.0,
    4.0])``.  As in SVG, the coordinate pairs after the first of a moveto
    are linetos.  An ``E`` ends the path.

    The path is checked as it is read: anything that is not a well-formed
    path in *dialect* raises |ValueError|.
    """

    def __init__(self, path: str, dialect: _PathDialect):
        self._path = path
        self._dialect = dialect
        self._tokens = _path_tokens(path, dialect.name)
        if not self._tokens:
            raise ValueError(f"no recognisable commands in {dialect.name} {path!r}")
        self._pos = 0
        # -- the command a number with no letter before it repeats --
        self._current = ""

    def __iter__(self) -> Iterator[tuple[str, list[float]]]:
        while self._pos < len(self._tokens):
            cmd = self._next_command()
            coordinates = self._take_coordinates(cmd)
            if cmd in ("E", "e") and self._pos < len(self._tokens):
                raise ValueError(
                    f"nothing can follow the end command {cmd!r} in"
                    f" {self._dialect.name} {self._path!r}"
                )
            yield cmd, coordinates
            # -- as in SVG, further coordinate pairs after a moveto are linetos --
            self._current = {"M": "L", "m": "l"}.get(cmd, cmd)

    def _next_command(self) -> str:
        """The command the token at the read position starts or repeats."""
        token = self._tokens[self._pos]
        if isinstance(token, str):
            self._pos += 1
            return self._checked_command(token)
        if not self._current:
            raise ValueError(
                f"{self._dialect.name} must start with M/m; got a number in {self._path!r}"
            )
        if self._current in ("Z", "z"):
            # Every other command repeats for as long as coordinates follow;
            # closepath takes none, so a number here belongs to no command.
            raise ValueError(
                f"expected a command after {self._current!r}, got a number in"
                f" {self._dialect.name} {self._path!r}"
            )
        return self._current

    def _checked_command(self, letter: str) -> str:
        """*letter*, once it is known to be a command that can come next."""
        if letter.upper() not in self._dialect.arg_counts:
            raise ValueError(self._dialect.unsupported.format(cmd=letter, path=self._path))
        if not self._current and letter.upper() != "M":
            raise ValueError(
                f"{self._dialect.name} must start with M/m; got {letter!r} in {self._path!r}"
            )
        return letter

    def _take_coordinates(self, cmd: str) -> list[float]:
        """Read the coordinates of one repetition of *cmd*."""
        count = self._dialect.arg_counts[cmd.upper()]
        args = self._tokens[self._pos : self._pos + count]
        if len(args) < count or any(isinstance(arg, str) for arg in args):
            raise ValueError(
                f"{cmd!r} needs {count} coordinate(s) in {self._dialect.name} {self._path!r}"
            )
        self._pos += count
        return [float(arg) for arg in args]


def _normalise_motion_path(path: Any) -> str:
    """Return the OOXML motion path *path* checked, tidied and terminated.

    A motion path is a sequence of ``M``/``L``/``C`` commands with their
    coordinates, optionally closed by ``Z``, and ended by ``E``.  The result
    holds exactly that: each command followed by its coordinates as plain
    decimals, one space apart, with the ending ``E`` added if *path* stops
    short of one (a path closed with ``Z`` is complete as it stands).  Being
    made of nothing but those letters, digits, signs and points, it can go
    into an XML attribute as it is.

    Raises |ValueError| for anything else, so that a malformed path is
    reported here rather than written into the slide.
    """
    if not isinstance(path, str) or not path.strip():
        raise ValueError(
            "motion path must be a non-empty OOXML path string, e.g. 'M 0 0 L 0.5 0 E'"
        )
    out: list[str] = []
    cmd = ""
    for cmd, coordinates in _PathCommands(path, _MOTION_PATH):
        out.append(cmd)
        out.extend(_fmt(value) for value in coordinates)
    # -- a path ended with E, or closed with Z, is complete as it stands --
    if cmd.upper() not in ("E", "Z"):
        out.append("E")
    return " ".join(out)


def _cubic_from_quadratic(
    start: tuple[float, float], control: tuple[float, float], end: tuple[float, float]
) -> tuple[float, float, float, float]:
    """Control points of the cubic bezier tracing the same curve as a quadratic one.

    The quadratic from *start* to *end* with the single control point
    *control* is exactly the cubic whose control points lie two thirds of the
    way from each end towards *control*.
    """
    return (
        start[0] + 2.0 / 3.0 * (control[0] - start[0]),
        start[1] + 2.0 / 3.0 * (control[1] - start[1]),
        end[0] + 2.0 / 3.0 * (control[0] - end[0]),
        end[1] + 2.0 / 3.0 * (control[1] - end[1]),
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

    A motion path knows only moves, lines and cubic curves (ISO/IEC 29500-1
    §19.5.4 allows ``M L C Z E``), so a quadratic curve is written as the
    cubic that traces the same curve.

    When *viewbox* is ``None`` the path is assumed to already live in
    the unit square ``(0, 0, 1, 1)`` — the OOXML coordinate system —
    which is convenient for hand-authored paths.

    Raises |ValueError| for anything that is not a well-formed path in the
    supported commands.
    """
    if not svg or not svg.strip():
        raise ValueError("svg path must be a non-empty string")
    width, height = _viewbox_size(viewbox)
    return _SvgMotionPathWriter(width, height).write(_PathCommands(svg, _SVG_PATH))


def _viewbox_size(viewbox: tuple[float, float, float, float] | None) -> tuple[float, float]:
    """The width and height of *viewbox*, the unit square's when it is ``None``."""
    if viewbox is None:
        return 1.0, 1.0
    _, _, width, height = (float(v) for v in viewbox)
    if width <= 0 or height <= 0:
        raise ValueError(f"viewbox width and height must be positive; got {viewbox!r}")
    return width, height


class _SvgMotionPathWriter:
    """Writes the commands of an SVG path as an OOXML motion path.

    Every point is rebased so that the first moveto lands on ``0 0`` (a
    motion path is relative to where the shape starts) and mapped from a
    viewbox *width* by *height* into the unit square.
    """

    def __init__(self, width: float, height: float):
        self._width = width
        self._height = height
        self._parts: list[str] = []
        # -- the current point, in SVG coordinates --
        self._cursor = (0.0, 0.0)
        # -- where the first moveto landed: the point that becomes ``0 0`` --
        self._origin = (0.0, 0.0)
        self._started = False
        # -- where the current subpath started, which ``Z`` returns to --
        self._subpath_start = (0.0, 0.0)
        self._draw = {
            "M": self._move,
            "L": self._line,
            "H": self._horizontal_line,
            "V": self._vertical_line,
            "C": self._cubic,
            "Q": self._quadratic,
            "Z": self._close,
        }

    def write(self, commands: _PathCommands) -> str:
        """The motion path drawing *commands*, ended with ``E``."""
        for cmd, coordinates in commands:
            self._draw[cmd.upper()](cmd.islower(), coordinates)
        self._parts.append("E")
        return " ".join(self._parts)

    def _move(self, relative: bool, coordinates: list[float]) -> None:
        (point,) = self._points(relative, coordinates)
        if not self._started:
            self._origin = point
            self._started = True
        self._subpath_start = point
        self._emit("M", point)

    def _line(self, relative: bool, coordinates: list[float]) -> None:
        self._emit("L", *self._points(relative, coordinates))

    def _horizontal_line(self, relative: bool, coordinates: list[float]) -> None:
        x, y = self._cursor
        self._emit("L", (coordinates[0] + x if relative else coordinates[0], y))

    def _vertical_line(self, relative: bool, coordinates: list[float]) -> None:
        x, y = self._cursor
        self._emit("L", (x, coordinates[0] + y if relative else coordinates[0]))

    def _cubic(self, relative: bool, coordinates: list[float]) -> None:
        self._emit("C", *self._points(relative, coordinates))

    def _quadratic(self, relative: bool, coordinates: list[float]) -> None:
        # -- a motion path has no quadratic curve; write the cubic tracing it --
        control, end = self._points(relative, coordinates)
        c1x, c1y, c2x, c2y = _cubic_from_quadratic(self._cursor, control, end)
        self._emit("C", (c1x, c1y), (c2x, c2y), end)

    def _close(self, relative: bool, coordinates: list[float]) -> None:
        # -- closing a subpath draws a line back to its start --
        self._emit("L", self._subpath_start)

    def _points(self, relative: bool, coordinates: list[float]) -> list[tuple[float, float]]:
        """*coordinates* as absolute points; relative ones are offsets from the cursor."""
        pairs = zip(coordinates[0::2], coordinates[1::2])
        if not relative:
            return list(pairs)
        cx, cy = self._cursor
        return [(x + cx, y + cy) for x, y in pairs]

    def _emit(self, letter: str, *points: tuple[float, float]) -> None:
        """Write *letter* and *points* rebased and scaled; the last point is the new cursor."""
        origin_x, origin_y = self._origin
        self._parts.append(letter)
        for x, y in points:
            self._parts.append(_fmt((x - origin_x) / self._width))
            self._parts.append(_fmt((y - origin_y) / self._height))
        self._cursor = points[-1]


def _slide_dimensions_emu(slide: Slide) -> tuple[int, int]:
    """Return the (width, height) of *slide*'s presentation in EMU.

    Falls back to PowerPoint's default 10in × 7.5in if either dimension
    is missing (which should not happen for any well-formed deck).
    """
    prs_part = slide.part.package.presentation_part
    presentation = prs_part.presentation
    width = presentation.slide_width or 9_144_000  # 10 inches
    height = presentation.slide_height or 6_858_000  # 7.5 inches
    return int(width), int(height)


def _fmt(value: float) -> str:
    """Format a motion-path coordinate as a plain decimal number.

    ``%g`` emits scientific notation for small magnitudes (``1.5e-17`` from
    sin/cos float noise), which PowerPoint's path parser cannot read — ``e``
    is not part of the number grammar and ``E`` is the End command — so the
    whole animation is dropped.  Fixed-point with six decimals, trailing
    zeros stripped, and float-noise clamped to ``0``.

    Raises |ValueError| for a coordinate that is not finite, which has no
    such form.
    """
    if not math.isfinite(value):
        raise ValueError(f"motion-path coordinate must be a finite number, got {value!r}")
    if abs(value) < 5e-7:
        return "0"
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text
