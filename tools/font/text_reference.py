"""Simple text, as fontlib lays it out and draws it, written plainly in Python: the rules
libs/font/fontlib/text.phi follows.

  - Text is UTF-8, decoded as the WHATWG Encoding Standard decodes it (and Python's 'replace'): each
    malformed sequence, as far as it's a valid start, is one U+FFFD.
  - Each character is the glyph of the first font in the list that has one for it (by HarfBuzz's
    lookup); if none has, the first font's glyph 0 (.notdef).
  - A glyph's advance is HarfBuzz's at the size: hmtx's advance times mult, plus 32768, over 65536,
    mult being (ppem * 64 << 16) / units per em. They add up, in 64ths of a pixel.
  - Kerning (kern_reference), unless it's turned off: in each run of glyphs from one font, for the
    script asked for ('latn' if none is), adding to glyphs' advances and offsets. No other shaping
    (ligatures, marks).
  - Drawing: each glyph's bitmap (raster_reference) is put with its origin at the pen, rounded to a
    whole pixel ((x + 32) >> 6), its left `left` pixels right of that and its top `top` pixels above
    the baseline; each pixel's coverage times the color's alpha ((c * a + 127) / 255) blends the
    color over the canvas as imagelib's BlendRow does ((src * a + dst * (255 - a) + 127) / 255 a
    channel), the canvas's alpha kept. Pixels off the canvas are left out.
"""
import ttf_reference as T
import raster_reference as R
import kern_reference as K


def decode(data):
    return [ord(c) for c in bytes(data).decode('utf-8', errors='replace')]


class Font:
    """a font at a size"""

    def __init__(self, data, ppem):
        self.face = T.Face(data)
        self.cmap = T.Cmap(data)
        self.ppem = ppem
        self.scale = R.scale_of(ppem, self.face.units_per_em)
        self.mult = (ppem * 64 << 16) // self.face.units_per_em
        self.bitmaps = {}
        self.data = data
        self.kerns = {}

    def kern(self, script):
        if script not in self.kerns:
            self.kerns[script] = K.Kern(self.data, script)
        return self.kerns[script]

    def advance(self, g):
        adv, _ = self.face.metrics(g)
        return (adv * self.mult + 32768) >> 16

    def bitmap(self, g):
        if g not in self.bitmaps:
            res = self.face.glyph(g, self.scale)
            if isinstance(res, str):
                self.bitmaps[g] = None
            else:
                self.bitmaps[g] = R.render(res[0], res[1], res[2], self.face.overlap)
        return self.bitmaps[g]


def glyphs(fonts, text, script='latn', kerning=True):
    """[(font index, glyph, advance, offset)] for the text, in 64ths of a pixel"""
    out = []
    for u in decode(text):
        for k, f in enumerate(fonts):
            g = f.cmap.glyph(u)
            if g and g < f.face.num_glyphs:
                out.append([k, g, f.advance(g), 0])
                break
        else:
            out.append([0, 0, fonts[0].advance(0), 0])
    if kerning:
        i = 0
        while i < len(out):
            j = i
            while j < len(out) and out[j][0] == out[i][0]:
                j += 1
            f = fonts[out[i][0]]
            adj = f.kern(script).apply([gl[1] for gl in out[i:j]], f.mult)
            for n, (a, o) in enumerate(adj):
                out[i + n][2] += a
                out[i + n][3] += o
            i = j
    return [tuple(gl) for gl in out]


def measure(fonts, text, script='latn', kerning=True):
    return sum(a for _, _, a, _ in glyphs(fonts, text, script, kerning))


def draw(fonts, text, canvas, width, height, x, y, color, script='latn', kerning=True):
    """draws text on canvas (a list of width * height 0xAARRGGBB) with its pen starting at x (in 64ths
    of a pixel) on the baseline y (in pixels); gives the pen's x after it"""
    ca = color >> 24
    pen = x
    for k, g, adv, off in glyphs(fonts, text, script, kerning):
        bm = fonts[k].bitmap(g)
        if bm is not None:
            left, top, w, h, pixels = bm
            ox = ((pen + off + 32) >> 6) + left
            oy = y - top
            for row in range(h):
                cy = oy + row
                if cy < 0 or cy >= height:
                    continue
                for col in range(w):
                    cx = ox + col
                    if cx < 0 or cx >= width:
                        continue
                    c = pixels[row * w + col]
                    if not c:
                        continue
                    a = (c * ca + 127) // 255
                    if not a:
                        continue
                    d = canvas[cy * width + cx]
                    out = d & 0xFF000000
                    for shift in (16, 8, 0):
                        s_ch = (color >> shift) & 255
                        d_ch = (d >> shift) & 255
                        out |= ((s_ch * a + d_ch * (255 - a) + 127) // 255) << shift
                    canvas[cy * width + cx] = out
        pen += adv
    return pen
