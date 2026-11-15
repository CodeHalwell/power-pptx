"""Deck fixtures for tests of the presentation-properties part (`ppt/presProps.xml`).

The default template carries a `presProps.xml` with nothing in it but
PowerPoint's extension list, so the two cases that matter have to be made:

* a deck from a tool that leaves the part out (`without_presprops`), and
* a deck whose slide-show setup was saved by PowerPoint (`with_presprops` and
  `POWERPOINT_PRESPROPS_XML`).
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from lxml import etree

import power_pptx

PRESPROPS = "ppt/presProps.xml"
PRESPROPS_RELTYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps"

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
_P15 = "http://schemas.microsoft.com/office/powerpoint/2012/main"

# -- What PowerPoint writes after *Set Up Slide Show* is used to choose a
# -- looping kiosk show: the show properties with their own pen colour and
# -- extension list, a recently-used-colours list, and the deck-level
# -- extension list. Everything but `loop` and `p:kiosk` is content the
# -- slide-show API has no business touching. --
POWERPOINT_PRESPROPS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    '<p:presentationPr xmlns:a="%(a)s" xmlns:r="%(r)s" xmlns:p="%(p)s">'
    '<p:showPr loop="1" showNarration="1">'
    "<p:kiosk/>"
    "<p:sldAll/>"
    '<p:penClr><a:prstClr val="red"/></p:penClr>'
    "<p:extLst>"
    '<p:ext uri="{EC167BDD-8182-4AB7-AECC-EB403E3ABB37}">'
    '<p14:laserClr xmlns:p14="%(p14)s"><a:srgbClr val="FF0000"/></p14:laserClr>'
    "</p:ext>"
    '<p:ext uri="{2FDB2607-1784-4EEB-B798-7EB5836EED8A}">'
    '<p14:showMediaCtrls xmlns:p14="%(p14)s" val="1"/>'
    "</p:ext>"
    "</p:extLst>"
    "</p:showPr>"
    '<p:clrMru><a:srgbClr val="FF6600"/><a:srgbClr val="003366"/></p:clrMru>'
    "<p:extLst>"
    '<p:ext uri="{E76CE94A-603C-4142-B9EB-6D1370010A27}">'
    '<p14:discardImageEditData xmlns:p14="%(p14)s" val="0"/>'
    "</p:ext>"
    '<p:ext uri="{D31A062A-798A-4329-ABDD-BBA856620510}">'
    '<p14:defaultImageDpi xmlns:p14="%(p14)s" val="32767"/>'
    "</p:ext>"
    '<p:ext uri="{FD5EFAAD-0ECE-453E-9831-46B23BE46B34}">'
    '<p15:chartTrackingRefBased xmlns:p15="%(p15)s" val="1"/>'
    "</p:ext>"
    "</p:extLst>"
    "</p:presentationPr>"
) % {"a": _A, "r": _R, "p": _P, "p14": _P14, "p15": _P15}


def saved(prs) -> bytes:
    """Return `prs` saved to bytes."""
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def reopened(prs):
    """Return `prs` after a save and a fresh load."""
    return power_pptx.Presentation(io.BytesIO(saved(prs)))


def part_names(blob: bytes) -> list[str]:
    """Return the member names of the package in `blob`."""
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        return zf.namelist()


def part_bytes(blob: bytes, name: str) -> bytes:
    """Return the bytes of member `name` of the package in `blob`."""
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        return zf.read(name)


def presprops_root(blob: bytes):
    """Return the parsed `p:presentationPr` root of the package in `blob`."""
    return etree.fromstring(part_bytes(blob, PRESPROPS))


def canonical(xml: bytes | str) -> bytes:
    """Return `xml` in canonical form, for comparing XML regardless of serialisation."""
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    root = etree.fromstring(xml, etree.XMLParser(remove_blank_text=True))
    return etree.tostring(root, method="c14n2")


def blank_deck_bytes(slides: int = 1) -> bytes:
    """Return a saved deck built from the default template with `slides` blank slides."""
    prs = power_pptx.Presentation()
    for _ in range(slides):
        prs.slides.add_slide(prs.slide_layouts[6])
    return saved(prs)


def _rewritten(blob: bytes, replace: dict[str, bytes | None]) -> bytes:
    """Return the package in `blob` with members replaced (or dropped, for |None|)."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(blob)) as zin:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename in replace:
                    data = replace[item.filename]
                    if data is None:
                        continue
                else:
                    data = zin.read(item.filename)
                zout.writestr(item.filename, data)
    return out.getvalue()


def with_presprops(xml: str | bytes, blob: bytes | None = None) -> bytes:
    """Return a deck whose `ppt/presProps.xml` is `xml`."""
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    return _rewritten(blank_deck_bytes() if blob is None else blob, {PRESPROPS: xml})


def without_presprops(blob: bytes | None = None) -> bytes:
    """Return a deck with no presentation-properties part at all.

    The part, its relationship from the presentation part and its content-type
    override are all removed, which is what a deck written by a tool that does
    not emit the part looks like.
    """
    blob = blank_deck_bytes() if blob is None else blob

    def without(name: str, attr: str, doomed) -> bytes:
        root = etree.fromstring(part_bytes(blob, name))
        for child in list(root):
            if doomed(child.get(attr) or ""):
                root.remove(child)
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    return _rewritten(
        blob,
        {
            PRESPROPS: None,
            "[Content_Types].xml": without(
                "[Content_Types].xml", "PartName", lambda v: v == "/" + PRESPROPS
            ),
            "ppt/_rels/presentation.xml.rels": without(
                "ppt/_rels/presentation.xml.rels", "Type", lambda v: v == PRESPROPS_RELTYPE
            ),
        },
    )


_pml_schema = None


def presprops_schema_errors(blob: bytes) -> list[str]:
    """Return the ISO 29500 schema errors in `ppt/presProps.xml` of the package in `blob`.

    The packaged validator (`power_pptx.validation`) only checks the parts on
    its own list, which does not include this one, so the part is validated
    here against the same bundled `pml.xsd`.
    """
    global _pml_schema
    if _pml_schema is None:
        xsd = Path(power_pptx.__file__).parent / "schemas" / "pml.xsd"
        _pml_schema = etree.XMLSchema(etree.parse(str(xsd)))
    _pml_schema.validate(presprops_root(blob))
    return [str(error) for error in _pml_schema.error_log]
