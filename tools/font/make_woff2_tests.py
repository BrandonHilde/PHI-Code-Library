#!/usr/bin/env python3
"""Makes the WOFF2 fonts fontlib's WOFF2 reader is tested with, and checks them with macOS's CoreText.

    python3 -I tools/font/make_woff2_tests.py

Writes libs/font/tests/woff2/, each a font from libs/font/tests/fonts packed as WOFF2 here, by the
W3C's WOFF 2.0 (its tables in one Brotli stream, made by the `brotli` command):

    LiberationSans-transformed.woff2   glyf and loca transformed (5.1), and hmtx too (5.4)
    LiberationSans-plain.woff2         nothing transformed (glyf and loca as they are, version 3)
    SourceCodePro.woff2                a CFF font (nothing to transform)

The writer is this script's, so a WOFF2 file it makes is checked by another reader before it's
kept: CoreText (tools/font/coretext_glyphs.swift) must make of each file exactly what it makes of
the font it came from, glyph by glyph (advance, bounding box, and the parts of its outline). That
shows the files are WOFF2 as the format means it; test_woff2 then shows fontlib reads each as the
font it came from. Run on a Mac.
"""
import os
import struct
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONTS = os.path.join(ROOT, 'libs', 'font', 'tests', 'fonts')
OUT = os.path.join(ROOT, 'libs', 'font', 'tests', 'woff2')
KNOWN = ['cmap', 'head', 'hhea', 'hmtx', 'maxp', 'name', 'OS/2', 'post', 'cvt ', 'fpgm', 'glyf', 'loca', 'prep',
         'CFF ', 'VORG', 'EBDT', 'EBLC', 'gasp', 'hdmx', 'kern', 'LTSH', 'PCLT', 'VDMX', 'vhea', 'vmtx', 'BASE', 'GDEF',
         'GPOS', 'GSUB', 'EBSC', 'JSTF', 'MATH', 'CBDT', 'CBLC', 'COLR', 'CPAL', 'SVG ', 'sbix', 'acnt', 'avar', 'bdat',
         'bloc', 'bsln', 'cvar', 'fdsc', 'feat', 'fmtx', 'fvar', 'gvar', 'hsty', 'just', 'lcar', 'mort', 'morx', 'opbd',
         'prop', 'trak', 'Zapf', 'Silf', 'Glat', 'Gloc', 'Feat', 'Sill']


def tables_of(font):
    n = struct.unpack_from('>H', font, 4)[0]
    out = {}
    order = []
    for i in range(n):
        tag, _, off, ln = struct.unpack_from('>4sIII', font, 12 + 16 * i)
        out[tag.decode('latin-1')] = font[off:off + ln]
        order.append(tag.decode('latin-1'))
    return out, order


def base128(v):
    out = [v & 0x7F]
    v >>= 7
    while v:
        out.append(0x80 | (v & 0x7F))
        v >>= 7
    return bytes(reversed(out))


def u255(v):
    if v < 253:
        return bytes([v])
    if v < 506:
        return bytes([255, v - 253])
    if v < 759:
        return bytes([254, v - 506])
    return bytes([253]) + struct.pack('>H', v)


def glyphs_of(t):
    """each glyph's bytes, from glyf by loca"""
    long_loca = struct.unpack_from('>h', t['head'], 50)[0] == 1
    n = struct.unpack_from('>H', t['maxp'], 4)[0]
    loca = t['loca']
    if long_loca:
        offs = struct.unpack_from('>%dI' % (n + 1), loca)
    else:
        offs = [2 * v for v in struct.unpack_from('>%dH' % (n + 1), loca)]
    return [t['glyf'][offs[i]:offs[i + 1]] for i in range(n)], long_loca


def simple_points(g, contours):
    ends = struct.unpack_from('>%dH' % contours, g, 10)
    npts = ends[-1] + 1 if contours else 0
    at = 10 + 2 * contours
    ilen = struct.unpack_from('>H', g, at)[0]
    instr = g[at + 2:at + 2 + ilen]
    at += 2 + ilen
    flags = []
    while len(flags) < npts:
        f = g[at]
        at += 1
        flags.append(f)
        if f & 8:
            r = g[at]
            at += 1
            flags += [f] * r
    xs, ys = [], []
    for coords, short, same in ((xs, 2, 16), (ys, 4, 32)):
        v = 0
        for f in flags:
            if f & short:
                d = g[at]
                at += 1
                v += d if f & same else -d
            elif not f & same:
                v += struct.unpack_from('>h', g, at)[0]
                at += 2
            coords.append(v)
    on = [f & 1 for f in flags]
    overlap = bool(flags and flags[0] & 0x40)
    return ends, instr, on, xs, ys, overlap


