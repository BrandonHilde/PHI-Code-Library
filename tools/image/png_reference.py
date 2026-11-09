"""What imagelib's PNG decoder should make of a file, written plainly in Python.

    from png_reference import decode
    ok, result = decode(data)   # ok: result is (width, height, pixels); otherwise it's why not

pixels is a list of 0xAARRGGBB values, a row at a time from the top. This is the rule book that
imagelib's decoder follows, check for check and in the same order, so that the two give the same
reasons. make_png_tests.py checks it against outside evidence: PngSuite, and two decoders that
share no code, ImageMagick (which reads PNG with libpng) and Pillow. Where the PNG standard leaves
a choice, the choice is libpng's, which is the browsers':

  - A sample of n bits becomes 8 by scaling, round(v * 255 / (2^n - 1)), so 16-bit samples are
    rounded rather than cut to their top byte.
  - tRNS makes a gray or RGB color transparent when it matches all 16 bits of the sample, before
    any scaling. Pixels made transparent keep their color.
  - A palette index past the end of the palette is opaque black.
  - Gamma, color profiles, sBIT and the rest are ignored, so the samples are what the file holds.
  - Ancillary chunks that are wrong are ignored, as libpng does: a bad CRC, a tRNS of the wrong
    length or out of place, a PLTE in a gray image. Critical ones are refused.

And it shows what it can, as Pillow and the browsers do:

  - The image is done at the end of the IDATs, so nothing after them is read: no IEND is needed,
    and a chunk after them that's wrong in any way is no matter.
  - Image data past what the image needs is ignored.
  - Image data that ends too soon (the file cut short, in an IDAT or before one more, or a zlib
    stream that stops early or has no Adler-32) gives the rows that came whole, and the rest of
    the image is transparent (0), as Pillow gives it with LOAD_TRUNCATED_IMAGES and the browsers
    show it.

What it refuses is what libpng and Pillow both refuse: image data that's damaged, an IDAT's CRC that
doesn't match it, headers that are wrong, and a file with no IDAT. Not done: APNG's other frames (the
default image is read).
"""
import array
import zlib

MAX_PIXELS = 16 * 1024 * 1024          # imagelib's default for Img.max_pixels

SIGNATURE = b'\x89PNG\r\n\x1a\n'

DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}

# Adam7: where each pass starts, and its steps, across and down
PASSES = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


class Refused(Exception):
    pass


def u32(d, at):
    return d[at] << 24 | d[at + 1] << 16 | d[at + 2] << 8 | d[at + 3]


def passes(w, h, interlace):
    """each pass's (x0, y0, dx, dy, width, height), leaving out empty ones"""
    if not interlace:
        return [(0, 0, 1, 1, w, h)]
    out = []
    for x0, y0, dx, dy in PASSES:
        pw = (w - x0 + dx - 1) // dx if w > x0 else 0
        ph = (h - y0 + dy - 1) // dy if h > y0 else 0
        if pw and ph:
            out.append((x0, y0, dx, dy, pw, ph))
    return out


def decode(data, max_pixels=MAX_PIXELS):
    try:
        return True, read(bytes(data), max_pixels)
    except Refused as e:
        return False, str(e)


