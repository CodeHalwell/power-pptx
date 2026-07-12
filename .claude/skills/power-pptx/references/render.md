# Slide thumbnails (Phase 10)

`power_pptx.render` shells out to LibreOffice to rasterise slides as PNGs.
This is for review tooling, dashboards, and CI artifacts — it does not
require Microsoft PowerPoint or an Office license, but `soffice` must
be on `$PATH` (or you can point at a custom binary).

## Convenience methods

```python
# All slides → ./thumbs/<n>.png
paths = prs.render_thumbnails(out_dir="thumbs")

# Single slide as bytes
png = slide.render_thumbnail(return_bytes=True)

# Single slide written to a specific path
slide.render_thumbnail(out_path="cover.png")
```

## Module-level entry points

```python
from power_pptx.render import (
    render_slide_thumbnails,
    render_slide_thumbnail,
)

paths = render_slide_thumbnails(
    prs,
    out_dir="thumbs",
    slide_indexes=[0, 3, 7],                              # only these slides
    soffice_bin="/opt/libreoffice/program/soffice",
    timeout=60,                                            # seconds
)

png = render_slide_thumbnail(slide, return_bytes=True)
```

The output resolution is whatever LibreOffice's headless PNG
converter chooses — there's no `width=` knob. If you need a specific
size, post-process with Pillow (``Image.open(...).resize(...)``).

## Pointing at a custom binary

Three ways to choose `soffice`, in priority order:

1. The `soffice_bin=` keyword argument
2. The `POWER_PPTX_SOFFICE` environment variable
3. The first `soffice` (or `libreoffice`) on `$PATH`

```python
import os
os.environ["POWER_PPTX_SOFFICE"] = "/opt/libreoffice/program/soffice"
prs.render_thumbnails(out_dir="thumbs")
```

## Known limitations of the LibreOffice thumbnail path

The `soffice` + `pdftoppm` pipeline that backs `render_thumbnails`
renders most decks faithfully, but a few cross-renderer quirks are
worth knowing about — these show up in the thumbnail even when the
generated `.pptx` opens correctly in PowerPoint:

* **Emoji glyphs render as tofu** on systems without an emoji font
  installed (most Linux runtimes lack one by default). PowerPoint
  uses Segoe UI Emoji as a fallback; LibreOffice headless typically
  does not. For decks meant to be thumbnail-reviewed on the same
  machine, prefer Unicode glyphs from the shipped DejaVu families
  (`•`, `→`, `★`, `‹›`, `■`, etc.) over emoji codepoints.
* **Un-aligned text in fresh textboxes** renders centered instead of
  left-aligned. A textbox created via `slide.shapes.add_textbox(...)`
  has no `a:pPr/@algn` attribute; PowerPoint treats that as the
  OOXML default (left), LibreOffice as centered. Set
  `paragraph.alignment = PP_ALIGN.LEFT` explicitly to make
  thumbnails match how PowerPoint will render the slide.
* **`wrap="none" + spAutoFit` (the textbox default) re-centers under
  LibreOffice.** A fresh textbox has `<a:bodyPr wrap="none">
  <a:spAutoFit/></a:bodyPr>`. PowerPoint shrinks the box around the
  declared anchor; LibreOffice re-centers the shrunken box inside
  its original width, so a kicker line declared at
  `left=Inches(1.1), width=Inches(11)` renders near the middle of
  the slide rather than the left edge. Setting `tf.word_wrap = True`
  suppresses `spAutoFit` and keeps the declared geometry intact —
  fold it into every textbox in a recipe-style helper.

## Errors

```python
from power_pptx.render import (
    ThumbnailRendererUnavailable,
    ThumbnailRendererError,
)

try:
    paths = prs.render_thumbnails(out_dir="thumbs")
except ThumbnailRendererUnavailable as e:
    # soffice not on PATH — message includes an install hint
    print(e)
except ThumbnailRendererError as e:
    # soffice ran but produced no PNG / exited non-zero / timed out
    print(e)
```

## Patterns

### Generate review images for an HTML preview

```python
import base64

prs.save("deck.pptx")
images = []
for i in range(len(prs.slides)):
    png = prs.slides[i].render_thumbnail(return_bytes=True)
    images.append(base64.b64encode(png).decode("ascii"))

html = "\n".join(
    f'<img src="data:image/png;base64,{b64}" width="640">'
    for b64 in images
)
```

### CI artefacts

```python
# In tests/conftest.py or similar
from pathlib import Path

def attach_deck_thumbs(prs, out: Path):
    out.mkdir(exist_ok=True)
    return prs.render_thumbnails(out_dir=out)
```

### Skip on dev machines without LibreOffice

```python
import shutil
import pytest

requires_soffice = pytest.mark.skipif(
    shutil.which("soffice") is None and shutil.which("libreoffice") is None,
    reason="LibreOffice not installed",
)

@requires_soffice
def test_renders_thumbnails(tmp_path):
    prs = build_demo_deck()
    paths = prs.render_thumbnails(out_dir=tmp_path)
    assert len(paths) == len(prs.slides)
```
