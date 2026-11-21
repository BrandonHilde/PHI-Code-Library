#!/usr/bin/env python3
"""Writes Brotli's fixed data for corelib (RFC 7932), from the Brotli library itself.

    python3 -I tools/core/brotli_tables.py [libbrotlicommon.dylib|.so]

Through the library's own functions (BrotliGetDictionary, BrotliGetTransforms) and data
(_kBrotliContextLookupTable, _kBrotliPrefixCodeRanges), not typed in:

    libs/core/brotli/dictionary.bin   the static dictionary, 122,784 bytes (RFC 7932, appendix A),
                                      which a program gives corelib to read streams that use it
    libs/core/corelib/brotlitables.phi  the rest, which is small: the dictionary's shape (how many
                                      words of each length, and where they start), the 121 transforms
                                      (appendix B), the literal context lookup (7.1), and the block
                                      lengths' ranges (6)

Checked as it goes: the dictionary's size, its first words, the number of transforms and the first
few as the RFC lists them, and the ranges' first and last. Brotli is MIT-licensed (THIRD_PARTY.md).
"""
import ctypes
import glob
import os
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Dictionary(ctypes.Structure):
    _fields_ = [('size_bits_by_length', ctypes.c_uint8 * 32), ('offsets_by_length', ctypes.c_uint32 * 32),
                ('data_size', ctypes.c_size_t), ('data', ctypes.POINTER(ctypes.c_uint8))]


class Transforms(ctypes.Structure):
    _fields_ = [('prefix_suffix_size', ctypes.c_uint16), ('prefix_suffix', ctypes.POINTER(ctypes.c_uint8)),
                ('prefix_suffix_map', ctypes.POINTER(ctypes.c_uint16)), ('num_transforms', ctypes.c_uint32),
                ('transforms', ctypes.POINTER(ctypes.c_uint8)), ('params', ctypes.POINTER(ctypes.c_uint8)),
                ('cutOffTransforms', ctypes.c_int16 * 10)]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob('/opt/homebrew/lib/libbrotlicommon.*.dylib'))[0]
    lib = ctypes.CDLL(path)
    lib.BrotliGetDictionary.restype = ctypes.POINTER(Dictionary)
    lib.BrotliGetTransforms.restype = ctypes.POINTER(Transforms)
    d = lib.BrotliGetDictionary().contents
    data = bytes(d.data[:d.data_size])
    size_bits = list(d.size_bits_by_length)
    offsets = list(d.offsets_by_length)
    assert len(data) == 122784, 'the dictionary is %d bytes' % len(data)
    assert data.startswith(b'timedownlifeleftbackcodedatashowonlysitecity'), 'the dictionary starts otherwise'
    assert size_bits[4:25] == [10, 10, 11, 11, 10, 10, 10, 10, 10, 9, 9, 8, 7, 7, 8, 7, 7, 6, 6, 5, 5], size_bits
    assert all(offsets[n] + (n << size_bits[n]) == (offsets[n + 1] if n < 24 else len(data)) for n in range(4, 25)), 'offsets'
    t = lib.BrotliGetTransforms().contents
    n = t.num_transforms
    assert n == 121, '%d transforms' % n
    trip = [t.transforms[i] for i in range(n * 3)]
    ps = bytes(t.prefix_suffix[:t.prefix_suffix_size])
    psmap = [t.prefix_suffix_map[i] for i in range(max(trip[0::3] + trip[2::3]) + 1)]

    def text(i):
        at = psmap[i]
        return ps[at + 1:at + 1 + ps[at]]
    # RFC 7932, appendix B: the first few, (prefix, type, suffix)
    rfc = [(b'', 0, b''), (b'', 0, b' '), (b' ', 0, b' '), (b'', 12, b''), (b'', 10, b' '), (b'', 0, b' the '),
           (b' ', 0, b''), (b's ', 0, b' '), (b'', 0, b' of '), (b'', 10, b'')]
    for i, (p, k, s) in enumerate(rfc):
        got = (text(trip[i * 3]), trip[i * 3 + 1], text(trip[i * 3 + 2]))
        assert got == (p, k, s), 'transform %d is %r' % (i, got)
    lut = (ctypes.c_uint8 * 2048).in_dll(lib, '_kBrotliContextLookupTable')
    lut = list(lut)
    assert lut[:64] == list(range(64)) and lut[256:320] == [0] * 64, 'the LSB6 table'
    ranges_raw = (ctypes.c_uint8 * (26 * 4)).in_dll(lib, '_kBrotliPrefixCodeRanges')
    raw = bytes(ranges_raw)
    ranges = [(raw[i * 4] | raw[i * 4 + 1] << 8, raw[i * 4 + 2]) for i in range(26)]
    assert ranges[0] == (1, 2) and ranges[-1] == (16625, 24), ranges

    os.makedirs(os.path.join(ROOT, 'libs', 'core', 'brotli'), exist_ok=True)
    with open(os.path.join(ROOT, 'libs', 'core', 'brotli', 'dictionary.bin'), 'wb') as f:
        f.write(data)

    def rows(name, typ, values, per):
        out = [f'\t{typ} {name}:']
        for i in range(0, len(values), per):
            out.append('\t\t' + ' '.join(str(v) for v in values[i:i + per]))
        out[-1] += ';'
        return '\n'.join(out)
    # the prefixes and suffixes as one run of bytes, each found by where it starts and how long it is
    ps_at = [psmap[i] + 1 for i in range(len(psmap))]
    ps_len = [ps[psmap[i]] for i in range(len(psmap))]
    text_out = f'''# Brotli's fixed data (RFC 7932), made by tools/core/brotli_tables.py from the Brotli library's own,
# and checked there against the RFC. Don't change it by hand. Brotli is MIT-licensed: THIRD_PARTY.md.
# The static dictionary itself is libs/core/brotli/dictionary.bin, which a program gives
# CoreBrotli.Dictionary, so that 120 KB isn't in every program that uses corelib.

phi.CoreBrotliTables:Library
{{
	const u32 DICTIONARY_SIZE: {len(data)};
	const u32 DICTIONARY_CRC: {zlib.crc32(data)};
	# the dictionary's words of each length (4 to 24): how many, as bits, and where they start
{rows('size_bits', 'u8', size_bits, 32)}
{rows('offsets', 'u32', offsets, 16)}
	# the 121 transforms (appendix B): prefix, kind, suffix each; kinds 0 identity, 1 to 9 omit
	# that many last, 10 uppercase the first, 11 uppercase all, 12 to 20 omit 1 to 9 first
{rows('transforms', 'u8', trip, 30)}
	# the prefixes and suffixes: where each starts in affix, and how long it is
{rows('affix_at', 'u16', ps_at, 25)}
{rows('affix_len', 'u8', ps_len, 25)}
{rows('affix', 'u8', list(ps), 32)}
	# a literal's context from the two bytes before it, by mode (LSB6, MSB6, UTF8, SIGNED): each
	# mode 512 bytes, lookup[p1] | lookup[256 + p2] (7.1)
{rows('lookup', 'u8', lut, 32)}
	# block lengths' codes: each's base and its extra bits (6)
{rows('range_base', 'u16', [r[0] for r in ranges], 26)}
{rows('range_bits', 'u8', [r[1] for r in ranges], 26)}
}}
'''
    with open(os.path.join(ROOT, 'libs', 'core', 'corelib', 'brotlitables.phi'), 'w', newline='\n') as f:
        f.write(text_out)
    print('wrote the dictionary (%d bytes, CRC-32 %08x) and brotlitables.phi from %s; every check passed' % (len(data), zlib.crc32(data), path))


if __name__ == '__main__':
    main()
