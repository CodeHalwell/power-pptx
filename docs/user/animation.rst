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
PowerPoint's built-in animation library.  The XML it generates is valid
against the OOXML schema, survives a save → open → save cycle with |pp|,
and imports into LibreOffice as the effect each preset names; playback in
PowerPoint is the open question described above.  Animations authored in
the desktop UI survive a read–modify–write cycle untouched, and effects
added to such a slide join its main sequence.

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
    Entrance.wipe(slide, shape, direction="left")
    Entrance.zoom(slide, shape)
    Entrance.wheel(slide, shape)
    Entrance.random_bars(slide, shape)

    Exit.disappear(slide, shape)
    Exit.fade(slide, shape)
    Exit.fly_out(slide, shape, direction="bottom")
    Exit.float_out(slide, shape)
    Exit.wipe(slide, shape, direction="left")
    Exit.zoom(slide, shape)
    Exit.wheel(slide, shape)
    Exit.random_bars(slide, shape)

    Emphasis.pulse(slide, shape)
    Emphasis.spin(slide, shape)
    Emphasis.teeter(slide, shape)

``direction`` is one of ``"bottom"``, ``"top"``, ``"left"``, ``"right"``
for the presets that have one (fly in/out, wipe); anything else raises
:class:`ValueError`.  Presets without a direction ignore it.

Per-paragraph reveal
--------------------

Pass ``by_paragraph=True`` to fade, wipe, zoom, wheel, random-bar or
appear a text frame in one paragraph at a time.  Each paragraph fires
``AFTER_PREVIOUS`` so the whole sequence plays from a single click;
``direction`` and ``easing`` apply to every paragraph::

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
    MotionPath.custom(slide, shape, "M 0 0 L 0.5 0.5 E")  # OOXML expr
    MotionPath.svg(slide, shape, "M 0 0 H 100 V 50",
                   viewbox=(0, 0, 200, 100))            # SVG path

A raw motion path knows five commands: ``M`` (move to), ``L`` (line to),
``C`` (cubic curve to), ``Z`` (close the loop) and ``E`` (end), in lower
case for coordinates relative to the current point.  Coordinates are
fractions of the slide: ``(0, 0)`` is where the shape starts, ``(1, 0)``
one slide width to its right.  ``custom`` adds the closing ``E`` if it is
left out and raises :class:`ValueError` for anything that is not such a
path.  ``svg`` accepts the wider SVG set (``M L H V C Q Z``, either case)
and converts it; arcs (``A``) and smooth curves (``S``, ``T``) are not
supported and raise :class:`ValueError`.
