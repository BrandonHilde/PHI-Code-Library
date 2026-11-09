"""What imagelib's BMP decoder should make of a file, written plainly in Python.

    from bmp_reference import decode
    ok, result = decode(data)   # ok: result is (width, height, pixels); otherwise it's why not

pixels is a list of 0xAARRGGBB values, a row at a time from the top. This is the rule book that
imagelib's decoder follows, and make_bmp_tests.py checks it against outside evidence: BMP Suite's
reference images, and Pillow. Where those disagree with each other, the choice is BMP Suite's
(and the browsers'), and the README says where that leaves this and Pillow apart:

  - Pixels RLE skips over (with a delta, or an early end of line or of the image) are transparent.
  - A channel of n bits becomes 8 by scaling, round(v * 255 / (2^n - 1)), so its top value is 255.
  - Alpha only comes from an alpha mask: in a header of 56 bytes or more, or BI_ALPHABITFIELDS.
    The unused bits of 16 and 32-bit pixels without one are ignored, so those images are opaque.
  - An index past the end of the palette is opaque black.

What it refuses: anything it can't read whole (it's cut short), headers of sizes no BMP has, bit
depths and compressions it doesn't do (2-bit is done; 64-bit, Huffman 1D, RLE24 and embedded
JPEG and PNG aren't), RLE stored top-down, masks that aren't one run of bits, and any image of
more than max_pixels pixels, which is checked before anything is allocated.
"""
import array

MAX_PIXELS = 16 * 1024 * 1024          # imagelib's default for Img.max_pixels

HEADER_SIZES = (12, 16, 40, 52, 56, 64, 108, 124)

RGB, RLE8, RLE4, BITFIELDS, JPEG, PNG, ALPHABITFIELDS = 0, 1, 2, 3, 4, 5, 6


class Refused(Exception):
    pass


def u16(d, at):
    if at + 2 > len(d):
        raise Refused('the file is cut short')
    return d[at] | d[at + 1] << 8


def u32(d, at):
    if at + 4 > len(d):
        raise Refused('the file is cut short')
    return d[at] | d[at + 1] << 8 | d[at + 2] << 16 | d[at + 3] << 24


def i32(d, at):
    v = u32(d, at)
    return v - (1 << 32) if v & 0x80000000 else v


def channel(mask):
    """(shift, bits) for a mask; refuses one that isn't a single run of bits"""
    if mask == 0:
        return 0, 0
    shift = 0
    while not (mask >> shift) & 1:
        shift += 1
    run = mask >> shift
    bits = 0
    while (run >> bits) & 1:
        bits += 1
    if run >> bits:
        raise Refused('a color mask that isn\'t one run of bits')
    return shift, bits


