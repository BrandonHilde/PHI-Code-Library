"""Glyph bitmaps, as fontlib makes them, written plainly in Python: the rules libs/font/fontlib/raster.phi
follows. They're FreeType's (2.13, unhinted, FT_RENDER_MODE_NORMAL), as browsers draw text on Linux:

  - The size: an integer number of pixels per em, ppem, and the scale FT_DivFix(ppem * 64, units per
    em), font units to 26.6 pixels (a 64th of a pixel). The glyph is loaded scaled (ttf_reference).
  - The bitmap: the outline's control box (every point, on the curve or not), rounded out to whole
    pixels; its left is that box's left, and its top its top, in pixels from the origin.
  - The outline is read as FreeType's FT_Outline_Decompose reads it: a contour that starts off the
    curve starts at its last point, if that's on it, or else halfway between the two; two control
    points in a row have an on-curve point halfway between them (halves rounded toward zero).
  - Lines are walked cell by cell, a cell being a pixel, in 256ths of a pixel, adding each cell's
    cover (how far up the line goes in it) and area (twice the area to its left, in 256ths squared),
    as ftgrays.c's gray_render_line does, with its divisions by multiplying by a reciprocal.
  - A quadratic curve is split into 2^n lines, n the fewest that bring its deviation (the larger of
    |p0 + p2 - 2 p1| in x and y) to a quarter of a pixel, found by forward differences in 32.32 fixed
    point, as gray_render_conic does.
  - Each row is swept from the left, its cover added up: a pixel's coverage is (cover * 512 - area)
    >> 9, by the non-zero winding rule: a negative one is complemented, and more than 255 is 255.
  - A glyph FreeType marks as overlapping (FT_OUTLINE_OVERLAP) is drawn 4 times as wide and high, and
    each pixel is the sum of its 16 subpixels' coverage in 16ths, rounded ((c + 8) / 16), at most 255,
    as ft_smooth_raster_overlap does; one whose bitmap is wider than 0x7FFF / 4 can't be drawn.
"""
PIXEL_BITS = 8
ONE = 1 << PIXEL_BITS


def div_fix(a, b):
    """FT_DivFix: a * 65536 / b, rounded"""
    s = 1
    if a < 0:
        a, s = -a, -s
    if b < 0:
        b, s = -b, -s
    q = ((a << 16) + (b >> 1)) // b if b else 0x7FFFFFFF
    return q if s > 0 else -q


def scale_of(ppem, units_per_em):
    return div_fix(ppem * 64, units_per_em)


def tdiv(a, b):
    """C's division, toward zero"""
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def udiv_prep(c, b):
    return 0xFFFFFFFF // b if c else 0


def udiv(a, r):
    return ((a & 0xFFFFFFFFFFFFFFFF) * r & 0xFFFFFFFFFFFFFFFF) >> 32


