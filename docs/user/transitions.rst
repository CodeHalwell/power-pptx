.. _transitions:

Slide transitions
=================

Each slide exposes a ``transition`` proxy backed by ``<p:transition>``.
Reads on an unset transition return |None| and never mutate XML, keeping
theme inheritance intact.

Per-slide
---------

::

    from pptx.enum.action import MSO_TRANSITION_TYPE

    slide.transition.kind = MSO_TRANSITION_TYPE.MORPH
    slide.transition.duration = 1500          # milliseconds
    slide.transition.advance_on_click = True
    slide.transition.advance_after = 5000     # auto-advance after 5s

    slide.transition.clear()                  # remove the element

The supported set covers 25+ kinds, including Morph, Vortex, Conveyor,
Switch, Gallery, and Fly Through.  Direction modifiers are not yet
exposed.

Deck-wide
---------

``Presentation.set_transition(...)`` applies the same transition (or a
partial update) to every slide in one call.  Unspecified kwargs leave
each slide's existing setting untouched::

    prs.set_transition(kind=MSO_TRANSITION_TYPE.FADE, duration=750)
    prs.set_transition(advance_on_click=True)
