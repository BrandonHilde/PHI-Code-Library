"""Makes libs/font/tests/var/made.ttf, a small variable font, and libs/font/test_var.expected: what
test_var.phi must print for it, each glyph's outline and advance at several places on its axes.

    python3 tools/font/make_var_tests.py [--coretext]

The font is written here byte by byte (no font library is needed), with one or a few of each thing
gvar can say: a tuple for every point and tuples that list their points (the rest worked out from
their neighbours on the contour), points listed once for the glyph and by a tuple for itself, a
peak the font's tuples share and one a tuple carries, a tuple that begins and ends part way along an
axis, two axes and a tuple at the corner of both, deltas packed as zeros, bytes and words, a composite
whose components move, an empty glyph whose advance changes, and an avar map.

What's expected is worked out here from the file's bytes by the rules of the OpenType specification
(fvar, avar, gvar), in exact fractions, and is checked to come to whole numbers at every place used, so
that it doesn't depend on how anyone rounds. With --coretext (on a Mac, with swiftc) macOS's CoreText
is asked for each glyph's advance and box at the same places, and has to agree.
"""
import os
import struct
import subprocess
import sys
import tempfile
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, '..', '..', 'libs', 'font', 'tests', 'var')
EXPECTED = os.path.join(HERE, '..', '..', 'libs', 'font', 'test_var.expected')

UPEM = 1000
AXES = [(b'wght', 100, 400, 900), (b'wdth', 50, 100, 200)]
# avar: wght's upper half is bent (half way is three quarters); wdth is straight
AVAR = [[(-1, -1), (0, 0), (0.5, 0.75), (1, 1)], [(-1, -1), (0, 0), (1, 1)]]

# the places asked for: (wght, wdth)
PLACES = [(400, 100), (900, 100), (650, 100), (100, 100), (250, 100), (400, 200), (900, 200), (525, 100),
          (400, 50), (1000, 300)]


# ---------------------------------------------------------------- the glyphs

def square(x0, y0, x1, y1):
    return [(x0, y0, 1), (x0, y1, 1), (x1, y1, 1), (x1, y0, 1)]


# simple glyphs: contours of (x, y, on); composites: components (glyph, dx, dy)
GLYPHS = {
    0: {'contours': [square(100, 0, 500, 700)], 'advance': 600},
    1: {'contours': [square(40, 0, 440, 800), square(140, 100, 340, 700)], 'advance': 480},
    2: {'contours': [[(60, 0, 1), (60, 400, 1), (160, 500, 0), (260, 400, 1), (260, 0, 1), (160, -100, 0)]],
        'advance': 320},
    3: {'components': [(1, 0, 0), (2, 520, 40)], 'advance': 880},
    4: {'contours': [], 'advance': 240},
    5: {'contours': [square(80, 0, 280, 600)], 'advance': 360},
}

# each glyph's tuples: (peak per axis, (starts, ends) or None, points listed or None for all,
# deltas (dx, dy) one a listed point, 'shared' or 'own' peak and points). The points of a glyph are
# its outline's (or its components), then four phantom points: the second is its advance.
W = (1.0, 0.0)
THIN = (-1.0, 0.0)
WIDE = (0.0, 1.0)
BOTH = (1.0, 1.0)

