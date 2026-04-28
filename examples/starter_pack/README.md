# power-pptx starter pack

Three opinionated `DesignTokens` sets that drop straight into the
`pptx.design.recipes` slide constructors. Pick the one closest to what
you want, copy it into your project, and tweak the palette or
typography to taste.

| Set       | Mood                            | Typography         |
|-----------|---------------------------------|--------------------|
| Modern    | Vivid indigo, soft surfaces     | Inter, sans, big   |
| Classic   | Navy + warm grey, conservative  | Cambria + Calibri  |
| Editorial | High-contrast charcoal & accent | Playfair + Source  |

## Using a token set

```python
from pptx import Presentation
from pptx.design.recipes import title_slide, bullet_slide, kpi_slide

# Pick whichever set fits the brief.
from examples.starter_pack.modern import TOKENS

prs = Presentation()
title_slide(prs, title="Q4 Review", subtitle="April 2026",
             tokens=TOKENS, transition="morph")
bullet_slide(prs, title="Highlights",
              bullets=["Two flagships shipped.", "NPS +8 QoQ."],
              tokens=TOKENS)
kpi_slide(prs, title="Run-rate metrics",
           kpis=[{"label": "ARR", "value": "$182M", "delta": +0.27},
                 {"label": "NDR", "value": "131%",  "delta": +0.03}],
           tokens=TOKENS)
prs.save("review.pptx")
```

Each module exposes a `TOKENS` constant (a fully-built
`DesignTokens` object) and the raw `SPEC` dict it was built from, so you
can dump it to YAML or JSON and edit by hand.

## Generating preview decks

`build_preview.py` produces one `.pptx` per token set so you can compare
them side-by-side:

```bash
python examples/starter_pack/build_preview.py
```

The decks land in `examples/starter_pack/_out/`.
