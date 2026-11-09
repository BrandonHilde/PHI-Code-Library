#!/usr/bin/env python3
"""Makes the cases imagelib's PNG decoder is tested on, and checks what they expect against
outside evidence.

    python3 -P tools/image/make_png_tests.py                        # from the committed PngSuite copy
    python3 -P tools/image/make_png_tests.py --pngsuite DIR         # copies PngSuite from DIR first
                                                                    # (DIR is PngSuite-2017jul19 unpacked)

(-P rather than -I, since Pillow and numpy are usually in the user's site-packages. ImageMagick's
`magick` must be on the path.)

Writes libs/image/tests/png/:

    pngsuite/      PngSuite's images (free to copy and pass on), copied from DIR when --pngsuite is given
    cases.bin      every case: where its bytes come from, and what imagelib must make of it
    cases.txt      the same, readable: one a line

What each case expects comes from png_reference.py, the rules written plainly in Python. Before
writing anything, this checks those rules against outside evidence and stops if they disagree in a
way that isn't listed:

    PngSuite          its files whose names start with x are broken, and the rest aren't
    ImageMagick       which reads PNG with libpng: every pixel, at 16 bits, must be the same
    Pillow            whose own PNG reader shares no code with libpng: counted, and where it
                      differs the reason is listed (in PILLOW_NOTES, or by a case's rule)

Four groups of cases, in cases.bin (its format is in cases.py):

    suite   PngSuite's files
    made    files written here, for what PngSuite doesn't cover: every color type and bit depth at
            many sizes, interlaced and not, every filter; tRNS and PLTE of each kind; chunks of every
            sort in every wrong place; image data that's damaged, short or too long; and the limit
    cut     good files cut short at many lengths
    fuzz    small files with a few bytes changed, with a fixed seed. Most have their CRCs mended
            after the change, so the change gets past the CRC to what it was aimed at
"""
import argparse
import io
import os
import random
import shutil
import struct
import subprocess
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from png_reference import decode, MAX_PIXELS, SIGNATURE, CHANNELS, DEPTHS, passes  # noqa: E402
from cases import Cases as CaseFile, as_rgba, run_magick  # noqa: E402

LIB = os.path.normpath(os.path.join(HERE, '..', '..', 'libs', 'image'))
OUT = os.path.join(LIB, 'tests', 'png')
SUITE = os.path.join(OUT, 'pngsuite')

SUITE_GROUP, MADE, CUT, FUZZ = 0, 1, 2, 3

# The everyday cases prove each feature, and are what build.ps1 -Test runs. With --release, this
# also makes the release cases (release.bin): every size, and files cut short at many lengths and
# fuzzed, all checked against the outside evidence; those are for when the library is near release.
RELEASE = False

GROUP_NAMES = ['suite', 'made', 'cut', 'fuzz']

# Where Pillow 11.1 differs from the rules on PngSuite, and why. ImageMagick must agree on every one.
PILLOW_NOTES = {
    'pil1': 'Pillow cuts 16-bit samples to their top byte, rather than rounding',
    'pil16gray': 'Pillow clips 16-bit gray to 255, rather than scaling it',
    'piltrns': 'Pillow doesn\'t scale the tRNS color of a gray image of under 8 bits',
    'pilcrc': 'Pillow reads it, though its IDAT\'s CRC is wrong',
}


# ---------------------------------------------------------------- the two outside decoders

def zero_clear(a):
    a = a.copy()
    a[a[:, :, 3] == 0] = 0
    return a


def difference(a, b):
    """the largest difference in any channel, counting fully transparent pixels as 0; None if the
    sizes differ"""
    import numpy as np
    if a.shape != b.shape:
        return None
    return int(np.abs(zero_clear(a).astype(np.int16) - zero_clear(b).astype(np.int16)).max())


