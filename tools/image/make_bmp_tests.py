#!/usr/bin/env python3
"""Makes the cases imagelib's BMP decoder is tested on, and checks what they expect against
outside evidence.

    python3 -P tools/image/make_bmp_tests.py                        # from the committed BMP Suite copy
    python3 -P tools/image/make_bmp_tests.py --bmpsuite DIR         # also against BMP Suite's own
                                                                    # reference images (DIR is the
                                                                    # unpacked bmpsuite-2.8)

(-P rather than -I, since Pillow and numpy are usually in the user's site-packages.)

Writes libs/image/tests/bmp/:

    bmpsuite/      BMP Suite 2.8's images (public domain), copied from DIR when --bmpsuite is given
    cases.bin      every case: where its bytes come from, and what imagelib must make of it
    cases.txt      the same, readable: one a line

What each case expects comes from bmp_reference.py, the rules written plainly in Python. Before
writing anything, this checks those rules against two outside sources and stops if they disagree
in a way that isn't listed (in SUITE_NOTES, or in the rules for the cases made here):

    BMP Suite's reference images   for each of its files that has one (with --bmpsuite)
    Pillow                         for every file Pillow reads

Four groups of cases:

    suite   BMP Suite's files: g (good), q (questionable), b (bad), x (related formats)
    made    files written here, for what BMP Suite doesn't cover: every bit depth at many widths,
            each header size, bit fields, RLE's corners, and each way a header can be wrong
    cut     good files cut short at many lengths
    fuzz    small files with a few bytes changed, with a fixed seed

cases.bin's format is in cases.py.
"""
import argparse
import os
import random
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bmp_reference import decode, MAX_PIXELS  # noqa: E402
from cases import Cases as CaseFile, as_rgba  # noqa: E402

LIB = os.path.normpath(os.path.join(HERE, '..', '..', 'libs', 'image'))
OUT = os.path.join(LIB, 'tests', 'bmp')
SUITE = os.path.join(OUT, 'bmpsuite')

SUITE_GROUP, MADE, CUT, FUZZ = 0, 1, 2, 3
GROUP_NAMES = ['suite', 'made', 'cut', 'fuzz']

# Left out of the copy: their embedded ICC profiles aren't BMP Suite's to give away.
SUITE_LEFT_OUT = {'q/rgb24prof.bmp', 'q/rgb24prof2.bmp'}

# Where BMP Suite's reference image or Pillow differs from bmp_reference, and why. Anything not
# here must match exactly (counting every fully transparent pixel as 0).
SUITE_NOTES = {
    'g/pal8nonsquare.bmp': ('ref', 'the reference image is stretched to square pixels'),
    'q/rgb32-111110.bmp': ('ref1', 'channels wider than 8 bits: within 1 of the reference'),
    'q/rgb32-7187.bmp': ('ref1', 'channels wider than 8 bits: within 1 of the reference'),
    'q/rgba32-61754.bmp': ('ref1', 'channels wider than 8 bits: within 1 of the reference'),
    'q/rgba32-81284.bmp': ('ref1', 'channels wider than 8 bits: within 1 of the reference'),
    'g/rgb16.bmp': ('pil1', 'Pillow widens 5 and 6-bit channels by shifting, not scaling'),
    'g/rgb16bfdef.bmp': ('pil1', 'Pillow widens 5 and 6-bit channels by shifting, not scaling'),
    'g/rgb16-565.bmp': ('pil1', 'Pillow widens 5 and 6-bit channels by shifting, not scaling'),
    'g/rgb16-565pal.bmp': ('pil1', 'Pillow widens 5 and 6-bit channels by shifting, not scaling'),
    'q/rgb16faketrns.bmp': ('pil1', 'Pillow widens 5 and 6-bit channels by shifting, not scaling'),
    'g/pal4rle.bmp': ('pil', 'Pillow 11 draws every other pixel of an RLE4 run in color 0'),
    'q/pal4rletrns.bmp': ('pil', 'Pillow makes skipped pixels color 0, and has the RLE4 fault'),
    'q/pal4rlecut.bmp': ('pil', 'Pillow makes skipped pixels color 0, and has the RLE4 fault'),
    'q/pal8rletrns.bmp': ('pil', 'Pillow makes skipped pixels color 0, not transparent'),
    'q/pal8rlecut.bmp': ('pil', 'Pillow makes skipped pixels color 0, not transparent'),
    'b/badrle.bmp': ('pil', 'Pillow makes skipped pixels color 0, not transparent'),
    'b/badrlebis.bmp': ('pil', 'Pillow makes skipped pixels color 0, not transparent'),
    'b/badrleter.bmp': ('pil', 'Pillow makes skipped pixels color 0, not transparent'),
    'b/badrle4.bmp': ('pil', 'Pillow makes skipped pixels color 0, and has the RLE4 fault'),
    'b/badrle4bis.bmp': ('pil', 'Pillow makes skipped pixels color 0, and has the RLE4 fault'),
    'b/badrle4ter.bmp': ('pil', 'Pillow makes skipped pixels color 0, and has the RLE4 fault'),
    'q/rgba16-5551.bmp': ('pil', 'Pillow ignores a 16-bit image\'s alpha mask'),
    'b/rletopdown.bmp': ('pilread', 'Pillow reads RLE stored top-down, which BMP doesn\'t allow'),
}