def triplet(on, dx, dy, flags, glyph):
    ax, ay = abs(dx), abs(dy)
    on_bit = 0 if on else 128
    xs = 1 if dx >= 0 else 0
    ys = 2 if dy >= 0 else 0
    if dx == 0 and ay < 1280:
        flags.append(on_bit + ((ay & 0xF00) >> 7) + (1 if dy >= 0 else 0))
        glyph.append(ay & 0xFF)
    elif dy == 0 and ax < 1280:
        flags.append(on_bit + 10 + ((ax & 0xF00) >> 7) + xs)
        glyph.append(ax & 0xFF)
    elif ax < 65 and ay < 65:
        flags.append(on_bit + 20 + ((ax - 1) & 0x30) + (((ay - 1) & 0x30) >> 2) + xs + ys)
        glyph.append((((ax - 1) & 0xF) << 4) | ((ay - 1) & 0xF))
    elif ax < 769 and ay < 769:
        flags.append(on_bit + 84 + 12 * (((ax - 1) & 0x300) >> 8) + (((ay - 1) & 0x300) >> 6) + xs + ys)
        glyph.append((ax - 1) & 0xFF)
        glyph.append((ay - 1) & 0xFF)
    elif ax < 4096 and ay < 4096:
        flags.append(on_bit + 120 + xs + ys)
        glyph.extend([ax >> 4, ((ax & 0xF) << 4) | (ay >> 8), ay & 0xFF])
    else:
        flags.append(on_bit + 124 + xs + ys)
        glyph.extend([ax >> 8, ax & 0xFF, ay >> 8, ay & 0xFF])


def transform_glyf(t):
    glyphs, long_loca = glyphs_of(t)
    n = len(glyphs)
    ncont, npts, flags, glyph, comp, instr = bytearray(), bytearray(), bytearray(), bytearray(), bytearray(), bytearray()
    bitmap = bytearray(((n + 31) >> 5) * 4)
    boxes = bytearray()
    overlap = bytearray((n + 7) >> 3)
    any_overlap = False
    xmins = []
    for i, g in enumerate(glyphs):
        if not g:
            ncont += struct.pack('>h', 0)
            xmins.append(0)
            continue
        contours, x0, y0, x1, y1 = struct.unpack_from('>hhhhh', g, 0)
        xmins.append(x0)
        ncont += struct.pack('>h', contours)
        if contours < 0:
            # composite: its components as they are; its box always written
            at = 10
            has_instr = False
            while True:
                f, _ = struct.unpack_from('>HH', g, at)
                size = 4 + (4 if f & 1 else 2) + (2 if f & 8 else 4 if f & 0x40 else 8 if f & 0x80 else 0)
                comp += g[at:at + size]
                at += size
                has_instr = has_instr or bool(f & 0x100)
                if not f & 0x20:
                    break
            if has_instr:
                ilen = struct.unpack_from('>H', g, at)[0]
                glyph += u255(ilen)
                instr += g[at + 2:at + 2 + ilen]
            bitmap[i >> 3] |= 0x80 >> (i & 7)
            boxes += struct.pack('>hhhh', x0, y0, x1, y1)
            continue
        ends, ins, on, xs, ys, ov = simple_points(g, contours)
        prev = -1
        for e in ends:
            npts += u255(e - prev)
            prev = e
        px = py = 0
        for k in range(len(xs)):
            triplet(on[k], xs[k] - px, ys[k] - py, flags, glyph)
            px, py = xs[k], ys[k]
        glyph += u255(len(ins))
        instr += ins
        if ov:
            overlap[i >> 3] |= 0x80 >> (i & 7)
            any_overlap = True
        if xs and (min(xs), min(ys), max(xs), max(ys)) != (x0, y0, x1, y1):
            bitmap[i >> 3] |= 0x80 >> (i & 7)
            boxes += struct.pack('>hhhh', x0, y0, x1, y1)
    bbox = bytes(bitmap) + bytes(boxes)
    streams = [bytes(ncont), bytes(npts), bytes(flags), bytes(glyph), bytes(comp), bbox, bytes(instr)]
    head = struct.pack('>HHHH', 0, 1 if any_overlap else 0, n, 1 if long_loca else 0)
    head += b''.join(struct.pack('>I', len(s)) for s in streams)
    return head + b''.join(streams) + (bytes(overlap) if any_overlap else b''), xmins


