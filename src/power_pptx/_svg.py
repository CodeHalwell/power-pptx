"""SVG support for ``ShapeTree.add_svg_picture``.

Modern PowerPoint requires every embedded SVG to ship alongside a PNG
fallback: the ``<a:blip>`` references the PNG and an
``<asvg:svgBlip>`` extension references the SVG.  This module provides
the helpers that drive that wiring — SVG detection, blob loading,
optional rasterisation via ``cairosvg``, and OOXML element rewriting.

``cairosvg`` is an *optional* dependency: callers can supply their own
PNG fallback (``png_fallback=`` argument on ``add_svg_picture``) and the
import is never attempted, so installs without ``cairosvg`` keep
working.  The import is deferred to first use and routed through a
clear error message when missing.
"""

from __future__ import annotations

import os
import re
from typing import IO, Any, Tuple, Union

from lxml import etree

from power_pptx.opc.constants import CONTENT_TYPE as CT
from power_pptx.oxml.ns import nsuri, qn

PathOrFile = Union[str, "os.PathLike[str]", IO[bytes], bytes]
"""Either a filesystem path, a binary file-like, or a raw blob."""


# {96DAC541-7B7A-43D3-8B79-37D633B846F1} is the well-known URI for the
# Microsoft "SVG Image Extension" element introduced with Office 2016.
_SVG_EXT_URI = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"


class CairoSvgUnavailable(RuntimeError):
    """Raised when SVG rasterisation is needed but ``cairosvg`` is missing."""


def load_image_blob(source: PathOrFile) -> Tuple[bytes, str | None]:
    """Return ``(blob, filename)`` for `source`.

    `source` may be inline SVG markup, a path, a binary file-like, or a
    raw ``bytes`` blob. The filename component is best-effort and is only used as a
    nice-to-have for the partname; ``None`` is returned for in-memory
    sources.

    .. note::
       File-like sources are rewound with ``source.seek(0)`` before
       reading when seeking is supported, so the *entire* contents of
       the stream are loaded regardless of where the cursor was when
       the function was called.  This matches the behavior of
       :meth:`Image.from_file` (used by ``add_picture``) and means
       callers who pass a partially-read stream will get the full blob,
       not just the unread tail.  Pass a :class:`bytes` blob directly
       if you want to feed the function a pre-sliced subset of a
       stream.
    """
    if isinstance(source, (bytes, bytearray)):
        return bytes(source), None
    if isinstance(source, str) and source.lstrip("\ufeff \t\r\n").startswith("<"):
        return source.encode("utf-8"), None
    if isinstance(source, (str, os.PathLike)):
        with open(source, "rb") as f:
            return f.read(), os.path.basename(os.fspath(source))
    # Assume file-like.  Match `Image.from_file`'s rewind-then-read
    # convention so behavior is consistent across the picture APIs.
    if callable(getattr(source, "seek", None)):
        source.seek(0)
    return source.read(), None


def looks_like_svg(blob: bytes) -> bool:
    """True for a well-formed SVG document, rather than HTML containing SVG."""
    try:
        root = etree.fromstring(
            blob,
            parser=etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True),
        )
    except (etree.XMLSyntaxError, ValueError):
        return False
    name = etree.QName(root)
    return name.localname == "svg" and name.namespace in {None, "http://www.w3.org/2000/svg"}


# -- every `url(...)` in a style; whether its argument stays inside the document is decided
# -- once the quotes and whitespace around it are off, not by the pattern --
_CSS_URL = re.compile(r"url\(([^)]*)\)", re.IGNORECASE)
_CSS_IMPORT = re.compile(r"@import\b[^;]*;?", re.IGNORECASE)
# -- what lxml gives as the `tag` of an entity reference and of a processing instruction --
_ENTITY: Any = getattr(etree, "Entity")
_PI: Any = getattr(etree, "ProcessingInstruction")


def _safe_parser() -> etree.XMLParser:
    """A parser that expands no entity, loads no DTD and never touches the network."""
    return etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)


def _is_internal_reference(url: str) -> bool:
    """True for a reference that stays inside the document: a fragment or a ``data:`` URL."""
    url = url.strip()
    return url.startswith("#") or url[:5].lower() == "data:"


def _neutralised_css(css: str) -> str:
    """Return `css` with every reference to another resource taken out."""
    return _CSS_URL.sub(_css_url_or_none, _CSS_IMPORT.sub("", css))


def _css_url_or_none(match: re.Match[str]) -> str:
    """The `url(...)` of `match` as it is when it stays inside the document, else ``none``.

    ``url('#gradient')``, ``url( "#clip" )`` and a quoted ``data:`` URL are as
    internal as their bare forms.
    """
    target = match.group(1).strip().strip("'\"").strip()
    return match.group(0) if _is_internal_reference(target) else "none"


