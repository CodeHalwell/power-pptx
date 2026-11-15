.. _transitions:

Slide transitions
=================

Each slide exposes a ``transition`` proxy backed by ``<p:transition>``.
Reads on an unset transition return |None| and never mutate XML, keeping
theme inheritance intact.

Per-slide
---------

::

    from power_pptx.enum.presentation import MSO_TRANSITION_TYPE

    slide.transition.kind = MSO_TRANSITION_TYPE.MORPH
    slide.transition.duration = 1500          # milliseconds
    slide.transition.advance_on_click = True
    slide.transition.advance_after = 5000     # auto-advance after 5s

    slide.transition.clear()                  # remove the element

``MSO_TRANSITION_TYPE`` has the 21 transitions of the ISO standard
(``BLINDS``, ``CHECKER``, ``CIRCLE``, ``COMB``, ``COVER``, ``CUT``,
``DIAMOND``, ``DISSOLVE``, ``FADE``, ``NEWSFLASH``, ``PLUS``, ``PULL``,
``PUSH``, ``RANDOM``, ``RANDOM_BAR``, ``SPLIT``, ``STRIPS``, ``WEDGE``,
``WHEEL``, ``WIPE``, ``ZOOM``), the PowerPoint 2010 ``CONVEYOR``,
``FLY_THROUGH``, ``GALLERY``, ``SWITCH`` and ``VORTEX``, and the
PowerPoint 2016 ``MORPH``, plus ``NONE`` for an explicit "no
transition".  Direction modifiers are not yet exposed.

A transition PowerPoint wrote in a kind with no member (the PowerPoint
2013 Airplane, Curtains, Wind and so on) reads as |None| and is saved
back exactly as it was read unless it is changed.

Deck-wide
---------

``Presentation.set_transition(...)`` applies the same transition (or a
partial update) to every slide in one call.  Unspecified kwargs leave
each slide's existing setting untouched::

    prs.set_transition(kind=MSO_TRANSITION_TYPE.FADE, duration=750)
    prs.set_transition(advance_on_click=True)

A deck-wide ``kind`` skips slides that already have a kind of their own
(pass ``force=True`` to overwrite those too); a slide whose transition
only carries timing settings has none yet and gets the new kind.
