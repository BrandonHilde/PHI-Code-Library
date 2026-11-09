"""Kerning, as fontlib applies it, written plainly in Python: the rules libs/font/fontlib/kern.phi
follows. They're HarfBuzz's, with only its `kern` feature on:

  - GPOS, if it has a `kern` feature anywhere: the script asked for (or else DFLT, dflt, latn), its
    default language system, and the lookups of its `kern` features, applied in the order of their
    indexes. Pair adjustment (lookup type 2, or 9 wrapping it), formats 1 (pairs of glyphs) and 2
    (pairs of classes); each lookup's subtables tried in turn until one applies. A lookup skips the
    glyphs its flags say to (marks, base glyphs, ligatures, by GDEF's glyph classes; marks not of its
    attachment type; marks not in its filtering set), both as the first glyph and when looking for
    the second. A pair's first value goes to the first glyph, its second to the second, and when there
    is a second value the second glyph isn't the first of a pair after it. XAdvance adds to a glyph's
    advance, XPlacement to its offset, each scaled as advances are; device tables are left out (as
    HarfBuzz leaves them out when no ppem is set).
  - Otherwise the `kern` table (version 0), its format 0 subtables that are horizontal and not
    cross-stream: each pair's value (scaled) split between the two glyphs, half (rounded down) to the
    first's advance, the rest to the second's advance and offset, marks skipped as above.
  - Kerning is within a run of glyphs from one font: not across fallback.

Damaged GPOS, GDEF and kern tables are read as far as they can be, where HarfBuzz may reject the whole
table; make_text_tests.py checks the rules against HarfBuzz on fonts that aren't damaged.
"""
import struct

from ttf_reference import u16, i16, u32, hb_table


def tag(s):
    return struct.unpack('>I', s.encode())[0]


class Reader:
    """a table's bytes, read with bounds: anything outside reads as 0"""

    def __init__(self, data, start, end):
        self.d, self.start, self.end = data, start, end

    def u16(self, p):
        return u16(self.d, p) if self.start <= p and p + 2 <= self.end else 0

    def i16(self, p):
        v = self.u16(p)
        return v - 0x10000 if v & 0x8000 else v

    def u32(self, p):
        return u32(self.d, p) if self.start <= p and p + 4 <= self.end else 0


def coverage(r, p, g):
    """glyph g's index in the coverage table at p, or -1"""
    fmt = r.u16(p)
    if fmt == 1:
        n = r.u16(p + 2)
        lo, hi = 0, n - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            v = r.u16(p + 4 + 2 * mid)
            if g < v:
                hi = mid - 1
            elif g > v:
                lo = mid + 1
            else:
                return mid
        return -1
    if fmt == 2:
        n = r.u16(p + 2)
        lo, hi = 0, n - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            q = p + 4 + 6 * mid
            start, end = r.u16(q), r.u16(q + 2)
            if g < start:
                hi = mid - 1
            elif g > end:
                lo = mid + 1
            else:
                return r.u16(q + 4) + g - start
        return -1
    return -1


def class_of(r, p, g):
    """glyph g's class in the class definition at p (0 if it has none)"""
    if not p:
        return 0
    fmt = r.u16(p)
    if fmt == 1:
        first, n = r.u16(p + 2), r.u16(p + 4)
        return r.u16(p + 6 + 2 * (g - first)) if first <= g < first + n else 0
    if fmt == 2:
        n = r.u16(p + 2)
        lo, hi = 0, n - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            q = p + 4 + 6 * mid
            start, end = r.u16(q), r.u16(q + 2)
            if g < start:
                hi = mid - 1
            elif g > end:
                lo = mid + 1
            else:
                return r.u16(q + 4)
        return 0
    return 0


