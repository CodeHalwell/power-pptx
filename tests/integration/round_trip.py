"""Round-trip diff harness for python-pptx-next.

Save a deck, reopen it, save it again, and assert that no XML part has changed
between the two saves. Per the project roadmap, this is the gate every later
phase ships behind: any change that loses or reorders XML is a regression.

The harness canonicalizes XML before comparison (so attribute order and
insignificant whitespace don't trigger false positives) and compares non-XML
parts (e.g. embedded images) byte-for-byte.
"""

from __future__ import annotations

import io
from typing import Callable
from zipfile import ZipFile

from lxml import etree

from pptx import Presentation
from pptx.presentation import Presentation as PresentationT


def _parts(pptx_bytes: bytes) -> dict[str, bytes]:
    """Return a dict mapping each part name to its raw bytes inside the deck."""
    with ZipFile(io.BytesIO(pptx_bytes)) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def _canonicalize_xml(xml_bytes: bytes) -> bytes:
    """Return a c14n-canonicalized form of `xml_bytes` suitable for byte equality."""
    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.fromstring(xml_bytes, parser)
    return etree.tostring(root, method="c14n2")


def _save_to_bytes(prs: PresentationT) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def round_trip_diff(prs: PresentationT) -> dict[str, tuple[bytes | None, bytes | None]]:
    """Save → reopen → save `prs` and return a per-part diff.

    The result is an empty dict when the round-trip is clean; otherwise each entry
    is `(saved_first, saved_second)` for a part whose content differs (or is
    present on only one side).
    """
    first = _save_to_bytes(prs)
    reopened = Presentation(io.BytesIO(first))
    second = _save_to_bytes(reopened)

    parts1, parts2 = _parts(first), _parts(second)
    diff: dict[str, tuple[bytes | None, bytes | None]] = {}
    for name in set(parts1) | set(parts2):
        p1 = parts1.get(name)
        p2 = parts2.get(name)
        if p1 is None or p2 is None:
            diff[name] = (p1, p2)
            continue
        if name.endswith((".xml", ".rels")):
            try:
                if _canonicalize_xml(p1) != _canonicalize_xml(p2):
                    diff[name] = (p1, p2)
            except etree.XMLSyntaxError:
                if p1 != p2:
                    diff[name] = (p1, p2)
        else:
            if p1 != p2:
                diff[name] = (p1, p2)
    return diff


def assert_round_trip(
    prs_or_factory: PresentationT | Callable[[], PresentationT],
) -> None:
    """Assert `prs_or_factory` survives a save → open → save cycle unchanged.

    Pass either a presentation instance or a zero-arg factory that returns one;
    the factory form is preferred when the caller wants the harness to own the
    full lifecycle (e.g. so a fresh deck is built per assertion in a parametrized
    test).
    """
    prs = prs_or_factory() if callable(prs_or_factory) else prs_or_factory
    diff = round_trip_diff(prs)
    if diff:
        raise AssertionError(
            "round-trip changed the following parts: " + ", ".join(sorted(diff))
        )
