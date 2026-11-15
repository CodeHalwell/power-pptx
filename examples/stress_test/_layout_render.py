"""Pillow layout renderer for reviewing deck geometry without LibreOffice.

Draws each slide's shapes to scale from their real EMU geometry: slide
background, solid/gradient fills, autoshape outlines, text, embedded pictures,
and labeled placeholders for charts/tables. This is a *layout* preview — it is
faithful for position/size/alignment/colour/overlap (the "are the backgrounds
and card boxes where I intended" review), not a PowerPoint-fidelity renderer.
"""

from __future__ import annotations

import io
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


# A transform maps a shape's local EMU coords to slide EMU coords:
#   slide = (tx + local * s).  Top-level shapes use the identity; group
#   children compose the group's offset + child-space scaling so nested
#   groups render in the right place and size.
IDENT = (0.0, 0.0, 1.0, 1.0)

# Charts / tables / OLE / media are drawn as a labeled placeholder box.
PLACEHOLDER_LABELS = {
    MSO_SHAPE_TYPE.CHART: "CHART",
    MSO_SHAPE_TYPE.TABLE: "TABLE",
    MSO_SHAPE_TYPE.MEDIA: "MEDIA/OLE",
    MSO_SHAPE_TYPE.EMBEDDED_OLE_OBJECT: "MEDIA/OLE",
}


def render_slide(slide, prs, scale, idx):
    W = int(prs.slide_width / EMU * scale)
    H = int(prs.slide_height / EMU * scale)
    img = Image.new("RGB", (W, H), (255, 255, 255))
    canvas = _Canvas(img, ImageDraw.Draw(img, "RGBA"), scale)
    canvas.paint_background(slide, W, H)
    for shape in slide.shapes:
        canvas.draw_shape(shape)

    # slide number badge
    d = canvas.draw
    d.rectangle([0, H - 22, 60, H], fill=(0, 0, 0))
    d.text((6, H - 20), f"#{idx}", fill=(255, 255, 255), font=_font(14, True))
    return img


def _shape_type(shape):
    try:
        return shape.shape_type
    except Exception:
        return None


def _child_transform(group, tf):
    """Compose *tf* with *group*'s child-space → parent-space mapping."""
    tx, ty, sx, sy = tf
    try:
        xfrm = group._element.grpSpPr.xfrm
        off, ext = xfrm.off, xfrm.ext
        ch_off, ch_ext = xfrm.chOff, xfrm.chExt
        csx = (ext.cx / ch_ext.cx) * sx if ch_ext.cx else sx
        csy = (ext.cy / ch_ext.cy) * sy if ch_ext.cy else sy
        ctx = tx + off.x * sx - ch_off.x * csx
        cty = ty + off.y * sy - ch_off.y * csy
        return (ctx, cty, csx, csy)
    except Exception:
        # Fall back to a plain translate by the group's slide position.
        return (tx + group.left * sx, ty + group.top * sy, sx, sy)


def _outline_flags(shape):
    """``(is_oval, is_round)`` from the shape's preset geometry, when it has one."""
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
    return is_oval, is_round


