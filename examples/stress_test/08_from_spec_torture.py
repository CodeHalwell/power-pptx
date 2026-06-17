"""from_spec torture: every documented layout, tokens via preset + inline +
overrides, multiple slide sizes, transitions in-spec, and lint='raise'.
"""

from __future__ import annotations

from _util import save

from power_pptx.compose import from_spec


def build():
    spec = {
        "slide_size": "16:9",
        "tokens": {
            "preset": "modern_light",
            "overrides": {"palette": {"accent": "#FF6600"}},
        },
        "lint": "raise",
        "slides": [
            {
                "layout": "title",
                "title": "Stress Test: from_spec",
                "subtitle": "Exercising every declarative layout",
                "transition": "morph",
            },
            {
                "layout": "kpi",
                "title": "Run-rate metrics",
                "kpis": [
                    {"label": "ARR", "value": "$182M", "delta": +0.27},
                    {"label": "NDR", "value": "131%", "delta": +0.03},
                    {"label": "CAC payback", "value": "8 mo", "delta": -0.10},
                    {"label": "Gross margin", "value": "82%", "delta": +0.02},
                ],
                "transition": "fade",
            },
            {
                "layout": "bullets",
                "title": "Customer impact",
                "bullets": [
                    "Two flagship customers shipped this week.",
                    "NPS improved 8 points QoQ.",
                    "EU expansion ahead of plan.",
                    "Churn down to a record low across all segments.",
                ],
            },
            {
                "layout": "quote",
                "quote": "The new dashboards saved my team a week per sprint.",
                "attribution": "Director of Engineering, Flagship Customer",
            },
        ],
    }
    prs = from_spec(spec)

    return prs


if __name__ == "__main__":
    save(build(), "08_from_spec_torture.pptx")