def _neutralise_element(element) -> bool:
    """Take the references to other resources out of `element`; True if it was changed."""
    changed = False
    for name, value in list(element.attrib.items()):
        local = etree.QName(name).localname.lower()
        if local in ("href", "src"):
            if not _is_internal_reference(value):
                del element.attrib[name]
                changed = True
        elif "url(" in value.lower():
            cleaned = _neutralised_css(value)
            if cleaned != value:
                element.attrib[name] = cleaned
                changed = True
    if etree.QName(element).localname.lower() == "style" and element.text:
        cleaned = _neutralised_css(element.text)
        if cleaned != element.text:
            element.text = cleaned
            changed = True
    return changed


def neutralise_external_references(svg_blob: bytes) -> bytes:
    """Return `svg_blob` with everything that makes a viewer read another resource removed.

    An SVG can name images, other SVG documents and stylesheets by URL, and a
    program that draws it may go and read them: LibreOffice, asked to render a
    deck, reads a local file named by ``<image href="file:///...">`` and draws
    it into the output. This takes out every ``href`` / ``src`` that is not a
    fragment (``#id``) or a ``data:`` URL, every such ``url(...)`` and
    ``@import`` in styles, any ``<?xml-stylesheet?>`` and any DTD. What is left
    draws from the document alone.

    A document with none of those comes back as the same bytes. One that is not
    well-formed XML comes back as an empty SVG, since nothing can be said about
    what a lenient reader would make of it.
    """
    try:
        root: Any = etree.fromstring(svg_blob, parser=_safe_parser())
    except (etree.XMLSyntaxError, ValueError):
        return _EMPTY_SVG
    tree = root.getroottree()
    changed = bool(tree.docinfo.doctype) or tree.docinfo.internalDTD is not None
    # -- a stylesheet named ahead of the root element goes the way of the DTD --
    changed = changed or any(node.tag is _PI for node in root.itersiblings(preceding=True))
    for node in list(root.iter()):
        if isinstance(node.tag, str):
            changed = _neutralise_element(node) or changed
        elif node.tag is _ENTITY or node.tag is _PI:
            # -- an entity reference means nothing once the DTD declaring it is gone --
            _remove_keeping_tail(node.getparent(), node)
            changed = True
    if not changed:
        return svg_blob
    # -- serialising the root element, rather than its tree, leaves behind the DTD and
    # -- whatever else came before the root --
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def _remove_keeping_tail(parent, node) -> None:
    """Remove `node` from `parent`, leaving the text that followed it where it was."""
    tail = node.tail or ""
    previous = node.getprevious()
    if previous is not None:
        previous.tail = (previous.tail or "") + tail
    else:
        parent.text = (parent.text or "") + tail
    parent.remove(node)


# What CairoSVG draws in place of a resource it was not allowed to fetch.
_EMPTY_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'


def _fetch_data_url_only(url: str, resource_type: str) -> bytes:
    """Return the content of `url` for CairoSVG when it is a ``data:`` URL.

    An SVG can pull in images and stylesheets by URL. CairoSVG before 2.7
    fetches every one, local files and network addresses alike, so an untrusted
    SVG (from a ``from_spec(..., safe=True)`` spec, say) could read files or make
    requests while it is rasterised. Any other URL gets an empty SVG instead,
    which is what CairoSVG 2.7 and later do by default.
    """
    if not url or url[:5].lower() != "data:":
        return _EMPTY_SVG
    from urllib.request import urlopen

    # -- urllib decodes a data: URL in memory; nothing is opened or requested --
    with urlopen(url) as response:
        return response.read()


#: The most pixels an SVG is rasterised to when the caller names no size. An SVG states
#: its own size, so a few bytes can ask for a canvas of gigabytes; one that asks for more
#: than this is drawn smaller, at the same proportions.
MAX_RASTER_PIXELS = 32_000_000

_CSS_PX_PER_UNIT = {
    "": 1.0,
    "px": 1.0,
    "pt": 96 / 72,
    "pc": 16.0,
    "mm": 96 / 25.4,
    "cm": 96 / 2.54,
    "in": 96.0,
    "em": 16.0,
    "ex": 8.0,
}
_SVG_LENGTH = re.compile(r"^\s*([0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*([a-zA-Z]*)\s*$")


def _svg_length_px(value: str | None) -> float | None:
    """`value`, an SVG length such as ``"30cm"``, in CSS pixels; None if it is not absolute."""
    match = _SVG_LENGTH.match(value or "")
    if match is None or match.group(2).lower() not in _CSS_PX_PER_UNIT:
        return None
    return float(match.group(1)) * _CSS_PX_PER_UNIT[match.group(2).lower()]