class _Canvas:
    """The slide image being drawn, its RGBA draw handle and px-per-inch scale."""

    def __init__(self, img, draw, scale):
        self.img = img
        self.draw = draw
        self.scale = scale

    def paint_background(self, slide, W, H):
        try:
            bg = slide.background
            kind, data = _fill_color_obj(bg.fill)
            if kind == "solid" and data:
                self.draw.rectangle([0, 0, W, H], fill=data)
            elif kind == "gradient" and data:
                _draw_gradient(self.img, (0, 0, W, H), data)
        except Exception:
            pass

    def emu_box(self, shape, tf):
        """The pixel box ``[x0, y0, x1, y1]`` of *shape* under transform *tf*."""
        tx, ty, sx, sy = tf
        scale = self.scale
        x0 = int((tx + shape.left * sx) / EMU * scale)
        y0 = int((ty + shape.top * sy) / EMU * scale)
        x1 = int((tx + (shape.left + shape.width) * sx) / EMU * scale)
        y1 = int((ty + (shape.top + shape.height) * sy) / EMU * scale)
        return [x0, y0, x1, y1]

    def draw_shape(self, shape, tf=IDENT):
        st = _shape_type(shape)
        # groups: recurse with the composed child transform (offset + scale)
        if st == MSO_SHAPE_TYPE.GROUP:
            self._draw_group(shape, tf)
            return
        box = self._visible_box(shape, tf)
        if box is None:
            return
        if st == MSO_SHAPE_TYPE.PICTURE:
            self._draw_picture(shape, box)
        elif st in PLACEHOLDER_LABELS:
            self._draw_placeholder(shape, box, PLACEHOLDER_LABELS[st])
        elif st == MSO_SHAPE_TYPE.LINE:
            self._draw_line(shape, box)
        else:
            self._draw_autoshape(shape, box)

    def _draw_group(self, group, tf):
        child_tf = _child_transform(group, tf)
        try:
            for sub in group.shapes:
                self.draw_shape(sub, child_tf)
        except Exception:
            pass

    def _visible_box(self, shape, tf):
        """The shape's pixel box, or ``None`` when it has no geometry or no area."""
        try:
            box = self.emu_box(shape, tf)
        except Exception:
            return None
        if box[2] <= box[0] or box[3] <= box[1]:
            return None
        return box

    def _draw_picture(self, shape, box):
        """Paste the actual image, or an "IMG" placeholder when it can't be read."""
        try:
            blob = shape.image.blob
            pim = Image.open(io.BytesIO(blob)).convert("RGB")
            pim = pim.resize((box[2] - box[0], box[3] - box[1]))
            self.img.paste(pim, (box[0], box[1]))
        except Exception:
            self.draw.rectangle(box, fill=(220, 220, 225), outline=(150, 150, 150))
            self.draw.text((box[0] + 4, box[1] + 4), "IMG", fill=(80, 80, 80), font=_font(14))

    def _draw_placeholder(self, shape, box, label):
        d = self.draw
        d.rectangle(box, fill=(238, 240, 245), outline=(120, 130, 150), width=2)
        d.text((box[0] + 6, box[1] + 6), label, fill=(70, 80, 110), font=_font(16, True))
        if label == "TABLE":
            _draw_table(d, shape, box)

    def _draw_line(self, shape, box):
        """Connectors / lines."""
        col = _rgb(shape.line.color) or (60, 60, 60)
        self.draw.line([box[0], box[1], box[2], box[3]], fill=col, width=2)

    def _draw_autoshape(self, shape, box):
        """Autoshapes / textboxes: fill, border, then the first lines of text."""
        kind, data = _fill_color(shape)
        is_oval, is_round = _outline_flags(shape)
        self._paint_fill(box, kind, data, is_oval, is_round)
        self._paint_border(shape, box, is_oval)
        self._paint_text(shape, box)

    def _paint_fill(self, box, kind, data, is_oval, is_round):
        d = self.draw
        if kind == "gradient" and data:
            # (an oval's corners are not masked off — kept simple)
            _draw_gradient(self.img, tuple(box), data)
        elif kind == "solid" and data:
            if is_oval:
                d.ellipse(box, fill=data)
            elif is_round:
                d.rounded_rectangle(box, radius=max(4, (box[3]-box[1])//8), fill=data)
            else:
                d.rectangle(box, fill=data)
        # no fill — faint outline so we can see the box
        elif is_oval:
            d.ellipse(box, outline=(200, 200, 205))
        else:
            d.rectangle(box, outline=(205, 205, 210))

    def _paint_border(self, shape, box, is_oval):
        try:
            lc = _rgb(shape.line.color)
            if not lc:
                return
            if is_oval:
                self.draw.ellipse(box, outline=lc, width=2)
            else:
                self.draw.rectangle(box, outline=lc, width=2)
        except Exception:
            pass

    def _paint_text(self, shape, box):
        txt = _text_of(shape)
        if not txt:
            return
        tc = _text_color(shape)
        fs = max(10, min(int((box[3]-box[1]) * 0.32), 26))
        f = _font(fs, True)
        lines = txt.split("\n")[:4]
        ty = box[1] + 4
        for ln in lines:
            self.draw.text((box[0] + 5, ty), ln[:60], fill=tc, font=f)
            ty += fs + 2
            if ty > box[3] - fs:
                break

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
