"""GIF, as imagelib reads it, written plainly in Python: the rules libs/image/imagelib/gif.phi follows,
check for check, giving the same reasons.

What a GIF shows is decided by browsers, so where the references differ the rules follow them. Each
difference from the GIF test suite, Pillow and ImageMagick is listed with its reason in
make_gif_tests.py.

  - The header is GIF87a or GIF89a.
  - The canvas is the logical screen, grown to hold the first frame if that's past its right or
    bottom edge, as Chrome grows it (and Pillow); after that, frames are clipped to it. A canvas of
    no width or height is refused, as is one over the pixel limit. It starts transparent. The background color is ignored, as
    browsers ignore it.
  - Each image is a frame, drawn over what the frames before it left, clipped to the screen. Its
    graphic control extension (the last one before it) gives its delay, its transparent index and
    how it's disposed of.
  - A transparent pixel leaves the canvas as it was. An index past the end of the color table (the
    local one, or else the global one, or none at all) is opaque black.
  - Disposal, before the next frame is drawn: 2 clears the frame's area to transparent; 3 puts back
    what the area held before the frame was drawn, and so does 4, as browsers read it (some specs
    put "restore previous" in the field's third bit); 0, 1 and 5 to 7 leave it.
  - LZW codes are read as the GIF spec has them. The code size grows when the next free code
    reaches it, up to 12 bits. When the table is full, no more codes are added until a clear (a "deferred
    clear"). Codes after the end code, and pixels past the frame's, are ignored.
  - Damage shows what can be shown, as browsers show it. If a frame's data ends early (its blocks
    end, or the file does), or has a code that can't be, what was drawn of it stays, the rest of its
    area is as it was, and that's the last frame. A file that ends between frames ends the
    animation there. A byte between blocks that starts none (not an image, an extension or the
    trailer) is skipped, as GIF87a says and Pillow and ImageMagick do (Chrome ends the animation).
  - A file with no image in it is refused, and so is a first image whose LZW code size isn't 2 to 11
    (GIF's are 2 to 8, but Pillow and ImageMagick read up to 11). For a later frame, that ends the
    animation.
  - The loop count is from a NETSCAPE2.0 (or ANIMEXTS1.0) application extension: 0 means forever,
    n means n more times after the first; -1 means there was none, so it plays once.
  - Each frame's delay is in milliseconds, as the file has it (in hundredths of a second). Browsers
    show a delay of 10 ms or less as 100 ms, which is for the program showing it to do.
"""
import array


class Refused(Exception):
    pass