def read(d, max_pixels):
    if len(d) < 8 or d[:8] != SIGNATURE:
        raise Refused('not a PNG file')
    n = len(d)
    at = 8
    width = height = depth = color = interlace = 0
    have_header = False
    palette = None
    trns = None           # palette alphas, or the 16-bit gray value, or the (r, g, b) one
    idat = []
    idat_state = 0        # 0: none yet, 1: in them, 2: past them
    expected = 0
    while True:
        if n - at < 12:
            if idat_state:
                break                           # the image data is all there is
            raise Refused('the file is cut short')
        length = u32(d, at)
        kind = d[at + 4:at + 8]
        if idat_state and kind != b'IDAT':
            break                               # the end of the IDATs: the image is done
        if length > 0x7FFFFFFF:
            raise Refused('a chunk of more than 2 GB')
        cut = length > n - at - 12
        if cut and kind != b'IDAT':
            raise Refused('the file is cut short')
        if not all(65 <= c <= 90 or 97 <= c <= 122 for c in kind):
            raise Refused('a chunk whose name isn\'t four letters')
        name = kind.decode('ascii')
        critical = kind[0] <= 90
        if cut:
            body = d[at + 8:n]                  # an IDAT cut short: what there is of it, unchecked
            at = n
        else:
            body = d[at + 8:at + 8 + length]
            crc = u32(d, at + 8 + length)
            at += 12 + length
            if zlib.crc32(kind + body) != crc:
                if critical:
                    raise Refused('the ' + name + ' chunk\'s CRC doesn\'t match it')
                continue
        if not have_header and name != 'IHDR':
            raise Refused('the file doesn\'t start with an IHDR chunk')

        if name == 'IHDR':
            if have_header:
                raise Refused('more than one IHDR chunk')
            if length != 13:
                raise Refused('an IHDR chunk of %d bytes, where it has 13' % length)
            have_header = True
            width = u32(body, 0)
            height = u32(body, 4)
            depth, color, method, filtering, interlace = body[8:13]
            if width == 0 or height == 0 or width > 0x7FFFFFFF or height > 0x7FFFFFFF:
                raise Refused('a width or height of 0, or of more than 2^31 - 1')
            if color not in DEPTHS:
                raise Refused('color type %d, which PNG doesn\'t have' % color)
            if depth not in DEPTHS[color]:
                raise Refused('a bit depth of %d with color type %d, which PNG doesn\'t allow' % (depth, color))
            if method != 0:
                raise Refused('compression method %d, which PNG doesn\'t have' % method)
            if filtering != 0:
                raise Refused('filter method %d, which PNG doesn\'t have' % filtering)
            if interlace > 1:
                raise Refused('interlace method %d, which PNG doesn\'t have' % interlace)
            if width * height > max_pixels:
                raise Refused('%d by %d is more than the limit of %d pixels' % (width, height, max_pixels))
            bits = depth * CHANNELS[color]
            expected = sum(ph * (1 + (pw * bits + 7) // 8) for _, _, _, _, pw, ph in passes(width, height, interlace))
            if expected > 0x7FFFFFFF:
                raise Refused('the image data would be more than 2 GB')
        elif name == 'PLTE':
            if color in (0, 4):
                continue                        # not allowed in a gray image, and ignored
            if palette is not None:
                raise Refused('more than one PLTE chunk')
            if length == 0 or length > 768 or length % 3:
                raise Refused('a PLTE chunk of %d bytes' % length)
            palette = [0xFF000000 | body[k] << 16 | body[k + 1] << 8 | body[k + 2] for k in range(0, length, 3)]
        elif name == 'tRNS':
            # wrong in any way, it's ignored, as libpng does
            if trns is not None:
                continue
            if color == 3:
                if palette is not None and 0 < length <= len(palette):
                    trns = list(body)
            elif color == 0:
                if length == 2:
                    trns = body[0] << 8 | body[1]
            elif color == 2:
                if length == 6:
                    trns = (body[0] << 8 | body[1], body[2] << 8 | body[3], body[4] << 8 | body[5])
        elif name == 'IDAT':
            if color == 3 and palette is None:
                raise Refused('a palette image with no PLTE chunk before its image data')
            idat_state = 1
            idat.append(body)
            if cut:
                break
        elif name == 'IEND':
            if not idat_state:
                raise Refused('no image data (no IDAT chunk)')
            break
        elif critical:
            raise Refused('a critical chunk imagelib doesn\'t know, ' + name)

    raw = inflate(b''.join(idat), expected)
    return width, height, pixels(raw, width, height, depth, color, interlace, palette, trns)


def inflate(data, expected):
    """the image data, up to expected bytes: as much as there is, when it ends too soon. What comes
    after the last byte the image needs isn't looked at, as libpng doesn't look at it (zlib still
    reads on past it while that takes no room, through the end of a block, and so does imagelib's
    inflate)."""
    z = zlib.decompressobj()
    try:
        out = z.decompress(data, expected)
    except zlib.error:
        raise Refused('the image data is damaged')
    return out


def unfilter(raw, at, pw, ph, bits):
    """one pass's rows, unfiltered: a list of bytearrays"""
    stride = (pw * bits + 7) // 8
    step = max(1, bits // 8)
    rows = []
    prior = bytearray(stride)
    for y in range(ph):
        f = raw[at]
        row = bytearray(raw[at + 1:at + 1 + stride])
        at += 1 + stride
        if f > 4:
            raise Refused('a row with filter type %d, which PNG doesn\'t have' % f)
        for i in range(stride):
            a = row[i - step] if i >= step else 0
            b = prior[i]
            if f == 1:
                row[i] = (row[i] + a) & 255
            elif f == 2:
                row[i] = (row[i] + b) & 255
            elif f == 3:
                row[i] = (row[i] + (a + b) // 2) & 255
            elif f == 4:
                c = prior[i - step] if i >= step else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                if pa <= pb and pa <= pc:
                    pred = a
                elif pb <= pc:
                    pred = b
                else:
                    pred = c
                row[i] = (row[i] + pred) & 255
        rows.append(row)
        prior = row
    return rows, at


def samples(row, count, depth):
    """count samples from a row, each as the file has it (up to 16 bits)"""
    if depth == 16:
        return [row[2 * k] << 8 | row[2 * k + 1] for k in range(count)]
    if depth == 8:
        return list(row[:count])
    per = 8 // depth
    top = (1 << depth) - 1
    return [(row[k // per] >> (8 - depth - (k % per) * depth)) & top for k in range(count)]


def scale(v, depth):
    top = (1 << depth) - 1
    return (v * 255 + top // 2) // top


def pixels(raw, w, h, depth, color, interlace, palette, trns):
    out = array.array('I', [0]) * (w * h)
    channels = CHANNELS[color]
    bits = depth * channels
    at = 0
    for x0, y0, dx, dy, pw, ph in passes(w, h, interlace):
        # the rows of the pass that came whole; when they stop, the rest of the image is 0
        whole = min(ph, (len(raw) - at) // (1 + (pw * bits + 7) // 8))
        rows, at = unfilter(raw, at, pw, whole, bits)
        for y, row in enumerate(rows):
            s = samples(row, pw * channels, depth)
            o = (y0 + y * dy) * w
            for x in range(pw):
                v = s[x * channels:(x + 1) * channels]
                if color == 3:
                    i = v[0]
                    if i < len(palette):
                        p = palette[i]
                        if trns is not None and i < len(trns):
                            p = (p & 0xFFFFFF) | trns[i] << 24
                    else:
                        p = 0xFF000000
                else:
                    c = [scale(c, depth) for c in v]
                    if color == 0:
                        a = 0 if trns == v[0] else 255
                        p = a << 24 | c[0] << 16 | c[0] << 8 | c[0]
                    elif color == 4:
                        p = c[1] << 24 | c[0] << 16 | c[0] << 8 | c[0]
                    elif color == 2:
                        a = 0 if trns == tuple(v) else 255
                        p = a << 24 | c[0] << 16 | c[1] << 8 | c[2]
                    else:
                        p = c[3] << 24 | c[0] << 16 | c[1] << 8 | c[2]
                out[o + x0 + x * dx] = p
        if whole < ph:
            break
    return out
