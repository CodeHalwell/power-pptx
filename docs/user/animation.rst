.. _animation:

Animations
==========

.. warning::

   **Experimental — playback is currently broken in PowerPoint.**
   Animation timing XML produced by this module round-trips through
   the OOXML schema and reads back correctly via the introspection
   API, but in PowerPoint slideshow mode animated shapes sit at
   10–15% opacity for several seconds and then snap to fully visible
   all at once instead of playing the requested animation.
   LibreOffice renders the animation correctly when converting to
   PDF.  Slides that combine entrance animations with a Morph
   transition can additionally trigger PowerPoint's "Repair?" dialog
   on open.

   Until this is resolved, prefer slide :doc:`transitions <transitions>`
   (which round-trip and play correctly) over animations.  See
   ``IMPROVEMENT_PLAN.md`` (item 1) for the diagnostic plan.

|pp| ships a preset-only animation API that maps directly onto
PowerPoint's built-in animation library.  All generated XML is valid OOXML
and round-trips through PowerPoint without loss.  Animations authored in
the desktop UI survive a read–modify–write cycle untouched.

Triggers
--------

Every preset accepts an optional ``trigger`` and ``delay``::

    from power_pptx.animation import Entrance, Trigger

    Entrance.fade(slide, shape)                                # ON_CLICK
    Entrance.fly_in(slide, shape, trigger=Trigger.WITH_PREVIOUS)
    Entrance.zoom(slide, shape, trigger=Trigger.AFTER_PREVIOUS,
                  delay=500)

Entrance / exit / emphasis presets
----------------------------------

::

    Entrance.appear(slide, shape)
    Entrance.fade(slide, shape)
    Entrance.fly_in(slide, shape, direction="bottom")
    Entrance.float_in(slide, shape)
    Entrance.wipe(slide, shape)
    Entrance.zoom(slide, shape)
    Entrance.wheel(slide, shape)
    Entrance.random_bars(slide, shape)

    Exit.disappear(slide, shape)
    Exit.fade(slide, shape)
    Exit.fly_out(slide, shape)

    Emphasis.pulse(slide, shape)
    Emphasis.spin(slide, shape)
    Emphasis.teeter(slide, shape)

Per-paragraph reveal
--------------------

Pass ``by_paragraph=True`` to fade, wipe, zoom, wheel, or appear a text
frame in one paragraph at a time.  Each paragraph fires
``AFTER_PREVIOUS`` so the whole sequence plays from a single click::

    Entrance.fade(slide, body_text_frame, by_paragraph=True)

Sequencing
----------

A context manager defaults the first effect inside the block to the
caller-supplied (or ``ON_CLICK``) trigger and chains the rest with
``AFTER_PREVIOUS``::

    with slide.animations.sequence():
        Entrance.fade(slide, title)
        Entrance.fly_in(slide, body)
        Emphasis.pulse(slide, badge)

Sequences are not nestable; explicit per-call triggers still win.

Motion paths
------------

::

    from power_pptx.animation import MotionPath
    from power_pptx.util import Inches

    MotionPath.line(slide, shape, Inches(2), Inches(1))
    MotionPath.diagonal(slide, shape, Inches(3), Inches(2))
    MotionPath.circle(slide, shape, radius=Inches(1), clockwise=True)
    MotionPath.arc(slide, shape, Inches(3), Inches(0), height=0.4)
    MotionPath.zigzag(slide, shape, Inches(4), Inches(0),
                      segments=6, amplitude=0.2)
    MotionPath.spiral(slide, shape, Inches(2), turns=2.5)
    MotionPath.custom(slide, shape, "M 0 0 L 0.5 0.5")  # OOXML expr