class Gdef:
    def __init__(self, data):
        t = hb_table(data, b'GDEF')
        self.r = None
        if t is None:
            return
        r = Reader(data, t[0], t[1])
        s = t[0]
        self.r = r
        self.version = r.u32(s)
        self.glyph_classes = s + r.u16(s + 4) if r.u16(s + 4) else 0
        self.mark_classes = s + r.u16(s + 10) if r.u16(s + 10) else 0
        sets = r.u16(s + 12) if self.version >= 0x00010002 else 0
        self.mark_sets = s + sets if sets else 0

    def glyph_class(self, g):
        return class_of(self.r, self.glyph_classes, g) if self.r and self.glyph_classes else 0

    def skips(self, g, flag, mark_set):
        """whether a lookup with flag skips glyph g"""
        c = self.glyph_class(g)
        if c == 1 and flag & 2:
            return True
        if c == 2 and flag & 4:
            return True
        if c == 3:
            if flag & 8:
                return True
            if flag & 0x10:
                # in the mark filtering set, or skipped
                p = self.mark_sets
                if not p or mark_set >= self.r.u16(p + 2):
                    return True
                cov = p + self.r.u32(p + 4 + 4 * mark_set)
                return coverage(self.r, cov, g) < 0
            if flag & 0xFF00:
                return class_of(self.r, self.mark_classes, g) != flag >> 8
        return False


