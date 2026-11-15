
Working with Slides
===================

Every slide in a presentation is based on a slide layout. Not surprising then
that you have to specify which slide layout to use when you create a new slide.
Let's take a minute to understand a few things about slide layouts that we'll
need so the slide we add looks the way we want it to.


Slide layout basics
-------------------

A slide layout is like a template for a slide. Whatever is on the slide layout
"shows through" on a slide created with it and formatting choices made on the
slide layout are inherited by the slide. This is an important feature for
getting a professional-looking presentation deck, where all the slides are
formatted consistently. Each slide layout is based on the slide master in
a similar way, so you can make presentation-wide formatting decisions on the
slide master and layout-specific decisions on the slide layouts. There can
actually be multiple slide masters, but I'll pretend for now there's only one.
Usually there is.

The presentation themes that come with PowerPoint have about nine slide
layouts, with names like *Title*, *Title and Content*, *Title Only*, and
*Blank*. Each has zero or more placeholders (mostly not zero), preformatted
areas into which you can place a title, multi-level bullets, an image, etc.
More on those later.

The slide layouts in a standard PowerPoint theme always occur in the same
sequence. This allows content from one deck to be pasted into another and be
connected with the right new slide layout:

* Title (presentation title slide)
* Title and Content
* Section Header (sometimes called Segue)
* Two Content (side by side bullet textboxes)
* Comparison (same but additional title for each side by side content box)
* Title Only
* Blank
* Content with Caption
* Picture with Caption

In |pp|, these are ``prs.slide_layouts[0]`` through ``prs.slide_layouts[8]``.
However, there's no rule they have to appear in this order, it's just
a convention followed by the themes provided with PowerPoint. If the deck
you're using as your template has different slide layouts or has them in
a different order, you'll have to work out the slide layout indices for
yourself. It's pretty easy. Just open it up in Slide Master view in PowerPoint
and count down from the top, starting at zero.

Now we can get to creating a new slide.


Adding a slide
--------------

Let's use the Title and Content slide layout; a lot of slides do::

    SLD_LAYOUT_TITLE_AND_CONTENT = 1

    prs = Presentation()
    slide_layout = prs.slide_layouts[SLD_LAYOUT_TITLE_AND_CONTENT]
    slide = prs.slides.add_slide(slide_layout)

A few things to note:

* Using a "constant" value like ``SLD_LAYOUT_TITLE_AND_CONTENT`` is up to you.
  If you're creating many slides it can be handy to have constants defined so
  a reader can more easily make sense of what you're doing. There isn't a set
  of these built into the package because they can't be assured to be right for
  the starting deck you're using.

* ``prs.slide_layouts`` is the collection of slide layouts contained in the
  presentation and has list semantics, at least for item access which is about
  all you can do with that collection at the moment. Using ``prs`` for the
  Presentation instance is purely conventional, but I like it and use it
  consistently.

* ``prs.slides`` is the collection of slides in the presentation, also has
  list semantics for item access, and len() works on it. Note that the method
  to add the slide is on the slide collection, not the presentation. The
  ``add_slide()`` method appends the new slide to the end of the collection;
  ``prs.slides.move(len(prs.slides) - 1, idx)`` then puts it at position
  ``idx``. A slide can also be added as a copy of another, see
  :ref:`duplicating-a-slide`.


.. _hiding-a-slide:

Hiding a slide
--------------

A hidden slide stays in the deck, and can still be edited, but is skipped when
the presentation is run as a slide show.  It is PowerPoint's *Hide Slide*
command::

    slide.hidden = True       # skipped in the show
    slide.hidden              # True
    slide.hidden = False      # shown again

Use it to keep backup material in a deck, or to drop a slide from a generated
show when the data behind it is missing, without renumbering anything::

    for slide, rows in zip(prs.slides, tables):
        slide.hidden = not rows

Hiding a slide sets ``show="0"`` on the slide's ``<p:sld>`` element, which is
what code that reached into ``slide._element`` used to do by hand.  Showing it
again removes the attribute rather than writing ``show="1"``, so a slide that is
hidden and then un-hidden is exactly as it was.  Only |True| and |False| are
accepted; anything else raises |TypeError|.

Hidden slides are still linted, and :ref:`rendering <render>` includes them,
so ``slide_indexes=[n]`` always means ``prs.slides[n]``.


.. _removing-a-slide:

Removing a slide
----------------

``prs.slides.remove(slide)`` deletes a slide from the deck, the way PowerPoint's
*Delete Slide* command does::

    prs.slides.remove(prs.slides[2])

    for slide in list(prs.slides):     # iterate over a copy while removing
        if not slide.shapes:
            prs.slides.remove(slide)

Everything that refers to the slide is updated with it. It leaves its section
(a section it was the last slide of stays, empty) and any custom show. A shape
or text run elsewhere in the deck that jumps to it — a
``click_action.target_slide``, a run's ``hyperlink.target_slide``, or a link on
hover, on a slide, its notes, a layout or a master — keeps its text and
formatting but stops being a link. Its notes, its charts and their workbooks,
and the pictures and media no other slide uses are not saved with the deck any
more; a picture another slide also shows stays. The saved file has no
dangling references, so PowerPoint opens it without offering to repair it.

Don't remove a slide by taking its entry out of ``prs.slides._sldIdLst`` and
dropping the relationship by hand, as was once the only way: that leaves the
slide in the package, reached through any link to it, and in its section.

A slide that is not in the presentation — one from another deck, or one
already removed — raises |ValueError|; the |Slide| object of a removed slide
should not be used again. To leave a slide in the deck but out of the show,
:ref:`hide it <hiding-a-slide>` instead.


.. _duplicating-a-slide:

Duplicating a slide
-------------------

``prs.slides.duplicate(slide)`` adds a copy of a slide right after it and
returns the copy, like PowerPoint's *Duplicate Slide* command. Pass ``index``
to put the copy somewhere else; ``prs.slides[index]`` is the copy afterwards::

    template = prs.slides[1]
    for region in ["North", "South", "East"]:
        copy = prs.slides.duplicate(template, index=-1)    # at the end
        copy.shapes.title.text = region
    prs.slides.remove(template)

The copy is independent of the original. It has its own shapes, its own notes,
and its own copy of each chart and of the workbook behind it, so editing the
text or replacing the chart data of one leaves the other as it was. Pictures,
audio and video are shared rather than stored twice; they cannot be edited in
place, so sharing them is safe, and removing the original later keeps them for
the copy. A link to another slide still leads to that slide; a link from the
slide to itself leads to the copy. The copy uses the same layout as the
original, and in a deck with sections it joins the section of the slide before
it — the original's, unless ``index`` puts it elsewhere.

A slide of another deck raises |ValueError|; to copy a slide between
presentations use :meth:`Presentation.import_slide()
<power_pptx.presentation.Presentation.import_slide>` (see :ref:`compose`), of
which ``duplicate`` is the same-deck case.


Moving slides
-------------

``prs.slides.move(old_index, new_index)`` moves one slide and
``prs.slides.reorder(new_order)`` puts them all in a new order; sections follow
the slides as they do in PowerPoint's slide sorter.


Up next ...
-----------

Ok, now that we have a new slide, let's talk about how to put something on
it ...
