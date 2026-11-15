"""Objects related to layout of rendered text, such as TextFitter."""

from __future__ import annotations

import bisect
import functools
import math
import re
from typing import NamedTuple, Sequence

from PIL import ImageFont

from power_pptx.text._linebreak import (
    asian_latin_gaps,
    break_offsets,
    is_character_start,
    split_words,
)
from power_pptx.util import Length

#: What separates the paragraphs of a text. A vertical tab is a line break
#: inside a paragraph, as in `TextFrame.text`.
_PARAGRAPH_BREAK = re.compile(r"\r\n|[\n\r]")

#: LibreOffice only ends a line after a slash this far or further from the
#: previous space, so that "and/or" and short paths stay in one piece.
_SLASH_REACH = 65

#: Space, in ems, reserved where an East Asian letter meets a Latin one or a
#: digit; LibreOffice adds a little less than this by default.
_ASIAN_LATIN_GAP_EM = 0.25


class ParagraphFormat(NamedTuple):
    """The formatting of one paragraph that changes how much room its text takes.

    `line_spacing` is |None| for single spacing, a number for a multiple of it
    (``1.5``) or a |Length| for an exact distance between lines. `space_before`
    and `space_after` are a |Length|, or a number for that fraction of the font
    size; renderers leave them out above the first paragraph and below the
    last. `letter_spacing` is the tracking added after every character, in EMU.
    Text drawn in capitals is measured by passing it upper-cased.
    """

    line_spacing: float | Length | None = None
    space_before: float | Length = 0
    space_after: float | Length = 0
    letter_spacing: int = 0


class _Layout(NamedTuple):
    """What a fitter has to respect besides its box and its font."""

    line_spacing: float | Length | None = None
    formats: tuple[ParagraphFormat, ...] | None = None
    max_lines: int | None = None
    preserve_breaks: bool = False
    in_table: bool = False
    break_long_words: bool = False


