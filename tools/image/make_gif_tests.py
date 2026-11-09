"""Makes libs/image/tests/gif/cases.bin (with cases.txt, which says what's in it): the cases test_gif
runs imagelib's GIF decoder against, checked with the rules in gif_reference.py, which are checked
against Pillow and ImageMagick here (and, with --gifsuite DIR, the GIF test suite from
https://github.com/robert-ancell/pygif, whose test-suite folder isn't kept here: it's CC-BY-SA).

    python3 tools/image/make_gif_tests.py [--release] [--gifsuite DIR]

The cases:
  written   GIFs written by Pillow and ImageMagick: still images, transparency, interlacing, and
            animations with each disposal, as they write them
  made      GIFs made here, one or a few of each feature and each kind of damage
  cut       good files cut short
  fuzz      small files with a few bytes changed

A case is a whole animation (up to 64 frames): its verdict is the screen's size and one CRC-32 over
every frame's pixels, then each frame's delay, then the loop count, each a u32 (the pixels as
0xAARRGGBB, all little-endian). test_gif makes the same CRC as it reads the frames.

Where the rules differ from Pillow and ImageMagick (their fill of the first frame's uncovered area
with the background color; Pillow's canvas growing to hold a frame that's bigger than the screen; a
file damaged in a way they refuse), it's counted and said, never left unchecked: every pixel the rules
draw must be theirs.
"""
import argparse
import array
import io
import os
import random
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gif_reference  # noqa: E402
from cases import Cases as CaseFile, run_magick  # noqa: E402

LIB = os.path.normpath(os.path.join(HERE, '..', '..', 'libs', 'image'))
OUT = os.path.join(LIB, 'tests', 'gif')
MAX_PIXELS = 16 * 1024 * 1024
MOST_FRAMES = 64
WRITTEN, MADE, CUT, FUZZ = 0, 1, 2, 3
GROUP_NAMES = ['written', 'made', 'cut', 'fuzz']
RELEASE = False


def signature(data, max_pixels=MAX_PIXELS):
    """the rules' verdict on a whole animation, as Cases wants one: (True, (w, h, words)), the words
    being every frame's pixels, then each frame's delay, then the loop count; or (False, why)"""
    ok, result = gif_reference.animate(data, max_pixels, MOST_FRAMES)
    if not ok:
        return ok, result
    w, h, loops, frames = result
    words = array.array('I')
    for px, _ in frames:
        words.extend(px)
    for _, delay in frames:
        words.append(delay & 0xFFFFFFFF)
    words.append(loops & 0xFFFFFFFF)
    return True, (w, h, words)


# ---------------------------------------------------------------- writing GIF files

def lzw(indexes, min_size, clear_first=True, eoi=True, defer=False, clear_every=0, extra=b''):
    """indexes LZW-coded as GIF has them, in sub-blocks ending with the terminator. The decoder's
    code size is followed exactly, so codes change size where a decoder expects. defer: when the
    table is full, go on without adding codes (a deferred clear), rather than sending a clear.
    clear_every: a clear before every that many pixels. extra: bytes after the end code."""
    clear, end = 1 << min_size, (1 << min_size) + 1
    bits = []
    size = [min_size + 1]
    dec = {'nxt': clear + 2, 'prev': False}

    def emit(code):
        bits.append((code, size[0]))
        if code == clear:
            size[0] = min_size + 1
            dec['nxt'] = clear + 2
            dec['prev'] = False
            return
        if code == end:
            return
        if dec['prev'] and dec['nxt'] < 4096:
            dec['nxt'] += 1
        if dec['nxt'] >= 1 << size[0] and size[0] < 12:
            size[0] += 1
        dec['prev'] = True

    table = {}
    nxt = clear + 2
    if clear_first:
        emit(clear)
    w = None
    count = 0
    for k in indexes:
        if clear_every and count and count % clear_every == 0 and w is not None:
            emit(w)
            emit(clear)
            table, nxt, w = {}, clear + 2, None
        count += 1
        if w is None:
            w = k
            continue
        if (w, k) in table:
            w = table[(w, k)]
            continue
        emit(w)
        if nxt < 4096:
            table[(w, k)] = nxt
            nxt += 1
        elif not defer:
            emit(clear)
            table, nxt = {}, clear + 2
        w = k
    if w is not None:
        emit(w)
    if eoi:
        emit(end)
    acc = n = 0
    out = bytearray()
    for code, s in bits:
        acc |= code << n
        n += s
        while n >= 8:
            out.append(acc & 255)
            acc >>= 8
            n -= 8
    if n:
        out.append(acc & 255)
    out += extra
    return blocks(bytes(out))


def blocks(data, size=255):
    out = bytearray()
    for i in range(0, len(data), size):
        part = data[i:i + size]
        out += bytes([len(part)]) + part
    return bytes(out + b'\x00')


