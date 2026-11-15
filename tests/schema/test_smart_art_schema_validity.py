"""Schema validity of SmartArt diagram data after text substitution.

The deck-level validator has no root schema for diagram parts, so the data
part `SmartArtShape.set_text()` rewrites is validated here directly against
the bundled `dml-diagram.xsd`.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import etree

import power_pptx
from power_pptx import Presentation
from power_pptx.oxml.ns import qn

from .oxml_schema_validator import assert_schema_valid, schema_validation_available

pytestmark = pytest.mark.skipif(
    not schema_validation_available(),
    reason="lxml or the bundled ISO-29500 XSD schemas are unavailable",
)

# -- a diagram saved by PowerPoint: untyped content nodes, and a drawing part
# -- caching the laid-out shapes (the hand-built fixture under tests/test_files
# -- uses model ids the schema rejects, so it cannot serve here)
POWERPOINT = os.path.join(
    os.path.dirname(__file__), "..", "..", "features", "steps", "test_files", "shp-shapes.pptx"
)


def _diagram_schema() -> etree.XMLSchema:
    xsd = Path(power_pptx.__file__).with_name("schemas") / "dml-diagram.xsd"
    return etree.XMLSchema(etree.parse(str(xsd)))


def _saved(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _assert_data_part_valid(pptx: bytes) -> None:
    schema = _diagram_schema()
    with ZipFile(io.BytesIO(pptx)) as zf:
        names = [n for n in zf.namelist() if n.startswith("ppt/diagrams/data")]
        assert names, "deck has no diagram data part"
        for name in names:
            doc = etree.fromstring(zf.read(name))
            assert schema.validate(doc), "%s: %s" % (name, schema.error_log)


def _content_nodes(sa):
    pt_lst = sa._data_element.find(qn("dgm:ptLst"))
    return [pt for pt in pt_lst.findall(qn("dgm:pt")) if pt.get("type") in (None, "node", "asst")]


class DescribeSmartArtTextSchemaValidity:
    def it_validates_the_fixture_as_it_is(self):
        # -- so that a failure below is down to `set_text()`, not to the input --
        _assert_data_part_valid(Path(POWERPOINT).read_bytes())

    def it_keeps_the_data_part_valid_after_replacing_text(self):
        prs = Presentation(POWERPOINT)
        prs.slides[0].smart_art[0].set_text(["Plan", "Build", "Ship"])

        pptx = _saved(prs)

        _assert_data_part_valid(pptx)
        assert_schema_valid(pptx)

    def it_keeps_the_data_part_valid_after_filling_a_node_showing_its_prompt(self):
        prs = Presentation(POWERPOINT)
        sa = prs.slides[0].smart_art[0]
        pt = _content_nodes(sa)[1]
        pt.find(qn("dgm:prSet")).set("phldr", "1")
        t = pt.find(qn("dgm:t"))
        for p in t.findall(qn("a:p")):
            t.remove(p)
        etree.SubElement(etree.SubElement(t, qn("a:p")), qn("a:endParaRPr"), lang="en-US")

        sa.set_text(["Plan", "Build", "Ship"])

        assert sa.texts == ["Plan", "Build", "Ship"]
        _assert_data_part_valid(_saved(prs))

    def it_keeps_the_data_part_valid_after_giving_a_node_its_first_text_body(self):
        prs = Presentation(POWERPOINT)
        sa = prs.slides[0].smart_art[0]
        pt = _content_nodes(sa)[1]
        pt.remove(pt.find(qn("dgm:t")))
        etree.SubElement(pt, qn("dgm:extLst"))

        sa.set_text(["Plan", "Build", "Ship"])

        assert sa.texts == ["Plan", "Build", "Ship"]
        _assert_data_part_valid(_saved(prs))