class TextFitter(tuple):
    """Value object that knows how to fit text into given rectangular extents."""

    def __new__(cls, line_source, extents, font_file, letter_spacing=0, layout=None):
        width, height = extents
        return tuple.__new__(
            cls,
            (line_source, width, height, font_file, int(letter_spacing), layout or _Layout()),
        )

    @classmethod
    def best_fit_font_size(
        cls,
        text: str,
        extents: tuple[Length, Length],
        max_size: int,
        font_file: str | None,
        *,
        min_size: int = 1,
        max_lines: int | None = None,
        preserve_breaks: bool = False,
        line_spacing: float | Length | None = None,
        letter_spacing: int = 0,
        paragraph_formats: Sequence[ParagraphFormat] | None = None,
        in_table: bool = False,
        break_long_words: bool = False,
    ) -> int | None:
        """Return whole-number best fit point size less than or equal to `max_size`.

        The return value is the largest whole-number point size less than or equal to
        `max_size` that allows `text` to fit completely within `extents` when rendered
        using font defined in `font_file`.  Returns ``None`` when no size from
        `min_size` up fits the extents — callers are expected to surface that as an
        error (see :meth:`TextFrame._best_fit_font_size`).

        Text wraps where PowerPoint and LibreOffice wrap it: at spaces, after
        hyphens and slashes, and between East Asian characters. Words are kept
        whole when some size from `min_size` up allows it. Only when none does,
        or when `break_long_words` is true, is a word wider than the box split
        at the edge of the box, which is what the renderers do with it.

        `line_spacing` is the spacing the paragraphs will be rendered with: a
        multiple of single spacing, a |Length| for an exact line height, or
        |None| for single spacing. `letter_spacing` is extra tracking in EMU
        added after every character, matching how PowerPoint applies
        ``<a:rPr spc>``. `paragraph_formats` gives these and the space between
        paragraphs separately for each newline-separated paragraph of `text`,
        and takes precedence. `in_table` measures text in a
        table cell, where LibreOffice makes a line as tall as the font's own
        ascent and descent rather than 1.2 times its size.
        """
        if not math.isfinite(letter_spacing):
            raise ValueError("letter_spacing must be finite")
        if (min_size, max_lines, preserve_breaks, line_spacing) != (1, None, False, None):
            _validate_constraints(min_size, max_size, max_lines, line_spacing)
        layout = _Layout(
            line_spacing,
            None if paragraph_formats is None else tuple(paragraph_formats),
            max_lines,
            preserve_breaks,
            in_table,
            break_long_words,
        )
        text_fitter = cls(_LineSource(text), extents, font_file, letter_spacing, layout)
        size = text_fitter._best_fit_font_size(max_size, min_size)
        if size is None and not break_long_words:
            layout = layout._replace(break_long_words=True)
            text_fitter = cls(_LineSource(text), extents, font_file, letter_spacing, layout)
            size = text_fitter._best_fit_font_size(max_size, min_size)
        return size

    def _best_fit_font_size(self, max_size: int, min_size: int = 1) -> int | None:
        """
        Return the largest whole-number point size from *min_size* to
        *max_size* that this fitter can fit, or ``None`` when no size fits.
        """
        if int(max_size) < 1:
            raise ValueError("max_size must be at least 1pt")
        predicate = self._fits_inside_predicate
        sizes = _BinarySearchTree.from_ordered_sequence(range(min_size, int(max_size) + 1))
        return sizes.find_max(predicate)

    @property
    def _fits_inside_predicate(self):
        """Return  function taking an integer point size argument.

        The function returns |True| if the text in this fitter can be wrapped to fit
        entirely within its extents when rendered at that point size.
        """

        def predicate(point_size):
            """Return |True| when text in `line_source` can be wrapped to fit.

            Fit means text can be broken into lines that fit entirely within `extents`
            when rendered at `point_size` using the font defined in `font_file`.
            """
            layout = self._layout
            if layout.formats is None:
                text_lines = self._wrap_lines(self._line_source, point_size)
                line_counts = None if text_lines is None else (len(text_lines),)
            else:
                paragraphs = self._wrap_paragraphs(self._line_source, point_size)
                line_counts = None if paragraphs is None else [len(p) for p in paragraphs]
            if line_counts is None:
                # A word is wider than the box at this point size; treat as
                # "doesn't fit" so the search continues to smaller sizes
                # rather than crashing.
                return False
            line_count = sum(line_counts)
            if layout.max_lines is not None and line_count > layout.max_lines:
                return False
            if layout.preserve_breaks and line_count != self._line_source.explicit_line_count:
                return False
            return self._text_height(point_size, line_counts) <= self._height

        return predicate

    @property
    def _font_file(self):
        return self[3]

    @property
    def _letter_spacing(self):
        return self[4]

    @property
    def _layout(self) -> _Layout:
        return self[5]

    def _line_width(self, text, point_size, letter_spacing=None):
        """Width of `text` in EMU at `point_size`, including letter spacing.

        Where East Asian and Latin text meet, the space a renderer puts between
        them is included too.
        """
        if letter_spacing is None:
            letter_spacing = self._letter_spacing
        width = _rendered_size(text, point_size, self._font_file)[0] + letter_spacing * len(text)
        gaps = asian_latin_gaps(text)
        if gaps:
            width += int(gaps * _ASIAN_LATIN_GAP_EM * point_size * 12700)
        return width

    @property
    def _height(self):
        return self[2]

    @property
    def _line_source(self):
        return self[0]

    @property
    def _width(self):
        return self[1]

    def _text_height(self, point_size, line_counts):
        """Height in EMU of text wrapped to `line_counts` lines in each paragraph.

        A renderer stacks lines one line pitch apart, the first one included,
        and adds the space after a paragraph and the space before the next one
        between them. Neither is added above the first paragraph or below the
        last (LibreOffice measured; it keeps a one-paragraph fit unchanged).
        """
        layout = self._layout
        font_file, in_table = self._font_file, layout.in_table
        if layout.formats is None:
            pitch = _line_pitch(point_size, font_file, layout.line_spacing, in_table)
            return pitch * sum(line_counts)
        height, last = 0, len(layout.formats) - 1
        for index, (paragraph, line_count) in enumerate(zip(layout.formats, line_counts)):
            pitch = _line_pitch(point_size, font_file, paragraph.line_spacing, in_table)
            height += pitch * line_count
            if index > 0:
                height += _paragraph_space(paragraph.space_before, point_size)
            if index < last:
                height += _paragraph_space(paragraph.space_after, point_size)
        return height

    def _wrap_lines(self, line_source, point_size):
        """
        Return a sequence of str values representing the text in
        *line_source* wrapped within this fitter when rendered at
        *point_size*.

        Returns ``None`` when a word in *line_source* is wider than the
        available width at *point_size* and long words are not to be broken,
        signalling "no-fit" to callers without raising.
        """
        paragraphs = self._wrap_paragraphs(line_source, point_size)
        if paragraphs is None:
            return None
        return [line for lines in paragraphs for line in lines]

    def _wrap_paragraphs(self, line_source, point_size):
        """The wrapped lines of each paragraph of *line_source*, or ``None`` on no-fit.

        Paragraph boundaries (\\n) and soft breaks (\\v) always occupy a line,
        including empty and trailing lines.
        """
        formats = self._layout.formats
        paragraphs = _paragraphs(line_source._text)
        if formats is not None and len(formats) != len(paragraphs):
            raise ValueError(
                "paragraph_formats needs one entry for each of the %d paragraphs of the text, "
                "got %d" % (len(paragraphs), len(formats))
            )
        wrapped = []
        letter_spacing = self._letter_spacing
        for index, explicit_lines in enumerate(paragraphs):
            if formats is not None:
                letter_spacing = int(formats[index].letter_spacing)
            lines = []
            for units in explicit_lines:
                unit_lines = self._wrap_units(units, point_size, letter_spacing)
                if unit_lines is None:
                    return None
                lines.extend(unit_lines)
            wrapped.append(lines)
        return wrapped

    def _wrap_units(self, units, point_size, letter_spacing):
        """The lines one explicit line of text wraps to, or ``None`` on no-fit.

        Each line takes as many whole units as fit this fitter's width. The
        rough width of every candidate comes from adding up cached advance
        widths; only the candidates next to the edge of the box are measured
        exactly, so a long text costs a couple of measurements a line.
        """
        text, starts, ends = units.text, units.starts, units.ends
        count = len(ends)
        if not count:
            return [""]
        width, font_file = self._width, self._font_file

        def fits(begin, end):
            return self._line_width(text[begin:end], point_size, letter_spacing) <= width

        estimates = units.estimates(point_size, font_file, letter_spacing)
        budget = width / 12700.0
        tracking = letter_spacing / 12700.0
        lines = []
        first, begin = 0, 0
        while first < count:
            head = ends[first] - begin
            used = estimates[first] - tracking * head
            used -= _advance(text[begin : ends[first]], point_size, font_file)
            last = max(first, bisect.bisect_right(estimates, used + budget, first, count) - 1)
            if fits(begin, ends[last]):
                while last + 1 < count and fits(begin, ends[last + 1]):
                    last += 1
            else:
                last -= 1
                while last >= first and not fits(begin, ends[last]):
                    last -= 1
            if last == count - 1:
                lines.append(text[begin:])
                break
            # -- `cut` is the unit the line ends on, or None when no break fits on it --
            cut = last if last >= first else None
            if cut is not None and units.breaks_after_slash(last):
                cut = self._slash_break(units, first, begin, last, fits)
            if cut is None:
                # -- a renderer then cuts the line where the box ends --
                if not self._layout.break_long_words:
                    return None
                floor = ends[last] if last >= first else begin
                end = _fill(text, begin, floor, ends[last + 1], fits)
            else:
                end = ends[cut]
            lines.append(text[begin:end])
            first = bisect.bisect_left(ends, end)
            if ends[first] == end:
                first += 1
                begin = starts[first] if first < count else end
            else:
                begin = end
        return lines

    @staticmethod
    def _slash_break(units, first, begin, last, fits):
        """Index of the unit a line ends on when unit `last`, which ends in a slash, fits.

        Returns ``None`` when the line is to be cut where the box ends instead.
        This is LibreOffice's handling of paths and URLs: it does not end a
        line with the slash that exactly fills it, and it uses a slash at all
        only when there is no space shortly before it. With a space nearby the
        whole path goes to the next line, or, when the path starts the line, is
        cut at the edge of the box.
        """
        ends, word_starts = units.ends, units.word_starts
        if not fits(begin, ends[last] + 1):
            if last == first:
                return last
            last -= 1
            if not units.breaks_after_slash(last):
                return last
        word_start = word_starts[last]
        # -- a soft line break before the line counts as the space LibreOffice looks for --
        if (word_start == 0 and not units.after_soft_break) or (
            ends[last] - word_start > _SLASH_REACH
        ):
            return last
        if word_start <= begin:
            return None
        while word_starts[last] == word_start:
            last -= 1
        return last


