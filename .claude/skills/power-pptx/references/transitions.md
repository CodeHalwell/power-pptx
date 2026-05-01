# Slide transitions (Phase 4)

> ℹ️ **Per-slide overrides are preserved across `set_transition`**
>
> As of 2.5, `prs.set_transition(kind=…)` skips slides that already
> have an explicit per-slide transition kind, instead of silently
> overwriting them. Either order now works — set the per-slide
> override before *or* after the deck-wide call:
>
> ```python
> slide1.transition.kind = MSO_TRANSITION_TYPE.MORPH       # before
> prs.set_transition(MSO_TRANSITION_TYPE.FADE)             # leaves slide1 alone
>
> # Or:
> prs.set_transition(MSO_TRANSITION_TYPE.FADE)             # default for the deck
> slide1.transition.kind = MSO_TRANSITION_TYPE.MORPH       # after — also fine
> ```
>
> Pass `force=True` to restore the old "force every slide" behaviour:
> `prs.set_transition(MSO_TRANSITION_TYPE.FADE, force=True)`.

Each slide exposes a `transition` proxy backed by `<p:transition>`.
Reads on an unset transition return `None` and never mutate XML,
keeping theme inheritance intact.

## Per-slide

```python
from power_pptx.enum.presentation import MSO_TRANSITION_TYPE

slide.transition.kind             = MSO_TRANSITION_TYPE.MORPH
slide.transition.duration         = 1500          # milliseconds
slide.transition.advance_on_click = True
slide.transition.advance_after    = 5000          # 5-second auto-advance
```

To remove a transition entirely:

```python
slide.transition.clear()
```

Reads without explicit settings:

```python
if slide.transition.kind is None:
    print("inherits from theme")
```

## Supported kinds

`MSO_TRANSITION_TYPE` covers 25+ kinds including Office 2010+
extension transitions on the `p14:` namespace:

- Classics: `FADE`, `PUSH`, `WIPE`, `SPLIT`, `REVEAL`, `RANDOM_BARS`,
  `SHAPE`, `UNCOVER`, `COVER`, `CUT`, `DISSOLVE`, `ZOOM`
- Office 2010+ (p14): `MORPH`, `VORTEX`, `CONVEYOR`, `SWITCH`,
  `GALLERY`, `FLY_THROUGH`, `RIPPLE`, `HONEYCOMB`, `GLITTER`, `ORBIT`,
  `PAN`, `WARP`, `WIND`

Direction modifiers (`fromLeft`, `fromTop`, etc.) are not yet
exposed by the high-level API — they round-trip but you have to set
them through the underlying element.

## Deck-wide helper

`Presentation.set_transition(...)` applies the same transition (or a
partial update) to every slide in one call. Unspecified kwargs leave
each slide's existing setting untouched:

```python
prs.set_transition(kind=MSO_TRANSITION_TYPE.FADE, duration=750)

# Bump the duration on every slide without changing the kind
prs.set_transition(duration=1200)

# Turn on auto-advance everywhere without disturbing kind or duration
prs.set_transition(advance_on_click=True, advance_after=8000)

# Remove the transition element on every slide
prs.set_transition(kind=None)
```

## End-to-end example

```python
from power_pptx import Presentation
from power_pptx.enum.presentation import MSO_TRANSITION_TYPE
from power_pptx.util import Inches

prs = Presentation()

# Slide 1 — title
slide1 = prs.slides.add_slide(prs.slide_layouts[0])
slide1.shapes.title.text = "Q4 Review"
slide1.placeholders[1].text = "April 2026"

# Slide 2 — content
slide2 = prs.slides.add_slide(prs.slide_layouts[5])
slide2.shapes.title.text = "Run-rate metrics"

# Use Morph between the two title slides
slide1.transition.kind     = MSO_TRANSITION_TYPE.MORPH
slide1.transition.duration = 1500

# Default everything else to a quick fade.  set_transition skips
# slides with an explicit kind by default, so slide1's MORPH is
# preserved.  Pass force=True if you ever want to clobber per-slide
# kinds.
prs.set_transition(kind=MSO_TRANSITION_TYPE.FADE, duration=400)

prs.save("with-transitions.pptx")
```