def colors_of(colors):
    """a color table, padded to a power of two: (its bytes, its size field)"""
    n = 2
    field = 0
    while n < len(colors):
        n *= 2
        field += 1
    out = bytearray()
    for r, g, b in list(colors) + [(0, 0, 0)] * (n - len(colors)):
        out += bytes((r, g, b))
    return bytes(out), field


def gce(delay=0, transparent=None, dispose=0):
    flags = (dispose & 7) << 2 | (1 if transparent is not None else 0)
    return b'\x21\xF9\x04' + struct.pack('<BHB', flags, delay, transparent or 0) + b'\x00'


def netscape(loops):
    return b'\x21\xFF\x0BNETSCAPE2.0\x03\x01' + struct.pack('<H', loops) + b'\x00'


def image(w, h, indexes, x=0, y=0, colors=None, interlace=False, min_size=None, data=None, **lzw_options):
    flags = 0x40 if interlace else 0
    table = b''
    if colors is not None:
        table, field = colors_of(colors)
        flags |= 0x80 | field
    if interlace:
        rows = gif_reference.interlaced_rows(h)
        indexes = [indexes[r * w + c] for r in rows for c in range(w)]
    if min_size is None:
        top = max(list(indexes) + [1])
        min_size = 2
        while (1 << min_size) <= top:
            min_size += 1
    head = b'\x2C' + struct.pack('<HHHHB', x, y, w, h, flags) + table
    if data is not None:
        return head + data
    return head + bytes([min_size]) + lzw(indexes, min_size, **lzw_options)


def gif(w, h, body, colors=((0, 0, 0), (255, 255, 255)), bg=0, version=b'GIF89a', trailer=True):
    flags = 0
    table = b''
    if colors is not None:
        table, field = colors_of(colors)
        flags = 0x80 | 0x70 | field
    out = version + struct.pack('<HHBBB', w, h, flags, bg, 0) + table + body
    return out + (b'\x3B' if trailer else b'')