class _Units(object):
    """One explicit line of text, cut into the units a renderer keeps on one line.

    A unit is a word or, where a line may also break inside a word (after a
    hyphen, between East Asian characters), a piece of one. `text` is the line
    with each run of spaces reduced to one space; unit `n` is
    ``text[starts[n]:ends[n]]`` and belongs to the word starting at
    ``word_starts[n]``. `after_soft_break` says a line break (``\\v``), not a
    paragraph start, precedes the line.
    """

    __slots__ = ("text", "starts", "ends", "word_starts", "after_soft_break")

    def __init__(self, text, after_soft_break=False):
        self.after_soft_break = after_soft_break
        words = split_words(text)
        self.text = " ".join(words)
        self.starts, self.ends, self.word_starts = [], [], []
        word_start = 0
        for word in words:
            start = word_start
            for offset in (*break_offsets(word), len(word)):
                self.starts.append(start)
                self.ends.append(word_start + offset)
                self.word_starts.append(word_start)
                start = word_start + offset
            word_start += len(word) + 1

    def breaks_after_slash(self, index):
        """True when unit `index` ends in a slash with more of its word following."""
        end = self.ends[index]
        return (
            self.text[end - 1] == "/"
            and index + 1 < len(self.ends)
            and self.starts[index + 1] == end
        )

    def estimates(self, point_size, font_file, letter_spacing):
        """Estimated width in points of `text` up to the end of each unit."""
        text, tracking = self.text, letter_spacing / 12700.0
        space = _advance(" ", point_size, font_file)
        estimates, total, previous_end = [], 0.0, 0
        for start, end in zip(self.starts, self.ends):
            if start != previous_end:
                total += space
            total += _advance(text[start:end], point_size, font_file)
            estimates.append(total + tracking * end)
            previous_end = end
        return estimates


