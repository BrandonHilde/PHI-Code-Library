"""Makes libs/font/tests/ttf/cases.bin (with cases.txt): the cases test_ttf runs fontlib against, checked
with the rules in ttf_reference.py, which are checked here against FreeType (through freetype-py) for the
face, the outlines and the metrics, and HarfBuzz (through uharfbuzz) for which glyph each character is.

    python3 -P tools/font/make_font_tests.py [--release]

The cases:
  fonts     Liberation Sans (libs/font/tests/fonts, OFL)
  made      fonts made here with fontTools, one or a few of each feature and each kind of damage
  cut       good fonts cut short
  fuzz      fonts with a few bytes changed

The format of cases.bin is imagelib's (tools/image/cases.py) but for the verdict: u8 ok; if ok, eight
u32s: the number of glyphs, units per em, ascender, descender, line height and widest advance (each
as a 32-bit int), the CRC-32 of every glyph (below), and the CRC-32 of the glyph of each code point
from 0 to 0xFFFF and every 16th from 0x10000 to 0x2FFFF (each a u32); if not, u8 length, the reason.

A glyph's part of its CRC, each number little-endian: if it can't be loaded, the u32 0xFFFFFFFF; if it
can, its advance (i32), its number of points and of contours (u32 each), each point's x and y (i32)
and on-curve flag (u8), and each contour's last point (u16).
"""
import argparse
import io
import os
import random
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ttf_reference as R  # noqa: E402

LIB = os.path.normpath(os.path.join(HERE, '..', '..', 'libs', 'font'))
OUT = os.path.join(LIB, 'tests', 'ttf')
FONTS = os.path.join(LIB, 'tests', 'fonts')
LIBERATION = 'LiberationSans-Regular.ttf'
# the code points whose glyphs are checked: every one to U+FFFF, and every 16th from there to U+2FFFF
CODE_POINTS = list(range(0x10000)) + list(range(0x10000, 0x30000, 16))
FONTS_GROUP, MADE, CUT, FUZZ = 0, 1, 2, 3
GROUP_NAMES = ['fonts', 'made', 'cut', 'fuzz']
RELEASE = False


# ---------------------------------------------------------------- the verdicts

def glyph_bytes(result):
    if isinstance(result, str):
        return struct.pack('<I', 0xFFFFFFFF)
    points, flags, ends, adv = result
    out = bytearray(struct.pack('<iII', adv, len(points), len(ends)))
    for (x, y), f in zip(points, flags):
        out += struct.pack('<iiB', x, y, f)
    for e in ends:
        out += struct.pack('<H', e & 0xFFFF)
    return bytes(out)


def rules(data):
    """(True, the eight numbers) or (False, why)"""
    try:
        face = R.Face(data)
    except R.Refused as e:
        return False, str(e)
    crc = 0
    for g in range(face.num_glyphs):
        crc = zlib.crc32(glyph_bytes(face.glyph(g)), crc)
    cmap = R.Cmap(data)
    ccrc = zlib.crc32(b''.join(struct.pack('<I', cmap.glyph(u)) for u in CODE_POINTS))
    return True, (face.num_glyphs, face.units_per_em, face.ascender, face.descender, face.height,
                  face.max_advance, crc, ccrc)


def freetype_face(data):
    import freetype
    try:
        return freetype.Face(io.BytesIO(data))
    except Exception:
        return None


def freetype_glyph(face, g):
    import freetype
    try:
        face.load_glyph(g, freetype.FT_LOAD_NO_SCALE | freetype.FT_LOAD_NO_HINTING)
    except Exception as e:
        return str(e) or 'error'
    o = face.glyph.outline
    return list(o.points), [t & 1 for t in o.tags], list(o.contours), face.glyph.advance.x


def harfbuzz_glyphs(data):
    import uharfbuzz as hb
    font = hb.Font(hb.Face(hb.Blob(data)))
    return [font.get_nominal_glyph(u) or 0 for u in CODE_POINTS]


