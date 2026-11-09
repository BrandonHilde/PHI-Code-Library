"""EXIF orientation, as imagelib reads and applies it, written plainly in Python: used by
jpeg_reference.py (an APP1 segment) and png_reference.py (an eXIf chunk).

It reads the orientation the way Chrome does, since that's what people see: the TIFF header must
be II*\\0 or MM\\0*, and the orientation is tag 0x0112 in the first IFD, of type SHORT and count 1,
with a value from 1 to 8. Anything else is orientation 1. And it applies it as Pillow's
ImageOps.exif_transpose does:

    1  as stored          5  transposed (across the main diagonal)
    2  mirrored            6  turned a quarter clockwise
    3  turned a half       7  transversed (across the other diagonal)
    4  flipped             8  turned a quarter counter-clockwise

so 5 to 8 swap the width and height.
"""
import array


def orientation(tiff):
    """the orientation in a TIFF block (EXIF's own, after its 'Exif\\0\\0'): 1 to 8, or None when
    the block isn't a TIFF header Chrome takes"""
    if len(tiff) < 8:
        return None
    if tiff[:4] == b'II*\x00':
        big = False
    elif tiff[:4] == b'MM\x00*':
        big = True
    else:
        return None

    def u16(at):
        return tiff[at] << 8 | tiff[at + 1] if big else tiff[at] | tiff[at + 1] << 8

    def u32(at):
        return u16(at) << 16 | u16(at + 2) if big else u16(at) | u16(at + 2) << 16

    ifd = u32(4)
    if ifd > len(tiff) - 2:
        return 1
    count = u16(ifd)
    for k in range(count):
        at = ifd + 2 + 12 * k
        if at > len(tiff) - 12:
            return 1
        if u16(at) == 0x0112:
            if u16(at + 2) == 3 and u32(at + 4) == 1:
                v = u16(at + 8)
                return v if 1 <= v <= 8 else 1
            return 1
    return 1


def orient(w, h, px, o):
    """an image of w by h pixels turned to orientation o: (width, height, pixels)"""
    if o == 1:
        return w, h, px
    turned = o >= 5
    ow, oh = (h, w) if turned else (w, h)
    out = array.array('I', [0]) * (w * h)
    for y in range(h):
        for x in range(w):
            if o == 2:
                X, Y = w - 1 - x, y
            elif o == 3:
                X, Y = w - 1 - x, h - 1 - y
            elif o == 4:
                X, Y = x, h - 1 - y
            elif o == 5:
                X, Y = y, x
            elif o == 6:
                X, Y = h - 1 - y, x
            elif o == 7:
                X, Y = h - 1 - y, w - 1 - x
            else:
                X, Y = y, w - 1 - x
            out[Y * ow + X] = px[y * w + x]
    return ow, oh, out
