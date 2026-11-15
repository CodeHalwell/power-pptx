
Working with text
=================

Auto shapes and table cells can contain text. Other shapes can't. Text is
always manipulated the same way, regardless of its container.

Text exists in a hierarchy of three levels:

* :attr:`.Shape.text_frame`
* :attr:`.TextFrame.paragraphs`
* :attr:`._Paragraph.runs`

All the text in a shape is contained in its *text frame*. A text frame has
vertical alignment, margins, wrapping and auto-fit behavior, a rotation angle,
some possible 3D visual features, and can be set to format its text into
multiple columns. It also contains a sequence of paragraphs, which always
contains at least one paragraph, even when empty.

A paragraph has line spacing, space before, space after, available bullet
formatting, tabs, outline/indentation level, and horizontal alignment.
A paragraph can be empty, but if it contains any text, that text is contained
in one or more runs.

A run exists to provide character level formatting, including font typeface,
size, and color, an optional hyperlink target URL, bold, italic, and underline
styles, strikethrough, kerning, and a few capitalization styles like all caps.

Let's run through these one by one. Only features available in the current
release are shown.


Accessing the text frame
------------------------

As mentioned, not all shapes have a text frame. So if you're not sure and you
don't want to catch the possible exception, you'll want to check before
attempting to access it::

    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        text_frame = shape.text_frame
        # do things with the text frame
        ...


Accessing paragraphs
--------------------

A text frame always contains at least one paragraph. This causes the process
of getting multiple paragraphs into a shape to be a little clunkier than one
might like. Say for example you want a shape with three paragraphs::

    paragraph_strs = [
        'Egg, bacon, sausage and spam.',
        'Spam, bacon, sausage and spam.',
        'Spam, egg, spam, spam, bacon and spam.'
    ]

    text_frame = shape.text_frame
    text_frame.clear()  # remove any existing paragraphs, leaving one empty one

    p = text_frame.paragraphs[0]
    p.text = paragraph_strs[0]

    for para_str in paragraph_strs[1:]:
        p = text_frame.add_paragraph()
        p.text = para_str


Adding text
-----------

Only runs can actually contain text. Assigning a string to the ``.text``
attribute on a shape, text frame, or paragraph is a shortcut method for placing
text in a run contained by those objects. The following two snippets produce
the same result::

    shape.text = 'foobar'

    # is equivalent to ...

    text_frame = shape.text_frame
    text_frame.clear()
    p = text_frame.paragraphs[0]
    run = p.add_run()
    run.text = 'foobar'


Applying text frame-level formatting
------------------------------------

