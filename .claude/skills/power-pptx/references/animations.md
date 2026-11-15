# Animations (Phase 5)

`power_pptx.animation` ships a preset-only API that maps directly onto
PowerPoint's built-in animation library. The XML it generates is valid
against the OOXML schema, survives a save → open → save cycle with this
library, and imports into LibreOffice as the effect each preset names.

> **Experimental.** That is a guarantee about the file, not about
> playback in Microsoft PowerPoint, which has not been verified: it has
> been reported to show animated shapes faint and then snap them into
> view instead of playing the effect (see the `power_pptx.animation`
> module docstring). Prefer slide transitions where they serve, and check
> any animated deck in PowerPoint itself before relying on it.

## Imports

```python
from power_pptx.animation import Entrance, Exit, Emphasis, MotionPath, Trigger
from power_pptx.util import Inches, Pt
```

`Trigger` is an alias for `power_pptx.enum.animation.PP_ANIM_TRIGGER`.

## Triggers and delay

Every preset accepts an optional `trigger` and `delay` (milliseconds):

```python
Entrance.fade(slide, shape)                                    # default: ON_CLICK
Entrance.fly_in(slide, shape, trigger=Trigger.WITH_PREVIOUS)
Entrance.zoom(slide, shape, trigger=Trigger.AFTER_PREVIOUS, delay=500)
```

## Entrance presets

```python
Entrance.appear(slide, shape)
Entrance.fade(slide, shape)
Entrance.fly_in(slide, shape, direction="bottom")  # also "top", "left", "right"
Entrance.float_in(slide, shape)
Entrance.wipe(slide, shape, direction="left")      # also "right", "top", "bottom"
Entrance.zoom(slide, shape)
Entrance.wheel(slide, shape)
Entrance.random_bars(slide, shape)
```

## Exit presets

```python
Exit.disappear(slide, shape)
Exit.fade(slide, shape)
Exit.fly_out(slide, shape, direction="bottom")     # the edge it leaves by
Exit.float_out(slide, shape)
Exit.wipe(slide, shape, direction="left")
Exit.zoom(slide, shape)
Exit.wheel(slide, shape)
Exit.random_bars(slide, shape)
```

`direction` is one of `"bottom"`, `"top"`, `"left"`, `"right"` for the
presets that have one (fly in/out, wipe); anything else raises
`ValueError`. Presets without a direction ignore it.

## Emphasis presets

```python
Emphasis.pulse(slide, shape)
Emphasis.spin(slide, shape)
Emphasis.teeter(slide, shape)
```

## Per-paragraph reveal

Reveal a text frame one paragraph at a time, fired by a single click:

```python
body = slide.placeholders[1].text_frame
Entrance.fade(slide, body, by_paragraph=True)
```

Supported presets for `by_paragraph=True`: `appear`, `fade`, `wipe`,
`zoom`, `wheel`, `random_bars`. The first paragraph fires on the
caller-supplied trigger (or `ON_CLICK`); subsequent paragraphs default
to `Trigger.AFTER_PREVIOUS`. `direction` (for `wipe`) and `easing`
apply to every paragraph.

## Sequencing — chain effects from one click

```python
with slide.animations.sequence():
    Entrance.fade(slide, title_shape)
    Entrance.fly_in(slide, body_shape)
    Emphasis.pulse(slide, badge_shape)
```

Inside the `with` block:
- The first effect fires on `Trigger.ON_CLICK` (or whatever `start=` is
  passed to `sequence(start=...)`).
- Every subsequent effect defaults to `Trigger.AFTER_PREVIOUS`.
- Explicit per-call triggers still win.

Sequences cannot be nested.

## Grouping — animate sub-shapes as one cluster

`group()` is the right primitive for "this card / row / panel made of
several sub-shapes should animate as one visual unit." Inside the
block, the first effect uses the group's `start` trigger and every
subsequent effect defaults to `Trigger.WITH_PREVIOUS`:

```python
for i, card in enumerate(cards):
    with slide.animations.group(delay=0 if i == 0 else 200):
        Entrance.fade(slide, card.body)
        Entrance.fade(slide, card.title)
        Entrance.fade(slide, card.blurb)
```

