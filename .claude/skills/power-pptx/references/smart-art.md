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

The nodes are the diagram's content nodes: every `dgm:pt` point whose
`type` is `node` or `asst`, **or that has no `type` at all** — the
schema default is `node`, and PowerPoint leaves the attribute off
ordinary content nodes, so a diagram saved by PowerPoint has no
`type="node"` anywhere. The structural points (`doc`, `pres`,
`parTrans`, `sibTrans`) are never nodes, whatever text they carry.

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

A node PowerPoint shows as `[Text]` (an empty placeholder) holds an empty
paragraph; `set_text` writes into that paragraph, so the text lands on
the first line. It also clears the node's `phldr` placeholder flag, which
the nodes of a PowerPoint-saved diagram that hold text do not carry.

## Thumbnails and other renderers: the cached drawing

PowerPoint saves each diagram twice: the data model
(`ppt/diagrams/data#.xml`) and a laid-out copy of it
(`ppt/diagrams/drawing#.xml`). PowerPoint lays the diagram out afresh from
the data model, so editing the model is enough for it. LibreOffice,
Keynote and Google Slides draw the **cached copy** instead, so a
`render_thumbnails()` of a diagram whose data model alone was edited
still shows the old text.

`set_text` therefore updates the text in the cached drawing too. It finds
a cached shape through the data model's `presOf` connections (the shapes
are keyed by *presentation* point, not by node) and rewrites its
paragraph, keeping the cached run formatting; an empty cached paragraph
gets a run that inherits the cached size.

What it does **not** do: the cached shapes keep their size and position,
so a much longer string is not re-fitted in LibreOffice (PowerPoint
re-fits on open); and a cached shape that does not unambiguously show the
changed nodes (a different number of paragraphs than nodes feeding it,
or text that no longer matches the data model) is left as it is rather
than guessed at. A deck without a cached drawing part works as before.

## Round-trip

`DiagramDataPart` and its sibling part classes are registered so the
SmartArt `diagrams/data#.xml`, `layout#`, `quickStyle#`, and `colors#`
parts are handled as typed `XmlPart` subclasses. Reads never mutate. The
cached `drawing#.xml` is carried as an opaque part and only touched by
`set_text`, as above.

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
    "Alex Halwell",  # CEO
    "Priya Shah",  # COO
    "Sam Tucker",  # CFO
    "Lin Chen",  # CTO
    "Jordan Reyes",  # CRO
    "Morgan Patel",  # CMO
]
slide.smart_art[0].set_text(names)

prs.save("org-chart-2026q2.pptx")
```
