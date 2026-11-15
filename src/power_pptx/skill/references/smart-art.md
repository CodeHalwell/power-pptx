# SmartArt text substitution (Phase 8)

Full SmartArt creation is intentionally **out of scope** — the layout
algorithms are proprietary and non-trivial to reverse-engineer.

What `power-pptx` *does* support is text substitution inside an
*existing* template's SmartArt. The classic use case: a corporate
org-chart template whose names need refreshing every quarter.

## Iterating SmartArt on a slide

```python
prs = Presentation("org-chart-template.pptx")
slide = prs.slides[0]

for sa in slide.smart_art:
    print("nodes:", sa.texts)
```

`slide.smart_art` is a `SmartArtCollection`. Each item is a
`SmartArtShape` with:

- `texts` — ordered list of node text strings
- `set_text(values, *, strict=True)` — replaces node text in document
  order without touching layout, style, or color parts

Both work on diagrams as PowerPoint saves them, where content nodes
carry no `type` attribute (it defaults to `node`). A node nobody has
typed into yet (it shows a `[Text]` prompt) reads as `""` and can be
given text like any other.

## Replacing names

```python
slide.smart_art[0].set_text(["Alex", "Priya", "Sam", "Lin", "Jordan"])
```

By default `set_text` is `strict=True` and raises if `len(values)`
doesn't match the number of nodes in the diagram. Pass
`strict=False` to truncate / pad with the existing text instead:

```python
slide.smart_art[0].set_text(["Alex", "Priya"], strict=False)
```

## Round-trip

`DiagramDataPart` and its sibling part classes are registered so the
SmartArt `diagrams/data#.xml`, `layout#`, `quickStyle#`, and `colors#`
parts are handled as typed `XmlPart` subclasses. Reads never mutate.

## The cached drawing

PowerPoint 2010+ also saves `diagrams/drawing#.xml`, a cache of the
shapes the diagram was last laid out as. Viewers display that cache
(LibreOffice always does), so `set_text` replaces the text there too
— otherwise the old names would still show. The cached shapes keep
their size and font size, which were fitted to the old text; PowerPoint
re-fits them the next time the diagram is edited. Keep replacement
text close in length to what it replaces, and render the slide to
check the fit when it matters.

## What this is not

- **No creation.** You can't build a new SmartArt graphic from
  scratch. Author it in PowerPoint as a template, then use this API to
  refresh it.
- **No structural edits.** Adding/removing nodes is not supported. The
  list you pass to `set_text` must align with the existing nodes.
- **No styling changes.** Color and quick-style parts are left alone.

## End-to-end: refresh a quarterly org chart

```python
from power_pptx import Presentation

prs = Presentation("org-chart-template.pptx")
slide = prs.slides[0]

names = [
    "Alex Halwell",       # CEO
    "Priya Shah",         # COO
    "Sam Tucker",         # CFO
    "Lin Chen",           # CTO
    "Jordan Reyes",       # CRO
    "Morgan Patel",       # CMO
]
slide.smart_art[0].set_text(names)

prs.save("org-chart-2026q2.pptx")
```
