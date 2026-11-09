"""TrueType fonts, as fontlib reads them, written plainly in Python: the rules
libs/font/fontlib/truetype.phi follows, check for check, giving the same reasons.

Two references decide them, as they decide what browsers show:

  - The face, the glyphs' outlines and their metrics are FreeType's (FT_LOAD_NO_SCALE |
    FT_LOAD_NO_HINTING): its table directory, which tables it needs, its checks on each glyph, its
    composites (transforms, offsets, point matching, USE_MY_METRICS, loops refused), and the shift
    it gives an unhinted outline, so that its left edge is at the left side bearing.
  - Which glyph a character is: HarfBuzz's (hb_font_get_nominal_glyph), which is how browsers look a
    character up (HarfBuzz 15.0): its own reading of the table directory and of `cmap`, its choice of
    subtable (symbol (3,0) first, then (3,10), (0,6), (0,4), (3,1), (0,3), (0,2), (0,1), (0,0), Mac
    Roman (1,0), and any other Mac one), and its fallbacks: a symbol font's U+F000 to U+F0FF also at
    U+0000 to U+00FF (when OS/2 gives no "font page"), Mac Roman through its table, and only ASCII
    for other Mac encodings. A subtable its sanitizer fails leaves the font with no characters.

make_font_tests.py checks the rules against both, on Liberation Sans, on fonts it makes, and on those
cut short and fuzzed.
"""
import struct


class Refused(Exception):
    pass


def u16(d, p):
    return d[p] << 8 | d[p + 1]


def i16(d, p):
    v = d[p] << 8 | d[p + 1]
    return v - 0x10000 if v & 0x8000 else v


def u32(d, p):
    return d[p] << 24 | d[p + 1] << 16 | d[p + 2] << 8 | d[p + 3]


def w32(v):
    """v kept to 32 bits, as fontlib keeps a coordinate"""
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


# FreeType's most points and contours in one outline (FT_OUTLINE_POINTS_MAX, and CONTOURS_MAX)
MOST_POINTS = 32767
MOST_CONTOURS = 32767


def i8(v):
    return v - 256 if v & 0x80 else v


# ---------------------------------------------------------------- FreeType's fixed-point helpers

def mul_fix(a, b):
    """FT_MulFix: a * b / 65536, rounded half away from zero"""
    s = 1
    if a < 0:
        a, s = -a, -s
    if b < 0:
        b, s = -b, -s
    c = (a * b + 0x8000) >> 16
    return c if s > 0 else -c


ARCTAN = [1740967, 919879, 466945, 234379, 117304, 58666, 29335, 14668, 7334, 3667, 1833, 917, 458,
          229, 115, 57, 29, 14, 7, 4, 2, 1]
ANGLE_PI2 = 90 << 16
ANGLE_PI = 180 << 16


def _c32(v):
    """as a C long on the 64-bit systems FreeType is checked on: no change, but kept for clarity"""
    return v


def vector_length(x, y):
    """FT_Vector_Length (FT_Hypot): exact when either part is 0; otherwise CORDIC, as FreeType does it"""
    if x == 0:
        return abs(y)
    if y == 0:
        return abs(x)
    # prenorm
    m = (abs(x) | abs(y)) & 0xFFFFFFFF
    msb = m.bit_length() - 1
    if msb <= 29:
        shift = 29 - msb
        x <<= shift
        y <<= shift
    else:
        shift = msb - 29
        x >>= shift
        y >>= shift
        shift = -shift
    # pseudo-polarize: the vector into [-PI/4, PI/4], then rotations
    if y > x:
        if y > -x:
            x, y = y, -x
        else:
            x, y = -x, -y
    else:
        if y < -x:
            x, y = -y, x
    b = 1
    for i in range(1, 23):
        if y > 0:
            xt = x + ((y + b) >> i)
            y = y - ((x + b) >> i)
            x = xt
        else:
            xt = x - ((y + b) >> i)
            y = y + ((x + b) >> i)
            x = xt
        b <<= 1
    # downscale
    s = 1
    v = x
    if v < 0:
        v, s = -v, -1
    v = (v * 0xDBD95B16 + 0x100000000) >> 32
    v = v if s > 0 else -v
    if shift > 0:
        return (v + (1 << (shift - 1))) >> shift
    return (v << -shift) & 0xFFFFFFFF


