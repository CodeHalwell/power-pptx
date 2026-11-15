"""Where a renderer may start a new line inside text that contains no spaces.

PowerPoint and LibreOffice wrap at more than whitespace: between East Asian
characters, after a hyphen or dash, after the slashes of a long path. This
module reproduces the part of the Unicode line-breaking algorithm (UAX #14)
they apply, with the tailorings LibreOffice makes to it, so text can be wrapped
for measurement the way it will be wrapped on the slide.

East Asian text follows the kinsoku rules: a line never starts with closing
punctuation (``、。」）``, a small kana, the prolonged-sound mark ``ー``) and never
ends with opening punctuation (``「（``). Renderers differ on the small kana and
on letting ``、。`` hang past the margin; the stricter reading is used here, so a
measured line is never longer than a rendered one.

Text in scripts that need a dictionary to find word boundaries (Thai, Lao,
Khmer, Burmese) is treated as one word.
"""

from __future__ import annotations

import functools
import re
import unicodedata

# -- line-breaking classes, named as in UAX #14 (HG is Hangul, which
# -- LibreOffice keeps together as words rather than breaking per syllable) --
(AL, BA, B2, CL, CM, EX, GL, HG, HY, ID, IN, IS, NS, NU, OP, PO, PR, QU, SY, ZW) = range(20)

_CLASS_OF = {
    char: class_
    for class_, chars in (
        # -- glue: no-break space, figure space, non-breaking hyphen, narrow
        # -- no-break space, word joiner, zero-width no-break space and joiner --
        (GL, "\u00a0\u2007\u2011\u202f\u2060\ufeff\u200d"),
        (ZW, "\u200b"),
        # -- break after: soft hyphen, hyphen, figure and en dash, hyphenation point --
        (BA, "\u00ad\u2010\u2012\u2013\u2027|"),
        (HY, "-"),
        (B2, "\u2014\u2e3a\u2e3b"),
        # -- LibreOffice treats the backslash of a Windows path like a slash --
        (SY, "/\\"),
        # -- infix punctuation; the middle dot, double bar and bullet behave the same
        # -- way in the Chinese kinsoku lists, holding on to what comes before --
        (IS, ",.:;\u00b7\u2016\u2022\u037e\u0589\u060c\u060d\u2044\ufe10\ufe13\ufe14\ufe30"),
        (EX, "!?\u05c6\u061b\u061e\u061f\u06d4\ufe15\ufe16\ufe56\ufe57\uff01\uff1f"),
        (QU, "\"'\u275b\u275c\u275d\u275e"),
        (OP, "\u00a1\u00bf"),
        (CL, "\u3001\u3002\ufe11\ufe12\ufe50\ufe52\uff0c\uff0e\uff61\uff64"),
        (
            NS,
            # -- iteration marks, sound marks, middle dots, fullwidth colon and
            # -- semicolon, wave dash and the vertical forms kinsoku lists name --
            "\u203c\u2047\u2048\u2049\u3005\u301c\u303b\u309b\u309c\u309d\u309e"
            "\u30a0\u30fb\u30fd\u30fe\ufe31\ufe33\ufe34\ufe4f\ufe54\ufe55\uff1a\uff1b\uff5c\uff5e"
            "\uff65\uff9e\uff9f"
            # -- small kana and the prolonged-sound mark --
            "\u3041\u3043\u3045\u3047\u3049\u3063\u3083\u3085\u3087\u308e\u3095\u3096"
            "\u30a1\u30a3\u30a5\u30a7\u30a9\u30c3\u30e3\u30e5\u30e7\u30ee\u30f5\u30f6\u30fc"
            "\uff67\uff68\uff69\uff6a\uff6b\uff6c\uff6d\uff6e\uff6f\uff70",
        ),
        (
            PO,
            "%\u00a2\u00b0\u2030\u2031\u2032\u2033\u2034\u2035\u2036\u2037\u2103\u2109"
            "\ufe6a\uff05\uffe0",
        ),
        (PR, "+\u00b1\u2116\u2212\u2213"),
        (IN, "\u2024\u2025\u2026\ufe19"),
    )
    for char in chars
}

#: Whitespace a line may break at: any space except the no-break spaces, which
#: hold the words on either side of them together.
_BREAKING_SPACE = re.compile("[^\\S\u00a0\u2007\u202f]+")


_WORD = re.compile("[\\S\u00a0\u2007\u202f]+")


def split_words(text: str) -> list[str]:
    """The words of `text`: the runs of characters between breaking spaces."""
    return [word for word in _BREAKING_SPACE.split(text) if word]


def line_start_offsets(text: str) -> list[int]:
    """Ascending offsets in `text` at which a renderer may start a new line.

    These are the start of every word but the first and the places inside a
    word that `break_offsets` gives.
    """
    offsets: list[int] = []
    for index, match in enumerate(_WORD.finditer(text)):
        start = match.start()
        if index:
            offsets.append(start)
        offsets.extend(start + offset for offset in break_offsets(match.group()))
    return offsets


