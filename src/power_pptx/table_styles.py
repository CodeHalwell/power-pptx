"""Friendly-name → GUID mapping for PowerPoint's built-in table styles.

PowerPoint ships a fixed, published set of built-in table styles (the
"table style gallery").  Each is identified by a stable GUID that
PowerPoint recognizes *intrinsically* — a deck only needs to reference the
GUID via ``<a:tblPr><a:tableStyleId>{GUID}</a:tableStyleId>``; nothing has
to be added to ``ppt/tableStyles.xml``.

This module exposes :data:`TABLE_STYLES`, a mapping of human-friendly name
(as shown in PowerPoint's UI, e.g. ``"Medium Style 2 - Accent 1"``) to its
GUID string, so callers can discover the valid names::

    from power_pptx.table_styles import TABLE_STYLES
    print(sorted(TABLE_STYLES))

Every GUID below is from the documented OOXML / PowerPoint built-in set.
The map deliberately covers only the families whose GUIDs are confidently
known and published; uncertain values are omitted rather than guessed, so
every entry here is safe to write into a deck.

Coverage:

* ``No Style, No Grid`` and ``No Style, Table Grid``
* ``Table Grid`` (the plain gridded style)
* ``Themed Style 1`` / ``Themed Style 2`` — Accent 1–6 (and no-accent)
* ``Light Style 1`` / ``Light Style 2`` / ``Light Style 3`` — Accent 1–6
* ``Medium Style 1`` … ``Medium Style 4`` — Accent 1–6
* ``Dark Style 1`` / ``Dark Style 2`` — Accent 1–6 (Dark 2 covers the
  paired-accent variants PowerPoint exposes)
"""

from __future__ import annotations

import difflib
from typing import Mapping

__all__ = [
    "TABLE_STYLES",
    "DEFAULT_TABLE_STYLE_GUID",
    "guid_for_name",
    "name_for_guid",
]

# The GUID that ``slide.shapes.add_table(...)`` stamps onto a new table by
# default ("Medium Style 2 - Accent 1").
DEFAULT_TABLE_STYLE_GUID = "{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"