The following produces a shape with a single paragraph, a slightly wider bottom
than top margin (these default to 0.05"), no left margin, text aligned top, and
word wrapping turned off. In addition, the auto-size behavior is set to
adjust the width and height of the shape to fit its text. Note that vertical
alignment is set on the text frame. Horizontal alignment is set on each
paragraph::

    from power_pptx.util import Inches
    from power_pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE

    text_frame = shape.text_frame
    text_frame.text = 'Spam, eggs, and spam'
    text_frame.margin_bottom = Inches(0.08)
    text_frame.margin_left = 0
    text_frame.vertical_anchor = MSO_ANCHOR.TOP
    text_frame.word_wrap = False
    text_frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT

The possible values for ``TextFrame.auto_size`` and
``TextFrame.vertical_anchor`` are specified by the enumeration
:ref:`MsoAutoSize` and :ref:`MsoVerticalAnchor` respectively.


Applying paragraph formatting
-----------------------------

The following produces a shape containing three left-aligned paragraphs, the
second and third indented (like sub-bullets) under the first::

    from power_pptx.enum.text import PP_ALIGN

    paragraph_strs = [
        'Egg, bacon, sausage and spam.',
        'Spam, bacon, sausage and spam.',
        'Spam, egg, spam, spam, bacon and spam.'
    ]

    text_frame = shape.text_frame
    text_frame.clear()

    p = text_frame.paragraphs[0]
    p.text = paragraph_strs[0]
    p.alignment = PP_ALIGN.LEFT

    for para_str in paragraph_strs[1:]:
        p = text_frame.add_paragraph()
        p.text = para_str
        p.alignment = PP_ALIGN.LEFT
        p.level = 1


Applying character formatting
-----------------------------

Character level formatting is applied at the run level, using the ``.font``
attribute. The following formats a sentence in 18pt Calibri Bold and applies
the theme color Accent 1.

::

    from power_pptx.dml.color import RGBColor
    from power_pptx.enum.dml import MSO_THEME_COLOR
    from power_pptx.util import Pt

    text_frame = shape.text_frame
    text_frame.clear()  # not necessary for newly-created shape

    p = text_frame.paragraphs[0]
    run = p.add_run()
    run.text = 'Spam, eggs, and spam'

    font = run.font
    font.name = 'Calibri'
    font.size = Pt(18)
    font.bold = True
    font.italic = None  # cause value to be inherited from theme
    font.color.theme_color = MSO_THEME_COLOR.ACCENT_1

If you prefer, you can set the font color to an absolute RGB value. Note that
this will not change color when the theme is changed::

    font.color.rgb = RGBColor(0xFF, 0x7F, 0x50)

A run can also be made into a hyperlink by providing a target URL::

    run.hyperlink.address = 'https://github.com/scanny/python-pptx'


.. _fit-text:

Fitting text to its shape
-------------------------

Generated text rarely arrives at a length you know in advance.
:meth:`TextFrame.fit_text() <power_pptx.text.text.TextFrame.fit_text>` measures
it with real font metrics and writes the largest size at which all of it fits
the shape::

    text_frame = shape.text_frame
    text_frame.text = 'Quarterly results beat the plan in every region – a record year.'
    text_frame.fit_text('DejaVu Sans', max_size=40)    # -> 24 in a 4" x 1.5" box

It turns word wrap on, sets ``auto_size`` to ``MSO_AUTO_SIZE.NONE`` and writes
the size on every run, so the result does not depend on the program that opens
the deck. Lines break where PowerPoint and LibreOffice break them: at spaces,
after hyphens, dashes and the slashes of a long path, and between Chinese,
Japanese and Korean characters (never before closing or after opening
punctuation). The text is measured with the formatting it keeps: each
paragraph's line spacing and the space before and after it, capitals and
letter spacing, including what a placeholder inherits from its layout and
master. For East Asian text the typeface is also written as the run's East
Asian font (``<a:ea>``), which is the one PowerPoint draws those characters
with.

``min_size``, ``max_lines``, ``preserve_breaks`` and ``line_spacing`` (a
multiple such as ``1.2`` or a length such as ``Pt(28)``) constrain the fit.
A fit that cannot meet them raises |ValueError| and changes nothing::

    text_frame.fit_text('DejaVu Sans', max_size=40, min_size=12, max_lines=2)

The result is only as good as the font it is measured with. Name an installed
family, pass ``font_file=``, or register a folder of fonts with
:func:`power_pptx.text.register_font_dir` (see :doc:`authoring-workflows`).
Naming a family that is not installed measures with a fallback font and emits
a :class:`~power_pptx.exc.FontMetricsWarning`; ``strict=True`` raises instead.
:ref:`common_pitfalls` has the details. ``slide.lint()`` measures with the same
engine, so a frame ``fit_text`` sized is not reported as overflowing.

Measuring without a shape
~~~~~~~~~~~~~~~~~~~~~~~~~

:func:`~power_pptx.text.measure_text` wraps text to a width and reports the
lines and the space they take, and :func:`~power_pptx.text.truncate_text`
shortens text with an ellipsis so it fits a number of lines; neither touches a
slide::

    from power_pptx.text import measure_text, truncate_text
    from power_pptx.util import Inches

    m = measure_text('Quarterly results beat the plan in every region',
                     Inches(3), size_pt=18, font_family='DejaVu Sans')
    m.lines        # ('Quarterly results beat', 'the plan in every region')
    m.height.pt    # 51.84: two lines of 1.2 x 18pt, at 1.2 line spacing

    truncate_text('Quarterly results beat the plan in every region',
                  Inches(2), size_pt=18, font_family='DejaVu Sans')
    # 'Quarterly…'

Each line takes 1.2 times the font size times the line spacing, which is how
PowerPoint and LibreOffice lay out a shape. ``line_spacing`` defaults to
``1.2``, the spacing the design components write; pass |None| for
single-spaced text or a length for an exact line height. ``in_table=True``
reserves the font's own ascent and descent when they are taller, as
LibreOffice does in a table cell. A word wider than the width raises
|ValueError| unless ``break_long_words=True``. ``used_fallback`` says whether
the figures come from a fallback font.
