
Working with Presentations
==========================

|pp| allows you to create new presentations as well as make changes to
existing ones. Actually, it only lets you make changes to existing
presentations; it's just that if you start with a presentation that doesn't
have any slides, it feels at first like you're creating one from scratch.

However, a lot of how a presentation looks is determined by the parts that are
left when you delete all the slides, specifically the theme, the slide master,
and the slide layouts that derive from the master. Let's walk through it a step
at a time using examples, starting with the two things you can do with
a presentation, open it and save it.


Opening a presentation
----------------------

The simplest way to get started is to open a new presentation without
specifying a file to open::

    from power_pptx import Presentation

    prs = Presentation()
    prs.save('test.pptx')

This creates a new presentation from the built-in default template and saves it
unchanged to a file named 'test.pptx'. A couple things to note:

* The so-called "default template" is actually just a PowerPoint file that
  doesn't have any slides in it, stored with the installed |pp| package. It's
  the same as what you would get if you created a new presentation from a fresh
  PowerPoint install, a 4x3 aspect ratio presentation based on the "White"
  template. Well, except it won't contain any slides. PowerPoint always adds
  a blank first slide by default.

* You don't need to do anything to it before you save it. If you want to see
  exactly what that template contains, just look in the 'test.pptx' file this
  creates.

* We've called it a *template*, but in fact it's just a regular PowerPoint file
  with all the slides removed. Actual PowerPoint template files (.potx files)
  are something a bit different, though |pp| opens those too (see below). You
  won't need them to work with |pp|.


REALLY opening a presentation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Okay, so if you want any control at all to speak of over the final
presentation, or if you want to change an existing presentation, you need to
open one with a filename::

    prs = Presentation('existing-prs-file.pptx')
    prs.save('new-file-name.pptx')

Things to note:

