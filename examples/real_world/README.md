# Real-world example decks

Ten end-to-end PowerPoint presentations of the kind you'd actually
deliver inside a Fortune 500 company — built entirely with
`power-pptx`. Each script is self-contained, lints before save, and
produces a deck that holds up next to a hand-crafted one.

| # | Script | Audience | Slides |
|---|---|---|---|
| 01 | `01_q4_earnings_review.py`     | Investor relations / audit committee   | 11 |
| 02 | `02_annual_strategic_plan.py`  | Executive committee                     | 10 |
| 03 | `03_product_launch.py`         | Field, partners, analysts (launch day)  | 10 |
| 04 | `04_investor_pitch.py`         | Series-D institutional investors        | 11 |
| 05 | `05_cybersecurity_briefing.py` | Board risk & audit committee            |  9 |
| 06 | `06_sales_qbr.py`              | CRO + senior sales staff (quarterly)    | 10 |
| 07 | `07_acquisition_proposal.py`   | M&A committee                           | 10 |
| 08 | `08_operational_excellence.py` | COO staff + business-unit GMs           | 10 |
| 09 | `09_talent_strategy.py`        | Executive committee (annual)            | 10 |
| 10 | `10_marketing_campaign.py`     | Executive committee (budget approval)   | 10 |

Each deck has its own brand identity — palette and typography drawn
from `_brand.py` — so the suite shows how a single token spec drives
every recipe and chart palette across very different verticals.

## Build everything

```bash
pip install -e .
python examples/real_world/build_all.py
```

Outputs land in `examples/real_world/_out/`.

## Build a single deck

Each script is independently runnable:

```bash
python examples/real_world/01_q4_earnings_review.py
python examples/real_world/04_investor_pitch.py
# ...
```

## What each deck demonstrates

Every deck uses the lint-or-die pattern and the design-system layer.
The scripts also show off feature areas that map to specific
chapters of the user guide:

- **Recipes** — `title_slide`, `kpi_slide`, `bullet_slide`,
  `quote_slide` are used in every deck for cover, KPI dashboards,
  and pull-quote moments.
- **`fit_text` + `auto_size`** — section titles, big-idea cover
  text, and pricing cards lean on the space-aware authoring stack
  so long copy never overflows.
- **Charts** — column, bar, line, and pie charts with custom
  palettes, per-data-point coloring, gradient series fills, and
  quick-layout presets.
- **Tables** — every deck uses at least one table with custom
  header fills, alternating row stripes, conditional cell coloring
  for status / delta columns, and `Cell.borders` for separators.
- **Visual effects** — shadow, gradient fills, alpha-tinted glass
  cards on cover and closing slides.
- **Transitions** — deck-wide fade with a per-slide Morph
  override on the "Introducing Atlas" and "Big idea" reveal slides
  in the product launch and marketing campaign decks. Entrance
  animations are intentionally not exercised here — they are still
  experimental and may not play correctly in PowerPoint.

## Files

- `_brand.py` — ten distinct token sets (palette + typography +
  shadows + spacings) — one per deck.
- `_common.py` — shared helpers: `cover_slide`, `closing_slide`,
  `section_title`, `eyebrow`, `divider`, `footer`,
  `styled_card`, `lint_or_die`, etc.
- `build_all.py` — builds every script in sequence.
- `01_*.py` … `10_*.py` — the ten decks.

## Notes on the content

The numbers, customer names, deal codes, and people in these decks
are all fictional. The shape of the content — what slides go in a
QBR, how an M&A committee deck is organised, what sits in a CISO
board briefing — is drawn from the conventions you'll find at most
mature Fortune 500 companies. Treat them as templates, not data.
