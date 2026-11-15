# Slide transitions (Phase 4)

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

`kind` also reads `None` for a transition PowerPoint wrote that has no
`MSO_TRANSITION_TYPE` member, such as the PowerPoint 2013 kinds
(Airplane, Curtains, Origami, Wind, …). Such a transition is left
exactly as it was read when the deck is saved, unless you change it.

`kind = MSO_TRANSITION_TYPE.NONE` asks for no transition explicitly.
Assigning `None` to the last remaining timing setting removes the
transition element instead of leaving an empty one behind.

## Supported kinds

`MSO_TRANSITION_TYPE` has these members (besides `NONE`):

- ISO standard (`p:`): `BLINDS`, `CHECKER`, `CIRCLE`, `COMB`, `COVER`,
  `CUT`, `DIAMOND`, `DISSOLVE`, `FADE`, `NEWSFLASH`, `PLUS`, `PULL`,
  `PUSH`, `RANDOM`, `RANDOM_BAR`, `SPLIT`, `STRIPS`, `WEDGE`, `WHEEL`,
  `WIPE`, `ZOOM`
- PowerPoint 2010 (`p14:`): `CONVEYOR`, `FLY_THROUGH`, `GALLERY`,
  `SWITCH`, `VORTEX`
- PowerPoint 2016 (`p159:`): `MORPH`

PowerPoint's gallery names some of these differently: its *Uncover* is
`PULL`, and its *Shape* is `CIRCLE`, `DIAMOND` or `PLUS`. Other
PowerPoint 2010+ kinds (Ripple, Honeycomb, Glitter, Pan, Prism, …) and
the PowerPoint 2013 kinds have no member; a deck that uses them keeps
them, but they cannot be set from this API.

Extension kinds (and a `duration`, which is a PowerPoint 2010
attribute) are written inside `mc:AlternateContent` with a plain
fallback, which is what PowerPoint itself does.

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

When `kind` is given, a slide that already has a kind of its own keeps
it (pass `force=True` to overwrite it too). A slide whose transition
only carries timing settings, from an earlier call like the
auto-advance one above, has no kind yet and does get the new one.

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

# Default everything else to a quick fade. slide1 keeps its Morph: a
# deck-wide kind only goes to slides without one (unless force=True).
# `duration` does apply to every slide, so set slide1's own afterwards.
prs.set_transition(kind=MSO_TRANSITION_TYPE.FADE, duration=400)
slide1.transition.duration = 1500

prs.save("with-transitions.pptx")
```
