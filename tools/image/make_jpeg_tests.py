#!/usr/bin/env python3
"""Makes the cases imagelib's JPEG decoder is tested on, and checks what they expect against
outside evidence.

    python3 -P tools/image/make_jpeg_tests.py

(-P rather than -I, since Pillow and numpy are usually in the user's site-packages. ImageMagick's
`magick` must be on the path.)

Writes libs/image/tests/jpeg/:

    cases.bin      every case: its bytes, and what imagelib must make of it (the format is in cases.py)
    cases.txt      the same, readable: one a line

What each case expects comes from jpeg_reference.py, the rules written plainly in Python. Before
writing anything, this checks those rules against libjpeg-turbo, which both of the outside decoders
use (Pillow its own copy, ImageMagick the system's): every file the rules read must give the same
pixels as libjpeg-turbo's C code (through ImageMagick, with JSIMD_FORCENONE), damaged files
included, and every file the rules refuse libjpeg must refuse too, unless it's a kind of JPEG that
imagelib doesn't read yet. The cut and fuzz cases are checked this way as well. There's no free JPEG test suite to take, so the files are made here:

    libjpeg   files written by libjpeg-turbo itself, through Pillow and ImageMagick: many sizes,
              qualities and subsamplings, optimized tables, restart markers, RGB, and kinds that
              aren't read yet (progressive, CMYK)
    made      files written here, by a small baseline encoder, for what those don't cover: every
              sampling layout that divides evenly, one component a scan, scans of two, restart
              intervals of every length, 16-bit and redefined tables, each way of naming the
              color space, every marker in every wrong place, and entropy-coded data that's
              damaged or ends early
    cut       good files cut short at many lengths
    fuzz      small files with a few bytes changed, with a fixed seed
"""
import io
import os
import random
import struct
import subprocess
import sys

# libjpeg-turbo's C code, in Pillow too (it reads this when it starts): see magick()
os.environ['JSIMD_FORCENONE'] = '1'

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jpeg_reference  # noqa: E402
from jpeg_reference import decode, MAX_PIXELS, ZIGZAG  # noqa: E402
from cases import Cases as CaseFile, as_rgba, run_magick  # noqa: E402

LIB = os.path.normpath(os.path.join(HERE, '..', '..', 'libs', 'image'))
OUT = os.path.join(LIB, 'tests', 'jpeg')

LIBJPEG, MADE, CUT, FUZZ = 0, 1, 2, 3

# The everyday cases prove each feature, and are what build.ps1 -Test runs. With --release, this
# also makes the release cases (release.bin): every size, and files cut short at many lengths and
# fuzzed, all checked against the outside evidence; those are for when the library is near release.
RELEASE = False

GROUP_NAMES = ['libjpeg', 'made', 'cut', 'fuzz']


# ---------------------------------------------------------------- the outside decoders

def difference(a, b):
    import numpy as np
    if a is None or b is None or a.shape != b.shape:
        return None
    return int(np.abs(a.astype(np.int16) - b.astype(np.int16)).max())


def magick(data):
    """ImageMagick's pixels, as RGBA, or None if libjpeg gives up; and whether libjpeg warned, or
    'gave up' when ImageMagick did, not libjpeg (after a thousand warnings, "insufficient image
    data": as when a segment runs past the end of the file, and its source manager gives an EOI,
    and a warning, for every 2 bytes skipped)"""
    import numpy as np
    # libjpeg-turbo's C code, not its SIMD: the two give the same pixels for every block of a good
    # file, but the SIMD IDCT saturates where the C one wraps, so they differ on the garbage
    # blocks of a damaged one, and the C code is the reference the SIMD is tested against
    r = run_magick(['jpg:-', '-depth', '8', '-format', '%w %h\n', '-write', 'info:-', 'rgb:-'], data,
                   env=dict(os.environ, JSIMD_FORCENONE='1'))
    if r is None:
        return None, 'gave up'
    warned = b'warning/' in r.stderr or b'error/' in r.stderr
    if r.returncode != 0:
        return None, 'gave up' if b'insufficient image data' in r.stderr else warned
    head, _, body = r.stdout.partition(b'\n')
    try:
        w, h = map(int, head.split())
    except ValueError:
        return None, warned
    if len(body) != w * h * 3:
        return None, warned
    a = np.frombuffer(body, dtype=np.uint8).reshape(h, w, 3)
    return np.concatenate([a, np.full((h, w, 1), 255, np.uint8)], axis=2), warned


def pillow(data, truncated=False):
    import numpy as np
    from PIL import Image, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = truncated
    try:
        im = Image.open(io.BytesIO(data))
        if im.format != 'JPEG':
            return None
        im.load()
        return np.asarray(im.convert('RGBA'), dtype=np.uint8)
    except Exception:
        return None


# ---------------------------------------------------------------- writing JPEG files

# the example tables in the JPEG standard's Annex K, row by row
LUMINANCE = (16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56,
             14, 17, 22, 29, 51, 87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113,
             92, 49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99)
CHROMINANCE = (17, 18, 24, 47, 99, 99, 99, 99, 18, 21, 26, 66, 99, 99, 99, 99, 24, 26, 56, 99, 99, 99, 99, 99,
               47, 66, 99, 99, 99, 99, 99, 99) + (99,) * 32


