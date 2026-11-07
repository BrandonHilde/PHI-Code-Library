#!/usr/bin/env python3
"""Makes the reference data corelib's inflate is tested against, with Python's zlib.

    python3 -I tools/core/make_inflate_tests.py

Writes libs/core/tests/inflate/:

    sources.bin    the uncompressed data the good streams were made from
    cases.bin      every case: its stream, and what zlib says it inflates to (or that it's bad)
    cases.txt      the same cases, readable: one a line

Three groups of cases:

    good   every compression level, in each of the three formats, from several kinds of data,
           plus zlib's strategies and window sizes, and gzip headers with every optional field
    bad    streams broken in one particular way each, most of them written bit by bit here
    fuzz   small streams with a few bytes or bits changed, with a fixed seed. Each one's verdict
           is zlib's, so the test checks that corelib agrees with zlib on every one

Every case's expected result comes from zlib itself (zlib.decompressobj), never from this script's
idea of what should happen: the script only checks that zlib's verdict on a hand-made case is the
one the case was made for, so that a case can't quietly test the wrong thing.

The formats of the .bin files (every number little-endian):

    sources.bin:  u32 count, then for each: u8 name length, name, u32 length, bytes
    cases.bin:    u32 count, then for each:
                  u8 group (0 good, 1 bad, 2 fuzz), u8 format (0 raw, 1 zlib, 2 gzip),
                  u8 name length, name, u32 limit (0: the default), u32 length, bytes,
                  u8 ok, u32 output length, u32 output CRC-32, u32 bytes used, i32 source (-1: none)
"""
import gzip
import io
import os
import random
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, '..', '..', 'libs', 'core', 'tests', 'inflate'))

RAW, ZLIB, GZIP = 0, 1, 2
GOOD, BAD, FUZZ = 0, 1, 2
FORMAT_NAMES = ['raw', 'zlib', 'gzip']
GROUP_NAMES = ['good', 'bad', 'fuzz']


# ---------------------------------------------------------------- what zlib says

def zlib_verdict(data, fmt):
    """(ok, output, used) as zlib inflates it: ok only if a whole stream (or, for gzip, every
    member) ended properly. used is how many bytes the stream took."""
    wbits = {RAW: -15, ZLIB: 15, GZIP: 31}[fmt]
    out = b''
    rest = data
    first = True
    while first or (fmt == GZIP and rest[:2] == b'\x1f\x8b'):
        first = False
        d = zlib.decompressobj(wbits)
        try:
            out += d.decompress(rest)
        except zlib.error:
            return False, b'', 0
        if not d.eof:
            return False, b'', 0
        rest = d.unused_data
    return True, out, len(data) - len(rest)


# ---------------------------------------------------------------- the data the streams hold

def make_sources(rng):
    words = []
    for _ in range(400):
        n = rng.choice([1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 7, 8, 9, 11])
        words.append(''.join(rng.choice('etaoinshrdlcumwfgypbvkjxqz'[:rng.choice([8, 14, 26])]) for _ in range(n)))
    text = []
    size = 0
    while size < 24000:
        sentence = ' '.join(rng.choice(words) for _ in range(rng.randint(3, 18)))
        sentence = sentence[0].upper() + sentence[1:] + rng.choice(['. ', '. ', '? ', '! ', '.\n\n'])
        text.append(sentence)
        size += len(sentence)

    runs = bytearray()
    while len(runs) < 20000:
        runs += bytes([rng.randrange(256)]) * rng.choice([1, 2, 3, 5, 40, 257, 258, 259, 300, 1000])

    block = rng.randbytes(3000)
    return {
        'empty': b'',
        'one': b'A',
        'text': ''.join(text).encode('ascii'),
        'random': rng.randbytes(8192),
        'zeros': bytes(70000),
        'runs': bytes(runs),
        'bytes': bytes(range(256)) * 16,
        # a match exactly 32768 bytes back, the farthest DEFLATE reaches
        'far': block + bytes(32768 - len(block)) + block + b'end',
    }


def deflate(data, level=6, fmt=ZLIB, strategy=zlib.Z_DEFAULT_STRATEGY, wbits=15, mem=8):
    w = {RAW: -wbits, ZLIB: wbits, GZIP: 16 + wbits}[fmt]
    c = zlib.compressobj(level, zlib.DEFLATED, w, mem, strategy)
    return c.compress(data) + c.flush()


