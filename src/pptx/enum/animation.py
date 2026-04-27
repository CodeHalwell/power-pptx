"""Enumerations for animation-related objects."""

from __future__ import annotations

from pptx.enum.base import BaseEnum


class PP_ANIM_TRIGGER(BaseEnum):
    """Controls when an animation effect starts relative to the previous event.

    Example::

        from pptx.animation import Entrance, Trigger

        Entrance.fade(slide, shape, trigger=Trigger.ON_CLICK)
        Entrance.fade(slide, shape, trigger=Trigger.WITH_PREVIOUS)
    """

    ON_CLICK = (1, "Effect starts on the next mouse click.")
    """Effect starts on the next mouse click."""

    WITH_PREVIOUS = (2, "Effect starts at the same time as the preceding effect.")
    """Effect starts at the same time as the preceding effect."""

    AFTER_PREVIOUS = (3, "Effect starts immediately after the preceding effect finishes.")
    """Effect starts immediately after the preceding effect finishes."""


#: Convenience alias – ``Trigger.ON_CLICK`` reads more naturally than
#: ``PP_ANIM_TRIGGER.ON_CLICK`` in application code.
Trigger = PP_ANIM_TRIGGER