TUPLES = {
    # every point, by a shared peak: wider and taller, the advance with it
    0: [dict(peak=W, points=None, peak_shared=True,
             deltas=[(0, 0), (0, 80), (160, 80), (160, 0), (0, 0), (160, 0), (0, 0), (0, 0)])],
    # some points: the outer contour's two left corners and its top right one, one corner of the
    # inner one (which all of it follows), and the advance; the rest come from their neighbours
    1: [dict(peak=W, points=[0, 2, 5, 9], peak_shared=True, points_shared=True,
             deltas=[(-40, 0), (120, 80), (40, -40), (160, 0)]),
        dict(peak=THIN, points=[0, 2, 5, 9], peak_shared=False, points_shared=True,
             deltas=[(40, 0), (-80, 0), (0, 0), (-80, 0)])],
    # two tuples the same way, and one that begins and ends part way along
    2: [dict(peak=W, points=None, peak_shared=True,
             deltas=[(0, 0), (0, 0), (80, 80), (160, 0), (160, 0), (80, -40), (0, 0), (160, 0), (0, 0), (0, 0)]),
        dict(peak=(0.5, 0.0), region=((0.25, 0.0), (0.75, 0.0)), points=[2, 5], peak_shared=False,
             deltas=[(0, 300), (0, -300)])],
    # a composite: its second component moves, and its advance
    3: [dict(peak=W, points=[1, 3], peak_shared=True, deltas=[(240, 80), (320, 0)])],
    # nothing to draw: its advance
    4: [dict(peak=W, points=[1], peak_shared=True, deltas=[(80, 0)]),
        dict(peak=WIDE, points=None, peak_shared=True, deltas=[(0, 0), (240, 0), (0, 0), (0, 0)])],
    # two axes, and the corner of both
    5: [dict(peak=W, points=None, peak_shared=True,
             deltas=[(0, 0), (0, 0), (80, 0), (80, 0), (0, 0), (80, 0), (0, 0), (0, 0)]),
        dict(peak=WIDE, points=None, peak_shared=True,
             deltas=[(0, 0), (0, 0), (400, 0), (400, 0), (0, 0), (400, 0), (0, 0), (0, 0)]),
        dict(peak=BOTH, points=[2, 3], peak_shared=False, deltas=[(-40, 300), (-40, 0)])],
}
SHARED = [W, WIDE]


# ---------------------------------------------------------------- writing the font

def f2dot14(v):
    return struct.pack('>h', int(round(v * 16384)))


def fixed(v):
    return struct.pack('>i', int(round(v * 65536)))


def pack_points(points):
    if points is None:
        return b'\x00'
    n = len(points)
    out = bytes([n]) if n < 128 else bytes([0x80 | (n >> 8), n & 255])
    gaps = []
    last = 0
    for p in points:
        gaps.append(p - last)
        last = p
    i = 0
    while i < n:
        wide = gaps[i] > 255
        run = [gaps[i]]
        i += 1
        while i < n and len(run) < 128 and (gaps[i] > 255) == wide:
            run.append(gaps[i])
            i += 1
        out += bytes([(0x80 if wide else 0) | (len(run) - 1)])
        for g in run:
            out += struct.pack('>H', g) if wide else bytes([g])
    return out


def pack_deltas(values):
    out = b''
    i = 0
    n = len(values)
    while i < n:
        v = values[i]
        kind = 0 if v == 0 else (1 if -128 <= v <= 127 else 2)
        run = [v]
        i += 1
        while i < n and len(run) < 64:
            w = values[i]
            k = 0 if w == 0 else (1 if -128 <= w <= 127 else 2)
            if k != kind:
                break
            run.append(w)
            i += 1
        if kind == 0:
            out += bytes([0x80 | (len(run) - 1)])
        elif kind == 1:
            out += bytes([len(run) - 1]) + struct.pack('>%db' % len(run), *run)
        else:
            out += bytes([0x40 | (len(run) - 1)]) + struct.pack('>%dh' % len(run), *run)
    return out


def outline_points(g):
    """a glyph's own points at its usual place (a composite's too, put together)"""
    glyph = GLYPHS[g]
    if 'components' in glyph:
        pts = []
        for sub, dx, dy in glyph['components']:
            pts += [(x + dx, y + dy, on) for x, y, on in outline_points(sub)]
        return pts
    return [p for c in glyph['contours'] for p in c]


