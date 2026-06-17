"""Transitions torture: every MSO_TRANSITION_TYPE kind (including the p14:
extension transitions like MORPH/VORTEX/CONVEYOR), per-slide overrides,
deck-wide set_transition with and without force, advance settings, and clear.
"""

from __future__ import annotations

from _util import blank, deck, save

from power_pptx.enum.presentation import MSO_TRANSITION_TYPE
from power_pptx.util import Inches

KINDS = [
    MSO_TRANSITION_TYPE.NONE, MSO_TRANSITION_TYPE.FADE, MSO_TRANSITION_TYPE.PUSH,
    MSO_TRANSITION_TYPE.WIPE, MSO_TRANSITION_TYPE.SPLIT,
    MSO_TRANSITION_TYPE.RANDOM, MSO_TRANSITION_TYPE.COVER,
    MSO_TRANSITION_TYPE.CUT, MSO_TRANSITION_TYPE.DISSOLVE,
    MSO_TRANSITION_TYPE.ZOOM, MSO_TRANSITION_TYPE.BLINDS,
    MSO_TRANSITION_TYPE.CHECKER, MSO_TRANSITION_TYPE.CIRCLE,
    MSO_TRANSITION_TYPE.DIAMOND, MSO_TRANSITION_TYPE.PLUS,
    MSO_TRANSITION_TYPE.WEDGE, MSO_TRANSITION_TYPE.WHEEL,
    MSO_TRANSITION_TYPE.NEWSFLASH, MSO_TRANSITION_TYPE.STRIPS,
    # p14: extension transitions
    MSO_TRANSITION_TYPE.MORPH, MSO_TRANSITION_TYPE.VORTEX,
    MSO_TRANSITION_TYPE.CONVEYOR, MSO_TRANSITION_TYPE.SWITCH,
    MSO_TRANSITION_TYPE.GALLERY, MSO_TRANSITION_TYPE.FLY_THROUGH,
]


def build():
    prs = deck()

    # --- one slide per transition kind -----------------------------------
    for kind in KINDS:
        s = blank(prs)
        tb = s.shapes.add_textbox(Inches(1), Inches(3), Inches(11), Inches(1.5))
        name = kind.name if hasattr(kind, "name") else str(kind)
        tb.text_frame.text = f"transition: {name}"
        s.transition.kind = kind
        s.transition.duration = 800
        s.transition.advance_on_click = True
        # read-back
        assert s.transition.kind == kind, (name, s.transition.kind)

    # --- per-slide MORPH preserved across deck-wide set_transition -------
    morph_slide = prs.slides[KINDS.index(MSO_TRANSITION_TYPE.MORPH)]
    prs.set_transition(kind=MSO_TRANSITION_TYPE.FADE, duration=400)
    assert morph_slide.transition.kind == MSO_TRANSITION_TYPE.MORPH

    # --- auto-advance everywhere without disturbing kind -----------------
    prs.set_transition(advance_after=6000)

    # --- force overrides a per-slide kind --------------------------------
    s = blank(prs)
    s.transition.kind = MSO_TRANSITION_TYPE.WHEEL
    prs.set_transition(kind=MSO_TRANSITION_TYPE.PUSH, force=True)
    assert s.transition.kind == MSO_TRANSITION_TYPE.PUSH

    # --- clear on a fresh slide ------------------------------------------
    s = blank(prs)
    s.transition.kind = MSO_TRANSITION_TYPE.FADE
    s.transition.clear()
    assert s.transition.kind is None

    return prs


if __name__ == "__main__":
    save(build(), "07_transitions_torture.pptx")
