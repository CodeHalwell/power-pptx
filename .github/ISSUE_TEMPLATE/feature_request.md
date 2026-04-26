---
name: Feature request
about: Propose a new public API or enhancement
labels: enhancement
---

## Summary

One or two sentences describing the feature.

## Motivation

Why do you need this? What problem does it solve? Include the use-case or
workflow this would unblock.

## Proposed API

Show what the ideal calling code would look like:

```python
from pptx import Presentation

prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[6])

# proposed usage
slide.some_new_method(...)
```

## Alternatives considered

Any workarounds you've tried, or alternative API shapes you considered.

## Checklist

- [ ] I've checked the [roadmap](../../ROADMAP.md) and this isn't already
  planned for a specific phase.
- [ ] I'm willing to open a draft PR once the design is agreed.
