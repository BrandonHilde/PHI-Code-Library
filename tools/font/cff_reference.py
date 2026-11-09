"""CFF outlines (OpenType .otf fonts), as fontlib reads them, written plainly in Python: the rules
libs/font/fontlib/cff.phi follows. They're FreeType's (2.13, its CFF engine, unhinted):

  - The CFF table: its header (major version 1, a header of 4 bytes or more, offsets of 1 to 4 bytes),
    the Name, Top DICT, String and Global Subrs indexes, the first font's Top DICT (CharStrings, Private,
    CharstringType 2; for a CID-keyed font, FDArray and FDSelect) and Private DICT (local Subrs).
  - Type 2 charstrings, in 16.16 fixed point: every path operator (rmoveto, hmoveto, vmoveto, rlineto,
    hlineto, vlineto, rrcurveto, hhcurveto, vvcurveto, hvcurveto, vhcurveto, rcurveline, rlinecurve, and
    flex, hflex, hflex1, flex1), subroutines with their bias, the hint operators counted (so that
    hintmask and cntrmask skip the right number of bytes), and an odd first argument taken as the width.
  - A contour starts at its moveto, and is closed by a line back to its start if it isn't there; then,
    as FreeType's builder does, its last point is left out if it's on the curve and at its first, and a
    contour of one point is left out.
  - Points are whole font units: the 16.16 value, rounded down. At a size they're scaled with
    FT_MulFix, as TrueType's are. A glyph's advance is hmtx's, as FreeType takes it for CFF in an
    OpenType font.
  - Not done: seac accents (endchar with 4 arguments) and the arithmetic operators, which a font made
    in the last 25 years doesn't use; a glyph using them can't be loaded.
"""
from ttf_reference import u16, u32, Refused, w32, MOST_POINTS, MOST_CONTOURS


class Index:
    """a CFF INDEX at p: its items, as (start, end); and where it ends"""

    def __init__(self, d, p, limit):
        if p < 0 or p + 2 > limit:
            raise Refused('a CFF index past the end of the table')
        self.count = u16(d, p)
        self.items = []
        if self.count == 0:
            self.end = p + 2
            return
        if p + 3 > limit:
            raise Refused('a CFF index past the end of the table')
        size = d[p + 2]
        if size < 1 or size > 4:
            raise Refused('a CFF index with offsets of %d bytes' % size)
        offsets_at = p + 3
        data = offsets_at + (self.count + 1) * size - 1     # offsets count from the byte before the data
        if offsets_at + (self.count + 1) * size > limit:
            raise Refused('a CFF index past the end of the table')

        def offset(k):
            v = 0
            for b in d[offsets_at + k * size:offsets_at + (k + 1) * size]:
                v = v << 8 | b
            return v
        last = offset(self.count)
        if last < 1 or data + last > limit:
            raise Refused('a CFF index past the end of the table')
        prev = offset(0)
        for k in range(1, self.count + 1):
            v = offset(k)
            if v < prev or v > last:
                raise Refused('a CFF index whose offsets go backwards')
            self.items.append((data + prev, data + v))
            prev = v
        self.end = data + last


def dict_entries(d, start, end):
    """a DICT's (operator, operands) pairs; operators 12 x are 1200 + x"""
    out = []
    ops = []
    p = start
    while p < end:
        b = d[p]
        if b <= 21:
            if b == 12:
                if p + 1 >= end:
                    break
                op = 1200 + d[p + 1]
                p += 2
            else:
                op = b
                p += 1
            out.append((op, ops))
            ops = []
        elif b == 28:
            if p + 3 > end:
                break
            v = u16(d, p + 1)
            ops.append(v - 0x10000 if v & 0x8000 else v)
            p += 3
        elif b == 29:
            if p + 5 > end:
                break
            v = u32(d, p + 1)
            ops.append(v - 0x100000000 if v & 0x80000000 else v)
            p += 5
        elif b == 30:
            # a real: its nibbles, up to 0xf; kept only as a number we don't need exactly
            p += 1
            while p < end:
                hi, lo = d[p] >> 4, d[p] & 15
                p += 1
                if hi == 15 or lo == 15:
                    break
            ops.append(0)
        elif 32 <= b <= 246:
            ops.append(b - 139)
            p += 1
        elif 247 <= b <= 250:
            if p + 2 > end:
                break
            ops.append((b - 247) * 256 + d[p + 1] + 108)
            p += 2
        elif 251 <= b <= 254:
            if p + 2 > end:
                break
            ops.append(-(b - 251) * 256 - d[p + 1] - 108)
            p += 2
        else:
            p += 1          # 22 to 27, 31 and 255: reserved
    return out