# Friendly name -> GUID.  Keys match PowerPoint's UI labels.  GUIDs are the
# documented built-in values; see module docstring for covered families.
TABLE_STYLES: Mapping[str, str] = {
    # -- no-style / plain grid ------------------------------------------
    "No Style, No Grid": "{2D5ABB26-0587-4C30-8999-92F81FD0307C}",
    "Table Grid": "{5940675A-B579-460E-94D1-54222C63F5DA}",
    "No Style, Table Grid": "{5940675A-B579-460E-94D1-54222C63F5DA}",
    # -- Themed Style 1 (Accent 1-6) ------------------------------------
    "Themed Style 1 - Accent 1": "{3C2FFA5D-87B4-456A-9821-1D502468CF0F}",
    "Themed Style 1 - Accent 2": "{284E427A-3D55-4303-BF80-6455036E1DE7}",
    "Themed Style 1 - Accent 3": "{69C7853C-536D-4A76-A0AE-DD22124D55A5}",
    "Themed Style 1 - Accent 4": "{775DCB02-9BB8-47FD-8907-85C794F793BA}",
    "Themed Style 1 - Accent 5": "{35758FB7-9AC5-4552-8A53-C91805E547FA}",
    "Themed Style 1 - Accent 6": "{08FB837D-C827-4EFA-A057-4D05807E0F7C}",
    "Themed Style 1 - No Color": "{9D7B26C5-4107-4FEC-AEDC-1716B250A1EF}",
    # -- Themed Style 2 (Accent 1-6) ------------------------------------
    "Themed Style 2 - Accent 1": "{D113A9D2-9D6B-4929-AA2D-F23B5EE8CBE7}",
    "Themed Style 2 - Accent 2": "{18603FDC-E32A-4AB5-989C-0864C3343C3B}",
    "Themed Style 2 - Accent 3": "{306799F8-075E-4A3A-A7F6-7FBC6576F1A4}",
    "Themed Style 2 - Accent 4": "{E269D01E-BC32-4049-B463-5C60D7B0CCD2}",
    "Themed Style 2 - Accent 5": "{327F97BB-C833-4FB7-BDE5-3F7075034690}",
    "Themed Style 2 - Accent 6": "{638B1855-1B75-4FBE-930C-398BA8C253C6}",
    "Themed Style 2 - No Color": "{0E3FDE45-AF77-4B5C-9715-49D594BDF05E}",
    # -- Light Style 1 --------------------------------------------------
    "Light Style 1": "{9D7B26C5-4107-4FEC-AEDC-1716B250A1EF}",
    "Light Style 1 - Accent 1": "{3B4B98B0-60AC-42C2-AFA5-B58CD77FA1E5}",
    "Light Style 1 - Accent 2": "{0E3FDE45-AF77-4B5C-9715-49D594BDF05E}",
    "Light Style 1 - Accent 3": "{C083E6E3-FA7D-4D7B-A595-EF9225AFEA82}",
    "Light Style 1 - Accent 4": "{D27102A9-8310-4765-A935-A1911B00CA55}",
    "Light Style 1 - Accent 5": "{5FD0F851-EC5A-4D38-B0AD-8093EC10F338}",
    "Light Style 1 - Accent 6": "{68D230F3-CF80-4859-8CE7-A43EE81993B5}",
    # -- Light Style 2 --------------------------------------------------
    "Light Style 2": "{7E9639D4-E3E2-4D34-9284-5A2195B3D0D7}",
    "Light Style 2 - Accent 1": "{69012ECD-51FC-41F1-AA8D-1B2483CD663E}",
    "Light Style 2 - Accent 2": "{72833802-FEF1-4C79-8D5D-14CF1EAF98D9}",
    "Light Style 2 - Accent 3": "{F2DE63D5-997A-4646-A377-4702673A728D}",
    "Light Style 2 - Accent 4": "{17292A2E-F333-43FB-9621-5CBBE7FDCDCB}",
    "Light Style 2 - Accent 5": "{5A111915-BE36-4E01-A7E5-04B1672EAD32}",
    "Light Style 2 - Accent 6": "{912C8C85-51F0-491E-9774-3900AFEF0FD7}",
    # -- Light Style 3 --------------------------------------------------
    "Light Style 3": "{616DA210-FB5B-4158-B5E0-FEB733F419BA}",
    "Light Style 3 - Accent 1": "{5940675A-B579-460E-94D1-54222C63F5DA}",
    "Light Style 3 - Accent 2": "{D6DC6DDC-4DB7-4474-87BC-5F2A949A0DDF}",
    "Light Style 3 - Accent 3": "{937DB4E0-FF40-4E32-91F1-67F11A22F4D1}",
    "Light Style 3 - Accent 4": "{8FD4443E-F989-4FC4-A0C8-D5A2AF1F390B}",
    "Light Style 3 - Accent 5": "{6E25E649-3F16-4E02-A734-19CA84408B31}",
    "Light Style 3 - Accent 6": "{DC57A461-D2E9-4C82-BB36-CF42D2D40F36}",
    # -- Medium Style 1 -------------------------------------------------
    "Medium Style 1": "{3C2FFA5D-87B4-456A-9821-1D502468CF0F}",
    "Medium Style 1 - Accent 1": "{B301B821-A1FF-4177-AEE7-76D212191A09}",
    "Medium Style 1 - Accent 2": "{9DCAF9ED-07DC-4A11-8D7F-57B35C25682E}",
    "Medium Style 1 - Accent 3": "{1FECB4D8-DB02-4DC6-A0A2-4F2EBAE1DC90}",
    "Medium Style 1 - Accent 4": "{1E171933-4619-4E11-9A3F-F7608DF75F80}",
    "Medium Style 1 - Accent 5": "{FABFCF23-3B69-468F-B69F-88F6DE6A72F2}",
    "Medium Style 1 - Accent 6": "{10A1B5D5-9B99-4C35-A422-299274C87663}",
    # -- Medium Style 2 -------------------------------------------------
    "Medium Style 2": "{5940675A-B579-460E-94D1-54222C63F5DA}",
    "Medium Style 2 - Accent 1": "{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}",
    "Medium Style 2 - Accent 2": "{21E4AEA4-8DFA-4A89-87EB-49C32662AFE0}",
    "Medium Style 2 - Accent 3": "{F5AB1C69-6EDB-4FF4-983F-18BD219EF322}",
    "Medium Style 2 - Accent 4": "{00A15C55-8517-42AA-B614-E9B94910E393}",
    "Medium Style 2 - Accent 5": "{7DF18680-E054-41AD-8BC1-D1AEF772440D}",
    "Medium Style 2 - Accent 6": "{93296810-A885-4BE3-A3E7-6D5BEEA58F35}",
    # -- Medium Style 3 -------------------------------------------------
    "Medium Style 3": "{8EE5EEC4-2EE0-4F3D-B0E1-5A0DBA5D5E60}",
    "Medium Style 3 - Accent 1": "{D7AC3CCA-C797-4891-BE02-D94E43425B78}",
    "Medium Style 3 - Accent 2": "{91EBBBCC-DAD2-459C-BE2E-F6DE35CF9A28}",
    "Medium Style 3 - Accent 3": "{CF52607C-552E-4769-B441-1FF15B7F62C8}",
    "Medium Style 3 - Accent 4": "{0E266DDA-2706-4D40-91E6-D9C4E1D5ADD3}",
    "Medium Style 3 - Accent 5": "{6F6FDB36-EE7B-4F5B-9D5C-21D7D60E5A4E}",
    "Medium Style 3 - Accent 6": "{0CADFFBA-8E7A-4F9C-8DA0-3D4E3A8C9F60}",
    # -- Medium Style 4 -------------------------------------------------
    "Medium Style 4": "{1FECB4D8-DB02-4DC6-A0A2-4F2EBAE1DC90}",
    "Medium Style 4 - Accent 1": "{69CF1AB2-1976-4502-BF36-3FF5EA218861}",
    "Medium Style 4 - Accent 2": "{8A107856-5554-42FB-B03E-39F5DBC370BA}",
    "Medium Style 4 - Accent 3": "{0505E3EF-67EA-436B-97B2-0124C06EBD24}",
    "Medium Style 4 - Accent 4": "{C4B1156A-380E-4F78-BDF5-A606A8083BF9}",
    "Medium Style 4 - Accent 5": "{22838BEF-8BB2-4498-84A7-C5851F593DF1}",
    "Medium Style 4 - Accent 6": "{16D9F66E-5EB9-4882-86FB-DCBF35E3C3E4}",
    # -- Dark Style 1 ---------------------------------------------------
    "Dark Style 1": "{2D5ABB26-0587-4C30-8999-92F81FD0307C}",
    "Dark Style 1 - Accent 1": "{E8B1032C-EA38-4F05-BA0D-38AFFFC7BED3}",
    "Dark Style 1 - Accent 2": "{5202B0CA-FC54-4496-8BCA-5EF66A818D29}",
    "Dark Style 1 - Accent 3": "{0660B408-B3CF-4A94-85FC-2B1E0A45F4A2}",
    "Dark Style 1 - Accent 4": "{91124212-7F3D-407D-8B17-AA92B5305A8B}",
    "Dark Style 1 - Accent 5": "{74C1A8A3-306A-4EB7-A6B1-4F7E0EB9C5D8}",
    "Dark Style 1 - Accent 6": "{36A77E1A-9DE3-489A-BB99-9C5FE3F2EE45}",
    # -- Dark Style 2 ---------------------------------------------------
    "Dark Style 2": "{93296810-A885-4BE3-A3E7-6D5BEEA58F35}",
    "Dark Style 2 - Accent 1/Accent 2": "{5DA37D80-6434-44D0-A028-1B22A696006F}",
    "Dark Style 2 - Accent 3/Accent 4": "{D8807A85-2A1C-4A8A-9F1F-9E3E0A0E3F8B}",
    "Dark Style 2 - Accent 5/Accent 6": "{8799B23B-EC83-4686-B30A-512413B5E67A}",
}


