"""Objects related to layout of rendered text, such as TextFitter."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from PIL import ImageFont

if TYPE_CHECKING:
    from power_pptx.util import Length

#: A renderer starts a new line at each paragraph boundary (`"\n"` in `TextFrame.text`) and at
#: each soft line break (`<a:br>`, `"\v"` in `TextFrame.text`).
_FORCED_LINE_BREAK = re.compile("[\n\v]")

#: Height of one rendered line as a multiple of the point size, when the font does not call for
#: more room than that. See `_line_height()`.
_LINE_HEIGHT_EM = 1.2

_EMU_PER_PT = 12700


class TextFitter(tuple):
    """Value object that knows how to fit text into given rectangular extents.

    The text is laid out the way a renderer lays it out. Every paragraph boundary (`"\\n"`) and
    soft line break (`"\\v"`) starts a new line, and an empty paragraph still occupies one. The
    words of each paragraph wrap greedily at the width of the extents. A word wider than the
    extents cannot be broken, so such text fits at no size.
    """

    def __new__(cls, text, extents, font_file):
        width, height = extents
        return tuple.__new__(cls, (_split_into_segments(text), width, height, font_file))

    @classmethod
    def best_fit_font_size(
        cls, text: str, extents: tuple[Length, Length], max_size: int, font_file: str | None
    ) -> int | None:
        """Return whole-number best fit point size less than or equal to `max_size`.

        The return value is the largest whole-number point size less than or equal to
        `max_size` that allows `text` to fit completely within `extents` when rendered
        using font defined in `font_file`.  Returns ``None`` when even 1pt overflows the
        extents — callers are expected to surface that as an error (see
        :meth:`TextFrame._best_fit_font_size`).

        Raises |ValueError| when `max_size` is less than 1, because no whole-number point size
        qualifies, or when `font_file` cannot be loaded as a font.
        """
        text_fitter = cls(text, extents, font_file)
        return text_fitter._best_fit_font_size(max_size)

    def _best_fit_font_size(self, max_size: int) -> int | None:
        """
        Return the largest whole-number point size less than or equal to
        *max_size* that this fitter can fit, or ``None`` when no size fits.
        """
        if max_size < 1:
            raise ValueError(f"max_size must be at least 1 point, got {max_size!r}")
        predicate = self._fits_inside_predicate
        sizes = _BinarySearchTree.from_ordered_sequence(range(1, int(max_size) + 1))
        return sizes.find_max(predicate)

    def _fits_in_width_predicate(self, point_size):
        """
        Return a function taking a text string value and returns |True| if
        that text fits in this fitter's width when rendered at *point_size*.
        Used by _wrap_lines() to decide where a line must break.
        """

        def predicate(text):
            """
            Return |True| if *text* fits in this fitter's width when rendered
            at *point_size*.
            """
            cx = _rendered_size(text, point_size, self._font_file)[0]
            return cx <= self._width

        return predicate

    @property
    def _fits_inside_predicate(self):
        """Return  function taking an integer point size argument.

        The function returns |True| if the text in this fitter can be wrapped to fit
        entirely within its extents when rendered at that point size.
        """

        def predicate(point_size):
            """Return |True| when the text can be wrapped to fit at `point_size`.

            Fit means the text can be broken into lines that fit the width of `extents`, and
            that those lines stacked on top of each other fit the height of `extents`, when
            rendered at `point_size` using the font defined in `font_file`.
            """
            line_count = self._line_count(point_size)
            if line_count is None:
                # No whole word fits in the available width at this point
                # size; treat as "doesn't fit" so the search continues to
                # smaller sizes rather than crashing.
                return False
            return line_count * _line_height(point_size, self._font_file) <= self._height

        return predicate

    @property
    def _font_file(self):
        return self[3]

    @property
    def _height(self):
        return self[2]

    def _line_count(self, point_size):
        """Return the number of lines this fitter's text occupies at *point_size*.

        Every paragraph and soft line break starts a new line and the words in between wrap
        within the width. Returns ``None`` when a word is wider than the width, so that no
        wrapping can make the text fit at *point_size*.
        """
        line_count = 0
        for words in self._segments:
            lines = self._wrap_lines(words, point_size)
            if lines is None:
                return None
            line_count += len(lines)
        return line_count

    @property
    def _segments(self):
        """The words of each run of text between forced line breaks, in order.

        A segment is a tuple of words, empty for an empty paragraph.
        """
        return self[0]

    @property
    def _width(self):
        return self[1]

    def _wrap_lines(self, words, point_size):
        """
        Return a list of str values representing *words* wrapped within this
        fitter's width when rendered at *point_size*. Each line is made to hold as
        many words as will fit. An empty sequence of words (an empty paragraph)
        still takes up a single, empty line.

        Returns ``None`` when a single word is wider than the available width
        at *point_size*, signalling "no-fit" to callers without raising.
        """
        if not words:
            return [""]
        fits_in_width = self._fits_in_width_predicate(point_size)
        lines = []
        line = ""
        for word in words:
            candidate = f"{line} {word}" if line else word
            if fits_in_width(candidate):
                line = candidate
            elif line and fits_in_width(word):
                lines.append(line)
                line = word
            else:
                return None
        lines.append(line)
        return lines


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
        try:
            return ImageFont.truetype(font_path, point_size)
        except OSError as e:
            # Pillow reports a missing or unreadable file as a bare "cannot open resource"
            # that does not even say which file; name it.
            raise ValueError(
                f"cannot load font file {font_path!r} ({e}); font_file must be the path of a "
                "readable TrueType or OpenType font"
            ) from e


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


def _line_height(point_size, font_file):
    """
    Return the height in English Metric Units (EMU) that one rendered line of
    text takes up at *point_size* in the font defined in *font_file*.

    That is the greater of 1.2 times the point size, which is what a renderer
    allows a line in the typical font, and the ascent plus descent of the font
    itself, since a font with more of either gets taller lines. The ink box
    that Pillow reports for a piece of text is no substitute: it leaves out
    the leading between lines. Pillow measures the ascent and descent in whole
    pixels, rounded outwards, so this errs a little on the high side, which is
    the side that keeps text inside its box.
    """
    height = point_size * _LINE_HEIGHT_EM
    font = _Fonts.font(font_file, point_size)
    try:
        ascent, descent = font.getmetrics()
    except AttributeError:
        # Pillow < 10.1's bitmap default font reports no metrics.
        pass
    else:
        height = max(height, ascent + descent)
    return round(height * _EMU_PER_PT)


def _split_into_segments(text):
    """
    Return a tuple holding a tuple of words for each run of text in *text*
    between forced line breaks, that is, between paragraphs ("\\n") and soft
    line breaks ("\\v"). A segment with no words in it, an empty paragraph, is
    an empty tuple; it still takes up a line.
    """
    return tuple(tuple(segment.split()) for segment in _FORCED_LINE_BREAK.split(text))