@functools.lru_cache(maxsize=4096)
def _class_of(char: str) -> int:
    """The line-breaking class of `char`."""
    class_ = _CLASS_OF.get(char)
    if class_ is not None:
        return class_
    category = unicodedata.category(char)
    code = ord(char)
    # -- combining marks, variation selectors and emoji skin tones stay with their base --
    if category in ("Mn", "Mc", "Me") or 0x1F3FB <= code <= 0x1F3FF:
        return CM
    if category == "Ps":
        return OP
    if category == "Pe":
        return CL
    if category in ("Pi", "Pf"):
        return QU
    if category == "Sc":
        return PR
    if 0xAC00 <= code <= 0xD7A3 or 0x1100 <= code <= 0x11FF or 0x3130 <= code <= 0x318F:
        return HG
    # -- East Asian wide and fullwidth characters, and halfwidth katakana --
    if unicodedata.east_asian_width(char) in ("W", "F") or 0xFF66 <= code <= 0xFF9D:
        return ID
    if category == "Nd":
        return NU
    return AL


def _may_break(before: int, after: int, in_number: bool, after_number: bool) -> bool:
    """True when a line may end between a character of class `before` and one of `after`.

    `in_number` says `before` belongs to a number such as ``1,234.5`` or
    ``12/31``; `after_number` says it is the bracket closing one.
    """
    if after in (CM, GL, ZW) or before == GL:
        return False
    if before == ZW:
        return True
    if after in (CL, EX, IS, SY, BA, HY, NS) or before == OP:
        return False
    if QU in (before, after) or before == after in (B2, HG):
        return False
    if after == IN:
        return before not in (AL, ID, HG, IN, NU)
    if after == NU:
        return not (in_number or before in (AL, PR, PO, IS, CL))
    if after in (PR, PO) and (in_number or after_number):
        return False
    if after == PO:
        return before not in (ID, HG)
    if after == PR:
        return before != AL
    if after == AL:
        return before not in (AL, NU, PR, PO, IS, CL)
    if after == OP:
        return before not in (AL, NU)
    # -- an East Asian character or a dash: only a currency sign holds on to the former --
    return not (before == PR and after in (ID, HG))


@functools.lru_cache(maxsize=8192)
def break_offsets(word: str) -> tuple[int, ...]:
    """Offsets inside `word` at which a renderer may end a line.

    `word` is text between two spaces. ``"state-of-the-art"`` gives ``(6, 9,
    13)`` (after each hyphen); ordinary words give ``()``.
    """
    if word.isascii() and word.isalnum():
        return ()
    offsets: list[int] = []
    before = -1
    in_number = after_number = False
    for offset, char in enumerate(word):
        after = _class_of(char)
        if before == -1:
            if after == CM:
                continue
        elif after == OP and before in (PR, PO) and _next_is_digit(word, offset):
            pass  # -- "$(100)": the sign stays with the bracketed amount --
        elif _may_break(before, after, in_number, after_number):
            offsets.append(offset)
        if after == CM:
            continue
        after_number = in_number and after == CL
        in_number = after == NU or (in_number and after in (SY, IS))
        before = after
    return tuple(offsets)


def _next_is_digit(word: str, offset: int) -> bool:
    return offset + 1 < len(word) and _class_of(word[offset + 1]) == NU


@functools.lru_cache(maxsize=4096)
def _script_side(char: str) -> int:
    """1 for an East Asian letter, 2 for any other letter, digit or symbol, else 0."""
    category = unicodedata.category(char)
    if unicodedata.east_asian_width(char) in ("W", "F"):
        return 1 if category[0] == "L" else 0
    if category[0] in ("Z", "C") or category in ("Ps", "Pe", "Pi", "Pf", "Pd"):
        return 0
    return 2


def asian_latin_gaps(text: str) -> int:
    """How many times an East Asian letter directly meets a Latin letter, digit or symbol.

    LibreOffice puts about a quarter of an em between the two (its "space
    between Asian and non-Asian text", on by default), as in ``"売上高はQ3"``.
    """
    if text.isascii():
        return 0
    gaps, previous = 0, 0
    for char in text:
        side = _script_side(char)
        if side and previous and side != previous:
            gaps += 1
        previous = side
    return gaps


def split_full_width(text: str) -> tuple[str, int]:
    """Return `text` without its wide and fullwidth characters, and how many there were.

    Those characters occupy exactly one em in every East Asian font, and a
    renderer draws them in such a font even when the run names a Latin face
    that has no glyph for them. Measuring them in the named face would give
    the width of its "missing glyph" box instead (0.69 em in Outfit, for
    example), so the engine counts each as one em and measures the rest.
    """
    if text.isascii():
        return text, 0
    narrow = [char for char in text if unicodedata.east_asian_width(char) not in ("W", "F")]
    return "".join(narrow), len(text) - len(narrow)


def has_east_asian(text: str) -> bool:
    """True when `text` has a wide or fullwidth character, as East Asian scripts do."""
    return not text.isascii() and any(
        unicodedata.east_asian_width(char) in ("W", "F") for char in text
    )


def is_character_start(text: str, offset: int) -> bool:
    """True when a new character starts at `offset`, so `text` may be cut there.

    False in front of a combining mark and on either side of a zero-width joiner.
    """
    return _class_of(text[offset]) != CM and "\u200d" not in text[offset - 1 : offset + 1]
