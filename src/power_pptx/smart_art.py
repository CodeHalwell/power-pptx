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

from copy import deepcopy
from typing import TYPE_CHECKING, Iterator, Sequence

from lxml import etree
from lxml.etree import _Element as LxmlElement  # pyright: ignore[reportPrivateUsage]

from power_pptx.opc.constants import CONTENT_TYPE as CT
from power_pptx.opc.oxml import serialize_part_xml
from power_pptx.oxml import parse_xml
from power_pptx.oxml.ns import _nsmap as _GLOBAL_NSMAP  # pyright: ignore[reportPrivateUsage]
from power_pptx.oxml.ns import qn
from power_pptx.spec import GRAPHIC_DATA_URI_DIAGRAM

if TYPE_CHECKING:
    from power_pptx.opc.package import Part
    from power_pptx.oxml.xmlchemy import BaseOxmlElement
    from power_pptx.parts.slide import SlidePart
    from power_pptx.slide import Slide


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# <dgm:pt> types that carry visible text content (all others are structural)
_NODE_TYPES = frozenset({"node", "asst"})

# Namespace of the `dsp:` elements in a diagram's cached drawing (`ppt/diagrams/drawing#.xml`),
# which is not part of the shared namespace map.
_DSP_NS = "http://schemas.microsoft.com/office/drawing/2008/diagram"


def _xpath(element: LxmlElement, expr: str) -> list[LxmlElement]:
    """Evaluate *expr* on *element* using the global namespace map.

    Uses ``lxml.etree._Element.xpath`` directly so that the call always
    receives the full ``namespaces`` keyword argument, even when *element* is
    a ``BaseOxmlElement`` whose ``xpath`` method has an overridden signature.
    """
    return LxmlElement.xpath(element, expr, namespaces=_GLOBAL_NSMAP)  # type: ignore[arg-type]


def _node_pts(data_element: LxmlElement) -> list[LxmlElement]:
    """Return all ``<dgm:pt>`` elements whose ``type`` marks them as content nodes.

    ``type`` is optional on ``<dgm:pt>`` and defaults to ``"node"`` (``ST_PtType``), and
    PowerPoint omits it on ordinary content nodes, so a point without the attribute is a
    content node too.  The doc / pres / parTrans / sibTrans points are structural and
    never match.

    The returned list is in document order, which corresponds to the visual
    display order in most SmartArt layouts.
    """
    return _xpath(data_element, "dgm:ptLst/dgm:pt[not(@type) or @type='node' or @type='asst']")


def _text_runs(pt: LxmlElement) -> list[LxmlElement]:
    """Return all ``<a:t>`` leaf elements inside a ``<dgm:pt>/<dgm:t>`` text body."""
    return _xpath(pt, "dgm:t//a:r/a:t")


def _add_run(p: LxmlElement, text: str) -> None:
    """Append a run holding `text` to paragraph `p`, ahead of its ``a:endParaRPr``.

    The new run inherits the paragraph's end-of-paragraph character properties (language,
    and in a cached drawing the size too) the way PowerPoint carries them over when text is
    typed into an empty paragraph.
    """
    r = p.makeelement(qn("a:r"))
    end_para_rPr = p.find(qn("a:endParaRPr"))
    if end_para_rPr is not None:
        rPr = deepcopy(end_para_rPr)
        rPr.tag = qn("a:rPr")
        r.append(rPr)
        end_para_rPr.addprevious(r)
    else:
        p.append(r)
    etree.SubElement(r, qn("a:t")).text = text


def _write_node_text(pt: LxmlElement, text: str) -> None:
    """Replace the text of the content node `pt` with `text`."""
    runs = _text_runs(pt)
    if runs:
        # Overwrite first run; clear the rest.
        runs[0].text = text
        for extra_run in runs[1:]:
            extra_run.text = ""
    else:
        # No existing <a:t>.  PowerPoint's "[Text]" placeholder nodes hold an empty paragraph
        # (<a:p><a:endParaRPr/></a:p>); write into it rather than starting a second one,
        # which would render the new text on line two.
        t_body = pt.find(qn("dgm:t"))
        if t_body is None:
            t_body = etree.SubElement(pt, qn("dgm:t"))
            etree.SubElement(t_body, qn("a:bodyPr"))
            etree.SubElement(t_body, qn("a:lstStyle"))
        p = t_body.find(qn("a:p"))
        if p is None:
            p = etree.SubElement(t_body, qn("a:p"))
        _add_run(p, text)

    # A node holding real text is no longer a placeholder: PowerPoint drops `phldr` once text
    # is typed in, and a node left flagged would still be treated as the "[Text]" prompt.
    if text:
        for prSet in pt.findall(qn("dgm:prSet")):
            prSet.attrib.pop("phldr", None)


def _node_text(pt: LxmlElement) -> str:
    """The text of the content node `pt`: its runs, concatenated."""
    return "".join(t.text or "" for t in _text_runs(pt))


