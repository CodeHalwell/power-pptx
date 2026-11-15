# pyright: reportPrivateUsage=false

"""Unit-test suite for `power_pptx.parts.presprops` module."""

from __future__ import annotations

import io

import pytest

import power_pptx
from power_pptx.opc.constants import CONTENT_TYPE as CT
from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT
from power_pptx.opc.package import Part
from power_pptx.opc.packuri import PackURI
from power_pptx.oxml.presprops import CT_PresentationProperties
from power_pptx.parts.presprops import PresentationPropertiesPart

from ..unitutil.presprops import (
    PRESPROPS,
    blank_deck_bytes,
    part_bytes,
    part_names,
    saved,
    with_presprops,
    without_presprops,
)


def _presprops_rels(prs):
    """Return the presProps relationships of the presentation part of `prs`."""
    return [rel for rel in prs.part.rels.values() if rel.reltype == RT.PRES_PROPS]


class DescribePresentationPropertiesPart(object):
    """Unit-test suite for `power_pptx.parts.presprops.PresentationPropertiesPart`."""

    def it_is_the_class_presProps_xml_is_loaded_as(self):
        prs = power_pptx.Presentation()

        part = prs.part.part_related_by(RT.PRES_PROPS)

        assert isinstance(part, PresentationPropertiesPart)
        assert part.partname == "/ppt/presProps.xml"
        assert part.content_type == CT.PML_PRES_PROPS
        assert isinstance(part.presentationPr, CT_PresentationProperties)
        assert part.added_on_demand is False

    def it_can_find_the_part_of_a_presentation(self):
        prs = power_pptx.Presentation()

        part = PresentationPropertiesPart.find(prs.part)

        assert part is prs.part.part_related_by(RT.PRES_PROPS)

    def but_it_finds_nothing_and_adds_nothing_when_the_deck_has_no_such_part(self):
        prs = power_pptx.Presentation(io.BytesIO(without_presprops()))

        assert PresentationPropertiesPart.find(prs.part) is None
        assert _presprops_rels(prs) == []
        assert PRESPROPS not in part_names(saved(prs))

    def it_can_construct_a_new_empty_part(self):
        prs = power_pptx.Presentation(io.BytesIO(without_presprops()))

        part = PresentationPropertiesPart.new(prs.part.package)

        assert isinstance(part.partname, PackURI)
        assert part.partname == "/ppt/presProps.xml"
        assert part.content_type == CT.PML_PRES_PROPS
        assert part.package is prs.part.package
        assert part.added_on_demand is True
        assert len(part.presentationPr) == 0
        # -- constructing it relates it to nothing --
        assert _presprops_rels(prs) == []

    def and_it_chooses_another_partname_when_presProps_xml_is_taken(self):
        prs = power_pptx.Presentation()

        part = PresentationPropertiesPart.new(prs.part.package)

        assert part.partname != "/ppt/presProps.xml"
        assert part.partname.startswith("/ppt/presProps")
        assert part.partname not in {p.partname for p in prs.part.package.iter_parts()}

    def it_returns_the_existing_part_from_get_or_add(self):
        prs = power_pptx.Presentation()
        existing = PresentationPropertiesPart.find(prs.part)

        part = PresentationPropertiesPart.get_or_add(prs.part)

        assert part is existing
        assert len(_presprops_rels(prs)) == 1

    def and_it_adds_the_part_and_its_relationship_when_the_deck_has_none(self):
        prs = power_pptx.Presentation(io.BytesIO(without_presprops()))

        part = PresentationPropertiesPart.get_or_add(prs.part)

        assert part.added_on_demand is True
        assert PresentationPropertiesPart.find(prs.part) is part
        assert [rel.target_part for rel in _presprops_rels(prs)] == [part]
        # -- and a second call does not add a second one --
        assert PresentationPropertiesPart.get_or_add(prs.part) is part
        assert len(_presprops_rels(prs)) == 1

    def it_writes_an_added_part_with_its_relationship_and_content_type(self):
        prs = power_pptx.Presentation(io.BytesIO(without_presprops()))
        PresentationPropertiesPart.get_or_add(prs.part)

        blob = saved(prs)

        assert PRESPROPS in part_names(blob)
        rels = part_bytes(blob, "ppt/_rels/presentation.xml.rels").decode("utf-8")
        assert rels.count('Type="%s"' % RT.PRES_PROPS) == 1
        assert 'Target="presProps.xml"' in rels
        content_types = part_bytes(blob, "[Content_Types].xml").decode("utf-8")
        assert (
            '<Override PartName="/ppt/presProps.xml" ContentType="%s"/>' % CT.PML_PRES_PROPS
            in content_types
        )
        # -- and it loads again as the same kind of part, no longer "added" --
        again = PresentationPropertiesPart.find(power_pptx.Presentation(io.BytesIO(blob)).part)
        assert again is not None
        assert again.added_on_demand is False

    def it_can_remove_itself_from_a_presentation(self):
        prs = power_pptx.Presentation(io.BytesIO(without_presprops()))
        part = PresentationPropertiesPart.get_or_add(prs.part)

        part.remove_from(prs.part)

        assert PresentationPropertiesPart.find(prs.part) is None
        assert _presprops_rels(prs) == []
        assert PRESPROPS not in part_names(saved(prs))

    def it_ignores_a_presProps_part_with_an_unexpected_content_type(self):
        """A part the standard content type was not declared for loads as a plain `Part`."""
        prs = power_pptx.Presentation(io.BytesIO(_deck_with_untyped_presprops()))
        assert type(prs.part.part_related_by(RT.PRES_PROPS)) is Part

        assert PresentationPropertiesPart.find(prs.part) is None

    def but_it_refuses_to_add_a_second_part_alongside_it(self):
        prs = power_pptx.Presentation(io.BytesIO(_deck_with_untyped_presprops()))

        with pytest.raises(ValueError, match="unexpected content type 'application/xml'"):
            PresentationPropertiesPart.get_or_add(prs.part)

        assert len(_presprops_rels(prs)) == 1

    def it_leaves_the_rest_of_the_part_as_it_was_read(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:presentationPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
            ' xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:prnPr prnWhat="handouts6" clrMode="gray"/>'
            '<p:clrMru><a:srgbClr val="FF6600"/></p:clrMru>'
            "</p:presentationPr>"
        )
        prs = power_pptx.Presentation(io.BytesIO(with_presprops(xml)))

        root = PresentationPropertiesPart.find(prs.part).presentationPr

        assert [child.tag.rpartition("}")[2] for child in root] == ["prnPr", "clrMru"]
        assert b'<p:prnPr prnWhat="handouts6" clrMode="gray"/>' in part_bytes(saved(prs), PRESPROPS)


def _deck_with_untyped_presprops() -> bytes:
    """Return a deck whose content-types stream has no override for `presProps.xml`.

    The part then falls back to the `xml` default (`application/xml`), which is
    how a deck assembled by hand or by a careless tool can end up.
    """
    import zipfile

    blob = blank_deck_bytes()
    content_types = part_bytes(blob, "[Content_Types].xml").decode("utf-8")
    override = '<Override PartName="/ppt/presProps.xml" ContentType="%s"/>' % CT.PML_PRES_PROPS
    assert override in content_types
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(blob)) as zin:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "[Content_Types].xml":
                    data = content_types.replace(override, "").encode("utf-8")
                zout.writestr(item.filename, data)
    return out.getvalue()