def check(name, data, rule, counts, problems):
    """the rules against FreeType and HarfBuzz"""
    def count(key):
        counts[key] = counts.get(key, 0) + 1
    try:
        face = R.Face(data)
    except R.Refused as e:
        face = None
        why = str(e)
    ft = freetype_face(data)
    if face is None:
        if ft is not None:
            if rule in NOTES:
                count('refused, as noted')
            else:
                problems.append('%s: the rules refuse it (%s), but FreeType reads it' % (name, why))
        elif rule == 'read':
            problems.append('%s: refused by both, but it should be read: %s' % (name, why))
        else:
            count('refused by both')
        return
    if ft is None:
        problems.append('%s: the rules read it, but FreeType refuses it' % name)
        return
    if rule == 'refused':
        problems.append('%s: should be refused, but both read it' % name)
        return
    mine = (face.num_glyphs, face.units_per_em, face.ascender, face.descender, face.height, face.max_advance)
    theirs = (ft.num_glyphs, ft.units_per_EM, ft.ascender, ft.descender, ft.height, ft.max_advance_width)
    if mine != theirs:
        problems.append('%s: the face is %s, FreeType\'s %s' % (name, mine, theirs))
        return
    for g in range(face.num_glyphs):
        a, b = face.glyph(g), freetype_glyph(ft, g)
        if isinstance(a, str) or isinstance(b, str):
            if isinstance(a, str) != isinstance(b, str):
                problems.append('%s: glyph %d: the rules say %s, FreeType %s' %
                                (name, g, a if isinstance(a, str) else 'read', b if isinstance(b, str) else 'read'))
                return
            continue
        if (list(a[0]), a[1], a[2], a[3]) != (b[0], b[1], b[2], b[3]):
            problems.append('%s: glyph %d differs from FreeType\'s: %s / %s' % (name, g, (a[0][:4], a[3]), (b[0][:4], b[3])))
            return
    cmap = R.Cmap(data)
    hb = harfbuzz_glyphs(data)
    for k, u in enumerate(CODE_POINTS):
        if cmap.glyph(u) != hb[k]:
            problems.append('%s: U+%04X is glyph %d, where HarfBuzz has %d' % (name, u, cmap.glyph(u), hb[k]))
            return
    count('the same as FreeType and HarfBuzz')


# Made fonts the rules refuse though FreeType reads them, and why
NOTES = {}


# ---------------------------------------------------------------- making fonts

def square(x0, y0, x1, y1):
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    p = TTGlyphPen(None)
    p.moveTo((x0, y0))
    p.lineTo((x0, y1))
    p.lineTo((x1, y1))
    p.lineTo((x1, y0))
    p.closePath()
    return p.glyph()


