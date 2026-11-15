# Slide thumbnails (Phase 10)

For a complete review bundle, prefer `power-pptx review deck.pptx --out-dir review`.
It produces PDF, all slide PNGs, contact sheets, validation, optional reference
differences, and a local gallery. Batch inputs are supported. Read
`authoring-workflows.md` for setup, options, and the required visual inspection.

`power_pptx.render` shells out to LibreOffice to rasterise slides as PNGs.
This is for review tooling, dashboards, and CI artifacts — it does not
require Microsoft PowerPoint or an Office license, but `soffice` must
be on `$PATH` (or you can point at a custom binary).

Each call converts in a private workspace with its own LibreOffice profile.
It is safe to reuse `out_dir`: returned paths contain only the current
render's requested slides, even when the new deck has fewer slides. Existing
unrelated files are preserved; PNGs with the same output names are replaced.
The saved input deck, intermediate PDF, and profile are removed after the
call. `return_bytes=True` returns bytes without writing to `out_dir`.

Hidden slides (`<p:sld show="0">`) are rendered like any other, so
`slide_indexes=[n]` always means `prs.slides[n]`, and `power-pptx review`
covers them too. This needs LibreOffice 7.4 or later; an older build
renders the visible slides and raises `ThumbnailRendererError` for a hidden
one you ask for.

## Convenience methods

```python
# All slides → ./thumbs/_render_input-page-<n>.png (n counts from 1)
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
    dpi=150,                                               # the default
)

png = render_slide_thumbnail(slide, return_bytes=True)
```

### Resolution, strategy and file names

`dpi=` sets the resolution (default 150, so a 10in-wide slide is 1500px
wide). `render_slides(scale=...)` is the same knob in PDF units: `scale=1.0`
is 72 DPI, `scale=2` is 144, and it overrides `dpi=`. Both apply to every
deck, one-slide decks included.

`strategy="auto"` (the default) exports a PDF and splits it into pages with
`pdftoppm` (Poppler) or, failing that, `pypdfium2`. Only when neither is
installed does it use LibreOffice's direct PNG filter, which ignores `dpi=`
and, on stock LibreOffice 7+, writes just the first slide, so it serves
one-slide decks only. `strategy="pdf"` and `strategy="png"` force one path.

Files are named `_render_input-page-<n>.png`, where `<n>` is the slide number
counting from 1, zero-padded to the width of the slide count (`-page-07` in
a 12-slide deck), whichever path rendered them. For names of your own use
`render_slides(prs, out_dir="thumbs", name_template="slide-{:02d}.png")`
(that index counts from 0).

### Fonts that aren't in a system folder

```python
from power_pptx.render import render_slides

render_slides(prs, out_dir="thumbs", font_dirs=["assets/fonts"])
```

`font_dirs=` (on `render_slides`, `render_slide_thumbnails` and
`render_slide_thumbnail`) writes a temporary `fonts.conf` that includes the
system configuration, the OS font folders and the given folders. It sets
`FONTCONFIG_FILE` for the `soffice` subprocess only. Folders registered with
`power_pptx.text.register_font_dir` or `POWER_PPTX_FONT_DIRS`, and the files
registered with `register_font_family`, are always passed through. Use it when previews show a serif fallback although the PPTX
names the right font. On macOS that happens to fonts in `~/Library/Fonts`,
because LibreOffice's bundled fontconfig doesn't search there. Confirm with
`pdffonts` on the intermediate PDF.

There's no `width=` knob. For an exact pixel size, pick the `dpi=` that
gives it (`dpi = pixels / slide width in inches`) or post-process with
Pillow (``Image.open(...).resize(...)``).

## Pointing at a custom binary

Three ways to choose `soffice`, in priority order:

1. The `soffice_bin=` keyword argument
2. The `POWER_PPTX_SOFFICE` environment variable
3. The first `soffice` on `$PATH`, or else the first `libreoffice`

A binary named through the first two is used as given: if it can't be found,
`ThumbnailRendererUnavailable` is raised without falling back to `$PATH`.

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

`timeout=` (seconds, default 120) applies to the LibreOffice conversion and
to the PDF split separately. A step that overruns is stopped, together with
the worker processes LibreOffice started, before the error is raised.

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
