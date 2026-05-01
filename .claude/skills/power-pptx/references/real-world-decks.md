# Real-world deck patterns

The repo's `examples/real_world/` directory ships ten end-to-end
Fortune-500-style decks that exercise the design / charts / lint
paths together. They're the practical "what good looks like"
reference and the combined smoke test for the surface.

## How to look at them

Each script is self-contained — `python 01_q4_earnings_review.py`
emits a `.pptx` next to it. `build_all.py` runs every one in series
(useful as a CI gate). `_brand.py` and `_common.py` hold the shared
tokens / typography / chart palette so each demo deck stays focused
on layout choices.

## What each deck demonstrates

| Deck | Patterns |
|---|---|
| `01_q4_earnings_review.py` | Cover, KPI dashboard with deltas, table with conditional row colours, charts with palette, executive summary callouts. |
| `02_annual_strategic_plan.py` | Multi-stage roadmap timeline, three-pillar layout, "Goals → Initiatives → KPIs" tree. |
| `03_product_launch.py` | Hero slide with overlay caption, feature cards with icons, before/after comparison. |
| `04_investor_pitch.py` | Cover with logo, market-size waterfall, traction line chart, team bios with circular crops. |
| `05_cybersecurity_briefing.py` | Threat-level dashboard, redacted bullet lists, callout blocks with severity colours. |
| `06_sales_qbr.py` | Quota attainment table with conditional fills, top-deals list, win/loss column chart. |
| `07_acquisition_proposal.py` | Two-column comparison tables, valuation waterfall, financial KPI deltas. |
| `08_operational_excellence.py` | Process-flow diagram (shapes + arrows), defect-rate chart, before/after metric cards. |
| `09_talent_strategy.py` | Funnel chart, headcount pyramid, OKR cards. |
| `10_marketing_campaign.py` | Campaign timeline, attribution donut, channel-mix stacked bar. |

## What they don't demonstrate

- **Animations.** All `Entrance.*` calls have been stripped from the
  example suite because of the playback bug (see `animations.md`).
  Don't bring them back when borrowing from these decks.
- **Direct shape XML manipulation.** The decks compose entirely
  through the high-level API; if you need raw `<a:xyz>` editing,
  reach for `references/effects.md` and the ``element`` accessor on a
  shape.

## Useful idioms in the example suite

- **Card stacks** — `slide.lint_group_overlaps(card, accent_bar,
  label, value)` tags an intentional layered group in one call.
- **Branded fonts** — `tf.set_paragraph_defaults(font_name=...,
  size=Pt(...), color="#222222")` after `tf.text = ...` instead of
  looping over runs.
- **Charts** — `chart = slide.shapes.add_chart(...).chart` then
  `chart.shape.left = ...` to position the parent graphic-frame.
- **Lint-or-die** — every script ends with `prs.lint().auto_fix()`
  before save; the examples are the proof that the linter and fixer
  are accurate enough for production decks.