def glyph_bytes(g):
    glyph = GLYPHS[g]
    pts = outline_points(g)
    if not pts:
        return b''
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    box = struct.pack('>hhhh', min(xs), min(ys), max(xs), max(ys))
    if 'components' in glyph:
        out = struct.pack('>h', -1) + box
        parts = glyph['components']
        for k, (sub, dx, dy) in enumerate(parts):
            flags = 0x0001 | 0x0002      # words, and they're offsets
            if k + 1 < len(parts):
                flags |= 0x0020
            out += struct.pack('>HHhh', flags, sub, dx, dy)
        return out
    out = struct.pack('>h', len(glyph['contours'])) + box
    end = -1
    for c in glyph['contours']:
        end += len(c)
        out += struct.pack('>H', end)
    out += struct.pack('>H', 0)
    out += bytes([p[2] for p in pts])          # flags: on the curve or not, both coordinates words
    last = 0
    for x in xs:
        out += struct.pack('>h', x - last)
        last = x
    last = 0
    for y in ys:
        out += struct.pack('>h', y - last)
        last = y
    return out


def gvar_glyph(g):
    tuples = TUPLES.get(g)
    if not tuples:
        return b''
    shared_points = None
    for t in tuples:
        if t.get('points_shared'):
            shared_points = t['points']
    headers = b''
    data = b''
    if shared_points is not None:
        data += pack_points(shared_points)
    for t in tuples:
        body = b''
        index = 0
        if t.get('points_shared'):
            pass
        else:
            index |= 0x2000
            body += pack_points(t['points'])
        body += pack_deltas([d[0] for d in t['deltas']]) + pack_deltas([d[1] for d in t['deltas']])
        extra = b''
        if t['peak_shared']:
            index |= SHARED.index(t['peak'])
        else:
            index |= 0x8000
            extra += b''.join(f2dot14(v) for v in t['peak'])
        if t.get('region'):
            index |= 0x4000
            extra += b''.join(f2dot14(v) for v in t['region'][0]) + b''.join(f2dot14(v) for v in t['region'][1])
        headers += struct.pack('>HH', len(body), index) + extra
        data += body
    count = len(tuples) | (0x8000 if shared_points is not None else 0)
    out = struct.pack('>HH', count, 4 + len(headers)) + headers + data
    if len(out) % 2:
        out += b'\x00'
    return out