@functools.lru_cache(maxsize=64)
def _paragraphs(text):
    """The paragraphs of `text`, each a tuple of the |_Units| of its explicit lines."""
    return tuple(
        tuple(_Units(line, index > 0) for index, line in enumerate(paragraph.split("\v")))
        for paragraph in _PARAGRAPH_BREAK.split(text)
    )


def _fill(text, begin, floor, limit, fits):
    """Offset at which a line starting at `begin` is cut for want of a place to break.

    The line takes as many characters as fit, and always at least one. `floor`
    is an offset known to fit and `limit` one known not to.
    """
    low, high = floor, limit - 1
    while low < high:
        middle = (low + high + 1) // 2
        if fits(begin, middle):
            low = middle
        else:
            high = middle - 1
    end = low
    while end > begin and not is_character_start(text, end):
        end -= 1
    if end == begin:
        end += 1
        while end < limit and not is_character_start(text, end):
            end += 1
    return end


def _line_pitch(point_size, font_file, line_spacing=None, in_table=False):
    """Distance in EMU from one line of text to the next at `point_size`.

    PowerPoint, and LibreOffice when it opens a .pptx, make a single-spaced
    line in a shape 1.2 times the point size whatever the font, and scale that
    by the paragraph's line spacing. In a table cell LibreOffice uses the
    font's own ascent and descent instead, so the taller of the two is
    reserved there. A |Length| `line_spacing` is an exact pitch. Pillow's ink
    height of ``"Ty"`` is a floor, for spacing tighter than the glyphs.
    """
    ink_cy = _rendered_size("Ty", point_size, font_file)[1]
    if isinstance(line_spacing, Length):
        return max(ink_cy, int(line_spacing))
    leading = point_size * (max(1.2, _line_height_em(font_file)) if in_table else 1.2)
    if line_spacing is not None:
        leading *= line_spacing
    return max(ink_cy, int(leading * 914400 / 72.0))


