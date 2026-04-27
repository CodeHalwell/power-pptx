"""High-level animation API for python-pptx.

Exposes entrance, exit, and emphasis preset animations that map to
PowerPoint's built-in animation library.  All generated XML is valid
OOXML and round-trips through PowerPoint without loss.

Typical usage::

    from pptx.animation import Entrance, Exit, Emphasis, Trigger

    # Fade a shape in on the next mouse click (default trigger)
    Entrance.fade(slide, shape)

    # Fly in from the bottom, starting with the previous effect
    Entrance.fly_in(slide, shape, trigger=Trigger.WITH_PREVIOUS)

    # Pulse emphasis
    Emphasis.pulse(slide, shape)

    # Fade exit
    Exit.fade(slide, shape)

    # Via the slide proxy
    slide.animations.add_entrance("fade", shape)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pptx.enum.animation import PP_ANIM_TRIGGER
from pptx.oxml.ns import nsdecls, qn
from pptx.oxml import parse_xml

if TYPE_CHECKING:
    from pptx.shapes.base import BaseShape
    from pptx.slide import Slide

#: Short alias; application code reads ``Trigger.ON_CLICK`` more naturally.
Trigger = PP_ANIM_TRIGGER

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

    # -- public API ----------------------------------------------------------

    def add_entrance(
        self,
        preset: str,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
        delay: int = 0,
        duration: int = 500,
        direction: str = "bottom",
    ) -> None:
        """Append an entrance animation for *shape* to the slide timeline.

        *preset* is one of: ``"appear"``, ``"fade"``, ``"fly_in"``,
        ``"float_in"``, ``"wipe"``, ``"zoom"``, ``"wheel"``,
        ``"random_bars"``.

        *direction* is only used for ``"fly_in"``; accepted values are
        ``"bottom"`` (default), ``"top"``, ``"left"``, ``"right"``.
        """
        if preset not in _ENTRANCE_PRESETS:
            raise ValueError(
                f"Unknown entrance preset {preset!r}. "
                f"Choose from: {sorted(_ENTRANCE_PRESETS)}"
            )
        preset_id, preset_subtype = _ENTRANCE_PRESETS[preset]
        behaviors = self._entrance_behaviors(preset, shape.shape_id, duration, direction)
        self._append_effect(
            shape.shape_id, preset_id, "entr", preset_subtype, trigger, delay, behaviors
        )

    def add_exit(
        self,
        preset: str,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
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
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
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
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
        delay: int = 0,
    ) -> None:
        """Shape pops into view instantly (no duration)."""
        slide.animations.add_entrance("appear", shape, trigger=trigger, delay=delay)

    @classmethod
    def fade(
        cls,
        slide: Slide,
        shape: BaseShape,
        *,
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
        delay: int = 0,
        duration: int = 500,
    ) -> None:
        """Shape fades in."""
        slide.animations.add_entrance(
            "fade", shape, trigger=trigger, delay=delay, duration=duration
        )

    @classmethod
    def fly_in(
        cls,
        slide: Slide,
        shape: BaseShape,
        *,
        direction: str = "bottom",
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
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
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
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
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
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
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
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
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
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
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
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
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
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
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
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
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
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
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
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
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
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
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
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
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
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
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
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
        trigger: PP_ANIM_TRIGGER = PP_ANIM_TRIGGER.ON_CLICK,
        delay: int = 0,
        duration: int = 800,
    ) -> None:
        """Shape rocks back and forth (teeter)."""
        slide.animations.add_emphasis(
            "teeter", shape, trigger=trigger, delay=delay, duration=duration
        )