* You can open any PowerPoint 2007 or later file this way (.ppt files from
  PowerPoint 2003 and earlier won't work). While you might not be able to
  manipulate all the contents yet, whatever is already in there will load and
  save just fine. Parts |pp| has no API for (SmartArt layouts, say) are left
  alone and saved without being understood.

* A file that is not a package |pp| can read — a ``.ppt``, a
  password-protected file, plain text, a zip archive with no presentation in
  it — raises :class:`~power_pptx.exc.InvalidPackageError` with a message
  saying what is wrong. It is a subclass of
  :class:`~power_pptx.exc.PackageNotFoundError` (raised when there is no file
  at the path at all), :class:`zipfile.BadZipFile` and |KeyError|, so older
  ``except`` clauses still catch it. A valid package that is not a
  presentation, such as a Word document, raises |ValueError|.

* If you use the same filename to open and save the file, |pp| will obediently
  overwrite the original file without a peep. You'll want to make sure that's
  what you intend. Saving to a path is atomic: the deck is written to a
  temporary file beside the target and moved into place, so a save that fails
  part-way leaves any existing file as it was.

* A PowerPoint template (``.potx``) or slide show (``.ppsx``) opens the same
  way. What gets written follows the name you save under: ``.potx`` saves a
  template, ``.ppsx`` a slide show, and anything else, including a file-like
  object, an ordinary presentation. So opening ``brand.potx`` and saving
  ``deck.pptx`` gives you a presentation PowerPoint will open::

      prs = Presentation('brand.potx')
      prs.save('deck.pptx')


Opening a 'file-like' presentation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

|pp| can open a presentation from a so-called *file-like* object. It can also
save to a file-like object. This can be handy when you want to get the source
or target presentation over a network connection or from a database and don't
want to (or aren't allowed to) fuss with interacting with the file system. In
practice this means you can pass a file opened in binary mode or a ``BytesIO``
stream object to open or save a presentation like so::

    from io import BytesIO

    with open('foobar.pptx', 'rb') as f:
        prs = Presentation(f)

    # or

    with open('foobar.pptx', 'rb') as f:
        source_stream = BytesIO(f.read())
    prs = Presentation(source_stream)
    source_stream.close()
    ...
    target_stream = BytesIO()
    prs.save(target_stream)

A stream is always saved as an ordinary presentation (``.pptx``).


Okay, so you've got a presentation open and are pretty sure you can save it
somewhere later. Next step is to get a slide in there ...


Validating on save
------------------

A generated deck can be checked on its way out of the door.  Setting
``lint_on_save`` runs the :ref:`layout linter <lint>` over every slide
*before* anything is written::

    prs.lint_on_save = "raise"
    prs.save("out.pptx")     # LintError if a shape ran off the slide

``"off"`` is the default and does no lint work at all; ``"warn"`` logs
each error-severity issue on the ``power_pptx.presentation`` logger and
writes the file anyway; ``"raise"`` raises
:class:`power_pptx.exc.LintError` and writes nothing, so a broken deck
never reaches disk.  Only error-severity issues trigger it.

The setting lives on the in-memory presentation and is not stored in the
``.pptx`` file, so re-opening the saved deck starts you back at ``"off"``.


.. _slide-size:

Slide size
----------

The width and height of the slides belong to the presentation, not to each
slide.  They can be set one at a time or together::

    from power_pptx.util import Inches

    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    prs.set_slide_size(Inches(13.333), Inches(7.5))    # the same, in one call

Setting the size does not move or resize anything already in the deck,
layouts and masters included, so do it before adding content.

Limits
~~~~~~

A slide can be no smaller than 1 inch and no larger than 56 inches in either
direction.  That is PowerPoint's own limit; the two bounds are available as
lengths::

    from power_pptx.util import MAX_SLIDE_SIZE, MIN_SLIDE_SIZE

    MIN_SLIDE_SIZE.inches, MAX_SLIDE_SIZE.inches      # (1.0, 56.0)

A size outside them is refused with a message that says what the limits are::

    >>> prs.set_slide_size(Inches(80), Inches(11.25))
    Traceback (most recent call last):
      ...
    ValueError: slide width must be between 1 and 56 inches (914400 to 51206400
    EMU), got 80 inches (73152000 EMU); pass fit=True to scale the size to fit,
    keeping its proportions

Sizes that are too big: video walls and banners
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

An LED wall is specified in pixels, and at any sensible pixels-per-inch its
size is well past 56 inches.  What matters for such a deck is the *shape* of
the slide, so the thing to do is use the largest slide with the same aspect
ratio and scale the content by the same amount.  Passing ``fit=True`` does the
first part and reports the factor for the second::

    # a 7680 x 1080 px wall, at 96 px to the inch, is 80" x 11.25"
    size = prs.set_slide_size(Inches(7680 / 96), Inches(1080 / 96), fit=True)

    size.width.inches       # 56.0
    size.height.inches      # 7.875
    size.scale              # 0.7

The return value is a :class:`~power_pptx.util.SlideSize`, a ``(width, height,
scale)`` named tuple.  ``scale`` is what the requested size was multiplied by
-- ``1.0`` when it already fit -- so a layout worked out in wall pixels lands
where it should once every coordinate is multiplied by it::

    from power_pptx.util import Pt

    px = size.scale * Inches(1) / 96        # one wall pixel, on the slide

    box = slide.shapes.add_textbox(1920 * px, 120 * px, 3840 * px, 400 * px)
    box.text_frame.text = "Departures"
    box.text_frame.paragraphs[0].font.size = Pt(160 * size.scale)

Font sizes are lengths as well, and need the same factor.

The rules ``fit=True`` follows:

* A size that is already inside the limits is left alone.  It is not enlarged
  because there is room.
* A size that is too large is scaled down until its longer side is exactly 56
  inches.
* A size that is too small is scaled up until its shorter side is exactly
  1 inch, and ``scale`` is then greater than 1.
* A shape more elongated than 56:1 cannot be a slide at any size, and raises
  |ValueError|.

:func:`power_pptx.util.fit_slide_size` does the same arithmetic without
a presentation, which is useful for planning a layout before the deck exists::

    from power_pptx.util import fit_slide_size

    width, height, scale = fit_slide_size(Inches(7680 / 96), Inches(1080 / 96))


.. _slide-show-settings:

Slide-show settings
-------------------

``prs.slide_show`` holds the settings of PowerPoint's *Set Up Slide Show*
dialog: whether the show loops, how it is presented, and whether timings,
narration and animation are used::

    show = prs.slide_show
    show.loop = True                # "Loop continuously until 'Esc'"
    show.show_type = "kiosk"        # "speaker" (default), "window" or "kiosk"
    show.use_timings = True         # False: advance manually, ignore timings
    show.show_narration = True      # False: "Show without narration"
    show.show_animation = True      # False: "Show without animation"

These are stored in ``ppt/presProps.xml`` rather than ``ppt/presentation.xml``,
which is why they used to need hand-edited XML.

A looping display
~~~~~~~~~~~~~~~~~

A deck that has to run unattended on a screen -- built from live data and
shown on a wall display, say -- needs three things: the loop, a show type,
and an advance time on the slides.  ``loop`` alone only changes what happens
after the last slide; something still has to move the show along::

    from power_pptx.enum.presentation import MSO_TRANSITION

    prs.slide_show.loop = True
    prs.slide_show.show_type = "kiosk"
    prs.set_transition(MSO_TRANSITION.FADE, advance_after=5000)   # 5 s a slide

    prs.save("lobby.pptx")

The advance time is a property of each slide's :ref:`transition
<transitions>`, in milliseconds.  Give the transition a kind as well
(``MSO_TRANSITION.CUT`` if you want no visible effect): LibreOffice ignores
the advance time of a slide whose transition has no kind.

Show types
~~~~~~~~~~

``show_type`` accepts a string or a member of
:ref:`PP_SLIDE_SHOW_TYPE <PpSlideShowType>`, and always reads back as a
member:

==============  ================================================================
``"speaker"``   Presented by a speaker, full screen.  The default.
``"window"``    Browsed by an individual, in a window.
``"kiosk"``     Browsed at a kiosk: full screen, and a click does not advance
                the slide, so the slides need advance times or navigation
                buttons.
==============  ================================================================

PowerPoint always loops a kiosk show.  Set ``loop`` as well, so that other
viewers do the same.

What reading and writing do to the file
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Reading a setting never modifies the deck.  A presentation that has no
slide-show settings reports what PowerPoint assumes for it: ``loop`` is
|False|, ``show_type`` is ``SPEAKER`` and the other three are |True|.

The ``<p:showPr>`` element is created the first time a setting is changed,
and removed again once every setting is back at its default, so setting and
resetting a value leaves the file as it was.  The same goes for
``ppt/presProps.xml`` itself in a deck written by a tool that leaves the part
out: it is added, with its relationship, when it is first needed.

Everything else PowerPoint keeps in that part -- the pen colour, the
recently-used colours, its extension lists -- is left untouched.

The four on/off settings take |True| or |False| and nothing else;
``show.loop = "false"`` raises |TypeError| rather than switching the loop on.
