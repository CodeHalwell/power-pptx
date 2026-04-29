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
from typing import IO, Tuple, Union

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

    `source` may be a path, a binary file-like, or a raw ``bytes``
    blob.  The filename component is best-effort and is only used as a
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
    if isinstance(source, (str, os.PathLike)):
        with open(source, "rb") as f:
            return f.read(), os.path.basename(os.fspath(source))
    # Assume file-like.  Match `Image.from_file`'s rewind-then-read
    # convention so behavior is consistent across the picture APIs.
    if callable(getattr(source, "seek", None)):
        source.seek(0)
    return source.read(), None


def looks_like_svg(blob: bytes) -> bool:
    """Heuristic: does `blob` smell like an SVG document?"""
    head = blob[:512].lstrip()
    if not head:
        return False
    # Allow leading XML declaration / DOCTYPE; just look for "<svg" up
    # near the start.  Real SVG sniffing would require an XML parse,
    # which is overkill for a one-shot helper.
    lowered = head.lower()
    return b"<svg" in lowered


def rasterize_svg(svg_blob: bytes, *, output_size: tuple[int, int] | None = None) -> bytes:
    """Rasterise `svg_blob` to PNG bytes using ``cairosvg``.

    `output_size` is an optional ``(width_px, height_px)`` pair.  When
    omitted, ``cairosvg`` uses the SVG's intrinsic size, which is
    usually the right thing for embedding.  Raises
    :class:`CairoSvgUnavailable` when ``cairosvg`` isn't installed.
    """
    try:
        import cairosvg  # type: ignore[import-not-found]
    except ImportError as exc:
        raise CairoSvgUnavailable(
            "rasterising SVG requires the optional `cairosvg` dependency; "
            "install it with `pip install cairosvg`, or pass an explicit "
            "`png_fallback=` argument to add_svg_picture()."
        ) from exc

    kwargs = {}
    if output_size is not None:
        kwargs["output_width"] = int(output_size[0])
        kwargs["output_height"] = int(output_size[1])
    return cairosvg.svg2png(bytestring=svg_blob, **kwargs)


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