def bias(count):
    return 107 if count < 1240 else 1131 if count < 33900 else 32768


class Cff:
    def __init__(self, d, start, length):
        end = start + length
        if length < 4:
            raise Refused('a CFF table too short for its header')
        major, hdr, offsize = d[start], d[start + 2], d[start + 3]
        if major != 1 or hdr < 4 or offsize < 1 or offsize > 4:
            raise Refused('a CFF table this isn\'t version 1 of')
        self.d = d
        names = Index(d, start + hdr, end)
        tops = Index(d, names.end, end)
        strings = Index(d, tops.end, end)
        self.gsubrs = Index(d, strings.end, end)
        if not tops.items:
            raise Refused('a CFF table with no font in it')
        top = dict(dict_entries(d, *tops.items[0]))
        if top.get(1206, [2])[:1] != [2]:
            raise Refused('charstrings that aren\'t Type 2')
        if 17 not in top or not top[17]:
            raise Refused('a CFF font with no charstrings')
        self.charstrings = Index(d, start + top[17][-1], end)
        self.privates = []      # (local subrs or None) for each font dict
        self.fd_select = None
        if 1230 in top:       # ROS: a CID-keyed font
            if 1236 not in top or 1237 not in top:
                raise Refused('a CID-keyed CFF font without FDArray or FDSelect')
            fds = Index(d, start + top[1236][-1], end)
            for fs, fe in fds.items:
                self.privates.append(self.private(dict(dict_entries(d, fs, fe)), start, end))
            self.fd_select = start + top[1237][-1]
            self.end = end
        else:
            self.privates.append(self.private(top, start, end))

    def private(self, dct, start, end):
        if 18 not in dct or len(dct[18]) < 2:
            return None
        size, off = dct[18][-2], dct[18][-1]
        ps = start + off
        if size < 0 or off < 0 or ps + size > end:
            raise Refused('a CFF Private DICT past the end of the table')
        priv = dict(dict_entries(self.d, ps, ps + size))
        if 19 in priv and priv[19]:
            return Index(self.d, ps + priv[19][-1], end)
        return None

    def font_dict(self, g):
        if self.fd_select is None:
            return 0
        d = self.d
        p = self.fd_select
        if p < 0 or p >= self.end:
            raise Refused('an FDSelect past the end of the table')
        fmt = d[p]
        if fmt == 0:
            if p + 1 + g >= self.end:
                raise Refused('an FDSelect past the end of the table')
            fd = d[p + 1 + g]
        elif fmt == 3:
            if p + 3 > self.end:
                raise Refused('an FDSelect past the end of the table')
            n = u16(d, p + 1)
            if p + 3 + 3 * n + 2 > self.end:
                raise Refused('an FDSelect past the end of the table')
            fd = None
            for k in range(n):
                q = p + 3 + 3 * k
                first, f, nxt = u16(d, q), d[q + 2], u16(d, q + 3)
                if first <= g < nxt:
                    fd = f
                    break
            if fd is None:
                raise Refused('a glyph FDSelect has no font dict for')
        else:
            raise Refused('an FDSelect of a format CFF doesn\'t have')
        if fd >= len(self.privates):
            raise Refused('a glyph whose font dict isn\'t there')
        return fd

    # ------------------------------------------------------------ charstrings

    def glyph(self, g):
        """(points in 16.16 font units, tags (1 on, 2 cubic control), contour ends)"""
        if g >= self.charstrings.count:
            raise Refused('no such glyph')
        subrs = self.privates[self.font_dict(g)]
        self.points, self.tags, self.ends = [], [], []
        self.stack = []
        self.stems = 0
        self.width_done = False
        self.x = self.y = 0
        self.open = False
        self.start = 0
        self.depth = 0
        self.run(*self.charstrings.items[g], subrs)
        self.close()
        return self.points, self.tags, self.ends

    def width(self, even):
        """the first stack-clearing operator's extra argument is the width"""
        if not self.width_done:
            self.width_done = True
            if (len(self.stack) % 2 == 1) == even and self.stack:
                self.stack.pop(0)

    def room(self, n):
        if len(self.points) + n > MOST_POINTS:
            raise Refused('a glyph with too many points')

    def move(self, dx, dy):
        self.close()
        self.room(1)
        self.x += dx
        self.y += dy
        self.start = len(self.points)
        self.points.append((self.x, self.y))
        self.tags.append(1)
        self.open = True

    def begin(self):
        """a line or curve with no contour open starts one where the pen is"""
        if not self.open:
            self.move(0, 0)

    def line(self, dx, dy):
        self.begin()
        self.room(1)
        self.x += dx
        self.y += dy
        self.points.append((self.x, self.y))
        self.tags.append(1)

    def curve(self, d1x, d1y, d2x, d2y, d3x, d3y):
        self.begin()
        self.room(3)
        x1, y1 = self.x + d1x, self.y + d1y
        x2, y2 = x1 + d2x, y1 + d2y
        self.x, self.y = x2 + d3x, y2 + d3y
        self.points += [(x1, y1), (x2, y2), (self.x, self.y)]
        self.tags += [2, 2, 1]

    def close(self):
        if not self.open:
            return
        self.open = False
        first = self.points[self.start]
        # FreeType's builder: the last point left out if it's on the curve and at the first
        if len(self.points) - self.start > 1 and self.points[-1] == first and self.tags[-1] == 1:
            self.points.pop()
            self.tags.pop()
        if len(self.points) - 1 == self.start:
            self.points.pop()
            self.tags.pop()
            return
        if len(self.ends) >= MOST_CONTOURS:
            raise Refused('a glyph with too many contours')
        self.ends.append(len(self.points) - 1)

    def run(self, p, end, subrs):
        d = self.d
        self.depth += 1
        if self.depth > 10:
            raise Refused('subroutines nested more than 10 deep')
        s = self.stack
        while p < end:
            b = d[p]
            p += 1
            if b >= 32 or b == 28 or b == 255:
                if b == 28:
                    if p + 2 > end:
                        raise Refused('a charstring cut short')
                    v = u16(d, p)
                    s.append((v - 0x10000 if v & 0x8000 else v) << 16)
                    p += 2
                elif b == 255:
                    if p + 4 > end:
                        raise Refused('a charstring cut short')
                    v = u32(d, p)
                    s.append(v - 0x100000000 if v & 0x80000000 else v)
                    p += 4
                elif b <= 246:
                    s.append((b - 139) << 16)
                elif b <= 250:
                    if p >= end:
                        raise Refused('a charstring cut short')
                    s.append(((b - 247) * 256 + d[p] + 108) << 16)
                    p += 1
                else:
                    if p >= end:
                        raise Refused('a charstring cut short')
                    s.append((-(b - 251) * 256 - d[p] - 108) << 16)
                    p += 1
                if len(s) > 48:
                    raise Refused('a charstring with more than 48 arguments')
                continue
            if b in (1, 3, 18, 23):                     # hstem, vstem, hstemhm, vstemhm
                self.width(True)
                self.stems += len(s) // 2
                s.clear()
            elif b in (19, 20):                         # hintmask, cntrmask
                self.width(True)
                self.stems += len(s) // 2
                s.clear()
                p += (self.stems + 7) // 8
            elif b == 21:                               # rmoveto
                self.width(True)
                if len(s) < 2:
                    raise Refused('a charstring short of arguments')
                self.move(s[-2], s[-1])
                s.clear()
            elif b in (22, 4):                          # hmoveto, vmoveto
                self.width(False)
                if not s:
                    raise Refused('a charstring short of arguments')
                self.move(s[-1], 0) if b == 22 else self.move(0, s[-1])
                s.clear()
            elif b == 5:                                # rlineto
                for k in range(0, len(s) - 1, 2):
                    self.line(s[k], s[k + 1])
                s.clear()
            elif b in (6, 7):                           # hlineto, vlineto
                horizontal = b == 6
                for v in s:
                    self.line(v, 0) if horizontal else self.line(0, v)
                    horizontal = not horizontal
                s.clear()
            elif b == 8:                                # rrcurveto
                for k in range(0, len(s) - 5, 6):
                    self.curve(*s[k:k + 6])
                s.clear()
            elif b == 24:                               # rcurveline
                k = 0
                while k + 6 <= len(s) - 2:
                    self.curve(*s[k:k + 6])
                    k += 6
                if k + 2 <= len(s):
                    self.line(s[k], s[k + 1])
                s.clear()
            elif b == 25:                               # rlinecurve
                k = 0
                while k + 2 <= len(s) - 6:
                    self.line(s[k], s[k + 1])
                    k += 2
                if k + 6 <= len(s):
                    self.curve(*s[k:k + 6])
                s.clear()
            elif b == 26:                               # vvcurveto
                k = 0
                dx1 = 0
                if len(s) % 4 == 1:
                    dx1 = s[0]
                    k = 1
                while k + 4 <= len(s):
                    self.curve(dx1, s[k], s[k + 1], s[k + 2], 0, s[k + 3])
                    dx1 = 0
                    k += 4
                s.clear()
            elif b == 27:                               # hhcurveto
                k = 0
                dy1 = 0
                if len(s) % 4 == 1:
                    dy1 = s[0]
                    k = 1
                while k + 4 <= len(s):
                    self.curve(s[k], dy1, s[k + 1], s[k + 2], s[k + 3], 0)
                    dy1 = 0
                    k += 4
                s.clear()
            elif b in (30, 31):                         # vhcurveto, hvcurveto
                horizontal = b == 31
                k = 0
                while k + 4 <= len(s):
                    last = len(s) - k == 5
                    extra = s[k + 4] if last else 0
                    if horizontal:
                        self.curve(s[k], 0, s[k + 1], s[k + 2], extra, s[k + 3])
                    else:
                        self.curve(0, s[k], s[k + 1], s[k + 2], s[k + 3], extra)
                    horizontal = not horizontal
                    k += 5 if last else 4
                s.clear()
            elif b in (10, 29):                         # callsubr, callgsubr
                if not s:
                    raise Refused('a charstring short of arguments')
                index = self.gsubrs if b == 29 else subrs
                if index is None:
                    raise Refused('a call to subroutines the font hasn\'t')
                n = (s.pop() >> 16) + bias(index.count)
                if n < 0 or n >= index.count:
                    raise Refused('a call to a subroutine that isn\'t there')
                if self.run(*index.items[n], subrs):
                    self.depth -= 1
                    return True
            elif b == 11:                               # return
                self.depth -= 1
                return False
            elif b == 14:                               # endchar
                self.width(True)
                if len(s) >= 4:
                    raise Refused('a seac accent, which isn\'t read yet')
                s.clear()
                self.depth -= 1
                return True
            elif b == 12:
                if p >= end:
                    raise Refused('a charstring cut short')
                e = d[p]
                p += 1
                if e == 35:                             # flex
                    if len(s) < 13:
                        raise Refused('a charstring short of arguments')
                    self.curve(*s[0:6])
                    self.curve(*s[6:12])
                elif e == 34:                           # hflex
                    if len(s) < 7:
                        raise Refused('a charstring short of arguments')
                    y0 = self.y
                    self.curve(s[0], 0, s[1], s[2], s[3], 0)
                    self.curve(s[4], 0, s[5], y0 - self.y, s[6], 0)
                elif e == 36:                           # hflex1
                    if len(s) < 9:
                        raise Refused('a charstring short of arguments')
                    self.curve(s[0], s[1], s[2], s[3], s[4], 0)
                    self.curve(s[5], 0, s[6], s[7], s[8], -(s[1] + s[3] + s[7]))
                elif e == 37:                           # flex1
                    if len(s) < 11:
                        raise Refused('a charstring short of arguments')
                    x0, y0 = self.x, self.y
                    dx = s[0] + s[2] + s[4] + s[6] + s[8]
                    dy = s[1] + s[3] + s[5] + s[7] + s[9]
                    self.curve(*s[0:6])
                    if abs(dx) > abs(dy):
                        self.curve(s[6], s[7], s[8], s[9], s[10], y0 - (self.y + s[7] + s[9]))
                    else:
                        self.curve(s[6], s[7], s[8], s[9], x0 - (self.x + s[6] + s[8]), s[10])
                else:
                    raise Refused('a charstring operator that isn\'t read yet (12 %d)' % e)
                s.clear()
            else:
                raise Refused('a charstring operator that isn\'t read yet (%d)' % b)
        self.depth -= 1
        return False


def outline(cff, g):
    """(points in whole font units, on-curve tags (1 on, 0 conic, 2 cubic), ends)"""
    pts, tags, ends = cff.glyph(g)
    return [(w32(x >> 16), w32(y >> 16)) for x, y in pts], tags, ends
