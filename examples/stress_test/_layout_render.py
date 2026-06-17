"""Pillow layout renderer for reviewing deck geometry without LibreOffice.

Draws each slide's shapes to scale from their real EMU geometry: slide
background, solid/gradient fills, autoshape outlines, text, embedded pictures,
and labeled placeholders for charts/tables. This is a *layout* preview — it is
faithful for position/size/alignment/colour/overlap (the "are the backgrounds
and card boxes where I intended" review), not a PowerPoint-fidelity renderer.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from power_pptx import Presentation
from power_pptx.enum.shapes import MSO_SHAPE_TYPE

EMU = 914400


def _font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in paths:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _rgb(color_proxy):
    try:
        rgb = color_proxy.rgb
        return (rgb[0], rgb[1], rgb[2])
    except Exception:
        return None


def _fill_color(shape):
    """Best-effort (kind, data) for a shape fill."""
    try:
        f = shape.fill
        t = f.type
    except Exception:
        return ("none", None)
    if t is None:
        return ("none", None)
    name = getattr(t, "name", str(t))
    if name == "SOLID":
        c = _rgb(f.fore_color)
        return ("solid", c)
    if name == "GRADIENT":
        try:
            stops = [(s.position, _rgb(s.color)) for s in f.gradient_stops]
            stops = [(p, c) for p, c in stops if c]
            if len(stops) >= 2:
                return ("gradient", stops)
        except Exception:
            pass
        return ("solid", (200, 200, 210))
    if name == "PATTERNED":
        try:
            return ("solid", _rgb(f.fore_color) or (180, 180, 190))
        except Exception:
            return ("solid", (180, 180, 190))
    if name == "BACKGROUND":
        return ("none", None)
    return ("none", None)


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _draw_gradient(img, box, stops):
    x0, y0, x1, y1 = box
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    grad = Image.new("RGB", (w, h))
    px = grad.load()
    stops = sorted(stops)
    for yy in range(h):
        t = yy / max(1, h - 1)
        # find segment
        col = stops[-1][1]
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]
            p1, c1 = stops[i + 1]
            if p0 <= t <= p1:
                lt = (t - p0) / max(1e-6, (p1 - p0))
                col = _lerp(c0, c1, lt)
                break
        else:
            if t < stops[0][0]:
                col = stops[0][1]
        for xx in range(w):
            px[xx, yy] = col
    img.paste(grad, (x0, y0))


def _text_of(shape):
    try:
        if shape.has_text_frame and shape.text_frame.text.strip():
            return shape.text_frame.text.strip()
    except Exception:
        pass
    return ""


def _text_color(shape):
    try:
        p = shape.text_frame.paragraphs[0]
        # run-level colour wins (e.g. add_text / styled runs); fall back to
        # paragraph font colour, then a dark default.
        for run in p.runs:
            c = _rgb(run.font.color)
            if c:
                return c
        return _rgb(p.font.color) or (30, 30, 30)
    except Exception:
        return (30, 30, 30)


def render_slide(slide, prs, scale, idx):
    W = int(prs.slide_width / EMU * scale)
    H = int(prs.slide_height / EMU * scale)
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img, "RGBA")

    # slide background
    try:
        bg = slide.background
        kind, data = _fill_color_obj(bg.fill)
        if kind == "solid" and data:
            d.rectangle([0, 0, W, H], fill=data)
        elif kind == "gradient" and data:
            _draw_gradient(img, (0, 0, W, H), data)
    except Exception:
        pass

    def emu_box(shape, ox=0, oy=0):
        x0 = int((shape.left + ox) / EMU * scale)
        y0 = int((shape.top + oy) / EMU * scale)
        x1 = int((shape.left + ox + shape.width) / EMU * scale)
        y1 = int((shape.top + oy + shape.height) / EMU * scale)
        return [x0, y0, x1, y1]

    def draw_shape(shape, ox=0, oy=0):
        try:
            st = shape.shape_type
        except Exception:
            st = None
        # groups: recurse (approximate — ignore child-offset transform)
        if st == MSO_SHAPE_TYPE.GROUP:
            try:
                for sub in shape.shapes:
                    draw_shape(sub, ox, oy)
            except Exception:
                pass
            return
        try:
            box = emu_box(shape, ox, oy)
        except Exception:
            return
        if box[2] <= box[0] or box[3] <= box[1]:
            return

        # pictures: paste actual image
        if st == MSO_SHAPE_TYPE.PICTURE:
            try:
                blob = shape.image.blob
                import io as _io
                pim = Image.open(_io.BytesIO(blob)).convert("RGB")
                pim = pim.resize((box[2] - box[0], box[3] - box[1]))
                img.paste(pim, (box[0], box[1]))
                return
            except Exception:
                d.rectangle(box, fill=(220, 220, 225), outline=(150, 150, 150))
                d.text((box[0] + 4, box[1] + 4), "IMG", fill=(80, 80, 80), font=_font(14))
                return

        # charts / tables / ole / media → labeled placeholder
        label = None
        if st == MSO_SHAPE_TYPE.CHART:
            label = "CHART"
        elif st == MSO_SHAPE_TYPE.TABLE:
            label = "TABLE"
        elif st in (MSO_SHAPE_TYPE.MEDIA, getattr(MSO_SHAPE_TYPE, "EMBEDDED_OLE_OBJECT", None)):
            label = "MEDIA/OLE"
        if label:
            d.rectangle(box, fill=(238, 240, 245), outline=(120, 130, 150), width=2)
            d.text((box[0] + 6, box[1] + 6), label, fill=(70, 80, 110), font=_font(16, True))
            if label == "TABLE":
                _draw_table(d, shape, box)
            return

        # connectors / lines
        if st == MSO_SHAPE_TYPE.LINE:
            col = _rgb(shape.line.color) or (60, 60, 60)
            d.line([box[0], box[1], box[2], box[3]], fill=col, width=2)
            return

        # autoshapes / textboxes
        kind, data = _fill_color(shape)
        is_oval = False
        is_round = False
        try:
            asn = shape.auto_shape_type
            if asn is not None:
                an = getattr(asn, "name", "")
                is_oval = an == "OVAL"
                is_round = "ROUND" in an
        except Exception:
            pass

        if kind == "gradient" and data:
            _draw_gradient(img, tuple(box), data)
            if is_oval:
                # mask non-ellipse corners lightly (approx) — skip for simplicity
                pass
        elif kind == "solid" and data:
            if is_oval:
                d.ellipse(box, fill=data)
            elif is_round:
                d.rounded_rectangle(box, radius=max(4, (box[3]-box[1])//8), fill=data)
            else:
                d.rectangle(box, fill=data)
        else:
            # no fill — faint outline so we can see the box
            if is_oval:
                d.ellipse(box, outline=(200, 200, 205))
            else:
                d.rectangle(box, outline=(205, 205, 210))

        # border
        try:
            lc = _rgb(shape.line.color)
            if lc:
                if is_oval:
                    d.ellipse(box, outline=lc, width=2)
                else:
                    d.rectangle(box, outline=lc, width=2)
        except Exception:
            pass

        # text
        txt = _text_of(shape)
        if txt:
            tc = _text_color(shape)
            fs = max(10, min(int((box[3]-box[1]) * 0.32), 26))
            f = _font(fs, True)
            lines = txt.split("\n")[:4]
            ty = box[1] + 4
            for ln in lines:
                d.text((box[0] + 5, ty), ln[:60], fill=tc, font=f)
                ty += fs + 2
                if ty > box[3] - fs:
                    break

    for shape in slide.shapes:
        draw_shape(shape)

    # slide number badge
    d.rectangle([0, H - 22, 60, H], fill=(0, 0, 0))
    d.text((6, H - 20), f"#{idx}", fill=(255, 255, 255), font=_font(14, True))
    return img


def _fill_color_obj(fill):
    """Like _fill_color but for a FillFormat directly (slide background)."""
    try:
        t = fill.type
    except Exception:
        return ("none", None)
    if t is None:
        return ("none", None)
    name = getattr(t, "name", str(t))
    if name == "SOLID":
        return ("solid", _rgb(fill.fore_color))
    if name == "GRADIENT":
        try:
            stops = [(s.position, _rgb(s.color)) for s in fill.gradient_stops]
            stops = [(p, c) for p, c in stops if c]
            if len(stops) >= 2:
                return ("gradient", stops)
        except Exception:
            pass
    return ("none", None)


def _draw_table(d, shape, box):
    try:
        tbl = shape.table
        rows = len(tbl.rows)
        cols = len(tbl.columns)
        x0, y0, x1, y1 = box
        for r in range(rows + 1):
            yy = y0 + (y1 - y0) * r // max(1, rows)
            d.line([x0, yy, x1, yy], fill=(150, 160, 180))
        for c in range(cols + 1):
            xx = x0 + (x1 - x0) * c // max(1, cols)
            d.line([xx, y0, xx, y1], fill=(150, 160, 180))
        for r in range(rows):
            for c in range(cols):
                try:
                    t = tbl.cell(r, c).text[:10]
                except Exception:
                    t = ""
                if t:
                    cx = x0 + (x1 - x0) * c // cols + 3
                    cy = y0 + (y1 - y0) * r // rows + 3
                    d.text((cx, cy), t, fill=(40, 40, 40), font=_font(11))
    except Exception:
        pass


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "_out/99_everything.pptx"
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "_review")
    out.mkdir(exist_ok=True)
    prs = Presentation(src)
    scale = 96.0  # px per inch-ish (slide_width/EMU is inches)
    paths = []
    for i, slide in enumerate(prs.slides, 1):
        img = render_slide(slide, prs, scale, i)
        p = out / f"slide{i:02d}.png"
        img.save(p)
        paths.append(p)
    # contact sheets (6 per sheet)
    thumbs = [Image.open(p) for p in paths]
    tw, th = 480, 270
    per_row, per_col = 3, 2
    per_sheet = per_row * per_col
    sheets = []
    for s in range(0, len(thumbs), per_sheet):
        chunk = thumbs[s:s + per_sheet]
        sheet = Image.new("RGB", (tw * per_row, th * per_col), (245, 245, 248))
        for j, t in enumerate(chunk):
            tt = t.resize((tw, th))
            r, c = divmod(j, per_row)
            sheet.paste(tt, (c * tw, r * th))
        sp = out / f"contact_{s // per_sheet + 1}.png"
        sheet.save(sp)
        sheets.append(sp)
    print(f"rendered {len(paths)} slides, {len(sheets)} contact sheets to {out}/")


if __name__ == "__main__":
    main()