# ---------------------------------------------------------------- FreeType: the face



class Face:
    def __init__(self, data):
        self.data = d = data
        if len(d) < 12:
            raise Refused('not a font file')
        tag = d[:4]
        if tag == b'OTTO':
            raise Refused('CFF outlines (an OpenType .otf font), which aren\'t read yet')
        if tag == b'ttcf':
            raise Refused('a font collection, which isn\'t read yet')
        if tag not in (b'\x00\x01\x00\x00', b'true'):
            raise Refused('not a TrueType font')
        n = u16(d, 4)
        # the directory: as many entries as there are; FreeType keeps those inside the file, and
        # clips hmtx's length to the file, to a multiple of 4
        self.tables = []
        for k in range(n):
            p = 12 + 16 * k
            if p + 16 > len(d):
                break
            t, off, length = bytes(d[p:p + 4]), u32(d, p + 8), u32(d, p + 12)
            if off > len(d):
                continue
            if length > len(d) - off:
                if t != b'hmtx':
                    continue
                length = (len(d) - off) & ~3
            self.tables.append((t, off, length))
        if not self.tables:
            raise Refused('a font with no tables')
        head = self.table(b'head')
        if head is None or head[1] < 0x36:
            raise Refused('a font with no head table')
        hp = head[0]
        if hp + 54 > len(d):
            raise Refused('the file is cut short')
        self.units_per_em = u16(d, hp + 18)
        if self.units_per_em < 16 or self.units_per_em > 16384:
            raise Refused('units per em of %d, which isn\'t 16 to 16384' % self.units_per_em)
        self.x_min, self.y_min, self.x_max, self.y_max = (i16(d, hp + 36 + 2 * k) for k in range(4))
        self.long_loca = i16(d, hp + 50) != 0
        # no maxp is no glyphs, as FreeType has it
        maxp = self.table(b'maxp')
        self.num_glyphs = 0
        if maxp is not None:
            if maxp[0] + 6 > len(d):
                raise Refused('the file is cut short')
            self.num_glyphs = u16(d, maxp[0] + 4)
        hhea = self.table(b'hhea')
        self.mac = hhea is None and tag == b'true'
        if self.mac:
            # FreeType's "SFNT Mac font": no hhea is allowed, and then no metrics at all
            self.ascender = self.descender = self.line_gap = self.max_advance = self.long_metrics = 0
            self.hmtx = (0, 0)
        elif hhea is None:
            raise Refused('a font with no hhea table')
        else:
            if hhea[0] + 36 > len(d):
                raise Refused('the file is cut short')
            p = hhea[0]
            self.ascender, self.descender, self.line_gap = i16(d, p + 4), i16(d, p + 6), i16(d, p + 8)
            self.max_advance = u16(d, p + 10)
            self.long_metrics = u16(d, p + 34)
            hmtx = self.table(b'hmtx')
            if hmtx is None:
                raise Refused('a font with no hmtx table')
            self.hmtx = hmtx
        # glyf and loca: no glyf is no outlines; no loca refuses the font
        glyf = self.table(b'glyf')
        self.glyf = glyf if glyf is not None else (0, 0)
        loca = self.table(b'loca')
        if loca is None:
            raise Refused('a font with no loca table')
        shift = 2 if self.long_loca else 1
        if loca[1] >= (0x40000 if self.long_loca else 0x20000):
            raise Refused('a loca table too big for the glyphs it can have')
        self.loca = loca
        self.num_locations = loca[1] >> shift
        if self.num_locations != self.num_glyphs + 1 and self.num_locations <= self.num_glyphs:
            # FreeType: if the bytes up to the next table (or the end) can hold loca for every glyph,
            # it's taken as that long; otherwise there are fewer glyphs
            want = (self.num_glyphs + 1) << shift
            dist = None
            for _, off, _ in self.tables:
                diff = off - loca[0]
                if diff > 0 and (dist is None or diff < dist):
                    dist = diff
            if dist is None:
                dist = len(d) - loca[0]
            if want <= dist:
                self.num_locations = self.num_glyphs + 1
            else:
                self.num_glyphs = self.num_locations - 1 if self.num_locations else 0
        # the line, as FreeType has it: OS/2's typo metrics when its USE_TYPO_METRICS bit is set; or
        # else hhea's, or OS/2's when hhea's ascender and descender are both 0. OS/2 counts if its
        # fields for its version are in the file. The height is kept in 16 bits, and made positive.
        os2 = self.os2()
        if self.mac:
            self.height = 0
            return
        if os2 is not None and u16(d, os2 + 62) & 128:
            self.ascender, self.descender = i16(d, os2 + 68), i16(d, os2 + 70)
            height = self.ascender - self.descender + i16(d, os2 + 72)
        else:
            height = self.ascender - self.descender + self.line_gap
            if self.ascender == 0 and self.descender == 0 and os2 is not None:
                ta, td, tg = i16(d, os2 + 68), i16(d, os2 + 70), i16(d, os2 + 72)
                if ta or td:
                    self.ascender, self.descender = ta, td
                    height = ta - td + tg
                else:
                    self.ascender, self.descender = i16s(u16(d, os2 + 74)), -i16s(u16(d, os2 + 76))
                    height = self.ascender - self.descender
        height = i16s(height)
        if height < 0:
            height = i16s(-height)
        self.height = height
        self.max_advance = i16s(self.max_advance)

    def os2(self):
        """where OS/2 starts, if FreeType can read it: its version's fields all in the file"""
        t = self.table(b'OS/2')
        if t is None:
            return None
        q = t[0]
        d = self.data
        if q + 78 > len(d):
            return None
        version = u16(d, q)
        need = 78 + (8 if version >= 1 else 0) + (10 if version >= 2 else 0) + (4 if version >= 5 else 0)
        return q if q + need <= len(d) else None

    def table(self, tag):
        """FreeType's: the first entry with the tag and a length that isn't 0"""
        for t, off, length in self.tables:
            if t == tag and length != 0:
                return off, length
        return None

    def metrics(self, g):
        """(advance, left side bearing) from hmtx, as tt_face_get_metrics reads them"""
        d = self.data
        off, size = self.hmtx
        end = off + size
        k = self.long_metrics
        if k == 0:
            return 0, 0
        if g < k:
            p = off + 4 * g
            if p + 4 > end:
                return 0, 0
            return u16(d, p), i16(d, p + 2)
        p = off + 4 * (k - 1)
        if p + 2 > end:
            return 0, 0
        adv = u16(d, p)
        p = off + 4 * k + 2 * (g - k)
        lsb = i16(d, p) if p + 2 <= end else 0
        return adv, lsb

    def location(self, g):
        """(offset in glyf, length) as tt_face_get_location gives them"""
        d = self.data
        off, size = self.loca
        if g >= self.num_locations - 1:
            return 0, 0
        if self.long_loca:
            p = off + 4 * g
            pos1 = u32(d, p) if p + 4 <= len(d) else None
            pos2 = u32(d, p + 4) if p + 8 <= off + self.num_locations * 4 and p + 8 <= len(d) else pos1
        else:
            p = off + 2 * g
            pos1 = u16(d, p) * 2 if p + 2 <= len(d) else None
            pos2 = u16(d, p + 2) * 2 if p + 4 <= off + self.num_locations * 2 and p + 4 <= len(d) else pos1
        if pos1 is None:
            return 0, 0
        glyf_len = self.glyf[1]
        if pos1 > glyf_len:
            return 0, 0
        if pos2 > glyf_len:
            if g == self.num_locations - 2:
                pos2 = glyf_len
            else:
                return 0, 0
        return pos1, (pos2 - pos1 if pos2 >= pos1 else pos1 - pos2)

    # ------------------------------------------------------------ glyphs

    def glyph(self, g, scale=0):
        """(points [(x, y)], on-curve flags, contour ends, advance), or a str: why it can't be loaded.
        With a scale (16.16, font units to 26.6 pixels), the points are scaled as FreeType scales them:
        each simple glyph's as it's loaded, then composites' transforms and (scaled) offsets, then the
        shift; the advance stays in font units, and pp1 (in font units) is kept in self.pp1."""
        if g >= self.num_glyphs:
            return 'no such glyph'
        self.scale = scale
        self.loading = []
        self.points = []
        self.flags = []
        self.ends = []
        try:
            pp1, adv = self.load(g, 0)
        except Refused as e:
            return str(e)
        self.pp1 = pp1
        shift = mul_fix(pp1, scale) if scale else pp1
        if shift:
            self.points = [(w32(x - shift), y) for x, y in self.points]
        return self.points, self.flags, self.ends, adv

    def load(self, g, depth):
        """loads glyph g's points onto the outline; gives its phantom point 1's x and its advance"""
        d = self.data
        adv, lsb = self.metrics(g)
        pos, size = self.location(g)
        if size == 0:
            return -lsb, adv           # pp1.x = 0 - lsb: an empty glyph's bbox is 0
        p = self.glyf[0] + pos
        if p + size > len(d):
            raise Refused('a glyph past the end of the file')
        limit = p + size
        if size < 10:
            raise Refused('a glyph too short for its header')
        n_contours = i16(d, p)
        x_min = i16(d, p + 2)
        pp1 = x_min - lsb
        if n_contours == 0:
            return pp1, adv
        q = p + 10
        if n_contours > 0:
            self.simple(q, limit, n_contours)
            return pp1, adv
        # a composite
        if g in self.loading:
            raise Refused('a composite glyph that contains itself')
        self.loading.append(g)
        subs = []
        while True:
            if q + 4 > limit:
                raise Refused('a composite glyph cut short')
            flags, index = u16(d, q), u16(d, q + 2)
            q += 4
            if index >= self.num_glyphs:
                raise Refused('a component that isn\'t a glyph')
            count = 2
            if flags & 1:
                count += 2
            if flags & 8:
                count += 2
            elif flags & 0x40:
                count += 4
            elif flags & 0x80:
                count += 8
            if q + count > limit:
                raise Refused('a composite glyph cut short')
            if flags & 2:
                if flags & 1:
                    a1, a2 = i16(d, q), i16(d, q + 2)
                    q += 4
                else:
                    a1, a2 = i8(d[q]), i8(d[q + 1])
                    q += 2
            else:
                if flags & 1:
                    a1, a2 = u16(d, q), u16(d, q + 2)
                    q += 4
                else:
                    a1, a2 = d[q], d[q + 1]
                    q += 2
            xx = yy = 0x10000
            xy = yx = 0
            if flags & 8:
                xx = yy = i16(d, q) * 4
                q += 2
            elif flags & 0x40:
                xx, yy = i16(d, q) * 4, i16(d, q + 2) * 4
                q += 4
            elif flags & 0x80:
                xx, yx, xy, yy = (i16(d, q + 2 * k) * 4 for k in range(4))
                q += 8
            subs.append((flags, index, a1, a2, xx, xy, yx, yy))
            if not flags & 0x20:
                break
        start_point = len(self.points)
        for flags, index, a1, a2, xx, xy, yx, yy in subs:
            base = len(self.points)
            sub_pp1, sub_adv = self.load(index, depth + 1)
            if flags & 0x200:              # USE_MY_METRICS
                pp1, adv = sub_pp1, sub_adv
            if len(self.points) == base:
                continue
            have_scale = bool(flags & (8 | 0x40 | 0x80))
            if have_scale:
                for i in range(base, len(self.points)):
                    x, y = self.points[i]
                    self.points[i] = (w32(mul_fix(x, xx) + mul_fix(y, xy)), w32(mul_fix(x, yx) + mul_fix(y, yy)))
            if not flags & 2:
                k, l = a1 + start_point, a2 + base
                if k >= base or l >= len(self.points):
                    raise Refused('a component matched to a point it doesn\'t have')
                dx = w32(self.points[k][0] - self.points[l][0])
                dy = w32(self.points[k][1] - self.points[l][1])
            else:
                dx, dy = a1, a2
                if not dx and not dy:
                    continue
                if have_scale and flags & 0x800:     # SCALED_COMPONENT_OFFSET
                    dx = w32(mul_fix(dx, vector_length(xx, xy)))
                    dy = w32(mul_fix(dy, vector_length(yy, yx)))
                if self.scale:
                    dx = w32(mul_fix(dx, self.scale))
                    dy = w32(mul_fix(dy, self.scale))
            if dx or dy:
                for i in range(base, len(self.points)):
                    x, y = self.points[i]
                    self.points[i] = (w32(x + dx), w32(y + dy))
        self.loading.pop()
        return pp1, adv

    def simple(self, q, limit, n_contours):
        d = self.data
        if len(self.ends) + n_contours > MOST_CONTOURS:
            raise Refused('a glyph with too many contours')
        if n_contours >= 0xFFF or q + (n_contours + 1) * 2 > limit:
            raise Refused('a glyph cut short')
        # the contours' last points, as 16-bit signed numbers, each after the one before
        ends = []
        prev = i16(d, q)
        if prev < 0:
            raise Refused('a glyph whose contours aren\'t in order')
        ends.append(prev)
        for k in range(1, n_contours):
            e = i16(d, q + 2 * k)
            if e <= prev:
                raise Refused('a glyph whose contours aren\'t in order')
            ends.append(e)
            prev = e
        q += 2 * n_contours
        n_points = ends[-1] + 1
        # FreeType's limit, with room for its 4 phantom points
        if len(self.points) + n_points + 4 > MOST_POINTS:
            raise Refused('a glyph with too many points')
        n_ins = u16(d, q)
        q += 2
        if limit - q < n_ins:
            raise Refused('a glyph whose instructions run past its end')
        q += n_ins
        flags = []
        while len(flags) < n_points:
            if q + 1 > limit:
                raise Refused('a glyph cut short')
            c = d[q]
            q += 1
            flags.append(c)
            if c & 8:
                if q + 1 > limit:
                    raise Refused('a glyph cut short')
                count = d[q]
                q += 1
                if len(flags) + count > n_points:
                    raise Refused('a glyph whose flags run past its points')
                flags.extend([c] * count)
        xs = []
        x = 0
        for f in flags:
            if f & 2:
                if q + 1 > limit:
                    raise Refused('a glyph cut short')
                delta = d[q] if f & 0x10 else -d[q]
                q += 1
            elif not f & 0x10:
                if q + 2 > limit:
                    raise Refused('a glyph cut short')
                delta = i16(d, q)
                q += 2
            else:
                delta = 0
            x += delta
            xs.append(x)
        y = 0
        base = len(self.points)
        for i, f in enumerate(flags):
            if f & 4:
                if q + 1 > limit:
                    raise Refused('a glyph cut short')
                delta = d[q] if f & 0x20 else -d[q]
                q += 1
            elif not f & 0x20:
                if q + 2 > limit:
                    raise Refused('a glyph cut short')
                delta = i16(d, q)
                q += 2
            else:
                delta = 0
            y += delta
            if self.scale:
                self.points.append((w32(mul_fix(xs[i], self.scale)), w32(mul_fix(y, self.scale))))
            else:
                self.points.append((xs[i], y))
            self.flags.append(f & 1)
        self.ends.extend(e + base for e in ends)


