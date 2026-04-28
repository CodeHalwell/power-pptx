# Animations (Phase 5)

`pptx.animation` ships a preset-only API that maps directly onto
PowerPoint's built-in animation library. All generated XML is valid
OOXML and round-trips through PowerPoint without loss.

## Imports

```python
from pptx.animation import Entrance, Exit, Emphasis, MotionPath, Trigger
from pptx.util import Inches, Pt
```

`Trigger` is an alias for `pptx.enum.animation.PP_ANIM_TRIGGER`.

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
Entrance.wipe(slide, shape)
Entrance.zoom(slide, shape)
Entrance.wheel(slide, shape)
Entrance.random_bars(slide, shape)
```

## Exit presets

```python
Exit.disappear(slide, shape)
Exit.fade(slide, shape)
Exit.fly_out(slide, shape)
Exit.float_out(slide, shape)
Exit.wipe(slide, shape)
Exit.zoom(slide, shape)
```

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
to `Trigger.AFTER_PREVIOUS`.

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

# Pass a raw OOXML motion-path expression
MotionPath.custom(slide, shape, "M 0 0 L 0.5 0.5 L 1 0")
```

All preset constructors normalise EMU inputs against the slide
dimensions before emitting the path attribute, so the *absolute* travel
distance is preserved across slide sizes.

## Round-trip safety

Animations authored in PowerPoint survive a read–modify–write cycle.
Generated effects are appended to the existing `<p:tnLst>` timing tree
without touching pre-existing `<p:par>` nodes:

```python
prs = Presentation("hand-authored.pptx")
slide = prs.slides[0]
Entrance.fade(slide, slide.shapes[0])           # adds, doesn't disturb
prs.save("with-extra-fade.pptx")
```

## End-to-end example

```python
from pptx import Presentation
from pptx.animation import Entrance, Emphasis, MotionPath, Trigger
from pptx.util import Inches

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
