"""Makes libs/image/tests/scale/cases.bin (with cases.txt): the cases test_scale runs Img.Scale against,
checked with the rules in scale_reference.py, which must give Pillow's pixels exactly on every one.

    python3 tools/image/make_scale_tests.py [--release]

A case's pixels aren't kept: they're made the same way here and in test_scale, from a seed. The
format (little-endian):

    u32 count, then for each:
      u8 name length, name, u8 how (0 nearest, 1 bilinear, others refused), u8 pixels (the kind below),
      u32 seed, i32 width, i32 height, i32 new width, i32 new height, u32 max_pixels (0: the default),
      u8 ok; if ok: u32 CRC-32 of the new pixels (each as 4 bytes, B G R A, top row first);
      if not: u8 length, the reason

The kinds of pixels, each made with xorshift32 from the seed: 0 noise; 1 noise, opaque; 2 noise, each
pixel opaque or transparent; 3 a smooth opaque gradient; 4 a gradient whose alpha goes from 0 to 255
across it.
"""
import argparse
import array
import io
import os
import random
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scale_reference  # noqa: E402
from cases import pixel_crc  # noqa: E402

OUT = os.path.normpath(os.path.join(HERE, '..', '..', 'libs', 'image', 'tests', 'scale'))
MAX_PIXELS = 16 * 1024 * 1024
RELEASE = False


def pixels(kind, seed, w, h):
    out = array.array('I', [0]) * (w * h)
    s = seed or 1
    for i in range(w * h):
        x, y = i % w, i // w
        s ^= (s << 13) & 0xFFFFFFFF
        s ^= s >> 17
        s ^= (s << 5) & 0xFFFFFFFF
        if kind == 0:
            v = s
        elif kind == 1:
            v = s | 0xFF000000
        elif kind == 2:
            v = s | 0xFF000000 if s & 0x80000000 else s & 0x00FFFFFF
        else:
            r = x * 255 // max(w - 1, 1)
            g = y * 255 // max(h - 1, 1)
            b = (x + y) * 7 & 255
            a = 255 if kind == 3 else r
            v = a << 24 | r << 16 | g << 8 | b
        out[i] = v
    return out


def rule(how, kind, seed, w, h, nw, nh, max_pixels):
    """(True, the new pixels) or (False, why), as Img.Scale has it"""
    if nw <= 0 or nh <= 0:
        return False, 'a size of no pixels: %d by %d' % (nw, nh)
    if how not in (0, 1):
        return False, 'not a way of scaling imagelib has'
    limit = max_pixels or MAX_PIXELS
    if nw * nh > limit:
        return False, '%d by %d is more than the limit of %d pixels' % (nw, nh, limit)
    return True, scale_reference.scale(w, h, pixels(kind, seed, w, h), nw, nh, how == 1)


def pillow(how, kind, seed, w, h, nw, nh):
    import numpy as np
    from PIL import Image
    px = np.frombuffer(pixels(kind, seed, w, h), np.uint32).reshape(h, w)
    a = np.stack([(px >> 16) & 255, (px >> 8) & 255, px & 255, px >> 24], axis=2).astype(np.uint8)
    out = np.asarray(Image.fromarray(a, 'RGBA').resize((nw, nh), Image.BILINEAR if how else Image.NEAREST))
    return out


def same_as_pillow(result, how, kind, seed, w, h, nw, nh):
    import numpy as np
    m = np.frombuffer(result, np.uint32).reshape(nh, nw)
    mine = np.stack([(m >> 16) & 255, (m >> 8) & 255, m & 255, m >> 24], axis=2).astype(np.uint8)
    theirs = pillow(how, kind, seed, w, h, nw, nh)
    return mine.shape == theirs.shape and (mine == theirs).all()


def cases():
    out = []
    n = [0]

    def add(name, how, kind, w, h, nw, nh, max_pixels=0):
        n[0] += 1
        out.append((name, how, kind, 1000 + n[0], w, h, nw, nh, max_pixels))

    sizes = [(5, 4, 11, 9), (11, 9, 5, 4), (16, 16, 8, 8), (16, 16, 32, 32), (7, 3, 7, 10), (7, 3, 20, 3),
             (1, 1, 6, 4), (6, 4, 1, 1), (100, 3, 7, 3), (3, 100, 3, 7), (33, 17, 64, 5), (64, 48, 63, 47),
             (5, 5, 5, 5), (40, 40, 3, 3), (2, 2, 9, 9)]
    if RELEASE:
        sizes += [(300, 200, 77, 51), (77, 51, 300, 200), (1000, 2, 999, 2), (1, 500, 3, 499), (256, 256, 255, 257)]
    for w, h, nw, nh in sizes:
        for how in (0, 1):
            for kind in ((0, 1, 2, 3, 4) if RELEASE else (0, 3, 4) if how else (0,)):
                add('%s-%dx%d-to-%dx%d-%s' % (('nearest', 'bilinear')[how], w, h, nw, nh,
                                              ('noise', 'opaque', 'clear', 'gradient', 'alpha')[kind]), how, kind, w, h, nw, nh)
    add('bilinear-opaque-noise', 1, 1, 9, 7, 4, 13)
    add('bilinear-clear-noise', 1, 2, 9, 7, 4, 13)
    add('limit-12-pixels', 1, 0, 5, 5, 4, 3, 12)
    add('limit-11-pixels', 1, 0, 5, 5, 4, 3, 11)
    add('no-width', 1, 0, 5, 5, 0, 3)
    add('negative-height', 0, 0, 5, 5, 3, -2)
    add('no-such-way', 2, 0, 5, 5, 3, 3)
    if RELEASE:
        r = random.Random(20261109)
        dims = [1, 2, 3, 4, 5, 7, 8, 9, 13, 16, 17, 31, 32, 33, 50, 64, 99, 100, 127, 128]
        for k in range(1500):
            w, h, nw, nh = (r.choice(dims) for _ in range(4))
            how = r.randrange(2)
            add('random-%d' % k, how, r.randrange(5), w, h, nw, nh)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--release', action='store_true', help='make the release cases')
    args = ap.parse_args()
    global RELEASE
    RELEASE = args.release
    os.makedirs(OUT, exist_ok=True)

    data = bytearray()
    lines = ['# made by tools/image/make_scale_tests.py: what Img.Scale must make of each case']
    all_cases = cases()
    data += struct.pack('<I', len(all_cases))
    same = refused = 0
    for name, how, kind, seed, w, h, nw, nh, max_pixels in all_cases:
        ok, result = rule(how, kind, seed, w, h, nw, nh, max_pixels)
        nb = name.encode()
        data += struct.pack('<B', len(nb)) + nb + struct.pack('<BBIiiiiI', how, kind, seed, w, h, nw, nh, max_pixels)
        if ok:
            if not same_as_pillow(result, how, kind, seed, w, h, nw, nh):
                sys.exit('%s: the rules differ from Pillow' % name)
            same += 1
            data += struct.pack('<BI', 1, pixel_crc(result))
            lines.append('%-48s ok' % name)
        else:
            refused += 1
            rb = result.encode()
            data += struct.pack('<BB', 0, len(rb)) + rb
            lines.append('%-48s refused: %s' % (name, result))
    filename = 'release' if RELEASE else 'cases'
    with open(os.path.join(OUT, filename + '.bin'), 'wb') as f:
        f.write(data)
    with open(os.path.join(OUT, filename + '.txt'), 'w', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    print('%s.bin: %d cases, %d bytes: %d the same as Pillow, %d refused' % (filename, len(all_cases), len(data), same, refused))


if __name__ == '__main__':
    main()