# ---------------------------------------------------------------- comparing images

def difference(a, b):
    """the largest difference in any channel, counting fully transparent pixels as 0; None if the
    sizes differ"""
    import numpy as np
    if a.shape != b.shape:
        return None
    a = a.copy()
    b = b.copy()
    a[a[:, :, 3] == 0] = 0
    b[b[:, :, 3] == 0] = 0
    return int(np.abs(a.astype(int) - b.astype(int)).max())


def pillow(data):
    import io
    import numpy as np
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))
        if im.format != 'BMP':
            return None
        im.load()
        return np.asarray(im.convert('RGBA'), dtype=np.uint8)
    except Exception:
        return None


# ---------------------------------------------------------------- writing BMP files

def bmp(width, height, bpp, rows=None, header=40, compression=0, masks=None, palette=None,
        colors=None, top_down=False, data=None, gap=0, offset=None, planes=1, file_size=None,
        mask_count=None):
    """A BMP file. rows (top row first) are lists of palette indexes or pixel values, packed
    here; data, if given, is the pixel data as it is (RLE, say). masks go in the header from 52
    bytes on, or after a 40-byte one."""
    if data is None:
        data = b''
        order = rows if top_down else rows[::-1]
        for row in order:
            line = bytearray()
            if bpp <= 8:
                acc = 0
                nbits = 0
                for v in row:
                    acc = acc << bpp | v
                    nbits += bpp
                    if nbits == 8:
                        line.append(acc)
                        acc = nbits = 0
                if nbits:
                    line.append(acc << (8 - nbits))
            elif bpp == 24:
                for v in row:
                    line += bytes([v & 255, v >> 8 & 255, v >> 16 & 255])
            else:
                for v in row:
                    line += v.to_bytes(bpp // 8, 'little')
            while len(line) % 4:
                line.append(0)
            data += bytes(line)
    pal = b''
    if palette:
        for c in palette:
            pal += bytes([c & 255, c >> 8 & 255, c >> 16 & 255]) + (b'' if header == 12 else b'\0')
    after = b''
    if masks is not None and header < 52:
        count = (4 if compression == 6 else 3) if mask_count is None else mask_count
        after = b''.join(struct.pack('<I', m) for m in masks[:count])
    if header == 12:
        info = struct.pack('<IHHHH', 12, width, height, planes, bpp)
    else:
        info = struct.pack('<IiiHHIIiiII', header, width, -height if top_down else height, planes, bpp,
                           compression, len(data), 2835, 2835,
                           len(palette) if colors is None and palette else (colors or 0), 0)
        if header >= 52:
            m = list(masks or []) + [0] * 4
            info += struct.pack('<IIII', m[0], m[1], m[2], m[3])
        if header > len(info):
            extra = bytearray(header - len(info))
            if header >= 108:
                extra[0:4] = b'BGRs'         # LCS_sRGB, as Windows writes it
            info += bytes(extra)
        info = info[:header]
    head = 14 + len(info) + len(after) + len(pal) + gap
    if offset is None:
        offset = head
    total = head + len(data)
    out = b'BM' + struct.pack('<IHHI', total if file_size is None else file_size, 0, 0, offset)
    return out + info + after + pal + bytes(gap) + data


def gradient(w, h, bpp, seed):
    r = random.Random(seed)
    top = (1 << bpp) - 1 if bpp <= 8 else (1 << min(bpp, 32)) - 1
    return [[r.randint(0, top) for _ in range(w)] for _ in range(h)]


def palette_of(n, seed):
    r = random.Random(seed)
    return [r.randint(0, 0xFFFFFF) for _ in range(n)]


def rle(*commands):
    """RLE data from commands: (count, value) runs, ('abs', [values], four), 'eol', 'end',
    ('delta', dx, dy), or raw bytes"""
    out = bytearray()
    for c in commands:
        if c == 'eol':
            out += b'\0\0'
        elif c == 'end':
            out += b'\0\1'
        elif isinstance(c, (bytes, bytearray)):
            out += c
        elif c[0] == 'delta':
            out += bytes([0, 2, c[1], c[2]])
        elif c[0] == 'abs':
            values, four = c[1], c[2]
            out += bytes([0, len(values)])
            if four:
                packed = bytearray()
                for k in range(0, len(values), 2):
                    hi = values[k]
                    lo = values[k + 1] if k + 1 < len(values) else 0
                    packed.append(hi << 4 | lo)
            else:
                packed = bytearray(values)
            if len(packed) % 2:
                packed.append(0)
            out += packed
        else:
            out += bytes([c[0], c[1]])
    return bytes(out)


# ---------------------------------------------------------------- the cases made here

def made_cases():
    """(name, bytes, max_pixels, pillow_rule) for each. pillow_rule says how Pillow must compare:
    'same', 'within1' (16-bit channel widening), 'skip' (Pillow can't be the judge, with why
    in the name or comment), 'refuses' (Pillow refuses it and so do we), or 'pilreads' (we
    refuse what Pillow reads: bit fields on 24-bit pixels and RLE8 on 4-bit ones, which BMP
    doesn't have, and pixels that start inside the headers)."""
    cases = []

    def add(name, data, rule='same', max_pixels=0):
        cases.append((name, data, max_pixels, rule))

    # every bit depth, at widths around each padding boundary, both ways up
    for bpp in (1, 2, 4, 8, 16, 24, 32):
        for w in (1, 2, 3, 4, 5, 6, 7, 8, 9, 15, 16, 17, 31, 32, 33):
            for top_down in (False, True):
                h = 3
                rows = gradient(w, h, bpp if bpp <= 8 else min(bpp, 32), bpp * 1000 + w)
                pal = palette_of(1 << bpp, bpp) if bpp <= 8 else None
                if bpp == 16:
                    rows = [[v & 0x7FFF for v in row] for row in rows]
                if bpp == 24:
                    rows = [[v & 0xFFFFFF for v in row] for row in rows]
                rule = 'skip' if bpp == 2 else ('within1' if bpp == 16 else 'same')
                add('depth%d-w%d%s' % (bpp, w, '-topdown' if top_down else ''),
                    bmp(w, h, bpp, rows, palette=pal, top_down=top_down), rule)

    # each header size, on an 8-bit image and a 24-bit one
    rows8 = gradient(13, 5, 8, 1)
    pal8 = palette_of(256, 2)
    rows24 = [[v & 0xFFFFFF for v in row] for row in gradient(13, 5, 24, 3)]
    for header in (12, 16, 40, 52, 56, 64, 108, 124):
        rule = 'skip' if header in (16, 52, 56) else 'same'   # Pillow doesn't take these sizes
        add('header%d-pal8' % header, bmp(13, 5, 8, rows8, header=header, palette=pal8), rule)
        add('header%d-rgb24' % header, bmp(13, 5, 24, rows24, header=header), rule)

    # palettes: short ones (missing colors are black), long ones (only the first 2^bpp count)
    add('palette-short', bmp(8, 2, 8, [[0, 1, 2, 3, 4, 5, 6, 7], [7, 6, 5, 4, 3, 2, 1, 0]],
                             palette=pal8[:4]), 'skip')
    add('palette-one-color-1bit', bmp(9, 2, 1, [[0, 1] * 4 + [1], [1, 0] * 4 + [0]],
                                      palette=[0x123456]), 'skip')
    add('palette-300-colors', bmp(4, 1, 8, [[0, 1, 254, 255]], palette=palette_of(300, 5)), 'skip')
    add('palette-0-means-all', bmp(4, 1, 4, [[0, 5, 10, 15]], palette=palette_of(16, 6), colors=0))
    add('palette-os2-short', bmp(4, 1, 8, [[0, 1, 2, 3]], header=12, palette=pal8[:3]), 'skip')
    add('palette-gap-after', bmp(4, 1, 8, [[0, 1, 2, 3]], palette=pal8, gap=37))
    add('rgb24-with-palette', bmp(4, 1, 24, [[0x112233, 0x445566, 0x778899, 0xAABBCC]],
                                  palette=palette_of(300, 7)))
    add('last-row-unpadded', bmp(5, 2, 8, [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]], palette=pal8)[:-3],
        'skip')

    # bit fields: masks of every shape, with and without alpha, in each place they can be
    r = random.Random(11)
    fields = [
        ('565', 16, [0xF800, 0x07E0, 0x001F, 0]),
        ('555', 16, [0x7C00, 0x03E0, 0x001F, 0]),
        ('4444', 16, [0x0F00, 0x00F0, 0x000F, 0xF000]),
        ('1555', 16, [0x7C00, 0x03E0, 0x001F, 0x8000]),
        ('one-bit-each', 16, [0x0004, 0x0002, 0x0001, 0x0008]),
        ('no-blue', 16, [0xFF00, 0x00FF, 0, 0]),
        ('no-channels', 16, [0, 0, 0, 0]),
        ('all-16-green', 16, [0, 0xFFFF, 0, 0]),
        ('8888', 32, [0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000]),
        ('8888-abgr', 32, [0x000000FF, 0x0000FF00, 0x00FF0000, 0xFF000000]),
        ('xrgb-high', 32, [0xFF000000, 0x00FF0000, 0x0000FF00, 0]),
        ('10-10-10-2', 32, [0x3FF00000, 0x000FFC00, 0x000003FF, 0xC0000000]),
        ('32-bit-red', 32, [0xFFFFFFFF, 0, 0, 0]),
        ('11-11-10', 32, [0xFFE00000, 0x001FFC00, 0x000003FF, 0]),
        ('overlapping', 32, [0x00FFFF00, 0x0000FFFF, 0x000000FF, 0]),
    ]
    for name, bpp, masks in fields:
        rows = [[r.getrandbits(bpp) for _ in range(7)] for _ in range(3)]
        alpha = masks[3] != 0
        # Pillow knows only a few layouts, and none of the 16-bit ones with alpha
        known = {(16, (0xF800, 0x07E0, 0x001F)), (16, (0x7C00, 0x03E0, 0x001F)),
                 (32, (0x00FF0000, 0x0000FF00, 0x000000FF)), (32, (0xFF000000, 0x00FF0000, 0x0000FF00))}
        plain = (bpp, tuple(masks[:3])) in known and not alpha
        for header in (40, 52, 56, 108, 124):
            if alpha and header < 56:
                continue
            rule = ('within1' if bpp == 16 else 'same') if plain and header in (40, 108, 124) else 'skip'
            add('fields-%s-header%d' % (name, header),
                bmp(7, 3, bpp, rows, header=header, compression=3, masks=masks), rule)
        if alpha:
            add('fields-%s-alphabitfields' % name,
                bmp(7, 3, bpp, rows, header=40, compression=6, masks=masks), 'skip')
        add('fields-%s-header40-alpha-ignored' % name,
            bmp(7, 3, bpp, rows, header=40, compression=3, masks=masks[:3] + [0]),
            ('within1' if bpp == 16 else 'same') if (bpp, tuple(masks[:3])) in known else 'skip')
    # 16-bit images of 65,536 pixels or more, which imagelib decodes through a table
    big = [[r.getrandbits(16) for _ in range(256)] for _ in range(256)]
    add('fields-565-256-square', bmp(256, 256, 16, big, compression=3, masks=[0xF800, 0x07E0, 0x001F]),
        'within1')
    add('fields-4444-256-square', bmp(256, 256, 16, big, header=56, compression=3,
                                      masks=[0x0F00, 0x00F0, 0x000F, 0xF000]), 'skip')
    add('rgb32-unused-bits-set', bmp(3, 1, 32, [[0x80112233, 0xFF445566, 0x01778899]]))
    add('rgb16-unused-bit-set', bmp(3, 1, 16, [[0x8000, 0xFFFF, 0x7FFF]]), 'within1')

    # RLE: what BMP Suite doesn't reach
    p16 = palette_of(16, 21)
    add('rle8-run-past-row-end', bmp(5, 2, 8, palette=pal8, compression=1,
                                     data=rle((9, 7), 'eol', (3, 2), 'end')), 'skip')
    add('rle8-absolute-odd', bmp(5, 1, 8, palette=pal8, compression=1,
                                 data=rle(('abs', [1, 2, 3], False), (2, 9), 'end')), 'skip')
    add('rle8-absolute-past-row-end', bmp(4, 2, 8, palette=pal8, compression=1,
                                          data=rle(('abs', [1, 2, 3, 4, 5, 6, 7], False), 'eol', (4, 3), 'end')), 'skip')
    add('rle8-delta', bmp(6, 4, 8, palette=pal8, compression=1,
                          data=rle((2, 5), ('delta', 1, 2), (2, 6), 'end')), 'skip')
    add('rle8-delta-off-the-right', bmp(4, 3, 8, palette=pal8, compression=1,
                                        data=rle(('delta', 200, 1), (2, 6), 'eol', (4, 1), 'end')), 'skip')
    add('rle8-delta-off-the-top', bmp(4, 3, 8, palette=pal8, compression=1,
                                      data=rle((4, 1), ('delta', 0, 200), (2, 6))), 'skip')
    add('rle8-eol-at-row-end', bmp(3, 2, 8, palette=pal8, compression=1,
                                   data=rle((3, 1), 'eol', (3, 2), 'eol', 'end')), 'skip')
    add('rle8-rows-past-the-top', bmp(2, 2, 8, palette=pal8, compression=1,
                                      data=rle((2, 1), 'eol', (2, 2), 'eol', (2, 3), 'eol')), 'skip')
    add('rle8-no-end', bmp(3, 2, 8, palette=pal8, compression=1, data=rle((3, 1), 'eol', (3, 2))),
        'skip')
    add('rle8-ends-in-delta', bmp(3, 2, 8, palette=pal8, compression=1, data=rle((3, 1), b'\0\2\1')),
        'skip')
    add('rle8-ends-in-absolute', bmp(3, 2, 8, palette=pal8, compression=1, data=rle((3, 1), b'\0\5\1\2')),
        'skip')
    add('rle8-index-past-palette', bmp(4, 1, 8, palette=pal8[:2], compression=1,
                                       data=rle((2, 1), (2, 200), 'end')), 'skip')
    add('rle8-empty-runs', bmp(3, 1, 8, palette=pal8, compression=1,
                               data=rle((0, 0), (0, 0), (3, 4), 'end')), 'skip')
    add('rle4-run-odd', bmp(7, 1, 4, palette=p16, compression=2, data=rle((5, 0x3A), (2, 0x51), 'end')),
        'skip')
    add('rle4-absolute-odd', bmp(7, 1, 4, palette=p16, compression=2,
                                 data=rle(('abs', [1, 2, 3, 4, 5], True), (2, 0x99), 'end')), 'skip')
    add('rle4-absolute-3', bmp(4, 1, 4, palette=p16, compression=2,
                               data=rle(('abs', [7, 8, 9], True), 'end')), 'skip')
    add('rle4-run-past-row-end', bmp(3, 2, 4, palette=p16, compression=2,
                                     data=rle((9, 0x12), 'eol', (3, 0x45), 'end')), 'skip')

    # refused: one thing wrong in each
    good = bmp(4, 2, 8, [[1, 2, 3, 4], [5, 6, 7, 8]], palette=pal8[:16])

    def patch(data, at, fmt, value):
        b = bytearray(data)
        struct.pack_into(fmt, b, at, value)
        return bytes(b)

    add('bad-signature', b'BN' + good[2:], 'refuses')
    add('bad-too-short', good[:17], 'refuses')
    add('bad-empty', b'', 'refuses')
    for hs in (0, 11, 13, 39, 41, 100, 0xFFFFFFFF):
        add('bad-header-size-%d' % hs, patch(good, 14, '<I', hs), 'refuses')
    add('bad-header-cut', good[:14 + 30], 'refuses')
    add('bad-width-0', patch(good, 18, '<i', 0), 'refuses')
    add('bad-width-negative', patch(good, 18, '<i', -4), 'refuses')
    add('bad-height-0', patch(good, 22, '<i', 0), 'refuses')
    add('bad-height-most-negative', patch(good, 22, '<i', -0x80000000), 'refuses')
    add('bad-os2-width-0', patch(bmp(3, 2, 8, [[1, 2, 3], [4, 5, 6]], header=12, palette=pal8), 18, '<H', 0),
        'refuses')
    for b in (0, 3, 5, 12, 48, 64, 65535):
        add('bad-bpp-%d' % b, patch(good, 28, '<H', b), 'skip' if b == 64 else 'refuses')
    for c in (4, 5, 7, 11, 0xFFFFFFFF):
        add('bad-compression-%d' % c, patch(good, 30, '<I', c), 'refuses')
    add('bad-os2v2-huffman', bmp(8, 1, 1, [[0] * 8], header=64, compression=3, palette=[0, 0xFFFFFF]),
        'skip')
    add('bad-os2v2-rle24', bmp(2, 1, 24, header=64, compression=4, data=b'\2\0\0\0\0\0\1'), 'skip')
    add('bad-rle8-with-4-bits', patch(bmp(4, 1, 4, [[1, 2, 3, 4]], palette=p16), 30, '<I', 1), 'pilreads')
    add('bad-rle4-with-8-bits', patch(good, 30, '<I', 2), 'refuses')
    add('bad-rle-top-down', bmp(3, 2, 8, palette=pal8, compression=1, top_down=True,
                                data=rle((3, 1), 'eol', (3, 2), 'end')), 'skip')
    add('bad-fields-with-24-bits', bmp(2, 1, 24, [[1, 2]], compression=3, masks=[0xFF0000, 0xFF00, 0xFF]),
        'pilreads')
    add('bad-fields-with-8-bits', bmp(2, 1, 8, [[1, 2]], compression=3, masks=[0xE0, 0x1C, 0x3], palette=pal8),
        'refuses')
    add('bad-mask-gap', bmp(2, 1, 16, [[1, 2]], compression=3, masks=[0xF00F, 0x0F00, 0x00F0]), 'refuses')
    add('bad-mask-wider-than-16', bmp(2, 1, 16, [[1, 2]], compression=3, masks=[0x1F0000, 0x07E0, 0x1F]),
        'refuses')
    add('bad-masks-cut-off', bmp(2, 1, 16, [[1, 2]], compression=3, masks=[0xF800, 0x07E0, 0x001F])[:54 + 6],
        'refuses')
    add('bad-palette-too-big', patch(good, 46, '<I', 0x10000000), 'refuses')
    add('bad-palette-cut-off', bmp(2, 1, 8, [[1, 2]], header=12, palette=pal8, offset=0)[:26 + 100],
        'refuses')
    add('bad-offset-past-end', patch(good, 10, '<I', len(good) + 1), 'refuses')
    add('bad-offset-in-header', patch(bmp(2, 1, 24, [[1, 2]]), 10, '<I', 20), 'pilreads')
    add('bad-pixels-cut-off', good[:-5], 'refuses')
    add('bad-pixels-one-short', bmp(5, 2, 8, [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]], palette=pal8)[:-4],
        'refuses')
    # sizes: a pixel bomb in a tiny file, the limit exactly, and one over it
    bomb = bmp(1, 1, 8, palette=pal8[:2], compression=1, data=rle('end'))
    add('bomb-65536-square', patch(patch(bomb, 18, '<i', 65536), 22, '<i', 65536), 'skip')
    add('bomb-wide', patch(patch(bomb, 18, '<i', 0x7FFFFFFF), 22, '<i', 1), 'skip')
    add('bomb-tall-top-down', patch(patch(bmp(1, 1, 24, [[1]]), 18, '<i', 3), 22, '<i', -0x7FFFFFFF),
        'skip')
    add('bomb-os2', patch(patch(bmp(1, 1, 8, [[1]], header=12, palette=pal8[:2]), 18, '<H', 65535), 20, '<H', 65535),
        'skip')
    limit = bmp(10, 10, 24, [[0x102030] * 10] * 10)
    add('limit-exactly', limit, 'skip', max_pixels=100)
    add('limit-one-over', limit, 'skip', max_pixels=99)
    add('limit-big', bmp(1, 1, 8, palette=pal8[:2], compression=1,
                         data=rle('end'))[:18] + struct.pack('<ii', 5000, 4000) +
        bmp(1, 1, 8, palette=pal8[:2], compression=1, data=rle('end'))[26:], 'skip', max_pixels=20000000)
    return cases