# ---------------------------------------------------------------- DEFLATE, a bit at a time

class BitWriter:
    def __init__(self):
        self.bits = []

    def put(self, value, n):
        """n bits of value, low bit first (DEFLATE's order for everything but Huffman codes)"""
        for i in range(n):
            self.bits.append((value >> i) & 1)

    def code(self, code, length):
        """a Huffman code: high bit first"""
        for i in range(length - 1, -1, -1):
            self.bits.append((code >> i) & 1)

    def align(self):
        while len(self.bits) % 8:
            self.bits.append(0)

    def raw_bytes(self, data):
        self.align()
        for b in data:
            self.put(b, 8)

    def done(self):
        self.align()
        out = bytearray()
        for i in range(0, len(self.bits), 8):
            byte = 0
            for k in range(8):
                byte |= self.bits[i + k] << k
            out.append(byte)
        return bytes(out)


def canonical(lengths):
    """symbol -> (code, length), from code lengths, as DEFLATE assigns them"""
    codes = {}
    code = 0
    for length in range(1, 16):
        for sym, l in enumerate(lengths):
            if l == length:
                codes[sym] = (code, length)
                code += 1
        code <<= 1
    return codes


FIXED_LIT = [8] * 144 + [9] * 112 + [7] * 24 + [8] * 8
FIXED_DIST = [5] * 32
CODE_ORDER = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15]
# a complete code for the code lengths: 16, 17, 18, 1, 2 and 3 get 5 bits, the rest 4
CL_LENGTHS = [4 if s in (0,) + tuple(range(4, 16)) else 5 for s in range(19)]

LENGTH_BASE = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115, 131,
               163, 195, 227, 258]
LENGTH_EXTRA = [0] * 8 + [1] * 4 + [2] * 4 + [3] * 4 + [4] * 4 + [5] * 4 + [0]
DIST_BASE = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025, 1537, 2049,
             3073, 4097, 6145, 8193, 12289, 16385, 24577]
DIST_EXTRA = [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13]


def block_header(w, final, kind):
    w.put(1 if final else 0, 1)
    w.put(kind, 2)


def dynamic_header(w, lit_lengths, dist_lengths, cl_items=None, cl_lengths=CL_LENGTHS, hlit=None, hdist=None):
    """A dynamic block's header. cl_items, if given, is the list of code-length symbols (with their
    extra bits) to write instead of the plain lengths, for writing broken ones."""
    nlen = len(lit_lengths) if hlit is None else hlit
    ndist = len(dist_lengths) if hdist is None else hdist
    w.put(nlen - 257, 5)
    w.put(ndist - 1, 5)
    w.put(19 - 4, 4)
    for s in CODE_ORDER:
        w.put(cl_lengths[s], 3)
    cl = canonical(cl_lengths)
    if cl_items is None:
        cl_items = [(l, 0, 0) for l in list(lit_lengths) + list(dist_lengths)]
    for sym, extra, nbits in cl_items:
        w.code(*cl[sym])
        w.put(extra, nbits)


def put_match(w, lit, dist, length, distance):
    ls = max(i for i in range(29) if LENGTH_BASE[i] <= length)
    w.code(*lit[257 + ls])
    w.put(length - LENGTH_BASE[ls], LENGTH_EXTRA[ls])
    ds = max(i for i in range(30) if DIST_BASE[i] <= distance)
    w.code(*dist[ds])
    w.put(distance - DIST_BASE[ds], DIST_EXTRA[ds])


def lengths_with(n, items):
    out = [0] * n
    for sym, l in items.items():
        out[sym] = l
    return out


