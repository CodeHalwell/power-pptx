"""Self-tests for the master/layout hierarchy validator.

The validator is only worth having if it really flags the bug classes it guards against, so
each test below breaks a good deck in one specific way and expects that breakage reported.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Callable

import pytest
from lxml import etree

from power_pptx import Presentation

from .hierarchy_decks import saved_bytes
from .hierarchy_validator import iter_hierarchy_violations

_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _rewrite_member(blob: bytes, member: str, transform: Callable[[bytes], bytes]) -> bytes:
    """Return `blob` (a zip) with `member` replaced by `transform(its bytes)`."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(blob)) as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            # -- read before writing: writestr(zinfo, ...) mutates the shared ZipInfo --
            data = zin.read(item.filename)
            zout.writestr(item, transform(data) if item.filename == member else data)
    return out.getvalue()


def _edit_xml(blob: bytes, member: str, edit: Callable[[etree._Element], None]) -> bytes:
    def transform(data: bytes) -> bytes:
        root = etree.fromstring(data)
        edit(root)
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    return _rewrite_member(blob, member, transform)


_MASTER = "ppt/slideMasters/slideMaster1.xml"


class DescribeHierarchyValidator:
    @pytest.fixture
    def blob(self) -> bytes:
        return saved_bytes(Presentation())

    def it_accepts_a_deck_straight_from_the_default_template(self, blob):
        assert list(iter_hierarchy_violations(blob)) == []

    def it_flags_a_layout_entry_that_resolves_to_the_theme(self, blob):
        # -- the bug apply_template used to write: a stale r:id landing on the theme --
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            rels = z.read("ppt/slideMasters/_rels/slideMaster1.xml.rels").decode()
        theme_rId = re.search(r'Id="(rId\d+)"[^>]*/theme"', rels).group(1)

        def edit(root):
            root.find(".//{%s}sldLayoutId" % _P_NS).set("{%s}id" % _R_NS, theme_rId)

        broken = _edit_xml(blob, _MASTER, edit)

        violations = list(iter_hierarchy_violations(broken))
        assert any("not a slideLayout relationship" in msg for _, msg in violations), violations

    def it_flags_a_layout_that_the_master_relates_to_but_does_not_list(self, blob):
        def edit(root):
            entries = root.findall(".//{%s}sldLayoutId" % _P_NS)
            entries[-1].getparent().remove(entries[-1])

        broken = _edit_xml(blob, _MASTER, edit)

        violations = list(iter_hierarchy_violations(broken))
        assert any("related to the master but not listed" in msg for _, msg in violations)

    def it_flags_an_id_used_twice(self, blob):
        def edit(root):
            first, second = root.findall(".//{%s}sldLayoutId" % _P_NS)[:2]
            second.set("id", first.get("id"))

        broken = _edit_xml(blob, _MASTER, edit)

        violations = list(iter_hierarchy_violations(broken))
        assert any("already used by" in msg for _, msg in violations), violations

    def it_flags_an_id_below_the_minimum_the_spec_allows(self, blob):
        def edit(root):
            root.find(".//{%s}sldLayoutId" % _P_NS).set("id", "256")

        broken = _edit_xml(blob, _MASTER, edit)

        violations = list(iter_hierarchy_violations(broken))
        assert any("outside 2147483648" in msg for _, msg in violations), violations

    def it_flags_a_master_entry_without_an_id(self, blob):
        def edit(root):
            del root.find(".//{%s}sldMasterId" % _P_NS).attrib["id"]

        broken = _edit_xml(blob, "ppt/presentation.xml", edit)

        violations = list(iter_hierarchy_violations(broken))
        assert any("no id attribute" in msg for _, msg in violations), violations