# ---------------------------------------------------------------- the cases file

def suite_files():
    files = []
    for d in 'gqbx':
        folder = os.path.join(SUITE, d)
        if os.path.isdir(folder):
            for f in sorted(os.listdir(folder)):
                if f.endswith('.bmp'):
                    files.append(d + '/' + f)
    return files


def copy_suite(source):
    if os.path.isdir(SUITE):
        shutil.rmtree(SUITE)
    for d in 'gqbx':
        os.makedirs(os.path.join(SUITE, d))
        for f in sorted(os.listdir(os.path.join(source, d))):
            name = d + '/' + f
            if f.endswith('.bmp') and name not in SUITE_LEFT_OUT:
                shutil.copyfile(os.path.join(source, d, f), os.path.join(SUITE, d, f))


def reference_images(source):
    """BMP Suite's reference image for each file, from its bmpsuite.html (the first one listed is
    the one it calls correct)"""
    import re
    html = open(os.path.join(source, 'html', 'bmpsuite.html')).read()
    refs = {}
    for row in re.findall(r'<tr.*?</tr>', html, re.S):
        files = re.findall(r'([gqbx]/[a-z0-9-]+\.bmp)', row)
        images = [i for i in re.findall(r'<img[^>]*src="([^"]+)"', row) if not i.startswith('../')]
        if files and images and images[0].endswith('.png'):
            refs[files[0]] = os.path.join(source, 'html', images[0])
    return refs


