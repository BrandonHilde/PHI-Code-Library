#!/usr/bin/env python3
"""Makes the cases imagelib's WebP decoder is tested against, with libwebp (through ImageMagick 7,
whose WebP coder is libwebp's encoder and decoder).

    python3 -I tools/image/make_webp_tests.py

Writes libs/image/tests/webp/cases.bin and cases.txt. The pictures are made here (in plain Python),
encoded by libwebp with each kind of setting, and decoded by libwebp for what imagelib must give:

    lossless   every kind of transform libwebp chooses among (methods 0 to 6), palettes of 2, 4,
               16 and 200 colors (so indexes packed 8, 4, 2 and 1 to a pixel), alpha, odd sizes,
               and 1 by 1. imagelib must give libwebp's pixels exactly.
    lossy      qualities from 5 to 100, odd sizes (not a whole number of macroblocks), alpha kept
               raw and packed losslessly with each filter, the simple loop filter and the normal one
               at several strengths and sharpnesses, 1 to 4 segments, 1 to 8 partitions, and every
               encoder method. imagelib must give libwebp's pixels exactly too: the RFC leaves the
               color upsampling and YUV to RGB to the decoder, and imagelib's are libwebp's.
    damaged    a third of the good files under 8 KB, cut short and with bytes changed (fixed seed):
               each must come back, read or refused, without a crash.

The format of cases.bin (little-endian):
    u32 count, then each: u8 kind (0 lossless, 1 lossy, 2 damaged), u8 name length, name,
    u32 length, the file, u8 ok (what libwebp did); if ok: u32 width, u32 height, and for a
    lossless or lossy case u32 CRC-32 of libwebp's pixels (each B G R A)
"""
import os
import random
import struct
import subprocess
import sys
import tempfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'libs', 'image', 'tests', 'webp')


def pam(w, h, px):
    """RGBA pixels (a list of (r, g, b, a)) as a PAM file"""
    head = f'P7\nWIDTH {w}\nHEIGHT {h}\nDEPTH 4\nMAXVAL 255\nTUPLTYPE RGB_ALPHA\nENDHDR\n'.encode()
    return head + bytes(v for p in px for v in p)


