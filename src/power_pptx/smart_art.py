"""SmartArt shape access for text substitution.

Exposes :class:`SmartArtCollection` (accessed via ``slide.smart_art``) and
:class:`SmartArtShape`, whose :meth:`~SmartArtShape.set_text` method rewrites
the text nodes inside an existing ``diagrams/data#.xml`` part without touching
layout, style, or colour parts.

Scope: text *substitution* in existing SmartArt only.  Full SmartArt creation
is explicitly out of scope.

Example::

    slide = prs.slides[0]
    org_chart = slide.smart_art[0]
    print(org_chart.texts)          # ['CEO', 'CTO', 'CFO']
    org_chart.set_text(['Alice', 'Bob', 'Carol'])
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Sequence

from lxml import etree
from lxml.etree import _Element as LxmlElement  # pyright: ignore[reportPrivateUsage]

from power_pptx.oxml.ns import _nsmap as _GLOBAL_NSMAP  # pyright: ignore[reportPrivateUsage]
from power_pptx.oxml.ns import qn
from power_pptx.spec import GRAPHIC_DATA_URI_DIAGRAM

if TYPE_CHECKING:
    from power_pptx.oxml.xmlchemy import BaseOxmlElement

    from power_pptx.parts.slide import SlidePart
    from power_pptx.slide import Slide


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# <dgm:pt> types that carry visible text content (all others are structural)
_NODE_TYPES = frozenset({"node", "asst"})

# -- the namespace of the drawing part in which PowerPoint 2010+ caches the
# -- shapes a diagram was last laid out as (`ppt/diagrams/drawing#.xml`)
_DSP_URI = "http://schemas.microsoft.com/office/drawing/2008/diagram"
_NSMAP = dict(_GLOBAL_NSMAP, dsp=_DSP_URI)


def _xpath(element: LxmlElement, expr: str) -> list[LxmlElement]:
    """Evaluate *expr* on *element* using the global namespace map.

    Uses ``lxml.etree._Element.xpath`` directly so that the call always
    receives the full ``namespaces`` keyword argument, even when *element* is
    a ``BaseOxmlElement`` whose ``xpath`` method has an overridden signature.
    """
    return LxmlElement.xpath(element, expr, namespaces=_NSMAP)  # type: ignore[arg-type]


def _node_pts(data_element: LxmlElement) -> list[LxmlElement]:
    """Return all ``<dgm:pt>`` elements whose ``type`` marks them as content nodes.

    ``type`` defaults to ``"node"``, and PowerPoint relies on that: it writes
    the attribute only on the other kinds of point, so a content node is
    usually one with no ``type`` at all.

    The returned list is in document order, which corresponds to the visual
    display order in most SmartArt layouts.
    """
    return _xpath(data_element, "dgm:ptLst/dgm:pt[not(@type) or @type='node' or @type='asst']")


def _text_runs(text_body: LxmlElement) -> list[LxmlElement]:
    """Return all ``<a:t>`` leaf elements of the runs in *text_body*."""
    return _xpath(text_body, ".//a:r/a:t")


def _set_text(text_body: LxmlElement, text: str) -> None:
    """Make *text* the content of *text_body* (a ``dgm:t`` or ``dsp:txBody``).

    The first run takes the text and any further run is emptied, so the run
    and paragraph formatting already there is kept. A body without a run,
    which is what a node still showing its "[Text]" prompt has, gets one in
    its first paragraph.
    """
    runs = _text_runs(text_body)
    if runs:
        runs[0].text = text
        for extra_run in runs[1:]:
            extra_run.text = ""
        return

    p = text_body.find(qn("a:p"))
    if p is None:
        p = etree.SubElement(text_body, qn("a:p"))
    r = etree.Element(qn("a:r"))
    end = p.find(qn("a:endParaRPr"))
    if end is None:
        p.append(r)
    else:
        # -- runs precede the end-of-paragraph properties, whose settings (the
        # -- font size a cached shape was laid out with, say) the new run adopts
        if end.attrib:
            etree.SubElement(r, qn("a:rPr"), dict(end.attrib))
        end.addprevious(r)
    etree.SubElement(r, qn("a:t")).text = text


def _set_node_text(pt: LxmlElement, text: str) -> None:
    """Make *text* the text of the content node *pt*.

    A node without a text body is given one, and a node given text of its
    own is no longer a placeholder.
    """
    t_body = pt.find(qn("dgm:t"))
    if t_body is None:
        t_body = _add_text_body(pt)
    _set_text(t_body, text)
    if text:
        for prSet in pt.findall(qn("dgm:prSet")):
            prSet.attrib.pop("phldr", None)


def _add_text_body(pt: LxmlElement) -> LxmlElement:
    """Give the content node *pt* a minimal, empty ``dgm:t`` and return it.

    It goes ahead of any ``dgm:extLst``, which closes the sequence of a point.
    """
    t_body = etree.Element(qn("dgm:t"))
    etree.SubElement(t_body, qn("a:bodyPr"))
    etree.SubElement(t_body, qn("a:lstStyle"))
    ext_lst = pt.find(qn("dgm:extLst"))
    if ext_lst is None:
        pt.append(t_body)
    else:
        ext_lst.addprevious(t_body)
    return t_body


# ---------------------------------------------------------------------------
# Public classes
# ---------------------------------------------------------------------------


class SmartArtShape:
    """Proxy for one SmartArt graphic on a slide.

    Wraps a ``<p:graphicFrame>`` that encloses a SmartArt diagram and exposes
    the diagram-data part as a mutable text surface.

    Do not construct directly; obtain instances from :attr:`Slide.smart_art`.
    """

    def __init__(self, graphic_frame: BaseOxmlElement, slide_part: SlidePart) -> None:
        self._frame = graphic_frame
        self._slide_part = slide_part

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Internal shape name, e.g. "SmartArt 5"."""
        cNvPr_elms = _xpath(self._frame, ".//p:cNvPr")
        return cNvPr_elms[0].get("name", "") if cNvPr_elms else ""

    @property
    def texts(self) -> list[str]:
        """Ordered list of text strings — one per content node in the diagram data.

        Each string is the concatenation of all ``<a:t>`` run text inside the
        corresponding ``<dgm:pt>`` element.  The order matches the visual
        sequence in most layouts (document order in ``<dgm:ptLst>``).
        """
        data_el = self._data_element
        result: list[str] = []
        for pt in _node_pts(data_el):
            runs = _xpath(pt, "dgm:t//a:r/a:t")
            result.append("".join(r.text or "" for r in runs))
        return result

    def set_text(self, values: Sequence[str], *, strict: bool = True) -> None:
        """Replace the text of each content node with the corresponding entry in *values*.

        Parameters
        ----------
        values:
            New text strings, one per content node.  The order must match
            :attr:`texts`.
        strict:
            When ``True`` (the default), raises :class:`ValueError` if
            ``len(values)`` does not equal the number of content nodes.
            When ``False``, extra values are silently ignored and nodes
            without a corresponding value are left unchanged.

        A diagram saved by PowerPoint 2010 or later also carries a drawing
        part caching the shapes it was last laid out as, which is what gets
        displayed until the diagram is laid out afresh. The text there is
        replaced as well, in the shapes as they stand: PowerPoint re-fits the
        text when the diagram is next edited.

        Raises
        ------
        ValueError
            When ``strict=True`` and ``len(values) != len(self.texts)``.
        """
        data_el = self._data_element
        nodes = _node_pts(data_el)

        if strict and len(values) != len(nodes):
            raise ValueError(
                f"set_text() received {len(values)} value(s) but this SmartArt has "
                f"{len(nodes)} content node(s).  Pass strict=False to suppress this check."
            )

        drawing = self._cached_drawing
        for i, pt in enumerate(nodes):
            if i >= len(values):
                break
            new_text = str(values[i])
            _set_node_text(pt, new_text)
            if drawing is not None:
                for text_body in self._cached_text_bodies(drawing, data_el, pt):
                    _set_text(text_body, new_text)
        if drawing is not None:
            self._save_cached_drawing(drawing)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @property
    def _drawing_part(self):
        """The part caching the laid-out shapes of this diagram, or |None|.

        PowerPoint 2010+ names it in an extension of the data part, by the id
        of the relationship from the slide.
        """
        rel_ids = _xpath(self._data_element, "dgm:extLst/a:ext/dsp:dataModelExt/@relId")
        if not rel_ids:
            return None
        try:
            return self._slide_part.related_part(str(rel_ids[0]))
        except KeyError:
            return None

    @property
    def _cached_drawing(self) -> LxmlElement | None:
        """Root element of the cached drawing of this diagram, or |None| if it has none."""
        part = self._drawing_part
        if part is None:
            return None
        element = getattr(part, "_element", None)
        if element is not None:
            return element
        try:
            return etree.fromstring(part.blob)
        except etree.XMLSyntaxError:
            return None

    def _save_cached_drawing(self, drawing: LxmlElement) -> None:
        """Write *drawing* back to its part, unless the part serializes its own element."""
        part = self._drawing_part
        if part is None or getattr(part, "_element", None) is not None:
            return
        part.blob = etree.tostring(drawing, encoding="UTF-8", standalone=True)

    @staticmethod
    def _cached_text_bodies(
        drawing: LxmlElement, data_el: LxmlElement, pt: LxmlElement
    ) -> list[LxmlElement]:
        """The text bodies in *drawing* that display the text of the content node *pt*.

        A cached shape is tied to a presentation point of the data model, which
        in turn names the content node it presents. The shape whose body holds
        runs is the one showing the text; when the node was empty there is no
        such shape, and its text can only be placed if a single shape of the
        node has a text body at all.
        """
        model_id = pt.get("modelId")
        pres_ids = {
            pres.get("modelId")
            for pres in _xpath(data_el, "dgm:ptLst/dgm:pt[@type='pres']")
            if any(prSet.get("presAssocID") == model_id for prSet in pres.findall(qn("dgm:prSet")))
        }
        bodies = [
            body
            for sp in drawing.iter("{%s}sp" % _DSP_URI)
            if sp.get("modelId") in pres_ids
            for body in sp.findall("{%s}txBody" % _DSP_URI)
        ]
        with_runs = [body for body in bodies if _text_runs(body)]
        if with_runs:
            return with_runs
        return bodies if len(bodies) == 1 else []

    @property
    def _data_rId(self) -> str:
        """rId of the diagram-data relationship from the slide part."""
        # <a:graphicData><dgm:relIds r:dm="rIdN" .../>
        rel_ids = _xpath(self._frame, ".//dgm:relIds")
        if not rel_ids:
            raise ValueError("SmartArt frame has no <dgm:relIds> element.")
        return rel_ids[0].get(qn("r:dm"))  # type: ignore[return-value]

    @property
    def _data_element(self) -> BaseOxmlElement:
        """Root element of the diagram-data part for this SmartArt."""
        rId = self._data_rId
        data_part = self._slide_part.related_part(rId)
        return data_part._element  # pyright: ignore[reportPrivateUsage]


