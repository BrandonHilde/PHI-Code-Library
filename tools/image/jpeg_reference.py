"""What imagelib's JPEG decoder should make of a file, written plainly in Python.

    from jpeg_reference import decode
    ok, result = decode(data)   # ok: result is (width, height, pixels); otherwise it's why not

pixels is a list of 0xAARRGGBB values (all opaque), a row at a time from the top. This is the rule
book that imagelib's decoder follows, check for check and in the same order, so that the two give
the same reasons. make_jpeg_tests.py checks it against libjpeg-turbo, through Pillow and through
ImageMagick: the pixels must be the same, not merely close, because this does what libjpeg-turbo
does by default, step for step:

  - the integer IDCT (libjpeg's "islow", from Loeffler, Ligtenberg and Moschytz), with its
    13-bit constants, its two passes, and its shortcuts for columns and rows with no AC terms;
  - "fancy" upsampling, the triangle filter, for chroma at half width (h2v1), half height (h1v2) or
    both (h2v2), with the edges repeated; and plain repeating for other ratios, and for components
    of 2 samples across or fewer;
  - YCbCr to RGB by libjpeg's fixed-point tables (16 fraction bits).

The arithmetic is 32-bit, wrapping, as imagelib's is, and coefficients are kept in 16 bits, as
libjpeg keeps them: that only matters for damaged files, whose results this and imagelib must still
agree on.

What it reads: baseline and extended sequential JPEG (SOF0, SOF1) with Huffman coding, 8-bit
samples, gray or three components (YCbCr, or RGB when an Adobe marker or the component IDs say so),
any sampling factors that divide evenly, interleaved scans or one component a scan, and restart
markers. The color space is chosen as libjpeg-turbo chooses it.

What it refuses, where libjpeg would warn and go on: entropy-coded data that's damaged or ends
early, restart markers missing or out of order, a run of coefficients past the end of a block, a
scan that isn't sequential, a component left out of every scan or in two, and a file that doesn't
end with EOI. Not done: progressive (SOF2, which is next), lossless, hierarchical and arithmetic
coding, 12-bit samples, four components (CMYK), and DNL. EXIF orientation isn't applied.
"""

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
            if code > (1 << length):
                raise Refused('a Huffman table with more codes than there\'s room for')
            code <<= 1
        if dc and any(v > 15 for v in self.values):
            raise Refused('a DC Huffman table with a value over 15')


