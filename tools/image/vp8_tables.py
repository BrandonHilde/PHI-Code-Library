#!/usr/bin/env python3
"""Writes libs/image/imagelib/vp8tables.phi: the fixed tables of lossy WebP (VP8, RFC 6386).

    python3 -I tools/image/vp8_tables.py [LIBWEBP.dylib|.so]

The tables are RFC 6386's (its coefficient probabilities and their update probabilities, 13.5
and 13.4; the key frame's 4x4 intra mode probabilities, 12.3; the quantizer tables, 14.1). Rather
than typed in by hand, they're taken from libwebp's own compiled library, where they lie one after
another as its source declares them, and checked: each found where the one before it ends, by
values the RFC gives (first rows, last rows, the ends of the quantizer tables), with the band map
between two of them. Any mismatch stops it.
"""
import glob
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    lib = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob('/opt/homebrew/lib/libwebp.*.dylib'))[0]
    b = open(lib, 'rb').read()
    dc_at = b.find(bytes([4, 5, 6, 7, 8, 9, 10, 10, 11, 12, 13, 14, 15, 16, 17, 17]))
    assert dc_at > 0, 'no DC table'
    dc = list(b[dc_at:dc_at + 128])
    ac = list(struct.unpack('<128H', b[dc_at + 128:dc_at + 384]))
    upd = list(b[dc_at + 384:dc_at + 384 + 1056])
    coef = list(b[dc_at + 384 + 1056:dc_at + 384 + 2112])
    bands = list(b[dc_at + 384 + 2112:dc_at + 384 + 2129])
    bmode = list(b[dc_at + 384 + 2129:dc_at + 384 + 2129 + 900])
    checks = [
        (dc[-4:] == [148, 151, 154, 157], 'the DC table ends 148 151 154 157'),
        (ac[:8] == [4, 5, 6, 7, 8, 9, 10, 11] and ac[-4:] == [269, 274, 279, 284], 'the AC table runs 4 to 284'),
        (upd[:33] == [255] * 33 and upd[33:36] == [176, 246, 255], 'the update probabilities begin 255..., 176 246 255'),
        (coef[:33] == [128] * 33 and coef[33:39] == [253, 136, 254, 255, 228, 219], 'the probabilities begin 128..., 253 136 254'),
        (bands == [0, 1, 2, 3, 6, 4, 5, 6, 6, 6, 6, 6, 6, 6, 6, 7, 0], 'the band map lies between them'),
        (bmode[:9] == [231, 120, 48, 89, 115, 113, 120, 152, 112], 'the mode probabilities begin 231 120 48'),
        (bmode[-9:] == [112, 19, 12, 61, 195, 128, 48, 4, 24], 'and end 112 19 12 61 195 128 48 4 24'),
        (min(upd + coef + bmode) >= 1, 'every probability is 1 to 255'),
    ]
    for ok, what in checks:
        if not ok:
            sys.exit('not as RFC 6386 has it: ' + what)

    def rows(name, typ, values, per):
        out = [f'\t{typ} {name}:']
        for i in range(0, len(values), per):
            out.append('\t\t' + ' '.join(str(v) for v in values[i:i + per]))
        out[-1] += ';'
        return '\n'.join(out)
    text = f'''# Lossy WebP's fixed tables (VP8, RFC 6386), made by tools/image/vp8_tables.py from libwebp's own
# library and checked there against the values the RFC gives. Don't change them by hand.

phi.ImgVp8Tables:Library
{{
	# the quantizer's steps by index (14.1)
{rows('dc', 'u8', dc, 16)}
{rows('ac', 'u16', ac, 16)}
	# the probabilities that a coefficient probability is updated, [type][band][context][node] (13.4)
{rows('update', 'u8', upd, 11)}
	# the coefficient probabilities a key frame starts with (13.5)
{rows('coef', 'u8', coef, 11)}
	# which band each position of a block is in
{rows('bands', 'u8', bands, 17)}
	# a key frame's 4x4 modes' probabilities, [above][left][node] (12.3)
{rows('bmode', 'u8', bmode, 9)}

	# These few are written here, not taken from libwebp: they're short and the RFC's own.
	# The 4x4 modes' tree (12.3), in libwebp's numbering of the modes, which its table above uses:
	# DC 0, TM 1, VE 2, HE 3, RD 4, VR 5, LD 6, VL 7, HD 8, HU 9. At node i, a bit of probability
	# i picks tree:(2 i + bit): a node above 0, or a mode as 0 or below (its number, negated).
	int tree: 0 1 -1 2 -2 3 4 6 -3 5 -4 -5 -6 7 -7 8 -8 -9;
	# a block's positions in the order its coefficients come (13)
	u8 zigzag: 0 1 4 8 5 2 3 6 9 12 13 10 7 11 14 15;
	# the extra bits' probabilities of the large categories, 3 to 6, each list ending in 0 (13.2)
	u8 cats: 173 148 140 0 176 155 140 135 0 180 157 141 134 130 0 254 254 243 230 196 177 153 140 133 130 129 0;
	u8 cat_at: 0 4 9 15;
}}
'''
    path = os.path.join(ROOT, 'libs', 'image', 'imagelib', 'vp8tables.phi')
    with open(path, 'w', newline='\n') as f:
        f.write(text)
    print('wrote', path, 'from', lib, '(every check passed)')


if __name__ == '__main__':
    main()