def qtable(base, quality, most=255):
    scale = 5000 // quality if quality < 50 else 200 - 2 * quality
    return [min(max((b * scale + 50) // 100, 1), most) for b in base]


def segment(marker, body):
    return bytes([0xFF, marker]) + struct.pack('>H', len(body) + 2) + body


JFIF = segment(0xE0, b'JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00')


def adobe(transform):
    return segment(0xEE, b'Adobe\x00\x64\x00\x00\x00\x00' + bytes([transform]))


def dqt(tables):
    """tables: (id, values in natural order, 16-bit)"""
    body = b''
    for tid, values, wide in tables:
        body += bytes([(1 if wide else 0) << 4 | tid])
        for k in range(64):
            v = values[ZIGZAG[k]]
            body += struct.pack('>H', v) if wide else bytes([v])
    return segment(0xDB, body)


def dht(tables):
    """tables: (class, id, counts, values)"""
    body = b''
    for tc, th, counts, values in tables:
        body += bytes([tc << 4 | th]) + bytes(counts) + bytes(values)
    return segment(0xC4, body)


def optimal_table(freq):
    """counts and values for a Huffman table, from symbol frequencies, as libjpeg makes them: code
    lengths of at most 16, and no code of all ones"""
    freq = list(freq) + [1]
    size = [0] * 257
    others = [-1] * 257
    while True:
        c1 = -1
        v = 1 << 60
        for i in range(257):
            if freq[i] and freq[i] <= v:
                v, c1 = freq[i], i
        c2 = -1
        v = 1 << 60
        for i in range(257):
            if freq[i] and freq[i] <= v and i != c1:
                v, c2 = freq[i], i
        if c2 < 0:
            break
        freq[c1] += freq[c2]
        freq[c2] = 0
        size[c1] += 1
        while others[c1] >= 0:
            c1 = others[c1]
            size[c1] += 1
        others[c1] = c2
        size[c2] += 1
        while others[c2] >= 0:
            c2 = others[c2]
            size[c2] += 1
    bits = [0] * 33
    for i in range(257):
        if size[i]:
            bits[size[i]] += 1
    for i in range(32, 16, -1):
        while bits[i] > 0:
            j = i - 2
            while bits[j] == 0:
                j -= 1
            bits[i] -= 2
            bits[i - 1] += 1
            bits[j + 1] += 2
            bits[j] -= 1
    i = 16
    while bits[i] == 0:
        i -= 1
    bits[i] -= 1
    values = [s for length in range(1, 33) for s in range(256) if size[s] == length]
    return bits[1:17], values[:sum(bits[1:17])]


def canonical(counts, values):
    codes = {}
    code = 0
    k = 0
    for length in range(1, 17):
        for _ in range(counts[length - 1]):
            codes[values[k]] = (code, length)
            code += 1
            k += 1
        code <<= 1
    return codes


class BitWriter:
    def __init__(self):
        self.out = bytearray()
        self.acc = 0
        self.n = 0

    def put(self, v, n):
        for i in range(n - 1, -1, -1):
            self.acc = (self.acc << 1) | ((v >> i) & 1)
            self.n += 1
            if self.n == 8:
                self.out.append(self.acc)
                if self.acc == 0xFF:
                    self.out.append(0)
                self.acc = self.n = 0

    def flush(self):
        while self.n:
            self.put(1, 1)


def dct_matrix():
    import numpy as np
    t = np.zeros((8, 8))
    for u in range(8):
        for x in range(8):
            t[u, x] = (np.sqrt(1 / 8) if u == 0 else np.sqrt(2 / 8)) * np.cos((2 * x + 1) * u * np.pi / 16)
    return t


T = None


def coefficients(block, q):
    """an 8 by 8 block's quantized coefficients, in natural order"""
    import numpy as np
    global T
    if T is None:
        T = dct_matrix()
    f = T @ (np.array(block, dtype=float).reshape(8, 8) - 128) @ T.T
    out = []
    for k in range(64):
        v = int(round(f.flat[k] / q[k]))
        out.append(max(-2047, min(2047, v)) if k == 0 else max(-1023, min(1023, v)))
    return out


def category(v):
    a = abs(v)
    s = 0
    while a:
        s += 1
        a >>= 1
    return s


def jpeg(w, h, comps=((1, 1, 1), (2, 1, 1), (3, 1, 1)), seed=0, quality=75, scans=None, restart=0,
         sample=None, wide=False, most=255, app=JFIF, sof=0xC0, shared=False, table_ids=None,
         between=None, after=b'', end=b'\xff\xd9', parts=False, tq=None):
    """A baseline JPEG. comps are (id, h, v). Samples are smooth with noise (with the seed) unless
    sample(component, x, y) is given, at each component's own size. scans are lists of component
    indexes (default: all in one). between[i] goes before scan i's SOS. With parts, the pieces
    come back as a dict, to be put together wrong."""
    r = random.Random(seed)
    nc = len(comps)
    hmax = max(c[1] for c in comps)
    vmax = max(c[2] for c in comps)
    mcux = (w + 8 * hmax - 1) // (8 * hmax)
    mcuy = (h + 8 * vmax - 1) // (8 * vmax)
    if sample is None:
        noise = {}

        def sample(ci, x, y):
            key = (ci, x, y)
            if key not in noise:
                base = (x * 9 + y * 5 + ci * 70) % 256 if ci else (x * 4 + y * 6) % 256
                noise[key] = max(0, min(255, base + r.randint(-40, 40)))
            return noise[key]
    if tq is None:
        tq = [0] + [1] * (nc - 1)
    tables = {0: qtable(LUMINANCE, quality, most), 1: qtable(CHROMINANCE, quality, most)}
    for t in set(tq):
        tables.setdefault(t, qtable(LUMINANCE, max(1, quality // 2), most))
    if table_ids is None:
        table_ids = [0] * nc if shared or nc == 1 else [0] + [1] * (nc - 1)

    # each component's blocks, quantized
    blocks = []
    for ci, (cid, ch, cv) in enumerate(comps):
        cw = (w * ch + hmax - 1) // hmax
        chh = (h * cv + vmax - 1) // vmax
        gw = mcux * ch if nc > 1 else (cw + 7) // 8
        gh = mcuy * cv if nc > 1 else (chh + 7) // 8
        grid = {}
        for by in range(gh):
            for bx in range(gw):
                px = [sample(ci, min(bx * 8 + x, cw - 1), min(by * 8 + y, chh - 1)) for y in range(8) for x in range(8)]
                grid[(bx, by)] = coefficients(px, tables[tq[ci]])
        blocks.append((grid, cw, chh))

    if scans is None:
        scans = [list(range(nc))]
    # the tokens of each scan, to count for the tables and then write
    scan_tokens = []
    for scan in scans:
        if len(scan) == 1:
            grid, cw, chh = blocks[scan[0]]
            across = (cw + 7) // 8
            total = across * ((chh + 7) // 8)
        else:
            across = mcux
            total = mcux * mcuy
        tokens = []
        preds = [0] * len(scan)
        for mcu in range(total):
            if restart and mcu and mcu % restart == 0:
                tokens.append(('rst',))
                preds = [0] * len(scan)
            mx, my = mcu % across, mcu // across
            for si, ci in enumerate(scan):
                cid, ch, cv = comps[ci]
                where = [(mx, my)] if len(scan) == 1 else [(mx * ch + bx, my * cv + by) for by in range(cv) for bx in range(ch)]
                for key in where:
                    coef = blocks[ci][0][key]
                    diff = coef[0] - preds[si]
                    preds[si] = coef[0]
                    s = category(diff)
                    tokens.append(('dc', table_ids[ci], s, diff))
                    run = 0
                    for k in range(1, 64):
                        v = coef[ZIGZAG[k]]
                        if v == 0:
                            run += 1
                            continue
                        while run > 15:
                            tokens.append(('ac', table_ids[ci], 0xF0, 0))
                            run -= 16
                        s = category(v)
                        tokens.append(('ac', table_ids[ci], run << 4 | s, v))
                        run = 0
                    if run:
                        tokens.append(('ac', table_ids[ci], 0x00, 0))
        scan_tokens.append(tokens)

    freqs = {}
    for tokens in scan_tokens:
        for t in tokens:
            if t[0] != 'rst':
                f = freqs.setdefault((t[0], t[1]), [0] * 256)
                f[t[2]] += 1
    huff = {}
    for (kind, tid), f in sorted(freqs.items()):
        counts, values = optimal_table(f)
        huff[(kind, tid)] = (counts, values, canonical(counts, values))

    datas = []
    for tokens in scan_tokens:
        bw = BitWriter()
        interval = 0
        for t in tokens:
            if t[0] == 'rst':
                bw.flush()
                bw.out += bytes([0xFF, 0xD0 + (interval & 7)])
                interval += 1
                continue
            code, length = huff[(t[0], t[1])][2][t[2]]
            bw.put(code, length)
            s = t[2] & 15 if t[0] == 'ac' else t[2]
            if s:
                v = t[3]
                bw.put(v if v > 0 else v + (1 << s) - 1, s)
        bw.flush()
        datas.append(bytes(bw.out))

    p = {}
    p['soi'] = b'\xff\xd8'
    p['app'] = app
    p['dqt'] = dqt([(t, tables[t], wide or max(tables[t]) > 255) for t in sorted(set(tq))])
    body = struct.pack('>BHHB', 8, h, w, nc)
    for ci, (cid, ch, cv) in enumerate(comps):
        body += bytes([cid, ch << 4 | cv, tq[ci]])
    p['sof'] = segment(sof, body)
    p['dht'] = dht([(0 if kind == 'dc' else 1, tid, counts, values)
                    for (kind, tid), (counts, values, _) in sorted(huff.items())])
    p['dri'] = segment(0xDD, struct.pack('>H', restart)) if restart else b''
    p['scans'] = []
    for i, scan in enumerate(scans):
        body = bytes([len(scan)])
        for ci in scan:
            body += bytes([comps[ci][0], table_ids[ci] << 4 | table_ids[ci]])
        body += bytes([0, 63, 0])
        p['scans'].append([between[i] if between else b'', segment(0xDA, body), datas[i]])
    p['after'] = after
    p['eoi'] = end
    return p if parts else join(p)


def join(p):
    out = p['soi'] + p['app'] + p['dqt'] + p['sof'] + p['dht'] + p['dri']
    for before, sos, data in p['scans']:
        out += before + sos + data
    return out + p['after'] + p['eoi']


# ---------------------------------------------------------------- the cases

# a case's rule, for the outside check:
#   auto          libjpeg must do what the rules do: give the same pixels when they read it (with a
#                 warning or not), and give up when they refuse it
#   unsupported   a kind of JPEG imagelib doesn't read (yet), which libjpeg reads
#   limit         refused for imagelib's pixel limit, which libjpeg doesn't have

SAMPLINGS = {
    '444': ((1, 1), (1, 1), (1, 1)),
    '422': ((2, 1), (1, 1), (1, 1)),
    '440': ((1, 2), (1, 1), (1, 1)),
    '420': ((2, 2), (1, 1), (1, 1)),
    '411': ((4, 1), (1, 1), (1, 1)),
    '410': ((4, 2), (1, 1), (1, 1)),
    '311': ((3, 1), (1, 1), (1, 1)),
    '321': ((3, 2), (1, 1), (1, 1)),
    '14': ((1, 4), (1, 1), (1, 1)),
    'mixed': ((2, 2), (2, 1), (1, 1)),
    'crossed': ((2, 1), (1, 2), (1, 1)),
    'low-luma': ((1, 1), (2, 2), (2, 2)),
    'all-21': ((2, 1), (2, 1), (2, 1)),
}


def comps_of(name):
    return tuple((k + 1, h, v) for k, (h, v) in enumerate(SAMPLINGS[name]))


def libjpeg_cases():
    """files written by libjpeg-turbo, through Pillow and ImageMagick"""
    import numpy as np
    from PIL import Image
    r = np.random.default_rng(3)
    cases = []

    def picture(w, h):
        y, x = np.mgrid[0:h, 0:w]
        a = np.stack([(x * 255 // max(w - 1, 1)), (y * 255 // max(h - 1, 1)), ((x * 7 + y * 3) % 256)], axis=2)
        return np.clip(a + r.integers(-30, 31, size=a.shape), 0, 255).astype(np.uint8)

    def pil(name, a, rule='auto', **kw):
        b = io.BytesIO()
        im = Image.fromarray(a)
        if kw.pop('cmyk', False):
            im = im.convert('CMYK')
        im.save(b, 'JPEG', **kw)
        cases.append((name, b.getvalue(), 0, rule))

    def im(name, a, *args):
        b = io.BytesIO()
        Image.fromarray(a).save(b, 'PNG')
        out = subprocess.run(['magick', 'png:-'] + list(args) + ['jpg:-'], input=b.getvalue(), capture_output=True,
                             check=True).stdout
        cases.append((name, out, 0, 'auto'))

    for w, h in (((1, 1), (2, 2), (3, 5), (8, 8), (17, 9), (33, 31), (64, 48)) if RELEASE else ((1, 1), (17, 9), (33, 31))):
        a = picture(w, h)
        for sub, sname in ((0, '444'), (1, '422'), (2, '420')):
            for q in (10, 75, 95):
                pil('pil-%dx%d-%s-q%d' % (w, h, sname, q), a, quality=q, subsampling=sub)
        pil('pil-%dx%d-gray' % (w, h), a[:, :, 0], quality=80)
        pil('pil-%dx%d-optimized' % (w, h), a, quality=80, optimize=True, subsampling=2)
        for sf in ('1x2', '4x1', '4x2', '2x1,1x2,1x1', '1x1,2x2,2x2'):
            im('im-%dx%d-%s' % (w, h, sf.replace(',', '-')), a, '-sampling-factor', sf, '-quality', '85')
    a = picture(37, 53)
    pil('pil-restart-every-3-blocks', a, restart_marker_blocks=3)
    pil('pil-restart-every-row-420', a, restart_marker_rows=1, subsampling=2)
    pil('pil-restart-every-block-gray', a[:, :, 0], restart_marker_blocks=1)
    pil('pil-rgb', a, keep_rgb=True, quality=90)
    pil('pil-q100-444', a, quality=100, subsampling=0)
    pil('pil-q1-420', a, quality=1, subsampling=2)
    pil('pil-exif-and-comment', a, exif=b'Exif\x00\x00MM\x00\x2a\x00\x00\x00\x08\x00\x00', comment=b'hello')
    # progressive: libjpeg's own progression (DC first and refined, AC bands first and refined)
    pil('pil-progressive', a, progressive=True)
    for w, h in ((1, 1), (17, 9), (64, 48)):
        for sub, sname in ((0, '444'), (2, '420')):
            pil('pil-progressive-%dx%d-%s' % (w, h, sname), picture(w, h), progressive=True, subsampling=sub)
    pil('pil-progressive-gray', a[:, :, 0], progressive=True)
    pil('pil-progressive-restart', a, progressive=True, restart_marker_blocks=2)
    pil('pil-progressive-q100', a, progressive=True, quality=100, subsampling=0)
    im('im-progressive-411', picture(33, 31), '-interlace', 'JPEG', '-sampling-factor', '4x1')
    pil('pil-cmyk', a, 'unsupported', cmyk=True)
    im('im-arithmetic', picture(16, 16), '-define', 'jpeg:arithmetic-coding=true')
    cases[-1] = cases[-1][:3] + ('unsupported',)
    pic = picture(100, 75)
    pil('pil-100x75-q90', pic, quality=90)
    im('im-100x75-q60-420', pic, '-quality', '60', '-sampling-factor', '2x2,1x1,1x1')
    return cases


def made_cases():
    cases = []

    def add(name, data, rule='auto', max_pixels=0):
        cases.append((name, data, max_pixels, rule))

    # every sampling layout, at sizes that are and aren't whole MCUs
    seed = 1
    for sname in SAMPLINGS:
        for w, h in (((1, 1), (2, 3), (3, 3), (5, 7), (8, 8), (16, 16), (17, 13), (33, 31), (47, 9)) if RELEASE
                     else ((1, 1), (17, 13), (33, 31))):
            add('%s-%dx%d' % (sname, w, h), jpeg(w, h, comps_of(sname), seed))
            seed += 1
    # gray, with sampling factors that don't matter for one component
    for w, h in ((1, 1), (7, 9), (16, 8), (41, 23)):
        for hv in ((1, 1), (2, 2), (4, 1)):
            add('gray-%dx%d-%dx%d' % (w, h, hv[0], hv[1]), jpeg(w, h, ((1,) + hv,), seed))
            seed += 1
    # one component a scan, and scans of two
    for sname in ('444', '420', '411', 'mixed', 'low-luma'):
        add('scans-each-%s' % sname, jpeg(29, 19, comps_of(sname), seed, scans=[[0], [1], [2]]))
        add('scans-1-2-%s' % sname, jpeg(29, 19, comps_of(sname), seed + 1, scans=[[0], [1, 2]]))
        add('scans-backwards-%s' % sname, jpeg(29, 19, comps_of(sname), seed + 2, scans=[[2], [1], [0]]))
        seed += 3
    # restart intervals, interleaved and not, and more than eight of them (the markers wrap)
    for every in (1, 2, 3, 7, 50):
        add('restart-%d-420' % every, jpeg(45, 37, comps_of('420'), seed, restart=every))
        add('restart-%d-scans' % every, jpeg(45, 37, comps_of('420'), seed + 1, restart=every, scans=[[0], [1], [2]]))
        seed += 2
    add('restart-gray-every-block', jpeg(70, 9, ((1, 1, 1),), seed, restart=1))
    # qualities, and tables
    for q in (1, 5, 50, 90, 100):
        add('quality-%d' % q, jpeg(23, 17, comps_of('420'), seed, quality=q))
        seed += 1
    add('dqt-16-bit', jpeg(23, 17, comps_of('420'), seed, quality=1, most=32767))
    add('dqt-16-bit-small-values', jpeg(23, 17, comps_of('420'), seed, wide=True))
    add('tables-shared', jpeg(23, 17, comps_of('422'), seed, shared=True))
    add('tables-2-and-3', jpeg(23, 17, comps_of('422'), seed, table_ids=[2, 3, 3], sof=0xC1))
    add('quant-tables-each', jpeg(23, 17, comps_of('444'), seed, tq=[0, 1, 2]))
    add('sof1', jpeg(23, 17, comps_of('420'), seed, sof=0xC1))
    p = jpeg(23, 17, comps_of('420'), seed, scans=[[0], [1], [2]], parts=True)
    other = jpeg(23, 17, comps_of('420'), seed + 7, scans=[[0], [1], [2]], quality=30, parts=True)
    # the tables for the later scans defined again, between scans, as other's
    p['scans'][1][0] = other['dht']
    p['scans'][2][0] = other['dqt']
    p['scans'][1][2] = other['scans'][1][2]
    p['scans'][2][2] = other['scans'][2][2]
    add('tables-redefined-between-scans', join(p))
    seed += 1

    # how the color space is named
    rgbish = lambda ci, x, y: (x * 20 + ci * 90) % 256  # noqa: E731
    add('jfif', jpeg(9, 9, comps_of('444'), sample=rgbish))
    add('no-markers-ids-123', jpeg(9, 9, comps_of('444'), sample=rgbish, app=b''))
    add('no-markers-ids-rgb', jpeg(9, 9, ((82, 1, 1), (71, 1, 1), (66, 1, 1)), sample=rgbish, app=b''))
    add('no-markers-ids-012', jpeg(9, 9, ((0, 1, 1), (1, 1, 1), (2, 1, 1)), sample=rgbish, app=b''))
    for t in (0, 1, 2):
        add('adobe-%d' % t, jpeg(9, 9, comps_of('444'), sample=rgbish, app=adobe(t)))
    add('jfif-and-adobe-0', jpeg(9, 9, comps_of('444'), sample=rgbish, app=JFIF + adobe(0)))
    add('adobe-short', jpeg(9, 9, ((82, 1, 1), (71, 1, 1), (66, 1, 1)), sample=rgbish, app=segment(0xEE, b'Adobe\x00')))
    add('jfif-short-ids-rgb', jpeg(9, 9, ((82, 1, 1), (71, 1, 1), (66, 1, 1)), sample=rgbish, app=segment(0xE0, b'JFIF\x00')))

    # markers that are skipped, and fill bytes
    base = jpeg(13, 11, comps_of('420'), 300, parts=True)
    for name, extra in (('com', segment(0xFE, b'a comment')), ('app1', segment(0xE1, b'Exif\x00\x00' + bytes(20))),
                        ('app15', segment(0xEF, b'x' * 300)),
                        ('dac', segment(0xCC, b'\x00\x11')), ('dri-0', segment(0xDD, b'\x00\x00')),
                        ('fill-bytes', b'\xff\xff\xff'), ('empty-app', segment(0xE5, b''))):
        p = dict(base)
        p['dht'] = extra + base['dht']
        add('marker-' + name, join(p))
    p = dict(base)
    p['eoi'] = b'\xff\xff\xd9'
    add('fill-before-eoi', join(p))
    p = dict(base)
    p['after'] = b''
    p['eoi'] = b'\xff\xd9' + b'junk after the end' + b'\xff\xd9'
    add('after-eoi', join(p))
    p = dict(base, scans=[list(s) for s in base['scans']])
    data = p['scans'][0][2]
    at = data.find(b'\xff\x00')
    if at >= 0:
        p['scans'][0][2] = data[:at] + b'\xff' + data[at:]
        add('fill-before-stuffed-ff', join(p))

    # wrong: the file's structure
    good = jpeg(13, 11, comps_of('420'), 301)
    add('bad-empty', b'')
    add('bad-not-jpeg', b'\x89PNG' + good[4:])
    add('bad-soi-only', b'\xff\xd8')
    add('bad-no-eoi', good[:-2])
    add('bad-second-soi', good[:2] + b'\xff\xd8' + good[2:])
    add('bad-garbage-between', good[:2] + b'\x00\x00' + good[2:])
    add('bad-rst-outside', good[:2] + b'\xff\xd0' + good[2:])
    add('bad-tem', good[:2] + b'\xff\x01' + good[2:])
    add('bad-unknown-marker', good[:2] + segment(0x02, b'') + good[2:])
    add('bad-segment-length-0', good[:2] + b'\xff\xfe\x00\x00' + good[2:])
    add('bad-segment-past-end', good[:2] + b'\xff\xfe\xff\xf0abc')
    add('bad-dnl', good[:-2] + segment(0xDC, b'\x00\x0b') + b'\xff\xd9')
    add('bad-jpg-marker', good[:2] + segment(0xC8, b'') + good[2:])
    add('bad-jpgn-marker', good[:2] + segment(0xF0, b'abc') + good[2:])
    for marker, name in ((0xC2, 'progressive'), (0xC3, 'lossless'), (0xC5, 'hierarchical'),
                         (0xC9, 'arithmetic'), (0xDE, 'dhp')):
        p = dict(base)
        p['sof'] = bytes([0xFF, marker]) + base['sof'][2:]
        if marker == 0xDE:
            p['sof'] = segment(0xDE, base['sof'][4:]) + base['sof']
        add('bad-%s' % name, join(p), 'unsupported' if marker == 0xC9 else 'auto')

    # wrong: the frame header
    def frame(body):
        p = dict(base)
        p['sof'] = segment(0xC0, body)
        return join(p)
    sof = base['sof'][4:]
    add('bad-sof-12-bit', frame(b'\x0c' + sof[1:]), 'unsupported')
    add('bad-sof-short', frame(sof[:-1]))
    add('bad-sof-long', frame(sof + b'\x00'))
    add('bad-sof-tiny', frame(sof[:4]))
    add('bad-two-frames', join(dict(base, dht=base['sof'] + base['dht'])))
    add('bad-width-0', frame(sof[:3] + b'\x00\x00' + sof[5:]))
    add('bad-height-0', frame(sof[:1] + b'\x00\x00' + sof[3:]))
    add('bad-2-components', frame(sof[:5] + b'\x02' + sof[6:12]))
    add('bad-4-components', jpeg(9, 9, ((1, 1, 1), (2, 1, 1), (3, 1, 1), (4, 1, 1)), 302, app=b''), 'unsupported')
    add('bad-sampling-0', frame(sof[:7] + b'\x01' + sof[8:]))
    add('bad-sampling-5', frame(sof[:7] + b'\x51' + sof[8:]))
    add('bad-quant-table-4', frame(sof[:8] + b'\x04' + sof[9:]))
    add('bad-same-ids', frame(sof[:9] + b'\x01' + sof[10:]))
    add('bad-uneven-sampling', jpeg(9, 9, ((1, 3, 1), (2, 2, 1), (3, 1, 1)), 303))
    add('bad-mcu-11-blocks', jpeg(9, 9, ((1, 3, 3), (2, 1, 1), (3, 1, 1)), 304))
    add('bad-mcu-12-blocks', jpeg(9, 9, ((1, 2, 2), (2, 2, 2), (3, 2, 2)), 305))

    # wrong: the tables
    def tables(dqt_seg=None, dht_seg=None):
        p = dict(base)
        if dqt_seg is not None:
            p['dqt'] = dqt_seg
        if dht_seg is not None:
            p['dht'] = dht_seg
        return join(p)
    q = base['dqt'][4:]
    add('bad-dqt-precision-2', tables(segment(0xDB, b'\x20' + q[1:])))
    add('bad-dqt-table-4', tables(segment(0xDB, b'\x04' + q[1:])))
    add('bad-dqt-short', tables(segment(0xDB, q[:-1])))
    add('bad-no-dqt', tables(b''))
    h = base['dht'][4:]
    add('bad-dht-class-2', tables(dht_seg=segment(0xC4, b'\x20' + h[1:])))
    add('bad-dht-table-4', tables(dht_seg=segment(0xC4, b'\x04' + h[1:])))
    add('bad-dht-short', tables(dht_seg=segment(0xC4, h[:-1])))
    add('bad-dht-counts-only', tables(dht_seg=segment(0xC4, h[:10])))
    add('bad-no-dht', tables(dht_seg=b''))
    add('dht-overfull-unused', tables(dht_seg=dht([(0, 0, [3] + [0] * 15, [0, 1, 2])]) + base['dht']))
    add('bad-dht-overfull', tables(dht_seg=base['dht'] + dht([(0, 0, [3] + [0] * 15, [0, 1, 2])])))
    add('bad-dht-257', tables(dht_seg=segment(0xC4, b'\x10' + bytes([0] * 8 + [255, 2] + [0] * 6) + bytes(257))))
    add('bad-dc-value-16', tables(dht_seg=base['dht'] + dht([(0, 0, [0, 1] + [0] * 14, [16])])))

    # wrong: the scan headers
    def scan(body, k=0, b=None):
        p = dict(b or base, scans=[list(s) for s in (b or base)['scans']])
        p['scans'][k][1] = segment(0xDA, body)
        return join(p)
    sos = base['scans'][0][1][4:]
    add('bad-sos-short', scan(sos[:-1]))
    add('bad-sos-0-components', scan(b'\x00\x00\x3f\x00'))
    add('bad-sos-unknown-component', scan(sos[:1] + b'\x09' + sos[2:]))
    add('bad-sos-component-twice', scan(sos[:3] + b'\x01' + sos[4:]))
    add('bad-sos-table-undefined', scan(sos[:2] + b'\x22' + sos[3:]))
    add('bad-sos-ss', scan(sos[:-3] + b'\x01\x3f\x00'))
    add('bad-sos-se', scan(sos[:-3] + b'\x00\x05\x00'))
    add('bad-sos-approximation', scan(sos[:-3] + b'\x00\x3f\x01'))
    add('bad-sos-before-sof', b'\xff\xd8' + base['scans'][0][1] + base['sof'] + good[2:])
    # wrong: a progressive scan's band or bits, each scan header of libjpeg's own progression
    # changed one way
    import numpy as np
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(np.full((16, 16, 3), 100, np.uint8)).save(b, 'JPEG', progressive=True)
    prog = b.getvalue()
    soses = [i for i in range(len(prog) - 1) if prog[i] == 0xFF and prog[i + 1] == 0xDA]

    def progression(k, ss=None, se=None, a=None):
        at = soses[k]
        n = prog[at + 4]
        tail = at + 5 + 2 * n
        out = bytearray(prog)
        for i, v in ((tail, ss), (tail + 1, se), (tail + 2, a)):
            if v is not None:
                out[i] = v
        return bytes(out)
    first_ac = next(k for k in range(len(soses)) if prog[soses[k] + 5 + 2 * prog[soses[k] + 4]] > 0)
    add('bad-progressive-dc-band', progression(0, se=5))
    add('bad-progressive-ss-past-se', progression(first_ac, ss=10, se=5))
    add('bad-progressive-se-past-63', progression(first_ac, se=64))
    add('bad-progressive-refine-not-one-bit', progression(first_ac, a=0x20))
    add('bad-progressive-al-14', progression(0, a=0x0E))
    add('bad-progressive-ac-of-three', progression(0, ss=1, se=5))
    add('progressive-scans-left-out', prog[:soses[2]] + b'\xff\xd9')

    sep = jpeg(13, 11, comps_of('420'), 306, scans=[[0], [1], [2]], parts=True)
    add('bad-component-left-out', join(dict(sep, scans=sep['scans'][:2])))
    add('bad-component-in-two-scans', join(dict(sep, scans=sep['scans'] + [sep['scans'][0]])))
    p = jpeg(13, 11, comps_of('420'), 307, tq=[0, 1, 2], parts=True)
    p['dqt'] = dqt([(0, qtable(LUMINANCE, 75), False), (1, qtable(CHROMINANCE, 75), False)])
    add('bad-quant-table-undefined', join(p))

    # wrong: the entropy-coded data
    def entropy(change, b=None, k=0):
        p = dict(b or base, scans=[list(s) for s in (b or base)['scans']])
        p['scans'][k][2] = change(p['scans'][k][2])
        return join(p)
    add('bad-data-cut', entropy(lambda d: d[:len(d) // 2]))
    add('bad-data-empty', entropy(lambda d: b''))
    add('bad-data-all-ones', entropy(lambda d: b'\xff\x00' * (len(d) // 2)))
    add('bad-data-zeros', entropy(lambda d: bytes(len(d))))
    rst = jpeg(45, 37, comps_of('420'), 308, restart=2, parts=True)
    add('bad-restart-missing', entropy(lambda d: d.replace(b'\xff\xd1', b'', 1), rst))
    add('bad-restart-out-of-order', entropy(lambda d: d.replace(b'\xff\xd1', b'\xff\xd2', 1), rst))
    add('bad-restart-extra', entropy(lambda d: d + b'\xff\xd0', jpeg(45, 37, comps_of('420'), 309, restart=200, parts=True)))
    # a run of zeros that goes past the end of a block: a ZRL and then a coefficient at 64
    run = jpeg(8, 8, ((1, 1, 1),), 310, sample=lambda ci, x, y: 128, parts=True)
    zrl = dht([(0, 0, [1] + [0] * 15, [0]), (1, 0, [0, 3] + [0] * 14, [0x00, 0xF0, 0xF1])])
    run['dht'] = zrl
    # DC: code 0 (0 bits). AC codes: 00 EOB, 01 ZRL, 10 F1. Then ZRL x3 (48), F1 (k 64): past the end
    # (bits: DC 0; ZRL 01 01 01; F1 10 and its bit 1; then 1s to the byte)
    run['scans'][0][2] = bytes([0b00101011, 0b01111111])
    add('bad-run-past-end', join(run))
    run['scans'][0][2] = bytes([0b00101010, 0b01111111])     # ZRL x3 and EOB: fine
    add('zrl-then-eob', join(run))
    run['scans'][0][2] = bytes([0b00101010, 0xFF, 0x00])     # ZRL x4: k reaches 64, the block's end
    add('zrl-to-the-end', join(run))
    run['scans'][0][2] = bytes([0b11111111, 0x00, 0xFF, 0x00])     # a code not in the table
    add('bad-huffman-code', join(run))

    # the limit, and a file that says it's big
    add('limit-at', jpeg(10, 10, comps_of('420'), 320), 'same', 100)
    add('limit-over', jpeg(10, 10, comps_of('420'), 321), 'limit', 99)
    big = dict(base)
    big['sof'] = segment(0xC0, struct.pack('>BHHB', 8, 65535, 65535, 1) + b'\x01\x11\x00')
    add('limit-default-over', join(big), 'limit')
    big['sof'] = segment(0xC0, struct.pack('>BHHB', 8, 4096, 4096, 1) + b'\x01\x11\x00')
    big['scans'] = [[b'', segment(0xDA, b'\x01\x01\x00\x00\x3f\x00'), b'\x00' * 100]]
    add('bomb-claims-big', join(big))
    return cases


# ---------------------------------------------------------------- checking

# the reasons the rules give for kinds of JPEG imagelib doesn't read yet, and libjpeg does
NOT_YET = ('progressive JPEG, which isn\'t supported yet', 'arithmetic coding, which isn\'t supported',
           '12-bit samples, which aren\'t supported', 'four components (CMYK), which isn\'t supported',
           'lossless JPEG, which isn\'t supported')


# Images bigger than this aren't compared with libjpeg: fuzzed headers claim up to the pixel limit,
# and each such image would be held several times over. They're still checked, against the rules, by
# imagelib's own tests.
BIGGEST_CHECKED = 1 << 20


def check(cases):
    """the rules against libjpeg (through ImageMagick), and Pillow counted; cases are
    (name, data, max_pixels, rule)"""
    problems = []
    counts = {'same': 0, 'same, though libjpeg warns': 0, 'refused by both': 0, 'unsupported': 0, 'limit': 0,
              'ImageMagick gives up, and Pillow\'s libjpeg agrees': 0, 'ImageMagick gives up, and Pillow stops short': []}
    pil = {'same': 0, 'differs': [], 'refuses too': 0, 'reads where the rules refuse': [],
           'refuses where the rules read': []}
    for name, data, max_pixels, rule in cases:
        ok, result = decode(data, max_pixels or MAX_PIXELS)
        if ok and jpeg_reference.last_smoothed:
            counts['libjpeg smooths it, which isn\'t done, so not compared'] = \
                counts.get('libjpeg smooths it, which isn\'t done, so not compared', 0) + 1
            continue
        if ok and result[0] * result[1] > BIGGEST_CHECKED and rule == 'auto':
            counts['more than a million pixels, so not compared'] = counts.get('more than a million pixels, so not compared', 0) + 1
            continue
        m, warned = magick(data)
        why = None
        if rule == 'unsupported':
            if ok:
                why = 'the rules read it'
            elif m is None:
                why = 'libjpeg doesn\'t read it either (the rules: %s)' % result
            else:
                counts['unsupported'] += 1
        elif rule == 'limit':
            if ok or 'limit' not in result:
                why = 'should be refused for the limit'
            else:
                counts['limit'] += 1
        elif ok and m is None and warned == 'gave up':
            if difference(as_rgba(*result), pillow(data, truncated=True)) == 0:
                counts['ImageMagick gives up, and Pillow\'s libjpeg agrees'] += 1
            else:
                counts['ImageMagick gives up, and Pillow stops short'].append(name)
        elif ok:
            d = difference(as_rgba(*result), m)
            if m is None:
                why = 'libjpeg refuses it, where the rules read it'
            elif d != 0:
                why = 'differs from libjpeg by %s' % d
            else:
                counts['same, though libjpeg warns' if warned else 'same'] += 1
        elif m is not None and result in NOT_YET:
            counts['not read yet, as libjpeg does'] = counts.get('not read yet, as libjpeg does', 0) + 1
        elif m is not None:
            why = 'libjpeg reads it, where the rules refuse it: %s' % result
        else:
            counts['refused by both'] += 1
        if why:
            problems.append('%s: %s' % (name, why))
        p = pillow(data)
        if ok and p is not None:
            if difference(as_rgba(*result), p) == 0:
                pil['same'] += 1
            else:
                pil['differs'].append(name)
        elif ok:
            pil['refuses where the rules read'].append(name)
        elif p is not None and rule != 'limit':
            pil['reads where the rules refuse'].append(name)
        else:
            pil['refuses too'] += 1
    return counts, pil, problems


def report(label, cases, problems, show_pillow=True):
    counts, pil, more = check(cases)
    print('%s: %d cases, against libjpeg: %s' % (label, len(cases), counts))
    if show_pillow:
        print('  Pillow (its own copy of libjpeg-turbo, and its own reading of the markers): %d the same, '
              '%d refused by both' % (pil['same'], pil['refuses too']))
        for k in ('differs', 'reads where the rules refuse', 'refuses where the rules read'):
            if pil[k]:
                print('  Pillow %s: %d: %s' % (k, len(pil[k]), ' '.join(pil[k][:40])))
    problems += more


def small_image(data):
    """whether the rules read data as an image of at most 256 by 256 pixels: fuzz cases start only
    from those, as a small file can claim a big image, and every changed copy of it would be one"""
    ok, result = decode(data)
    return ok and result[0] * result[1] <= 65536


def cut_lengths(size, step):
    """the lengths a good file of size bytes is cut at: in the release cases, every one near its start
    and its end and every few between (step says how far to the next); in the everyday ones, a few,
    from inside the first header to just before the end"""
    if RELEASE:
        out = []
        at = 0
        while at < size:
            out.append(at)
            at += step(at)
        return out
    return sorted(set(at for at in (8, 20, 40, size // 4, size // 2, size * 3 // 4, size - 1) if 0 < at < size))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--release', action='store_true', help='make the release cases too')
    args = ap.parse_args()
    global RELEASE
    RELEASE = args.release
    os.makedirs(OUT, exist_ok=True)
    groups = (('libjpeg', libjpeg_cases()), ('made', made_cases()))
    problems = []
    for label, cases in groups:
        report(label, cases, problems)

    cases = CaseFile(decode, MAX_PIXELS, OUT, 'make_jpeg_tests.py', GROUP_NAMES)
    index = {}
    for group, (label, made) in zip((LIBJPEG, MADE), groups):
        for name, data, max_pixels, _ in made:
            index[name] = cases.add(group, 1, name, data, max_pixels)
    # cut short: every length near the start, and then every 7th, and near the end
    for name in (('pil-17x9-420-q75', 'pil-33x31-444-q95', 'pil-restart-every-3-blocks', 'pil-8x8-gray',
                 '420-17x13', 'scans-each-420', 'restart-3-scans', 'dqt-16-bit', 'tables-redefined-between-scans', 'pil-progressive') if RELEASE else ('pil-17x9-420-q75', 'scans-each-420', 'pil-progressive')):
        source = index[name]
        data = cases.list[source][5]
        for at in cut_lengths(len(data), lambda at: 1 if at < 200 or len(data) - at <= 40 else 7):
            cases.add(CUT, 2, '%s-to-%d' % (name, at), data[:at], 0, (source, at))

    # fuzz: a few bytes changed, in the headers more often than not
    r = random.Random(20261108)
    small = [name for label, made in groups for name, data, _, rule in made
             if len(data) < 1500 and rule == 'auto' and small_image(data)]
    for k in range(4000 if RELEASE else 40):
        name = r.choice(small)
        source = index[name]
        data = bytearray(cases.list[source][5])
        changes = {}
        for _ in range(r.choice((1, 1, 2, 3, 5))):
            at = r.randrange(min(len(data), 400)) if r.random() < 0.6 else r.randrange(len(data))
            v = r.choice((0, 1, 255, 0x7F, 0x80, r.randrange(256), data[at] ^ (1 << r.randrange(8))))
            data[at] = v
            changes[at] = v
        cases.add(FUZZ, 3, 'fuzz-%d-%s' % (k, name), bytes(data), 0, (source, sorted(changes.items())))

    # the cut and fuzz cases against libjpeg too, as they're damaged files of every kind
    for group, label in ((CUT, 'cut'), (FUZZ, 'fuzz')):
        report(label, [(c[2], c[5], 0, 'auto') for c in cases.list if c[0] == group], problems, False)
    if problems:
        print('\n'.join(problems[:200]))
        sys.exit('the rules and libjpeg disagree, %d times' % len(problems))

    size = cases.write('release' if RELEASE else 'cases')
    print('%s.bin: %d cases, %d bytes:' % ('release' if RELEASE else 'cases', len(cases.list), size), cases.summary())


if __name__ == '__main__':
    main()
