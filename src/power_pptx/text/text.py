"""Text-related objects such as TextFrame and Paragraph."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, cast

from power_pptx.dml.color import _LazyColorFormat
from power_pptx.dml.effect import GlowFormat, ShadowFormat
from power_pptx.dml.fill import FillFormat
from power_pptx.dml.line import LineFormat
from power_pptx.enum.lang import MSO_LANGUAGE_ID
from power_pptx.enum.text import MSO_AUTO_SIZE, MSO_UNDERLINE, MSO_VERTICAL_ANCHOR
from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT
from power_pptx.oxml.simpletypes import ST_TextWrappingType
from power_pptx.shapes import Subshape
from power_pptx.text.fonts import FontFiles
from power_pptx.text.layout import TextFitter
from power_pptx.util import Centipoints, Emu, Length, Pt, lazyproperty

if TYPE_CHECKING:
    from power_pptx.dml.color import ColorFormat
    from power_pptx.enum.text import (
        MSO_TEXT_UNDERLINE_TYPE,
        MSO_VERTICAL_ANCHOR,
        PP_PARAGRAPH_ALIGNMENT,
    )
    from power_pptx.oxml.action import CT_Hyperlink
    from power_pptx.oxml.text import (
        CT_RegularTextRun,
        CT_TextBody,
        CT_TextCharacterProperties,
        CT_TextParagraph,
        CT_TextParagraphProperties,
        CT_TextTabStop,
    )
    from power_pptx.parts.slide import SlidePart
    from power_pptx.slide import Slide
    from power_pptx.types import ProvidesExtents, ProvidesPart


class TextFrame(Subshape):
    """The part of a shape that contains its text.

    Not all shapes have a text frame. Corresponds to the `p:txBody` element that can
    appear as a child element of `p:sp`. Not intended to be constructed directly.
    """

    def __init__(self, txBody: CT_TextBody, parent: ProvidesPart):
        super(TextFrame, self).__init__(parent)
        self._element = self._txBody = txBody
        self._parent = parent

    def add_paragraph(self):
        """
        Return new |_Paragraph| instance appended to the sequence of
        paragraphs contained in this text frame.
        """
        p = self._txBody.add_p()
        return _Paragraph(p, self)

    @property
    def auto_size(self) -> MSO_AUTO_SIZE | None:
        """Resizing strategy used to fit text within this shape.

        Determins the type of automatic resizing used to fit the text of this shape within its
        bounding box when the text would otherwise extend beyond the shape boundaries. May be
        |None|, `MSO_AUTO_SIZE.NONE`, `MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT`, or
        `MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE`.
        """
        return self._bodyPr.autofit

    @auto_size.setter
    def auto_size(self, value: MSO_AUTO_SIZE | None):
        self._bodyPr.autofit = value

    def clear(self):
        """Remove all paragraphs except one empty one."""
        for p in self._txBody.p_lst[1:]:
            self._txBody.remove(p)
        p = self.paragraphs[0]
        p.clear()

    def fit_text(
        self,
        font_family: str = "Calibri",
        max_size: int = 18,
        bold: bool = False,
        italic: bool = False,
        font_file: str | None = None,
    ):
        """Fit text-frame text entirely within bounds of its shape.

        Make the text in this text frame fit entirely within the bounds of its shape by setting
        word wrap on and applying the "best-fit" font size to all the text it contains.

        :attr:`TextFrame.auto_size` is set to :attr:`MSO_AUTO_SIZE.NONE`. The font size will not
        be set larger than `max_size` points. If the path to a matching TrueType font is provided
        as `font_file`, that font file will be used for the font metrics. If `font_file` is |None|,
        best efforts are made to locate a font file with matchhing `font_family`, `bold`, and
        `italic` installed on the current system (usually succeeds if the font is installed).
        """
        # ---no-op when empty as fit behavior not defined for that case---
        if self.text == "":
            return  # pragma: no cover

        font_size = self._best_fit_font_size(font_family, max_size, bold, italic, font_file)
        self._apply_fit(font_family, font_size, bold, italic)

    @property
    def margin_bottom(self) -> Length:
        """|Length| value representing the inset of text from the bottom text frame border.

        :meth:`power_pptx.util.Inches` provides a convenient way of setting the value, e.g.
        `text_frame.margin_bottom = Inches(0.05)`.
        """
        return self._bodyPr.bIns

    @margin_bottom.setter
    def margin_bottom(self, emu: Length):
        self._bodyPr.bIns = emu

    @property
    def margin_left(self) -> Length:
        """Inset of text from left text frame border as |Length| value."""
        return self._bodyPr.lIns

    @margin_left.setter
    def margin_left(self, emu: Length):
        self._bodyPr.lIns = emu

    @property
    def margin_right(self) -> Length:
        """Inset of text from right text frame border as |Length| value."""
        return self._bodyPr.rIns

    @margin_right.setter
    def margin_right(self, emu: Length):
        self._bodyPr.rIns = emu

    @property
    def margin_top(self) -> Length:
        """Inset of text from top text frame border as |Length| value."""
        return self._bodyPr.tIns

    @margin_top.setter
    def margin_top(self, emu: Length):
        self._bodyPr.tIns = emu

    @property
    def paragraphs(self) -> tuple[_Paragraph, ...]:
        """Sequence of paragraphs in this text frame.

        A text frame always contains at least one paragraph.
        """
        return tuple([_Paragraph(p, self) for p in self._txBody.p_lst])

    @property
    def text(self) -> str:
        """All text in this text-frame as a single string.

        Read/write. The return value contains all text in this text-frame. A line-feed character
        (`"\\n"`) separates the text for each paragraph. A vertical-tab character (`"\\v"`) appears
        for each line break (aka. soft carriage-return) encountered.

        The vertical-tab character is how PowerPoint represents a soft carriage return in clipboard
        text, which is why that encoding was chosen.

        Assignment replaces all text in the text frame. A new paragraph is added for each line-feed
        character (`"\\n"`) encountered. A line-break (soft carriage-return) is inserted for each
        vertical-tab character (`"\\v"`) encountered.

        Any control character other than newline, tab, or vertical-tab are escaped as plain-text
        like "_x001B_" (for ESC (ASCII 32) in this example).
        """
        return "\n".join(paragraph.text for paragraph in self.paragraphs)

    @text.setter
    def text(self, text: str):
        txBody = self._txBody
        txBody.clear_content()
        for p_text in text.split("\n"):
            p = txBody.add_p()
            p.append_text(p_text)

    def set_paragraph_defaults(
        self,
        *,
        font_name: str | None = None,
        size: Length | None = None,
        bold: bool | None = None,
        italic: bool | None = None,
        color: object | None = None,
    ) -> None:
        """Apply default font properties to every paragraph/run in this text frame.

        Sets the supplied properties on each existing paragraph (and on
        every run inside each paragraph) **only where the property is
        currently unset** — explicit per-run overrides are preserved
        verbatim.  Pass only the keyword arguments you want to enforce.

        Branded decks repeatedly want to set the same six lines
        (``font.name``, ``font.size``, ``font.bold``, ``font.color.rgb``)
        on every paragraph in a card body.  This wrapper collapses that
        ritual into one call::

            from power_pptx.util import Pt

            tf.set_paragraph_defaults(
                font_name="Inter",
                size=Pt(14),
                color="#222222",
            )

        ``color`` accepts any "color-like" value supported by
        :func:`power_pptx._color.coerce_color` (``RGBColor``,
        ``"#RRGGBB"`` hex, or ``(r, g, b)`` 3-tuple).  Pass ``None`` to
        leave a property alone — explicit defaults are required to be
        keyword-only so ``set_paragraph_defaults(font_name="Inter")``
        is unambiguous.

        See ``IMPROVEMENT_PLAN.md`` item 8.
        """
        rgb = None
        if color is not None:
            from power_pptx._color import coerce_color

            rgb = coerce_color(color)

        def _apply_to_font(font: Font) -> None:
            if font_name is not None and font.name is None:
                font.name = font_name
            if size is not None and font.size is None:
                font.size = size
            if bold is not None and font.bold is None:
                font.bold = bold
            if italic is not None and font.italic is None:
                font.italic = italic
            if rgb is not None:
                # Don't read ``font.color.rgb`` first — that raises
                # ``AttributeError`` for runs with an explicit non-RGB
                # color (e.g. ``theme_color`` / scheme colour), which
                # would crash the helper on mixed-format frames.  Use
                # ``font.color.type`` as the "is anything set?" probe
                # instead; ``None`` means no explicit colour, scheme /
                # RGB / preset / system means leave it alone.
                try:
                    color_type = font.color.type
                except AttributeError:
                    color_type = None
                if color_type is None:
                    font.color.rgb = rgb

        for paragraph in self.paragraphs:
            # The paragraph-level Font controls run defaults via
            # `a:defRPr`; setting it here gives a baseline that empty
            # paragraphs inherit, while the per-run pass below
            # overwrites any already-set run-level properties.
            _apply_to_font(paragraph.font)
            for run in paragraph.runs:
                _apply_to_font(run.font)

    @property
    def column_count(self) -> int:
        """Number of text columns laid out within this text frame.

        Read/write. Corresponds to the ``numCol`` attribute on ``<a:bodyPr>``. A value of
        ``1`` (the default) means a single column. Valid values are integers in the range
        1..16. Reading returns ``1`` when no explicit value is set (the inherited default);
        assigning ``1`` removes any explicit setting.
        """
        numCol = self._bodyPr.numCol
        return 1 if numCol is None else numCol

    @column_count.setter
    def column_count(self, value: int):
        self._bodyPr.numCol = None if value == 1 else value

    @property
    def column_spacing(self) -> Length | None:
        """Spacing between adjacent text columns as a |Length|.

        Read/write. Corresponds to the ``spcCol`` attribute on ``<a:bodyPr>``, the gutter
        between columns when :attr:`column_count` is greater than 1. |None| indicates no
        explicit value is set; assigning |None| removes any explicit value.
        """
        return self._bodyPr.spcCol

    @column_spacing.setter
    def column_spacing(self, value: Length | None):
        self._bodyPr.spcCol = value

    @property
    def vertical_anchor(self) -> MSO_VERTICAL_ANCHOR | None:
        """Represents the vertical alignment of text in this text frame.

        |None| indicates the effective value should be inherited from this object's style hierarchy.
        """
        return self._txBody.bodyPr.anchor

    @vertical_anchor.setter
    def vertical_anchor(self, value: MSO_VERTICAL_ANCHOR | None):
        bodyPr = self._txBody.bodyPr
        bodyPr.anchor = value

    @property
    def word_wrap(self) -> bool | None:
        """`True` when lines of text in this shape are wrapped to fit within the shape's width.

        Read-write. Valid values are True, False, or None. True and False turn word wrap on and
        off, respectively. Assigning None to word wrap causes any word wrap setting to be removed
        from the text frame, causing it to inherit this setting from its style hierarchy.
        """
        return {
            ST_TextWrappingType.SQUARE: True,
            ST_TextWrappingType.NONE: False,
            None: None,
        }[self._txBody.bodyPr.wrap]

    @word_wrap.setter
    def word_wrap(self, value: bool | None):
        if value not in (True, False, None):
            raise ValueError(  # pragma: no cover
                "assigned value must be True, False, or None, got %s" % value
            )
        self._txBody.bodyPr.wrap = {
            True: ST_TextWrappingType.SQUARE,
            False: ST_TextWrappingType.NONE,
            None: None,
        }[value]

    def _apply_fit(self, font_family: str, font_size: int, is_bold: bool, is_italic: bool):
        """Arrange text in this text frame to fit inside its extents.

        This is accomplished by setting auto size off, wrap on, and setting the font of
        all its text to `font_family`, `font_size`, `is_bold`, and `is_italic`.
        """
        self.auto_size = MSO_AUTO_SIZE.NONE
        self.word_wrap = True
        self._set_font(font_family, font_size, is_bold, is_italic)

    def _best_fit_font_size(
        self, family: str, max_size: int, bold: bool, italic: bool, font_file: str | None
    ) -> int:
        """Return font-size in points that best fits text in this text-frame.

        The best-fit font size is the largest integer point size not greater than `max_size` that
        allows all the text in this text frame to fit inside its extents when rendered using the
        font described by `family`, `bold`, and `italic`. If `font_file` is specified, it is used
        to calculate the fit, whether or not it matches `family`, `bold`, and `italic`. When no
        font file is provided and no matching system font can be located, Pillow's bundled
        default font is used so `fit_text` produces a usable estimate rather than raising.

        Raises :class:`ValueError` when even 1pt overflows the text frame — typically the
        frame is too small to render the wrapped text at any usable size.  Pre-IMPROVEMENTS
        item 7 this silently returned ``None`` and crashed the downstream ``_apply_fit``
        setter with a confusing ``TypeError`` from inside ``Pt(None)``.
        """
        if font_file is None:
            try:
                font_file = FontFiles.find(family, bold, italic)
            except (KeyError, OSError):
                font_file = None
        size = TextFitter.best_fit_font_size(self.text, self._extents, max_size, font_file)
        if size is None:
            raise ValueError(
                "fit_text: text does not fit at any size from 1pt to "
                f"{max_size}pt in this text frame; resize the shape, "
                "shorten the text, or split it across multiple frames."
            )
        return size

    @property
    def _bodyPr(self):
        return self._txBody.bodyPr

    @property
    def _extents(self) -> tuple[Length, Length]:
        """(cx, cy) 2-tuple representing the effective rendering area of this text-frame.

        Margins are taken into account.
        """
        parent = cast("ProvidesExtents", self._parent)
        return (
            Length(parent.width - self.margin_left - self.margin_right),
            Length(parent.height - self.margin_top - self.margin_bottom),
        )

    def _set_font(self, family: str, size: int, bold: bool, italic: bool):
        """Set the font properties of all the text in this text frame."""

        def iter_rPrs(txBody: CT_TextBody) -> Iterator[CT_TextCharacterProperties]:
            for p in txBody.p_lst:
                for elm in p.content_children:
                    yield elm.get_or_add_rPr()
                # generate a:endParaRPr for each <a:p> element
                yield p.get_or_add_endParaRPr()

        def set_rPr_font(
            rPr: CT_TextCharacterProperties, name: str, size: int, bold: bool, italic: bool
        ):
            f = Font(rPr)
            f.name, f.size, f.bold, f.italic = family, Pt(size), bold, italic

        txBody = self._element
        for rPr in iter_rPrs(txBody):
            set_rPr_font(rPr, family, size, bold, italic)


class Font(object):
    """Character properties object, providing font size, font name, bold, italic, etc.

    Corresponds to `a:rPr` child element of a run. Also appears as `a:defRPr` and
    `a:endParaRPr` in paragraph and `a:defRPr` in list style elements.
    """

    def __init__(self, rPr: CT_TextCharacterProperties):
        super(Font, self).__init__()
        self._element = self._rPr = rPr

    @property
    def bold(self) -> bool | None:
        """Get or set boolean bold value of |Font|, e.g. `paragraph.font.bold = True`.

        If set to |None|, the bold setting is cleared and is inherited from an enclosing shape's
        setting, or a setting in a style or master. Returns None if no bold attribute is present,
        meaning the effective bold value is inherited from a master or the theme.
        """
        return self._rPr.b

    @bold.setter
    def bold(self, value: bool | None):
        self._rPr.b = value

    @lazyproperty
    def color(self) -> ColorFormat:
        """The |ColorFormat| instance that provides access to the color settings for this font.

        Reads are non-mutating: when no explicit solid fill is set, accessing color
        properties returns the "no explicit color" sentinel (preserving theme
        inheritance) instead of inserting an empty `<a:solidFill>`. The fill is only
        switched to solid when `rgb` or `theme_color` is assigned.
        """
        return _LazyColorFormat(peek_fill=lambda: self.fill, ensure_fill=lambda: self.fill)

    @lazyproperty
    def fill(self) -> FillFormat:
        """|FillFormat| instance for this font.

        Provides access to fill properties such as fill color.
        """
        return FillFormat.from_fill_parent(self._rPr)

    @property
    def italic(self) -> bool | None:
        """Get or set boolean italic value of |Font| instance.

        Has the same behaviors as bold with respect to None values.
        """
        return self._rPr.i

    @italic.setter
    def italic(self, value: bool | None):
        self._rPr.i = value

    @lazyproperty
    def outline(self) -> LineFormat:
        """|LineFormat| for the text-outline stroke of this font.

        Wraps the `<a:ln>` child of the run's `<a:rPr>`, letting you give glyphs a
        coloured outline::

            run.font.outline.color.rgb = "FF0000"
            run.font.outline.width = Pt(1)

        Reads are non-mutating — no `<a:ln>` element is written until an outline
        property is assigned, preserving inheritance from the style hierarchy.
        """
        return LineFormat(self._rPr)

    @lazyproperty
    def shadow(self) -> ShadowFormat:
        """|ShadowFormat| for the outer-shadow effect on this font's glyphs.

        Wraps the `<a:effectLst>` child of the run's `<a:rPr>`::

            run.font.shadow.color.rgb = "808080"
            run.font.shadow.blur_radius = Pt(3)

        Reads are non-mutating; the effect XML is created lazily on first write.
        """
        # -- ShadowFormat needs an element exposing `effectLst` /
        # -- `get_or_add_effectLst`, which CT_TextCharacterProperties now
        # -- provides; the annotated `CT_ShapeProperties` is structural here. --
        return ShadowFormat(self._rPr)  # pyright: ignore[reportArgumentType]

    @lazyproperty
    def glow(self) -> GlowFormat:
        """|GlowFormat| for the glow effect on this font's glyphs.

        Wraps the `<a:effectLst>` child of the run's `<a:rPr>`::

            run.font.glow.color.rgb = "00B0F0"
            run.font.glow.radius = Pt(6)

        Reads are non-mutating; the effect XML is created lazily on first write.
        """
        # -- GlowFormat needs an element exposing `effectLst` /
        # -- `get_or_add_effectLst` (structural; see `shadow` above). --
        return GlowFormat(self._rPr)  # pyright: ignore[reportArgumentType]

    @property
    def caps(self) -> str | None:
        """Capitalization effect: ``"none"``, ``"small"``, ``"all"``, or |None|.

        |None| means the setting is inherited (no ``cap`` attribute is written).
        Most callers want the :attr:`all_caps` / :attr:`small_caps` booleans;
        this is the raw accessor.
        """
        return self._rPr.cap

    @caps.setter
    def caps(self, value: str | None):
        self._rPr.cap = value

    @property
    def all_caps(self) -> bool | None:
        """Whether the text renders in all capitals (``<a:rPr cap="all">``).

        Returns |None| when no capitalization is set (inherited). Setting
        ``False`` writes ``cap="none"`` (an explicit override); setting |None|
        clears the attribute. ``all_caps`` and :attr:`small_caps` share the one
        ``cap`` attribute, so they are mutually exclusive.
        """
        cap = self._rPr.cap
        return None if cap is None else cap == "all"

    @all_caps.setter
    def all_caps(self, value: bool | None):
        self._rPr.cap = None if value is None else ("all" if value else "none")

    @property
    def small_caps(self) -> bool | None:
        """Whether the text renders in small capitals (``<a:rPr cap="small">``).

        Same inheritance / mutual-exclusion semantics as :attr:`all_caps`.
        """
        cap = self._rPr.cap
        return None if cap is None else cap == "small"

    @small_caps.setter
    def small_caps(self, value: bool | None):
        self._rPr.cap = None if value is None else ("small" if value else "none")

    @property
    def letter_spacing(self) -> Length | None:
        """Inter-character spacing (tracking) as a |Length|, e.g. ``Pt(1.5)``.

        Positive values spread the text out, negative values tighten it.
        Returns |None| when inherited. Assign a |Length| (``Pt(...)``,
        ``Centipoints(...)``) or |None| to clear.
        """
        return self._rPr.spc

    @letter_spacing.setter
    def letter_spacing(self, value: Length | None):
        self._rPr.spc = value

    @property
    def strikethrough(self) -> bool | None:
        """Whether a strikethrough line is drawn through the text.

        Returns |None| when inherited, |True| for either single or double
        strike, |False| for an explicit no-strike. Setting |True| writes a
        single strike (``strike="sngStrike"``); use :attr:`caps`-style raw
        access via the XML for the double variant.
        """
        strike = self._rPr.strike
        return None if strike is None else strike != "noStrike"

    @strikethrough.setter
    def strikethrough(self, value: bool | None):
        self._rPr.strike = None if value is None else ("sngStrike" if value else "noStrike")

    @property
    def superscript(self) -> bool | None:
        """Whether the text is raised as superscript (``<a:rPr baseline="...">`` > 0).

        Returns |None| when no baseline shift is set. Setting |True| raises the
        run by 30%; |False| / |None| clears the shift. :attr:`superscript` and
        :attr:`subscript` share the one ``baseline`` attribute and so are
        mutually exclusive.
        """
        baseline = self._rPr.baseline
        return None if baseline is None else baseline > 0

    @superscript.setter
    def superscript(self, value: bool | None):
        self._rPr.baseline = 0.30 if value else None

    @property
    def subscript(self) -> bool | None:
        """Whether the text is lowered as subscript (``<a:rPr baseline="...">`` < 0).

        Same semantics as :attr:`superscript`; setting |True| lowers the run by
        25%.
        """
        baseline = self._rPr.baseline
        return None if baseline is None else baseline < 0

    @subscript.setter
    def subscript(self, value: bool | None):
        self._rPr.baseline = -0.25 if value else None

    @property
    def language_id(self) -> MSO_LANGUAGE_ID | None:
        """Get or set the language id of this |Font| instance.

        The language id is a member of the :ref:`MsoLanguageId` enumeration. Assigning |None|
        removes any language setting, the same behavior as assigning `MSO_LANGUAGE_ID.NONE`.
        """
        lang = self._rPr.lang
        if lang is None:
            return MSO_LANGUAGE_ID.NONE
        return self._rPr.lang

    @language_id.setter
    def language_id(self, value: MSO_LANGUAGE_ID | None):
        if value == MSO_LANGUAGE_ID.NONE:
            value = None
        self._rPr.lang = value

    @property
    def name(self) -> str | None:
        """Get or set the typeface name for this |Font| instance.

        Causes the text it controls to appear in the named font, if a matching font is found.
        Returns |None| if the typeface is currently inherited from the theme. Setting it to |None|
        removes any override of the theme typeface.
        """
        latin = self._rPr.latin
        if latin is None:
            return None
        return latin.typeface

    @name.setter
    def name(self, value: str | None):
        if value is None:
            self._rPr._remove_latin()  # pyright: ignore[reportPrivateUsage]
        else:
            latin = self._rPr.get_or_add_latin()
            latin.typeface = value

    @property
    def size(self) -> Length | None:
        """Indicates the font height in English Metric Units (EMU).

        Read/write. |None| indicates the font size should be inherited from its style hierarchy,
        such as a placeholder or document defaults (usually 18pt). |Length| is a subclass of |int|
        having properties for convenient conversion into points or other length units. Likewise,
        the :class:`power_pptx.util.Pt` class allows convenient specification of point values::

            >>> font.size = Pt(24)
            >>> font.size
            304800
            >>> font.size.pt
            24.0
        """
        sz = self._rPr.sz
        if sz is None:
            return None
        return Centipoints(sz)

    @size.setter
    def size(self, emu: Length | None):
        if emu is None:
            self._rPr.sz = None
        else:
            sz = Emu(emu).centipoints
            self._rPr.sz = sz

    @property
    def underline(self) -> bool | MSO_TEXT_UNDERLINE_TYPE | None:
        """Indicaties the underline setting for this font.

        Value is |True|, |False|, |None|, or a member of the :ref:`MsoTextUnderlineType`
        enumeration. |None| is the default and indicates the underline setting should be inherited
        from the style hierarchy, such as from a placeholder. |True| indicates single underline.
        |False| indicates no underline. Other settings such as double and wavy underlining are
        indicated with members of the :ref:`MsoTextUnderlineType` enumeration.
        """
        u = self._rPr.u
        if u is MSO_UNDERLINE.NONE:
            return False
        if u is MSO_UNDERLINE.SINGLE_LINE:
            return True
        return u

    @underline.setter
    def underline(self, value: bool | MSO_TEXT_UNDERLINE_TYPE | None):
        if value is True:
            value = MSO_UNDERLINE.SINGLE_LINE
        elif value is False:
            value = MSO_UNDERLINE.NONE
        self._element.u = value


class _Hyperlink(Subshape):
    """Text run hyperlink object.

    Corresponds to `a:hlinkClick` child element of the run's properties element (`a:rPr`).
    """

    def __init__(self, rPr: CT_TextCharacterProperties, parent: ProvidesPart):
        super(_Hyperlink, self).__init__(parent)
        self._rPr = rPr

    @property
    def address(self) -> str | None:
        """The URL of the hyperlink.

        Read/write. URL can be on http, https, mailto, or file scheme; others may work.
        """
        if self._hlinkClick is None:
            return None
        return self.part.target_ref(self._hlinkClick.rId)

    @address.setter
    def address(self, url: str | None):
        # implements all three of add, change, and remove hyperlink
        if self._hlinkClick is not None:
            self._remove_hlinkClick()
        if url:
            self._add_hlinkClick(url)

    @property
    def target_slide(self) -> Slide | None:
        """Slide in this presentation that this hyperlink jumps to.

        Read/write. Returns |None| when no hyperlink is present, or when the
        hyperlink targets an external URL rather than an internal slide. Assigning a
        |Slide| writes a relationship-based slide-jump action
        (``ppaction://hlinksldjump``) instead of a URI; assigning |None| removes the
        hyperlink.
        """
        hlink = self._hlinkClick
        if hlink is None:
            return None
        if hlink.action != "ppaction://hlinksldjump":
            return None
        rId = hlink.rId
        if not rId:
            return None
        slide_part = cast("SlidePart", self.part.related_part(rId))
        return slide_part.slide

    @target_slide.setter
    def target_slide(self, slide: Slide | None):
        if self._hlinkClick is not None:
            self._remove_hlinkClick()
        if slide is None:
            return
        rId = self.part.relate_to(slide.part, RT.SLIDE)
        hlink = self._rPr.get_or_add_hlinkClick()
        hlink.action = "ppaction://hlinksldjump"
        hlink.rId = rId

    def _add_hlinkClick(self, url: str):
        rId = self.part.relate_to(url, RT.HYPERLINK, is_external=True)
        self._rPr.add_hlinkClick(rId)

    @property
    def _hlinkClick(self) -> CT_Hyperlink | None:
        return self._rPr.hlinkClick

    def _remove_hlinkClick(self):
        assert self._hlinkClick is not None
        rId = self._hlinkClick.rId
        if rId:
            self.part.drop_rel(rId)
        self._rPr._remove_hlinkClick()  # pyright: ignore[reportPrivateUsage]


class _Paragraph(Subshape):
    """Paragraph object. Not intended to be constructed directly."""

    def __init__(self, p: CT_TextParagraph, parent: ProvidesPart):
        super(_Paragraph, self).__init__(parent)
        self._element = self._p = p

    def add_line_break(self):
        """Add line break at end of this paragraph."""
        self._p.add_br()

    def add_run(self) -> _Run:
        """Return a new run appended to the runs in this paragraph."""
        r = self._p.add_r()
        return _Run(r, self)

    @property
    def alignment(self) -> PP_PARAGRAPH_ALIGNMENT | None:
        """Horizontal alignment of this paragraph.

        The value |None| indicates the paragraph should 'inherit' its effective value from its
        style hierarchy. Assigning |None| removes any explicit setting, causing its inherited
        value to be used.
        """
        return self._pPr.algn

    @alignment.setter
    def alignment(self, value: PP_PARAGRAPH_ALIGNMENT | None):
        self._pPr.algn = value

    def clear(self):
        """Remove all content from this paragraph.

        Paragraph properties are preserved. Content includes runs, line breaks, and fields.
        """
        for elm in self._element.content_children:
            self._element.remove(elm)
        return self

    @property
    def font(self) -> Font:
        """|Font| object containing default character properties for the runs in this paragraph.

        These character properties override default properties inherited from parent objects such
        as the text frame the paragraph is contained in and they may be overridden by character
        properties set at the run level.
        """
        return Font(self._defRPr)

    @property
    def level(self) -> int:
        """Indentation level of this paragraph.

        Read-write. Integer in range 0..8 inclusive. 0 represents a top-level paragraph and is the
        default value. Indentation level is most commonly encountered in a bulleted list, as is
        found on a word bullet slide.
        """
        return self._pPr.lvl

    @level.setter
    def level(self, level: int):
        self._pPr.lvl = level

    @property
    def rtl(self) -> bool | None:
        """Right-to-left paragraph direction, e.g. for Hebrew, Arabic, or Farsi text.

        Read/write tri-state, like :attr:`Font.bold`. Corresponds to the ``rtl`` attribute on
        ``<a:pPr>``. |True| lays the paragraph out right-to-left, |False| forces
        left-to-right, and |None| (the default) removes any explicit setting so the effective
        value is inherited from the style hierarchy.
        """
        pPr = self._p.pPr
        if pPr is None:
            return None
        return pPr.rtl

    @rtl.setter
    def rtl(self, value: bool | None):
        self._pPr.rtl = value

    @property
    def start_at(self) -> int | None:
        """Starting number of an auto-numbered (ordered) list paragraph.

        Read/write. Corresponds to the ``startAt`` attribute on ``<a:buAutoNum>``. Returns
        |None| when this paragraph is not an auto-number list, or when the numbering starts at
        the default of ``1`` (no explicit ``startAt``).

        Assigning an integer turns this paragraph into an auto-numbered list if it isn't one
        already, defaulting the numbering scheme to ``"arabicPeriod"`` (e.g. ``1.``, ``2.``).
        Use :meth:`set_numbered` to choose a different scheme. Assigning |None| removes the
        explicit ``startAt`` (numbering resumes from ``1``) but leaves the list auto-numbered.
        """
        buAutoNum = self._p.pPr.buAutoNum if self._p.pPr is not None else None
        if buAutoNum is None:
            return None
        return buAutoNum.startAt

    @start_at.setter
    def start_at(self, value: int | None):
        existing = self._p.pPr.buAutoNum if self._p.pPr is not None else None
        if value is None:
            if existing is not None:
                existing.startAt = None
            return
        if existing is not None:
            # -- already a numbered list: just update startAt, preserving the scheme --
            existing.startAt = value
        else:
            self.set_numbered(start_at=value)

    def set_numbered(self, scheme: str = "arabicPeriod", start_at: int | None = None):
        """Make this paragraph an auto-numbered list item.

        ``scheme`` is an ``ST_TextAutonumberScheme`` token such as ``"arabicPeriod"`` (the
        default, ``1.`` ``2.`` ``3.``), ``"romanLcPeriod"`` (``i.`` ``ii.``), or
        ``"alphaUcParenR"`` (``A)`` ``B)``).  ``start_at`` optionally sets the first number
        (1..32767); when |None| the list starts at ``1``.  Replaces any existing bullet on the
        paragraph (the bullet element group is an XSD choice).
        """
        buAutoNum = self._pPr.get_or_add_buAutoNum_only()
        buAutoNum.type = scheme
        buAutoNum.startAt = start_at

    @lazyproperty
    def tab_stops(self) -> TabStops:
        """|TabStops| collection of the explicit tab stops for this paragraph.

        Tab stops are stored in the ``<a:tabLst>`` child of ``<a:pPr>``.  The collection is
        iterable, supports ``len()``, and exposes :meth:`TabStops.add_tab_stop` to append a
        stop at a given position and alignment.
        """
        return TabStops(self._pPr)

    @property
    def line_spacing(self) -> int | float | Length | None:
        """The space between baselines in successive lines of this paragraph.

        A value of |None| indicates no explicit value is assigned and its effective value is
        inherited from the paragraph's style hierarchy. A numeric value, e.g. `2` or `1.5`,
        indicates spacing is applied in multiples of line heights. A |Length| value such as
        `Pt(12)` indicates spacing is a fixed height. The |Pt| value class is a convenient way to
        apply line spacing in units of points.
        """
        pPr = self._p.pPr
        if pPr is None:
            return None
        return pPr.line_spacing

    @line_spacing.setter
    def line_spacing(self, value: int | float | Length | None):
        pPr = self._p.get_or_add_pPr()
        pPr.line_spacing = value

    @property
    def runs(self) -> tuple[_Run, ...]:
        """Sequence of runs in this paragraph."""
        return tuple(_Run(r, self) for r in self._element.r_lst)

    @property
    def space_after(self) -> Length | None:
        """The spacing to appear between this paragraph and the subsequent paragraph.

        A value of |None| indicates no explicit value is assigned and its effective value is
        inherited from the paragraph's style hierarchy. |Length| objects provide convenience
        properties, such as `.pt` and `.inches`, that allow easy conversion to various length
        units.
        """
        pPr = self._p.pPr
        if pPr is None:
            return None
        return pPr.space_after

    @space_after.setter
    def space_after(self, value: Length | None):
        pPr = self._p.get_or_add_pPr()
        pPr.space_after = value

    @property
    def space_before(self) -> Length | None:
        """The spacing to appear between this paragraph and the prior paragraph.

        A value of |None| indicates no explicit value is assigned and its effective value is
        inherited from the paragraph's style hierarchy. |Length| objects provide convenience
        properties, such as `.pt` and `.cm`, that allow easy conversion to various length units.
        """
        pPr = self._p.pPr
        if pPr is None:
            return None
        return pPr.space_before

    @space_before.setter
    def space_before(self, value: Length | None):
        pPr = self._p.get_or_add_pPr()
        pPr.space_before = value

    @property
    def text(self) -> str:
        """Text of paragraph as a single string.

        Read/write. This value is formed by concatenating the text in each run and field making up
        the paragraph, adding a vertical-tab character (`"\\v"`) for each line-break element
        (`<a:br>`, soft carriage-return) encountered.

        While the encoding of line-breaks as a vertical tab might be surprising at first, doing so
        is consistent with PowerPoint's clipboard copy behavior and allows a line-break to be
        distinguished from a paragraph boundary within the str return value.

        Assignment causes all content in the paragraph to be replaced. Each vertical-tab character
        (`"\\v"`) in the assigned str is translated to a line-break, as is each line-feed
        character (`"\\n"`). Contrast behavior of line-feed character in `TextFrame.text` setter.
        If line-feed characters are intended to produce new paragraphs, use `TextFrame.text`
        instead. Any other control characters in the assigned string are escaped as a hex
        representation like "_x001B_" (for ESC (ASCII 27) in this example).
        """
        return "".join(elm.text for elm in self._element.content_children)

    @text.setter
    def text(self, text: str):
        self.clear()
        self._element.append_text(text)

    @property
    def _defRPr(self) -> CT_TextCharacterProperties:
        """The element that defines the default run properties for runs in this paragraph.

        Causes the element to be added if not present.
        """
        return self._pPr.get_or_add_defRPr()

    @property
    def _pPr(self) -> CT_TextParagraphProperties:
        """Contains the properties for this paragraph.

        Causes the element to be added if not present.
        """
        return self._p.get_or_add_pPr()


# -- mapping between the friendly tab-stop alignment names accepted by the API
# -- and the `ST_TextTabAlignType` tokens emitted to the XML `algn` attribute. --
_TAB_ALIGNMENTS = {
    "left": "l",
    "center": "ctr",
    "right": "r",
    "decimal": "dec",
}
_TAB_ALIGNMENTS_INV = {v: k for k, v in _TAB_ALIGNMENTS.items()}


class TabStops(object):
    """A sequence of |TabStop| objects providing access to a paragraph's tab stops.

    Wraps the ``<a:tabLst>`` element of an ``<a:pPr>``. The collection is created on demand and
    is iterable and sized (``len()``); indexing returns a |TabStop|.
    """

    def __init__(self, pPr: CT_TextParagraphProperties):
        super(TabStops, self).__init__()
        self._pPr = pPr

    def __getitem__(self, idx: int) -> TabStop:
        tabLst = self._pPr.tabLst
        if tabLst is None:
            raise IndexError("TabStops object has no tab stops")
        return TabStop(tabLst.tab_lst[idx])

    def __iter__(self) -> Iterator[TabStop]:
        tabLst = self._pPr.tabLst
        if tabLst is None:
            return iter(())
        return (TabStop(tab) for tab in tabLst.tab_lst)

    def __len__(self) -> int:
        tabLst = self._pPr.tabLst
        if tabLst is None:
            return 0
        return len(tabLst.tab_lst)

    def add_tab_stop(self, position: Length, alignment: str = "left") -> TabStop:
        """Append and return a new |TabStop| at horizontal `position`.

        `position` is a |Length| measured from the left edge of the text frame. `alignment` is
        one of ``"left"`` (default), ``"center"``, ``"right"``, or ``"decimal"``, controlling
        how text aligns to the tab stop.
        """
        if alignment not in _TAB_ALIGNMENTS:
            raise ValueError(
                "alignment must be one of %s, got %r"
                % (", ".join(repr(k) for k in _TAB_ALIGNMENTS), alignment)
            )
        tabLst = self._pPr.get_or_add_tabLst()
        tab = tabLst.add_tab(position, _TAB_ALIGNMENTS[alignment])
        return TabStop(tab)


class TabStop(object):
    """An individual tab stop, an `<a:tab>` element within a paragraph's `<a:tabLst>`."""

    def __init__(self, tab: CT_TextTabStop):
        super(TabStop, self).__init__()
        self._tab = tab

    @property
    def position(self) -> Length | None:
        """The horizontal offset of this tab stop from the text frame's left edge, a |Length|."""
        return self._tab.pos

    @position.setter
    def position(self, value: Length):
        self._tab.pos = value

    @property
    def alignment(self) -> str:
        """Alignment of text at this tab stop.

        One of ``"left"``, ``"center"``, ``"right"``, or ``"decimal"``. Defaults to ``"left"``
        when the underlying ``algn`` attribute is absent.
        """
        algn = self._tab.algn
        if algn is None:
            return "left"
        return _TAB_ALIGNMENTS_INV[algn]

    @alignment.setter
    def alignment(self, value: str):
        if value not in _TAB_ALIGNMENTS:
            raise ValueError(
                "alignment must be one of %s, got %r"
                % (", ".join(repr(k) for k in _TAB_ALIGNMENTS), value)
            )
        self._tab.algn = _TAB_ALIGNMENTS[value]