class Gif:
    """an animation being read: open() it, then next_frame() until it gives False"""

    def __init__(self, data, max_pixels):
        self.data = data
        if len(data) < 13 or data[:6] not in (b'GIF87a', b'GIF89a'):
            raise Refused('not a GIF file')
        self.w = data[6] | data[7] << 8
        self.h = data[8] | data[9] << 8
        self.max_pixels = max_pixels
        if self.w * self.h > max_pixels:
            raise Refused('%d by %d is more than the limit of %d pixels' % (self.w, self.h, max_pixels))
        flags = data[10]
        self.pos = 13
        self.global_table = []
        if flags & 0x80:
            n = 2 << (flags & 7)
            if self.pos + 3 * n > len(data):
                raise Refused('the file is cut short')
            self.global_table = table(data, self.pos, n)
            self.pos += 3 * n
        self.canvas = None        # made at the first frame, when the canvas's size is known
        self.loops = -1
        self.frames = 0
        self.ended = False
        self.dispose = None       # (method, x0, y0, x1, y1, saved) for the last frame
        self.delay = 0

    def next_frame(self):
        """draws the next frame on the canvas: True, or False when there's none (and the first
        frame's trouble refuses the file)"""
        if self.ended:
            return False
        d = self.data
        gce = None
        while True:
            if self.pos >= len(d):
                return self.end()
            b = d[self.pos]
            if b == 0x21:
                if self.pos + 1 >= len(d):
                    return self.end()
                label = d[self.pos + 1]
                blocks, after = sub_blocks(d, self.pos + 2)
                if after is None:
                    return self.end()
                if label == 0xF9 and blocks and len(blocks[0]) >= 4:
                    gce = blocks[0]
                elif label == 0xFF and blocks and blocks[0] in (b'NETSCAPE2.0', b'ANIMEXTS1.0'):
                    for sb in blocks[1:]:
                        if len(sb) >= 3 and sb[0] == 1:
                            self.loops = sb[1] | sb[2] << 8
                            break
                self.pos = after
            elif b == 0x2C:
                return self.image(gce)
            elif b == 0x3B:
                return self.end()
            else:
                self.pos += 1         # a byte that starts no block: skipped

    def end(self):
        self.ended = True
        if self.frames == 0:
            raise Refused('a GIF with no image in it')
        return False

    def image(self, gce):
        d = self.data
        p = self.pos
        if p + 10 > len(d):
            return self.end()
        fx, fy = d[p + 1] | d[p + 2] << 8, d[p + 3] | d[p + 4] << 8
        fw, fh = d[p + 5] | d[p + 6] << 8, d[p + 7] | d[p + 8] << 8
        flags = d[p + 9]
        p += 10
        colors = self.global_table
        if flags & 0x80:
            n = 2 << (flags & 7)
            if p + 3 * n > len(d):
                return self.end()
            colors = table(d, p, n)
            p += 3 * n
        if p >= len(d):
            return self.end()
        min_size = d[p]
        p += 1
        if min_size < 2 or min_size > 11:
            if self.frames == 0:
                raise Refused('an LZW code size that isn\'t 2 to 11')
            self.ended = True
            return False

        if self.frames == 0:
            self.w = max(self.w, fx + fw)
            self.h = max(self.h, fy + fh)
            if self.w == 0 or self.h == 0:
                raise Refused('an image of no size')
            if self.w * self.h > self.max_pixels:
                raise Refused('%d by %d is more than the limit of %d pixels' % (self.w, self.h, self.max_pixels))
            self.canvas = array.array('I', [0]) * (self.w * self.h)

        # the last frame's disposal, now that there's a next one
        self.undo()
        transparent = -1
        dispose = 0
        self.delay = 0
        if gce is not None:
            dispose = (gce[0] >> 2) & 7
            if dispose == 4:
                dispose = 3
            if gce[0] & 1:
                transparent = gce[3]
            self.delay = (gce[1] | gce[2] << 8) * 10
        x0, y0 = min(fx, self.w), min(fy, self.h)
        x1, y1 = min(fx + fw, self.w), min(fy + fh, self.h)
        saved = None
        if dispose == 3:
            saved = [self.canvas[y * self.w + x0:y * self.w + x1] for y in range(y0, y1)]
        self.dispose = (dispose, x0, y0, x1, y1, saved)

        indexes, after, whole = lzw(d, p, min_size, fw * fh)
        palette = [0xFF000000 | r << 16 | g << 8 | bb for r, g, bb in colors]
        rows = interlaced_rows(fh) if flags & 0x40 else range(fh)
        k = 0
        for row in rows:
            if k >= len(indexes):
                break
            y = fy + row
            line = indexes[k:k + fw]
            k += fw
            if y >= self.h:
                continue
            for i, v in enumerate(line):
                x = fx + i
                if x >= self.w:
                    break
                if v != transparent:
                    self.canvas[y * self.w + x] = palette[v] if v < len(palette) else 0xFF000000
        self.frames += 1
        if not whole:
            self.ended = True
        else:
            self.pos = after
        return True

    def undo(self):
        if self.dispose is None:
            return
        method, x0, y0, x1, y1, saved = self.dispose
        if method == 2:
            for y in range(y0, y1):
                for x in range(x0, x1):
                    self.canvas[y * self.w + x] = 0
        elif method == 3:
            for y in range(y0, y1):
                self.canvas[y * self.w + x0:y * self.w + x1] = saved[y - y0]
        self.dispose = None


