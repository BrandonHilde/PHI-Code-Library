"""Makes libs/font/tests/raster/cases.bin (with cases.txt): the cases test_raster runs fontlib's glyph
bitmaps against, checked with the rules in raster_reference.py, which must give FreeType's bitmaps
exactly (freetype-py, FreeType 2.13, FT_LOAD_NO_HINTING, FT_RENDER_MODE_NORMAL).

    python3 -P tools/font/make_raster_tests.py [--release]

A case is a font at a size, in pixels per em: Liberation Sans, the fonts make_font_tests.py makes, and
some of those fuzzed. The format (little-endian):

    u32 count, then for each:
      u8 name length, name, u32 ppem, u8 kind (0: a path, from libs/font; 1: bytes),
      kind 0: u8 length, path;  kind 1: u32 length, bytes
      u8 ok; if ok: the size's ascender, descender, height and widest advance (i32 each, 26.6
      pixels), the number of glyphs (u32), and the CRC-32 of every glyph's part (below);
      if not: u8 length, the reason (the font's)

A glyph's part: if it can't be loaded, the u32 0xFFFFFFFF; if it can, its advance (i32, 26.6
pixels), its bitmap's left, top, width and height (i32 each), and its rows, top first (a byte a pixel).
A glyph whose bitmap would be more than MOST_PIXELS is counted as the u32 0xFFFFFFFE instead.
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
import ttf_reference as T  # noqa: E402
import raster_reference as R  # noqa: E402
import make_font_tests as M  # noqa: E402

OUT = os.path.join(M.LIB, 'tests', 'raster')
MOST_PIXELS = 1 << 20
RELEASE = False


def size_metrics(face, ppem, scale):
    """the size's ascender, descender, height and widest advance, in 26.6, as FreeType rounds them
    (FT_Request_Metrics): the ascender up to a whole pixel, the descender down, and the rest to the
    nearest"""
    asc = T.mul_fix(face.ascender, scale)
    desc = T.mul_fix(face.descender, scale)
    height = T.mul_fix(face.height, scale)
    adv = T.mul_fix(face.max_advance, scale)
    return (asc + 63) & ~63, desc & ~63, (height + 32) & ~63, (adv + 32) & ~63


def glyph_part(face, g, scale):
    res = face.glyph(g, scale)
    if isinstance(res, str):
        return struct.pack('<I', 0xFFFFFFFF), None
    points, flags, ends, adv = res
    advance = T.mul_fix(face.pp1 + adv, scale) - T.mul_fix(face.pp1, scale)
    if points:
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        w = ((max(xs) + 63) >> 6) - (min(xs) >> 6)
        h = ((max(ys) + 63) >> 6) - (min(ys) >> 6)
        if w * h > MOST_PIXELS:
            return struct.pack('<I', 0xFFFFFFFE), None
    drawn = R.render(points, flags, ends, face.overlap)
    if drawn is None:
        return struct.pack('<I', 0xFFFFFFFE), None
    left, top, w, h, bitmap = drawn
    return struct.pack('<iiiii', advance, left, top, w, h) + bitmap, (advance, left, top, w, h, bitmap)


def rules(data, ppem):
    try:
        face = T.Face(data)
    except T.Refused as e:
        return False, str(e), None
    scale = R.scale_of(ppem, face.units_per_em)
    crc = 0
    glyphs = []
    for g in range(face.num_glyphs):
        part, info = glyph_part(face, g, scale)
        crc = zlib.crc32(part, crc)
        glyphs.append(info)
    return True, size_metrics(face, ppem, scale) + (face.num_glyphs, crc), glyphs


def freetype_check(name, data, ppem, verdict, glyphs, counts, problems):
    import freetype
    try:
        ft = freetype.Face(io.BytesIO(data))
        ft.set_pixel_sizes(0, ppem)
    except Exception:
        problems.append('%s at %d: FreeType refuses it, or the size' % (name, ppem))
        return
    m = ft.size
    if verdict[:4] != (m.ascender, m.descender, m.height, m.max_advance):
        problems.append('%s at %d: the size is %s, FreeType\'s %s' % (name, ppem, verdict[:4],
                                                                     (m.ascender, m.descender, m.height, m.max_advance)))
        return
    for g, info in enumerate(glyphs):
        if info is None:
            continue
        try:
            ft.load_glyph(g, freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_NO_BITMAP | freetype.FT_LOAD_RENDER)
        except Exception as e:
            problems.append('%s at %d: glyph %d: FreeType: %s' % (name, ppem, g, e))
            return
        b = ft.glyph.bitmap
        theirs = b''.join(bytes(b.buffer[r * b.pitch:r * b.pitch + b.width]) for r in range(b.rows))
        mine = info
        if (mine[0], mine[1], mine[2], mine[3], mine[4]) != (ft.glyph.advance.x, ft.glyph.bitmap_left,
                                                              ft.glyph.bitmap_top, b.width, b.rows):
            problems.append('%s at %d: glyph %d: %s, FreeType %s' % (name, ppem, g, mine[:5], (
                ft.glyph.advance.x, ft.glyph.bitmap_left, ft.glyph.bitmap_top, b.width, b.rows)))
            return
        if mine[5] != theirs:
            diff = max(abs(a - c) for a, c in zip(mine[5], theirs))
            problems.append('%s at %d: glyph %d: pixels differ from FreeType\'s, by up to %d' % (name, ppem, g, diff))
            return
        counts['glyphs the same as FreeType\'s'] = counts.get('glyphs the same as FreeType\'s', 0) + 1


def cases():
    out = []
    liberation = open(os.path.join(M.FONTS, M.LIBERATION), 'rb').read()
    for ppem in ((7, 12, 19, 33, 100) if RELEASE else (12, 19)):
        out.append((M.LIBERATION, ppem, 0, 'tests/fonts/' + M.LIBERATION, liberation))
    made = [(n, d) for n, d, rule in M.made_cases() if rule == 'read' and len(d) < 20000]
    for name, data in made:
        for ppem in ((3, 12, 37) if RELEASE else (12,)):
            out.append((name, ppem, 1, None, data))
    r = random.Random(20261110)
    for k in range(400 if RELEASE else 16):
        name, data = r.choice(made)
        data = bytearray(data)
        for _ in range(r.choice((1, 2, 3))):
            at = r.randrange(len(data))
            data[at] = r.choice((0, 1, 255, 0x80, r.randrange(256), data[at] ^ (1 << r.randrange(8))))
        out.append(('fuzz-%d-%s' % (k, name), r.choice((5, 12, 30)), 1, None, bytes(data)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--release', action='store_true')
    args = ap.parse_args()
    global RELEASE
    RELEASE = args.release
    os.makedirs(OUT, exist_ok=True)
    counts, problems = {}, []
    blob = bytearray()
    lines = ['# made by tools/font/make_raster_tests.py: what fontlib must make of each font at each size']
    all_cases = cases()
    blob += struct.pack('<I', len(all_cases))
    for name, ppem, kind, path, data in all_cases:
        ok, verdict, glyphs = rules(data, ppem)
        if ok:
            freetype_check(name, data, ppem, verdict, glyphs, counts, problems)
        nb = name.encode()
        blob += struct.pack('<B', len(nb)) + nb + struct.pack('<IB', ppem, kind)
        if kind == 0:
            pb = path.encode()
            blob += struct.pack('<B', len(pb)) + pb
        else:
            blob += struct.pack('<I', len(data)) + data
        if ok:
            blob += struct.pack('<B', 1) + struct.pack('<iiiiII', *verdict)
            lines.append('%-48s %3d px  %d glyphs' % (name, ppem, verdict[4]))
        else:
            rb = verdict.encode()
            blob += struct.pack('<BB', 0, len(rb)) + rb
            lines.append('%-48s %3d px  refused: %s' % (name, ppem, verdict))
    print('against FreeType:', counts)
    if problems:
        print('\n'.join(problems[:30]))
        sys.exit('the rules and FreeType disagree, %d times' % len(problems))
    filename = 'release' if RELEASE else 'cases'
    with open(os.path.join(OUT, filename + '.bin'), 'wb') as f:
        f.write(blob)
    with open(os.path.join(OUT, filename + '.txt'), 'w', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    print('%s.bin: %d cases, %d bytes' % (filename, len(all_cases), len(blob)))


if __name__ == '__main__':
    main()
