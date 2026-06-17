"""Diagrams torture: every native-shape diagram recipe, dict overrides,
long labels, many nodes, all arrow-head styles, and dark themes.
"""

from __future__ import annotations

from _util import blank, deck

from power_pptx import BBox
from power_pptx.diagrams import (
    comparison_columns,
    cycle,
    decision_tree,
    horizontal_pipeline,
    hub_and_spoke,
    vertical_pipeline,
)
from power_pptx.util import Inches


def _title(s, text):
    tb = s.shapes.add_textbox(Inches(0.5), Inches(0.15), Inches(12.3), Inches(0.5))
    tb.text_frame.text = text


def build():
    prs = deck()

    # --- Horizontal pipeline with per-step dict overrides + arrow heads --
    for head in ["triangle", "stealth", "diamond", "oval", "arrow", "none"]:
        s = blank(prs)
        _title(s, f"horizontal_pipeline arrow_head={head}")
        horizontal_pipeline(
            s, BBox.from_inches(0.5, 2.5, 12.3, 1.8),
            steps=[
                {"label": "Extract", "sublabel": "S3 -> queue",
                 "fill": "#101826", "text_color": "#E6EDF3"},
                "Classify",
                {"label": "Enrich with reference data", "fill": "#0F2D6B",
                 "text_color": "#FFFFFF"},
                "Output",
            ],
            accent="#0B5CFF",
            arrow_head=head,
        )

    # --- Vertical pipeline -----------------------------------------------
    s = blank(prs)
    _title(s, "vertical_pipeline")
    vertical_pipeline(
        s, BBox.from_inches(4.5, 1.0, 4.3, 6.2),
        steps=["Intake", "Triage", "Resolve", "Verify", "Close"],
        accent="#0F766E",
    )

    # --- Hub and spoke, many spokes --------------------------------------
    s = blank(prs)
    _title(s, "hub_and_spoke (8 spokes)")
    hub_and_spoke(
        s, BBox.from_inches(2.5, 1.0, 8.3, 6.2),
        centre="Platform",
        spokes=["Ingest", "Model", "Serve", "Observe",
                "Secure", "Bill", "Audit", "Scale"],
        accent="#7C3AED", hub_fill="#7C3AED", hub_text_color="#FFFFFF",
    )

    # --- Cycle -----------------------------------------------------------
    s = blank(prs)
    _title(s, "cycle")
    cycle(s, BBox.from_inches(3, 1.2, 7.3, 6.0),
          steps=["Plan", "Build", "Measure", "Learn", "Iterate"])

    # --- Decision tree, nested + leaf styling ----------------------------
    s = blank(prs)
    _title(s, "decision_tree")
    decision_tree(
        s, BBox.from_inches(0.7, 1.0, 11.9, 6.2),
        root="Incoming request",
        branches=[
            {"label": "Cache hit", "children": ["Return cached"]},
            {"label": "Cache miss", "children": ["Compute", "Store", "Return"]},
            "Reject (rate limited)",
        ],
        fill="#141A23", text_color="#E6EDF3",
        root_fill="#5B9CFF", root_text_color="#0B0E14",
        leaf_fill="#1E2A38", leaf_text_color="#FFD166",
    )

    # --- Comparison columns ----------------------------------------------
    s = blank(prs)
    _title(s, "comparison_columns")
    comparison_columns(
        s, BBox.from_inches(0.5, 1.0, 12.3, 6.0),
        columns=[
            {"title": "Plan A", "body": ["Fast", "Cheap",
                                         "Scales to many regions"]},
            {"title": "Plan B", "body": "Single-region, lower latency"},
            {"title": "Plan C", "body": ["Enterprise SLA", "Dedicated tenancy",
                                         "Custom retention windows"]},
        ],
        header_fill="#0B5CFF", header_text_color="#FFFFFF",
    )

    return prs


if __name__ == "__main__":
    build().save("_out/04_diagrams_torture.pptx")