def magick(data):
    """ImageMagick's (libpng's) pixels, as 8 bits by the same rounding; None if it refuses. It's
    given -regard-warnings, so that what libpng only warns about counts as refusing, and its
    reading of a file it doesn't refuse is compared too (see magick_lenient)."""
    import numpy as np
    r = run_magick(['-regard-warnings', 'png:-', '-endian', 'MSB', '-depth', '16',
                    '-format', '%w %h\n', '-write', 'info:-', 'rgba:-'], data)
    if r is None or r.returncode != 0:
        return None
    head, _, body = r.stdout.partition(b'\n')
    w, h = map(int, head.split())
    if len(body) != w * h * 8:
        return None
    a = np.frombuffer(body, dtype='>u2').reshape(h, w, 4).astype(np.int64)
    return ((a * 255 + 32767) // 65535).astype(np.uint8)


def magick_lenient(data):
    """ImageMagick's pixels without -regard-warnings: what libpng shows after a warning"""
    import numpy as np
    r = run_magick(['png:-', '-endian', 'MSB', '-depth', '16', '-format', '%w %h\n',
                    '-write', 'info:-', 'rgba:-'], data)
    if r is None or r.returncode != 0:
        return None
    head, _, body = r.stdout.partition(b'\n')
    try:
        w, h = map(int, head.split())
    except ValueError:
        return None
    if len(body) != w * h * 8:
        return None
    a = np.frombuffer(body, dtype='>u2').reshape(h, w, 4).astype(np.int64)
    return ((a * 255 + 32767) // 65535).astype(np.uint8)


def pillow(data, truncated=False):
    import numpy as np
    from PIL import Image, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = truncated
    try:
        im = Image.open(io.BytesIO(data))
        if im.format != 'PNG':
            return None
        im.load()
        return np.asarray(im.convert('RGBA'), dtype=np.uint8)
    except Exception:
        return None


# ---------------------------------------------------------------- writing PNG files

def chunk(name, body=b'', crc=None):
    kind = name.encode('latin-1')
    if crc is None:
        crc = zlib.crc32(kind + body)
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', crc & 0xFFFFFFFF)


def ihdr(w, h, depth, color, interlace=0, method=0, filtering=0):
    return chunk('IHDR', struct.pack('>IIBBBBB', w, h, depth, color, method, filtering, interlace))


def pack(samples, depth):
    if depth == 16:
        return b''.join(struct.pack('>H', s) for s in samples)
    if depth == 8:
        return bytes(samples)
    per = 8 // depth
    out = bytearray((len(samples) + per - 1) // per)
    for k, s in enumerate(samples):
        out[k // per] |= s << (8 - depth - (k % per) * depth)
    return bytes(out)


def paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def filtered(row, prior, step, f):
    out = bytearray(len(row))
    for i in range(len(row)):
        a = row[i - step] if i >= step else 0
        b = prior[i]
        c = prior[i - step] if i >= step else 0
        pred = (0, a, b, (a + b) // 2, paeth(a, b, c))[f]
        out[i] = (row[i] - pred) & 255
    return bytes([f]) + bytes(out)


def image_data(w, h, depth, color, interlace, sample, filters):
    """the image's bytes before compression: sample(x, y, c) gives each sample, and filters(y, pass)
    each row's filter"""
    ch = CHANNELS[color]
    bits = depth * ch
    step = max(1, bits // 8)
    out = bytearray()
    for p, (x0, y0, dx, dy, pw, ph) in enumerate(passes(w, h, interlace)):
        prior = bytes((pw * bits + 7) // 8)
        for y in range(ph):
            row = pack([sample(x0 + x * dx, y0 + y * dy, c) for x in range(pw) for c in range(ch)], depth)
            out += filtered(row, prior, step, filters(y, p))
            prior = row
    return bytes(out)


def png(w, h, depth, color, interlace=0, seed=0, filters=None, palette=None, trns=None,
        before=b'', between=b'', after=b'', idat_sizes=None, data=None, level=6, header=None,
        sample=None, end=None):
    """a PNG file. Samples are random (with the seed) unless sample is given; filters cycle
    through all five unless given; a palette image gets a palette of 2^depth colors unless given.
    before goes after IHDR, between after PLTE and tRNS, after after the IDATs."""
    r = random.Random(seed)
    top = (1 << depth) - 1
    if palette is None and color == 3:
        palette = [(r.randrange(256), r.randrange(256), r.randrange(256)) for _ in range(1 << depth)]
    if sample is None:
        cache = {}

        def sample(x, y, c):
            key = (x, y, c)
            if key not in cache:
                cache[key] = r.randint(0, min(top, len(palette) - 1) if color == 3 else top)
            return cache[key]
    if filters is None:
        def filters(y, p):
            return (y + p) % 5
    if data is None:
        data = zlib.compress(image_data(w, h, depth, color, interlace, sample, filters), level)
    out = SIGNATURE + (header if header is not None else ihdr(w, h, depth, color, interlace)) + before
    if palette is not None:
        out += chunk('PLTE', b''.join(bytes(c) for c in palette))
    if trns is not None:
        out += chunk('tRNS', trns)
    out += between
    if idat_sizes is None:
        out += chunk('IDAT', data)
    else:
        at = 0
        for size in idat_sizes:
            out += chunk('IDAT', data[at:at + size])
            at += size
        if at < len(data):
            out += chunk('IDAT', data[at:])
    out += after
    out += chunk('IEND') if end is None else end
    return out


# ---------------------------------------------------------------- the cases made here

# A case is checked against libpng (through ImageMagick): when the rules read it, libpng must give
# the same pixels, with a warning or not; when they refuse it, libpng must refuse it too. Where libpng
# refuses a file that the rules read, as it does a file whose image data ends too soon, Pillow
# (with LOAD_TRUNCATED_IMAGES, as a browser shows such a file) must agree on every pixel the rules
# made, as it fills the rest its own way. A case's rule is 'limit' when it's refused for imagelib's
# pixel limit, which neither has.

def made_cases():
    cases = []

    def add(name, data, rule='auto', max_pixels=0):
        cases.append((name, data, max_pixels, rule))

    # every color type and bit depth, at many sizes, interlaced and not, with every filter
    sizes = [(1, 1), (5, 9), (8, 8), (17, 9)] if not RELEASE else [(1, 1), (2, 3), (3, 2), (4, 4), (5, 9), (7, 3), (8, 8), (9, 5), (13, 1), (1, 13),
             (16, 2), (17, 9), (33, 6)]
    seed = 1
    for color, depths in sorted(DEPTHS.items()):
        for depth in depths:
            for interlace in (0, 1):
                for w, h in sizes:
                    name = 'c%d-d%d-%s-%dx%d' % (color, depth, 'i' if interlace else 'n', w, h)
                    add(name, png(w, h, depth, color, interlace, seed))
                    seed += 1
    # each filter alone, on every row, at each byte step
    for f in range(5):
        for color, depth in ((0, 1), (0, 8), (2, 8), (4, 8), (2, 16), (6, 16), (6, 8), (0, 16)):
            add('filter%d-c%d-d%d' % (f, color, depth),
                png(11, 7, depth, color, 0, 100 + f, filters=lambda y, p, f=f: f))
    # a gradient, for Paeth's ties, and a larger image at each compression level
    for level in (0, 1, 9):
        add('gradient-level%d' % level,
            png(40, 30, 8, 2, 0, sample=lambda x, y, c: (x * 6 + y * 3 + c * 50) & 255,
                filters=lambda y, p: 4, level=level))
    add('large-rgba-interlaced', png(97, 61, 8, 6, 1, 7))
    add('large-palette', png(120, 45, 8, 3, 0, 8))

    # tRNS of each kind
    add('trns-palette-some', png(9, 9, 8, 3, 0, 20, palette=[(k, 255 - k, k // 2) for k in range(16)],
                                 sample=lambda x, y, c: (x + y) % 16, trns=bytes([0, 64, 128, 200])))
    add('trns-palette-all', png(9, 9, 4, 3, 1, 21, trns=bytes(range(0, 256, 16))))
    add('trns-palette-longer-than-plte', png(9, 9, 2, 3, 0, 22, trns=bytes([1, 2, 3, 4, 5])))
    add('trns-palette-empty', png(9, 9, 2, 3, 0, 23, trns=b''))
    add('trns-gray8', png(9, 9, 8, 0, 0, sample=lambda x, y, c: (x * 30) & 255, trns=b'\x00\x3c'))
    add('trns-gray1', png(9, 9, 1, 0, 0, sample=lambda x, y, c: (x + y) & 1, trns=b'\x00\x01'))
    add('trns-gray2', png(9, 9, 2, 0, 1, sample=lambda x, y, c: (x + y) & 3, trns=b'\x00\x02'))
    add('trns-gray4-out-of-range', png(9, 9, 4, 0, 0, 24, trns=b'\x00\x1f'))
    add('trns-gray16', png(9, 9, 16, 0, 0, sample=lambda x, y, c: x * 1000 + y, trns=struct.pack('>H', 3002)))
    add('trns-gray16-top-byte-only', png(9, 9, 16, 0, 0, sample=lambda x, y, c: 0x1200 + x, trns=b'\x12\x00'))
    add('trns-rgb8', png(9, 9, 8, 2, 0, sample=lambda x, y, c: ((x, y, 7)[c] * 20) & 255,
                         trns=struct.pack('>HHH', 40, 60, 140)))
    add('trns-rgb16', png(9, 9, 16, 2, 1, sample=lambda x, y, c: (x, y, 7)[c] * 300,
                          trns=struct.pack('>HHH', 600, 900, 2100)))
    add('trns-gray-wrong-length', png(9, 9, 8, 0, 0, 25, trns=b'\x00\x10\x00'))
    add('trns-rgb-wrong-length', png(9, 9, 8, 2, 0, 26, trns=b'\x00\x10'))
    add('trns-in-rgba', png(5, 5, 8, 6, 0, 27, trns=b'\x00\x00\x00\x00\x00\x00'))
    add('trns-in-gray-alpha', png(5, 5, 8, 4, 0, 28, trns=b'\x00\x00'))
    add('trns-after-idat', png(5, 5, 8, 0, 0, sample=lambda x, y, c: x, after=chunk('tRNS', b'\x00\x02')))
    add('trns-twice', png(5, 5, 8, 0, 0, sample=lambda x, y, c: x, trns=b'\x00\x02',
                          between=chunk('tRNS', b'\x00\x03')))
    add('trns-before-plte', png(5, 5, 8, 3, 0, 29, before=chunk('tRNS', b'\x00\x00\x00')))
    add('trns-bad-crc', png(5, 5, 8, 3, 0, 30, between=chunk('tRNS', b'\x00\x00', crc=1)))

    # PLTE of each kind
    add('plte-short-index-past-end', png(8, 8, 4, 3, 0, palette=[(255, 0, 0), (0, 255, 0), (0, 0, 255)],
                                         sample=lambda x, y, c: (x + y * 3) % 16))
    add('plte-one-color', png(4, 4, 1, 3, 0, palette=[(9, 8, 7)], sample=lambda x, y, c: 0))
    add('plte-256-on-1-bit', png(4, 4, 1, 3, 0, 31, palette=[(k, k, k) for k in range(256)]))
    add('plte-in-rgb', png(5, 5, 8, 2, 0, 32, palette=[(1, 2, 3)] * 5))
    add('plte-in-rgba', png(5, 5, 8, 6, 0, 33, palette=[(1, 2, 3)] * 5))
    add('plte-in-gray', png(5, 5, 8, 0, 0, 34, before=chunk('PLTE', b'\x01\x02\x03')))
    add('plte-in-gray-alpha', png(5, 5, 8, 4, 0, 35, before=chunk('PLTE', b'\x01\x02\x03')))
    add('bad-plte-missing', png(5, 5, 8, 3, 0, 36, palette=[], sample=lambda x, y, c: 0).replace(
        chunk('PLTE', b''), b''))
    add('bad-plte-empty', png(5, 5, 8, 3, 0, 37, palette=[], sample=lambda x, y, c: 0))
    add('bad-plte-length', png(5, 5, 8, 3, 0, 38, palette=[(1, 2, 3)], sample=lambda x, y, c: 0,
                               before=b'').replace(chunk('PLTE', b'\x01\x02\x03'), chunk('PLTE', b'\x01\x02\x03\x04')))
    add('bad-plte-too-long', png(5, 5, 8, 3, 0, 39, palette=[(1, 2, 3)] * 257, sample=lambda x, y, c: 0))
    add('bad-plte-twice', png(5, 5, 8, 3, 0, 40, between=chunk('PLTE', b'\x01\x02\x03')))
    add('bad-plte-after-idat', png(5, 5, 8, 2, 0, 41, after=chunk('PLTE', b'\x01\x02\x03')))

    # how the image data is split and wrapped
    add('idat-one-byte-each', png(7, 7, 8, 2, 0, 50, idat_sizes=[1] * 200))
    add('idat-empty-ones', png(7, 7, 8, 2, 1, 51, idat_sizes=[0, 5, 0, 0, 20, 0]))
    add('idat-stored', png(7, 7, 8, 6, 0, 52, level=0))
    add('unknown-ancillary', png(5, 5, 8, 2, 0, 53, before=chunk('teXt', b'hello') + chunk('zzZz', b'\x00' * 30),
                                 between=chunk('pHYs', bytes(9)), after=chunk('tIME', bytes(7))))
    add('ancillary-bad-crc', png(5, 5, 8, 2, 0, 54, before=chunk('tEXt', b'a\x00b', crc=5)))
    add('after-iend', png(5, 5, 8, 2, 0, 55, end=chunk('IEND') + b'\x00\x01junk after the end'))
    add('iend-with-data', png(5, 5, 8, 2, 0, 56, end=chunk('IEND', b'abc')))
    add('apng-chunks', png(5, 5, 8, 6, 0, 57, before=chunk('acTL', struct.pack('>II', 1, 0)),
                           after=chunk('fdAT', struct.pack('>I', 1) + zlib.compress(b'\x00' * 30))))
    add('gamma-and-srgb', png(5, 5, 8, 2, 0, 58, before=chunk('gAMA', struct.pack('>I', 45455)) + chunk('sRGB', b'\x00')))

    # chunks that are wrong
    add('bad-signature', b'\x89PNG\r\n\x1a\x0a'[:7] + b'\x00' + png(3, 3, 8, 0, 0, 60)[8:])
    add('bad-empty', b'')
    add('bad-signature-only', SIGNATURE)
    add('bad-ihdr-crc', png(3, 3, 8, 0, 0, 61).replace(ihdr(3, 3, 8, 0), ihdr(3, 3, 8, 0)[:-1] + b'\x00'))
    add('bad-idat-crc', png(3, 3, 8, 0, 0, 62, idat_sizes=[]).replace(
        chunk('IEND'), b'') + chunk('IDAT', zlib.compress(bytes(12)), crc=7) + chunk('IEND'))
    add('bad-ihdr-not-first', SIGNATURE + chunk('gAMA', struct.pack('>I', 45455)) + png(3, 3, 8, 0, 0, 63)[8:])
    add('bad-ihdr-twice', png(3, 3, 8, 0, 0, 64, before=ihdr(3, 3, 8, 0)))
    add('bad-ihdr-short', png(3, 3, 8, 0, 0, 65, header=chunk('IHDR', struct.pack('>IIBBBB', 3, 3, 8, 0, 0, 0))))
    add('bad-ihdr-long', png(3, 3, 8, 0, 0, 66, header=chunk('IHDR', struct.pack('>IIBBBBBB', 3, 3, 8, 0, 0, 0, 0, 0))))
    add('bad-width-0', png(3, 3, 8, 0, 0, 67, header=ihdr(0, 3, 8, 0), data=zlib.compress(b'')))
    add('bad-height-0', png(3, 3, 8, 0, 0, 68, header=ihdr(3, 0, 8, 0), data=zlib.compress(b'')))
    add('bad-width-2^31', png(3, 3, 8, 0, 0, 69, header=ihdr(0x80000000, 1, 8, 0)))
    for color, depth in ((1, 8), (5, 8), (7, 8), (2, 1), (2, 4), (3, 16), (4, 4), (6, 2), (0, 0), (0, 3), (0, 32)):
        add('bad-c%d-d%d' % (color, depth), png(3, 3, 8, 0, 0, 70, header=ihdr(3, 3, depth, color)))
    add('bad-compression-method', png(3, 3, 8, 0, 0, 71, header=ihdr(3, 3, 8, 0, method=1)))
    add('bad-filter-method', png(3, 3, 8, 0, 0, 72, header=ihdr(3, 3, 8, 0, filtering=1)))
    add('bad-interlace-method', png(3, 3, 8, 0, 0, 73, header=ihdr(3, 3, 8, 0, interlace=2)))
    add('bad-chunk-name', png(3, 3, 8, 0, 0, 74, before=chunk('te1t', b'')))
    add('bad-chunk-length', png(3, 3, 8, 0, 0, 75, before=struct.pack('>I', 0x80000000) + b'teXt'))
    add('bad-chunk-past-end', png(3, 3, 8, 0, 0, 76, before=struct.pack('>I', 0x7FFFFFF0) + b'teXt'))
    add('bad-unknown-critical', png(3, 3, 8, 0, 0, 77, before=chunk('CgBI', bytes(4))))
    add('bad-unknown-critical-after', png(3, 3, 8, 0, 0, 78, after=chunk('ABCD', b'')))
    add('bad-no-idat', SIGNATURE + ihdr(3, 3, 8, 0) + chunk('IEND'))
    add('bad-no-iend', png(3, 3, 8, 0, 0, 79, end=b''))
    z = zlib.compress(image_data(9, 9, 8, 2, 0, lambda x, y, c: x, lambda y, p: 0))
    add('bad-idat-not-together', SIGNATURE + ihdr(9, 9, 8, 2) + chunk('IDAT', z[:20]) + chunk('tEXt', b'a\x00b') +
        chunk('IDAT', z[20:]) + chunk('IEND'))

    # image data that's wrong
    raw = image_data(6, 4, 8, 2, 0, lambda x, y, c: x * 40 + c, lambda y, p: y % 5)
    add('bad-zlib-damaged', png(6, 4, 8, 2, 0, data=b'\x78\x9c\xff\xff\xff' + zlib.compress(raw)[5:]))
    add('bad-zlib-header', png(6, 4, 8, 2, 0, data=b'\x78\x9d' + zlib.compress(raw)[2:]))
    add('bad-zlib-dictionary', png(6, 4, 8, 2, 0, data=b'\x78\xbb' + b'\x00\x00\x00\x01' + zlib.compress(raw)[2:]))
    z = zlib.compress(raw)
    add('bad-zlib-adler', png(6, 4, 8, 2, 0, data=z[:-1] + bytes([z[-1] ^ 1])))
    add('bad-zlib-no-adler', png(6, 4, 8, 2, 0, data=z[:-4]))
    add('bad-zlib-cut', png(6, 4, 8, 2, 0, data=z[:len(z) // 2]))
    add('bad-too-little', png(6, 4, 8, 2, 0, data=zlib.compress(raw[:-1])))
    add('bad-too-little-rows', png(6, 4, 8, 2, 0, data=zlib.compress(raw[:19 * 2])))
    add('bad-too-much', png(6, 4, 8, 2, 0, data=zlib.compress(raw + b'\x00')))
    add('bad-much-too-much', png(6, 4, 8, 2, 0, data=zlib.compress(raw + bytes(100000))))
    add('after-zlib-end', png(6, 4, 8, 2, 0, data=z + b'\x00\x00extra'))
    for f in (5, 9, 255):
        bad = bytearray(raw)
        bad[19] = f
        add('bad-filter-type-%d' % f, png(6, 4, 8, 2, 0, data=zlib.compress(bytes(bad))))
    bad = bytearray(image_data(9, 9, 8, 0, 1, lambda x, y, c: x, lambda y, p: 1))
    bad[-1 - 9] = 7       # in the last pass
    add('bad-filter-type-interlaced', png(9, 9, 8, 0, 1, data=zlib.compress(bytes(bad))))

    # the limit, and files that say they're big
    add('limit-at', png(10, 10, 8, 0, 0, 90), 'same', 100)
    add('limit-over', png(10, 10, 8, 0, 0, 91), 'limit', 99)
    add('limit-default-over', png(4097, 4096, 8, 0, 0, 92, header=ihdr(4097, 4096, 8, 0), data=zlib.compress(b'')),
        'limit')
    add('bomb-claims-big', png(4096, 4096, 16, 6, 0, header=ihdr(4096, 4096, 16, 6), data=zlib.compress(bytes(1000))))
    add('bomb-too-much', png(1, 1, 8, 0, 0, data=zlib.compress(bytes(20 * 1024 * 1024), 9)))
    return cases


# ---------------------------------------------------------------- checking

def suite_files():
    if not os.path.isdir(SUITE):
        return []
    return sorted(f for f in os.listdir(SUITE) if f.endswith('.png'))


def copy_suite(source):
    if os.path.isdir(SUITE):
        shutil.rmtree(SUITE)
    os.makedirs(SUITE)
    for f in sorted(os.listdir(source)):
        if f.endswith('.png') or f in ('PngSuite.LICENSE', 'PngSuite.README'):
            shutil.copyfile(os.path.join(source, f), os.path.join(SUITE, f))


def pillow_note(name, mine, p):
    """why Pillow differs on a PngSuite file, or None if it doesn't or the reason isn't known"""
    d = difference(mine, p)
    if d == 0:
        return None
    if name[5:7] == '16' or name.endswith('16.png'):
        return 'pil1' if d == 1 else 'pil16gray'
    if name.startswith('tbbn0g04') or name.startswith('tbwn0g') or name.startswith('tbgn0g'):
        return 'piltrns'
    return '?'


def check_suite():
    problems = []
    counts = {'magick same': 0, 'magick refuses too': 0, 'pil same': 0, 'pil refuses too': 0}
    notes = {}
    for name in suite_files():
        data = open(os.path.join(SUITE, name), 'rb').read()
        ok, result = decode(data)
        broken = name.startswith('x')
        if ok == broken:
            problems.append('%s: PngSuite calls it %s, but the rules %s' %
                            (name, 'broken' if broken else 'good', 'read it' if ok else 'refuse it: ' + result))
        m = magick(data)
        p = pillow(data)
        if not ok:
            if m is not None:
                problems.append('%s: ImageMagick reads it, but the rules refuse it: %s' % (name, result))
            else:
                counts['magick refuses too'] += 1
            if p is None:
                counts['pil refuses too'] += 1
            elif name == 'xcsn0g01.png':
                notes.setdefault('pilcrc', []).append(name)
            else:
                problems.append('%s: Pillow reads it, and the reason isn\'t listed' % name)
            continue
        mine = as_rgba(*result)
        if m is None or difference(mine, m) != 0:
            problems.append('%s: differs from ImageMagick by %s' % (name, None if m is None else difference(mine, m)))
        else:
            counts['magick same'] += 1
        if p is None:
            problems.append('%s: Pillow refuses it' % name)
            continue
        note = pillow_note(name, mine, p)
        if note is None:
            counts['pil same'] += 1
        elif note == '?':
            problems.append('%s: differs from Pillow by %d, for no listed reason' % (name, difference(mine, p)))
        else:
            notes.setdefault(note, []).append(name)
    return counts, notes, problems


def header(data):
    """the depth and color type an IHDR says, if there's one where it should be"""
    if len(data) >= 26 and data[12:16] == b'IHDR':
        return data[24], data[25]
    return None, None


def pillow_agrees(mine, data):
    """how Pillow, reading a file as far as it goes, compares on the pixels the rules made (all but
    those they left transparent black): 'same', 'within 1' (Pillow cuts 16-bit samples to their top
    byte), 'not comparable' (it clips 16-bit gray), 'differs', or 'refuses'"""
    import numpy as np
    p = pillow(data, truncated=True)
    if p is None or p.shape != mine.shape:
        return 'refuses'
    depth, color = header(data)
    if depth == 16 and color in (0, 4):
        return 'not comparable'
    made = ~((mine[:, :, 3] == 0) & (mine[:, :, :3].sum(axis=2) == 0))
    a, b = zero_clear(mine).astype(np.int16), zero_clear(p).astype(np.int16)
    d = int(np.abs(a - b)[made].max()) if made.any() else 0
    if d == 0:
        return 'same'
    if d == 1 and depth == 16:
        return 'within 1'
    return 'differs'


# Images bigger than this aren't compared with libpng and Pillow: fuzzed headers claim up to the pixel
# limit, and each such image would be held several times over, in each decoder's output and numpy's
# working. They're still checked, against the rules, by imagelib's own tests.
BIGGEST_CHECKED = 1 << 20


def idats_then_iend(data):
    """the file up to the end of its IDATs, and then an IEND: what libpng reads when what comes
    after the IDATs is broken (libpng and Pillow read the next chunk's header, and give up on a
    bad one, where the image is done and a browser shows it); None if there are no whole IDATs"""
    at = 8
    seen = False
    while at + 12 <= len(data):
        length = struct.unpack('>I', data[at:at + 4])[0]
        kind = data[at + 4:at + 8]
        if seen and kind != b'IDAT':
            break
        if length > len(data) - at - 12:
            break
        if kind == b'IDAT':
            seen = True
        at += 12 + length
    return data[:at] + chunk('IEND') if seen else None


def check(cases, problems, full=None):
    """Every case against libpng, and where libpng refuses what the rules read, against the image the
    file was cut from (full, by name: the rules' pixels must be its pixels, wherever the rules made
    one), or failing that, Pillow reading as far as it goes. Pillow differs from the rules on the
    last row it gives of a cut file (it shows a row before the row's all there), and where it
    always does (a tRNS, 16-bit samples), so with a full image to go by its answer is only counted."""
    counts = {}

    def count(k):
        counts[k] = counts.get(k, 0) + 1
    for name, data, max_pixels, rule in cases:
        ok, result = decode(data, max_pixels or MAX_PIXELS)
        if rule == 'limit':
            if ok or 'limit' not in result:
                problems.append('%s: should be refused for the limit' % name)
            count('refused for the limit')
            continue
        if ok and result[0] * result[1] > BIGGEST_CHECKED:
            count('more than a million pixels, so not compared')
            continue
        m = magick_lenient(data)
        if ok:
            mine = as_rgba(*result)
            if m is not None:
                if difference(mine, m) != 0:
                    problems.append('%s: differs from libpng by %s' % (name, difference(mine, m)))
                else:
                    count('the same as libpng' if magick(data) is not None else 'the same as libpng, which warns')
                continue
            made = ~((mine[:, :, 3] == 0) & (mine[:, :, :3].sum(axis=2) == 0))
            verdict = pillow_agrees(mine, data)
            if full is not None and name in full:
                whole = full[name]
                if whole is None or whole.shape != mine.shape or not (mine[made] == whole[made]).all():
                    problems.append('%s: what the rules show of it isn\'t the image it was cut from' % name)
                else:
                    count('libpng refuses it; the rows shown are the full image\'s')
                count('  and Pillow (as far as it reads): ' + verdict)
                continue
            if verdict == 'refuses' and not made.any():
                count('libpng refuses it, nothing came whole, and Pillow gives up')
                continue
            if verdict in ('differs', 'refuses'):
                repaired = idats_then_iend(data)
                ended = magick_lenient(repaired) if repaired is not None else None
                if ended is not None and difference(mine, ended) == 0:
                    count('libpng and Pillow refuse it for a broken chunk after the IDATs; the same as '
                          'libpng with an IEND there')
                    continue
                again = pillow_agrees(mine, repaired) if repaired is not None else 'refuses'
                if again not in ('differs', 'refuses'):
                    count('libpng and Pillow refuse it for a broken chunk after the IDATs; with an IEND '
                          'there, Pillow (as far as it reads): ' + again)
                    continue
            if verdict == 'differs' and (b'tRNS' in data or header(data)[0] == 16):
                verdict = 'differs, as it does with tRNS or 16 bits'
            if verdict in ('differs', 'refuses'):
                problems.append('%s: libpng refuses it, and Pillow %s' % (name, verdict))
            count('libpng refuses it, and Pillow (as far as it reads): ' + verdict)
        elif m is not None:
            problems.append('%s: libpng reads it, where the rules refuse it: %s' % (name, result))
        else:
            count('refused by both')
    return counts


# ---------------------------------------------------------------- fuzzing

def chunk_crcs(data):
    """where each whole chunk's CRC is, and what it should be"""
    out = []
    at = 8
    while at + 12 <= len(data):
        length = struct.unpack('>I', data[at:at + 4])[0]
        if length > len(data) - at - 12:
            break
        crc = zlib.crc32(bytes(data[at + 4:at + 8 + length]))
        out.append((at + 8 + length, crc))
        at += 12 + length
    return out


def small_image(data):
    """whether the rules read data as an image of at most 256 by 256 pixels: fuzz cases start only
    from those, as a small file can claim a big image, and every changed copy of it would be one"""
    ok, result = decode(data)
    return ok and result[0] * result[1] <= 65536


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pngsuite', help='PngSuite-2017jul19 unpacked, to copy and check against')
    ap.add_argument('--release', action='store_true', help='make the release cases too')
    args = ap.parse_args()
    global RELEASE
    RELEASE = args.release
    os.makedirs(OUT, exist_ok=True)
    if args.pngsuite:
        copy_suite(args.pngsuite)
    if not suite_files():
        sys.exit('no PngSuite files in %s: give --pngsuite DIR' % SUITE)

    counts, notes, problems = check_suite()
    print('PngSuite against ImageMagick and Pillow:', counts)
    for k, v in notes.items():
        print('  Pillow differs on %d (%s): %s' % (len(v), PILLOW_NOTES[k], ' '.join(v)))
    made = made_cases()
    print('cases made here, against libpng (and Pillow):', check(made, problems))

    cases = CaseFile(decode, MAX_PIXELS, OUT, 'make_png_tests.py', GROUP_NAMES)
    index = {}
    for name in suite_files():
        data = open(os.path.join(SUITE, name), 'rb').read()
        index[name] = cases.add(SUITE_GROUP, 0, name, data, payload='tests/png/pngsuite/' + name)
    for name, data, max_pixels, _ in made:
        index[name] = cases.add(MADE, 1, name, data, max_pixels)
    if not RELEASE:
        if problems:
            print('\n'.join(problems))
            sys.exit('the rules and the outside evidence disagree, %d times' % len(problems))
        size = cases.write()
        print('cases.bin: %d cases, %d bytes:' % (len(cases.list), size), cases.summary())
        return

    # cut short: every length near the start, and then every 13th, and near the end
    for name in ('basn0g01.png', 'basi2c08.png', 'basn3p04.png', 'basi6a16.png', 'tbrn2c08.png',
                 'c3-d2-i-17x9', 'c6-d8-n-33x6', 'idat-one-byte-each', 'idat-stored', 'trns-rgb16'):
        source = index[name]
        data = cases.list[source][5]
        at = 0
        while at < len(data):
            cases.add(CUT, 2, '%s-to-%d' % (name, at), data[:at], 0, (source, at))
            at += 1 if at < 120 or len(data) - at <= 40 else 13

    # fuzz: a few bytes changed, mostly near the start; three in four with their CRCs mended
    r = random.Random(20261108)
    small = [name for name, data, _, rule in made if len(data) < 600 and rule != 'limit' and small_image(data)]
    small += [name for name in suite_files() if not name.startswith('x') and os.path.getsize(os.path.join(SUITE, name)) < 600]
    for k in range(4000):
        name = r.choice(small)
        source = index[name]
        base = cases.list[source][5]
        data = bytearray(base)
        changes = {}
        for _ in range(r.choice((1, 1, 2, 3, 5))):
            at = r.randrange(min(len(data), 60)) if r.random() < 0.6 else r.randrange(len(data))
            v = r.choice((0, 1, 255, 0x7F, 0x80, r.randrange(256), data[at] ^ (1 << r.randrange(8))))
            data[at] = v
            changes[at] = v
        if k % 4:
            for at, crc in chunk_crcs(data):
                for i, b in enumerate(struct.pack('>I', crc)):
                    if data[at + i] != b:
                        data[at + i] = b
                        changes[at + i] = b
        changes = sorted(changes.items())
        cases.add(FUZZ, 3, 'fuzz-%d-%s' % (k, name), bytes(data), 0, (source, changes))

    # the cut and fuzz cases against libpng and Pillow too, as they're damaged files of every kind
    # (each cut one with the image it was cut from, the rules' reading of the whole file)
    whole = {}
    for c in cases.list:
        if c[0] == CUT:
            source = cases.list[c[4][0]]
            if source[2] not in whole:
                ok, result = decode(source[5])
                whole[source[2]] = as_rgba(*result) if ok else None
    full = {c[2]: whole[cases.list[c[4][0]][2]] for c in cases.list if c[0] == CUT}
    for group, label in ((CUT, 'cut'), (FUZZ, 'fuzz')):
        print('%s, against libpng (and Pillow):' % label,
              check([(c[2], c[5], 0, 'auto') for c in cases.list if c[0] == group], problems,
                    full if group == CUT else None))
    if problems:
        print('\n'.join(problems[:200]))
        if os.environ.get('WRITE_ANYWAY'):
            cases.write()               # for looking into the problems: OUT is the caller's
        sys.exit('the rules and the outside evidence disagree, %d times' % len(problems))

    size = cases.write('release')
    print('release.bin: %d cases, %d bytes:' % (len(cases.list), size), cases.summary())


if __name__ == '__main__':
    main()