class Kern:
    """a font's kerning: apply(glyphs, scale_mult) gives each glyph's (advance, offset) adjustments"""

    def __init__(self, data, script='latn'):
        self.data = data
        self.gdef = Gdef(data)
        self.lookups = []
        self.kern = None
        t = hb_table(data, b'GPOS')
        if t is not None and self.has_kern_feature(Reader(data, t[0], t[1]), t[0]):
            self.gpos = Reader(data, t[0], t[1])
            self.lookups = self.kern_lookups(self.gpos, t[0], script)
            return
        k = hb_table(data, b'kern')
        if k is not None:
            self.kern = Reader(data, k[0], k[1])

    @staticmethod
    def has_kern_feature(r, s):
        fl = s + r.u16(s + 6)
        n = r.u16(fl)
        return any(r.u32(fl + 2 + 6 * k) == tag('kern') for k in range(n))

    def kern_lookups(self, r, s, script):
        sl = s + r.u16(s + 4)
        fl = s + r.u16(s + 6)
        ll = s + r.u16(s + 8)
        n = r.u16(sl)
        chosen = None
        for want in (script, 'DFLT', 'dflt', 'latn'):
            for k in range(n):
                if r.u32(sl + 2 + 6 * k) == tag(want):
                    chosen = sl + r.u16(sl + 6 + 6 * k)     # the first record with the tag
                    break
            if chosen is not None:
                break
        if chosen is None:
            return []
        dl = r.u16(chosen)
        if not dl:
            return []
        ls = chosen + dl
        indexes = []
        req = r.u16(ls + 2)
        count = r.u16(ls + 4)
        feats = [r.u16(ls + 6 + 2 * k) for k in range(count)]
        if req != 0xFFFF:
            feats = [req] + feats
        nfeat = r.u16(fl)
        lookups = set()
        for f in feats:
            if f >= nfeat:
                continue
            if r.u32(fl + 2 + 6 * f) != tag('kern'):
                continue
            fp = fl + r.u16(fl + 6 + 6 * f)
            for k in range(r.u16(fp + 2)):
                lookups.add(r.u16(fp + 4 + 2 * k))
        out = []
        nl = r.u16(ll)
        for i in sorted(lookups):
            if i >= nl:
                continue
            lp = ll + r.u16(ll + 2 + 2 * i)
            ltype, flag, nsub = r.u16(lp), r.u16(lp + 2), r.u16(lp + 4)
            subs = []
            for k in range(nsub):
                sp = lp + r.u16(lp + 6 + 2 * k)
                t = ltype
                if t == 9:
                    t = r.u16(sp + 2)
                    sp = sp + r.u32(sp + 4)
                if t == 2:
                    subs.append(sp)
            mark_set = r.u16(lp + 6 + 2 * nsub) if flag & 0x10 else 0
            if subs:
                out.append((flag, mark_set, subs))
        return out

    def skipped(self, g, flag, mark_set):
        return self.gdef.r is not None and self.gdef.skips(g, flag, mark_set)

    def apply(self, glyphs, mult):
        """[(advance adjustment, offset adjustment)] in 64ths of a pixel, for glyphs of one font"""
        n = len(glyphs)
        adj = [[0, 0] for _ in range(n)]
        scaled = lambda v: (v * mult + 32768) >> 16  # noqa: E731
        if self.lookups:
            r = self.gpos
            for flag, mark_set, subs in self.lookups:
                i = 0
                while i < n:
                    if self.skipped(glyphs[i], flag, mark_set):
                        i += 1
                        continue
                    j = i + 1
                    while j < n and self.skipped(glyphs[j], flag, mark_set):
                        j += 1
                    if j >= n:
                        i += 1
                        continue
                    done = None
                    for sp in subs:
                        done = self.pair(r, sp, glyphs[i], glyphs[j])
                        if done is not None:
                            break
                    if done is None:
                        i += 1
                        continue
                    (a1, o1), (a2, o2), second = done
                    adj[i][0] += scaled(a1)
                    adj[i][1] += scaled(o1)
                    adj[j][0] += scaled(a2)
                    adj[j][1] += scaled(o2)
                    i = j + 1 if second else j
        elif self.kern is not None:
            self.legacy(glyphs, adj, scaled)
        return adj

    @staticmethod
    def value(r, p, fmt):
        """(XAdvance, XPlacement) of the value record at p, and its length"""
        a = o = 0
        q = p
        if fmt & 1:
            o = r.i16(q)
            q += 2
        if fmt & 2:
            q += 2
        if fmt & 4:
            a = r.i16(q)
            q += 2
        q += 2 * bin(fmt & 0xF8).count('1')
        return (a, o), q - p

    def pair(self, r, sp, g1, g2):
        fmt = r.u16(sp)
        cov = coverage(r, sp + r.u16(sp + 2), g1)
        if cov < 0:
            return None
        vf1, vf2 = r.u16(sp + 4), r.u16(sp + 6)
        len1 = 2 * bin(vf1 & 0xFF).count('1')
        len2 = 2 * bin(vf2 & 0xFF).count('1')
        if fmt == 1:
            if cov >= r.u16(sp + 8):
                return None
            ps = sp + r.u16(sp + 10 + 2 * cov)
            count = r.u16(ps)
            rec = 2 + len1 + len2
            lo, hi = 0, count - 1
            while lo <= hi:
                mid = (lo + hi) // 2
                q = ps + 2 + rec * mid
                second = r.u16(q)
                if g2 < second:
                    hi = mid - 1
                elif g2 > second:
                    lo = mid + 1
                else:
                    v1, _ = self.value(r, q + 2, vf1)
                    v2, _ = self.value(r, q + 2 + len1, vf2)
                    return v1, v2, len2 > 0
            return None
        if fmt == 2:
            c1 = class_of(r, sp + r.u16(sp + 8), g1)
            c2 = class_of(r, sp + r.u16(sp + 10), g2)
            n1, n2 = r.u16(sp + 12), r.u16(sp + 14)
            if c1 >= n1 or c2 >= n2:
                return None
            q = sp + 16 + (c1 * n2 + c2) * (len1 + len2)
            v1, _ = self.value(r, q, vf1)
            v2, _ = self.value(r, q + len1, vf2)
            return v1, v2, len2 > 0
        return None

    def legacy(self, glyphs, adj, scaled):
        r = self.kern
        s = r.start
        if r.u16(s) != 0:
            return
        p = s + 4
        for _ in range(r.u16(s + 2)):
            length, cov = r.u16(p + 2), r.u16(p + 4)
            if cov >> 8 == 0 and cov & 1 and not cov & 4:
                n = r.u16(p + 6)
                n = min(n, max(0, (r.end - (p + 14)) // 6))
                i = 0
                while i < len(glyphs):
                    if self.skipped(glyphs[i], 8, 0):
                        i += 1
                        continue
                    j = i + 1
                    while j < len(glyphs) and self.skipped(glyphs[j], 8, 0):
                        j += 1
                    if j >= len(glyphs):
                        break
                    key = glyphs[i] << 16 | glyphs[j]
                    lo, hi = 0, n - 1
                    v = 0
                    while lo <= hi:
                        mid = (lo + hi) // 2
                        q = p + 14 + 6 * mid
                        k = r.u32(q)
                        if key < k:
                            hi = mid - 1
                        elif key > k:
                            lo = mid + 1
                        else:
                            v = r.i16(q + 4)
                            break
                    if v:
                        v = scaled(v)
                        k1 = v >> 1
                        adj[i][0] += k1
                        adj[j][0] += v - k1
                        adj[j][1] += v - k1
                    i = j
            if length < 6:
                break
            p += length