def crafted():
    """(name, format, bytes, should zlib accept it) for streams written here a bit at a time"""
    cases = []
    fl = canonical(FIXED_LIT)
    fd = canonical(FIXED_DIST)

    # ---- good

    # a dynamic block with a single 1-bit distance code: an incomplete code zlib allows
    lit = lengths_with(258, {97: 1, 256: 2, 257: 2})
    dist = [1]
    w = BitWriter()
    block_header(w, True, 2)
    dynamic_header(w, lit, dist)
    lc, dc = canonical(lit), canonical(dist)
    w.code(*lc[97])
    put_match(w, lc, dc, 3, 1)
    w.code(*lc[256])
    cases.append(('dynamic-one-distance-code', RAW, w.done(), True))

    # no distance codes at all, in a block with no matches
    lit = lengths_with(257, {97: 1, 256: 1})
    w = BitWriter()
    block_header(w, True, 2)
    dynamic_header(w, lit, [0])
    lc = canonical(lit)
    w.code(*lc[97])
    w.code(*lc[97])
    w.code(*lc[256])
    cases.append(('dynamic-no-distance-codes', RAW, w.done(), True))

    # only the end-of-block code, of 1 bit: incomplete, and allowed
    lit = lengths_with(257, {256: 1})
    w = BitWriter()
    block_header(w, True, 2)
    dynamic_header(w, lit, [0])
    w.code(*canonical(lit)[256])
    cases.append(('dynamic-lone-end-code', RAW, w.done(), True))

    # codes of every length from 1 to 15, so the long ones take the slow way
    syms = [256] + list(range(65, 80))          # 16 symbols: lengths 1, 2, ..., 14, 15, 15
    items = {s: min(i + 1, 15) for i, s in enumerate(syms)}
    lit = lengths_with(257, items)
    w = BitWriter()
    block_header(w, True, 2)
    dynamic_header(w, lit, [0])
    lc = canonical(lit)
    for s in list(range(79, 64, -1)) * 3:
        w.code(*lc[s])
    w.code(*lc[256])
    cases.append(('dynamic-long-codes', RAW, w.done(), True))

    # a stored block, an empty stored block, a fixed block and a dynamic one, in one stream
    w = BitWriter()
    block_header(w, False, 0)
    w.raw_bytes(struct.pack('<HH', 5, 0xFFFA) + b'hello')
    block_header(w, False, 0)
    w.raw_bytes(struct.pack('<HH', 0, 0xFFFF))
    block_header(w, False, 1)
    for c in b' world':
        w.code(*fl[c])
    put_match(w, fl, fd, 11, 11)
    w.code(*fl[256])
    lit = lengths_with(258, {33: 1, 256: 2, 257: 2})
    block_header(w, True, 2)
    dynamic_header(w, lit, [1])
    w.code(*canonical(lit)[33])
    w.code(*canonical(lit)[256])
    cases.append(('every-block-type', RAW, w.done(), True))

    # a match of 258 (length code 285), and the longest distance code's last value
    w = BitWriter()
    block_header(w, True, 1)
    for i in range(32768):
        w.code(*fl[i % 251])
    put_match(w, fl, fd, 258, 32768)
    w.code(*fl[256])
    cases.append(('fixed-longest-match', RAW, w.done(), True))

    # ---- bad

    def one_block(name, kind, body, ok=False):
        w = BitWriter()
        block_header(w, True, kind)
        body(w)
        cases.append((name, RAW, w.done(), ok))

    one_block('block-type-3', 3, lambda w: w.put(0, 16))
    one_block('stored-bad-check', 0, lambda w: w.raw_bytes(struct.pack('<HH', 5, 0xFFFB) + b'hello'))
    one_block('stored-cut-short', 0, lambda w: w.raw_bytes(struct.pack('<HH', 50, 0xFFCD) + b'hello'))
    one_block('fixed-length-code-286', 1, lambda w: (w.code(*fl[97]), w.code(*fl[286])))
    one_block('fixed-length-code-287', 1, lambda w: (w.code(*fl[97]), w.code(*fl[287])))
    one_block('fixed-distance-code-30', 1, lambda w: (w.code(*fl[97]), w.code(*fl[257]), w.code(*fd[30])))
    one_block('fixed-distance-code-31', 1, lambda w: (w.code(*fl[97]), w.code(*fl[257]), w.code(*fd[31])))
    one_block('distance-before-start', 1, lambda w: (w.code(*fl[97]), put_match(w, fl, fd, 3, 2), w.code(*fl[256])))
    one_block('match-first', 1, lambda w: (put_match(w, fl, fd, 3, 1), w.code(*fl[256])))
    one_block('no-end-of-block', 1, lambda w: [w.code(*fl[97]) for _ in range(3)])

    # no final block: a stored block that isn't the last, then the data ends
    w = BitWriter()
    block_header(w, False, 0)
    w.raw_bytes(struct.pack('<HH', 2, 0xFFFD) + b'hi')
    cases.append(('no-final-block', RAW, w.done(), False))

    cases.append(('empty-input', RAW, b'', False))

    def dyn(name, lit, dist, ok=False, **kw):
        w = BitWriter()
        block_header(w, True, 2)
        dynamic_header(w, lit, dist, **kw)
        lc = canonical(lit) if 'cl_items' not in kw else {}
        if 256 in lc:
            w.code(*lc[256])
        w.put(0, 16)
        cases.append((name, RAW, w.done(), ok))

    dyn('litlen-oversubscribed', lengths_with(257, {97: 1, 98: 1, 256: 1}), [1])
    dyn('litlen-incomplete', lengths_with(257, {97: 2, 256: 2}), [1])
    dyn('distance-oversubscribed', lengths_with(258, {97: 1, 256: 2, 257: 2}), [1, 1, 1])
    dyn('distance-incomplete', lengths_with(258, {97: 1, 256: 2, 257: 2}), [2, 2, 2])
    dyn('missing-end-of-block', lengths_with(257, {97: 1, 98: 1}), [1])
    dyn('code-lengths-incomplete', lengths_with(257, {97: 1, 256: 1}), [1],
        cl_lengths=[2 if s in (0, 1) else 0 for s in range(19)])
    dyn('code-lengths-oversubscribed', lengths_with(257, {97: 1, 256: 1}), [1],
        cl_lengths=[1 if s in (0, 1, 2) else 0 for s in range(19)])
    dyn('repeat-with-nothing-before', [0] * 257, [0], cl_items=[(16, 0, 2)] + [(0, 0, 0)] * 255)
    dyn('repeat-past-the-end', [0] * 257, [0], cl_items=[(18, 127, 7)] * 2 + [(18, 127, 7)])
    dyn('too-many-length-codes', [0] * 257, [0], hlit=287)
    dyn('too-many-distance-codes', [0] * 257, [0], hdist=31)

    return cases