def scale(v, bits):
    if bits == 0:
        return 0
    top = (1 << bits) - 1
    return (v * 255 + top // 2) // top


def decode(data, max_pixels=MAX_PIXELS):
    try:
        return True, _decode(bytes(data), max_pixels)
    except Refused as e:
        return False, str(e)


def _decode(d, max_pixels):
    if len(d) < 18 or d[0:2] != b'BM':
        raise Refused('not a BMP file')
    offset = u32(d, 10)
    hs = u32(d, 14)
    if hs not in HEADER_SIZES:
        raise Refused('a header of %d bytes, which no BMP has' % hs)
    if 14 + hs > len(d):
        raise Refused('the file is cut short')
    os2 = hs in (16, 64)
    if hs == 12:
        width, height = u16(d, 18), u16(d, 20)
        bpp = u16(d, 24)
        compression = RGB
        colors = 0
    else:
        width, height = i32(d, 18), i32(d, 22)
        bpp = u16(d, 28)
        compression = u32(d, 30) if hs >= 20 else RGB
        colors = u32(d, 46) if hs >= 36 else 0
    top_down = height < 0
    if top_down:
        height = -height
    if width <= 0 or height <= 0 or width > 0x7FFFFFFF or height > 0x7FFFFFFF:
        raise Refused('a width or height of 0 or less')

    if os2 and compression == 3:
        raise Refused('Huffman 1D compression, which isn\'t supported')
    if os2 and compression == 4:
        raise Refused('RLE24 compression, which isn\'t supported')
    if compression in (JPEG, PNG):
        raise Refused('an embedded JPEG or PNG, which isn\'t supported')
    if bpp not in (1, 2, 4, 8, 16, 24, 32):
        raise Refused('%d bits a pixel, which isn\'t supported' % bpp)
    if compression == RLE8 and bpp != 8 or compression == RLE4 and bpp != 4:
        raise Refused('RLE compression with the wrong number of bits a pixel')
    if compression in (BITFIELDS, ALPHABITFIELDS) and bpp not in (16, 32):
        raise Refused('bit fields with %d bits a pixel' % bpp)
    if compression not in (RGB, RLE8, RLE4, BITFIELDS, ALPHABITFIELDS):
        raise Refused('compression %d, which isn\'t supported' % compression)
    rle = compression in (RLE8, RLE4)
    if rle and top_down:
        raise Refused('RLE compression stored top-down, which BMP doesn\'t allow')

    if width * height > max_pixels:
        raise Refused('%d by %d is more than the limit of %d pixels' % (width, height, max_pixels))

    # the masks: in the header from 52 bytes on, or after a 40-byte one
    at = 14 + hs
    masks = None
    if compression in (BITFIELDS, ALPHABITFIELDS):
        if hs >= 52:
            masks = [u32(d, 54), u32(d, 58), u32(d, 62), u32(d, 66) if hs >= 56 else 0]
        else:
            count = 4 if compression == ALPHABITFIELDS else 3
            masks = [u32(d, at + 4 * k) for k in range(count)] + [0] * (4 - count)
            at += 4 * count
        if compression == ALPHABITFIELDS and hs >= 52 and hs < 56:
            masks[3] = u32(d, at)
            at += 4
    elif bpp == 16:
        masks = [0x7C00, 0x03E0, 0x001F, 0]
    elif bpp == 32:
        masks = [0xFF0000, 0xFF00, 0xFF, 0]
    if masks is not None:
        for m in masks:
            if m >> bpp:
                raise Refused('a color mask wider than the pixel')
        fields = [channel(m) for m in masks]

    # the palette
    palette = []
    if bpp <= 8:
        entry = 3 if hs == 12 else 4
        most = 1 << bpp
        if colors:
            if offset >= at and colors * entry > offset - at:
                raise Refused('a palette of %d colors, which doesn\'t fit before the pixels' % colors)
            count = min(colors, most)
        elif offset >= at:
            count = min(most, (offset - at) // entry)
        else:
            count = most
        if at + count * entry > len(d):
            raise Refused('the file is cut short')
        for k in range(count):
            p = at + k * entry
            palette.append(0xFF000000 | d[p + 2] << 16 | d[p + 1] << 8 | d[p])
    if offset < 14 + hs or offset > len(d):
        raise Refused('the pixels\' offset is outside the file')

    def color(index):
        return palette[index] if index < len(palette) else 0xFF000000

    pixels = array.array('I', [0]) * (width * height)
    if rle:
        rle_decode(d[offset:], width, height, compression == RLE4, color, pixels)
        return width, height, pixels

    row_bytes = (width * bpp + 31) // 32 * 4
    need = row_bytes * (height - 1) + (width * bpp + 7) // 8
    if offset + need > len(d):
        raise Refused('the file is cut short')
    for row in range(height):
        y = row if top_down else height - 1 - row
        p = offset + row * row_bytes
        out = y * width
        if bpp <= 8:
            per = 8 // bpp
            for x in range(width):
                byte = d[p + x // per]
                index = (byte >> (8 - bpp - (x % per) * bpp)) & ((1 << bpp) - 1)
                pixels[out + x] = color(index)
        elif bpp == 24:
            for x in range(width):
                q = p + 3 * x
                pixels[out + x] = 0xFF000000 | d[q + 2] << 16 | d[q + 1] << 8 | d[q]
        else:
            size = bpp // 8
            for x in range(width):
                q = p + size * x
                v = d[q] | d[q + 1] << 8
                if size == 4:
                    v |= d[q + 2] << 16 | d[q + 3] << 24
                r, g, b, a = [scale((v & m) >> s, n) for m, (s, n) in zip(masks, fields)]
                if masks[3] == 0:
                    a = 255
                pixels[out + x] = a << 24 | r << 16 | g << 8 | b
    return width, height, pixels


def rle_decode(src, width, height, four, color, pixels):
    """RLE8 or RLE4, from the bottom row up. What it never reaches stays transparent; runs that go
    past the end of a row are cut off there; data that ends without an end-of-image is a failure.
    x stops at width, which changes nothing drawn but keeps it small (as imagelib's u32 must be)."""
    x, y = 0, 0
    i = 0
    n = len(src)

    def put(index):
        if x < width and y < height:
            pixels[(height - 1 - y) * width + x] = color(index)

    while True:
        if y >= height:
            return
        if i + 2 > n:
            raise Refused('the RLE data ends before the end of the image')
        count, value = src[i], src[i + 1]
        i += 2
        if count:
            for k in range(count):
                put((value >> 4 if k % 2 == 0 else value & 15) if four else value)
                x += 1
            x = min(x, width)
        elif value == 0:
            x, y = 0, y + 1
        elif value == 1:
            return
        elif value == 2:
            if i + 2 > n:
                raise Refused('the RLE data ends before the end of the image')
            x = min(x + src[i], width)
            y += src[i + 1]
            i += 2
        else:
            size = (value + 1) // 2 if four else value
            if i + size > n:
                raise Refused('the RLE data ends before the end of the image')
            for k in range(value):
                if four:
                    byte = src[i + k // 2]
                    put(byte >> 4 if k % 2 == 0 else byte & 15)
                else:
                    put(src[i + k])
                x += 1
            x = min(x, width)
            i += size + (size & 1)