PALETTE = [(0, 0, 0), (255, 255, 255), (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
           (0, 255, 255), (255, 0, 255)]


def pattern(w, h, colors, seed=0):
    return [(x * 3 + y * 5 + seed + (x * y) % 3) % colors for y in range(h) for x in range(w)]


def random_pixels(w, h, colors, seed):
    r = random.Random(seed)
    return [r.randrange(colors) for _ in range(w * h)]


def made_cases():
    """(name, data, max_pixels, rule): rule is 'auto' (Pillow and ImageMagick must agree, but for
    the differences counted), 'refused' (the rules refuse it; Pillow and ImageMagick must too, or it's
    said why not), or 'damaged' (the rules show what they can; where Pillow and ImageMagick read it,
    what the rules draw must be theirs)"""
    cases = []

    def add(name, data, rule='auto', max_pixels=0):
        cases.append((name, data, max_pixels, rule))

    # each color table size, and each code size that comes from it
    for depth in range(1, 9):
        n = 1 << depth
        colors = [((i * 37) % 256, (i * 91) % 256, (i * 151) % 256) for i in range(n)]
        add('depth%d' % depth, gif(9, 7, image(9, 7, pattern(9, 7, n)), colors))
    add('one-pixel', gif(1, 1, image(1, 1, [1])))
    add('local-table', gif(5, 3, image(5, 3, pattern(5, 3, 4), colors=PALETTE[2:6])))
    add('no-global-table', gif(5, 3, image(5, 3, pattern(5, 3, 4), colors=PALETTE[:4]), colors=None))
    add('no-table-at-all', gif(5, 3, image(5, 3, pattern(5, 3, 4)), colors=None))
    add('index-past-the-table', gif(4, 2, image(4, 2, [0, 1, 2, 3, 3, 2, 1, 0], min_size=2)))
    for h in (1, 2, 3, 5, 8, 9, 17):
        add('interlace-h%d' % h, gif(3, h, image(3, h, pattern(3, h, 8), interlace=True), PALETTE))
    big = random_pixels(64, 48, 256, 7)
    colors256 = [((i * 7) % 256, (i * 13) % 256, (i * 29) % 256) for i in range(256)]
    add('random-64x48', gif(64, 48, image(64, 48, big), colors256))
    add('random-deferred-clear', gif(64, 48, image(64, 48, big, defer=True), colors256))
    add('random-many-clears', gif(64, 48, image(64, 48, big, clear_every=7), colors256))
    add('random-clear-each-pixel', gif(16, 4, image(16, 4, big[:64], clear_every=1), colors256))
    add('runs-long-strings', gif(200, 30, image(200, 30, [1] * 6000)))
    add('no-first-clear', gif(5, 3, image(5, 3, pattern(5, 3, 8), clear_first=False), PALETTE))
    add('no-end-code', gif(5, 3, image(5, 3, pattern(5, 3, 8), eoi=False), PALETTE))
    add('bytes-after-the-end-code', gif(5, 3, image(5, 3, pattern(5, 3, 8), extra=b'hidden'), PALETTE))
    extra_pixels = b'\x2C' + struct.pack('<HHHHB', 0, 0, 3, 2, 0) + bytes([3]) + lzw(pattern(3, 2, 8) + [1] * 30, 3)
    add('more-pixels-than-the-frame', gif(3, 2, extra_pixels, PALETTE))
    few_pixels = b'\x2C' + struct.pack('<HHHHB', 0, 0, 3, 2, 0) + bytes([3]) + lzw([1, 2, 3], 3)
    add('fewer-pixels-than-the-frame', gif(3, 2, few_pixels, PALETTE), 'damaged')
    for size in (2, 7, 11):
        body = b'\x2C' + struct.pack('<HHHHB', 0, 0, 4, 2, 0) + bytes([size]) + lzw([0, 1, 1, 0, 1, 1, 0, 0], size)
        add('code-size-%d' % size, gif(4, 2, body))
    for size in (0, 1, 12, 255):
        body = b'\x2C' + struct.pack('<HHHHB', 0, 0, 2, 1, 0) + bytes([size]) + b'\x01\x00\x00'
        add('code-size-%d' % size, gif(2, 1, body), 'refused')

    # transparency
    add('transparent', gif(4, 2, gce(transparent=2) + image(4, 2, pattern(4, 2, 8)), PALETTE))
    add('transparent-past-the-table', gif(4, 2, gce(transparent=200) + image(4, 2, pattern(4, 2, 8)), PALETTE))
    add('transparent-flag-off', gif(4, 2, b'\x21\xF9\x04\x00\x00\x00\x02\x00' + image(4, 2, pattern(4, 2, 8)), PALETTE))
    add('second-gce-wins', gif(4, 2, gce(transparent=1) + gce(transparent=2) + image(4, 2, pattern(4, 2, 8)), PALETTE))
    add('gce-short', gif(4, 2, b'\x21\xF9\x02\x01\x00\x00' + image(4, 2, pattern(4, 2, 8)), PALETTE))

    # where frames are
    add('frame-inside', gif(5, 4, image(2, 2, [1, 2, 3, 4], 1, 1), PALETTE))
    add('frame-past-the-right-and-bottom', gif(4, 3, image(3, 3, pattern(3, 3, 8), 2, 1), PALETTE))
    add('frame-off-the-screen', gif(4, 3, image(3, 3, pattern(3, 3, 8), 9, 9) +
                                    gce(dispose=1) + image(2, 1, [2, 3], 1, 1), PALETTE))
    add('frame-bigger-than-the-screen', gif(3, 2, image(5, 4, pattern(5, 4, 8)), PALETTE))
    add('second-frame-past-the-screen', gif(3, 2, image(3, 2, [1] * 6) + image(4, 4, pattern(4, 4, 8), 1, 1), PALETTE))
    add('frame-no-width', gif(3, 2, image(0, 2, []) + image(3, 2, pattern(3, 2, 8)), PALETTE), 'damaged')

    # animations: each disposal, delays, loops
    frames = [(0, 0, 3, 3), (1, 0, 2, 2), (2, 2, 2, 2), (0, 1, 1, 3)]
    for dispose in range(8):
        body = netscape(0)
        for i, (x, y, w, h) in enumerate(frames):
            body += gce(10 * (i + 1), transparent=0 if i % 2 else None, dispose=dispose)
            body += image(w, h, pattern(w, h, 8, i), x, y)
        add('dispose-%d' % dispose, gif(4, 4, body, PALETTE))
    body = netscape(0) + image(4, 4, [1] * 16)
    for i, (x, y, w, h) in enumerate(frames):
        body += gce(5, dispose=(2, 3, 1, 3)[i]) + image(w, h, pattern(w, h, 8, i + 3), x, y)
    add('dispose-mixed', gif(4, 4, body, PALETTE))
    for loops in (0, 1, 7, 65535):
        add('loops-%d' % loops, gif(2, 1, netscape(loops) + gce(20) + image(2, 1, [1, 0]) + gce(20) + image(2, 1, [0, 1])))
    add('no-loops', gif(2, 1, gce(20) + image(2, 1, [1, 0]) + gce(20) + image(2, 1, [0, 1])))
    add('animexts-loops', gif(2, 1, b'\x21\xFF\x0BANIMEXTS1.0\x03\x01\x03\x00\x00' + gce(20) + image(2, 1, [1, 0]) + image(2, 1, [0, 1])))
    add('no-gce-frames', gif(3, 1, image(3, 1, [1, 2, 3]) + image(1, 1, [4], 1, 0) + image(1, 1, [5], 2, 0), PALETTE))
    add('gif87a-frames', gif(3, 1, image(3, 1, [1, 2, 3]) + image(1, 1, [4], 1, 0), PALETTE, version=b'GIF87a'))
    add('many-frames', gif(2, 2, netscape(0) + b''.join(gce(1, dispose=1) + image(1, 1, [k % 8], k % 2, (k // 2) % 2)
                                                        for k in range(80)), PALETTE))

    # extensions and blocks that are skipped
    add('comment', gif(2, 1, b'\x21\xFE\x05hello\x00' + image(2, 1, [1, 0])))
    add('plain-text', gif(2, 1, b'\x21\x01\x0C' + bytes(12) + b'\x03abc\x00' + image(2, 1, [1, 0])))
    add('unknown-application', gif(2, 1, b'\x21\xFF\x0BXMP DataXMP\x03abc\x00' + image(2, 1, [1, 0])))
    add('unknown-extension', gif(2, 1, b'\x21\x99\x02ab\x00' + image(2, 1, [1, 0])))
    add('netscape-short', gif(2, 1, b'\x21\xFF\x0BNETSCAPE2.0\x01\x01\x00' + image(2, 1, [1, 0])))
    add('no-trailer', gif(2, 1, image(2, 1, [1, 0]), trailer=False))
    add('junk-after-a-frame', gif(2, 1, image(2, 1, [1, 0]) + b'\x55\x00' + image(2, 1, [0, 1])))
    add('junk-before-the-first-frame', gif(2, 1, b'\x7F' + image(2, 1, [1, 0])))
    add('background-index-past-the-table', gif(2, 1, image(2, 1, [1, 0]), bg=200))

    # refused
    add('bad-signature', b'GIF88a' + gif(1, 1, image(1, 1, [1]))[6:], 'refused')
    add('not-a-gif', b'GIF', 'refused')
    add('screen-no-width', gif(0, 1, image(1, 1, [1])))
    add('screen-no-height', gif(1, 0, image(1, 1, [1])))
    add('screen-and-frame-no-size', gif(0, 0, image(0, 0, [])), 'refused')
    add('frame-grows-past-the-limit', gif(3, 2, image(3, 3, [1] * 9)), 'limit', max_pixels=8)
    add('no-image', gif(2, 2, b''), 'refused')
    add('no-image-only-extensions', gif(2, 2, gce(5) + b'\x21\xFE\x01x\x00'), 'refused')
    add('header-cut-in-the-table', gif(2, 2, b'', colors=PALETTE)[:20], 'refused')
    add('limit-5-pixels', gif(3, 2, image(3, 2, [1] * 6)), 'limit', max_pixels=5)
    add('limit-6-pixels', gif(3, 2, image(3, 2, [1] * 6)), max_pixels=6)
    add('screen-65535-square', gif(65535, 65535, image(1, 1, [1])), 'refused')

    # damaged: shown as far as it goes
    good = gif(6, 4, image(6, 4, pattern(6, 4, 8)), PALETTE)
    p = good.index(b'\x2C') + 11
    add('bad-code-first', good[:p] + b'\x02\xFF\x07\x00\x3B', 'damaged')
    bad = bytearray(good)
    bad[p + 2] ^= 0xF0
    add('bad-code-later', bytes(bad), 'damaged')
    add('data-ends-in-a-block', good[:p + 4], 'damaged')
    add('second-frame-cut', gif(4, 2, image(4, 2, [1] * 8) + gce(5) + image(4, 2, [2] * 8), PALETTE)[:-6], 'damaged')
    add('frame-header-cut', gif(4, 2, image(4, 2, [1] * 8) + b'\x2C\x00\x00\x00', PALETTE, trailer=False), 'damaged')
    return cases


# ---------------------------------------------------------------- what Pillow and ImageMagick make of them

def as_frames(w, h, frames):
    import numpy as np
    out = []
    for px, _ in frames:
        a = np.frombuffer(px, dtype=np.uint32).reshape(h, w)
        out.append(np.stack([(a >> 16) & 255, (a >> 8) & 255, a & 255, a >> 24], axis=2).astype(np.uint8))
    return out


def pillow(data):
    """Pillow's frames, as RGBA, with their delays and the loop count; None if it refuses"""
    import numpy as np
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))
        if im.format != 'GIF':
            return None
        out = []
        while len(out) < MOST_FRAMES:
            im.load()
            out.append((np.asarray(im.convert('RGBA')).copy(), im.info.get('duration', 0)))
            try:
                im.seek(im.tell() + 1)
            except EOFError:
                break
        return out, im.info.get('loop')
    except Exception:
        return None


def magick(data):
    """ImageMagick's frames, coalesced, as RGBA, with their delays; None if it refuses"""
    import numpy as np
    r = run_magick(['gif:-[0-%d]' % (MOST_FRAMES - 1), '-coalesce', '-depth', '8', '-format', '%w %h %T\n',
                    '-write', 'info:-', 'rgba:-'], data)
    if r is None or r.returncode != 0:
        return None
    rest = r.stdout
    sizes = []
    while True:
        line, _, after = rest.partition(b'\n')
        parts = line.split()
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            break
        sizes.append(tuple(int(p) for p in parts))
        rest = after
    out = []
    at = 0
    for w, h, t in sizes:
        out.append((np.frombuffer(rest[at:at + w * h * 4], np.uint8).reshape(h, w, 4), t * 10))
        at += w * h * 4
    return out if at == len(rest) and out else None


def compare(mine, theirs, background):
    """how the rules' frames compare with another's: 'same', 'background' (the same but where the
    rules leave a pixel transparent and theirs is the background color, or transparent), or what
    differs"""
    import numpy as np
    how = 'same'
    for i, (a, (b, _)) in enumerate(zip(mine, theirs)):
        if a.shape != b.shape:
            return 'frame %d is %dx%d, theirs %dx%d' % (i, a.shape[1], a.shape[0], b.shape[1], b.shape[0])
        clear_a = a[:, :, 3] == 0
        clear_b = b[:, :, 3] == 0
        differ = (a != b).any(axis=2) & ~(clear_a & clear_b)
        if not differ.any():
            continue
        drawn = differ & ~clear_a
        if drawn.any():
            y, x = np.argwhere(drawn)[0]
            return 'frame %d at %d,%d: %s, theirs %s' % (i, x, y, tuple(a[y, x]), tuple(b[y, x]))
        if background is None or not (b[differ][:, :3] == background).all():
            return 'frame %d: where the rules leave it transparent, theirs isn\'t the background' % i
        how = 'background'
    return how


def background_of(data):
    if len(data) >= 13 and data[10] & 0x80 and data[11] < (2 << (data[10] & 7)):
        at = 13 + 3 * data[11]
        if at + 3 <= len(data):
            return tuple(data[at:at + 3])
    return None


def check(name, data, max_pixels, rule, counts, problems, full=True):
    """the rules against Pillow and ImageMagick for one case"""
    ok, result = gif_reference.animate(data, max_pixels or MAX_PIXELS, MOST_FRAMES)
    p = pillow(data)
    m = magick(data)

    def count(key):
        counts[key] = counts.get(key, 0) + 1

    notes = NOTES.get(name, {})
    if rule == 'limit':
        if ok:
            problems.append('%s: should be refused for the limit' % name)
        else:
            count('refused for the pixel limit, which Pillow and ImageMagick don\'t have')
        return
    if not ok:
        if rule not in ('refused', 'damaged', 'fuzz'):
            problems.append('%s: the rules refuse it: %s' % (name, result))
        elif p is not None and m is not None and rule != 'fuzz' and name not in REFUSED_BUT_READ:
            problems.append('%s: the rules refuse it (%s), but Pillow and ImageMagick read it' % (name, result))
        else:
            count('refused' if p is None and m is None else 'refused, where %s reads it' %
                  ('Pillow and ImageMagick' if p is not None and m is not None else 'Pillow' if p is not None else 'ImageMagick'))
        return
    if rule == 'refused':
        problems.append('%s: should be refused, but the rules read it' % name)
        return
    if rule == 'browser':
        count('read as browsers read it, where Pillow and ImageMagick differ')
        return
    w, h, loops, frames = result
    mine = as_frames(w, h, frames)
    bg = background_of(data)
    for who, theirs in (('Pillow', p), ('ImageMagick', m)):
        if who in notes:
            count('differs from %s, as noted' % who)
            continue
        if theirs is None:
            if rule in ('damaged', 'fuzz'):
                count('damaged: %s refuses it' % who)
            else:
                problems.append('%s: %s refuses it' % (name, who))
            continue
        their_frames = theirs[0] if who == 'Pillow' else theirs
        if len(their_frames) != len(mine) and rule in ('damaged', 'fuzz'):
            count('damaged: %s shows %s frames' % (who, 'more' if len(their_frames) > len(mine) else 'fewer'))
            n = min(len(their_frames), len(mine))
            how = compare(mine[:n - 1] if len(their_frames) > len(mine) else mine[:n], their_frames[:n], bg)
        else:
            if len(their_frames) != len(mine):
                problems.append('%s: %d frames, where %s has %d' % (name, len(mine), who, len(their_frames)))
                continue
            how = compare(mine, their_frames, bg)
            if how != 'same' and rule in ('damaged', 'fuzz'):
                # damage: theirs may stop drawing the last frame sooner
                how2 = compare(mine[:-1], their_frames[:-1], bg)
                if how2 in ('same', 'background'):
                    count('damaged: %s draws its last frame differently' % who)
                    continue
        if how == 'same':
            count('the same as %s' % who)
        elif how == 'background':
            count('the same as %s, but for its background fill' % who)
        elif rule == 'fuzz':
            count('fuzz: differs from %s' % who)
            FUZZ_DIFFERENCES.setdefault(who, []).append((name, how))
        else:
            problems.append('%s: differs from %s: %s' % (name, who, how))
            continue
        if who == 'Pillow' and rule == 'auto':
            delays = [d for _, d in frames]
            if [d for _, d in theirs[0]] != delays:
                problems.append('%s: delays %s, where Pillow has %s' % (name, delays, [d for _, d in theirs[0]]))
            if (theirs[1] if theirs[1] is not None else -1) != loops and 'Pillow loops' not in notes:
                problems.append('%s: loops %s, where Pillow has %s' % (name, loops, theirs[1]))


FUZZ_DIFFERENCES = {}

# Where a made case differs from Pillow or ImageMagick, and why. Each is only not compared with that one.
NOTES = {
    'index-past-the-table': {'ImageMagick': 'it refuses an index past the color table; browsers show opaque black, as Pillow does'},
    'gce-short': {'Pillow': 'it refuses a graphic control extension too short for its fields, which the rules ignore',
                  'ImageMagick': 'it uses what there is of a graphic control extension too short for its fields'},
    'no-table-at-all': {'Pillow': 'it gives a frame with no color table a gray one; every index is past the end of no table, so opaque black',
                        'ImageMagick': 'it refuses a frame with no color table'},
    'dispose-4': {'Pillow': 'it keeps a frame disposed of with 4, which browsers read as 3, "restore previous"',
                  'ImageMagick': 'it keeps a frame disposed of with 4, which browsers read as 3, "restore previous"'},
    'dispose-5': {'Pillow': 'it reads disposal 5 to 7 as its own; they keep the frame, as ImageMagick has it'},
    'dispose-6': {'Pillow': 'it reads disposal 5 to 7 as its own; they keep the frame, as ImageMagick has it'},
    'dispose-7': {'Pillow': 'it reads disposal 5 to 7 as its own; they keep the frame, as ImageMagick has it'},
    'dispose-3': {'Pillow': 'its "restore previous" on the first frame keeps that frame; browsers clear it, as ImageMagick does'},
    'animexts-loops': {'Pillow loops': 'it doesn\'t read ANIMEXTS1.0\'s loop count, which browsers read as NETSCAPE2.0\'s'},
    'frame-off-the-screen': {'ImageMagick': 'it doesn\'t grow the screen to hold the first frame; Chrome grows it, as Pillow does'},
    'frame-past-the-right-and-bottom': {'ImageMagick': 'it doesn\'t grow the screen to hold the first frame; Chrome grows it, as Pillow does'},
    'second-frame-past-the-screen': {'Pillow': 'it grows the screen for a later frame too; Chrome grows it only for the first, and clips the rest, as ImageMagick does'},
    'frame-bigger-than-the-screen': {'ImageMagick': 'it doesn\'t grow the screen to hold the first frame; Chrome grows it, as Pillow does'},
}

# made cases the rules refuse though Pillow and ImageMagick both read them, and why
REFUSED_BUT_READ = {
    'code-size-0': 'an LZW code size of 0, which GIF doesn\'t have',
    'code-size-1': 'an LZW code size of 1: Pillow and ImageMagick read this one, whose data is a single code, but refuse one with more',
}


# ---------------------------------------------------------------- files Pillow and ImageMagick write

def written_cases():
    import numpy as np
    from PIL import Image
    out = []

    def picture(w, h, seed):
        y, x = np.mgrid[0:h, 0:w]
        a = np.stack([(x * 255 // max(w - 1, 1)), (y * 255 // max(h - 1, 1)), ((x + y + seed * 40) * 9) % 256], axis=2)
        return Image.fromarray(a.astype(np.uint8))

    def save(im, **kw):
        b = io.BytesIO()
        im.save(b, 'GIF', **kw)
        return b.getvalue()

    sizes = ((1, 1), (7, 5), (33, 17), (64, 48)) if RELEASE else ((7, 5), (33, 17))
    for w, h in sizes:
        out.append(('pil-%dx%d' % (w, h), save(picture(w, h, 0).quantize(64))))
        out.append(('pil-%dx%d-not-interlaced' % (w, h), save(picture(w, h, 1).quantize(16), interlace=False)))
    im = picture(9, 6, 2).quantize(8)
    im.info['transparency'] = 3
    out.append(('pil-transparent', save(im, transparency=3)))
    frames = [picture(12, 8, k).quantize(32) for k in range(4)]
    for disposal in (0, 1, 2, 3):
        out.append(('pil-animation-disposal-%d' % disposal,
                    save(frames[0], save_all=True, append_images=frames[1:], duration=[30, 40, 50, 60],
                         loop=0, disposal=disposal)))
    out.append(('pil-animation-optimized', save(frames[0], save_all=True, append_images=frames[1:2] * 2 + frames[2:],
                                                duration=100, loop=3, optimize=True)))
    rgba = [Image.fromarray(np.where((np.arange(12)[None, :, None] + k) % 3 == 0, 0,
                                     np.asarray(picture(12, 8, k).convert('RGBA'))).astype(np.uint8)) for k in range(3)]
    out.append(('pil-animation-rgba', save(rgba[0], save_all=True, append_images=rgba[1:], duration=70, loop=0,
                                           disposal=2)))
    # ImageMagick, which writes frames as small as it can, with transparency, when it optimizes
    magick_files = [
        ('im-gradient', ['-size', '31x17', 'gradient:red-blue', 'gif:-']),
        ('im-plasma', ['-size', '40x30', 'xc:', '-seed', '5', '+noise', 'Random', '-colors', '100', 'gif:-']),
        ('im-animation-optimized', ['-size', '20x16', '-delay', '15', 'xc:white', '-fill', 'red', '-draw', 'rectangle 2,2 8,8',
                                    '(', '+clone', '-fill', 'blue', '-draw', 'rectangle 6,6 14,12', ')',
                                    '(', '+clone', '-fill', 'green', '-draw', 'circle 10,8 13,10', ')',
                                    '-loop', '2', '-layers', 'OptimizePlus', 'gif:-']),
        ('im-animation-dispose-previous', ['-size', '16x12', '-dispose', 'Previous', '-delay', '25', 'xc:yellow',
                                          '(', '-size', '5x5', 'xc:red', '-repage', '+3+2', ')',
                                          '(', '-size', '6x4', 'xc:blue', '-repage', '+8+6', ')', '-loop', '0', 'gif:-']),
    ]
    for name, args in magick_files:
        r = run_magick(args, b'')
        if r is None or r.returncode != 0 or not r.stdout.startswith(b'GIF'):
            sys.exit('ImageMagick couldn\'t write %s: %s' % (name, r.stderr.decode()[:200] if r else 'timeout'))
        out.append((name, r.stdout))
    return out


def check_suite(folder, counts, problems):
    """the rules against the GIF test suite's frames: each file's frames, where the suite has them"""
    import configparser
    import numpy as np
    from PIL import Image
    # where the rules differ from the suite, and why
    notes = {
        'images-combine': 'the suite makes one frame of images with no delay; browsers show each',
        'images-overlap': 'the suite makes one frame of images with no delay; browsers show each',
        'high-color': 'the suite makes one frame of images with no delay; browsers show each',
        'dispose-restore-previous': 'the suite makes one frame of images with no delay; browsers show each',
        'animation-multi-image': 'the suite makes one frame of images with no delay; browsers show each',
        'animation-multi-image-explicit-zero-delay': 'the suite makes one frame of images with no delay; browsers show each',
        'no-data': 'the suite shows a file with no image as its empty screen; the rules refuse it, as Pillow and ImageMagick do',
        'image-zero-width': 'a frame with no LZW data after it: the suite shows the empty screen; refused, as Pillow and ImageMagick do',
        'image-zero-height': 'the same',
        'image-zero-size': 'the same',
        'image-overlap-bg': 'the suite clips the first frame to the screen; Chrome grows the screen to hold it, as Pillow does',
        'image-outside-bg': 'the suite clips the first frame to the screen; Chrome grows the screen to hold it, as Pillow does',
    }
    for name in open(os.path.join(folder, 'TESTS')).read().split():
        c = configparser.ConfigParser()
        c.read(os.path.join(folder, name + '.conf'))
        conf = c['config']
        data = open(os.path.join(folder, conf['input']), 'rb').read()
        wanted = [f for f in conf['frames'].split(',') if f]
        ok, result = gif_reference.animate(data, MAX_PIXELS, 100)
        if name in notes:
            counts['suite: differs, as noted'] = counts.get('suite: differs, as noted', 0) + 1
            continue
        if not wanted:
            counts['suite: no frames given'] = counts.get('suite: no frames given', 0) + 1
            continue
        if not ok:
            problems.append('suite %s: the rules refuse it: %s' % (name, result))
            continue
        w, h, loops, frames = result
        if len(frames) != len(wanted) or (w, h) != (int(conf['width']), int(conf['height'])):
            problems.append('suite %s: %d frames of %dx%d, where the suite has %d of %sx%s' %
                            (name, len(frames), w, h, len(wanted), conf['width'], conf['height']))
            continue
        bad = None
        for i, (fname, (px, delay)) in enumerate(zip(wanted, frames)):
            f = c[fname]
            if 'pixels' in f:
                ref = np.frombuffer(open(os.path.join(folder, f['pixels']), 'rb').read(), np.uint8).reshape(h, w, 4)
            else:
                ref = np.asarray(Image.open(os.path.join(folder, f['image'])).convert('RGBA'))
            how = compare(as_frames(w, h, [(px, 0)]), [(ref, 0)], None)
            if how != 'same':
                bad = 'frame %d: %s' % (i, how)
                break
            if 'delay' in f and int(f['delay']) * 10 != delay:
                bad = 'frame %d: delay %d, where the suite has %s0' % (i, delay, f['delay'])
                break
        if bad:
            problems.append('suite %s: %s' % (name, bad))
        else:
            counts['suite: the same'] = counts.get('suite: the same', 0) + 1


def cut_lengths(size):
    if RELEASE:
        return [at for at in range(1, size) if at < 120 or size - at <= 40 or at % 17 == 0]
    return sorted(set(at for at in (8, 14, 30, size // 4, size // 2, size * 3 // 4, size - 1) if 0 < at < size))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--release', action='store_true', help='make the release cases too')
    ap.add_argument('--gifsuite', help='the GIF test suite\'s test-suite folder, to check the rules against')
    args = ap.parse_args()
    global RELEASE
    RELEASE = args.release
    os.makedirs(OUT, exist_ok=True)

    counts, problems = {}, []
    if args.gifsuite:
        check_suite(args.gifsuite, counts, problems)
    written = written_cases()
    for name, data in written:
        check(name, data, 0, 'auto', counts, problems)
    made = made_cases()
    for name, data, max_pixels, rule in made:
        check(name, data, max_pixels, rule, counts, problems)
    print('the rules against Pillow and ImageMagick (and the suite):', counts)
    if problems:
        print('\n'.join(problems))
        sys.exit('the rules and the outside evidence disagree, %d times' % len(problems))

    cases = CaseFile(signature, MAX_PIXELS, OUT, 'make_gif_tests.py', GROUP_NAMES)
    index = {}
    for name, data in written:
        index[name] = cases.add(WRITTEN, 1, name, data)
    for name, data, max_pixels, _ in made:
        index[name] = cases.add(MADE, 1, name, data, max_pixels)

    # cut short: each cut shows the frames its file showed, and as much of the next as came
    fuzz_counts = {}
    for name in (('pil-33x17', 'pil-animation-disposal-2', 'pil-animation-optimized', 'im-animation-optimized',
                  'interlace-h17', 'random-64x48', 'dispose-mixed') if RELEASE else
                 ('pil-animation-disposal-2', 'interlace-h17')):
        source = index[name]
        data = cases.list[source][5]
        _, (sw, sh, _, whole) = gif_reference.animate(data, MAX_PIXELS, MOST_FRAMES)
        for at in cut_lengths(len(data)):
            cut = data[:at]
            cases.add(CUT, 2, '%s-to-%d' % (name, at), cut, 0, (source, at))
            ok, result = gif_reference.animate(cut, MAX_PIXELS, MOST_FRAMES)
            if not ok:
                continue
            frames = result[3]
            for i, (px, _) in enumerate(frames[:-1]):
                if px != whole[i][0]:
                    sys.exit('%s-to-%d: frame %d isn\'t the frame it was cut from' % (name, at, i))
            last, full = frames[-1][0], whole[len(frames) - 1][0]
            before = frames[-2][0] if len(frames) > 1 else None
            for k in range(len(last)):
                if last[k] != full[k] and last[k] != 0 and (before is None or last[k] != before[k]):
                    sys.exit('%s-to-%d: its last frame shows what its file didn\'t' % (name, at))
            check('%s-to-%d' % (name, at), cut, 0, 'damaged', fuzz_counts, problems)

    # fuzz: small files with a few bytes changed
    r = random.Random(20261109)
    small = [name for name, data, _, rule in made if len(data) < 600 and rule in ('auto', 'browser')]
    small += [name for name, data in written if len(data) < 2000]
    for k in range(4000 if RELEASE else 40):
        name = r.choice(small)
        source = index[name]
        data = bytearray(cases.list[source][5])
        changes = []
        for _ in range(r.choice((1, 1, 2, 3, 5))):
            at = r.randrange(min(len(data), 40)) if r.random() < 0.5 else r.randrange(len(data))
            v = r.choice((0, 1, 255, 0x7F, 0x80, 0x21, 0x2C, 0x3B, r.randrange(256), data[at] ^ (1 << r.randrange(8))))
            data[at] = v
            changes.append((at, v))
        cases.add(FUZZ, 3, 'fuzz-%d-%s' % (k, name), bytes(data), 0, (source, changes))
        check('fuzz-%d-%s' % (k, name), bytes(data), 0, 'fuzz', fuzz_counts, problems)
    print('cut and fuzzed, against Pillow and ImageMagick:', fuzz_counts)
    for who, items in FUZZ_DIFFERENCES.items():
        print('  fuzzed files that differ from %s: %d, such as %s' % (who, len(items), items[:3]))
    if problems:
        print('\n'.join(problems))
        sys.exit('the rules and the outside evidence disagree, %d times' % len(problems))

    size = cases.write('release' if RELEASE else 'cases')
    print('%s.bin: %d cases, %d bytes:' % ('release' if RELEASE else 'cases', len(cases.list), size), cases.summary())


if __name__ == '__main__':
    main()