def check_suite(source):
    """the rules against BMP Suite's reference images and Pillow; returns the problems"""
    import numpy as np
    from PIL import Image
    refs = reference_images(source) if source else {}
    problems = []
    counts = {'ref same': 0, 'ref within 1': 0, 'ref noted': 0, 'pil same': 0, 'pil within 1': 0,
              'pil noted': 0, 'pil refuses': 0}
    for name in suite_files():
        data = open(os.path.join(SUITE, name), 'rb').read()
        ok, result = decode(data)
        mine = as_rgba(*result) if ok else None
        note = SUITE_NOTES.get(name, ('', ''))[0]
        if name in refs and ok:
            ref = np.asarray(Image.open(refs[name]).convert('RGBA'), dtype=np.uint8)
            d = difference(mine, ref)
            if d == 0:
                counts['ref same'] += 1
            elif note == 'ref1' and d == 1:
                counts['ref within 1'] += 1
            elif note == 'ref':
                counts['ref noted'] += 1
            else:
                problems.append('%s: differs from BMP Suite\'s reference image by %s' % (name, d))
        elif name in refs and name[0] in 'gq' and not ok:
            print('  refused, though BMP Suite has an image for it: %s (%s)' % (name, result))
        p = pillow(data)
        if p is None:
            counts['pil refuses'] += 1
            continue
        if not ok:
            if note != 'pilread':
                problems.append('%s: Pillow reads it, but the rules refuse it: %s' % (name, result))
            continue
        d = difference(mine, p)
        if d == 0:
            counts['pil same'] += 1
        elif note == 'pil1' and d == 1:
            counts['pil within 1'] += 1
        elif note == 'pil':
            counts['pil noted'] += 1
        else:
            problems.append('%s: differs from Pillow by %s' % (name, d))
    return counts, problems