class Raster:
    def __init__(self, width, height):
        self.w, self.h = width, height
        self.cells = {}           # (ex, ey) -> [area, cover]
        self.ex = self.ey = 0
        self.area = self.cover = 0
        self.x = self.y = 0

    def record(self):
        if self.area or self.cover:
            if 0 <= self.ey < self.h and self.ex < self.w:
                c = self.cells.setdefault((self.ex, self.ey), [0, 0])
                c[0] += self.area
                c[1] += self.cover

    def set_cell(self, ex, ey):
        if ex < 0:
            ex = -1
        if (ex, ey) != (self.ex, self.ey):
            self.record()
            self.ex, self.ey = ex, ey
            self.area = self.cover = 0

    def move_to(self, x, y):
        self.record()
        self.area = self.cover = 0
        x <<= PIXEL_BITS - 6
        y <<= PIXEL_BITS - 6
        ex, ey = x >> PIXEL_BITS, y >> PIXEL_BITS
        self.ex, self.ey = (ex if ex >= 0 else -1), ey
        self.x, self.y = x, y

    def line_to(self, x, y):
        self.render_line(x << (PIXEL_BITS - 6), y << (PIXEL_BITS - 6))

    def render_line(self, to_x, to_y):
        ex1, ex2 = self.x >> PIXEL_BITS, to_x >> PIXEL_BITS
        ey1, ey2 = self.y >> PIXEL_BITS, to_y >> PIXEL_BITS
        if (ey1 >= self.h and ey2 >= self.h) or (ey1 < 0 and ey2 < 0):
            self.x, self.y = to_x, to_y
            return
        fx1, fy1 = self.x & (ONE - 1), self.y & (ONE - 1)
        dx, dy = to_x - self.x, to_y - self.y
        if ex1 == ex2 and ey1 == ey2:
            pass
        elif dy == 0:
            self.set_cell(ex2, ey2)
            self.x, self.y = to_x, to_y
            return
        elif dx == 0:
            if dy > 0:
                while True:
                    fy2 = ONE
                    self.cover += fy2 - fy1
                    self.area += (fy2 - fy1) * fx1 * 2
                    fy1 = 0
                    ey1 += 1
                    self.set_cell(ex1, ey1)
                    if ey1 == ey2:
                        break
            else:
                while True:
                    fy2 = 0
                    self.cover += fy2 - fy1
                    self.area += (fy2 - fy1) * fx1 * 2
                    fy1 = ONE
                    ey1 -= 1
                    self.set_cell(ex1, ey1)
                    if ey1 == ey2:
                        break
        else:
            prod = dx * fy1 - dy * fx1
            dx_r = udiv_prep(ex1 != ex2, abs(dx)) if dx else 0
            dy_r = udiv_prep(ey1 != ey2, abs(dy)) if dy else 0
            while True:
                if prod - dx * ONE > 0 and prod <= 0:                       # left
                    fx2 = 0
                    fy2 = udiv(-prod, dx_r)
                    prod -= dy * ONE
                    self.cover += fy2 - fy1
                    self.area += (fy2 - fy1) * (fx1 + fx2)
                    fx1, fy1 = ONE, fy2
                    ex1 -= 1
                elif prod - dx * ONE + dy * ONE > 0 and prod - dx * ONE <= 0:   # up
                    prod -= dx * ONE
                    fx2 = udiv(-prod, dy_r)
                    fy2 = ONE
                    self.cover += fy2 - fy1
                    self.area += (fy2 - fy1) * (fx1 + fx2)
                    fx1, fy1 = fx2, 0
                    ey1 += 1
                elif prod + dy * ONE >= 0 and prod - dx * ONE + dy * ONE <= 0:  # right
                    prod += dy * ONE
                    fx2 = ONE
                    fy2 = udiv(prod, dx_r)
                    self.cover += fy2 - fy1
                    self.area += (fy2 - fy1) * (fx1 + fx2)
                    fx1, fy1 = 0, fy2
                    ex1 += 1
                else:                                                         # down
                    fy2 = 0
                    fx2 = udiv(prod, dy_r)
                    prod += dx * ONE
                    self.cover += fy2 - fy1
                    self.area += (fy2 - fy1) * (fx1 + fx2)
                    fx1, fy1 = fx2, ONE
                    ey1 -= 1
                self.set_cell(ex1, ey1)
                if ex1 == ex2 and ey1 == ey2:
                    break
        fx2, fy2 = to_x & (ONE - 1), to_y & (ONE - 1)
        self.cover += fy2 - fy1
        self.area += (fy2 - fy1) * (fx1 + fx2)
        self.x, self.y = to_x, to_y

    def conic_to(self, cx, cy, x, y):
        p0x, p0y = self.x, self.y
        p1x, p1y = cx << (PIXEL_BITS - 6), cy << (PIXEL_BITS - 6)
        p2x, p2y = x << (PIXEL_BITS - 6), y << (PIXEL_BITS - 6)
        t = lambda v: v >> PIXEL_BITS  # noqa: E731
        if (t(p0y) >= self.h and t(p1y) >= self.h and t(p2y) >= self.h) or (t(p0y) < 0 and t(p1y) < 0 and t(p2y) < 0):
            self.x, self.y = p2x, p2y
            return
        bx, by = p1x - p0x, p1y - p0y
        ax, ay = p2x - p1x - bx, p2y - p1y - by
        d = max(abs(ax), abs(ay))
        if d <= ONE // 4:
            self.render_line(p2x, p2y)
            return
        shift = 0
        while True:
            d >>= 2
            shift += 1
            if d <= ONE // 4:
                break
        rx = ax << (33 - 2 * shift)
        ry = ay << (33 - 2 * shift)
        qx = (bx << (33 - shift)) + (ax << (32 - 2 * shift))
        qy = (by << (33 - shift)) + (ay << (32 - 2 * shift))
        px, py = p0x << 32, p0y << 32
        for _ in range(1 << shift):
            px += qx
            py += qy
            qx += rx
            qy += ry
            self.render_line(px >> 32, py >> 32)

    def sweep(self):
        self.record()
        self.area = self.cover = 0
        bitmap = bytearray(self.w * self.h)
        rows = {}
        for (ex, ey), c in self.cells.items():
            rows.setdefault(ey, []).append((ex, c[0], c[1]))
        for ey, cells in rows.items():
            row = (self.h - 1 - ey) * self.w
            cells.sort()
            x = 0
            cover = 0
            for ex, area, cv in cells:
                if cover and ex > x:
                    v = coverage(cover)
                    for k in range(x, ex):
                        bitmap[row + k] = v
                cover += cv * ONE * 2
                a = cover - area
                if a and ex >= 0:
                    bitmap[row + ex] = coverage(a)
                x = ex + 1
            if cover:
                v = coverage(cover)
                for k in range(x, self.w):
                    bitmap[row + k] = v
        return bitmap