def _paragraph_space(space, point_size):
    """EMU of paragraph spacing `space`: a |Length|, or a fraction of the font size."""
    if isinstance(space, Length):
        return int(space)
    return int(space * point_size * 12700)


@functools.lru_cache(maxsize=None)
def _line_height_em(font_file):
    """The font's single-spaced line height (ascent + descent) in ems.

    LibreOffice makes a line of text in a table cell this tall; see
    `_line_pitch`. Falls back to 1.2 em without a font file.
    """
    if font_file is None:
        return 1.2
    try:
        ascent, descent = ImageFont.truetype(font_file, 1000).getmetrics()
    except OSError:
        return 1.2
    return (ascent + descent) / 1000


def _validate_constraints(min_size, max_size, max_lines, line_spacing):
    if isinstance(min_size, bool) or not isinstance(min_size, int) or min_size < 1:
        raise ValueError("min_size must be a positive integer point size")
    if isinstance(max_size, bool) or not isinstance(max_size, int) or max_size < min_size:
        raise ValueError("max_size must be an integer at least min_size")
    if max_lines is not None and (
        isinstance(max_lines, bool) or not isinstance(max_lines, int) or max_lines < 1
    ):
        raise ValueError("max_lines must be a positive integer or None")
    if line_spacing is not None and (
        isinstance(line_spacing, bool) or not math.isfinite(line_spacing) or line_spacing <= 0
    ):
        raise ValueError("line_spacing must be finite and positive")


class _BinarySearchTree(object):
    """
    A node in a binary search tree. Uniform for root, subtree root, and leaf
    nodes.
    """

    def __init__(self, value):
        self._value = value
        self._lesser = None
        self._greater = None

    def find_max(self, predicate, max_=None):
        """
        Return the largest item in or under this node that satisfies
        *predicate*.
        """
        if predicate(self.value):
            max_ = self.value
            next_node = self._greater
        else:
            next_node = self._lesser
        if next_node is None:
            return max_
        return next_node.find_max(predicate, max_)

    @classmethod
    def from_ordered_sequence(cls, iseq):
        """
        Return the root of a balanced binary search tree populated with the
        values in iterable *iseq*.
        """
        seq = list(iseq)
        # optimize for usually all fits by making longest first
        bst = cls(seq.pop())
        bst._insert_from_ordered_sequence(seq)
        return bst

    def insert(self, value):
        """
        Insert a new node containing *value* into this tree such that its
        structure as a binary search tree is preserved.
        """
        side = "_lesser" if value < self.value else "_greater"
        child = getattr(self, side)
        if child is None:
            setattr(self, side, _BinarySearchTree(value))
        else:
            child.insert(value)

    def tree(self, level=0, prefix=""):
        """
        A string representation of the tree rooted in this node, useful for
        debugging purposes.
        """
        text = "%s%s\n" % (prefix, self.value.text)
        prefix = "%s└── " % ("    " * level)
        if self._lesser:
            text += self._lesser.tree(level + 1, prefix)
        if self._greater:
            text += self._greater.tree(level + 1, prefix)
        return text

    @property
    def value(self):
        """
        The value object contained in this node.
        """
        return self._value

    @staticmethod
    def _bisect(seq):
        """
        Return a (medial_value, greater_values, lesser_values) 3-tuple
        obtained by bisecting sequence *seq*.
        """
        if len(seq) == 0:
            return [], None, []
        mid_idx = int(len(seq) / 2)
        mid = seq[mid_idx]
        greater = seq[mid_idx + 1 :]
        lesser = seq[:mid_idx]
        return mid, greater, lesser

    def _insert_from_ordered_sequence(self, seq):
        """
        Insert the new values contained in *seq* into this tree such that
        a balanced tree is produced.
        """
        if len(seq) == 0:
            return
        mid, greater, lesser = self._bisect(seq)
        self.insert(mid)
        self._insert_from_ordered_sequence(greater)
        self._insert_from_ordered_sequence(lesser)


