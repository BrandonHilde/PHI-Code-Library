"""WOFF 1, as fontlib unpacks it, written plainly in Python: the rules libs/font/fontlib/woff.phi follows.
A WOFF file is a TrueType or CFF font with each table perhaps compressed by zlib; it's unpacked into the
font it holds, which is then read as any font is. The checks are FreeType's (sfwoff.c):

  - The header: the signature wOFF, the length the file's own, at least one table, a directory that fits
    (44 + 20 per table, less than the length), a total size for the font that holds its own directory
    (12 + 16 per table, less than it) and is a multiple of 4, and metadata and private data whose fields
    agree (a length with no offset, or metadata with no unpacked length, refuses it).
  - The directory: tags in ascending order; each table inside the file, no longer compressed than
    unpacked, and the tables together within the total size.
  - Each table: stored as it is when its compressed length is its length, or else zlib data that
    inflates to exactly its length.
  - fontlib's own limit: a font of more than 32 MB, unpacked, is refused (FreeType has none).

The font is laid out as FreeType lays it out: its header (the WOFF's flavor, the number of tables, and
the search fields worked out from it), the directory in the WOFF's order, and the tables in it, each at a
multiple of 4.
"""
import struct
import zlib

from ttf_reference import u16, u32, Refused

# fontlib's limit on the font a WOFF unpacks to, so that a small file can't claim gigabytes (FreeType has
# none); the biggest CJK fonts are about 20 MB
MOST_FONT_BYTES = 32 * 1024 * 1024


def unwoff(d):
    if len(d) < 44 or d[:4] != b'wOFF':
        raise Refused('not a WOFF file')
    flavor, length, n = u32(d, 4), u32(d, 8), u16(d, 12)
    total = u32(d, 16)
    meta_off, meta_len, meta_orig = u32(d, 24), u32(d, 28), u32(d, 32)
    priv_off, priv_len = u32(d, 36), u32(d, 40)
    if (length != len(d) or n == 0 or 44 + n * 20 >= length or 12 + n * 16 >= total or total & 3 or
            (meta_off == 0 and (meta_len or meta_orig)) or (meta_len and not meta_orig) or
            (priv_off == 0 and priv_len)):
        raise Refused('a WOFF header that doesn\'t add up')
    if total > MOST_FONT_BYTES:
        raise Refused('a WOFF font of more than 32 MB')
    tables = []
    sfnt_offset = 12 + n * 16
    old_tag = None
    for k in range(n):
        p = 44 + 20 * k
        tag, off, comp, orig, check = d[p:p + 4], u32(d, p + 4), u32(d, p + 8), u32(d, p + 12), u32(d, p + 16)
        if old_tag is not None and tag <= old_tag:
            raise Refused('a WOFF directory whose tags aren\'t in order')
        old_tag = tag
        if comp > orig or off > length or comp > length - off:
            raise Refused('a WOFF table past the end of the file')
        if orig > total - sfnt_offset:
            raise Refused('WOFF tables bigger than the font they make')
        tables.append((tag, off, comp, orig, check, sfnt_offset))
        sfnt_offset += (orig + 3) & ~3
    out = bytearray(total)
    search = 1
    selector = 0
    while search * 2 <= n:
        search *= 2
        selector += 1
    out[0:12] = struct.pack('>IHHHH', flavor, n, search * 16, selector, n * 16 - search * 16)
    for k, (tag, off, comp, orig, check, at) in enumerate(tables):
        out[12 + 16 * k:28 + 16 * k] = tag + struct.pack('>III', check, at, orig)
        data = bytes(d[off:off + comp])
        if comp < orig:
            try:
                z = zlib.decompressobj()
                data = z.decompress(data, orig + 1)
            except zlib.error:
                raise Refused('a WOFF table whose zlib data is broken')
            if not z.eof or len(data) != orig:
                raise Refused('a WOFF table that inflates to the wrong length')
        out[at:at + orig] = data
    return bytes(out)