def curvy(x0, y0, size):
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    p = TTGlyphPen(None)
    p.moveTo((x0, y0))
    p.qCurveTo((x0, y0 + size), (x0 + size, y0 + size))
    p.qCurveTo((x0 + 2 * size, y0 + size), (x0 + 2 * size, y0), (x0 + size, y0 - size // 2))
    p.closePath()
    p.moveTo((x0 + 10, y0 + 10))
    p.lineTo((x0 + 20, y0 + 30))
    p.lineTo((x0 + 30, y0 + 10))
    p.closePath()
    return p.glyph()


def comp(name, x=0, y=0, flags=0, transform=None, point=None):
    from fontTools.ttLib.tables._g_l_y_f import GlyphComponent
    c = GlyphComponent()
    c.glyphName = name
    c.flags = flags
    if point:
        c.firstPt, c.secondPt = point
    else:
        c.x, c.y = x, y
    if transform:
        c.transform = transform
    return c


def build(glyphs, metrics, cmap=None, cmaps=None, upem=1000, ascent=800, descent=-200, line_gap=0,
          long_loca=None, os2=None):
    """a TrueType font: glyphs by name (a glyph, or a list of components), in order; their (advance,
    lsb); a cmap {code: name}, or cmaps [(platform, encoding, format, {code: name})]"""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.ttLib.tables._g_l_y_f import Glyph
    from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
    fb = FontBuilder(upem, isTTF=True)
    fb.setupGlyphOrder(list(glyphs))
    fb.setupCharacterMap(cmap or {})
    built = {}
    for n, g in glyphs.items():
        if isinstance(g, list):
            gg = Glyph()
            gg.numberOfContours = -1
            gg.components = g
            built[n] = gg
        else:
            built[n] = g
    fb.setupGlyf(built)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ascent, descent=descent, lineGap=line_gap)
    fb.setupNameTable({'familyName': 'Made', 'styleName': 'Regular'})
    fb.setupOS2(**(os2 or {}))
    fb.setupPost()
    font = fb.font
    if cmaps is not None:
        font['cmap'].tables = []
        for pid, eid, fmt, m in cmaps:
            t = CmapSubtable.newSubtable(fmt)
            t.platformID, t.platEncID, t.language, t.cmap = pid, eid, 0, m
            font['cmap'].tables.append(t)
    b = io.BytesIO()
    if long_loca is not None:
        font['head'].indexToLocFormat = 1 if long_loca else 0
        # fontTools picks the loca format when it compiles glyf; keep this one
        font.recalcBBoxes = True
        orig = font['glyf'].compile

        def compile_keep(ttFont, _orig=orig, _fmt=1 if long_loca else 0):
            out = _orig(ttFont)
            ttFont['head'].indexToLocFormat = _fmt
            return out
        font['glyf'].compile = compile_keep
    font.save(b)
    return b.getvalue()


def table_at(data, tag):
    n = struct.unpack('>H', data[4:6])[0]
    for k in range(n):
        p = 12 + 16 * k
        if data[p:p + 4] == tag:
            return struct.unpack('>II', data[p + 8:p + 16])
    raise KeyError(tag)


def patch(data, at, new):
    d = bytearray(data)
    d[at:at + len(new)] = new
    return bytes(d)


def glyph_offset(data, g):
    """where glyph g's data starts in the file"""
    from fontTools.ttLib import TTFont
    f = TTFont(io.BytesIO(data))
    return table_at(data, b'glyf')[0] + f['loca'][g]


def set_tag(data, old, new):
    n = struct.unpack('>H', data[4:6])[0]
    for k in range(n):
        p = 12 + 16 * k
        if data[p:p + 4] == old:
            return patch(data, p, new)
    raise KeyError(old)


def made_cases():
    """(name, data, rule): rule is 'read' (FreeType and HarfBuzz must agree with the rules on all of
    it), 'refused' (both refuse it), or 'damaged' (either)"""
    cases = []

    def add(name, data, rule='read'):
        cases.append((name, data, rule))

    base = {'.notdef': square(50, 0, 450, 700), 'A': curvy(30, 100, 200), 'B': square(80, -50, 400, 650),
            'space': square(0, 0, 0, 0)}
    metrics = {'.notdef': (500, 50), 'A': (600, 30), 'B': (520, 80), 'space': (250, 0)}
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    empty = TTGlyphPen(None).glyph()
    base['space'] = empty
    cmap = {0x41: 'A', 0x42: 'B', 0x20: 'space'}
    simple = build(base, metrics, cmap)
    add('simple', simple)
    add('upem-16', build(base, metrics, cmap, upem=16))
    add('upem-16384', build(base, metrics, cmap, upem=16384))
    add('short-loca', build(base, metrics, cmap, long_loca=False))
    add('long-loca', build(base, metrics, cmap, long_loca=True))
    add('line-gap', build(base, metrics, cmap, line_gap=90))
    add('os2-typo-metrics', build(base, metrics, cmap, ascent=0, descent=0,
                                  os2={'sTypoAscender': 750, 'sTypoDescender': -250, 'sTypoLineGap': 60}))
    add('os2-win-metrics', build(base, metrics, cmap, ascent=0, descent=0,
                                 os2={'sTypoAscender': 0, 'sTypoDescender': 0, 'usWinAscent': 900, 'usWinDescent': 300}))
    # fewer long metrics than glyphs: the rest have the last advance
    m2 = dict(metrics)
    m2['B'] = (600, 80)
    m2['space'] = (600, 0)
    add('short-metrics', build(base, m2, cmap))

    # where the outline goes: left at the left side bearing
    add('lsb-not-xmin', build({'.notdef': square(0, 0, 10, 10), 'A': square(100, 0, 300, 500)},
                              {'.notdef': (500, 0), 'A': (600, 40)}, {0x41: 'A'}))
    d = build({'.notdef': square(0, 0, 10, 10), 'A': square(100, 0, 300, 500)}, {'.notdef': (500, 0), 'A': (600, 100)}, {0x41: 'A'})
    add('header-xmin-not-points', patch(d, glyph_offset(d, 1) + 2, struct.pack('>h', 70)))

    # composites: each kind of offset and transform
    g = {'.notdef': square(0, 0, 10, 10), 'b': curvy(10, 20, 100), 'c': square(0, 0, 10, 10)}
    gm = {'.notdef': (500, 0), 'b': (500, 10), 'c': (300, 0)}

    def composite(name, components, adv=(600, 0)):
        gs = dict(g)
        gs['a'] = components
        ms = dict(gm)
        ms['a'] = adv
        add(name, build(gs, ms, {0x41: 'a', 0x42: 'b'}))
    composite('composite-offset', [comp('b', x=30, y=-20)])
    composite('composite-offset-words', [comp('b', x=300, y=-200)])
    composite('composite-two', [comp('b'), comp('c', x=150, y=40)])
    composite('composite-scale', [comp('b', transform=[[0.5, 0], [0, 0.5]])])
    composite('composite-xy-scale', [comp('b', x=10, transform=[[1.5, 0], [0, -0.75]])])
    composite('composite-2x2', [comp('b', x=5, y=7, transform=[[1, 0.5], [0.25, 1]])])
    composite('composite-scaled-offset', [comp('b', x=100, y=50, flags=0x800, transform=[[0.75, 0], [0, 1.5]])])
    composite('composite-scaled-offset-2x2', [comp('b', x=100, y=50, flags=0x800, transform=[[0.8, 0.3], [-0.6, 1.1]])])
    composite('composite-scaled-offset-2x2-b', [comp('b', x=-77, y=91, flags=0x800, transform=[[-1.25, 0.125], [0.5, 0.875]])])
    composite('composite-point-matching', [comp('b'), comp('c', point=(2, 0))])
    composite('composite-use-my-metrics', [comp('b', x=10, flags=0x200)])
    composite('composite-of-empty', [comp('.notdef'), comp('b', x=3)])
    gs = dict(g)
    gs['a'] = [comp('b', x=1)]
    gs['d'] = [comp('a', x=1), comp('c', y=5)]
    gs['e'] = [comp('d', x=1, transform=[[0.5, 0], [0, 0.5]])]
    ms = dict(gm)
    ms.update({'a': (600, 0), 'd': (600, 0), 'e': (600, 0)})
    add('composite-nested', build(gs, ms, {0x41: 'e'}))
    d = build(gs, ms, {0x41: 'e'})
    add('composite-contains-itself', patch(d, glyph_offset(d, 3) + 12, struct.pack('>H', 3)), 'damaged')
    add('composite-of-a-glyph-past-the-end', patch(d, glyph_offset(d, 3) + 12, struct.pack('>H', 99)), 'damaged')

    # characters: each cmap format, the subtable chosen, and the fallbacks
    glyphs3 = {'.notdef': square(0, 0, 10, 10), 'a': square(0, 0, 100, 100), 'b': square(0, 0, 50, 50)}
    m3 = {'.notdef': (500, 0), 'a': (600, 0), 'b': (500, 0)}
    many = {u: ('a' if u % 3 else 'b') for u in range(0x20, 0x250)}
    for name, subs in [
            ('cmap-format-0', [(1, 0, 0, {u: 'a' for u in range(0x41, 0x5B)})]),
            ('cmap-format-4', [(3, 1, 4, many)]),
            ('cmap-format-6', [(3, 1, 6, {u: 'b' for u in range(0x30, 0x40)})]),
            ('cmap-format-12', [(3, 10, 12, {0x41: 'a', 0x1F600: 'b', 0x2A000: 'a', **{u: 'b' for u in range(0x10000, 0x10100)}})]),
            ('cmap-format-13', [(3, 10, 13, {u: 'b' for u in range(0x1F300, 0x1F3FF)})]),
            ('cmap-3-10-before-3-1', [(3, 1, 4, {0x41: 'a'}), (3, 10, 12, {0x41: 'b', 0x1F600: 'a'})]),
            ('cmap-0-4-before-3-1', [(0, 4, 12, {0x41: 'b', 0x1F600: 'b'}), (3, 1, 4, {0x41: 'a'})]),
            ('cmap-3-1-before-0-3', [(0, 3, 4, {0x41: 'b'}), (3, 1, 4, {0x41: 'a'})]),
            ('cmap-0-3', [(0, 3, 4, many)]),
            ('cmap-symbol', [(3, 0, 4, {0xF041: 'a', 0xF020: 'b', 0x41: 'b'})]),
            ('cmap-mac-roman', [(1, 0, 0, {0x41: 'a', 0x80: 'b', 0xDB: 'a', 0xA5: 'b'})]),
            ('cmap-none', []),
    ]:
        add(name, build(glyphs3, m3, cmaps=subs))

    # damage FreeType reads past, or refuses
    add('tag-otto', b'OTTO' + simple[4:], 'refused')
    add('tag-ttcf', b'ttcf' + simple[4:], 'refused')
    add('tag-junk', b'abcd' + simple[4:], 'refused')
    add('tag-true', b'true' + simple[4:])
    add('too-short', simple[:11], 'refused')
    for t in (b'head', b'hhea', b'maxp', b'hmtx', b'loca', b'glyf', b'cmap'):
        add('no-%s' % t.decode().strip(), set_tag(simple, t, b'zzzz'), 'damaged')
    hp = table_at(simple, b'head')[0]
    add('upem-15', patch(simple, hp + 18, struct.pack('>H', 15)), 'refused')
    add('upem-16385', patch(simple, hp + 18, struct.pack('>H', 16385)), 'refused')
    mp = table_at(simple, b'maxp')[0]
    add('maxp-more-glyphs', patch(simple, mp + 4, struct.pack('>H', 9)), 'damaged')
    add('maxp-fewer-glyphs', patch(simple, mp + 4, struct.pack('>H', 2)), 'damaged')
    add('maxp-no-glyphs', patch(simple, mp + 4, struct.pack('>H', 0)), 'damaged')
    gp = glyph_offset(simple, 1)
    add('glyph-contours-out-of-order', patch(simple, gp + 10, struct.pack('>HH', 9, 3)), 'damaged')
    add('glyph-instructions-too-long', patch(simple, gp + 14, struct.pack('>H', 9999)), 'damaged')
    add('glyph-flags-repeat-too-far', patch(simple, gp + 16, b'\x09\xff'), 'damaged')
    return cases


# ---------------------------------------------------------------- writing cases.bin

class CaseFile:
    def __init__(self):
        self.list = []

    def add(self, group, kind, name, data, payload=None):
        ok, result = rules(data)
        self.list.append((group, kind, name, payload, data, ok, result))
        return len(self.list) - 1

    def write(self, filename):
        out = bytearray(struct.pack('<I', len(self.list)))
        lines = ['# made by tools/font/make_font_tests.py: what fontlib must make of each case in %s.bin' % filename,
                 '# (the cut and fuzz cases are summed up by the case they come from, at the end)']
        summary = {}
        for group, kind, name, payload, data, ok, result in self.list:
            nb = name.encode()
            out += struct.pack('<BBB', group, kind, len(nb)) + nb + struct.pack('<I', 0)
            if kind == 0:
                p = payload.encode()
                out += struct.pack('<B', len(p)) + p
            elif kind == 1:
                out += struct.pack('<I', len(data)) + data
            elif kind == 2:
                out += struct.pack('<II', *payload)
            else:
                source, changes = payload
                out += struct.pack('<IH', source, len(changes))
                for at, v in changes:
                    out += struct.pack('<IB', at, v)
            if ok:
                out += struct.pack('<B', 1) + struct.pack('<8I', *(v & 0xFFFFFFFF for v in result))
                verdict = 'ok, %d glyphs' % result[0]
            else:
                rb = result.encode()
                out += struct.pack('<BB', 0, len(rb)) + rb
                verdict = 'refused: ' + result
            if group in (CUT, FUZZ):
                key = (GROUP_NAMES[group], self.list[payload[0]][2])
                tally = summary.setdefault(key, [0, 0])
                tally[0 if ok else 1] += 1
            else:
                lines.append('%-5s %-40s %7d bytes  %s' % (GROUP_NAMES[group], name, len(data), verdict))
        for (group, source), (good, bad) in summary.items():
            lines.append('%-5s %-40s %4d ok, %4d refused' % (group, source, good, bad))
        with open(os.path.join(OUT, filename + '.bin'), 'wb') as f:
            f.write(out)
        with open(os.path.join(OUT, filename + '.txt'), 'w', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')
        return len(out)

    def summary(self):
        groups = {}
        for group, _, _, _, _, ok, _ in self.list:
            g = groups.setdefault(GROUP_NAMES[group], [0, 0])
            g[0 if ok else 1] += 1
        return ', '.join('%s %d ok, %d refused' % (k, v[0], v[1]) for k, v in groups.items())


def cut_lengths(size):
    if RELEASE:
        return sorted(set(list(range(0, min(size, 400), 7)) + list(range(400, size, max(1, size // 300)))))
    return sorted(set(at for at in (8, 20, 100, size // 4, size // 2, size * 3 // 4, size - 1) if 0 < at < size))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--release', action='store_true', help='make the release cases')
    args = ap.parse_args()
    global RELEASE
    RELEASE = args.release
    os.makedirs(OUT, exist_ok=True)

    counts, problems = {}, []
    liberation = open(os.path.join(FONTS, LIBERATION), 'rb').read()
    check(LIBERATION, liberation, 'read', counts, problems)
    made = made_cases()
    for name, data, rule in made:
        check(name, data, rule, counts, problems)
    print('the rules against FreeType and HarfBuzz:', counts)
    if problems:
        print('\n'.join(problems))
        sys.exit('the rules and the references disagree, %d times' % len(problems))

    cases = CaseFile()
    index = {LIBERATION: cases.add(FONTS_GROUP, 0, LIBERATION, liberation, 'tests/fonts/' + LIBERATION)}
    for name, data, _ in made:
        index[name] = cases.add(MADE, 1, name, data)

    fuzz_counts, fuzz_problems = {}, []
    for name in (('simple', 'composite-nested', 'cmap-format-4', 'cmap-format-12', 'short-loca') if RELEASE
                 else ('simple', 'composite-nested')):
        source = index[name]
        data = cases.list[source][4]
        for at in cut_lengths(len(data)):
            cases.add(CUT, 2, '%s-to-%d' % (name, at), data[:at], (source, at))
            check('%s-to-%d' % (name, at), data[:at], 'damaged', fuzz_counts, fuzz_problems)
    r = random.Random(20261109)
    small = [name for name, data, rule in made if rule == 'read']
    for k in range(int(os.environ.get('FUZZ', 4000 if RELEASE else 40))):
        name = r.choice(small)
        source = index[name]
        data = bytearray(cases.list[source][4])
        changes = []
        for _ in range(r.choice((1, 1, 2, 3, 5))):
            at = r.randrange(min(len(data), 300)) if r.random() < 0.3 else r.randrange(len(data))
            v = r.choice((0, 1, 255, 0x7F, 0x80, r.randrange(256), data[at] ^ (1 << r.randrange(8))))
            data[at] = v
            changes.append((at, v))
        cases.add(FUZZ, 3, 'fuzz-%d-%s' % (k, name), bytes(data), (source, changes))
        check('fuzz-%d-%s' % (k, name), bytes(data), 'damaged', fuzz_counts, fuzz_problems)
    print('cut and fuzzed, against FreeType and HarfBuzz:', fuzz_counts)
    if fuzz_problems:
        print('\n'.join(fuzz_problems[:30]))
        sys.exit('the rules and the references disagree, %d times' % len(fuzz_problems))

    size = cases.write('release' if RELEASE else 'cases')
    print('%s.bin: %d cases, %d bytes:' % ('release' if RELEASE else 'cases', len(cases.list), size), cases.summary())


if __name__ == '__main__':
    main()