class SmartArtCollection:
    """Sequence of :class:`SmartArtShape` objects on a slide.

    Accessed via :attr:`Slide.smart_art`.  Supports indexing and iteration.
    """

    def __init__(self, slide: Slide) -> None:
        self._slide = slide

    def __len__(self) -> int:
        return len(self._frames)

    def __getitem__(self, idx: int) -> SmartArtShape:
        frames = self._frames
        if idx < 0 or idx >= len(frames):
            raise IndexError(f"SmartArt index {idx} out of range (0–{len(frames) - 1})")
        return SmartArtShape(frames[idx], self._slide.part)

    def __iter__(self) -> Iterator[SmartArtShape]:
        for frame in self._frames:
            yield SmartArtShape(frame, self._slide.part)

    def __repr__(self) -> str:
        return f"SmartArtCollection({len(self)} SmartArt shape(s))"

    @property
    def _frames(self) -> list[BaseOxmlElement]:
        """All ``<p:graphicFrame>`` elements on the slide whose URI is the SmartArt URI."""
        spTree = self._slide._element.spTree  # pyright: ignore[reportPrivateUsage]
        frames: list[BaseOxmlElement] = []
        for gf in spTree.iter(qn("p:graphicFrame")):
            uri_nodes = _xpath(gf, ".//a:graphicData/@uri")
            if uri_nodes and uri_nodes[0] == GRAPHIC_DATA_URI_DIAGRAM:
                frames.append(gf)  # type: ignore[arg-type]
        return frames