def table(d, p, n):
    return [(d[p + 3 * i], d[p + 3 * i + 1], d[p + 3 * i + 2]) for i in range(n)]


def sub_blocks(d, p):
    """the sub-blocks from p, and where they end; None if the file ends first"""
    out = []
    while True:
        if p >= len(d):
            return out, None
        n = d[p]
        if n == 0:
            return out, p + 1
        if p + 1 + n > len(d):
            return out, None
        out.append(bytes(d[p + 1:p + 1 + n]))
        p += 1 + n


def interlaced_rows(h):
    return list(range(0, h, 8)) + list(range(4, h, 8)) + list(range(2, h, 4)) + list(range(1, h, 2))


def lzw(d, p, min_size, count):
    """a frame's indexes from its sub-blocks at p (at most count of them), where the sub-blocks end,
    and whether the data was whole: False when it ends early or has a code that can't be"""
    out = array.array('H')     # indexes: up to 2047, for a code size of 11
    clear = 1 << min_size
    eoi = clear + 1
    size = min_size + 1
    nxt = clear + 2
    prefix = [0] * 4096
    suffix = [0] * 4096
    first = [0] * 4096
    length = [0] * 4096
    for i in range(clear):
        suffix[i] = first[i] = i
        length[i] = 1
    prev = -1
    acc = 0
    nbits = 0
    block_left = 0
    ended = False        # the data stopped: the end code, or (with whole False) damage
    whole = True
    while True:
        # the next code, from the sub-blocks
        while nbits < size:
            if block_left == 0:
                if p >= len(d):
                    return out, None, False
                block_left = d[p]
                p += 1
                if block_left == 0:
                    return out, p, False      # the data ends without its end code
            if p >= len(d):
                return out, None, False
            acc |= d[p] << nbits
            nbits += 8
            p += 1
            block_left -= 1
        code = acc & ((1 << size) - 1)
        acc >>= size
        nbits -= size
        if code == clear:
            size = min_size + 1
            nxt = clear + 2
            prev = -1
            continue
        if code == eoi:
            break
        if prev < 0:
            if code >= clear:
                whole = False
                break
            out.append(code)
            prev = code
            if nxt >= 1 << size and size < 12:
                size += 1
        else:
            if code < nxt:
                c = code
            elif code == nxt and nxt < 4096:
                c = prev
            else:
                whole = False
                break
            # the code's string, written backwards
            n = length[c]
            start = len(out)
            out.extend(array.array('H', [0]) * n)
            j = c
            for i in range(n - 1, -1, -1):
                out[start + i] = suffix[j]
                j = prefix[j]
            if code == nxt:
                out.append(first[prev])
            if nxt < 4096:
                prefix[nxt] = prev
                suffix[nxt] = first[code] if code < nxt else first[prev]
                first[nxt] = first[prev]
                length[nxt] = length[prev] + 1
                nxt += 1
            if nxt >= 1 << size and size < 12:
                size += 1
            prev = code
        if len(out) >= count:
            break
    if len(out) > count:
        del out[count:]
    # skip to the end of the sub-blocks
    if block_left:
        p += block_left
        if p > len(d):
            return out, None, False
    while True:
        if p >= len(d):
            return out, None, False
        n = d[p]
        p += 1
        if n == 0:
            break
        p += n
    if p > len(d):
        return out, None, False
    return out, p, whole


def decode(data, max_pixels=16 * 1024 * 1024):
    """the first frame: (True, (w, h, pixels)) or (False, why)"""
    try:
        g = Gif(data, max_pixels)
        g.next_frame()
        return True, (g.w, g.h, g.canvas)
    except Refused as e:
        return False, str(e)


def animate(data, max_pixels=16 * 1024 * 1024, most=64):
    """every frame, up to most: (True, (w, h, loops, [(pixels, delay)...])) or (False, why)"""
    try:
        g = Gif(data, max_pixels)
        frames = []
        while len(frames) < most and g.next_frame():
            frames.append((array.array('I', g.canvas), g.delay))
        return True, (g.w, g.h, g.loops, frames)
    except Refused as e:
        return False, str(e)