def coverage(area):
    c = area >> (PIXEL_BITS * 2 + 1 - 8)
    if c < 0:
        c = ~c
    return 255 if c > 255 else c & 255


def render(points, flags, ends, overlap=False):
    """(left, top, width, height, bitmap) of an outline in 26.6 pixels; None if FreeType can't draw it"""
    if not points:
        return 0, 0, 0, 0, b''
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    left, bottom = min(xs) >> 6, min(ys) >> 6
    right, top = (max(xs) + 63) >> 6, (max(ys) + 63) >> 6
    w, h = right - left, top - bottom
    k = 4 if overlap else 1
    if overlap and w * 4 > 0x7FFF:
        return None
    r = Raster(w * k, h * k)
    dx, dy = -left * 64, -bottom * 64
    first = 0
    for last in ends:
        pts = [((x + dx) * k, (y + dy) * k) for x, y in points[first:last + 1]]
        tags = flags[first:last + 1]
        decompose(r, pts, tags)
        first = last + 1
    fine = r.sweep()
    if not overlap:
        return left, top, w, h, bytes(fine)
    out = bytearray(w * h)
    for row in range(h):
        for col in range(w):
            total = 0
            for sy in range(4):
                base = (row * 4 + sy) * w * 4 + col * 4
                for sx in range(4):
                    total += (fine[base + sx] + 8) // 16
            out[row * w + col] = min(total, 255)
    return left, top, w, h, bytes(out)


def decompose(r, pts, tags):
    """one contour, as FT_Outline_Decompose gives it to the rasterizer"""
    n = len(pts)
    start = pts[0]
    i = 0
    limit = n - 1
    if not tags[0]:
        if tags[-1]:
            start = pts[-1]
            limit -= 1
        else:
            start = (tdiv(pts[0][0] + pts[-1][0], 2), tdiv(pts[0][1] + pts[-1][1], 2))
        i = -1
    r.move_to(*start)
    while i < limit:
        i += 1
        if tags[i]:
            r.line_to(*pts[i])
            continue
        control = pts[i]
        while True:
            if i < limit:
                i += 1
                if tags[i]:
                    r.conic_to(control[0], control[1], *pts[i])
                    break
                mid = (tdiv(control[0] + pts[i][0], 2), tdiv(control[1] + pts[i][1], 2))
                r.conic_to(control[0], control[1], *mid)
                control = pts[i]
                continue
            r.conic_to(control[0], control[1], *start)
            return
    r.line_to(*start)