def _capped_size(svg_blob: bytes) -> tuple[int, int] | None:
    """The size to rasterise `svg_blob` at when its own would be over `MAX_RASTER_PIXELS`.

    ``None`` when the SVG's stated size is within the limit, or cannot be read
    here, in which case CairoSVG is left to work it out.
    """
    try:
        root = etree.fromstring(svg_blob, parser=_safe_parser())
    except (etree.XMLSyntaxError, ValueError):
        return None
    width, height = _svg_length_px(root.get("width")), _svg_length_px(root.get("height"))
    if width is None or height is None:
        try:
            box = [float(n) for n in (root.get("viewBox") or "").replace(",", " ").split()]
        except ValueError:
            box = []
        if len(box) != 4:
            return None
        width, height = width or box[2], height or box[3]
    if width <= 0 or height <= 0 or width * height <= MAX_RASTER_PIXELS:
        return None
    scale = (MAX_RASTER_PIXELS / (width * height)) ** 0.5
    return max(1, int(width * scale)), max(1, int(height * scale))


def rasterize_svg(svg_blob: bytes, *, output_size: tuple[int, int] | None = None) -> bytes:
    """Rasterise `svg_blob` to PNG bytes using ``cairosvg``.

    `output_size` is an optional ``(width_px, height_px)`` pair.  When
    omitted, ``cairosvg`` uses the SVG's intrinsic size, which is
    usually the right thing for embedding.  Resources the SVG refers to by
    URL are drawn only when the URL is a ``data:`` URL; files and network
    addresses are never read.  Raises :class:`CairoSvgUnavailable` when
    ``cairosvg`` isn't installed.
    """
    try:
        from cairosvg import surface  # type: ignore[import-not-found]
    except ImportError as exc:
        raise CairoSvgUnavailable(
            "rasterising SVG requires the optional `cairosvg` dependency; "
            "install it with `pip install cairosvg`, or pass an explicit "
            "`png_fallback=` argument to add_svg_picture()."
        ) from exc

    kwargs = {}
    if output_size is None:
        output_size = _capped_size(svg_blob)
    if output_size is not None:
        kwargs["output_width"] = int(output_size[0])
        kwargs["output_height"] = int(output_size[1])
    # -- `cairosvg.svg2png()` takes no `url_fetcher`; the converter it wraps passes one
    # -- through to the parser, in every release from 2.5 --
    result = surface.PNGSurface.convert(
        bytestring=svg_blob, url_fetcher=_fetch_data_url_only, **kwargs
    )
    if result is None:
        raise RuntimeError("SVG rasterisation produced no PNG data")
    return result


def add_svg_blip_extension(pic_elm, svg_rId: str) -> None:
    """Inject an ``<asvg:svgBlip>`` extension into the picture's blip.

    `pic_elm` is the ``<p:pic>`` lxml element returned by ``new_pic``.
    `svg_rId` is the relationship id of the SVG image part.
    """
    blip = pic_elm.find(".//" + qn("a:blip"))
    if blip is None:
        raise ValueError("picture has no <a:blip> to attach the SVG extension to")
    extLst = blip.find(qn("a:extLst"))
    if extLst is None:
        extLst = etree.SubElement(blip, qn("a:extLst"))
    ext = etree.SubElement(extLst, qn("a:ext"), uri=_SVG_EXT_URI)
    asvg_uri = nsuri("asvg")
    svgBlip = etree.SubElement(
        ext,
        "{%s}svgBlip" % asvg_uri,
        nsmap={"asvg": asvg_uri},
    )
    svgBlip.set(qn("r:embed"), svg_rId)


def add_svg_image_part(slide_part, svg_blob: bytes, filename: str | None = None):
    """Register `svg_blob` as a new SVG image part on `slide_part`'s package.

    Returns ``(image_part, rId)``: the freshly minted
    :class:`power_pptx.parts.image.ImagePart` plus the relationship id that
    points the slide at it.  Bypasses the Pillow-driven ``Image``
    constructor (which can't read SVG) and constructs the part directly
    with ``content_type='image/svg+xml'``.
    """
    from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT
    from power_pptx.parts.image import ImagePart

    package = slide_part.package
    # Reuse a logo/diagram across slides instead of storing one SVG part
    # for every occurrence. Raster fallbacks already use package deduplication.
    for part in package.iter_parts():
        if (
            isinstance(part, ImagePart)
            and part.content_type == SVG_CONTENT_TYPE
            and part.blob == svg_blob
        ):
            return part, slide_part.relate_to(part, RT.IMAGE)
    partname = package.next_image_partname("svg")
    image_part = ImagePart(
        partname,
        SVG_CONTENT_TYPE,
        package,
        svg_blob,
        filename=filename,
    )
    rId = slide_part.relate_to(image_part, RT.IMAGE)
    return image_part, rId


# Re-exported here so callers in ``shapetree.py`` don't need to know
# about the constants module organisation.
SVG_CONTENT_TYPE = CT.SVG
