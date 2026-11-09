"""What imagelib's JPEG decoder should make of a file, written plainly in Python.

    from jpeg_reference import decode
    ok, result = decode(data)   # ok: result is (width, height, pixels); otherwise it's why not

pixels is a list of 0xAARRGGBB values (all opaque), a row at a time from the top. This is the rule
book that imagelib's decoder follows, check for check and in the same order, so that the two give
the same reasons. make_jpeg_tests.py checks it against libjpeg-turbo, through ImageMagick: the pixels
must be the same, not merely close, damaged files included, because this does what libjpeg-turbo
does by default, step for step:

  - the integer IDCT (libjpeg's "islow", from Loeffler, Ligtenberg and Moschytz), with its
    13-bit constants, its two passes, and its shortcuts for columns and rows with no AC terms;
  - "fancy" upsampling, the triangle filter, for chroma at half width (h2v1), half height (h1v2) or
    both (h2v2), with the edges repeated; and plain repeating for other ratios, and for components
    of 2 samples across or fewer;
  - YCbCr to RGB by libjpeg's fixed-point tables (16 fraction bits);
  - and what it does with a damaged file, which is to show what it can:
      - entropy-coded data that runs out (at a marker, or the end of the file) reads as zero bits,
        and once a bit that isn't there has been used, the MCUs up to the next restart marker are
        left at zero (they come out gray);
      - a code that isn't in its Huffman table takes 17 bits, and is taken as 0;
      - a run of coefficients past the end of a block puts the coefficient in the last place;
      - restart markers out of order are resynced by libjpeg's rules (jpeg_resync_to_restart);
      - bytes that aren't a marker where a marker should be are skipped, as are restart and TEM
        markers outside a scan, DNL, and APPn or COM segments too short to be one;
      - past the end of the file come EOI markers, again and again, as libjpeg's source
        managers give them, wherever the end comes;
      - with no Huffman table defined, tables 0 and 1 are the standard ones (from the JPEG
        standard's Annex K, which libjpeg uses, as motion-JPEG frames expect);
      - a scan that says it isn't sequential is read as if it were.

Every component's coefficients are kept until the end, as libjpeg keeps them for a file of several
scans: so a component in no scan comes out as zero (gray), and one in two scans has the second's
coefficients written over the first's, where they aren't zero. The IDCT's arithmetic is libjpeg's C
code's (64-bit intermediates, a 32-bit work array, a 16-bit quantization table), and coefficients
are kept in 16 bits, as libjpeg keeps them. (libjpeg-turbo's SIMD gives the same pixels on every
good block, but saturates on the garbage blocks of a damaged file, where its C code wraps.)

A file whose first scan has every component in it is finished when that scan is: libjpeg makes
its pixels as it reads that scan, and what comes after (more scans, a marker it doesn't know, a
second frame header) only matters to it when it's done, too late to change them.

What it reads: baseline and extended sequential JPEG (SOF0, SOF1) with Huffman coding, 8-bit
samples, gray or three components (YCbCr, or RGB when an Adobe marker or the component IDs say so),
any sampling factors that divide evenly, interleaved scans or one component a scan, and restart
markers. The color space is chosen as libjpeg-turbo chooses it. What it refuses is what libjpeg
refuses: headers and tables that are wrong, and no image at all. Not done: progressive (SOF2, which
is next), lossless, hierarchical and arithmetic coding, 12-bit samples, four components (CMYK). EXIF
orientation isn't applied.
"""
import array

from exif import orientation, orient

MAX_PIXELS = 16 * 1024 * 1024          # imagelib's default for Img.max_pixels

ZIGZAG = (0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27,
          20, 13, 6, 7, 14, 21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58,
          59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63)


class Refused(Exception):
    pass


def i32(x):
    return ((x + 0x80000000) & 0xFFFFFFFF) - 0x80000000


def i16(x):
    return ((x + 0x8000) & 0xFFFF) - 0x8000


def decode(data, max_pixels=MAX_PIXELS):
    try:
        return True, read(bytes(data), max_pixels)
    except Refused as e:
        return False, str(e)


# ---------------------------------------------------------------- Huffman tables

class Huff:
    """a table from DHT: its codes, canonical, by length"""

    def __init__(self, counts, values):
        self.counts = counts
        self.values = values

    def build(self, dc):
        """checked, and made ready, when a scan uses it: as libjpeg does, so a table that's
        wrong but never used is no matter"""
        self.maxcode = [-1] * 17         # by length, the largest code of that length; -1: none
        self.valptr = [0] * 17           # by length, where its first value is in values
        self.mincode = [0] * 17
        code = 0
        k = 0
        for length in range(1, 17):
            self.valptr[length] = k
            self.mincode[length] = code
            code += self.counts[length - 1]
            k += self.counts[length - 1]
            if self.counts[length - 1]:
                self.maxcode[length] = code - 1
            # no code may be all ones, as libjpeg has it (jpeg_make_d_derived_tbl)
            if code >= (1 << length):
                raise Refused('a Huffman table with more codes than there\'s room for')
            code <<= 1
        if dc and any(v > 15 for v in self.values):
            raise Refused('a DC Huffman table with a value over 15')