def check_made(cases):
    problems = []
    counts = {'same': 0, 'within1': 0, 'refuses': 0, 'pilreads': 0, 'skip': 0}
    for name, data, max_pixels, rule in cases:
        ok, result = decode(data, max_pixels or MAX_PIXELS)
        if rule == 'skip':
            counts['skip'] += 1
            continue
        p = pillow(data)
        if rule == 'pilreads':
            if ok or p is None:
                problems.append('%s: should be read by Pillow and refused here' % name)
            else:
                counts['pilreads'] += 1
            continue
        if rule == 'refuses':
            if ok or p is not None:
                problems.append('%s: should be refused by both, but the rules say %s and Pillow %s' %
                                (name, 'ok' if ok else 'no', 'reads it' if p is not None else 'no'))
            else:
                counts['refuses'] += 1
            continue
        if not ok:
            problems.append('%s: the rules refuse it: %s' % (name, result))
            continue
        if p is None:
            problems.append('%s: Pillow refuses it' % name)
            continue
        d = difference(as_rgba(*result), p)
        if d == 0 or (rule == 'within1' and d == 1):
            counts[rule if d else 'same'] += 1
        else:
            problems.append('%s: differs from Pillow by %s' % (name, d))
    return counts, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bmpsuite', help='the unpacked bmpsuite-2.8, to copy and check against')
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if args.bmpsuite:
        copy_suite(args.bmpsuite)
    if not suite_files():
        sys.exit('no BMP Suite files in %s: give --bmpsuite DIR' % SUITE)

    counts, problems = check_suite(args.bmpsuite)
    print('BMP Suite against its reference images and Pillow:', counts)
    made = made_cases()
    made_counts, made_problems = check_made(made)
    print('cases made here, against Pillow:', made_counts)
    problems += made_problems
    if problems:
        print('\n'.join(problems))
        sys.exit('the rules and the outside evidence disagree')

    cases = CaseFile(decode, MAX_PIXELS, OUT, 'make_bmp_tests.py', GROUP_NAMES)
    index = {}
    for name in suite_files():
        data = open(os.path.join(SUITE, name), 'rb').read()
        index[name] = cases.add(SUITE_GROUP, 0, name, data, payload='tests/bmp/bmpsuite/' + name)
    for name, data, max_pixels, _ in made:
        index[name] = cases.add(MADE, 1, name, data, max_pixels)

    # cut short: every length near the start, and then every 29th, and near the end
    for name in ('g/pal8.bmp', 'g/pal4rle.bmp', 'g/pal8rle.bmp', 'g/rgb16-565.bmp', 'q/rgba32h56.bmp',
                 'g/pal8os2.bmp', 'depth1-w9', 'depth4-w5-topdown', 'fields-8888-header124',
                 'rle8-delta', 'rle4-absolute-odd', 'last-row-unpadded'):
        source = index[name]
        data = cases.list[source][5]
        at = 0
        while at < len(data):
            cases.add(CUT, 2, '%s-to-%d' % (name, at), data[:at], 0, (source, at))
            at += 1 if at < 160 or len(data) - at <= 40 else 29

    # fuzz: small files with a few bytes changed, mostly in the headers
    r = random.Random(20261108)
    small = [name for name, data, _, rule in made if len(data) < 400 and not name.startswith('bad-')
             and not name.startswith('bomb-') and not name.startswith('limit-')]
    for k in range(4000):
        name = r.choice(small)
        source = index[name]
        data = bytearray(cases.list[source][5])
        changes = []
        for _ in range(r.choice((1, 1, 2, 3, 5))):
            at = r.randrange(min(len(data), 80)) if r.random() < 0.7 else r.randrange(len(data))
            v = r.choice((0, 1, 255, 0x7F, 0x80, r.randrange(256), data[at] ^ (1 << r.randrange(8))))
            data[at] = v
            changes.append((at, v))
        cases.add(FUZZ, 3, 'fuzz-%d-%s' % (k, name), bytes(data), 0, (source, changes))

    size = cases.write()
    print('cases.bin: %d cases, %d bytes:' % (len(cases.list), size), cases.summary())


if __name__ == '__main__':
    main()