def transform_hmtx(t, xmins):
    """the hmtx transform, when the left side bearings it leaves out are the glyphs' xMins; or None"""
    metrics = struct.unpack_from('>H', t['hhea'], 34)[0]
    n = len(xmins)
    hm = t['hmtx']
    adv = [struct.unpack_from('>Hh', hm, 4 * i) for i in range(metrics)]
    rest = [struct.unpack_from('>h', hm, 4 * metrics + 2 * i)[0] for i in range(n - metrics)]
    prop = all(adv[i][1] == xmins[i] for i in range(metrics))
    mono = all(rest[i] == xmins[metrics + i] for i in range(n - metrics))
    if not prop and not mono:
        return None
    out = bytearray([(1 if prop else 0) | (2 if mono else 0)])
    out += b''.join(struct.pack('>H', a) for a, _ in adv)
    if not prop:
        out += b''.join(struct.pack('>h', l) for _, l in adv)
    if not mono:
        out += b''.join(struct.pack('>h', l) for l in rest)
    return bytes(out)


def brotli(data):
    with tempfile.TemporaryDirectory(dir=os.path.expanduser('~')) as d:
        a, b = os.path.join(d, 'in'), os.path.join(d, 'out')
        open(a, 'wb').write(data)
        subprocess.run(['brotli', '-q', '11', '-f', '-o', b, a], check=True)
        return open(b, 'rb').read()


def woff2(font, transform):
    t, order = tables_of(font)
    flavor = struct.unpack_from('>I', font, 0)[0]
    data = {tag: (t[tag], 0, False) for tag in order}
    if transform and 'glyf' in t:
        g, xmins = transform_glyf(t)
        data['glyf'] = (g, 0, True)
        data['loca'] = (b'', 0, True)
        h = transform_hmtx(t, xmins)
        if h is not None:
            data['hmtx'] = (h, 1, True)
    directory = bytearray()
    stream = bytearray()
    for tag in order:
        body, version, transformed = data[tag]
        if tag in ('glyf', 'loca') and not transformed:
            version = 3
        idx = KNOWN.index(tag) if tag in KNOWN else 63
        directory.append(idx | (version << 6))
        if idx == 63:
            directory += tag.encode('latin-1')
        directory += base128(len(t[tag]))
        if transformed:
            directory += base128(len(body))
        stream += body
    packed = brotli(bytes(stream))
    total_sfnt = 12 + 16 * len(order) + sum((len(t[tag]) + 3) & ~3 for tag in order)
    length = 48 + len(directory) + len(packed)
    length4 = (length + 3) & ~3
    header = struct.pack('>4sIIHHIIHHIIIII', b'wOF2', flavor, length4, len(order), 0, total_sfnt, len(packed), 1, 0, 0, 0, 0, 0, 0)
    return header + bytes(directory) + packed + bytes(length4 - length)


def coretext(path, tool):
    r = subprocess.run([tool, path], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit('CoreText could not read ' + path + ': ' + r.stdout + r.stderr)
    return r.stdout


def main():
    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=os.path.expanduser('~')) as d:
        tool = os.path.join(d, 'coretext_glyphs')
        subprocess.run(['swiftc', '-O', os.path.join(ROOT, 'tools', 'font', 'coretext_glyphs.swift'), '-o', tool], check=True)
        made = [('LiberationSans-Regular.ttf', 'LiberationSans-transformed.woff2', True),
                ('LiberationSans-Regular.ttf', 'LiberationSans-plain.woff2', False),
                ('SourceCodePro-Regular.otf', 'SourceCodePro.woff2', True)]
        for source, name, transform in made:
            font = open(os.path.join(FONTS, source), 'rb').read()
            w = woff2(font, transform)
            path = os.path.join(OUT, name)
            open(path, 'wb').write(w)
            a = coretext(os.path.join(FONTS, source), tool)
            b = coretext(path, tool)
            if a != b:
                bad = [(x, y) for x, y in zip(a.split('\n'), b.split('\n')) if x != y][:3]
                os.remove(path)
                sys.exit(f'CoreText reads {name} otherwise than {source}: {bad}')
            print(f'{name}: {len(w)} bytes from {len(font)}; CoreText reads all {a.split()[3]} glyphs as it reads {source}')


if __name__ == '__main__':
    main()