def gzip_member(data, name=None, comment=None, extra=None, header_crc=False, bad_header_crc=False):
    flags = (4 if extra is not None else 0) | (8 if name else 0) | (16 if comment else 0) | (2 if header_crc else 0)
    head = bytearray(b'\x1f\x8b\x08' + bytes([flags]) + struct.pack('<I', 0) + b'\x00\xff')
    if extra is not None:
        head += struct.pack('<H', len(extra)) + extra
    if name:
        head += name + b'\x00'
    if comment:
        head += comment + b'\x00'
    if header_crc:
        crc = zlib.crc32(bytes(head)) & 0xFFFF
        head += struct.pack('<H', crc ^ (1 if bad_header_crc else 0))
    body = deflate(data, 6, RAW)
    return bytes(head) + body + struct.pack('<II', zlib.crc32(data), len(data) & 0xFFFFFFFF)


# ---------------------------------------------------------------- the cases

def main():
    rng = random.Random(20261107)
    sources = make_sources(rng)
    names = list(sources)
    cases = []   # (group, format, name, limit, data, source or None)

    def good(name, fmt, data, source=None, limit=0):
        cases.append((GOOD, fmt, name, limit, data, source))

    for src in names:
        for level in range(10):
            good('%s-zlib-%d' % (src, level), ZLIB, deflate(sources[src], level, ZLIB), src)
        for level in (1, 6, 9):
            good('%s-raw-%d' % (src, level), RAW, deflate(sources[src], level, RAW), src)
        for level in (1, 9):
            good('%s-gzip-%d' % (src, level), GZIP, deflate(sources[src], level, GZIP), src)
    for strategy, sname in ((zlib.Z_FILTERED, 'filtered'), (zlib.Z_HUFFMAN_ONLY, 'huffman'),
                            (zlib.Z_RLE, 'rle'), (zlib.Z_FIXED, 'fixed')):
        for src in ('text', 'runs', 'random', 'far'):
            good('%s-zlib-%s' % (src, sname), ZLIB, deflate(sources[src], 6, ZLIB, strategy), src)
    for wbits in range(9, 16):
        good('text-zlib-window-%d' % wbits, ZLIB, deflate(sources['text'], 6, ZLIB, wbits=wbits), 'text')
    for mem in (1, 9):
        good('text-zlib-memlevel-%d' % mem, ZLIB, deflate(sources['text'], 9, ZLIB, mem=mem), 'text')

    # flushes put empty stored blocks, and blocks that aren't the last, in the middle
    c = zlib.compressobj(6)
    text = sources['text']
    flushed = c.compress(text[:7000]) + c.flush(zlib.Z_SYNC_FLUSH) + c.compress(text[7000:15000]) + \
        c.flush(zlib.Z_FULL_FLUSH) + c.compress(text[15000:]) + c.flush()
    good('text-zlib-flushes', ZLIB, flushed, 'text')

    # gzip headers, with each of the optional fields, and two members
    t = sources['text']
    good('text-gzip-name', GZIP, gzip_member(t, name=b'text.txt'), 'text')
    good('text-gzip-every-field', GZIP, gzip_member(t, name=b'a.txt', comment=b'a comment', extra=b'XY\x02\x00hi',
                                                    header_crc=True), 'text')
    good('text-gzip-empty-extra', GZIP, gzip_member(t, extra=b''), 'text')
    good('text-gzip-two-members', GZIP, gzip_member(t[:10000]) + gzip_member(t[10000:]), 'text')

    # data after the end, which is left alone
    good('text-raw-then-more', RAW, deflate(t, 6, RAW) + b'more data', 'text')
    good('text-zlib-then-more', ZLIB, deflate(t, 6, ZLIB) + b'more data', 'text')
    good('text-gzip-then-zeros', GZIP, deflate(t, 6, GZIP) + bytes(8), 'text')

    # the limit: exactly enough, and one byte short
    zeros = deflate(sources['zeros'], 9, ZLIB)
    good('zeros-limit-exact', ZLIB, zeros, 'zeros', limit=70000)
    cases.append((BAD, ZLIB, 'zeros-limit-one-short', 69999, zeros, None))
    # a bomb: 40 MB of zeros, refused at a limit of 1 MB
    cases.append((BAD, ZLIB, 'bomb-40mb', 1 << 20, deflate(bytes(40 << 20), 9, ZLIB), None))

    for name, fmt, data, ok in crafted():
        cases.append((GOOD if ok else BAD, fmt, name, 0, data, None))

    # broken wrappers
    z = deflate(t[:3000], 6, ZLIB)
    g = deflate(t[:3000], 6, GZIP)

    def fix_check(b):
        cmf = b[0]
        flg = b[1] & 0xE0
        flg += (31 - ((cmf << 8) | flg) % 31) % 31
        return bytes([cmf, flg]) + b[2:]

    for name, fmt, data in [
        ('zlib-bad-header-check', ZLIB, bytes([z[0], z[1] ^ 1]) + z[2:]),
        ('zlib-method-7', ZLIB, fix_check(bytes([(z[0] & 0xF0) | 7]) + z[1:])),
        ('zlib-window-too-big', ZLIB, fix_check(bytes([0x88]) + z[1:])),
        ('zlib-preset-dictionary', ZLIB, fix_check(bytes([z[0], z[1] | 0x20]) + struct.pack('>I', 1) + z[2:])),
        ('zlib-bad-adler', ZLIB, z[:-1] + bytes([z[-1] ^ 1])),
        ('zlib-no-adler', ZLIB, z[:-4]),
        ('zlib-one-byte', ZLIB, z[:1]),
        ('gzip-bad-magic', GZIP, b'\x1f\x8c' + g[2:]),
        ('gzip-method-7', GZIP, g[:2] + b'\x07' + g[3:]),
        ('gzip-reserved-flag', GZIP, g[:3] + b'\x20' + g[4:]),
        ('gzip-bad-crc', GZIP, g[:-8] + bytes([g[-8] ^ 1]) + g[-7:]),
        ('gzip-bad-size', GZIP, g[:-4] + bytes([g[-4] ^ 1]) + g[-3:]),
        ('gzip-no-trailer', GZIP, g[:-8]),
        ('gzip-name-unended', GZIP, g[:3] + b'\x08' + g[4:10] + b'abc'),
        ('gzip-extra-too-long', GZIP, g[:3] + b'\x04' + g[4:10] + b'\xff\x00abc'),
        ('gzip-bad-header-crc', GZIP, gzip_member(t[:3000], header_crc=True, bad_header_crc=True)),
        ('gzip-header-only', GZIP, g[:10]),
        ('gzip-second-member-broken', GZIP, g + g[:-1]),
    ]:
        cases.append((BAD, fmt, name, 0, data, None))

    # fuzz: small raw streams, changed a little
    bases = []
    for level in (1, 6, 9):
        for start, size in ((0, 300), (1000, 1200), (5000, 2500)):
            bases.append(deflate(t[start:start + size], level, RAW))
    bases.append(deflate(sources['runs'][:2000], 9, RAW))
    bases.append(deflate(t[:800], 6, RAW, zlib.Z_FIXED))
    bases.append(deflate(t[:800], 6, RAW, zlib.Z_HUFFMAN_ONLY))
    bases += [data for name, fmt, data, ok in crafted() if ok and len(data) < 2000]
    for i in range(600):
        b = bytearray(rng.choice(bases))
        how = rng.randrange(6)
        if how == 0:
            for _ in range(rng.randint(1, 3)):
                b[rng.randrange(len(b))] ^= 1 << rng.randrange(8)
        elif how == 1:
            b[rng.randrange(len(b))] = rng.randrange(256)
        elif how == 2:
            # the headers are where most of the checks are
            b[rng.randrange(min(len(b), 40))] ^= 1 << rng.randrange(8)
        elif how == 3:
            del b[rng.randrange(len(b)):]
        elif how == 4:
            b.insert(rng.randrange(len(b)), rng.randrange(256))
        else:
            at = rng.randrange(len(b))
            del b[at:at + rng.randint(1, 8)]
        cases.append((FUZZ, RAW, 'fuzz-%03d' % i, 0, bytes(b), None))

    # ---- what zlib says of each, and the files

    with open(os.path.join(OUT, 'sources.bin'), 'wb') as f:
        f.write(struct.pack('<I', len(names)))
        for n in names:
            f.write(bytes([len(n)]) + n.encode() + struct.pack('<I', len(sources[n])) + sources[n])

    lines = []
    with open(os.path.join(OUT, 'cases.bin'), 'wb') as f:
        f.write(struct.pack('<I', len(cases)))
        for group, fmt, name, limit, data, source in cases:
            ok, out, used = zlib_verdict(data, fmt)
            if ok and limit and len(out) > limit:
                ok, out, used = False, b'', 0
            if group == GOOD:
                assert ok, name + ': zlib refuses it'
                if source is not None:
                    assert out == sources[source], name + ": zlib doesn't give its source back"
            if group == BAD:
                assert not ok, name + ': zlib accepts it'
            f.write(bytes([group, fmt, len(name)]) + name.encode())
            f.write(struct.pack('<II', limit, len(data)) + data)
            f.write(struct.pack('<BIIIi', 1 if ok else 0, len(out), zlib.crc32(out), used,
                                names.index(source) if source is not None else -1))
            lines.append('%-5s %-4s %-32s %7d bytes  %s' % (
                GROUP_NAMES[group], FORMAT_NAMES[fmt], name, len(data),
                ('ok, %d bytes' % len(out)) if ok else 'bad'))

    with open(os.path.join(OUT, 'cases.txt'), 'w', newline='\n') as f:
        f.write('# made by tools/core/make_inflate_tests.py: what zlib says of each case in cases.bin\n')
        f.write('\n'.join(lines) + '\n')

    fuzz_ok = sum(1 for c in cases if c[0] == FUZZ and zlib_verdict(c[4], c[1])[0])
    print('%d sources, %d cases (%d good, %d bad, %d fuzz, of which zlib accepts %d), in %s' % (
        len(names), len(cases), sum(1 for c in cases if c[0] == GOOD), sum(1 for c in cases if c[0] == BAD),
        sum(1 for c in cases if c[0] == FUZZ), fuzz_ok, OUT))


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    main()