class _LineSource(object):
    """
    Generates all the possible even-word line breaks in a string of text,
    each in the form of a (line, remainder) 2-tuple where *line* contains the
    text before the break and *remainder* the text after as a |_LineSource|
    object. Its boolean value is |True| when it contains text, |False| when
    its text is the empty string or whitespace only.
    """

    def __init__(self, text):
        self._text = text

    def __bool__(self):
        """
        Gives this object boolean behaviors (in Python 3). bool(line_source)
        is False if it contains the empty string or whitespace only.
        """
        return self._text.strip() != ""

    def __eq__(self, other):
        return self._text == other._text

    @property
    def explicit_line_count(self):
        """Number of lines the text has before any wrapping: its paragraphs and soft breaks."""
        return len(re.split(r"\r\n|[\n\v\r]", self._text))

    def __iter__(self):
        """
        Generate a (text, remainder) pair for each possible even-word line
        break in this line source, where *text* is a str value and remainder
        is a |_LineSource| value.
        """
        words = self._text.split()
        for idx in range(1, len(words) + 1):
            line_text = " ".join(words[:idx])
            remainder_text = " ".join(words[idx:])
            remainder = _LineSource(remainder_text)
            yield _Line(line_text, remainder)

    def __nonzero__(self):
        """
        Gives this object boolean behaviors (in Python 2). bool(line_source)
        is False if it contains the empty string or whitespace only.
        """
        return self._text.strip() != ""

    def __repr__(self):
        return "<_LineSource('%s')>" % self._text


class _Line(tuple):
    """
    A candidate line broken at an even word boundary from a string of text,
    and a |_LineSource| value containing the text that remains after the line
    is broken at this spot.
    """

    def __new__(cls, text, remainder):
        return tuple.__new__(cls, (text, remainder))

    def __gt__(self, other):
        return len(self.text) > len(other.text)

    def __lt__(self, other):
        return not self.__gt__(other)

    def __len__(self):
        return len(self.text)

    def __repr__(self):
        return "'%s' => '%s'" % (self.text, self.remainder)

    @property
    def remainder(self):
        return self[1]

    @property
    def text(self):
        return self[0]


class _Fonts(object):
    """
    A memoizing cache for ImageFont objects.
    """

    fonts = {}

    @classmethod
    def font(cls, font_path, point_size):
        key = (font_path, point_size)
        if key not in cls.fonts:
            cls.fonts[key] = cls._load(font_path, point_size)
        return cls.fonts[key]

    @staticmethod
    def _load(font_path, point_size):
        if font_path is None:
            # `font_path=None` opts in to Pillow's bundled default font; this
            # is the fallback when no matching system font can be located, so
            # `TextFrame.fit_text` works on platforms without the requested
            # family installed (notably most Linux runtimes).
            try:
                return ImageFont.load_default(size=point_size)
            except TypeError:
                # Pillow < 10.1 does not accept a `size` argument; fall back
                # to the unsized bitmap default. Less accurate but at least
                # never blows up.
                return ImageFont.load_default()
        return ImageFont.truetype(font_path, point_size)


def _rendered_size(text, point_size, font_file):
    """
    Return a (width, height) pair representing the size of *text* in English
    Metric Units (EMU) when rendered at *point_size* in the font defined in
    *font_file*.
    """
    emu_per_inch = 914400
    px_per_inch = 72.0

    font = _Fonts.font(font_file, point_size)
    try:
        px_width, px_height = font.getsize(text)
    except AttributeError:
        left, top, right, bottom = font.getbbox(text)
        px_width, px_height = right - left, bottom - top

    emu_width = int(px_width / px_per_inch * emu_per_inch)
    emu_height = int(px_height / px_per_inch * emu_per_inch)

    return emu_width, emu_height


@functools.lru_cache(maxsize=65536)
def _advance(text, point_size, font_file):
    """Distance in points the pen moves drawing *text* at *point_size*.

    Unlike `_rendered_size`, the advances of the pieces of a line add up to
    the advance of the line, so one cached value per word estimates the width
    of any line the word appears in.
    """
    font = _Fonts.font(font_file, point_size)
    try:
        return font.getlength(text)
    except AttributeError:
        # -- Pillow's unsized bitmap default font, before Pillow 9.2 --
        return _rendered_size(text, point_size, font_file)[0] / 12700.0