class Bits:
    """the entropy-coded bits of one restart interval, high bit first, its stuffing taken out. Past
    the end it gives zeros, and using one of them is a failure."""

    def __init__(self, data):
        self.data = data
        self.pos = 0                      # in bits

    def bit(self):
        if self.pos >= len(self.data) * 8:
            raise Refused('the image data ends before the image does')
        b = (self.data[self.pos >> 3] >> (7 - (self.pos & 7))) & 1
        self.pos += 1
        return b

    def bits(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | self.bit()
        return v

    def decode(self, h):
        code = 0
        for length in range(1, 17):
            code = (code << 1) | self.bit()
            if code <= h.maxcode[length]:
                return h.values[h.valptr[length] + code - h.mincode[length]]
        raise Refused('a code that isn\'t in its Huffman table')


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
    """an 8 by 8 block's samples, from its coefficients (natural order) and quantization table"""
    ws = [0] * 64
    for col in range(8):
        if not any(coef[8 * k + col] for k in range(1, 8)):
            dc = i32(i32(coef[col] * q[col]) << PASS1_BITS)
            for k in range(8):
                ws[8 * k + col] = dc
            continue
        d = [i32(coef[8 * k + col] * q[8 * k + col]) for k in range(8)]
        out = butterfly(d, CONST_BITS - PASS1_BITS)
        for k in range(8):
            ws[8 * k + col] = out[k]
    samples = [0] * 64
    for row in range(8):
        w = ws[8 * row:8 * row + 8]
        if not any(w[1:]):
            v = limit(i32(w[0] + (1 << (PASS1_BITS + 2))) >> (PASS1_BITS + 3))
            for k in range(8):
                samples[8 * row + k] = v
            continue
        out = butterfly(w, CONST_BITS + PASS1_BITS + 3)
        for k in range(8):
            samples[8 * row + k] = limit(out[k])
    return samples


def butterfly(d, shift):
    """one 8-point pass of the islow IDCT, descaled by shift"""
    m = lambda a, b: i32(a * b)  # noqa: E731
    z2, z3 = d[2], d[6]
    z1 = m(i32(z2 + z3), F_0_541)
    tmp2 = i32(z1 + m(z3, -F_1_847))
    tmp3 = i32(z1 + m(z2, F_0_765))
    tmp0 = i32(i32(d[0] + d[4]) << CONST_BITS)
    tmp1 = i32(i32(d[0] - d[4]) << CONST_BITS)
    tmp10, tmp13 = i32(tmp0 + tmp3), i32(tmp0 - tmp3)
    tmp11, tmp12 = i32(tmp1 + tmp2), i32(tmp1 - tmp2)
    t0, t1, t2, t3 = d[7], d[5], d[3], d[1]
    z1, z2, z3, z4 = i32(t0 + t3), i32(t1 + t2), i32(t0 + t2), i32(t1 + t3)
    z5 = m(i32(z3 + z4), F_1_175)
    t0, t1, t2, t3 = m(t0, F_0_298), m(t1, F_2_053), m(t2, F_3_072), m(t3, F_1_501)
    z1, z2 = m(z1, -F_0_899), m(z2, -F_2_562)
    z3, z4 = i32(m(z3, -F_1_961) + z5), i32(m(z4, -F_0_390) + z5)
    t0 = i32(t0 + i32(z1 + z3))
    t1 = i32(t1 + i32(z2 + z4))
    t2 = i32(t2 + i32(z2 + z3))
    t3 = i32(t3 + i32(z1 + z4))
    r = 1 << (shift - 1)
    ds = lambda x: i32(x + r) >> shift  # noqa: E731
    return [ds(tmp10 + t3), ds(tmp11 + t2), ds(tmp12 + t1), ds(tmp13 + t0),
            ds(tmp13 - t0), ds(tmp12 - t1), ds(tmp11 - t2), ds(tmp10 - t3)]


# ---------------------------------------------------------------- reading the file

class Component:
    def __init__(self, cid, h, v, tq):
        self.id, self.h, self.v, self.tq = cid, h, v, tq
        self.scanned = False


def u16(d, at):
    return d[at] << 8 | d[at + 1]


def read(d, max_pixels):
    if len(d) < 2 or d[0] != 0xFF or d[1] != 0xD8:
        raise Refused('not a JPEG file')
    n = len(d)
    pos = 2
    qt = [None] * 4
    dc_tables = [None] * 4
    ac_tables = [None] * 4
    restart = 0
    frame = None
    jfif = False
    adobe = None
    scans = 0
    while True:
        if pos >= n:
            raise Refused('the file is cut short')
        if d[pos] != 0xFF:
            raise Refused('something other than a marker, where a marker should be')
        while pos < n and d[pos] == 0xFF:      # fill bytes before a marker
            pos += 1
        if pos >= n:
            raise Refused('the file is cut short')
        m = d[pos]
        pos += 1
        if m == 0xD9:
            break
        if m == 0xD8:
            raise Refused('a second start of image')
        if 0xD0 <= m <= 0xD7:
            raise Refused('a restart marker outside the image data')
        if m == 0x01 or m == 0x00:
            raise Refused('marker FF%02X, which JPEG doesn\'t use here' % m)
        if n - pos < 2:
            raise Refused('the file is cut short')
        length = u16(d, pos)
        if length < 2:
            raise Refused('a segment of less than 2 bytes')
        if length > n - pos:
            raise Refused('the file is cut short')
        body = d[pos + 2:pos + length]
        pos += length

        if m in (0xC0, 0xC1):
            if frame is not None:
                raise Refused('more than one frame header')
            frame = read_frame(body, max_pixels)
        elif m == 0xC2:
            raise Refused('progressive JPEG, which isn\'t supported yet')
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
        elif m == 0xDC:
            raise Refused('a DNL marker, which isn\'t supported')
        elif m == 0xDA:
            if frame is None:
                raise Refused('image data before the frame header')
            pos = read_scan(d, pos, body, frame, qt, dc_tables, ac_tables, restart)
            scans += 1
        elif m == 0xE0:
            if len(body) >= 14 and body[:5] == b'JFIF\x00':
                jfif = True
        elif m == 0xEE:
            if len(body) >= 12 and body[:5] == b'Adobe':
                adobe = body[11]
        elif 0xE1 <= m <= 0xEF or m == 0xFE or m == 0xCC:
            pass                               # APPn, COM and DAC: skipped
        else:
            raise Refused('marker FF%02X, which JPEG doesn\'t use here' % m)

    if frame is None or scans == 0:
        raise Refused('no image data')
    for c in frame.comps:
        if not c.scanned:
            raise Refused('a component with no image data')
    rgb = False
    if len(frame.comps) == 3:
        if jfif:
            rgb = False
        elif adobe is not None:
            rgb = adobe == 0
        else:
            ids = [c.id for c in frame.comps]
            rgb = ids == [82, 71, 66]
    return frame.width, frame.height, output(frame, rgb)


class Frame:
    pass


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
        if tq > 3:
            raise Refused('quantization table %d, which JPEG doesn\'t have' % tq)
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
        c.plane = bytearray(c.stride * c.rows)
    if len(f.comps) == 1:
        # one component: libjpeg's MCU is its one block, whatever its sampling factors say
        c = f.comps[0]
        c.stride = (c.width + 7) // 8 * 8
        c.rows = (c.height + 7) // 8 * 8
        c.plane = bytearray(c.stride * c.rows)
    return f


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
    """the scan's entropy-coded data, from pos, into its components' planes; where it ends"""
    if len(body) < 1:
        raise Refused('a scan header of the wrong length')
    count = body[0]
    if len(body) != 4 + 2 * count:
        raise Refused('a scan header of the wrong length')
    if count < 1 or count > 4:
        raise Refused('a scan of %d components' % count)
    comps = []
    for k in range(count):
        cid, t = body[1 + 2 * k], body[2 + 2 * k]
        c = next((c for c in frame.comps if c.id == cid), None)
        if c is None:
            raise Refused('a scan of a component the frame doesn\'t have')
        if c in comps:
            raise Refused('a component twice in one scan')
        if c.scanned:
            raise Refused('a component in two scans')
        td, ta = t >> 4, t & 15
        if td > 3 or ta > 3 or dc_tables[td] is None or ac_tables[ta] is None:
            raise Refused('a scan using a Huffman table that isn\'t defined')
        if qt[c.tq] is None:
            raise Refused('a component whose quantization table isn\'t defined')
        c.dc, c.ac, c.q = dc_tables[td], ac_tables[ta], qt[c.tq]
        c.dc.build(True)
        c.ac.build(False)
        comps.append(c)
    ss, se, a = body[1 + 2 * count], body[2 + 2 * count], body[3 + 2 * count]
    if ss != 0 or se != 63 or a != 0:
        raise Refused('a scan that isn\'t sequential')
    if count > 1 and sum(c.h * c.v for c in comps) > 10:
        raise Refused('more than 10 blocks in an MCU')
    for c in comps:
        c.scanned = True

    # the blocks of each MCU, as (component, block across, block down) for the MCU at 0, 0
    if count == 1:
        c = comps[0]
        across = (c.width + 7) // 8
        total = across * ((c.height + 7) // 8)
    else:
        across = frame.mcux
        total = frame.mcux * frame.mcuy
    done = 0
    interval = 0
    while done < total:
        data, pos = segment(d, pos)
        todo = total - done if restart == 0 else min(restart, total - done)
        bits = Bits(data)
        preds = [0] * count
        for k in range(todo):
            mx, my = (done + k) % across, (done + k) // across
            for ci, c in enumerate(comps):
                if count == 1:
                    blocks = [(mx, my)]
                else:
                    blocks = [(mx * c.h + bx, my * c.v + by) for by in range(c.v) for bx in range(c.h)]
                for bx, by in blocks:
                    preds[ci] = block(bits, c, preds[ci], bx, by)
        done += todo
        if done < total:
            if pos + 1 >= len(d) or d[pos + 1] != 0xD0 + (interval & 7):
                raise Refused('a restart marker missing or out of order')
            pos += 2
            interval += 1
    return pos


def segment(d, pos):
    """the entropy-coded bytes from pos to the next marker, unstuffed, and where that marker is"""
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
    """one block, decoded and put in its place; the DC prediction after it"""
    coef = [0] * 64
    s = bits.decode(c.dc)
    diff = extend(bits.bits(s), s) if s else 0
    pred = i32(pred + diff)
    coef[0] = i16(pred)
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
        if k > 63:
            raise Refused('a run of coefficients past the end of a block')
        coef[ZIGZAG[k]] = extend(bits.bits(s), s)
        k += 1
    samples = idct(coef, c.q)
    base = by * 8 * c.stride + bx * 8
    for y in range(8):
        c.plane[base + y * c.stride:base + y * c.stride + 8] = bytes(samples[8 * y:8 * y + 8])
    return pred


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
    out = [0] * (w * h)
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
