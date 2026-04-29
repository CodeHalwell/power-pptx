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


def _xpath(element: LxmlElement, expr: str) -> list[LxmlElement]:
    """Evaluate *expr* on *element* using the global namespace map.

    Uses ``lxml.etree._Element.xpath`` directly so that the call always
    receives the full ``namespaces`` keyword argument, even when *element* is
    a ``BaseOxmlElement`` whose ``xpath`` method has an overridden signature.
    """
    return LxmlElement.xpath(element, expr, namespaces=_GLOBAL_NSMAP)  # type: ignore[arg-type]


def _node_pts(data_element: LxmlElement) -> list[LxmlElement]:
    """Return all ``<dgm:pt>`` elements whose ``type`` marks them as content nodes.

    The returned list is in document order, which corresponds to the visual
    display order in most SmartArt layouts.
    """
    return _xpath(data_element, "dgm:ptLst/dgm:pt[@type='node' or @type='asst']")


def _text_runs(pt: LxmlElement) -> list[LxmlElement]:
    """Return all ``<a:t>`` leaf elements inside a ``<dgm:pt>/<dgm:t>`` text body."""
    return _xpath(pt, "dgm:t//a:r/a:t")


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
            runs = _text_runs(pt)
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

        for i, pt in enumerate(nodes):
            if i >= len(values):
                break
            new_text = str(values[i])
            runs = _text_runs(pt)
            if runs:
                # Overwrite first run; clear the rest.
                runs[0].text = new_text
                for extra_run in runs[1:]:
                    extra_run.text = ""
            else:
                # No existing <a:t>; build a minimal <dgm:t>/<a:p>/<a:r>/<a:t> subtree.
                t_body = pt.find(qn("dgm:t"))
                if t_body is None:
                    from lxml import etree

                    t_body = etree.SubElement(pt, qn("dgm:t"))
                    etree.SubElement(t_body, qn("a:bodyPr"))
                    etree.SubElement(t_body, qn("a:lstStyle"))
                from lxml import etree

                p = etree.SubElement(t_body, qn("a:p"))
                r = etree.SubElement(p, qn("a:r"))
                t = etree.SubElement(r, qn("a:t"))
                t.text = new_text

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
