# HTML as a slide design reference

This example builds two versions of the same styled two-slide document:

- `html-captured.pptx` captures each HTML section as a picture, with its
  visible text preserved in notes and alt text.
- `native-hybrid.pptx` explicitly recreates the design using editable
  text and cards, with the diagram embedded as a native SVG picture.
  It demonstrates an agent's reconstruction workflow, not automatic CSS conversion.

```bash
pip install -e '.[embedding]'
python -m playwright install chromium
python examples/html_embedding/build.py
# Or select an installed browser:
python examples/html_embedding/build.py --browser-path /usr/bin/chromium
```

Outputs are written to `_out/`, including the HTML reference PNGs. The
source uses a 1280 × 720 canvas, local CSS and a relative SVG asset.
It needs no remote fonts, CDN stylesheets or external images.

Compare the reference PNGs to rendered PowerPoint thumbnails. In the
native companion, headings, body copy and cards can be edited; the SVG is
one vector picture. In the captured deck, each slide is one static picture.
The full workflow guide is in the bundled skill's
`references/content-embedding.md`.