class _Run(Subshape):
    """Text run object. Corresponds to `a:r` child element in a paragraph."""

    def __init__(self, r: CT_RegularTextRun, parent: ProvidesPart):
        super(_Run, self).__init__(parent)
        self._r = r

    @property
    def font(self):
        """|Font| instance containing run-level character properties for the text in this run.

        Character properties can be and perhaps most often are inherited from parent objects such
        as the paragraph and slide layout the run is contained in. Only those specifically
        overridden at the run level are contained in the font object.
        """
        rPr = self._r.get_or_add_rPr()
        return Font(rPr)

    @lazyproperty
    def hyperlink(self) -> _Hyperlink:
        """Proxy for any `a:hlinkClick` element under the run properties element.

        Created on demand, the hyperlink object is available whether an `a:hlinkClick` element is
        present or not, and creates or deletes that element as appropriate in response to actions
        on its methods and attributes.
        """
        rPr = self._r.get_or_add_rPr()
        return _Hyperlink(rPr, self)

    @property
    def text(self):
        """Read/write. A unicode string containing the text in this run.

        Assignment replaces all text in the run. The assigned value can be a 7-bit ASCII
        string, a UTF-8 encoded 8-bit string, or unicode. String values are converted to
        unicode assuming UTF-8 encoding.

        Any other control characters in the assigned string other than tab or newline
        are escaped as a hex representation. For example, ESC (ASCII 27) is escaped as
        "_x001B_". Contrast the behavior of `TextFrame.text` and `_Paragraph.text` with
        respect to line-feed and vertical-tab characters.
        """
        return self._r.text

    @text.setter
    def text(self, text: str):
        self._r.text = text
