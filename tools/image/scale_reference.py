"""Scaling, as imagelib does it, written plainly in Python: the rules libs/image/imagelib/scale.phi
follows. Both ways of scaling are Pillow's (Image.resize):

  - Nearest: each pixel of the new image takes the old pixel under its center, found as Pillow finds
    it, in doubles: old x starts at (old_w / new_w) * 0.5 and goes up by old_w / new_w for each new
    pixel, and is that, rounded down. The running sum is what decides a center that falls exactly
    between two old pixels, as it does in Pillow. (PHI's f64 math is IEEE's, each result the nearest
    double, so this is the same in the 32 and 64-bit programs.) One that comes to the old image's
    edge, or past it, is left transparent, as Pillow leaves it.
  - Bilinear: Pillow's, worked out in exact integers rather than Pillow's doubles, so that the 32 and
    64-bit programs can't differ: which is a triangle filter as wide as one old pixel when growing, and as wide as
    a new pixel when shrinking (so shrinking averages every old pixel under it, not just the nearest
    four). Each new pixel's weights are the filter's at the old pixels' centers, normalized and made
    22-bit fixed point, rounded. The image is premultiplied by its alpha first, and divided by it
    again after, as Pillow does an RGBA image; it's scaled across first, each row rounded to 8 bits,
    and then down.

Pillow works the weights out in doubles, which now and then rounds one fixed-point weight
differently; make_scale_tests.py counts how often that changes a pixel, by how much.
"""
import array

PRECISION = 22


def weights(old, new):
    """for each new pixel along an axis: (first old pixel, [fixed-point weights])"""
    out = []
    big = max(old, new)
    for xx in range(new):
        # the filter's value at each old pixel's center, times 2 * big: max(0, 2 big - |d|), with
        # d = (2x + 1) new - (2xx + 1) old (center - x - 0.5, in units of 1 / (2 new), times
        # new / old when shrinking)
        # Pillow's bounds: (int)(center - support + 0.5) to (int)(center + support + 0.5), where
        # center is (xx + 0.5) old / new and support max(old / new, 1)
        support2 = 2 * max(old, new)            # support, times 2 new
        lo2 = (2 * xx + 1) * old - support2 + new   # (center - support + 0.5) * 2 new
        hi2 = (2 * xx + 1) * old + support2 + new
        lo = max(0, lo2 // (2 * new)) if lo2 >= 0 else 0
        hi = min(old, hi2 // (2 * new))
        ns = []
        for x in range(lo, hi):
            d = (2 * x + 1) * new - (2 * xx + 1) * old
            ns.append(max(0, 2 * big - abs(d)))
        total = sum(ns)
        fixed = [(2 * n * (1 << PRECISION) + total) // (2 * total) for n in ns]
        out.append((lo, fixed))
    return out


def premultiply(v):
    a = v >> 24
    out = a << 24
    for shift in (16, 8, 0):
        c = (v >> shift) & 255
        t = c * a + 128
        out |= ((t + (t >> 8)) >> 8) << shift
    return out


def unpremultiply(v):
    a = v >> 24
    if a in (0, 255):
        return v
    out = a << 24
    for shift in (16, 8, 0):
        c = (v >> shift) & 255
        out |= min(255, 255 * c // a) << shift
    return out


def clip8(s):
    s >>= PRECISION
    return 0 if s < 0 else 255 if s > 255 else s


def resample(px, w, h, new_w, new_h):
    """across, then down; px premultiplied"""
    def channels(v):
        return ((v >> 16) & 255, (v >> 8) & 255, v & 255, v >> 24)

    if new_w != w:
        across = weights(w, new_w)
        rows = array.array('I', [0]) * (new_w * h)
        for y in range(h):
            for xx, (lo, ks) in enumerate(across):
                s = [1 << (PRECISION - 1)] * 4
                for i, k in enumerate(ks):
                    c = channels(px[y * w + lo + i])
                    for j in range(4):
                        s[j] += c[j] * k
                r, g, b, a = (clip8(v) for v in s)
                rows[y * new_w + xx] = a << 24 | r << 16 | g << 8 | b
        px, w = rows, new_w
    if new_h != h:
        down = weights(h, new_h)
        out = array.array('I', [0]) * (w * new_h)
        for yy, (lo, ks) in enumerate(down):
            for x in range(w):
                s = [1 << (PRECISION - 1)] * 4
                for i, k in enumerate(ks):
                    c = channels(px[(lo + i) * w + x])
                    for j in range(4):
                        s[j] += c[j] * k
                r, g, b, a = (clip8(v) for v in s)
                out[yy * w + x] = a << 24 | r << 16 | g << 8 | b
        px = out
    return px


def centers(old, new):
    """the old pixel under each new one's center, as Pillow's running sum of doubles finds it; -1
    past the edge"""
    step = old / new
    at = step * 0.5
    out = []
    for _ in range(new):
        i = int(at)
        out.append(i if i < old else -1)
        at += step
    return out


def scale(w, h, px, new_w, new_h, bilinear):
    """an image of w by h pixels scaled to new_w by new_h: its pixels"""
    if (new_w, new_h) == (w, h):
        return array.array('I', px)
    if not bilinear:
        out = array.array('I', [0]) * (new_w * new_h)
        xs = centers(w, new_w)
        ys = centers(h, new_h)
        for y in range(new_h):
            if ys[y] < 0:
                continue
            for x in range(new_w):
                if xs[x] >= 0:
                    out[y * new_w + x] = px[ys[y] * w + xs[x]]
        return out
    pre = array.array('I', (premultiply(v) for v in px))
    out = resample(pre, w, h, new_w, new_h)
    return array.array('I', (unpremultiply(v) for v in out))
