"""Deck builders and zip inspectors shared by the master/layout hierarchy tests.

``apply_template`` and ``import_slide`` copy slide masters, layouts and themes
between packages.  The tests for them need decks whose masters, layouts and
themes carry *dependencies* (pictures, picture fills) and a few ways to look
inside the saved package.  They live here so the integration tests and the
schema tests build exactly the same decks.
"""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
from typing import TYPE_CHECKING

import pytest
from lxml import etree
from PIL import Image as PILImage

from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT
from power_pptx.oxml import parse_xml
from power_pptx.oxml.ns import nsdecls
from power_pptx.parts.image import Image, ImagePart

from .oxml_schema_validator import schema_validation_available

if TYPE_CHECKING:
    from power_pptx import Presentation

RED = (200, 30, 30)
BLUE = (30, 30, 200)

_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

needs_schema_validator = pytest.mark.skipif(
    not schema_validation_available(),
    reason="lxml or the bundled ISO-29500 XSD schemas are unavailable",
)


def solid_png(color: tuple[int, int, int]) -> bytes:
    """Return the bytes of a tiny solid-colour PNG; distinct colours give distinct bytes."""
    buf = io.BytesIO()
    PILImage.new("RGB", (8, 8), color).save(buf, format="PNG")
    return buf.getvalue()


def saved_bytes(prs: Presentation) -> bytes:
    """Return `prs` saved to an in-memory .pptx."""
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def zip_names(blob: bytes, pattern: str) -> list[str]:
    """Return the sorted member names of the zip `blob` that fully match regex `pattern`."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        return sorted(n for n in z.namelist() if re.fullmatch(pattern, n))


def add_logo(
    prs: Presentation, owner_part, png: bytes, shape_id: int, *, dedupe: bool = True
) -> None:
    """Show `png` as a picture on `owner_part`, a slide master or layout part of `prs`.

    The python-pptx shape collections of masters and layouts cannot add pictures, so this
    relates an image part to `owner_part` and appends a `p:pic` that embeds it.  With
    `dedupe=False` the picture gets an image part of its own even when `prs` already holds
    the same bytes (a package written by another producer may well store an image twice).
    """
    if dedupe:
        image_part = prs.part.package.get_or_add_image_part(io.BytesIO(png))
    else:
        image_part = ImagePart.new(prs.part.package, Image.from_blob(png))
    rId = owner_part.relate_to(image_part, RT.IMAGE)
    pic = parse_xml(
        f"<p:pic {nsdecls('p', 'a', 'r')}>"
        f'<p:nvPicPr><p:cNvPr id="{shape_id}" name="Logo {shape_id}"/>'
        '<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>'
        '<p:nvPr userDrawn="1"/></p:nvPicPr>'
        f'<p:blipFill><a:blip r:embed="{rId}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
        '<p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="914400" cy="914400"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        "</p:pic>"
    )
    owner_part._element.cSld.spTree.append(pic)


def add_theme_image_fill(prs: Presentation, png: bytes) -> None:
    """Make the last background fill of `prs`'s theme a picture fill showing `png`."""
    theme_part = prs.slide_master.part.part_related_by(RT.THEME)
    image_part = prs.part.package.get_or_add_image_part(io.BytesIO(png))
    rId = theme_part.relate_to(image_part, RT.IMAGE)
    bg_fills = theme_part._element.xpath(".//a:bgFillStyleLst")[0]
    bg_fills.remove(bg_fills[-1])
    bg_fills.append(
        parse_xml(
            f'<a:blipFill {nsdecls("a", "r")} rotWithShape="1">'
            f'<a:blip r:embed="{rId}"/><a:stretch><a:fillRect/></a:stretch></a:blipFill>'
        )
    )


def embedded_images(blob: bytes, partname: str) -> list[bytes | None]:
    """Return the image bytes behind each `r:embed` in part `partname` of the zip `blob`.

    An entry is `None` where the `r:embed` value names no relationship of the part (a dangling
    reference, which PowerPoint "repairs" by dropping the picture).
    """
    folder, base = posixpath.split(partname)
    rels_name = posixpath.join(folder, "_rels", base + ".rels")
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        targets: dict[str, str] = {}
        if rels_name in z.namelist():
            for rel in etree.fromstring(z.read(rels_name)):
                target = posixpath.normpath(posixpath.join(folder, rel.get("Target")))
                targets[rel.get("Id")] = target
        root = etree.fromstring(z.read(partname))
        embeds = root.xpath("//@r:embed", namespaces={"r": _R_NS})
        return [z.read(targets[e]) if e in targets else None for e in embeds]
