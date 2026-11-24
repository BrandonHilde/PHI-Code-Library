#!/usr/bin/env python3
"""Make libs/media/medialib/vorbistables.phi: Vorbis's floor1_inverse_dB_table, from the Vorbis I
specification (xiph.org/vorbis/doc/Vorbis_I_spec.html, section 10.1), as whole numbers.

    python3 tools/media/vorbis_tables.py PATH/TO/Vorbis_I_spec.html

Each of the 256 values (1.0649863e-07 to 1) is written as a mantissa m below 2^31 and a shift s,
value = m / 2^s, m the nearest whole number with its top bit at 30, so each keeps 31 bits of the
spec's 8 significant digits.
"""
import re, sys, html, os
t = open(sys.argv[1], encoding='utf-8', errors='replace').read()
t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', t)))
i = t.index('is a 256 element static lookup table')
j = t.index('Embedding Vorbis into an Ogg stream', i)
vals = [float(x) for x in re.findall(r'\d\.\d+e-\d+|\d+\.\d+|\b1\.(?!\d)', t[i + 40:j])]
assert len(vals) == 256, len(vals)
assert vals[0] == 1.0649863e-07 and vals[255] == 1.0, (vals[0], vals[255])
assert all(a < b for a, b in zip(vals, vals[1:]))
ms = []; ss = []
for v in vals:
    s = 0
    while v * (1 << s) < (1 << 30):
        s += 1
    m = round(v * (1 << s))
    if m >= (1 << 31):
        m //= 2; s -= 1
    ms.append(m); ss.append(s)
out = ['# Vorbis\'s fixed table, made by tools/media/vorbis_tables.py from the Vorbis I specification',
       '# (10.1). Don\'t change it by hand.', '', 'phi.MdVorbisTables:Library', '{',
       '\t# floor1_inverse_dB_table: value i is db_m:i / 2^(db_s:i)', '\tu32 db_m:']
for k in range(0, 256, 8):
    out.append('\t\t' + ' '.join(str(m) for m in ms[k:k + 8]))
out[-1] += ';'
out.append('\tu8 db_s:')
for k in range(0, 256, 16):
    out.append('\t\t' + ' '.join(str(s) for s in ss[k:k + 16]))
out[-1] += ';'
out.append('}')
dest = os.path.join(os.path.dirname(__file__), '..', '..', 'libs', 'media', 'medialib', 'vorbistables.phi')
open(dest, 'w').write('\n'.join(out) + '\n')
print('wrote', os.path.normpath(dest), ': shifts', min(ss), 'to', max(ss))