This produces one `AFTER_PREVIOUS` start plus N-1 `WITH_PREVIOUS`
followers per card — much cheaper for PowerPoint to render than the
same number of independent click-groups, and dramatically reduces the
"slide takes a beat to appear" lag on dense decks.

Use `group()` for sub-shape clusters; use `sequence()` for cluster-to-
cluster chains. They can't be combined.

## Inspecting and clearing animations

`SlideAnimations` is iterable and supports `len()`. It lists every
effect on the slide, including those authored in PowerPoint (which nests
them inside its main sequence):

```python
print(len(slide.animations))                  # how many entries?
for entry in slide.animations:
    print(entry.kind, entry.preset, entry.trigger,
          "shape=", entry.shape.name if entry.shape else None,
          "duration=", entry.duration, "delay=", entry.delay)
```

Each entry is a read-only `AnimationEntry`. To remove the entry from
the slide call `entry.remove()`; to wipe the whole slide call
`slide.animations.clear()` (returns the count of entries removed).

`slide.animations.purge_orphans()` is the narrower cousin — it only
removes what names a shape no longer on the slide: effects, the play
controls of a deleted movie, a sequence triggered by clicking it, and its
build-list entry. `shape.delete()` and `group.ungroup()` run it for you.

## Motion paths

```python
MotionPath.line(slide, shape, dx=Inches(2), dy=Inches(1))
MotionPath.diagonal(slide, shape, dx=Inches(3), dy=Inches(2))
MotionPath.circle(slide, shape, radius=Inches(1), clockwise=True)
MotionPath.arc(slide, shape, dx=Inches(3), dy=Inches(0), height=0.4)
MotionPath.zigzag(slide, shape, dx=Inches(4), dy=Inches(0),
                  segments=6, amplitude=0.2)
MotionPath.spiral(slide, shape, radius=Inches(2),
                  turns=2.5, clockwise=True)

# Pass a raw OOXML motion-path expression; `E` ends the path
MotionPath.custom(slide, shape, "M 0 0 L 0.5 0.5 L 1 0 E")

# Or an SVG path, mapped from its viewbox onto the slide
MotionPath.svg(slide, shape, "M 0 0 H 100 V 50", viewbox=(0, 0, 200, 100))
```

All preset constructors normalise EMU inputs against the slide
dimensions before emitting the path attribute, so the *absolute* travel
distance is preserved across slide sizes.

A raw motion path knows five commands: `M` (move to), `L` (line to),
`C` (cubic curve to), `Z` (close the loop) and `E` (end), in lower case
for coordinates relative to the current point. Coordinates are
fractions of the slide: `(0, 0)` is where the shape starts, `(1, 0)`
one slide width to its right. `custom` adds the closing `E` if you
leave it out and raises `ValueError` for anything that is not such a
path. `svg` accepts the wider SVG set (`M L H V C Q Z`, either case)
and converts it; arcs (`A`) and smooth curves (`S`, `T`) are not
supported and raise `ValueError`.

## Round-trip safety

Animations authored in PowerPoint survive a read–modify–write cycle.
Generated effects are appended after the existing ones without touching
them; on a slide PowerPoint animated, they go into its main sequence,
nested the way PowerPoint nests its own:

```python
prs = Presentation("hand-authored.pptx")
slide = prs.slides[0]
Entrance.fade(slide, slide.shapes[0])           # adds, doesn't disturb
prs.save("with-extra-fade.pptx")
```

## End-to-end example

```python
from power_pptx import Presentation
from power_pptx.animation import Entrance, Emphasis, MotionPath, Trigger
from power_pptx.util import Inches

prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[5])
slide.shapes.title.text = "Animated demo"

box = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(1))
box.text_frame.text = "Click anywhere to animate"

# A 3-step click-driven sequence
with slide.animations.sequence():
    Entrance.fade(slide, slide.shapes.title)
    Entrance.fly_in(slide, box, direction="left")
    Emphasis.pulse(slide, box)

# Extra effect after the sequence: a motion path on the box
MotionPath.arc(slide, box, dx=Inches(2), dy=Inches(0), height=0.3,
               trigger=Trigger.AFTER_PREVIOUS)

prs.save("animated.pptx")
```