# -- cached drawing -------------------------------------------------------------------------
#
# PowerPoint stores the laid-out diagram next to the data model, as a `dsp:drawing` part
# (`ppt/diagrams/drawing#.xml`), and names it from the data part's `dsp:dataModelExt/@relId`.
# PowerPoint re-lays a diagram out from the data model, but LibreOffice, Keynote and Google
# Slides draw the cache, so editing only the data model leaves them showing the old text.
#
# A cached `dsp:sp/@modelId` is the id of a *presentation* point, tied to the content node(s)
# whose text it displays by `presOf` connections (`srcId` node -> `destId` presentation point,
# `destOrd` ordering the nodes that share one shape, one paragraph each).  A shape keyed by
# the node's own id is accepted as well.


def _drawing_cache_part(slide_part: SlidePart, data_element: LxmlElement) -> Part | None:
    """The cached-drawing part that `data_element` points at, or |None| when there is none."""
    for ext in data_element.iter(f"{{{_DSP_NS}}}dataModelExt"):
        rId = ext.get("relId")
        if rId is None:
            continue
        try:
            part = slide_part.related_part(rId)
        except (KeyError, ValueError):
            continue
        if part.content_type == CT.DML_DIAGRAM_DRAWING:
            return part
    return None


def _paragraph_text(p: LxmlElement) -> str:
    """The text of paragraph `p`: its runs, concatenated."""
    return "".join(t.text or "" for t in p.findall(f"{qn('a:r')}/{qn('a:t')}"))


def _set_paragraph_text(p: LxmlElement, text: str) -> None:
    """Replace the text of paragraph `p`, keeping the formatting of its first run."""
    ts = p.findall(f"{qn('a:r')}/{qn('a:t')}")
    if not ts:
        _add_run(p, text)
        return
    ts[0].text = text
    for extra_t in ts[1:]:
        extra_t.text = ""


def _refresh_drawing_cache(
    part: Part,
    data_element: LxmlElement,
    nodes: Sequence[LxmlElement],
    old_texts: Sequence[str],
    new_texts: Sequence[str],
) -> None:
    """Carry the text edits of `nodes` (`old_texts` -> `new_texts`) over to the cached drawing.

    A shape is rewritten only when it unambiguously shows the nodes that changed: it must
    have one paragraph per content node that feeds it, and each paragraph must still hold
    that node's previous text.  Anything else (text in a shape shared with structural
    points, edited since the cache was written, split over several paragraphs) is left as it
    is rather than guessed at; PowerPoint regenerates it on open.
    """
    texts = {
        pt.get("modelId"): (old, new)
        for pt, old, new in zip(nodes, old_texts, new_texts)
        if pt.get("modelId") is not None
    }
    changed = {model_id for model_id, (old, new) in texts.items() if old != new}
    if not changed:
        return

    sources: dict[str, list[tuple[int, str]]] = {}
    for cxn in _xpath(data_element, "dgm:cxnLst/dgm:cxn[@type='presOf']"):
        dest, src = cxn.get("destId"), cxn.get("srcId")
        if dest is None or src is None:
            continue
        try:
            dest_ord = int(cxn.get("destOrd", "0"))
        except ValueError:
            dest_ord = 0
        sources.setdefault(dest, []).append((dest_ord, src))

    # -- a cache part is a plain `Part` today, but would be an `XmlPart` once typed --
    element = getattr(part, "_element", None)
    root = element if element is not None else parse_xml(part.blob)

    edited = False
    for sp in root.iter(f"{{{_DSP_NS}}}sp"):
        model_id = sp.get("modelId")
        if model_id is None:
            continue
        feeding = [src for _, src in sorted(sources.get(model_id, [(0, model_id)]))]
        feeding = [src for src in feeding if src in texts]
        if not changed.intersection(feeding):
            continue
        paragraphs = sp.findall(f"{{{_DSP_NS}}}txBody/{qn('a:p')}")
        if len(paragraphs) != len(feeding):
            continue
        if any(_paragraph_text(p) != texts[src][0] for p, src in zip(paragraphs, feeding)):
            continue
        for p, src in zip(paragraphs, feeding):
            old, new = texts[src]
            if new != old:
                _set_paragraph_text(p, new)
                edited = True

    if edited and element is None:
        part.blob = serialize_part_xml(root)


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
        return [_node_text(pt) for pt in _node_pts(self._data_element)]

    def set_text(self, values: Sequence[str], *, strict: bool = True) -> None:
        """Replace the text of each content node with the corresponding entry in *values*.

        PowerPoint re-lays a diagram out from its data model, but other renderers
        (LibreOffice, Keynote, Google Slides) draw the cached ``drawing#.xml`` that
        PowerPoint saves beside it; the cached text is updated too, so they show the new
        strings.  Only the text is refreshed: the cached shapes keep their size and
        position, so a much longer string is not re-fitted outside PowerPoint.

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

        old_texts = [_node_text(pt) for pt in nodes]
        for i, pt in enumerate(nodes):
            if i >= len(values):
                break
            _write_node_text(pt, str(values[i]))

        cache_part = _drawing_cache_part(self._slide_part, data_el)
        if cache_part is not None:
            new_texts = [_node_text(pt) for pt in nodes]
            _refresh_drawing_cache(cache_part, data_el, nodes, old_texts, new_texts)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

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