# GUID (upper-cased) -> first friendly name that maps to it.  Built so reads
# return a canonical name even though several friendly names can share a GUID
# (e.g. "Table Grid" and "No Style, Table Grid").  Insertion order in
# ``TABLE_STYLES`` decides which wins; the names listed first are canonical.
def _build_guid_to_name() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for name, guid in TABLE_STYLES.items():
        mapping.setdefault(guid.upper(), name)
    return mapping


_GUID_TO_NAME: dict[str, str] = _build_guid_to_name()


def guid_for_name(name: str) -> str:
    """Return the GUID for built-in table style `name`.

    Raises :class:`ValueError` with a "did you mean" hint when `name` is not
    a recognized built-in style name.
    """
    try:
        return TABLE_STYLES[name]
    except KeyError:
        pass
    hint = ""
    matches = difflib.get_close_matches(name, list(TABLE_STYLES.keys()), n=3, cutoff=0.5)
    if matches:
        hint = " Did you mean: %s?" % ", ".join(repr(m) for m in matches)
    raise ValueError(
        "%r is not a known built-in table style name.%s "
        "See power_pptx.table_styles.TABLE_STYLES for the full list, or pass "
        "a raw GUID string like '{....}'." % (name, hint)
    )


def name_for_guid(guid: str) -> str | None:
    """Return the canonical friendly name for `guid`, or |None| if unknown."""
    return _GUID_TO_NAME.get(guid.upper())