def table_checksum(data):
    data += b'\x00' * (-len(data) % 4)
    return sum(struct.unpack('>%dI' % (len(data) // 4), data)) & 0xFFFFFFFF


def make_font():
    n = len(GLYPHS)
    glyf = b''
    loca = [0]
    for g in range(n):
        b = glyph_bytes(g)
        b += b'\x00' * (-len(b) % 4)
        glyf += b
        loca.append(len(glyf))
    all_pts = [p for g in range(n) for p in outline_points(g)]
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    head = struct.pack('>IIIIHHQQhhhhHHhhh', 0x00010000, 0x00010000, 0, 0x5F0F3CF5, 0x0003, UPEM, 0, 0,
                       min(xs), min(ys), max(xs), max(ys), 0, 8, 2, 1, 0)
    hmtx = b''
    for g in range(n):
        pts = outline_points(g)
        lsb = min(p[0] for p in pts) if pts else 0
        hmtx += struct.pack('>Hh', GLYPHS[g]['advance'], lsb)
    hhea = struct.pack('>IhhhHhhhhhhhhhhhH', 0x00010000, 800, -200, 0, max(GLYPHS[g]['advance'] for g in GLYPHS),
                       0, 0, max(xs), 1, 0, 0, 0, 0, 0, 0, 0, n)
    maxp = struct.pack('>IHHHHHHHHHHHHHH', 0x00010000, n, 12, 2, 32, 8, 1, 0, 0, 0, 0, 0, 0, 2, 1)
    loca_b = b''.join(struct.pack('>I', o) for o in loca)
    # cmap: format 4, 'A' to 'E' are glyphs 1 to 5, and the space is glyph 4
    segs = [(0x20, 0x20, 4 - 0x20), (0x41, 0x43, 1 - 0x41), (0x44, 0x44, 5 - 0x44), (0xFFFF, 0xFFFF, 1)]
    seg_count = len(segs)
    sub = struct.pack('>HHHHHHH', 4, 16 + 8 * seg_count, 0, seg_count * 2, 8, 2, seg_count * 2 - 8)
    sub += b''.join(struct.pack('>H', s[1]) for s in segs) + struct.pack('>H', 0)
    sub += b''.join(struct.pack('>H', s[0]) for s in segs)
    sub += b''.join(struct.pack('>H', s[2] & 0xFFFF) for s in segs)
    sub += b''.join(struct.pack('>H', 0) for s in segs)
    cmap = struct.pack('>HHHHI', 0, 1, 3, 1, 12) + sub
    # the names CoreText wants before it will read a font: family, style, full and PostScript names
    names = [(1, 'PhiVarTest'), (2, 'Regular'), (4, 'PhiVarTest'), (6, 'PhiVarTest-Regular'),
             (256, 'Weight'), (257, 'Width')]
    strings = b''
    records = b''
    for name_id, text in names:
        raw = text.encode('utf-16-be')
        records += struct.pack('>HHHHHH', 3, 1, 0x409, name_id, len(raw), len(strings))
        strings += raw
    name = struct.pack('>HHH', 0, len(names), 6 + 12 * len(names)) + records + strings
    os2 = struct.pack('>HhHHHhhhhhhhhhhh10sIIII4sHHHhhhHH', 3, 400, 400, 5, 0, 300, 300, 0, 100, 300, 300, 0, 400, 50, 300, 0,
                      b'\x00' * 10, 1, 0, 0, 0, b'PHI ', 0x40, 0x20, 0x44, 800, -200, 0, 800, 200)
    os2 += struct.pack('>IIhhHHH', 1, 0, 500, 700, 0, 0x20, 1)
    post = struct.pack('>IIhhIIIII', 0x00030000, 0, -100, 50, 0, 0, 0, 0, 0)

    fvar = struct.pack('>HHHHHHHH', 1, 0, 16, 2, len(AXES), 20, 0, 4 + 4 * len(AXES))
    for k, (tag, lo, mid, hi) in enumerate(AXES):
        fvar += tag + fixed(lo) + fixed(mid) + fixed(hi) + struct.pack('>HH', 0, 256 + k)
    avar = struct.pack('>HHHH', 1, 0, 0, len(AXES))
    for seg in AVAR:
        avar += struct.pack('>H', len(seg)) + b''.join(f2dot14(a) + f2dot14(b) for a, b in seg)
    shared = b''.join(f2dot14(v) for t in SHARED for v in t)
    datas = [gvar_glyph(g) for g in range(n)]
    offsets = [0]
    for d in datas:
        offsets.append(offsets[-1] + len(d))
    header_len = 20 + 2 * (n + 1)
    gvar = struct.pack('>HHHHIHHI', 1, 0, len(AXES), len(SHARED), header_len, n, 0, header_len + len(shared))
    gvar += b''.join(struct.pack('>H', o // 2) for o in offsets) + shared + b''.join(datas)

    tables = {b'OS/2': os2, b'avar': avar, b'cmap': cmap, b'fvar': fvar, b'glyf': glyf, b'gvar': gvar,
              b'head': head, b'hhea': hhea, b'hmtx': hmtx, b'loca': loca_b, b'maxp': maxp, b'name': name,
              b'post': post}
    tags = sorted(tables)
    count = len(tags)
    power = 1
    while power * 2 <= count:
        power *= 2
    out = struct.pack('>IHHHH', 0x00010000, count, power * 16, power.bit_length() - 1, count * 16 - power * 16)
    at = 12 + 16 * count
    body = b''
    for tag in tags:
        data = tables[tag]
        out += tag + struct.pack('>III', table_checksum(data), at + len(body), len(data))
        body += data + b'\x00' * (-len(data) % 4)
    return out + body


# ---------------------------------------------------------------- reading it back, by the specification

class Font:
    def __init__(self, data):
        self.data = data
        self.tables = {}
        for k in range(struct.unpack_from('>H', data, 4)[0]):
            tag, _, off, size = struct.unpack_from('>4sIII', data, 12 + 16 * k)
            self.tables[tag] = data[off:off + size]
        self.n = struct.unpack_from('>H', self.tables[b'maxp'], 4)[0]
        fvar = self.tables[b'fvar']
        first, _, count, size = struct.unpack_from('>HHHH', fvar, 4)
        self.axes = []
        for k in range(count):
            tag, lo, mid, hi = struct.unpack_from('>4siii', fvar, first + k * size)
            self.axes.append((tag, Fraction(lo, 65536), Fraction(mid, 65536), Fraction(hi, 65536)))
        self.loca = struct.unpack('>%dI' % (self.n + 1), self.tables[b'loca'])

    def normalize(self, place):
        coords = []
        avar = self.tables[b'avar']
        p = 8
        for k, (tag, lo, mid, hi) in enumerate(self.axes):
            v = min(max(Fraction(place[k]), lo), hi)
            if v < mid:
                c = -(mid - v) / (mid - lo)
            elif v > mid:
                c = (v - mid) / (hi - mid)
            else:
                c = Fraction(0)
            count = struct.unpack_from('>H', avar, p)[0]
            seg = [(Fraction(a, 16384), Fraction(b, 16384))
                   for a, b in struct.iter_unpack('>hh', avar[p + 2:p + 2 + 4 * count])]
            p += 2 + 4 * count
            for i in range(1, len(seg)):
                if c <= seg[i][0]:
                    (a0, b0), (a1, b1) = seg[i - 1], seg[i]
                    c = b1 if a1 == a0 else b0 + (c - a0) * (b1 - b0) / (a1 - a0)
                    break
            coords.append(c)
        return coords

    def raw_glyph(self, g):
        """(contours of [x, y, on]) or (components [glyph, dx, dy]), the advance"""
        adv = struct.unpack_from('>H', self.tables[b'hmtx'], 4 * g)[0]
        d = self.tables[b'glyf'][self.loca[g]:self.loca[g + 1]]
        if not d:
            return 'simple', [], adv
        nc = struct.unpack_from('>h', d, 0)[0]
        if nc < 0:
            parts = []
            p = 10
            while True:
                flags, sub, dx, dy = struct.unpack_from('>HHhh', d, p)
                p += 8
                parts.append([sub, dx, dy])
                if not flags & 0x20:
                    break
            return 'composite', parts, adv
        ends = struct.unpack_from('>%dH' % nc, d, 10)
        n = ends[-1] + 1
        p = 10 + 2 * nc + 2
        flags = d[p:p + n]
        p += n
        xs = struct.unpack_from('>%dh' % n, d, p)
        ys = struct.unpack_from('>%dh' % n, d, p + 2 * n)
        pts = []
        x = y = 0
        for i in range(n):
            x += xs[i]
            y += ys[i]
            pts.append([x, y, flags[i] & 1])
        contours = []
        start = 0
        for e in ends:
            contours.append(pts[start:e + 1])
            start = e + 1
        return 'simple', contours, adv

    def unpack_points(self, d, p):
        count = d[p]
        p += 1
        if count == 0:
            return None, p
        if count & 0x80:
            count = ((count & 0x7F) << 8) | d[p]
            p += 1
        pts = []
        at = 0
        while len(pts) < count:
            c = d[p]
            p += 1
            for _ in range((c & 0x7F) + 1):
                if c & 0x80:
                    at += struct.unpack_from('>H', d, p)[0]
                    p += 2
                else:
                    at += d[p]
                    p += 1
                pts.append(at)
        return pts, p

    def unpack_deltas(self, d, p, count):
        out = []
        while len(out) < count:
            c = d[p]
            p += 1
            for _ in range((c & 0x3F) + 1):
                if c & 0x80:
                    out.append(0)
                elif c & 0x40:
                    out.append(struct.unpack_from('>h', d, p)[0])
                    p += 2
                else:
                    out.append(struct.unpack_from('>b', d, p)[0])
                    p += 1
        return out, p

    def deltas(self, g, coords, n, contours):
        """each of a glyph's n points' (dx, dy) at coords; contours: a simple glyph's, for the points
        a tuple leaves out"""
        gvar = self.tables[b'gvar']
        axis_count, shared_count, shared_at, glyph_count, flags, array_at = struct.unpack_from('>HHIHHI', gvar, 4)
        if flags & 1:
            a, b = struct.unpack_from('>II', gvar, 20 + 4 * g)
        else:
            a, b = (2 * v for v in struct.unpack_from('>HH', gvar, 20 + 2 * g))
        total = [[Fraction(0), Fraction(0)] for _ in range(n)]
        if b <= a:
            return total
        d = gvar[array_at + a:array_at + b]
        count, data_at = struct.unpack_from('>HH', d, 0)
        hp = 4
        dp = data_at
        shared_points = None
        if count & 0x8000:
            shared_points, dp = self.unpack_points(d, dp)
        for _ in range(count & 0x0FFF):
            size, index = struct.unpack_from('>HH', d, hp)
            hp += 4
            if index & 0x8000:
                peak = [Fraction(v, 16384) for v in struct.unpack_from('>%dh' % axis_count, d, hp)]
                hp += 2 * axis_count
            else:
                at = shared_at + (index & 0x0FFF) * 2 * axis_count
                peak = [Fraction(v, 16384) for v in struct.unpack_from('>%dh' % axis_count, gvar, at)]
            region = None
            if index & 0x4000:
                starts = [Fraction(v, 16384) for v in struct.unpack_from('>%dh' % axis_count, d, hp)]
                ends = [Fraction(v, 16384) for v in struct.unpack_from('>%dh' % axis_count, d, hp + 2 * axis_count)]
                hp += 4 * axis_count
                region = (starts, ends)
            q = dp
            dp += size
            scalar = Fraction(1)
            for k in range(axis_count):
                pk, c = peak[k], coords[k]
                if pk == 0:
                    continue
                if c == 0:
                    scalar = Fraction(0)
                    break
                if c == pk:
                    continue
                if region:
                    lo, hi = region[0][k], region[1][k]
                    if c <= lo or c >= hi:
                        scalar = Fraction(0)
                        break
                    scalar *= (c - lo) / (pk - lo) if c < pk else (hi - c) / (hi - pk)
                else:
                    if (c < 0) != (pk < 0) or abs(c) > abs(pk):
                        scalar = Fraction(0)
                        break
                    scalar *= c / pk
            points = shared_points
            if index & 0x2000:
                points, q = self.unpack_points(d, q)
            listed = n if points is None else len(points)
            dxs, q = self.unpack_deltas(d, q, listed)
            dys, q = self.unpack_deltas(d, q, listed)
            if scalar == 0:
                continue
            if points is None:
                mine = [[Fraction(dxs[i]), Fraction(dys[i])] for i in range(n)]
            else:
                mine = [None] * n
                for i, pt in enumerate(points):
                    if pt < n:
                        mine[pt] = [Fraction(dxs[i]), Fraction(dys[i])]
                if contours is not None:
                    start = 0
                    for c in contours:
                        idx = list(range(start, start + len(c)))
                        start += len(c)
                        hit = [i for i in idx if mine[i] is not None]
                        if not hit:
                            continue
                        flat = [p for cc in contours for p in cc]
                        worked = {}
                        for i in idx:
                            if mine[i] is not None:
                                continue
                            # the listed points before and after it, going round
                            before = max([h for h in hit if h < i], default=hit[-1])
                            after = min([h for h in hit if h > i], default=hit[0])
                            got = []
                            for axis in (0, 1):
                                x, a_, b_ = flat[i][axis], flat[before][axis], flat[after][axis]
                                da, db = mine[before][axis], mine[after][axis]
                                if a_ == b_:
                                    got.append(da if da == db else Fraction(0))
                                    continue
                                if a_ > b_:
                                    a_, b_, da, db = b_, a_, db, da
                                if x <= a_:
                                    got.append(da)
                                elif x >= b_:
                                    got.append(db)
                                else:
                                    got.append(da + (db - da) * Fraction(x - a_, b_ - a_))
                            worked[i] = got
                        for i, got in worked.items():
                            mine[i] = got
                mine = [m if m is not None else [Fraction(0), Fraction(0)] for m in mine]
            for i in range(n):
                total[i][0] += mine[i][0] * scalar
                total[i][1] += mine[i][1] * scalar
        return total

    def glyph(self, g, coords):
        """the glyph at coords: its points [x, y, on], its contours' ends, its advance, and its first
        phantom point's x (which the outline is moved left by)"""
        kind, body, adv = self.raw_glyph(g)
        if kind == 'simple':
            flat = [p for c in body for p in c]
            n = len(flat)
            d = self.deltas(g, coords, n + 4, body)
            pts = [[flat[i][0] + d[i][0], flat[i][1] + d[i][1], flat[i][2]] for i in range(n)]
            ends = []
            at = -1
            for c in body:
                at += len(c)
                ends.append(at)
            return pts, ends, adv + d[n + 1][0] - d[n][0], d[n][0]
        n = len(body)
        d = self.deltas(g, coords, n + 4, None)
        pts = []
        ends = []
        for k, (sub, dx, dy) in enumerate(body):
            sub_pts, sub_ends, _, _ = self.glyph(sub, coords)
            base = len(pts)
            pts += [[x + dx + d[k][0], y + dy + d[k][1], on] for x, y, on in sub_pts]
            ends += [e + base for e in sub_ends]
        return pts, ends, adv + d[n + 1][0] - d[n][0], d[n][0]


def whole(v, what):
    if v.denominator != 1:
        sys.exit('%s comes to %s, which isn\'t a whole number: the test is to be exact' % (what, v))
    return int(v)


def expected_text(font):
    lines = []
    lines.append('units %d glyphs %d' % (UPEM, font.n))
    for tag, lo, mid, hi in font.axes:
        lines.append('axis %s %d %d %d' % (tag.decode(), lo, mid, hi))
    lines.append('axis slnt: none')
    for place in PLACES:
        coords = font.normalize(place)
        lines.append('wght %d wdth %d' % place)
        for g in range(font.n):
            pts, ends, adv, pp1 = font.glyph(g, coords)
            adv = whole(adv, 'an advance')
            shift = whole(pp1, 'a phantom point')
            text = '%d: %d' % (g, adv)
            for x, y, on in pts:
                text += ' %d,%d%s' % (whole(x, 'x') - shift, whole(y, 'y'), '' if on else 'c')
            if ends:
                text += ' ends ' + ' '.join(str(e) for e in ends)
            lines.append(text)
    return lines


# ---------------------------------------------------------------- CoreText's word on it

SWIFT = r'''
import Foundation
import CoreText
let data = try! Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
guard let desc0 = CTFontManagerCreateFontDescriptorFromData(data as CFData) else { print("refused"); exit(1) }
let wght = NSNumber(value: 0x77676874)
let wdth = NSNumber(value: 0x77647468)
let vary: [NSNumber: NSNumber] = [wght: NSNumber(value: Double(CommandLine.arguments[2])!), wdth: NSNumber(value: Double(CommandLine.arguments[3])!)]
let desc = CTFontDescriptorCreateCopyWithAttributes(desc0, [kCTFontVariationAttribute: vary] as CFDictionary)
let upem = CGFloat(CTFontGetUnitsPerEm(CTFontCreateWithFontDescriptor(desc, 12, nil)))
let font = CTFontCreateWithFontDescriptor(desc, upem, nil)
let count = CTFontGetGlyphCount(font)
var glyphs = (0..<count).map { CGGlyph($0) }
var advances = [CGSize](repeating: .zero, count: count)
CTFontGetAdvancesForGlyphs(font, .horizontal, &glyphs, &advances, count)
for i in 0..<count {
    var box = CGRect.null
    if let path = CTFontCreatePathForGlyph(font, glyphs[i], nil) { box = path.boundingBoxOfPath }
    if box.isNull { print("\(i) \(advances[i].width) none"); continue }
    print("\(i) \(advances[i].width) \(box.minX) \(box.minY) \(box.maxX) \(box.maxY)")
}
'''


def curve_box(pts, ends):
    """the box of a glyph's curves (not of its control points), as a path's is"""
    xs = []
    ys = []
    start = 0
    for e in ends:
        c = pts[start:e + 1]
        start = e + 1
        n = len(c)
        for i in range(n):
            x, y, on = c[i]
            if on:
                xs.append(Fraction(x))
                ys.append(Fraction(y))
                continue
            # a control point: the curve between the points either side (or half way to a control point)
            def end(q):
                return (Fraction(q[0]), Fraction(q[1])) if q[2] else ((Fraction(q[0]) + x) / 2, (Fraction(q[1]) + y) / 2)
            (x0, y0), (x2, y2) = end(c[i - 1]), end(c[(i + 1) % n])
            for p0, p1, p2, out in ((x0, Fraction(x), x2, xs), (y0, Fraction(y), y2, ys)):
                out += [p0, p2]
                denom = p0 - 2 * p1 + p2
                if denom != 0:
                    t = (p0 - p1) / denom
                    if 0 < t < 1:
                        out.append((1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t * t * p2)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def check_coretext(font, path):
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'ct.swift')
        exe = os.path.join(tmp, 'ct')
        with open(src, 'w') as f:
            f.write(SWIFT)
        subprocess.run(['swiftc', '-O', src, '-o', exe], check=True, stderr=subprocess.DEVNULL)
        checked = 0
        for place in PLACES:
            out = subprocess.run([exe, path, str(place[0]), str(place[1])], capture_output=True, text=True).stdout
            if out.startswith('refused'):
                sys.exit('CoreText won\'t read the font')
            coords = font.normalize(place)
            for line in out.splitlines():
                f = line.split()
                g = int(f[0])
                pts, ends, adv, pp1 = font.glyph(g, coords)
                if abs(float(f[1]) - float(adv)) > 0.05:
                    sys.exit('at %s glyph %d: CoreText\'s advance is %s, the rules give %s' % (place, g, f[1], adv))
                box = curve_box(pts, ends)
                if box is None:
                    if f[2] != 'none':
                        sys.exit('at %s glyph %d: CoreText draws something, the rules nothing' % (place, g))
                    continue
                theirs = [float(v) for v in f[2:6]]
                ours = [float(box[0] - pp1), float(box[1]), float(box[2] - pp1), float(box[3])]
                if any(abs(a - b) > 0.05 for a, b in zip(theirs, ours)):
                    sys.exit('at %s glyph %d: CoreText\'s box is %s, the rules give %s' % (place, g, theirs, ours))
                checked += 1
        print('CoreText agrees: %d glyphs\' advances and boxes at %d places' % (checked, len(PLACES)))


def main():
    data = make_font()
    font = Font(data)
    lines = expected_text(font)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, 'made.ttf')
    with open(path, 'wb') as f:
        f.write(data)
    if '--coretext' in sys.argv:
        check_coretext(font, path)
    return path, lines


TRIES = 200     # the damaged copies test_var.phi makes of the font


if __name__ == '__main__':
    made, text = main()
    text.append('damaged: %d copies of it, cut short or with bytes changed, all came back' % TRIES)
    with open(EXPECTED, 'w') as f:
        f.write('\n'.join(text) + '\n')
    print('wrote %s (%d bytes) and %s (%d lines)' % (made, os.path.getsize(made), EXPECTED, len(text)))