class Bits:
    """the entropy-coded bits of one restart interval, high bit first, its stuffing taken out. Past
    the end it gives zeros, and using one of them sets short, as libjpeg's insufficient_data."""

    def __init__(self, data):
        self.data = data
        self.pos = 0                      # in bits
        self.short = False

    def bit(self):
        if self.pos >= len(self.data) * 8:
            self.short = True
            self.pos += 1
            return 0
        b = (self.data[self.pos >> 3] >> (7 - (self.pos & 7))) & 1
        self.pos += 1
        return b

    def bits(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | self.bit()
        return v

    def decode(self, h):
        """the next value in table h; a code that isn't in it takes 17 bits, and is 0"""
        code = 0
        for length in range(1, 17):
            code = (code << 1) | self.bit()
            if code <= h.maxcode[length]:
                return h.values[h.valptr[length] + code - h.mincode[length]]
        self.bit()
        return 0


def extend(v, s):
    return v - (1 << s) + 1 if v < (1 << (s - 1)) else v


# ---------------------------------------------------------------- the IDCT (libjpeg's islow)

CONST_BITS, PASS1_BITS = 13, 2
F_0_298, F_0_390, F_0_541, F_0_765 = 2446, 3196, 4433, 6270
F_0_899, F_1_175, F_1_501, F_1_847 = 7373, 9633, 12299, 15137
F_1_961, F_2_053, F_2_562, F_3_072 = 16069, 16819, 20995, 25172


def limit(x):
    """libjpeg's range limit after the IDCT: x + 128 clamped, for any x a damaged file can give"""
    v = x & 1023
    if v < 128:
        return v + 128
    if v < 512:
        return 255
    if v < 896:
        return 0
    return v - 896


def idct(coef, q):
    """an 8 by 8 block's samples, from its coefficients (natural order) and quantization table, as
    libjpeg-turbo's C code works them out (jidctint.c): its intermediates are JLONG, 64 bits, so they
    don't overflow, but the work array between the passes is int, so its values are cut to 32 bits;
    and the quantization table is kept in 16 bits, signed (libjpeg's MULTIPLIER, a short)"""
    q = [i16(v) for v in q]
    ws = [0] * 64
    for col in range(8):
        if not any(coef[8 * k + col] for k in range(1, 8)):
            dc = i32((coef[col] * q[col]) << PASS1_BITS)
            for k in range(8):
                ws[8 * k + col] = dc
            continue
        d = [coef[8 * k + col] * q[8 * k + col] for k in range(8)]
        out = butterfly(d, CONST_BITS - PASS1_BITS)
        for k in range(8):
            ws[8 * k + col] = i32(out[k])
    samples = [0] * 64
    for row in range(8):
        w = ws[8 * row:8 * row + 8]
        if not any(w[1:]):
            v = limit((w[0] + (1 << (PASS1_BITS + 2))) >> (PASS1_BITS + 3))
            for k in range(8):
                samples[8 * row + k] = v
            continue
        out = butterfly(w, CONST_BITS + PASS1_BITS + 3)
        for k in range(8):
            samples[8 * row + k] = limit(out[k])
    return samples


def butterfly(d, shift):
    """one 8-point pass of the islow IDCT, descaled by shift, exactly (libjpeg's JLONG)"""
    z2, z3 = d[2], d[6]
    z1 = (z2 + z3) * F_0_541
    tmp2 = z1 - z3 * F_1_847
    tmp3 = z1 + z2 * F_0_765
    tmp0 = (d[0] + d[4]) << CONST_BITS
    tmp1 = (d[0] - d[4]) << CONST_BITS
    tmp10, tmp13 = tmp0 + tmp3, tmp0 - tmp3
    tmp11, tmp12 = tmp1 + tmp2, tmp1 - tmp2
    t0, t1, t2, t3 = d[7], d[5], d[3], d[1]
    z1, z2, z3, z4 = t0 + t3, t1 + t2, t0 + t2, t1 + t3
    z5 = (z3 + z4) * F_1_175
    t0, t1, t2, t3 = t0 * F_0_298, t1 * F_2_053, t2 * F_3_072, t3 * F_1_501
    z1, z2 = -z1 * F_0_899, -z2 * F_2_562
    z3, z4 = z5 - z3 * F_1_961, z5 - z4 * F_0_390
    t0 += z1 + z3
    t1 += z2 + z4
    t2 += z2 + z3
    t3 += z1 + z4
    r = 1 << (shift - 1)
    return [(x + r) >> shift for x in (tmp10 + t3, tmp11 + t2, tmp12 + t1, tmp13 + t0,
                                       tmp13 - t0, tmp12 - t1, tmp11 - t2, tmp10 - t3)]


# ---------------------------------------------------------------- reading the file

class Component:
    def __init__(self, cid, h, v, tq):
        self.id, self.h, self.v, self.tq = cid, h, v, tq


def u16(d, at):
    return d[at] << 8 | d[at + 1]


# libjpeg's standard tables, for a scan that uses table 0 or 1 when no DHT has defined it
STD_DC_COUNTS = ([0, 1, 5, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0], [0, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0])
STD_DC_VALUES = list(range(12))
STD_AC_COUNTS = ([0, 2, 1, 3, 3, 2, 4, 3, 5, 5, 4, 4, 0, 0, 1, 125], [0, 2, 1, 2, 4, 4, 3, 4, 7, 5, 4, 4, 0, 1, 2, 119])
STD_AC_VALUES = (
    [1, 2, 3, 0, 4, 17, 5, 18, 33, 49, 65, 6, 19, 81, 97, 7, 34, 113, 20, 50, 129, 145, 161, 8, 35, 66, 177, 193,
     21, 82, 209, 240, 36, 51, 98, 114, 130, 9, 10, 22, 23, 24, 25, 26, 37, 38, 39, 40, 41, 42, 52, 53, 54, 55, 56,
     57, 58, 67, 68, 69, 70, 71, 72, 73, 74, 83, 84, 85, 86, 87, 88, 89, 90, 99, 100, 101, 102, 103, 104, 105,
     106, 115, 116, 117, 118, 119, 120, 121, 122, 131, 132, 133, 134, 135, 136, 137, 138, 146, 147, 148, 149,
     150, 151, 152, 153, 154, 162, 163, 164, 165, 166, 167, 168, 169, 170, 178, 179, 180, 181, 182, 183, 184,
     185, 186, 194, 195, 196, 197, 198, 199, 200, 201, 202, 210, 211, 212, 213, 214, 215, 216, 217, 218, 225,
     226, 227, 228, 229, 230, 231, 232, 233, 234, 241, 242, 243, 244, 245, 246, 247, 248, 249, 250],
    [0, 1, 2, 3, 17, 4, 5, 33, 49, 6, 18, 65, 81, 7, 97, 113, 19, 34, 50, 129, 8, 20, 66, 145, 161, 177, 193, 9,
     35, 51, 82, 240, 21, 98, 114, 209, 10, 22, 36, 52, 225, 37, 241, 23, 24, 25, 26, 38, 39, 40, 41, 42, 53, 54,
     55, 56, 57, 58, 67, 68, 69, 70, 71, 72, 73, 74, 83, 84, 85, 86, 87, 88, 89, 90, 99, 100, 101, 102, 103, 104,
     105, 106, 115, 116, 117, 118, 119, 120, 121, 122, 130, 131, 132, 133, 134, 135, 136, 137, 138, 146, 147,
     148, 149, 150, 151, 152, 153, 154, 162, 163, 164, 165, 166, 167, 168, 169, 170, 178, 179, 180, 181, 182,
     183, 184, 185, 186, 194, 195, 196, 197, 198, 199, 200, 201, 202, 210, 211, 212, 213, 214, 215, 216, 217,
     218, 226, 227, 228, 229, 230, 231, 232, 233, 234, 242, 243, 244, 245, 246, 247, 248, 249, 250])


def next_marker(d, pos):
    """libjpeg's next_marker: the next marker from pos, skipping anything that isn't one (FF 00
    included), as (its code, where its segment starts); None at the end of the file"""
    n = len(d)
    while True:
        while pos < n and d[pos] != 0xFF:
            pos += 1
        j = pos + 1
        while j < n and d[j] == 0xFF:
            j += 1
        if j >= n:
            return None
        if d[j] == 0:
            pos = j + 1
            continue
        return d[j], j + 1


# what libjpeg's source managers give at the end of the file, again and again: EOI. A segment
# can't be longer than 65,535 bytes, so this many is always enough to reach one.
PAST_THE_END = b'\xff\xd9' * 32769


def read(d, max_pixels):
    if len(d) < 2 or d[0] != 0xFF or d[1] != 0xD8:
        raise Refused('not a JPEG file')
    d += PAST_THE_END
    n = len(d)
    pos = 2
    qt = [None] * 4
    dc_tables = [None] * 4
    ac_tables = [None] * 4
    restart = 0
    frame = None
    jfif = False
    exif = None           # the orientation from the first APP1 with an EXIF header Chrome takes
    adobe = None
    scans = 0
    while True:
        found = next_marker(d, pos)
        if found is None:
            break                              # the end of the file is taken as EOI
        m, pos = found
        if m == 0xD9:
            break
        if m == 0xD8:
            raise Refused('a second start of image')
        if 0xD0 <= m <= 0xD7 or m == 0x01:
            continue                           # RSTn and TEM outside a scan: ignored
        if n - pos < 2:
            break
        length = u16(d, pos)
        skippable = 0xE0 <= m <= 0xEF or m == 0xFE or m == 0xDC
        if length < 2:
            if not skippable:
                raise Refused('a segment of less than 2 bytes')
            pos += 2                           # as libjpeg's skip_variable: nothing to skip
            continue
        if length > n - pos:
            break                              # it runs past the end of the file, which is EOI
        body = d[pos + 2:pos + length]
        pos += length

        if m in (0xC0, 0xC1, 0xC2):
            if frame is not None:
                raise Refused('more than one frame header')
            frame = read_frame(body, max_pixels)
            frame.progressive = m == 0xC2
        elif m == 0xC3:
            raise Refused('lossless JPEG, which isn\'t supported')
        elif m in (0xC5, 0xC6, 0xC7, 0xDE, 0xDF):
            raise Refused('hierarchical JPEG, which isn\'t supported')
        elif m in (0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            raise Refused('arithmetic coding, which isn\'t supported')
        elif m == 0xC4:
            read_dht(body, dc_tables, ac_tables)
        elif m == 0xDB:
            read_dqt(body, qt)
        elif m == 0xDD:
            if length != 4:
                raise Refused('a DRI segment of the wrong length')
            restart = u16(body, 0)
        elif m == 0xDA:
            if frame is None:
                raise Refused('image data before the frame header')
            pos = read_scan(d, pos, body, frame, qt, dc_tables, ac_tables, restart)
            scans += 1
            if scans == 1 and body[0] == len(frame.comps) and not frame.progressive:
                break                          # the image is done, as libjpeg's one pass makes it
        elif m == 0xE1 and scans == 0 and exif is None and body[:6] == b'Exif\x00\x00':
            exif = orientation(body[6:])
        elif m == 0xE0:
            if len(body) >= 14 and body[:5] == b'JFIF\x00':
                jfif = True
        elif m == 0xEE:
            if len(body) >= 12 and body[:5] == b'Adobe':
                adobe = body[11]
        elif m == 0xCC:
            read_dac(body)
        elif skippable:
            pass                               # APPn, COM and DNL: skipped
        else:
            raise Refused('marker FF%02X, which JPEG doesn\'t use here' % m)

    if frame is None or scans == 0:
        raise Refused('no image data')
    rgb = False
    if len(frame.comps) == 3:
        if jfif:
            rgb = False
        elif adobe is not None:
            rgb = adobe == 0
        else:
            ids = [c.id for c in frame.comps]
            rgb = ids == [82, 71, 66]
    global last_smoothed
    last_smoothed = frame.progressive and smoothing_ok(frame)
    for c in frame.comps:
        samples(c)
    return orient(frame.width, frame.height, output(frame, rgb), exif or 1)


def smoothing_ok(frame):
    """libjpeg-turbo's smoothing_ok: whether it would smooth a progressive image's blocks (every
    component has its table and some DC, the table's first 10 values aren't 0, and one of the first 9
    AC coefficients of some component hasn't all come)"""
    useful = False
    for c in frame.comps:
        if c.q is None:
            return False
        if any(c.q[ZIGZAG[k]] == 0 for k in range(10)):
            return False
        if c.coef_bits[0] < 0:
            return False
        if any(c.coef_bits[k] != 0 for k in range(1, 10)):
            useful = True
    return useful


class Frame:
    progressive = False


# Whether libjpeg would smooth the last image decode() made (a progressive one whose low AC
# coefficients haven't all come: see smoothing_ok), which this doesn't do. The tests don't compare
# such an image's pixels with libjpeg's.
last_smoothed = False


def read_frame(body, max_pixels):
    if len(body) < 6:
        raise Refused('a frame header of the wrong length')
    precision = body[0]
    height = u16(body, 1)
    width = u16(body, 3)
    count = body[5]
    if len(body) != 6 + 3 * count:
        raise Refused('a frame header of the wrong length')
    if precision != 8:
        raise Refused('%d-bit samples, which aren\'t supported' % precision)
    if count == 4:
        raise Refused('four components (CMYK), which isn\'t supported')
    if count != 1 and count != 3:
        raise Refused('%d components, which isn\'t supported' % count)
    if height == 0:
        raise Refused('a height of 0, to be set by a DNL marker, which isn\'t supported')
    if width == 0:
        raise Refused('a width of 0')
    f = Frame()
    f.width, f.height = width, height
    f.comps = []
    for k in range(count):
        cid, hv, tq = body[6 + 3 * k], body[7 + 3 * k], body[8 + 3 * k]
        h, v = hv >> 4, hv & 15
        if not (1 <= h <= 4 and 1 <= v <= 4):
            raise Refused('a sampling factor JPEG doesn\'t have')
        if any(c.id == cid for c in f.comps):
            raise Refused('two components with the same ID')
        f.comps.append(Component(cid, h, v, tq))
    f.hmax = max(c.h for c in f.comps)
    f.vmax = max(c.v for c in f.comps)
    for c in f.comps:
        if f.hmax % c.h or f.vmax % c.v:
            raise Refused('sampling factors that don\'t divide evenly')
    if width * height > max_pixels:
        raise Refused('%d by %d is more than the limit of %d pixels' % (width, height, max_pixels))
    f.mcux = (width + 8 * f.hmax - 1) // (8 * f.hmax)
    f.mcuy = (height + 8 * f.vmax - 1) // (8 * f.vmax)
    for c in f.comps:
        c.width = (width * c.h + f.hmax - 1) // f.hmax         # its samples across and down
        c.height = (height * c.v + f.vmax - 1) // f.vmax
        c.stride = f.mcux * c.h * 8                             # its plane's, padded to whole MCUs
        c.rows = f.mcuy * c.v * 8
        if len(f.comps) == 1:
            # one component: libjpeg's MCU is its one block, whatever its sampling factors say
            c.stride = (c.width + 7) // 8 * 8
            c.rows = (c.height + 7) // 8 * 8
        c.coefs = [0] * (c.stride * c.rows)                     # 64 to a block, block by block
        c.q = None                                              # its table, from its first scan
        c.coef_bits = [-1] * 10       # libjpeg's: the Al of the last scan of each of the first 10
    return f


def read_dac(body):
    """DAC, the conditioning of arithmetic coding's tables, which isn't used here but is checked
    as libjpeg checks it (get_dac): pairs of a table's index and its value"""
    if len(body) % 2:
        raise Refused('a DAC segment that\'s wrong')
    for k in range(0, len(body), 2):
        index, value = body[k], body[k + 1]
        if index >= 32 or (index < 16 and (value & 15) > (value >> 4)):
            raise Refused('a DAC segment that\'s wrong')


def read_dqt(body, qt):
    at = 0
    while at < len(body):
        pq, tq = body[at] >> 4, body[at] & 15
        at += 1
        if pq > 1:
            raise Refused('a quantization table of precision %d, which JPEG doesn\'t have' % pq)
        if tq > 3:
            raise Refused('quantization table %d, which JPEG doesn\'t have' % tq)
        size = 128 if pq else 64
        if len(body) - at < size:
            raise Refused('a DQT segment of the wrong length')
        table = [0] * 64
        for k in range(64):
            table[ZIGZAG[k]] = u16(body, at + 2 * k) if pq else body[at + k]
        at += size
        qt[tq] = table


def read_dht(body, dc_tables, ac_tables):
    at = 0
    while at < len(body):
        tc, th = body[at] >> 4, body[at] & 15
        at += 1
        if tc > 1 or th > 3:
            raise Refused('Huffman table %d of class %d, which JPEG doesn\'t have' % (th, tc))
        if len(body) - at < 16:
            raise Refused('a DHT segment of the wrong length')
        counts = list(body[at:at + 16])
        at += 16
        total = sum(counts)
        if total > 256:
            raise Refused('a Huffman table of more than 256 codes')
        if len(body) - at < total:
            raise Refused('a DHT segment of the wrong length')
        values = list(body[at:at + total])
        at += total
        (dc_tables if tc == 0 else ac_tables)[th] = Huff(counts, values)


def read_scan(d, pos, body, frame, qt, dc_tables, ac_tables, restart):
    """the scan's entropy-coded data, from pos, into its components' coefficients; where the scan
    ends (the marker after it)"""
    if len(body) < 1:
        raise Refused('a scan header of the wrong length')
    count = body[0]
    if len(body) != 4 + 2 * count:
        raise Refused('a scan header of the wrong length')
    if count < 1 or count > 4:
        raise Refused('a scan of %d components' % count)
    # in libjpeg's order: the components (get_sos), the MCU's size (per_scan_setup), the
    # quantization tables (latch_quant_tables), and then the Huffman tables (start_pass)
    comps = []
    for k in range(count):
        cid = body[1 + 2 * k]
        c = next((c for c in frame.comps if c.id == cid), None)
        if c is None:
            raise Refused('a scan of a component the frame doesn\'t have')
        if c in comps:
            raise Refused('a component twice in one scan')
        c.td, c.ta = body[2 + 2 * k] >> 4, body[2 + 2 * k] & 15
        comps.append(c)
    if count > 1 and sum(c.h * c.v for c in comps) > 10:
        raise Refused('more than 10 blocks in an MCU')
    for c in comps:
        if c.q is None:
            if c.tq > 3 or qt[c.tq] is None:
                raise Refused('a component whose quantization table isn\'t defined')
            c.q = qt[c.tq]
    ss, se, ah, al = body[1 + 2 * count], body[2 + 2 * count], body[3 + 2 * count] >> 4, body[3 + 2 * count] & 15
    if frame.progressive:
        # libjpeg's start_pass_phuff_decoder: a DC scan is coefficient 0 alone, an AC scan a band of
        # one component, a refinement one bit more, and Al at most 13
        bad = se != 0 if ss == 0 else (ss > se or se > 63 or count != 1)
        if ah and al != ah - 1:
            bad = True
        if al > 13:
            bad = True
        if bad:
            raise Refused('a progressive scan whose band or bits JPEG doesn\'t allow')
        for c in comps:
            for k in range(ss, min(se, 9) + 1):
                c.coef_bits[k] = al
    for c in comps:
        kinds = ((dc_tables, c.td, True), (ac_tables, c.ta, False))
        if frame.progressive:
            # a DC scan needs its DC table (but a refinement none); an AC scan its AC table
            kinds = ((kinds[0],) if ah == 0 else ()) if ss == 0 else (kinds[1],)
        for tables, tid, dc in kinds:
            if tid > 3:
                raise Refused('a scan using a Huffman table that isn\'t defined')
            if tables[tid] is None:
                # the standard tables stand in for 0 and 1, but not in a progressive file: libjpeg's
                # progressive decoder doesn't load them
                if tid > 1 or frame.progressive:
                    raise Refused('a scan using a Huffman table that isn\'t defined')
                tables[tid] = Huff(STD_DC_COUNTS[tid], STD_DC_VALUES) if dc else Huff(STD_AC_COUNTS[tid], STD_AC_VALUES[tid])
            tables[tid].build(dc)
        c.dc = dc_tables[c.td] if c.td <= 3 else None
        c.ac = ac_tables[c.ta] if c.ta <= 3 else None

    if count == 1:
        c = comps[0]
        across = (c.width + 7) // 8
        total = across * ((c.height + 7) // 8)
    else:
        across = frame.mcux
        total = frame.mcux * frame.mcuy

    # libjpeg's entropy decoder, MCU by MCU, with its recovery: data, and the marker after it
    data, marker = segment(d, pos)
    bits = Bits(data)
    held = False                 # whether the marker is being held, after a resync
    short = False                # libjpeg's insufficient_data
    preds = [0] * count
    eobrun = 0                   # a progressive AC scan's blocks left in an end-of-band run
    next_rst = 0
    to_go = restart
    for mcu in range(total):
        if restart and to_go == 0:
            m = marker_code(d, marker)
            if m == 0xD0 + next_rst:
                data, marker = segment(d, marker + 2)
                held = False
            else:
                # jpeg_resync_to_restart
                while True:
                    if m is not None and m < 0xC0:
                        action = 2
                    elif m is None or not 0xD0 <= m <= 0xD7:
                        action = 3
                    elif m in (0xD0 + ((next_rst + 1) & 7), 0xD0 + ((next_rst + 2) & 7)):
                        action = 3
                    elif m in (0xD0 + ((next_rst - 1) & 7), 0xD0 + ((next_rst - 2) & 7)):
                        action = 2
                    else:
                        action = 1
                    if action == 1:
                        data, marker = segment(d, marker + 2)
                        held = False
                        break
                    if action == 2:
                        marker = segment(d, marker + 2)[1]
                        m = marker_code(d, marker)
                        continue
                    data = b''
                    held = True
                    break
            next_rst = (next_rst + 1) & 7
            bits = Bits(data)
            preds = [0] * count
            eobrun = 0
            to_go = restart
            if not held:
                short = False
        # (a DC refinement goes on when the data has run out: zeros change nothing)
        if not short or (frame.progressive and ss == 0 and ah):
            mx, my = mcu % across, mcu // across
            for ci, c in enumerate(comps):
                if count == 1:
                    blocks = [(mx, my)]
                else:
                    blocks = [(mx * c.h + bx, my * c.v + by) for by in range(c.v) for bx in range(c.h)]
                for bx, by in blocks:
                    if not frame.progressive:
                        preds[ci] = block(bits, c, preds[ci], bx, by)
                    elif ss == 0 and ah == 0:
                        preds[ci] = dc_first(bits, c, preds[ci], bx, by, al)
                    elif ss == 0:
                        dc_refine(bits, c, bx, by, al)
                    elif ah == 0:
                        eobrun = ac_first(bits, c, bx, by, ss, se, al, eobrun)
                    else:
                        eobrun = ac_refine(bits, c, bx, by, ss, se, al, eobrun)
            short = bits.short
        if restart:
            to_go -= 1
    return marker


def marker_code(d, at):
    """the code of the marker at at; None at the end of the file (which is EOI)"""
    return d[at + 1] if at + 1 < len(d) else None


def segment(d, pos):
    """the entropy-coded bytes from pos to the next marker, unstuffed, and where that marker is
    (the end of the file, if there's none)"""
    out = bytearray()
    n = len(d)
    while pos < n:
        b = d[pos]
        if b != 0xFF:
            out.append(b)
            pos += 1
            continue
        j = pos + 1
        while j < n and d[j] == 0xFF:
            j += 1
        if j >= n:
            return bytes(out), n
        if d[j] == 0:
            out.append(0xFF)
            pos = j + 1
            continue
        return bytes(out), j - 1
    return bytes(out), n


def block(bits, c, pred, bx, by):
    """one block, decoded into the component's coefficients; the DC prediction after it. As in
    libjpeg's buffered mode, the DC is always written, and the AC coefficients that aren't zero."""
    coefs = c.coefs
    base = (by * (c.stride // 8) + bx) * 64
    s = bits.decode(c.dc)
    diff = extend(bits.bits(s), s) if s else 0
    pred = i32(pred + diff)
    coefs[base] = i16(pred)
    k = 1
    while k < 64:
        rs = bits.decode(c.ac)
        r, s = rs >> 4, rs & 15
        if s == 0:
            if r != 15:
                break
            k += 16
            continue
        k += r
        coefs[base + ZIGZAG[min(k, 63)]] = extend(bits.bits(s), s)
        k += 1
    return pred


# ---------------------------------------------------------------- progressive scans (libjpeg's jdphuff.c)

def dc_first(bits, c, pred, bx, by, al):
    """a DC scan's first pass over a block: the DC difference, its value shifted left by al"""
    s = bits.decode(c.dc)
    diff = extend(bits.bits(s), s) if s else 0
    if not -(1 << 31) <= pred + diff < 1 << 31:
        raise Refused('a DC coefficient too big to hold')
    pred += diff
    c.coefs[(by * (c.stride // 8) + bx) * 64] = i16(i32(pred << al))
    return pred


def dc_refine(bits, c, bx, by, al):
    """one more bit of a block's DC value"""
    if bits.bit():
        at = (by * (c.stride // 8) + bx) * 64
        c.coefs[at] = i16(c.coefs[at] | (1 << al))


def ac_first(bits, c, bx, by, ss, se, al, eobrun):
    """an AC scan's first pass over a block, coefficients ss to se; the end-of-band run after it"""
    if eobrun > 0:
        return eobrun - 1                     # a block of zeros in the band
    base = (by * (c.stride // 8) + bx) * 64
    k = ss
    while k <= se:
        rs = bits.decode(c.ac)
        r, s = rs >> 4, rs & 15
        if s:
            k += r
            c.coefs[base + ZIGZAG[min(k, 63)]] = i16(extend(bits.bits(s), s) << al)
        elif r == 15:
            k += 15
        else:
            run = 1 << r
            if r:
                run += bits.bits(r)
            return run - 1
        k += 1
    return 0


def ac_refine(bits, c, bx, by, ss, se, al, eobrun):
    """an AC scan's refinement of a block: a bit more of each coefficient that's already nonzero,
    and new ones of 1 or -1 (shifted left by al); the end-of-band run after it"""
    p1, m1 = 1 << al, -1 << al
    coefs = c.coefs
    base = (by * (c.stride // 8) + bx) * 64

    def correct(at):
        if bits.bit() and (coefs[at] & p1) == 0:
            coefs[at] = i16(coefs[at] + (p1 if coefs[at] >= 0 else m1))

    k = ss
    if eobrun == 0:
        while k <= se:
            rs = bits.decode(c.ac)
            r, s = rs >> 4, rs & 15
            if s:
                s = p1 if bits.bit() else m1     # (a size other than 1 is wrong: libjpeg only warns)
            elif r != 15:
                eobrun = 1 << r
                if r:
                    eobrun += bits.bits(r)
                break
            # past the coefficients already nonzero, correcting each, and r of those still zero
            while True:
                at = base + ZIGZAG[k]
                if coefs[at] != 0:
                    correct(at)
                else:
                    r -= 1
                    if r < 0:
                        break
                k += 1
                if k > se:
                    break
            if s:
                coefs[base + ZIGZAG[min(k, 63)]] = i16(s)
            k += 1
    if eobrun > 0:
        while k <= se:
            at = base + ZIGZAG[k]
            if coefs[at] != 0:
                correct(at)
            k += 1
        eobrun -= 1
    return eobrun


def samples(c):
    """the component's coefficients made samples, block by block, into its plane"""
    across = c.stride // 8
    c.plane = bytearray(c.stride * c.rows)
    q = c.q or [0] * 64
    for b in range(across * (c.rows // 8)):
        bx, by = b % across, b // across
        out = idct(c.coefs[b * 64:b * 64 + 64], q)
        at = by * 8 * c.stride + bx * 8
        for y in range(8):
            c.plane[at + y * c.stride:at + y * c.stride + 8] = bytes(out[8 * y:8 * y + 8])


# ---------------------------------------------------------------- upsampling and color

def upsample(frame, c):
    """the component at full size, frame.width by frame.height, as rows of samples"""
    w, h = frame.width, frame.height
    hf, vf = frame.hmax // c.h, frame.vmax // c.v
    cw, ch = c.width, c.height
    p, stride = c.plane, c.stride

    def at(x, y):
        return p[min(max(y, 0), ch - 1) * stride + min(max(x, 0), cw - 1)]

    rows = []
    if hf == 1 and vf == 1:
        return [p[y * stride:y * stride + w] for y in range(h)]
    if hf == 2 and vf == 1 and cw > 2:
        for y in range(h):
            row = bytearray(w)
            for x in range(w):
                j = x >> 1
                if x & 1:
                    row[x] = (3 * at(j, y) + at(j + 1, y) + 2) >> 2
                else:
                    row[x] = (3 * at(j, y) + at(j - 1, y) + 1) >> 2
            rows.append(row)
        return rows
    if hf == 1 and vf == 2:
        for y in range(h):
            i = y >> 1
            far, bias = (i + 1, 2) if y & 1 else (i - 1, 1)
            rows.append(bytearray((3 * at(x, i) + at(x, far) + bias) >> 2 for x in range(w)))
        return rows
    if hf == 2 and vf == 2 and cw > 2:
        for y in range(h):
            i = y >> 1
            far = i + 1 if y & 1 else i - 1

            def colsum(j):
                return 3 * at(j, i) + at(j, far)
            row = bytearray(w)
            for x in range(w):
                j = x >> 1
                if x & 1:
                    row[x] = (3 * colsum(j) + colsum(j + 1) + 7) >> 4
                else:
                    row[x] = (3 * colsum(j) + colsum(j - 1) + 8) >> 4
            rows.append(row)
        return rows
    # any other whole ratio, or too narrow for the triangle: each sample repeated
    return [bytearray(p[(y // vf) * stride + x // hf] for x in range(w)) for y in range(h)]


FIX = lambda x: int(x * 65536 + 0.5)  # noqa: E731
CR_R = [(FIX(1.40200) * (i - 128) + 32768) >> 16 for i in range(256)]
CB_B = [(FIX(1.77200) * (i - 128) + 32768) >> 16 for i in range(256)]
CR_G = [-FIX(0.71414) * (i - 128) for i in range(256)]
CB_G = [-FIX(0.34414) * (i - 128) + 32768 for i in range(256)]


def clamp(v):
    return 0 if v < 0 else 255 if v > 255 else v


def output(frame, rgb):
    w, h = frame.width, frame.height
    planes = [upsample(frame, c) for c in frame.comps]
    out = array.array('I', [0]) * (w * h)
    for y in range(h):
        if len(planes) == 1:
            row = planes[0][y]
            for x in range(w):
                g = row[x]
                out[y * w + x] = 0xFF000000 | g << 16 | g << 8 | g
            continue
        r0, r1, r2 = planes[0][y], planes[1][y], planes[2][y]
        for x in range(w):
            if rgb:
                r, g, b = r0[x], r1[x], r2[x]
            else:
                yy, cb, cr = r0[x], r1[x], r2[x]
                r = clamp(yy + CR_R[cr])
                g = clamp(yy + ((CB_G[cb] + CR_G[cr]) >> 16))
                b = clamp(yy + CB_B[cb])
            out[y * w + x] = 0xFF000000 | r << 16 | g << 8 | b
    return out