def i16s(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


# ---------------------------------------------------------------- HarfBuzz: characters to glyphs

# Unicode to Mac OS Roman's top half, for HarfBuzz's Mac Roman fallback
MAC_ROMAN = {ord(bytes([b]).decode('mac_roman')): b for b in range(128, 256)}


class Cmap:
    """a font's characters, as HarfBuzz looks them up"""

    def __init__(self, data):
        self.d = data
        self.sub = None
        self.records = []
        self.symbol = self.mac = False
        blob = hb_table(data, b'cmap')
        if blob is None:
            return
        start, end = blob
        d = data
        if end - start < 4 or u16(d, start) != 0:
            return
        n = u16(d, start + 2)
        if start + 4 + 8 * n > end:
            return
        records = []
        for k in range(n):
            p = start + 4 + 8 * k
            pid, eid, off = u16(d, p), u16(d, p + 2), u32(d, p + 4)
            sub = None
            if off:
                sub = sanitize_subtable(d, start + off, end) if start + off <= end else None
                if sub is None:
                    # one subtable HarfBuzz's sanitizer fails leaves the font with no characters
                    self.records = records
                    return
            records.append((pid, eid, sub))
        self.records = records

        def find(pid, eid):
            # HarfBuzz's binary search over the records, by (platform, encoding); an encoding of
            # 0xFFFF matches any
            lo, hi = 0, len(records) - 1
            while lo <= hi:
                mid = (lo + hi) // 2
                rp, re = records[mid][0], records[mid][1]
                c = (pid > rp) - (pid < rp)
                if c == 0 and eid != 0xFFFF:
                    c = (eid > re) - (eid < re)
                if c < 0:
                    hi = mid - 1
                elif c > 0:
                    lo = mid + 1
                else:
                    return records[mid][2] if records[mid][2] else None
            return None
        self.kind = 'plain'
        s = find(3, 0)
        if s is not None:
            self.sub = s
            # the fallback only when OS/2 gives no font page (its version 0, fsSelection's top byte)
            page = os2_font_page(d)
            self.kind = 'symbol' if page == 0 else 'plain'
            return
        for pid, eid in ((3, 10), (0, 6), (0, 4), (3, 1), (0, 3), (0, 2), (0, 1), (0, 0)):
            s = find(pid, eid)
            if s is not None:
                self.sub = s
                return
        s = find(1, 0)
        if s is not None:
            self.sub, self.kind = s, 'macroman'
            return
        s = find(1, 0xFFFF)
        if s is not None:
            self.sub, self.kind = s, 'ascii'

    def glyph(self, u):
        if self.sub is None:
            return 0
        if self.kind == 'ascii':
            return lookup(self.d, self.sub, u) if u < 0x80 else 0
        if self.kind == 'macroman':
            if u < 0x80:
                g = lookup(self.d, self.sub, u)
                if g:
                    return g
            # (HarfBuzz looks the character up in its Mac Roman table as 16 bits)
            m = MAC_ROMAN.get(u & 0xFFFF, 0)
            return lookup(self.d, self.sub, m) if m else 0
        g = lookup(self.d, self.sub, u)
        if g or self.kind != 'symbol':
            return g
        return lookup(self.d, self.sub, 0xF000 + u) if u <= 0xFF else 0


def os2_font_page(d):
    """HarfBuzz's font page: OS/2 version 0's fsSelection & 0xFF00, if its OS/2 passes the sanitizer"""
    t = hb_table(d, b'OS/2')
    if t is None:
        return 0
    start, end = t
    if end - start < 78:
        return 0
    version = u16(d, start)
    need = 78 + (8 if version >= 1 else 0) + (10 if version >= 2 else 0) + (4 if version >= 5 else 0)
    if end - start < need:
        return 0
    return u16(d, start + 62) & 0xFF00 if version == 0 else 0


def hb_table(d, tag):
    """HarfBuzz's table blob: (start, end) in the file, clamped to it; None if it isn't there"""
    if len(d) < 12:
        return None
    n = u16(d, 4)
    if 12 + 16 * n > len(d):
        return None
    # HarfBuzz looks tags up with a binary search, as the directory is meant to be sorted
    lo, hi = 0, n - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        p = 12 + 16 * mid
        t = bytes(d[p:p + 4])
        if tag < t:
            hi = mid - 1
        elif tag > t:
            lo = mid + 1
        else:
            off, length = u32(d, p + 8), u32(d, p + 12)
            if off >= len(d):
                return None
            return off, min(len(d), off + length)
    return None


def sanitize_subtable(d, p, end):
    """(format, start, end) of a subtable HarfBuzz's sanitizer passes, or None"""
    if p + 2 > end:
        return None
    fmt = u16(d, p)
    if fmt == 0:
        return (0, p, end) if p + 262 <= end else None
    if fmt == 4:
        # only its arrays must fit: its length field isn't used, and its glyph array runs to the
        # end of cmap
        if p + 14 > end:
            return None
        seg2 = u16(d, p + 6)
        return (4, p, end) if p + 16 + 4 * seg2 <= end else None
    if fmt == 6:
        if p + 10 > end:
            return None
        count = u16(d, p + 8)
        return (6, p, end) if p + 10 + 2 * count <= end else None
    if fmt in (12, 13):
        if p + 16 > end:
            return None
        n = u32(d, p + 12)
        return (fmt, p, end) if p + 16 + 12 * n <= end else None
    if fmt == 10:
        if p + 20 > end:
            return None
        count = u32(d, p + 16)
        return (10, p, end) if p + 20 + 2 * count <= end else None
    # every other format passes (2, 8, 14 and those GIF doesn't have), but isn't used to look
    # characters up
    return (fmt, p, end)


def lookup(d, sub, u):
    fmt, p, end = sub
    if fmt == 0:
        return d[p + 6 + u] if u < 256 else 0
    if fmt == 4:
        seg = u16(d, p + 6) // 2
        ends = p + 14
        starts = ends + 2 * seg + 2
        deltas = starts + 2 * seg
        ranges = deltas + 2 * seg
        glyphs = ranges + 2 * seg
        glyph_count = (end - p - 16 - 8 * seg) // 2
        lo, hi = 0, seg - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            # (HarfBuzz compares with the segment's end first)
            if u > u16(d, ends + 2 * mid):
                lo = mid + 1
            elif u < u16(d, starts + 2 * mid):
                hi = mid - 1
            else:
                ro = u16(d, ranges + 2 * mid)
                delta = u16(d, deltas + 2 * mid)
                if ro == 0:
                    g = (u + delta) & 0xFFFF
                else:
                    index = ro // 2 + (u - u16(d, starts + 2 * mid)) + mid - seg
                    if index < 0 or index >= glyph_count:     # (unsigned, in HarfBuzz)
                        return 0
                    g = u16(d, glyphs + 2 * index)
                    if not g:
                        return 0
                    g = (g + delta) & 0xFFFF
                return g
        return 0
    if fmt == 6:
        first, count = u16(d, p + 6), u16(d, p + 8)
        return u16(d, p + 10 + 2 * (u - first)) if first <= u < first + count else 0
    if fmt == 10:
        first, count = u32(d, p + 12), u32(d, p + 16)
        return u16(d, p + 20 + 2 * (u - first)) if first <= u < first + count else 0
    if fmt in (12, 13):
        n = u32(d, p + 12)
        lo, hi = 0, n - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            q = p + 16 + 12 * mid
            start, stop, g = u32(d, q), u32(d, q + 4), u32(d, q + 8)
            if u < start:
                hi = mid - 1
            elif u > stop:
                lo = mid + 1
            else:
                if fmt == 13:
                    return g
                return g + (u - start) if start <= stop else 0
        return 0
    return 0