def picture(kind, w, h, seed=1):
    rnd = random.Random(seed)
    px = []
    for y in range(h):
        for x in range(w):
            if kind == 'photo':
                r = (x * 255 // max(w - 1, 1) + rnd.randint(-12, 12)) & 255
                g = (y * 255 // max(h - 1, 1) + rnd.randint(-12, 12)) & 255
                b = ((x + y) * 3 + rnd.randint(-20, 20)) & 255
                px.append((r, g, b, 255))
            elif kind == 'drawing':
                c = (255, 255, 255)
                if (x - w // 2) ** 2 + (y - h // 2) ** 2 < (min(w, h) // 3) ** 2:
                    c = (47, 111, 228)
                if w // 8 < x < w // 3 and h // 6 < y < h // 2:
                    c = (229, 72, 77)
                if (x + y) % 23 < 2:
                    c = (0, 0, 0)
                px.append(c + (255,))
            elif kind.startswith('palette'):
                n = int(kind[7:])
                i = ((x // 3) * 7 + (y // 2) * 3) % n
                px.append(((i * 37) & 255, (i * 91) & 255, (i * 13 + 40) & 255, 255))
            elif kind == 'alpha':
                a = (x * 255 // max(w - 1, 1))
                px.append(((y * 9) & 255, 120, (x * 5) & 255, a))
            elif kind == 'cutout':
                inside = (x - w / 2) ** 2 + (y - h / 2) ** 2 < (min(w, h) / 2.5) ** 2
                px.append(((x * 4) & 255, (y * 4) & 255, 200, 255 if inside else (0 if (x + y) % 3 else 90)))
            elif kind == 'flat':
                px.append((10, 200, 30, 255))
    return px


def magick(args, data=None):
    r = subprocess.run(['magick'] + args, input=data, capture_output=True, timeout=120)
    return r


def encode(src, opts):
    with tempfile.TemporaryDirectory(dir=os.path.expanduser('~')) as d:
        a, b = os.path.join(d, 'in.pam'), os.path.join(d, 'out.webp')
        with open(a, 'wb') as f:
            f.write(src)
        r = magick([a] + opts + [b])
        if r.returncode != 0:
            sys.exit('magick could not encode: ' + r.stderr.decode())
        with open(b, 'rb') as f:
            return f.read()


def decode(data):
    """libwebp's pixels: (w, h, RGBA bytes), or None if it refuses"""
    with tempfile.TemporaryDirectory(dir=os.path.expanduser('~')) as d:
        a = os.path.join(d, 'in.webp')
        with open(a, 'wb') as f:
            f.write(data)
        r = magick(['identify', '-format', '%w %h', a])
        if r.returncode != 0 or not r.stdout:
            return None
        w, h = (int(v) for v in r.stdout.split()[:2])
        r = magick([a + '[0]', '-depth', '8', 'rgba:-'])
        if r.returncode != 0 or len(r.stdout) != w * h * 4:
            return None
        return w, h, r.stdout


def crc_bgra(rgba):
    out = bytearray(len(rgba))
    out[0::4], out[1::4], out[2::4], out[3::4] = rgba[2::4], rgba[1::4], rgba[0::4], rgba[3::4]
    return zlib.crc32(bytes(out))


def main():
    os.makedirs(OUT, exist_ok=True)
    cases = []
    lossless = [('photo', 64, 48), ('drawing', 120, 80), ('palette2', 33, 17), ('palette4', 33, 17),
                ('palette16', 40, 30), ('palette200', 40, 30), ('alpha', 50, 30), ('cutout', 48, 48),
                ('photo', 1, 1), ('photo', 3, 7), ('drawing', 17, 5), ('flat', 300, 200)]
    for kind, w, h in lossless:
        src = pam(w, h, picture(kind, w, h))
        for method in (0, 4, 6):
            if kind != 'photo' and method == 0 and (w, h) != (64, 48):
                continue
            opts = ['-define', 'webp:lossless=true', '-define', f'webp:method={method}', '-define', 'webp:exact=true']
            cases.append((0, f'lossless {kind} {w}x{h} method {method}', encode(src, opts)))
    lossy = [('photo', 64, 48, 75), ('photo', 64, 48, 5), ('photo', 64, 48, 100), ('drawing', 120, 80, 50),
             ('photo', 33, 17, 80), ('photo', 1, 1, 75), ('alpha', 50, 30, 80), ('cutout', 48, 48, 60)]
    for kind, w, h, q in lossy:
        src = pam(w, h, picture(kind, w, h))
        opts = ['-quality', str(q)]
        cases.append((1, f'lossy {kind} {w}x{h} q{q}', encode(src, opts)))
        if kind in ('alpha', 'cutout'):
            for comp, filt in ((0, 'none'), (1, 'none'), (1, 'fast'), (1, 'best')):
                o = opts + ['-define', f'webp:alpha-compression={comp}', '-define', f'webp:alpha-filtering={filt}']
                cases.append((1, f'lossy {kind} {w}x{h} q{q} alpha {comp} {filt}', encode(src, o)))
    # the encoder's other choices, each on a bigger picture: the simple filter and the normal one at
    # several strengths and sharpnesses, no filter, 1 to 4 segments, 2, 4 and 8 partitions, and
    # every method (which tries more 4x4 modes the higher it is)
    big = pam(160, 120, picture('photo', 160, 120, seed=7))
    variants = [
        ('simple filter', ['-define', 'webp:filter-type=0', '-define', 'webp:filter-strength=60']),
        ('strong filter sharp 0', ['-define', 'webp:filter-type=1', '-define', 'webp:filter-strength=80', '-define', 'webp:filter-sharpness=0']),
        ('strong filter sharp 3', ['-define', 'webp:filter-type=1', '-define', 'webp:filter-strength=50', '-define', 'webp:filter-sharpness=3']),
        ('strong filter sharp 7', ['-define', 'webp:filter-type=1', '-define', 'webp:filter-strength=100', '-define', 'webp:filter-sharpness=7']),
        ('no filter', ['-define', 'webp:filter-strength=0']),
        ('1 segment', ['-define', 'webp:segments=1']),
        ('4 segments sns 100', ['-define', 'webp:segments=4', '-define', 'webp:sns-strength=100']),
        ('2 partitions', ['-define', 'webp:partitions=1']),
        ('4 partitions', ['-define', 'webp:partitions=2']),
        ('8 partitions', ['-define', 'webp:partitions=3']),
    ] + [(f'method {m}', ['-define', f'webp:method={m}']) for m in range(7)]
    for name, o in variants:
        cases.append((1, f'lossy photo 160x120 q70 {name}', encode(big, ['-quality', '70'] + o)))
    drawing = pam(200, 150, picture('drawing', 200, 150))
    cases.append((1, 'lossy drawing 200x150 q90 method 6', encode(drawing, ['-quality', '90', '-define', 'webp:method=6'])))

    # damaged: cut short and changed
    rnd = random.Random(20261120)
    good = [c for c in cases if c[0] in (0, 1) and len(c[2]) < 8192]
    damaged = []
    for kind, name, data in good[::3]:
        for cut in (12, 20, 30, len(data) // 2, len(data) - 1):
            if cut < len(data):
                damaged.append((2, f'{name}, cut to {cut}', data[:cut]))
        for k in range(6):
            b = bytearray(data)
            for _ in range(rnd.randint(1, 4)):
                b[rnd.randrange(12, len(b))] = rnd.randrange(256)
            damaged.append((2, f'{name}, changed {k}', bytes(b)))
    cases += damaged

    out = bytearray(struct.pack('<I', len(cases)))
    lines = ['# made by tools/image/make_webp_tests.py: each case, and what libwebp made of it']
    for kind, name, data in cases:
        nb = name.encode()
        out += struct.pack('<BB', kind, len(nb)) + nb + struct.pack('<I', len(data)) + data
        got = decode(data)
        if got is None:
            out += b'\0'
            lines.append(f'{name:52} {len(data):7} bytes  refused by libwebp')
            if kind != 2:
                sys.exit(f'libwebp refused a good case: {name}')
            continue
        w, h, rgba = got
        out += struct.pack('<BII', 1, w, h)
        if kind in (0, 1):
            out += struct.pack('<I', crc_bgra(rgba))
        lines.append(f'{name:52} {len(data):7} bytes  {w} by {h}')
    with open(os.path.join(OUT, 'cases.bin'), 'wb') as f:
        f.write(out)
    with open(os.path.join(OUT, 'cases.txt'), 'w', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'{len(cases)} cases, {len(out)} bytes')


if __name__ == '__main__':
    main()
