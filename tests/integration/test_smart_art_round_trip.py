"""Round-trip suite for SmartArt text substitution in a PowerPoint-authored deck."""

from __future__ import annotations

import io
import os

from power_pptx import Presentation

from .round_trip import _canonicalize_xml, _parts, _save_to_bytes, assert_round_trip

# -- saved by PowerPoint: its diagram has untyped content nodes and a drawing
# -- part caching the laid-out shapes, neither of which the hand-built fixture
# -- under tests/test_files has --
POWERPOINT = os.path.join(
    os.path.dirname(__file__), "..", "..", "features", "steps", "test_files", "shp-shapes.pptx"
)


def _diagram_parts(pptx: bytes) -> dict[str, bytes]:
    return {
        name: _canonicalize_xml(blob)
        for name, blob in _parts(pptx).items()
        if name.startswith("ppt/diagrams/")
    }


class DescribeSmartArtRoundTrip:
    def it_saves_an_untouched_diagram_back_as_it_was_read(self):
        with open(POWERPOINT, "rb") as f:
            source = f.read()

        resaved = _save_to_bytes(Presentation(io.BytesIO(source)))

        assert _diagram_parts(resaved) == _diagram_parts(source)

    def it_round_trips_replaced_text(self):
        prs = Presentation(POWERPOINT)
        prs.slides[0].smart_art[0].set_text(["Plan", "Build", "Ship"])

        assert_round_trip(prs)

    def it_changes_only_the_data_and_the_cached_drawing(self):
        with open(POWERPOINT, "rb") as f:
            source = f.read()
        prs = Presentation(io.BytesIO(source))
        prs.slides[0].smart_art[0].set_text(["Plan", "Build", "Ship"])

        before, after = _diagram_parts(source), _diagram_parts(_save_to_bytes(prs))

        assert sorted(name for name in before if before[name] != after[name]) == [
            "ppt/diagrams/data1.xml",
            "ppt/diagrams/drawing1.xml",
        ]
